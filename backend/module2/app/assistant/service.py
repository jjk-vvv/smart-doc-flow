from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import unquote

from app.assistant.prompting import build_answer_messages
from app.assistant.provider import OpenAICompatibleChatProvider, resolve_llm_api_key, resolve_llm_base_url, resolve_llm_model
from app.assistant.streaming import chunk_text, sse_event
from app.assistant.tools import (
    build_action_preview,
    build_action_preview_citations,
    build_document_overview,
    build_field_citations,
    build_figure_citations,
    build_table_overview_citations,
    build_table_overview_context,
    classify_route,
    collect_trace_hits,
    dump_context_for_model,
    enrich_matched_fields_with_trace_hits,
    fallback_answer,
    locate_table_answer,
    match_fields,
    merge_structural_payload,
    payload_has_structural_context,
    reconstruct_payload_from_trace_hits,
    select_tables,
    select_figures,
)
from app.db.storage import ExtractionStorage
from app.schemas import (
    AssistantActionPreview,
    AssistantChatStreamRequest,
    AssistantObjectLock,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSessionMessage,
    AssistantSessionRequest,
    AssistantSessionResponse,
    DocumentExtractionResponse,
)


@dataclass
class TurnArtifacts:
    route: str
    warnings: List[str] = field(default_factory=list)
    matched_fields: List[Dict[str, Any]] = field(default_factory=list)
    matched_trace_hits: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    current_object_lock: Optional[Dict[str, Any]] = None
    action_preview: Optional[Dict[str, Any]] = None
    answer_context: Dict[str, Any] = field(default_factory=dict)
    fallback_answer: str = ""
    tool_events: List[Dict[str, Any]] = field(default_factory=list)
    prefer_fallback_only: bool = False


class AssistantService:
    def __init__(self, storage: ExtractionStorage) -> None:
        self._storage = storage
        self._temperature = max(0.0, min(1.0, float(os.getenv("MODULE2_ASSISTANT_TEMPERATURE", "1.0"))))
        self._max_tokens = max(600, int(os.getenv("MODULE2_ASSISTANT_MAX_TOKENS", "2200")))
        self._model = resolve_llm_model(default="gemini-3.1-pro")
        self._base_url = resolve_llm_base_url()
        self._api_key = resolve_llm_api_key()
        self._provider: Optional[OpenAICompatibleChatProvider] = None
        if self._base_url and self._api_key:
            self._provider = OpenAICompatibleChatProvider(
                base_url=self._base_url,
                api_key=self._api_key,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                timeout_sec=max(10.0, float(os.getenv("MODULE2_ASSISTANT_TIMEOUT_SEC", "120"))),
            )

    @staticmethod
    def _artifact_root_dir() -> Path:
        root = Path(os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "backend/module2/.cache")).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _load_payload_from_document_diagnostics(self, document: DocumentExtractionResponse) -> Dict[str, Any]:
        diagnostics = document.diagnostics if isinstance(document.diagnostics, dict) else {}
        artifact_path = str(diagnostics.get("assistant_payload_artifact_path") or "").strip()
        if not artifact_path:
            artifact_url = str(diagnostics.get("assistant_payload_artifact_url") or "").strip()
            prefix = "/extract/artifact/"
            if artifact_url.startswith(prefix):
                encoded = artifact_url[len(prefix):]
                artifact_path = "/".join(unquote(part) for part in encoded.split("/") if part)
        if not artifact_path:
            return {}

        root = self._artifact_root_dir()
        fragment = artifact_path.lstrip("/\\")
        target = (root / fragment).resolve()
        try:
            target.relative_to(root)
        except Exception:
            return {}
        if not target.exists() or not target.is_file():
            return {}
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        if isinstance(raw.get("payload"), dict):
            raw = raw.get("payload") or {}
        return raw if isinstance(raw, dict) else {}

    async def _resolve_extraction_payload(
        self,
        *,
        document: DocumentExtractionResponse,
        request_payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        resolved = dict(request_payload or {})
        if payload_has_structural_context(resolved):
            return resolved, None

        storage_payload = await self._storage.load_extraction_payload(document.file_hash) or {}
        resolved = merge_structural_payload(resolved, storage_payload)
        if payload_has_structural_context(resolved):
            return resolved, None

        artifact_payload = self._load_payload_from_document_diagnostics(document)
        resolved = merge_structural_payload(resolved, artifact_payload)
        if payload_has_structural_context(resolved):
            return resolved, {
                "tool_name": "restore_assistant_context",
                "status": "done",
                "message": "已从文档附带的结构化 artifact 恢复助手上下文",
                "detail": f"tables={len(resolved.get('tables', []) or [])}, figures={len(resolved.get('figures', []) or [])}",
                "output": {
                    "source": "diagnostic_artifact",
                    "table_count": len(resolved.get("tables", []) or []),
                    "figure_count": len(resolved.get("figures", []) or []),
                },
            }

        trace_payload = reconstruct_payload_from_trace_hits(document)
        resolved = merge_structural_payload(resolved, trace_payload)
        if payload_has_structural_context(resolved):
            return resolved, {
                "tool_name": "restore_assistant_context",
                "status": "done",
                "message": "已根据 trace_hits 重建轻量助手上下文",
                "detail": f"tables={len(resolved.get('tables', []) or [])}, figures={len(resolved.get('figures', []) or [])}",
                "output": {
                    "source": "trace_hits",
                    "table_count": len(resolved.get("tables", []) or []),
                    "figure_count": len(resolved.get("figures", []) or []),
                },
            }

        return resolved, None

    async def ensure_session(self, payload: AssistantSessionRequest) -> AssistantSessionResponse:
        requested_id = str(payload.session_id or "").strip()
        summary_text = str(payload.summary or "").strip()
        existing = await self._storage.fetch_assistant_session(requested_id) if requested_id else None
        if existing and str(existing.get("file_hash") or "").strip() == payload.document.file_hash:
            session_id = str(existing.get("session_id") or requested_id)
            current_lock_raw = existing.get("current_object_lock_json") if isinstance(existing.get("current_object_lock_json"), dict) else {}
            messages = await self._storage.list_assistant_messages(session_id, limit=40)
            await self._storage.upsert_assistant_session(
                session_id=session_id,
                file_hash=payload.document.file_hash,
                file_name=payload.document.file_name,
                summary_text=summary_text or str(existing.get("summary_text") or ""),
                current_object_lock=current_lock_raw,
                metadata={"track": payload.document.track},
            )
            return AssistantSessionResponse(
                session_id=session_id,
                summary_used=summary_text or str(existing.get("summary_text") or ""),
                current_object_lock=AssistantObjectLock(**current_lock_raw) if current_lock_raw else None,
                messages=[self._to_session_message(item) for item in messages],
            )

        session_id = f"asst-{uuid.uuid4().hex}"
        await self._storage.upsert_assistant_session(
            session_id=session_id,
            file_hash=payload.document.file_hash,
            file_name=payload.document.file_name,
            summary_text=summary_text,
            current_object_lock={},
            metadata={"track": payload.document.track},
        )
        return AssistantSessionResponse(
            session_id=session_id,
            summary_used=summary_text,
            current_object_lock=None,
            messages=[],
        )

    async def query_once(self, payload: AssistantQueryRequest) -> AssistantQueryResponse:
        extraction_payload, _restore_event = await self._resolve_extraction_payload(
            document=payload.document,
            request_payload=None,
        )
        artifacts = await self._build_turn_artifacts_safe(
            document=payload.document,
            summary_text=str(payload.summary or "").strip(),
            user_message=str(payload.user_instruction or "").strip(),
            top_k=int(payload.top_k or 12),
            current_object_lock=None,
            extraction_payload=extraction_payload,
        )
        if artifacts.prefer_fallback_only:
            answer = artifacts.fallback_answer
        else:
            answer = await self._complete_answer_text(
                route=artifacts.route,
                user_message=str(payload.user_instruction or "").strip(),
                summary_text=str(payload.summary or "").strip(),
                history=[],
                answer_context=artifacts.answer_context,
                fallback=artifacts.fallback_answer,
            )
        return AssistantQueryResponse(
            ok=True,
            answer=answer,
            summary_used=str(payload.summary or "").strip(),
            matched_fields=artifacts.matched_fields,
            matched_trace_hits=artifacts.matched_trace_hits,
            persisted=False,
            persisted_rows=0,
            warnings=artifacts.warnings,
        )

    async def stream_chat(self, payload: AssistantChatStreamRequest) -> AsyncIterator[bytes]:
        session_req = AssistantSessionRequest(
            document=payload.document,
            summary=payload.summary,
            session_id=payload.session_id,
        )
        session = await self.ensure_session(session_req)
        session_id = session.session_id
        session_lock = session.current_object_lock.model_dump(mode="json") if session.current_object_lock else {}
        request_lock = payload.current_object_lock.model_dump(mode="json") if payload.current_object_lock else {}
        current_lock = request_lock or session_lock or {}
        history = [item.model_dump(mode="json") for item in session.messages]
        user_message = str(payload.user_message or "").strip()
        summary_text = str(payload.summary or "").strip() or session.summary_used

        user_message_id = f"msg-{uuid.uuid4().hex}"
        assistant_message_id = f"msg-{uuid.uuid4().hex}"
        await self._storage.save_assistant_message(
            session_id=session_id,
            message_id=user_message_id,
            role="user",
            message_type="user_message",
            content=user_message,
            payload={},
        )
        yield sse_event(
            "assistant_start",
            {
                "session_id": session_id,
                "assistant_message_id": assistant_message_id,
            },
        )

        extraction_payload, restore_event = await self._resolve_extraction_payload(
            document=payload.document,
            request_payload=dict(payload.extraction_payload or {}),
        )
        if restore_event:
            await self._storage.save_tool_invocation(
                session_id=session_id,
                message_id=assistant_message_id,
                tool_name=str(restore_event.get("tool_name") or "restore_assistant_context"),
                status=str(restore_event.get("status") or "done"),
                input_summary={},
                output_summary=restore_event.get("output") if isinstance(restore_event.get("output"), dict) else {},
                latency_ms=0,
            )
            yield sse_event(
                "tool_status",
                {
                    "tool_name": str(restore_event.get("tool_name") or "restore_assistant_context"),
                    "status": str(restore_event.get("status") or "done"),
                    "message": str(restore_event.get("message") or ""),
                    "detail": str(restore_event.get("detail") or ""),
                },
            )
        artifacts = await self._build_turn_artifacts_safe(
            document=payload.document,
            summary_text=summary_text,
            user_message=user_message,
            top_k=int(payload.top_k or 12),
            current_object_lock=current_lock or None,
            extraction_payload=extraction_payload,
        )

        for event in artifacts.tool_events:
            tool_name = str(event.get("tool_name") or "").strip()
            await self._storage.save_tool_invocation(
                session_id=session_id,
                message_id=assistant_message_id,
                tool_name=tool_name,
                status=str(event.get("status") or "done"),
                input_summary=event.get("input") if isinstance(event.get("input"), dict) else {},
                output_summary=event.get("output") if isinstance(event.get("output"), dict) else {},
                latency_ms=int(event.get("latency_ms", 0) or 0),
            )
            yield sse_event(
                "tool_status",
                {
                    "tool_name": tool_name,
                    "status": str(event.get("status") or "done"),
                    "message": str(event.get("message") or ""),
                    "detail": str(event.get("detail") or ""),
                },
            )

        if artifacts.citations or artifacts.current_object_lock:
            yield sse_event(
                "citation_bundle",
                {
                    "citations": artifacts.citations,
                    "current_object_lock": artifacts.current_object_lock or {},
                },
            )

        if artifacts.action_preview:
            yield sse_event("action_preview", artifacts.action_preview)

        answer_text_parts: List[str] = []
        provider_error = ""
        if artifacts.prefer_fallback_only:
            for chunk in chunk_text(artifacts.fallback_answer, chunk_size=72):
                answer_text_parts.append(chunk)
                yield sse_event("assistant_delta", {"text": chunk})
        else:
            try:
                messages = build_answer_messages(
                    route=artifacts.route,
                    user_message=user_message,
                    summary_text=summary_text,
                    history=history,
                    answer_context=dump_context_for_model(artifacts.answer_context),
                )
                async for chunk in self._stream_provider_text(messages):
                    answer_text_parts.append(chunk)
                    yield sse_event("assistant_delta", {"text": chunk})
            except Exception as exc:
                provider_error = f"{type(exc).__name__}: {exc}"
                yield sse_event(
                    "tool_status",
                    {
                        "tool_name": "assistant_model_stream",
                        "status": "fallback",
                        "message": "模型流式输出异常，已切换到结构化事实兜底回答。",
                        "detail": provider_error,
                    },
                )
                fallback = self._provider_fallback_text(
                    artifacts.fallback_answer,
                    partial_answer_exists=bool(answer_text_parts),
                )
                for chunk in chunk_text(fallback, chunk_size=72):
                    answer_text_parts.append(chunk)
                    yield sse_event("assistant_delta", {"text": chunk})

        if provider_error:
            artifacts.warnings.append(f"assistant_provider_fallback:{provider_error}")

        final_answer = "".join(answer_text_parts).strip() or artifacts.fallback_answer
        await self._storage.save_assistant_message(
            session_id=session_id,
            message_id=assistant_message_id,
            role="assistant",
            message_type="assistant_text",
            content=final_answer,
            payload={
                "route": artifacts.route,
                "citations": artifacts.citations,
                "current_object_lock": artifacts.current_object_lock or {},
                "action_preview": artifacts.action_preview or {},
                "warnings": artifacts.warnings,
            },
        )
        await self._storage.upsert_assistant_session(
            session_id=session_id,
            file_hash=payload.document.file_hash,
            file_name=payload.document.file_name,
            summary_text=summary_text,
            current_object_lock=artifacts.current_object_lock or current_lock or {},
            metadata={"track": payload.document.track, "route": artifacts.route},
        )
        yield sse_event(
            "assistant_done",
            {
                "session_id": session_id,
                "assistant_message_id": assistant_message_id,
                "route": artifacts.route,
                "answer": final_answer,
                "warnings": artifacts.warnings,
                "current_object_lock": artifacts.current_object_lock or {},
                "citations": artifacts.citations,
                "action_preview": artifacts.action_preview or {},
            },
        )

    async def _build_turn_artifacts_safe(
        self,
        *,
        document: DocumentExtractionResponse,
        summary_text: str,
        user_message: str,
        top_k: int,
        current_object_lock: Optional[Dict[str, Any]],
        extraction_payload: Dict[str, Any],
    ) -> TurnArtifacts:
        try:
            return await self._build_turn_artifacts(
                document=document,
                summary_text=summary_text,
                user_message=user_message,
                top_k=top_k,
                current_object_lock=current_object_lock,
                extraction_payload=extraction_payload,
            )
        except Exception as exc:
            warning = f"assistant_context_fallback:{type(exc).__name__}: {exc}"
            artifacts = TurnArtifacts(
                route="clarification_needed",
                warnings=[warning],
                current_object_lock=dict(current_object_lock or {}) or None,
                tool_events=[
                    {
                        "tool_name": "build_turn_artifacts",
                        "status": "fallback",
                        "message": "本轮上下文构建异常，已切换到保守回答模式。",
                        "detail": warning,
                        "output": {
                            "route": "clarification_needed",
                        },
                    }
                ],
            )
            try:
                overview = build_document_overview(
                    document=document,
                    payload=extraction_payload,
                    summary_text=summary_text,
                    current_object_lock=current_object_lock,
                )
                artifacts.route = "document_summary"
                artifacts.answer_context = overview
                artifacts.fallback_answer = fallback_answer("document_summary", overview)
            except Exception:
                artifacts.answer_context = {
                    "summary_text": summary_text,
                    "matched_fields": [],
                    "matched_trace_hits_count": 0,
                }
                artifacts.fallback_answer = (
                    "当前这轮回答在组织上下文时发生异常。"
                    "我已经切换到保守模式，避免流式中断。"
                    "你可以直接重试刚才的问题，或指定字段名、表格、行号、图片对象继续提问。"
                )
            return artifacts

    @staticmethod
    def _provider_fallback_text(base_fallback: str, *, partial_answer_exists: bool) -> str:
        fallback = str(base_fallback or "").strip() or "当前无法生成更详细的模型回答，我先返回基于结构化事实整理出的结果。"
        if not partial_answer_exists:
            return fallback
        return (
            "\n\n补充说明：模型流式输出在本轮中途中断，"
            "以下内容改为基于已解析事实进行保守补全。\n"
            f"{fallback}"
        )

    async def _build_turn_artifacts(
        self,
        *,
        document: DocumentExtractionResponse,
        summary_text: str,
        user_message: str,
        top_k: int,
        current_object_lock: Optional[Dict[str, Any]],
        extraction_payload: Dict[str, Any],
    ) -> TurnArtifacts:
        route = classify_route(
            user_message=user_message,
            payload=extraction_payload,
            current_object_lock=current_object_lock,
        )
        artifacts = TurnArtifacts(route=route)
        if extraction_payload:
            artifacts.tool_events.append(
                {
                    "tool_name": "load_extraction_payload",
                    "status": "done",
                    "message": "已加载当前文档的结构化上下文",
                    "detail": f"tables={len(extraction_payload.get('tables', []) or [])}, figures={len(extraction_payload.get('figures', []) or [])}",
                    "output": {
                        "table_count": len(extraction_payload.get("tables", []) or []),
                        "figure_count": len(extraction_payload.get("figures", []) or []),
                    },
                }
            )

        if route == "table_lookup":
            started = time.perf_counter()
            result = locate_table_answer(
                document=document,
                payload=extraction_payload,
                user_message=user_message,
                current_object_lock=current_object_lock,
            )
            artifacts.tool_events.append(
                {
                    "tool_name": "locate_table_cells",
                    "status": "done" if result else "empty",
                    "message": "已完成表格行列定位" if result else "当前没有稳定定位到目标表格行",
                    "detail": str((result or {}).get("table_id") or ""),
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "output": {
                        "found": bool(result),
                        "table_id": str((result or {}).get("table_id") or ""),
                    },
                }
            )
            if result:
                artifacts.citations = [result["citation"]]
                artifacts.current_object_lock = result["current_object_lock"]
                artifacts.answer_context = dict(result)
                artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
                return artifacts
            artifacts.warnings.append("当前未稳定定位到目标表格行。")
            artifacts.route = "clarification_needed"
            artifacts.answer_context = {
                "matched_fields": [],
                "matched_trace_hits_count": 0,
                "document_overview": build_document_overview(
                    document=document,
                    payload=extraction_payload,
                    summary_text=summary_text,
                    current_object_lock=current_object_lock,
                ),
                "query": user_message,
            }
            artifacts.prefer_fallback_only = True
            artifacts.fallback_answer = (
                "当前没有在表格中稳定定位到你指定的目标行。"
                "为了避免错把别的行当成答案，我这轮不会自动替代返回其他记录。"
                "你可以补充更准确的站点名称、行号、编码，或者先让我列出候选记录。"
            )
            return artifacts

        if route in {"figure_overview", "figure_value_read"}:
            started = time.perf_counter()
            user_message_lower = user_message.lower()
            figures = select_figures(
                document=document,
                payload=extraction_payload,
                user_message=user_message,
                top_k=max(1, min(top_k, 8)),
            )
            citations = build_figure_citations(document, figures)
            artifacts.tool_events.append(
                {
                    "tool_name": "read_figures" if route == "figure_overview" else "inspect_figure",
                    "status": "done" if citations else "empty",
                    "message": "已整理图表对象信息" if citations else "当前没有拿到稳定的图表对象信息",
                    "detail": f"count={len(citations)}",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "output": {"figure_count": len(citations)},
                }
            )
            figures_for_model: List[Dict[str, Any]] = []
            for citation in citations:
                payload_json = citation.get("payload") if isinstance(citation.get("payload"), dict) else {}
                figures_for_model.append(
                    {
                        "figure_id": str(payload_json.get("figure_id") or citation.get("object_id") or ""),
                        "page": payload_json.get("page") or citation.get("page"),
                        "caption": str(payload_json.get("caption") or citation.get("title") or ""),
                        "figure_type": str(payload_json.get("figure_type") or ""),
                        "key_points": list(payload_json.get("key_points") or [])[:4],
                        "dataframe_rows": list(payload_json.get("dataframe_rows") or [])[:4],
                        "content_modes": list(payload_json.get("content_modes") or [])[:4],
                    }
                )
            fallback_fields: List[Dict[str, Any]] = []
            fallback_trace_hits: List[Dict[str, Any]] = []
            fallback_tables: List[Dict[str, Any]] = []
            if not figures_for_model:
                fallback_tables = build_table_overview_context(
                    select_tables(extraction_payload, user_message, top_k=2),
                    max_rows=3,
                    max_cells=5,
                )
                fallback_fields = match_fields(document, user_message, top_k=4)
                fallback_trace_hits = collect_trace_hits(document, fallback_fields, user_message, top_k=8)
                fallback_fields = enrich_matched_fields_with_trace_hits(fallback_fields, fallback_trace_hits)
                artifacts.matched_fields = fallback_fields
                artifacts.matched_trace_hits = fallback_trace_hits
            artifacts.citations = (
                citations
                or build_table_overview_citations(document, fallback_tables)
                or build_field_citations(fallback_fields, fallback_trace_hits)
            )
            artifacts.answer_context = {
                "figures": figures_for_model,
                "figure_count": len(figures_for_model),
                "summary_text": summary_text,
                "fallback_tables": fallback_tables[:2],
                "fallback_fields": fallback_fields[:4],
                "recognition_tier": (
                    "figure"
                    if figures_for_model
                    else ("ocr_table_only" if fallback_tables else ("ocr_field_only" if fallback_fields else "none"))
                ),
            }
            if figures_for_model:
                first = figures_for_model[0]
                artifacts.current_object_lock = {
                    "lock_type": "figure",
                    "object_id": str(first.get("figure_id") or ""),
                    "label": str(first.get("caption") or first.get("figure_id") or "图表"),
                    "page": first.get("page"),
                    "ref_id": str((citations[0] or {}).get("ref_id") or "") if citations else None,
                    "metadata": {"figure_type": str(first.get("figure_type") or "")},
                }
            else:
                artifacts.warnings.append("当前只拿到了较弱的图表线索，尚未形成稳定的 figure 级结果。")
            if (
                not figures_for_model
                and fallback_fields
                and any(token in user_message_lower for token in ("字段级", "字段事实", "ref_id", "页码", "page", "写明", "列出"))
            ):
                artifacts.prefer_fallback_only = True
            artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
            return artifacts

        if route == "document_summary":
            overview = build_document_overview(
                document=document,
                payload=extraction_payload,
                summary_text=summary_text,
                current_object_lock=current_object_lock,
            )
            artifacts.tool_events.append(
                {
                    "tool_name": "summarize_document_context",
                    "status": "done",
                    "message": "已整理文档概览上下文",
                    "detail": f"fields={overview.get('field_count', 0)}, tables={overview.get('table_count', 0)}, figures={overview.get('figure_count', 0)}",
                }
            )
            artifacts.answer_context = overview
            artifacts.fallback_answer = fallback_answer(route, overview)
            return artifacts

        matched_fields = match_fields(document, user_message, top_k=max(1, min(top_k, 8)))
        matched_trace_hits = collect_trace_hits(document, matched_fields, user_message, top_k=max(6, top_k))
        matched_fields = enrich_matched_fields_with_trace_hits(matched_fields, matched_trace_hits)
        artifacts.tool_events.append(
            {
                "tool_name": "match_fields",
                "status": "done" if matched_fields else "empty",
                "message": "已完成字段与溯源片段匹配" if matched_fields else "当前没有稳定命中的目标字段",
                "detail": f"field_count={len(matched_fields)}, trace_count={len(matched_trace_hits)}",
                "output": {"field_count": len(matched_fields), "trace_count": len(matched_trace_hits)},
            }
        )
        artifacts.matched_fields = matched_fields
        artifacts.matched_trace_hits = matched_trace_hits
        artifacts.citations = build_field_citations(matched_fields, matched_trace_hits)
        if route == "database_action":
            artifacts.action_preview = build_action_preview(
                user_message,
                document,
                matched_fields,
                payload=extraction_payload,
                current_object_lock=current_object_lock,
            )
            preview_payload = (
                artifacts.action_preview.get("payload")
                if isinstance(artifacts.action_preview, dict) and isinstance(artifacts.action_preview.get("payload"), dict)
                else {}
            )
            preview_citations = build_action_preview_citations(artifacts.action_preview)
            if preview_payload.get("focus_scope") == "table_row":
                artifacts.current_object_lock = {
                    "lock_type": "table_row",
                    "object_id": str(preview_payload.get("table_id") or ""),
                    "label": f"{str(preview_payload.get('table_id') or '表格')} 第{preview_payload.get('row_index') or '?'}行",
                    "page": preview_payload.get("page"),
                    "ref_id": str((preview_citations[0] or {}).get("ref_id") or "") if preview_citations else None,
                    "table_id": str(preview_payload.get("table_id") or ""),
                    "row_index": preview_payload.get("row_index"),
                    "source_row_index": preview_payload.get("source_row_index"),
                    "metadata": {
                        "header": str(((preview_citations[0] or {}).get("title") or "")) if preview_citations else "",
                    },
                }
            artifacts.citations = preview_citations or artifacts.citations
            artifacts.answer_context = {
                "action_preview": artifacts.action_preview,
                "matched_fields": matched_fields[:6],
                "summary_text": summary_text,
            }
            artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
            return artifacts

        if matched_fields:
            first = matched_fields[0]
            artifacts.current_object_lock = {
                "lock_type": "field",
                "object_id": str(first.get("field_name") or ""),
                "label": str(first.get("label") or first.get("field_name") or "字段"),
                "page": first.get("page"),
                "ref_id": first.get("source_ref_id"),
                "metadata": {},
            }
        else:
            overview = build_document_overview(document=document, payload=extraction_payload, summary_text=summary_text)
            artifacts.warnings.append("当前没有稳定匹配到字段，我改为基于整体文档上下文来组织回答。")
            artifacts.route = "clarification_needed"
            artifacts.answer_context = {
                "matched_fields": [],
                "matched_trace_hits_count": len(matched_trace_hits),
                "document_overview": overview,
            }
            artifacts.fallback_answer = fallback_answer(artifacts.route, artifacts.answer_context)
            return artifacts

        artifacts.answer_context = {
            "matched_fields": matched_fields[:6],
            "matched_trace_hits_count": len(matched_trace_hits),
            "summary_text": summary_text,
        }
        artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
        return artifacts

    async def _complete_answer_text(
        self,
        *,
        route: str,
        user_message: str,
        summary_text: str,
        history: List[Dict[str, Any]],
        answer_context: Dict[str, Any],
        fallback: str,
    ) -> str:
        if not self._provider or not self._provider.configured:
            return fallback
        try:
            messages = build_answer_messages(
                route=route,
                user_message=user_message,
                summary_text=summary_text,
                history=history,
                answer_context=dump_context_for_model(answer_context),
            )
            result = await asyncio.to_thread(
                self._provider.complete,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            content = str(getattr(result, "content", "") or "").strip()
            return content or fallback
        except Exception:
            return fallback

    async def _stream_provider_text(self, messages: List[Dict[str, Any]]) -> AsyncIterator[str]:
        if not self._provider or not self._provider.configured:
            raise RuntimeError("assistant provider is not configured")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        def _worker() -> None:
            try:
                for chunk in self._provider.stream_text(
                    messages=messages,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                ):
                    asyncio.run_coroutine_threadsafe(queue.put(("delta", chunk)), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(("error", f"{type(exc).__name__}: {exc}")), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(("done", "")), loop)

        threading.Thread(target=_worker, daemon=True).start()

        while True:
            kind, payload = await queue.get()
            if kind == "delta":
                if payload:
                    yield payload
                continue
            if kind == "error":
                raise RuntimeError(payload)
            break

    @staticmethod
    def _to_session_message(item: Dict[str, Any]) -> AssistantSessionMessage:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        return AssistantSessionMessage(
            message_id=str(item.get("message_id") or ""),
            role=str(item.get("role") or ""),
            message_type=str(item.get("message_type") or "assistant_text"),
            content=str(item.get("content") or ""),
            payload=payload,
            created_at=str(item.get("created_at") or ""),
        )
