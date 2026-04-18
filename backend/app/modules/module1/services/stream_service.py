from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Iterator, Optional

from fastapi import UploadFile
from fastapi.responses import StreamingResponse

from ..core.config import get_settings
from . import document_io_support as io_support
from . import interaction_support as interaction
from . import modification_support as modification_support
from .sandbox_service import cleanup_temp_paths, save_upload_to_temp


logger = logging.getLogger(__name__)


async def stream_workbench_operation(
    files: Optional[list[UploadFile]],
    instruction: str,
    *,
    conversation_context: str = "[]",
    selected_file_name: str = "",
) -> StreamingResponse:
    async def generate() -> Iterator[str]:
        prompt = (instruction or "").strip()
        context_messages = interaction._parse_conversation_context(conversation_context)
        normalized_files = [upload for upload in (files or []) if upload is not None]
        is_analysis_request = interaction._is_analysis_instruction(prompt)
        if not prompt:
            for chunk in interaction._chunk_text("可以直接输入你想分析、提取、润色或修改的需求。没有文件时也可以先聊天。"):
                yield interaction._sse({"type": "chunk", "content": chunk})
            yield interaction._sse({"type": "end"})
            return

        if not normalized_files:
            for event in interaction._stream_plain_chat_events(prompt, context_messages):
                yield event
            return

        settings = get_settings()
        temp_paths: list[str] = []

        try:
            if is_analysis_request:
                yield interaction._stage_sse("request_received")
                await asyncio.sleep(0)
                yield interaction._stage_sse("extracting_text")
                await asyncio.sleep(0)

            prepared_documents: list[dict[str, Any]] = []
            for upload in normalized_files:
                saved_upload = await save_upload_to_temp(
                    upload,
                    max_file_bytes=settings.max_file_bytes,
                    max_file_mb=settings.max_file_mb,
                )
                temp_paths.append(saved_upload.path)
                io_support._validate_saved_upload(saved_upload)

                working_path, converted_path = io_support._prepare_docx_source(saved_upload)
                if converted_path:
                    temp_paths.append(converted_path)

                working_ext = Path(working_path).suffix.lower()
                doc_content = io_support._extract_text(working_path, working_ext)
                simple_content = io_support._extract_text_simple(working_path, working_ext)

                visual_summary = interaction._describe_visual_content(working_path, working_ext, prompt)
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

            if is_analysis_request:
                yield interaction._stage_sse("preparing_analysis")
                await asyncio.sleep(0)

            agent = interaction._get_agent()
            if not agent.available:
                fallback_text = (
                    interaction._build_local_analysis_report(
                        prompt,
                        prepared_documents,
                        extra_hint="AI 响应较慢，已先返回本地摘要。",
                    )
                    if is_analysis_request
                    else interaction._build_local_document_reply(
                        prompt,
                        prepared_documents,
                        context_messages,
                    )
                )
                if is_analysis_request:
                    yield interaction._stage_sse("fallback_completed")
                for chunk in interaction._chunk_text(fallback_text):
                    yield interaction._sse({"type": "chunk", "content": chunk})
                inferred_modifications = modification_support._infer_modifications_from_instruction(prompt)
                if inferred_modifications and not is_analysis_request:
                    inferred_modifications = modification_support._sanitize_modifications_for_instruction(
                        inferred_modifications,
                        prompt,
                    )
                    for chunk in interaction._chunk_text("当前未配置 AI，已按本地规则生成基础修改方案，你可以直接继续应用。"):
                        yield interaction._sse({"type": "chunk", "content": chunk})
                    yield interaction._sse({"type": "modifications", "content": inferred_modifications})
                yield interaction._sse({"type": "end"})
                return

            try:
                if is_analysis_request:
                    content_for_analysis = combined_simple_content or combined_doc_content or "未提取到可分析文本。"
                    yield interaction._stage_sse("generating_report")
                    await asyncio.sleep(0)
                    for chunk in agent.stream_analysis_with_first_token_timeout(
                        prompt,
                        content_for_analysis,
                        context_messages,
                        first_token_timeout_sec=interaction.ANALYSIS_FIRST_TOKEN_TIMEOUT_SEC,
                    ):
                        yield interaction._sse({"type": "chunk", "content": chunk})
                    yield interaction._stage_sse("completed")
                    await asyncio.sleep(0)
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
                    explanation = modification_support._extract_text_explanation(full_response)
                    if not explanation:
                        explanation = "已根据你的指令生成修改方案，下面会进入修改应用流程。"
                    for chunk in interaction._chunk_text(explanation):
                        yield interaction._sse({"type": "chunk", "content": chunk})

                    modifications = modification_support._parse_ai_modifications(full_response)
                    inferred_modifications = modification_support._infer_modifications_from_instruction(prompt)
                    if inferred_modifications:
                        modifications = modification_support._deduplicate_modifications(
                            [*modifications, *inferred_modifications]
                        )
                    modifications = modification_support._sanitize_modifications_for_instruction(
                        modifications,
                        prompt,
                    )
                    if modifications:
                        yield interaction._sse({"type": "modifications", "content": modifications})
            except Exception as exc:
                logger.warning("AI 文档操作失败，切换到本地兜底回复: %s", exc)
                fallback_text = (
                    interaction._build_local_analysis_report(
                        prompt,
                        prepared_documents,
                        extra_hint="AI 响应较慢，已先返回本地摘要。",
                    )
                    if is_analysis_request
                    else interaction._build_local_document_reply(
                        prompt,
                        prepared_documents,
                        context_messages,
                        extra_hint="AI 服务暂时不可用，已返回本地兜底内容。",
                    )
                )
                if is_analysis_request:
                    yield interaction._stage_sse("fallback_completed")
                    await asyncio.sleep(0)
                for chunk in interaction._chunk_text(fallback_text):
                    yield interaction._sse({"type": "chunk", "content": chunk})
                inferred_modifications = modification_support._infer_modifications_from_instruction(prompt)
                if inferred_modifications and not is_analysis_request:
                    inferred_modifications = modification_support._sanitize_modifications_for_instruction(
                        inferred_modifications,
                        prompt,
                    )
                    for chunk in interaction._chunk_text("AI 服务暂时不可用，已切换到本地规则并生成基础修改方案。"):
                        yield interaction._sse({"type": "chunk", "content": chunk})
                    yield interaction._sse({"type": "modifications", "content": inferred_modifications})

            yield interaction._sse({"type": "end"})
        except ValueError as exc:
            if is_analysis_request:
                yield interaction._stage_sse("failed")
                await asyncio.sleep(0)
            yield interaction._sse({"type": "error", "content": str(exc)})
        except Exception as exc:
            logger.exception("流式操作失败")
            if is_analysis_request:
                yield interaction._stage_sse("failed")
                await asyncio.sleep(0)
            yield interaction._sse({"type": "error", "content": str(exc)})
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
        content = str(
            document.get(field_name)
            or document.get("simple_content")
            or document.get("doc_content")
            or ""
        ).strip()
        content = content[:4000] if content else "未提取到可用文本。"
        focus_suffix = "（当前焦点文档）" if focus_file_name and file_name == focus_file_name else ""
        summaries.append(f"【文档{index}】{file_name}{focus_suffix}\n{content}")
    return "\n\n".join(summaries)


__all__ = ["stream_workbench_operation"]
