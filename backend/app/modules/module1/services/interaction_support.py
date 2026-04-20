from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
import zipfile
from functools import lru_cache
from typing import Any, Iterator

from ..core.config import get_settings
from .agent_service import LayoutExpertAgent
from .document_io_support import IMAGE_EXTENSIONS, Image, pdfplumber


logger = logging.getLogger(__name__)

ANALYSIS_FIRST_TOKEN_TIMEOUT_SEC = 18.0
ANALYSIS_KEYWORDS = ("分析", "总结", "摘要", "提取", "查找", "统计", "概括", "归纳", "识别", "ocr", "报告", "解读", "研判")
IMAGE_KEYWORDS = ("图片", "图表", "图", "柱状图", "饼图", "折线图", "扫描件", "截图", "fig", "chart", "数据")


@lru_cache(maxsize=1)
def _get_agent() -> LayoutExpertAgent:
    return LayoutExpertAgent(get_settings())


def _build_local_chat_reply(
    instruction: str,
    conversation_context: list[dict[str, str]],
    extra_hint: str = "",
) -> str:
    text = (instruction or "").strip()
    if not text:
        return "现在模块一支持不上传文件直接聊天。你可以直接问我怎么处理文档，或者先描述你想执行的操作。"

    if any(keyword in text for keyword in ("格式", "支持", "文件类型", "上传")):
        return (
            "模块一当前支持 PDF、DOC、DOCX、TXT、XLS、XLSX、MD，以及 JPG、JPEG、PNG、GIF、BMP、WEBP。"
            "没有文件时也可以直接聊天，用来先梳理需求、整理提示词或确认处理思路。"
        )

    hint_suffix = f"\n\n补充信息：{extra_hint}" if extra_hint else ""
    context_suffix = "\n\n我会继续沿着你当前这段对话往下回答，不会擅自重置上下文。" if conversation_context else ""
    return (
        "现在模块一已经支持无文件聊天入口了。"
        "如果当前环境已经配置了模块一可用的 LLM API Key，这里会直接返回真实的 AI 回复；"
        "如果还没配置，我会先给出本地兜底说明，帮助你继续往下走。"
        "\n\n你可以继续这样用："
        "\n1. 直接描述你想对文档做什么。"
        "\n2. 让我帮你把需求改写成更适合文档处理的指令。"
        "\n3. 先不上传文件，只讨论分析或修改思路。"
        f"{context_suffix}"
        f"{hint_suffix}"
    )


def _build_local_document_reply(
    instruction: str,
    documents: list[dict[str, Any]],
    conversation_context: list[dict[str, str]],
    extra_hint: str = "",
) -> str:
    if not documents:
        return _build_local_chat_reply(instruction, conversation_context, extra_hint)

    if len(documents) == 1:
        document = documents[0]
        filename = str(document.get("filename") or "未命名文件")
        simple_content = str(document.get("simple_content") or "").strip()
        file_ext = str(document.get("working_ext") or "").strip()

        if file_ext in IMAGE_EXTENSIONS and not simple_content:
            base_text = (
                f"已收到文件 `{filename}`，但当前环境还没有可用的 AI 图片理解能力。"
                "后端已经不会因为无文件或有文件聊天而启动失败了；"
                "如果要得到图片内容分析，请先配置模块一可用的 LLM API Key 后再试。"
            )
            if extra_hint:
                return f"{base_text}\n\n补充信息：{extra_hint}"
            return base_text

        if simple_content:
            preview = simple_content[:600]
            base_text = (
                f"已收到文件 `{filename}`。当前环境未配置可用的模块一 LLM，所以先返回本地提取到的内容片段供你确认：\n\n"
                f"{preview}\n\n"
                "配置模块一可用的 LLM API Key 后，就可以继续获得真正的智能分析、总结和修改建议。"
            )
            if extra_hint:
                return f"{base_text}\n\n补充信息：{extra_hint}"
            return base_text

        base_text = (
            f"已收到文件 `{filename}`，但当前没有提取到足够文本。"
            "后端现在已经支持有文件和无文件两种聊天入口，不会再因为这条链路导致服务起不来；"
            "如果要继续做智能分析，请确认文件内容可提取，并配置模块一可用的 LLM API Key。"
        )
        if extra_hint:
            return f"{base_text}\n\n补充信息：{extra_hint}"
        return base_text

    file_names = "、".join(str(document.get("filename") or "未命名文件") for document in documents)
    preview_blocks = []
    for document in documents[:3]:
        preview = str(document.get("simple_content") or "").strip()
        if preview:
            preview_blocks.append(f"【{document.get('filename') or '未命名文件'}】\n{preview[:240]}")

    base_text = (
        f"已收到本批次 {len(documents)} 份文件：{file_names}。"
        "当前环境未配置可用的模块一 LLM，所以先返回本地提取到的多文件内容片段供你确认。"
    )
    if preview_blocks:
        base_text = f"{base_text}\n\n" + "\n\n".join(preview_blocks)
    if conversation_context:
        base_text = f"{base_text}\n\n我会继续沿着这批文档对应的当前对话上下文往下处理。"
    if extra_hint:
        return f"{base_text}\n\n补充信息：{extra_hint}"
    return base_text


def _build_local_analysis_report(
    instruction: str,
    documents: list[dict[str, Any]],
    extra_hint: str = "",
) -> str:
    if not documents:
        return "一、分析概览\n\n1. 当前状态\n\n(1) 暂未收到可分析文件。"

    focus_document = documents[0]
    focus_name = str(focus_document.get("filename") or "未命名文件")
    focus_content = str(
        focus_document.get("simple_content")
        or focus_document.get("doc_content")
        or ""
    ).strip()
    all_names = "、".join(str(document.get("filename") or "未命名文件") for document in documents)

    candidate_lines: list[str] = []
    for raw_line in focus_content.splitlines():
        cleaned = re.sub(r"\s+", " ", raw_line).strip(" -•*\t")
        if len(cleaned) < 8:
            continue
        if cleaned in candidate_lines:
            continue
        candidate_lines.append(cleaned)
        if len(candidate_lines) >= 4:
            break

    if not candidate_lines and focus_content:
        collapsed = re.sub(r"\s+", " ", focus_content).strip()
        if collapsed:
            candidate_lines.append(collapsed[:120])

    summary_lines = candidate_lines or ["当前文档已完成文本提取，但暂未整理出足够稳定的摘要片段。"]
    summary_block = "\n".join(f"({index}) {line}" for index, line in enumerate(summary_lines, start=1))

    guidance_lines = [
        "(1) 可以先缩小分析范围，例如只分析某一页、某个章节或某个字段。",
        "(2) 如果文档较大，建议先用“提取关键信息”再继续做深度分析。",
        "(3) 当前结果来自本地提取摘要，可继续重试 AI 分析获取更完整报告。",
    ]
    guidance_block = "\n".join(guidance_lines)
    hint_line = f"\n\n(4) {extra_hint}" if extra_hint else ""

    return (
        "一、分析概览\n\n"
        "1. 本次处理对象\n\n"
        f"(1) 当前共收到 {len(documents)} 份文档：{all_names}。\n"
        f"(2) 当前焦点文档为《{focus_name}》。\n"
        f"(3) 用户请求为：{instruction or '未提供明确指令'}。\n\n"
        "二、已提取的核心内容\n\n"
        f"1. 重点摘录\n\n{summary_block}\n\n"
        "三、后续建议\n\n"
        f"1. 建议操作\n\n{guidance_block}{hint_line}"
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stage_payload(stage_id: str) -> dict[str, Any]:
    stage_map = {
        "request_received": {
            "id": "request_received",
            "label": "已收到分析请求",
            "description": "正在准备处理",
            "progress": 10,
            "status": "active",
        },
        "extracting_text": {
            "id": "extracting_text",
            "label": "正在提取文档内容",
            "description": "正在整理可供分析的正文内容",
            "progress": 35,
            "status": "active",
        },
        "preparing_analysis": {
            "id": "preparing_analysis",
            "label": "正在准备分析",
            "description": "正在整理重点内容",
            "progress": 55,
            "status": "active",
        },
        "generating_report": {
            "id": "generating_report",
            "label": "正在生成分析报告",
            "description": "报告内容会持续更新",
            "progress": 80,
            "status": "active",
        },
        "completed": {
            "id": "completed",
            "label": "分析已完成",
            "description": "报告已生成完成，可继续阅读、编辑或下载",
            "progress": 100,
            "status": "completed",
        },
        "fallback_completed": {
            "id": "fallback_completed",
            "label": "已切换为本地摘要",
            "description": "AI 响应较慢，已先返回本地摘要",
            "progress": 100,
            "status": "fallback",
        },
        "failed": {
            "id": "failed",
            "label": "分析失败",
            "description": "请重试，或缩小分析范围",
            "progress": 100,
            "status": "failed",
        },
    }
    return stage_map[stage_id]


def _stage_sse(stage_id: str) -> str:
    return _sse({"type": "stage", "content": _stage_payload(stage_id)})


def _chunk_text(text: str, chunk_size: int = 18) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return [""]
    return [content[index:index + chunk_size] for index in range(0, len(content), chunk_size)]


def _is_analysis_instruction(instruction: str) -> bool:
    normalized = (instruction or "").lower()
    return any(keyword in normalized for keyword in ANALYSIS_KEYWORDS)


def _parse_conversation_context(raw_context: str) -> list[dict[str, str]]:
    if not raw_context:
        return []

    try:
        parsed = json.loads(raw_context)
    except Exception:
        return []

    if not isinstance(parsed, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in parsed[-12:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"system", "user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content[:2000]})
    return normalized


def _stream_plain_chat_events(
    instruction: str,
    conversation_context: list[dict[str, str]],
) -> Iterator[str]:
    agent = _get_agent()
    try:
        if agent.available:
            for chunk in agent.stream_chat(instruction, conversation_context):
                yield _sse({"type": "chunk", "content": chunk})
        else:
            for chunk in _chunk_text(_build_local_chat_reply(instruction, conversation_context)):
                yield _sse({"type": "chunk", "content": chunk})
        yield _sse({"type": "end"})
    except Exception as exc:
        logger.warning("纯聊天 AI 调用失败，切换到本地兜底回复: %s", exc)
        fallback_text = _build_local_chat_reply(
            instruction,
            conversation_context,
            extra_hint=str(exc),
        )
        for chunk in _chunk_text(fallback_text):
            yield _sse({"type": "chunk", "content": chunk})
        yield _sse({"type": "end"})


def _describe_visual_content(file_path: str, file_ext: str, instruction: str) -> str:
    agent = _get_agent()
    if not agent.available:
        return ""

    normalized_instruction = (instruction or "").lower()
    if file_ext in IMAGE_EXTENSIONS:
        return agent.describe_images([file_path], max_images=1)
    if file_ext not in {".pdf", ".docx"}:
        return ""
    if not any(keyword in normalized_instruction for keyword in IMAGE_KEYWORDS):
        return ""

    with tempfile.TemporaryDirectory(prefix="module1_images_") as image_dir:
        image_paths: list[str] = []
        if file_ext == ".docx":
            image_paths = _extract_images_from_docx(file_path, image_dir)
        elif file_ext == ".pdf":
            image_paths = _extract_images_from_pdf(file_path, image_dir)
        if not image_paths:
            return ""
        return agent.describe_images(image_paths, max_images=3)


def _extract_images_from_docx(docx_path: str, output_dir: str) -> list[str]:
    if Image is None:
        return []

    images: list[str] = []
    with zipfile.ZipFile(docx_path, "r") as docx_zip:
        for file_name in docx_zip.namelist():
            lower_name = file_name.lower()
            if not lower_name.startswith("word/media/"):
                continue
            if not lower_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                continue
            try:
                image_data = docx_zip.read(file_name)
                image = Image.open(io.BytesIO(image_data))
                save_path = os.path.join(output_dir, os.path.basename(file_name))
                image.save(save_path)
                images.append(save_path)
            except Exception:
                logger.exception("从 docx 提取图片失败: %s", file_name)
    return images


def _extract_images_from_pdf(pdf_path: str, output_dir: str) -> list[str]:
    if pdfplumber is None or Image is None:
        return []

    images: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                for image_index, image in enumerate(page.images, start=1):
                    try:
                        stream = image.get("stream")
                        if stream is None:
                            continue
                        image_data = stream.get_data()
                        picture = Image.open(io.BytesIO(image_data))
                        save_path = os.path.join(output_dir, f"page_{page_index}_{image_index}.png")
                        picture.save(save_path)
                        images.append(save_path)
                    except Exception:
                        logger.exception("从 PDF 提取单张图片失败")
    except Exception:
        logger.exception("从 PDF 提取图片失败")
    return images


__all__ = [
    "ANALYSIS_FIRST_TOKEN_TIMEOUT_SEC",
    "_build_local_analysis_report",
    "_build_local_chat_reply",
    "_build_local_document_reply",
    "_chunk_text",
    "_describe_visual_content",
    "_get_agent",
    "_is_analysis_instruction",
    "_parse_conversation_context",
    "_sse",
    "_stage_payload",
    "_stage_sse",
    "_stream_plain_chat_events",
]
