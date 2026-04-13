from __future__ import annotations

from difflib import SequenceMatcher
import io
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional
from xml.etree import ElementTree as ET
import urllib.parse

from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from core.config import get_settings
from models import SavedUpload
from services.agent_service import LayoutExpertAgent
from services.conversion_service import (
    convert_doc_bytes_to_docx,
    convert_word_bytes_to_pdf,
    is_word_file,
)
from services.sandbox_service import cleanup_temp_paths, derive_output_path, save_upload_to_temp


logger = logging.getLogger(__name__)

ANALYSIS_KEYWORDS = ("分析", "总结", "摘要", "提取", "查找", "统计", "概括", "归纳", "识别", "ocr", "报告", "解读", "研判")
IMAGE_KEYWORDS = ("图片", "图表", "图", "柱状图", "饼图", "折线图", "扫描件", "截图", "fig", "chart", "数据")
TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
SPREADSHEET_EXTENSIONS = {".xlsx"}
WORD_EXTENSIONS = {".doc", ".docx"}
SUPPORTED_UPLOAD_ORDER = (".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xlsx", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
SUPPORTED_UPLOAD_EXTENSIONS = set(SUPPORTED_UPLOAD_ORDER)
TEXT_FILE_ENCODINGS = ("utf-8", "utf-8-sig", "gbk")
COLOR_NAME_MAP = {
    "red": "#FF0000",
    "blue": "#0000FF",
    "green": "#00FF00",
    "yellow": "#FFFF00",
    "purple": "#800080",
    "orange": "#FFA500",
    "black": "#000000",
    "white": "#FFFFFF",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "gray": "#808080",
    "grey": "#808080",
    "红色": "#FF0000",
    "蓝色": "#0000FF",
    "绿色": "#00FF00",
    "黄色": "#FFFF00",
    "紫色": "#800080",
    "橙色": "#FFA500",
    "黑色": "#000000",
    "白色": "#FFFFFF",
    "灰色": "#808080",
}

try:
    import PyPDF2
except ImportError:  # pragma: no cover - optional dependency
    PyPDF2 = None

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.shared import Pt, RGBColor
    from docx.text.paragraph import Paragraph
except ImportError:  # pragma: no cover - optional dependency
    docx = None
    WD_ALIGN_PARAGRAPH = None
    OxmlElement = None
    Paragraph = None
    Pt = None
    RGBColor = None

try:
    import pdfplumber
except ImportError:  # pragma: no cover - optional dependency
    pdfplumber = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency
    Image = None


@lru_cache(maxsize=1)
def _get_agent() -> LayoutExpertAgent:
    return LayoutExpertAgent(get_settings().zhipu_api_key)


def build_health_response() -> dict[str, Any]:
    agent = _get_agent()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "libreoffice_available": _libreoffice_available(),
        "ai_available": agent.available,
        "modules": {
            "office_pdf": True,
            "pypdf2": PyPDF2 is not None,
            "python_docx": docx is not None,
            "zhipuai": agent.available,
        },
    }


async def handle_convert_docx_to_pdf(file: UploadFile) -> Response:
    settings = get_settings()
    filename = (file.filename or "").strip()
    if not filename:
        return JSONResponse(status_code=400, content={"error": "空文件名"})

    file_bytes = await file.read()
    if not file_bytes:
        return JSONResponse(status_code=400, content={"error": "空文件"})
    if len(file_bytes) > settings.max_file_bytes:
        return JSONResponse(status_code=400, content={"error": f"文件大小超过 {settings.max_file_mb}MB 限制"})
    if not is_word_file(filename):
        return JSONResponse(status_code=400, content={"error": f"不支持的文件类型: {filename}"})
    if not _matches_file_signature(Path(filename).suffix.lower(), file_bytes):
        return JSONResponse(status_code=400, content={"error": "文件内容与扩展名不匹配，请重新上传正确的 Word 文件"})

    try:
        pdf_bytes, _ = convert_word_bytes_to_pdf(file_name=filename, file_bytes=file_bytes, timeout_sec=90.0)
    except Exception as exc:
        logger.exception("Word 转 PDF 失败")
        return JSONResponse(status_code=500, content={"error": f"转换失败: {exc}"})

    output_name = f"{Path(filename).stem}.pdf"
    encoded_filename = urllib.parse.quote(output_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}"
        },
    )


async def handle_save_edited_document(file: UploadFile, content: str) -> Response:
    settings = get_settings()
    saved_upload: SavedUpload | None = None
    extra_paths: list[str] = []
    output_path = ""

    try:
        saved_upload = await save_upload_to_temp(
            file,
            max_file_bytes=settings.max_file_bytes,
            max_file_mb=settings.max_file_mb,
        )
        extra_paths.append(saved_upload.path)

        source_ext = _validate_saved_upload(saved_upload)
        normalized_content = str(content or "").replace("\r", "")

        if source_ext in {".doc", ".docx"}:
            output_name = f"edited_{Path(saved_upload.filename).stem}.docx"
            output_path = str(Path(saved_upload.path).with_name(output_name))
            _write_content_to_docx(output_path, normalized_content)
            media_type = _media_type_for_name(output_name)
        elif source_ext in TEXT_EXTENSIONS:
            output_name = f"edited_{saved_upload.filename}"
            output_path = str(Path(saved_upload.path).with_name(output_name))
            with open(output_path, "w", encoding="utf-8") as output_file:
                output_file.write(normalized_content)
            media_type = _media_type_for_name(output_name)
        else:
            return JSONResponse(status_code=400, content={"error": f"当前文件类型暂不支持直接保存编辑稿: {source_ext or 'unknown'}"})

        with open(output_path, "rb") as output_file:
            output_bytes = output_file.read()

        encoded_name = urllib.parse.quote(output_name)
        return Response(
            content=output_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={encoded_name}; filename*=UTF-8''{encoded_name}"
            },
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("保存编辑稿失败")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        cleanup_temp_paths(output_path, *extra_paths)


async def handle_apply_modifications(file: UploadFile, modifications_json: str) -> Response:
    settings = get_settings()
    saved_upload: SavedUpload | None = None
    extra_paths: list[str] = []
    output_path = ""

    try:
        modifications = _normalize_modifications_payload(modifications_json)
        saved_upload = await save_upload_to_temp(
            file,
            max_file_bytes=settings.max_file_bytes,
            max_file_mb=settings.max_file_mb,
        )
        extra_paths.append(saved_upload.path)

        source_ext = _validate_saved_upload(saved_upload)
        output_name = f"modified_{saved_upload.filename}"
        media_type = _media_type_for_name(saved_upload.filename)

        if source_ext in {".docx", ".doc"}:
            working_path, converted_path = _prepare_docx_source(saved_upload)
            if converted_path:
                extra_paths.append(converted_path)
                output_name = f"modified_{Path(saved_upload.filename).stem}.docx"
                media_type = _media_type_for_name(output_name)
            output_path = _apply_modifications_to_docx(working_path, modifications)
        elif source_ext in TEXT_EXTENSIONS:
            output_path = _apply_modifications_to_text(saved_upload.path, modifications)
        elif source_ext == ".pdf":
            extracted_text = _extract_text_from_pdf(saved_upload.path)
            if not extracted_text.strip():
                return JSONResponse(status_code=400, content={"error": "PDF 未提取到可修改文本，暂时无法生成修改版"})

            if docx is not None:
                working_path = str(Path(saved_upload.path).with_name(f"{Path(saved_upload.filename).stem}_extracted.docx"))
                _write_content_to_docx(working_path, extracted_text)
                extra_paths.append(working_path)
                output_name = f"modified_{Path(saved_upload.filename).stem}.docx"
                media_type = _media_type_for_name(output_name)
                output_path = _apply_modifications_to_docx(working_path, modifications)
            else:
                working_path = str(Path(saved_upload.path).with_name(f"{Path(saved_upload.filename).stem}_extracted.txt"))
                with open(working_path, "w", encoding="utf-8") as temp_text_file:
                    temp_text_file.write(extracted_text)
                extra_paths.append(working_path)
                output_name = f"modified_{Path(saved_upload.filename).stem}.txt"
                media_type = _media_type_for_name(output_name)
                output_path = _apply_modifications_to_text(working_path, modifications)
        else:
            return JSONResponse(status_code=400, content={"error": f"不支持的文件类型: {source_ext or 'unknown'}"})

        with open(output_path, "rb") as output_file:
            output_bytes = output_file.read()

        return Response(
            content=output_bytes,
            media_type=media_type,
            headers=_build_download_headers(output_name, len(modifications), applied=True),
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("应用修改失败")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        cleanup_temp_paths(output_path, *extra_paths)


async def handle_operate_stream(
    files: Optional[list[UploadFile]],
    instruction: str,
    *,
    conversation_context: str = "[]",
    selected_file_name: str = "",
) -> StreamingResponse:
    async def generate() -> Iterator[str]:
        prompt = (instruction or "").strip()
        context_messages = _parse_conversation_context(conversation_context)
        normalized_files = [upload for upload in (files or []) if upload is not None]
        if not prompt:
            for chunk in _chunk_text("可以直接输入你想分析、提取、润色或修改的需求。没有文件时也可以先聊天。"):
                yield _sse({"type": "chunk", "content": chunk})
            yield _sse({"type": "end"})
            return

        if not normalized_files:
            for event in _stream_plain_chat_events(prompt, context_messages):
                yield event
            return

        settings = get_settings()
        temp_paths: list[str] = []

        try:
            prepared_documents: list[dict[str, Any]] = []
            for upload in normalized_files:
                saved_upload = await save_upload_to_temp(
                    upload,
                    max_file_bytes=settings.max_file_bytes,
                    max_file_mb=settings.max_file_mb,
                )
                temp_paths.append(saved_upload.path)
                _validate_saved_upload(saved_upload)

                working_path, converted_path = _prepare_docx_source(saved_upload)
                if converted_path:
                    temp_paths.append(converted_path)

                working_ext = Path(working_path).suffix.lower()
                doc_content = _extract_text(working_path, working_ext)
                simple_content = _extract_text_simple(working_path, working_ext)

                visual_summary = _describe_visual_content(working_path, working_ext, prompt)
                if visual_summary:
                    doc_content = f"{doc_content}\n\n{visual_summary}".strip()
                    simple_content = f"{simple_content}\n\n{visual_summary}".strip()

                prepared_documents.append(
                    {
                        "filename": saved_upload.filename,
                        "working_ext": working_ext,
                        "doc_content": doc_content,
                        "simple_content": simple_content,
                    }
                )

            focus_document = _select_focus_document(prepared_documents, selected_file_name)
            focus_file_name = str((focus_document or {}).get("filename") or "")
            combined_simple_content = _build_document_context_summary(
                prepared_documents,
                focus_file_name=focus_file_name,
                field_name="simple_content",
            )
            combined_doc_content = _build_document_context_summary(
                prepared_documents,
                focus_file_name=focus_file_name,
                field_name="doc_content",
            )

            agent = _get_agent()
            if not agent.available:
                fallback_text = _build_local_document_reply(
                    prompt,
                    prepared_documents,
                    context_messages,
                )
                for chunk in _chunk_text(fallback_text):
                    yield _sse({"type": "chunk", "content": chunk})
                inferred_modifications = _infer_modifications_from_instruction(prompt)
                if inferred_modifications and not _is_analysis_instruction(prompt):
                    for chunk in _chunk_text("当前未配置 AI，已按本地规则生成基础修改方案，你可以直接继续应用。"):
                        yield _sse({"type": "chunk", "content": chunk})
                    yield _sse({"type": "modifications", "content": inferred_modifications})
                yield _sse({"type": "end"})
                return

            try:
                if _is_analysis_instruction(prompt):
                    content_for_analysis = combined_simple_content or combined_doc_content or "未提取到可分析文本。"
                    for chunk in agent.stream_analysis(prompt, content_for_analysis, context_messages):
                        yield _sse({"type": "chunk", "content": chunk})
                else:
                    planning_document = focus_document or prepared_documents[0]
                    planning_filename = str(planning_document.get("filename") or "未命名文档")
                    planning_content = (
                        str(planning_document.get("doc_content") or "").strip()
                        or str(planning_document.get("simple_content") or "").strip()
                        or "未提取到可修改文本。"
                    )

                    if len(prepared_documents) > 1:
                        planning_content = (
                            f"{planning_content}\n\n"
                            "同批次其他文档（只作辅助参考，不要混淆正文内容）：\n"
                            f"{_build_document_context_summary(prepared_documents, focus_file_name=focus_file_name, field_name='simple_content')}"
                        )

                    full_response = agent.plan_modifications(
                        prompt,
                        planning_filename,
                        planning_content,
                        context_messages,
                    )
                    explanation = _extract_text_explanation(full_response)
                    if not explanation:
                        explanation = "已根据你的指令生成修改方案，下面会进入修改应用流程。"
                    for chunk in _chunk_text(explanation):
                        yield _sse({"type": "chunk", "content": chunk})

                    modifications = _parse_ai_modifications(full_response)
                    inferred_modifications = _infer_modifications_from_instruction(prompt)
                    if inferred_modifications:
                        modifications = _deduplicate_modifications([*modifications, *inferred_modifications])
                    if modifications:
                        yield _sse({"type": "modifications", "content": modifications})
            except Exception as exc:
                logger.warning("AI 文档操作失败，切换到本地兜底回复: %s", exc)
                fallback_text = _build_local_document_reply(
                    prompt,
                    prepared_documents,
                    context_messages,
                    extra_hint="AI 服务暂时不可用，已返回本地兜底内容。",
                )
                for chunk in _chunk_text(fallback_text):
                    yield _sse({"type": "chunk", "content": chunk})
                inferred_modifications = _infer_modifications_from_instruction(prompt)
                if inferred_modifications and not _is_analysis_instruction(prompt):
                    for chunk in _chunk_text("AI 服务暂时不可用，已切换到本地规则并生成基础修改方案。"):
                        yield _sse({"type": "chunk", "content": chunk})
                    yield _sse({"type": "modifications", "content": inferred_modifications})

            yield _sse({"type": "end"})
        except ValueError as exc:
            yield _sse({"type": "error", "content": str(exc)})
        except Exception as exc:
            logger.exception("流式操作失败")
            yield _sse({"type": "error", "content": str(exc)})
        finally:
            cleanup_temp_paths(*temp_paths)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_plain_chat_events(instruction: str, conversation_context: list[dict[str, str]]) -> Iterator[str]:
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
        fallback_text = _build_local_chat_reply(instruction, conversation_context, extra_hint=str(exc))
        for chunk in _chunk_text(fallback_text):
            yield _sse({"type": "chunk", "content": chunk})
        yield _sse({"type": "end"})


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


def _select_focus_document(
    documents: list[dict[str, Any]],
    selected_file_name: str,
) -> dict[str, Any] | None:
    normalized_name = str(selected_file_name or "").strip()
    if not documents:
        return None
    if not normalized_name:
        return documents[0]

    for document in documents:
        if str(document.get("filename") or "").strip() == normalized_name:
            return document
    return documents[0]


def _build_document_context_summary(
    documents: list[dict[str, Any]],
    *,
    focus_file_name: str = "",
    field_name: str = "simple_content",
) -> str:
    summaries: list[str] = []
    for index, document in enumerate(documents, start=1):
        file_name = str(document.get("filename") or f"文档{index}")
        content = str(document.get(field_name) or document.get("simple_content") or document.get("doc_content") or "").strip()
        content = content[:4000] if content else "未提取到可用文本。"
        focus_suffix = "（当前焦点文档）" if focus_file_name and file_name == focus_file_name else ""
        summaries.append(f"【文档{index}】{file_name}{focus_suffix}\n{content}")
    return "\n\n".join(summaries)


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
        "如果当前环境配置了 `ZHIPU_API_KEY`，这里会直接返回真实的 AI 回复；"
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
                "如果要得到图片内容分析，请配置 `ZHIPU_API_KEY` 后再试。"
            )
            if extra_hint:
                return f"{base_text}\n\n补充信息：{extra_hint}"
            return base_text

        if simple_content:
            preview = simple_content[:600]
            base_text = (
                f"已收到文件 `{filename}`。当前环境未配置可用的智谱 AI，所以先返回本地提取到的内容片段供你确认：\n\n"
                f"{preview}\n\n"
                "配置 `ZHIPU_API_KEY` 后，就可以继续获得真正的智能分析、总结和修改建议。"
            )
            if extra_hint:
                return f"{base_text}\n\n补充信息：{extra_hint}"
            return base_text

        base_text = (
            f"已收到文件 `{filename}`，但当前没有提取到足够文本。"
            "后端现在已经支持有文件和无文件两种聊天入口，不会再因为这条链路导致服务起不来；"
            "如果要继续做智能分析，请确认文件内容可提取，并配置 `ZHIPU_API_KEY`。"
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
        "当前环境未配置可用的智谱 AI，所以先返回本地提取到的多文件内容片段供你确认。"
    )
    if preview_blocks:
        base_text = f"{base_text}\n\n" + "\n\n".join(preview_blocks)
    if conversation_context:
        base_text = f"{base_text}\n\n我会继续沿着这批文档对应的当前对话上下文往下处理。"
    if extra_hint:
        return f"{base_text}\n\n补充信息：{extra_hint}"
    return base_text


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, chunk_size: int = 18) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return [""]
    return [content[index:index + chunk_size] for index in range(0, len(content), chunk_size)]


def _is_analysis_instruction(instruction: str) -> bool:
    normalized = (instruction or "").lower()
    return any(keyword in normalized for keyword in ANALYSIS_KEYWORDS)


def _libreoffice_available() -> bool:
    env_candidates = [os.getenv("MODULE1_SOFFICE_PATH", "").strip(), os.getenv("MODULE2_SOFFICE_PATH", "").strip()]
    for item in env_candidates:
        if item and Path(item).exists():
            return True
    return shutil.which("soffice") is not None


def _media_type_for_name(file_name: str) -> str:
    ext = Path(file_name or "").suffix.lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == ".doc":
        return "application/msword"
    if ext == ".md":
        return "text/markdown"
    if ext in {".txt", ".csv"}:
        return "text/plain"
    return "application/octet-stream"


def _build_download_headers(file_name: str, modification_count: int, *, applied: bool) -> dict[str, str]:
    encoded_name = urllib.parse.quote(file_name)
    return {
        "Content-Disposition": f"attachment; filename={encoded_name}; filename*=UTF-8''{encoded_name}",
        "X-Modification-Applied": "true" if applied else "false",
        "X-Modification-Count": str(modification_count),
    }


def _supported_upload_types_text() -> str:
    return "PDF、DOC、DOCX、TXT、MD、CSV、XLSX、JPG、JPEG、PNG、GIF、BMP、WEBP"


def _validate_saved_upload(saved_upload: SavedUpload) -> str:
    source_ext = Path(saved_upload.filename).suffix.lower()
    if source_ext not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError(f"不支持的文件类型: {source_ext or saved_upload.filename}。当前支持：{_supported_upload_types_text()}")
    if not _matches_file_signature(source_ext, saved_upload.file_bytes):
        raise ValueError("文件内容与扩展名不匹配，请确认上传了正确的文件类型")
    return source_ext


def _matches_file_signature(file_ext: str, file_bytes: bytes) -> bool:
    if not file_bytes:
        return False

    sample = file_bytes[:32]
    normalized_ext = str(file_ext or "").lower()

    if normalized_ext in TEXT_EXTENSIONS:
        return _looks_like_text_payload(file_bytes)
    if normalized_ext == ".pdf":
        return sample.startswith(b"%PDF-")
    if normalized_ext == ".doc":
        return sample.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if normalized_ext in {".docx", ".xlsx"}:
        if not zipfile.is_zipfile(io.BytesIO(file_bytes)):
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return False
        if normalized_ext == ".docx":
            return "word/document.xml" in names
        return "xl/workbook.xml" in names
    if normalized_ext == ".png":
        return sample.startswith(b"\x89PNG\r\n\x1a\n")
    if normalized_ext in {".jpg", ".jpeg"}:
        return sample.startswith(b"\xff\xd8\xff")
    if normalized_ext == ".gif":
        return sample.startswith((b"GIF87a", b"GIF89a"))
    if normalized_ext == ".bmp":
        return sample.startswith(b"BM")
    if normalized_ext == ".webp":
        return sample.startswith(b"RIFF") and sample[8:12] == b"WEBP"
    return False


def _looks_like_text_payload(file_bytes: bytes) -> bool:
    sample = file_bytes[:4096]
    if not sample:
        return False
    if b"\x00" in sample:
        return False
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            sample.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def _normalize_modifications_payload(raw_payload: str) -> list[dict[str, Any]]:
    payload = raw_payload or "[]"
    parsed = json.loads(payload)
    if isinstance(parsed, dict):
        parsed = parsed.get("modifications", [])
    if not isinstance(parsed, list):
        raise ValueError("修改方案必须是数组")
    return [item for item in parsed if isinstance(item, dict)]


def _prepare_docx_source(saved_upload: SavedUpload) -> tuple[str, str]:
    ext = Path(saved_upload.filename).suffix.lower()
    if ext != ".doc":
        return saved_upload.path, ""

    converted_bytes, _ = convert_doc_bytes_to_docx(
        file_name=saved_upload.filename,
        file_bytes=saved_upload.file_bytes,
        timeout_sec=90.0,
    )
    converted_path = f"{saved_upload.path}.docx"
    with open(converted_path, "wb") as converted_file:
        converted_file.write(converted_bytes)
    return converted_path, converted_path


def _extract_text(file_path: str, file_ext: str) -> str:
    if file_ext == ".pdf":
        return _extract_text_from_pdf(file_path)
    if file_ext == ".docx":
        return _extract_text_from_docx(file_path)
    if file_ext in TEXT_EXTENSIONS:
        return _read_text_file(file_path)
    if file_ext in SPREADSHEET_EXTENSIONS:
        return _extract_text_from_xlsx(file_path)
    if file_ext in IMAGE_EXTENSIONS:
        return "这是一个图片文件。"
    return f"不支持的文件类型: {file_ext}"


def _extract_text_simple(file_path: str, file_ext: str) -> str:
    if file_ext == ".pdf":
        return _extract_text_from_pdf(file_path, limit=5000)
    if file_ext == ".docx":
        return _extract_text_from_docx_plain(file_path, limit=5000)
    if file_ext in TEXT_EXTENSIONS:
        return _read_text_file(file_path)[:5000]
    if file_ext in SPREADSHEET_EXTENSIONS:
        return _extract_text_from_xlsx(file_path, limit=5000)
    return ""


def _extract_text_from_pdf(file_path: str, limit: int | None = None) -> str:
    if PyPDF2 is None and pdfplumber is None:
        return "PDF 处理库未安装，无法提取文本。"

    candidates: list[str] = []

    if pdfplumber is not None:
        try:
            pdfplumber_text = _extract_text_from_pdf_with_pdfplumber(file_path)
            if pdfplumber_text.strip():
                candidates.append(pdfplumber_text)
        except Exception as exc:
            logger.warning("pdfplumber 提取 PDF 文本失败: %s", exc)

    if PyPDF2 is not None:
        try:
            pypdf2_text = _extract_text_from_pdf_with_pypdf2(file_path)
            if pypdf2_text.strip():
                candidates.append(pypdf2_text)
        except Exception as exc:
            logger.warning("PyPDF2 提取 PDF 文本失败: %s", exc)

    text = max(candidates, key=_score_extracted_text, default="").strip()
    if limit is not None:
        return text[:limit]
    return text


def _extract_text_from_pdf_with_pypdf2(file_path: str) -> str:
    if PyPDF2 is None:
        return ""

    text_parts: list[str] = []
    with open(file_path, "rb") as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text_parts.append((page.extract_text() or "").strip())
    return "\n".join(part for part in text_parts if part).strip()


def _extract_text_from_pdf_with_pdfplumber(file_path: str) -> str:
    if pdfplumber is None:
        return ""

    text_parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = (page.extract_text(layout=True) or page.extract_text() or "").strip()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def _score_extracted_text(text: str) -> int:
    normalized = re.sub(r"\s+", "", str(text or ""))
    if not normalized:
        return 0
    non_empty_lines = [line for line in str(text or "").splitlines() if line.strip()]
    return len(normalized) + len(non_empty_lines) * 24 + len(set(normalized))


def _extract_text_from_docx(file_path: str) -> str:
    if docx is None:
        return "Word 处理库未安装，无法提取文本。"

    try:
        document = docx.Document(file_path)
        paragraphs = []
        for index, paragraph in enumerate(document.paragraphs):
            paragraphs.append(
                {
                    "index": index,
                    "text": paragraph.text,
                    "style": paragraph.style.name if paragraph.style else "Normal",
                    "runs": [
                        {
                            "text": run.text,
                            "bold": run.bold,
                            "italic": run.italic,
                            "underline": run.underline,
                            "font_name": run.font.name,
                            "font_size": run.font.size.pt if run.font.size else None,
                            "color": str(run.font.color.rgb) if run.font.color and run.font.color.rgb else None,
                        }
                        for run in paragraph.runs
                    ],
                }
            )

        tables = []
        for table in document.tables:
            tables.append([[cell.text for cell in row.cells] for row in table.rows])

        return json.dumps(
            {
                "paragraphs": paragraphs,
                "tables": tables,
                "paragraph_count": len(document.paragraphs),
                "table_count": len(document.tables),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        logger.warning("python-docx 解析失败，降级为纯文本提取: %s", exc)
        fallback_text = _extract_text_from_docx_plain(file_path)
        fallback_lines = [line.strip() for line in fallback_text.splitlines() if line.strip()]

        return json.dumps(
            {
                "paragraphs": [
                    {
                        "index": index,
                        "text": line,
                        "style": "RecoveredText",
                        "runs": [{"text": line}],
                    }
                    for index, line in enumerate(fallback_lines)
                ],
                "tables": [],
                "paragraph_count": len(fallback_lines),
                "table_count": 0,
                "recovered": True,
            },
            ensure_ascii=False,
            indent=2,
        )


def _extract_text_from_docx_plain(file_path: str, limit: int | None = None) -> str:
    if docx is None:
        return "Word 处理库未安装，无法提取文本。"

    try:
        document = docx.Document(file_path)
        lines = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text for cell in row.cells if cell.text.strip())
                if row_text:
                    lines.append(row_text)
        text = "\n".join(lines).strip()
    except Exception:
        with zipfile.ZipFile(file_path, "r") as docx_zip:
            text_parts: list[str] = []
            if "word/document.xml" in docx_zip.namelist():
                root = ET.fromstring(docx_zip.read("word/document.xml"))
                for element in root.iter():
                    if element.tag.endswith("t") and element.text and element.text.strip():
                        text_parts.append(element.text)
            text = "\n".join(text_parts).strip()

    if limit is not None:
        return text[:limit]
    return text


def _extract_text_from_xlsx(file_path: str, limit: int | None = None) -> str:
    rows: list[str] = []
    with zipfile.ZipFile(file_path, "r") as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.iter():
                if item.tag.endswith("t"):
                    shared_strings.append(item.text or "")

        worksheet_names = sorted(
            name for name in workbook.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        for worksheet_name in worksheet_names:
            root = ET.fromstring(workbook.read(worksheet_name))
            for row in root.iter():
                if not row.tag.endswith("row"):
                    continue
                values: list[str] = []
                for cell in row:
                    if not cell.tag.endswith("c"):
                        continue
                    cell_type = cell.attrib.get("t")
                    raw_value = ""
                    inline_text_parts: list[str] = []

                    for child in cell:
                        if child.tag.endswith("v") and child.text is not None:
                            raw_value = child.text
                        elif child.tag.endswith("is"):
                            inline_text_parts.extend(
                                element.text or ""
                                for element in child.iter()
                                if element.tag.endswith("t") and element.text is not None
                            )

                    if cell_type == "inlineStr" and inline_text_parts:
                        values.append("".join(inline_text_parts).strip())
                        continue
                    if not raw_value:
                        continue
                    if cell_type == "s":
                        try:
                            values.append(shared_strings[int(raw_value)])
                        except Exception:
                            values.append(raw_value)
                    elif cell_type == "str":
                        values.append(raw_value)
                    else:
                        values.append(raw_value)
                if values:
                    rows.append(" | ".join(values))

    text = "\n".join(rows).strip()
    if limit is not None:
        return text[:limit]
    return text


def _read_text_file(file_path: str) -> str:
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            with open(file_path, "r", encoding=encoding) as text_file:
                return text_file.read()
        except UnicodeDecodeError:
            continue
    raise ValueError("无法解码文本文件")


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


def _parse_ai_modifications(ai_response: str) -> list[dict[str, Any]]:
    modifications: list[dict[str, Any]] = []
    patterns = [
        r"```json\s*(.*?)\s*```",
        r"```\s*(.*?)\s*```",
        r"(\[\s*{.*?}\s*\])",
        r"({\s*\"modifications\".*?})",
    ]

    for pattern in patterns:
        for matched_text in re.findall(pattern, ai_response, flags=re.DOTALL):
            try:
                parsed = json.loads(matched_text.strip())
            except json.JSONDecodeError:
                continue

            raw_items: list[dict[str, Any]]
            if isinstance(parsed, list):
                raw_items = [item for item in parsed if isinstance(item, dict)]
            elif isinstance(parsed, dict) and isinstance(parsed.get("modifications"), list):
                raw_items = [item for item in parsed["modifications"] if isinstance(item, dict)]
            elif isinstance(parsed, dict):
                raw_items = [parsed]
            else:
                continue

            for raw_item in raw_items:
                normalized_item = _normalize_ai_modification(raw_item)
                if normalized_item:
                    modifications.append(normalized_item)

            if modifications:
                return modifications

    fallback_item = _infer_modification_from_text(ai_response)
    return [fallback_item] if fallback_item else []


def _parse_ordinal_index(token: str) -> int | None:
    normalized = str(token or "").strip()
    if not normalized:
        return None

    if normalized.isdigit():
        value = int(normalized)
        return value - 1 if value > 0 else 0

    digit_map = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }

    if normalized == "十":
        return 9

    if normalized.startswith("十"):
        tail = digit_map.get(normalized[1:], 0)
        return 9 + tail

    if normalized.endswith("十"):
        head = digit_map.get(normalized[0], 0)
        return head * 10 - 1 if head else None

    if "十" in normalized:
        head_token, tail_token = normalized.split("十", 1)
        head = digit_map.get(head_token, 1)
        tail = digit_map.get(tail_token, 0)
        return head * 10 + tail - 1

    if normalized in digit_map:
        return digit_map[normalized] - 1

    return None


def _deduplicate_modifications(modifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()

    for modification in modifications:
        signature = json.dumps(modification, ensure_ascii=False, sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        deduplicated.append(modification)

    return deduplicated


def _infer_modifications_from_instruction(instruction: str) -> list[dict[str, Any]]:
    prompt = str(instruction or "").strip()
    if not prompt:
        return []

    modifications: list[dict[str, Any]] = []

    for match in re.finditer(
        r'(?:将|把)?[“"「](?P<old>.+?)[”"」]\s*(?:替换为|替换成|改为|改成)\s*[“"「](?P<new>.+?)[”"」]',
        prompt,
    ):
        old_text = match.group("old").strip()
        new_text = match.group("new").strip()
        if old_text:
            modifications.append({
                "type": "replace_text",
                "old_text": old_text,
                "new_text": new_text,
            })

    for match in re.finditer(
        r'在(?:第\s*(?P<ordinal>[一二三四五六七八九十两0-9]+)\s*(?P<unit>段|行)|[“"「](?P<reference>.+?)[”"」]|开头|结尾|末尾)(?:的)?(?P<position>前|后)?插入[：:\s]*[“"「](?P<text>.+?)[”"」]',
        prompt,
    ):
        insert_text = match.group("text").strip()
        if not insert_text:
            continue

        modification: dict[str, Any] = {"type": "insert_text", "text": insert_text}
        ordinal = match.group("ordinal")
        unit = match.group("unit")
        reference_text = (match.group("reference") or "").strip()
        position_token = match.group("position")

        if "开头" in match.group(0):
            modification["position"] = "start"
        elif "结尾" in match.group(0) or "末尾" in match.group(0):
            modification["position"] = "end"
        elif position_token == "前":
            modification["position"] = "before"
        elif position_token == "后":
            modification["position"] = "after"
        else:
            modification["position"] = "end"

        if ordinal:
            parsed_index = _parse_ordinal_index(ordinal)
            if parsed_index is not None:
                if unit == "行":
                    modification["line_index"] = parsed_index
                else:
                    modification["paragraph_index"] = parsed_index
        elif reference_text:
            modification["reference_text"] = reference_text

        modifications.append(modification)

    format_modification: dict[str, Any] = {"type": "text_run_format"}

    target_match = re.search(r'第\s*([一二三四五六七八九十两0-9]+)\s*(段|行)', prompt)
    if target_match:
        parsed_index = _parse_ordinal_index(target_match.group(1))
        if parsed_index is not None:
            if target_match.group(2) == "行":
                format_modification["line_index"] = parsed_index
            else:
                format_modification["paragraph_index"] = parsed_index
    elif "标题" in prompt:
        format_modification["paragraph_index"] = 0
    else:
        quoted_targets = re.findall(r'[“"「](.+?)[”"」]', prompt)
        if quoted_targets and not modifications:
            format_modification["reference_text"] = quoted_targets[0].strip()

    if "加粗" in prompt:
        format_modification["bold"] = True
    if "斜体" in prompt:
        format_modification["italic"] = True
    if "下划线" in prompt:
        format_modification["underline"] = True

    color_match = re.search(r'(#?[0-9a-fA-F]{6}|红色|蓝色|绿色|黄色|紫色|橙色|黑色|白色|灰色|red|blue|green|yellow|purple|orange|black|white|gray|grey)', prompt, flags=re.IGNORECASE)
    if color_match:
        normalized_color = _normalize_color(color_match.group(1))
        if normalized_color:
            format_modification["color"] = normalized_color

    font_match = re.search(r'(?:字体(?:改为|设为|用)?|font(?:\s*family)?(?:\s*[:：]|设为|改为)?)[“"「]?([A-Za-z][A-Za-z0-9 \-]+|微软雅黑|宋体|仿宋|楷体|黑体|PingFang SC|Arial|Times New Roman)[”"」]?', prompt, flags=re.IGNORECASE)
    if font_match:
        format_modification["font_name"] = font_match.group(1).strip()

    font_size_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:px|pt|磅|号)', prompt, flags=re.IGNORECASE)
    if font_size_match:
        format_modification["font_size"] = float(font_size_match.group(1))

    if "居中" in prompt or "居中对齐" in prompt or "中心对齐" in prompt:
        format_modification["alignment"] = "center"
    elif "右对齐" in prompt or "居右" in prompt:
        format_modification["alignment"] = "right"
    elif "左对齐" in prompt or "居左" in prompt:
        format_modification["alignment"] = "left"
    elif "两端对齐" in prompt:
        format_modification["alignment"] = "justify"

    if "一级标题" in prompt:
        format_modification["heading_level"] = 1
    elif "二级标题" in prompt:
        format_modification["heading_level"] = 2
    elif "三级标题" in prompt:
        format_modification["heading_level"] = 3
    elif "正文" in prompt and ("标题级别" in prompt or "改成正文" in prompt):
        format_modification["heading_level"] = 0

    line_spacing_match = re.search(r'行距(?:调整为|设为|改为)?\s*(\d+(?:\.\d+)?)', prompt)
    if line_spacing_match:
        format_modification["line_spacing"] = float(line_spacing_match.group(1))

    space_before_match = re.search(r'段前(?:间距)?(?:调整为|设为|改为)?\s*(\d+(?:\.\d+)?)', prompt)
    if space_before_match:
        format_modification["space_before"] = float(space_before_match.group(1))

    space_after_match = re.search(r'段后(?:间距)?(?:调整为|设为|改为)?\s*(\d+(?:\.\d+)?)', prompt)
    if space_after_match:
        format_modification["space_after"] = float(space_after_match.group(1))

    if any(key in format_modification for key in (
        "bold",
        "italic",
        "underline",
        "color",
        "font_name",
        "font_size",
        "alignment",
        "heading_level",
        "line_spacing",
        "space_before",
        "space_after",
    )) and any(key in format_modification for key in ("paragraph_index", "reference_text", "line_index")):
        modifications.append(format_modification)

    return _deduplicate_modifications(modifications)


def _normalize_ai_modification(raw_item: dict[str, Any]) -> dict[str, Any] | None:
    normalized_type = _normalize_modification_type(raw_item.get("type"))
    if normalized_type is None:
        return None

    normalized: dict[str, Any] = {"type": normalized_type}

    paragraph_index = raw_item.get("paragraph_index", raw_item.get("paragraphIndex"))
    if paragraph_index is not None:
        try:
            normalized["paragraph_index"] = int(paragraph_index)
        except (TypeError, ValueError):
            return None

    line_index = raw_item.get("line_index", raw_item.get("lineIndex"))
    if line_index is not None:
        try:
            normalized["line_index"] = int(line_index)
        except (TypeError, ValueError):
            normalized.pop("line_index", None)

    reference_text = raw_item.get("reference_text", raw_item.get("referenceText"))
    if reference_text is not None:
        reference_text = str(reference_text).strip()
        if reference_text:
            normalized["reference_text"] = reference_text

    run_indices = raw_item.get("run_indices", raw_item.get("runIndices"))
    if isinstance(run_indices, list):
        normalized["run_indices"] = _normalize_run_indices(run_indices)

    for key in ("old_text", "new_text", "text", "font_name", "alignment"):
        value = raw_item.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if value != "":
            normalized[key] = value

    for nested_key in ("changes", "format_changes", "properties"):
        nested_value = raw_item.get(nested_key)
        if not isinstance(nested_value, dict):
            continue
        for key in (
            "bold",
            "italic",
            "underline",
            "color",
            "font_name",
            "font_size",
            "alignment",
            "heading_level",
            "line_spacing",
            "space_before",
            "space_after",
        ):
            if key not in normalized and nested_value.get(key) is not None:
                normalized[key] = nested_value[key]

    for bool_key in ("bold", "italic", "underline"):
        bool_value = _coerce_optional_bool(raw_item.get(bool_key))
        if bool_value is not None:
            normalized[bool_key] = bool_value
        elif bool_key in normalized:
            nested_bool_value = _coerce_optional_bool(normalized[bool_key])
            if nested_bool_value is None:
                normalized.pop(bool_key, None)
            else:
                normalized[bool_key] = nested_bool_value

    normalized_position = _normalize_insert_position(raw_item.get("position", normalized.get("position")))
    if normalized_position:
        normalized["position"] = normalized_position
    else:
        normalized.pop("position", None)

    if raw_item.get("color") is not None and "color" not in normalized:
        normalized["color"] = raw_item["color"]
    if raw_item.get("font_size") is not None and "font_size" not in normalized:
        normalized["font_size"] = raw_item["font_size"]
    if raw_item.get("heading_level") is not None and "heading_level" not in normalized:
        normalized["heading_level"] = raw_item["heading_level"]
    if raw_item.get("line_spacing") is not None and "line_spacing" not in normalized:
        normalized["line_spacing"] = raw_item["line_spacing"]
    if raw_item.get("space_before") is not None and "space_before" not in normalized:
        normalized["space_before"] = raw_item["space_before"]
    if raw_item.get("space_after") is not None and "space_after" not in normalized:
        normalized["space_after"] = raw_item["space_after"]

    if "color" in normalized:
        normalized_color = _normalize_color(normalized["color"])
        if normalized_color:
            normalized["color"] = normalized_color
        else:
            normalized.pop("color", None)

    for numeric_key in ("font_size", "line_spacing", "space_before", "space_after"):
        if numeric_key not in normalized:
            continue
        try:
            normalized[numeric_key] = float(normalized[numeric_key])
        except (TypeError, ValueError):
            normalized.pop(numeric_key, None)

    if "heading_level" in normalized:
        try:
            normalized["heading_level"] = max(0, min(3, int(normalized["heading_level"])))
        except (TypeError, ValueError):
            normalized.pop("heading_level", None)

    if "alignment" in normalized:
        normalized_alignment = _normalize_alignment(normalized["alignment"])
        if normalized_alignment is None:
            normalized.pop("alignment", None)
        else:
            normalized["alignment"] = normalized_alignment

    if normalized["type"] == "text_run_format" and not any(
        key in normalized for key in ("paragraph_index", "reference_text", "line_index")
    ):
        return None
    if normalized["type"] == "replace_text" and not str(normalized.get("old_text") or "").strip():
        return None
    if normalized["type"] == "insert_text" and not str(normalized.get("text") or "").strip():
        return None
    return normalized


def _infer_modification_from_text(ai_response: str) -> dict[str, Any] | None:
    text = (ai_response or "").lower()
    if "加粗" not in text and "red" not in text and "红色" not in text:
        return None

    fallback: dict[str, Any] = {"type": "text_run_format", "paragraph_index": 0}
    if "加粗" in text or "bold" in text:
        fallback["bold"] = True
    if "红色" in text or "red" in text:
        fallback["color"] = "#FF0000"
    return fallback


def _extract_text_explanation(ai_response: str) -> str:
    text = re.sub(r"```json\s*.*?\s*```", "", ai_response or "", flags=re.DOTALL)
    text = re.sub(r"```\s*.*?\s*```", "", text, flags=re.DOTALL)
    return text.strip()


def _write_content_to_docx(output_path: str, content: str) -> str:
    if docx is None:
        raise RuntimeError("python-docx 未安装")

    document = docx.Document()
    normalized_content = str(content or "").replace("\r", "").strip()
    blocks = re.split(r"\n\s*\n", normalized_content) if normalized_content else []

    if not blocks:
        document.add_paragraph("")
    else:
        for block in blocks:
            for line in block.split("\n"):
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped_line)
                if heading_match:
                    paragraph = document.add_paragraph(heading_match.group(2).strip())
                    try:
                        paragraph.style = f"Heading {len(heading_match.group(1))}"
                    except Exception:
                        pass
                    continue

                document.add_paragraph(stripped_line)

    document.save(output_path)
    return output_path


def _apply_modifications_to_docx(input_path: str, modifications: list[dict[str, Any]]) -> str:
    if docx is None:
        raise RuntimeError("python-docx 未安装")

    document = docx.Document(input_path)
    for modification in modifications:
        modification_type = str(modification.get("type") or "").lower()
        if modification_type == "text_run_format":
            _apply_text_run_format(document, modification)
        elif modification_type == "replace_text":
            _apply_replace_text_to_docx(document, modification)
        elif modification_type == "insert_text":
            _apply_insert_text_to_docx(document, modification)

    output_path = derive_output_path(input_path, prefix="modified_")
    document.save(output_path)
    return output_path


def _resolve_docx_paragraph_indexes(document: Any, modification: dict[str, Any]) -> list[int]:
    paragraph_index = modification.get("paragraph_index")
    if isinstance(paragraph_index, int) and 0 <= paragraph_index < len(document.paragraphs):
        return [paragraph_index]

    line_index = modification.get("line_index")
    if isinstance(line_index, int) and 0 <= line_index < len(document.paragraphs):
        return [line_index]

    reference_text = str(modification.get("reference_text") or "").strip()
    if reference_text:
        for index, paragraph in enumerate(document.paragraphs):
            if reference_text and reference_text in paragraph.text:
                return [index]
        normalized_reference = _normalize_match_text(reference_text)
        if normalized_reference:
            for index, paragraph in enumerate(document.paragraphs):
                if normalized_reference in _normalize_match_text(paragraph.text):
                    return [index]
            best_index = _find_best_matching_paragraph(document.paragraphs, reference_text)
            if best_index is not None:
                return [best_index]

    return []


def _insert_docx_paragraph_after(paragraph: Any, text: str) -> None:
    if OxmlElement is None or Paragraph is None:
        paragraph.add_run(f"\n{text}")
        return

    new_element = OxmlElement("w:p")
    paragraph._p.addnext(new_element)
    new_paragraph = Paragraph(new_element, paragraph._parent)
    try:
        new_paragraph.style = paragraph.style
    except Exception:
        pass
    if text:
        new_paragraph.add_run(text)


def _apply_text_run_format(document: Any, modification: dict[str, Any]) -> None:
    paragraph_indexes = _resolve_docx_paragraph_indexes(document, modification)
    if not paragraph_indexes:
        return

    requested_indices = modification.get("run_indices")
    color = _normalize_color(modification.get("color"))
    font_name = str(modification.get("font_name") or "").strip()
    font_size = modification.get("font_size")
    alignment = _normalize_alignment(modification.get("alignment"))
    heading_level = modification.get("heading_level")
    line_spacing = modification.get("line_spacing")
    space_before = modification.get("space_before")
    space_after = modification.get("space_after")

    for paragraph_index in paragraph_indexes:
        paragraph = document.paragraphs[paragraph_index]
        if not paragraph.runs and paragraph.text:
            paragraph.add_run(paragraph.text)

        runs = paragraph.runs
        if runs:
            if isinstance(requested_indices, list) and requested_indices:
                run_indices = [index for index in requested_indices if isinstance(index, int) and 0 <= index < len(runs)]
            else:
                run_indices = list(range(len(runs)))

            for run_index in run_indices:
                run = runs[run_index]
                if "bold" in modification:
                    run.bold = bool(modification["bold"])
                if "italic" in modification:
                    run.italic = bool(modification["italic"])
                if "underline" in modification:
                    run.underline = bool(modification["underline"])
                if font_name:
                    run.font.name = font_name
                if isinstance(font_size, (int, float)) and Pt is not None:
                    run.font.size = Pt(float(font_size))
                if color and RGBColor is not None:
                    run.font.color.rgb = RGBColor(int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))

        if alignment is not None and WD_ALIGN_PARAGRAPH is not None:
            alignment_value_map = {
                "left": WD_ALIGN_PARAGRAPH.LEFT,
                "center": WD_ALIGN_PARAGRAPH.CENTER,
                "right": WD_ALIGN_PARAGRAPH.RIGHT,
                "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            }
            paragraph.alignment = alignment_value_map.get(alignment, paragraph.alignment)

        if isinstance(heading_level, int):
            if heading_level <= 0:
                try:
                    paragraph.style = document.styles["Normal"]
                except Exception:
                    pass
            else:
                try:
                    paragraph.style = document.styles[f"Heading {max(1, min(3, heading_level))}"]
                except Exception:
                    pass

        paragraph_format = paragraph.paragraph_format
        if isinstance(line_spacing, (int, float)):
            paragraph_format.line_spacing = float(line_spacing)

        if isinstance(space_before, (int, float)) and Pt is not None:
            paragraph_format.space_before = Pt(float(space_before))

        if isinstance(space_after, (int, float)) and Pt is not None:
            paragraph_format.space_after = Pt(float(space_after))


def _apply_replace_text_to_docx(document: Any, modification: dict[str, Any]) -> None:
    old_text = str(modification.get("old_text") or "")
    new_text = str(modification.get("new_text") or "")
    if not old_text:
        return

    for paragraph in document.paragraphs:
        _replace_text_in_paragraph(paragraph, old_text, new_text)

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_text_in_paragraph(paragraph, old_text, new_text)


def _apply_insert_text_to_docx(document: Any, modification: dict[str, Any]) -> None:
    insert_text = str(modification.get("text") or "")
    if not insert_text:
        return

    position = str(modification.get("position") or "end").lower()
    paragraph_indexes = _resolve_docx_paragraph_indexes(document, modification)

    if paragraph_indexes:
        paragraph = document.paragraphs[paragraph_indexes[0]]
        current_text = paragraph.text
        if position == "start":
            _prepend_text_to_paragraph(paragraph, insert_text)
        elif position == "before":
            paragraph.insert_paragraph_before(insert_text)
        elif position == "after":
            _insert_docx_paragraph_after(paragraph, insert_text)
        else:
            _append_text_to_paragraph(paragraph, insert_text)
        return

    if position == "start" and document.paragraphs:
        _prepend_text_to_paragraph(document.paragraphs[0], insert_text)
    else:
        document.add_paragraph(insert_text)


def _set_paragraph_text(paragraph: Any, text: str, *, template_run: Any | None = None) -> None:
    template_style = _capture_run_style(template_run or (paragraph.runs[0] if paragraph.runs else None))
    paragraph_element = paragraph._element
    for child in list(paragraph_element):
        paragraph_element.remove(child)
    new_run = paragraph.add_run(text)
    _apply_run_style(new_run, template_style)


def _replace_text_in_paragraph(paragraph: Any, old_text: str, new_text: str) -> bool:
    if old_text not in paragraph.text:
        return False

    for run in paragraph.runs:
        if old_text in run.text:
            run.text = run.text.replace(old_text, new_text)
            return True

    template_run = paragraph.runs[0] if paragraph.runs else None
    _set_paragraph_text(paragraph, paragraph.text.replace(old_text, new_text), template_run=template_run)
    return True


def _prepend_text_to_paragraph(paragraph: Any, text: str) -> None:
    if not text:
        return
    if not paragraph.runs:
        paragraph.add_run(text)
        return

    first_run = paragraph.runs[0]
    new_run = paragraph.add_run(text)
    _apply_run_style(new_run, _capture_run_style(first_run))
    first_run._r.addprevious(new_run._r)


def _append_text_to_paragraph(paragraph: Any, text: str) -> None:
    if not text:
        return

    template_run = paragraph.runs[-1] if paragraph.runs else None
    new_run = paragraph.add_run(text)
    _apply_run_style(new_run, _capture_run_style(template_run))


def _capture_run_style(run: Any | None) -> dict[str, Any]:
    if run is None:
        return {}

    style: dict[str, Any] = {
        "bold": run.bold,
        "italic": run.italic,
        "underline": run.underline,
    }

    if getattr(run.font, "name", None):
        style["font_name"] = run.font.name
    if getattr(run.font, "size", None) is not None:
        style["font_size"] = run.font.size
    if getattr(run.font, "color", None) is not None and getattr(run.font.color, "rgb", None) is not None:
        style["color_rgb"] = run.font.color.rgb

    return style


def _apply_run_style(run: Any, style: dict[str, Any]) -> None:
    if not style:
        return

    if "bold" in style:
        run.bold = style["bold"]
    if "italic" in style:
        run.italic = style["italic"]
    if "underline" in style:
        run.underline = style["underline"]
    if style.get("font_name"):
        run.font.name = style["font_name"]
    if style.get("font_size") is not None:
        run.font.size = style["font_size"]
    if style.get("color_rgb") is not None:
        run.font.color.rgb = style["color_rgb"]


def _apply_modifications_to_text(input_path: str, modifications: list[dict[str, Any]]) -> str:
    content = _read_text_file(input_path)
    for modification in modifications:
        modification_type = str(modification.get("type") or "").lower()
        if modification_type == "replace_text":
            old_text = str(modification.get("old_text") or "")
            new_text = str(modification.get("new_text") or "")
            if old_text:
                content = content.replace(old_text, new_text)
        elif modification_type == "insert_text":
            insert_text = str(modification.get("text") or "")
            position = str(modification.get("position") or "end").lower()
            line_index = modification.get("line_index")
            if not isinstance(line_index, int):
                paragraph_index = modification.get("paragraph_index")
                if isinstance(paragraph_index, int):
                    line_index = paragraph_index
            reference_text = str(modification.get("reference_text") or "")
            if not insert_text:
                continue
            if isinstance(line_index, int):
                lines = content.split("\n")
                safe_index = max(0, min(line_index, len(lines) - 1 if lines else 0))

                if position == "before":
                    lines.insert(safe_index, insert_text)
                elif position == "after":
                    lines.insert(min(safe_index + 1, len(lines)), insert_text)
                elif position == "start" and lines:
                    lines[safe_index] = f"{insert_text}{lines[safe_index]}"
                elif position == "end" and lines:
                    lines[safe_index] = f"{lines[safe_index]}{insert_text}"
                else:
                    lines.append(insert_text)

                content = "\n".join(lines)
            elif reference_text and reference_text in content and position in {"before", "after"}:
                replacement = f"{insert_text}{reference_text}" if position == "before" else f"{reference_text}{insert_text}"
                content = content.replace(reference_text, replacement, 1)
            elif position == "start":
                content = f"{insert_text}{content}"
            else:
                content = f"{content}{insert_text}"

    output_path = derive_output_path(input_path, prefix="modified_")
    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(content)
    return output_path


def _normalize_color(value: Any) -> str | None:
    if value is None:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None

    lowered = raw_value.lower()
    raw_value = COLOR_NAME_MAP.get(lowered, raw_value)
    if re.fullmatch(r"#[0-9a-fA-F]{6}", raw_value):
        return raw_value.upper()
    if re.fullmatch(r"[0-9a-fA-F]{6}", raw_value):
        return f"#{raw_value.upper()}"
    return None


def _normalize_alignment(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    alignment_map = {
        "left": "left",
        "start": "left",
        "居左": "left",
        "左对齐": "left",
        "center": "center",
        "centre": "center",
        "居中": "center",
        "居中对齐": "center",
        "right": "right",
        "end": "right",
        "居右": "right",
        "右对齐": "right",
        "justify": "justify",
        "两端对齐": "justify",
    }
    return alignment_map.get(normalized)


def _normalize_modification_type(value: Any) -> str | None:
    normalized = str(value or "text_run_format").strip().lower()
    type_map = {
        "text_run_format": "text_run_format",
        "format_text": "text_run_format",
        "format": "text_run_format",
        "style": "text_run_format",
        "样式": "text_run_format",
        "replace_text": "replace_text",
        "replace": "replace_text",
        "替换": "replace_text",
        "insert_text": "insert_text",
        "insert": "insert_text",
        "插入": "insert_text",
    }
    return type_map.get(normalized)


def _normalize_run_indices(raw_indices: list[Any]) -> list[int]:
    normalized_indices: list[int] = []
    for item in raw_indices:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if index < 0 or index in normalized_indices:
            continue
        normalized_indices.append(index)
    return normalized_indices


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "是", "开启", "开"}:
        return True
    if normalized in {"false", "0", "no", "n", "否", "关闭", "关"}:
        return False
    return None


def _normalize_insert_position(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    position_map = {
        "before": "before",
        "前": "before",
        "after": "after",
        "后": "after",
        "start": "start",
        "beginning": "start",
        "prepend": "start",
        "开头": "start",
        "头部": "start",
        "end": "end",
        "append": "end",
        "结尾": "end",
        "末尾": "end",
    }
    return position_map.get(normalized)


def _normalize_match_text(value: Any) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).casefold()
    return re.sub(r"[^\w\u4e00-\u9fff]", "", normalized)


def _find_best_matching_paragraph(paragraphs: list[Any], reference_text: str) -> int | None:
    normalized_reference = _normalize_match_text(reference_text)
    if not normalized_reference:
        return None

    best_index: int | None = None
    best_score = 0.0
    for index, paragraph in enumerate(paragraphs):
        candidate = _normalize_match_text(paragraph.text)
        if not candidate:
            continue
        score = SequenceMatcher(None, normalized_reference, candidate).ratio()
        if score > best_score:
            best_score = score
            best_index = index

    if best_score >= 0.58:
        return best_index
    return None
