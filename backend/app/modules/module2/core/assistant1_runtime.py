from __future__ import annotations

import asyncio
import importlib
import json
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Iterator

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.core.config import Settings
from app.core.assistant_config import AssistantSettings
from app.integrations.assistant_provider import AssistantResponsesProvider

from .config import ExtractionSettings, get_extraction_settings
from .assistant1_upstream_runtime import Assistant1UpstreamRuntime


ASSISTANT1_STREAM_PROTOCOL = "assistant1.sse.v1"
_REF_PATTERN = re.compile(r"<ref id=\"([^\"]+)\">(.*?)</ref>", re.DOTALL)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _sse_event(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {str(event or 'message').strip()}\ndata: {payload}\n\n".encode("utf-8")


def _join_non_empty(parts: Iterable[str], sep: str = "\n") -> str:
    return sep.join([str(part).strip() for part in parts if str(part or "").strip()]).strip()


def _backend_root_dir() -> Path:
    return Path(__file__).resolve().parents[4]


def _ensure_backend_root_on_path() -> None:
    backend_root = str(_backend_root_dir())
    if backend_root not in sys.path:
        sys.path.append(backend_root)


def _assistant1_stream_module_candidates() -> tuple[str, ...]:
    return ("app.modules.module2.assistant_1.stream_runtime",)


def _assistant1_grounding_module_candidates() -> tuple[str, ...]:
    return ("app.modules.module2.assistant_1.frontend_grounding",)


def _load_legacy_assistant1_stream_module() -> Any:
    _ensure_backend_root_on_path()
    last_error: Exception | None = None
    for module_name in _assistant1_stream_module_candidates():
        try:
            return importlib.import_module(module_name)
        except Exception as exc:
            last_error = exc
    detail = f"{type(last_error).__name__}: {last_error}" if last_error is not None else "unknown error"
    raise RuntimeError(f"failed to import legacy assistant1 runtime: {detail}")


@lru_cache(maxsize=1)
def get_legacy_assistant1_runtime() -> Any:
    stream_module = _load_legacy_assistant1_stream_module()
    runtime_cls = getattr(stream_module, "Assistant1StreamingRuntime", None)
    if runtime_cls is None:
        raise RuntimeError("legacy assistant1 runtime class is unavailable")
    return runtime_cls()


@lru_cache(maxsize=1)
def _load_frontend_grounding_module() -> Any | None:
    _ensure_backend_root_on_path()
    for module_name in _assistant1_grounding_module_candidates():
        try:
            return importlib.import_module(module_name)
        except Exception:
            continue
    return None


@dataclass(frozen=True)
class Assistant1ContextBundle:
    file_hash: str = ""
    file_name: str = ""
    track: str = ""
    job_id: str = ""
    extraction_status: str = ""
    source_excerpt: str = ""
    source_artifact_path: str = ""
    source_artifact_url: str = ""
    result_fields: tuple[dict[str, Any], ...] = ()
    trace_hits: tuple[dict[str, Any], ...] = ()
    evidence_items: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def has_grounded_context(bundle: Assistant1ContextBundle) -> bool:
    return bool(
        bundle.result_fields
        or bundle.trace_hits
        or bundle.evidence_items
        or str(bundle.source_excerpt or "").strip()
    )


def build_assistant1_context_bundle(
    settings: Settings,
    *,
    file_hash: str,
    top_k: int = 5,
    extraction_settings: ExtractionSettings | None = None,
) -> Assistant1ContextBundle:
    extraction_cfg = extraction_settings or get_extraction_settings()
    normalized_hash = str(file_hash or "").strip().lower()
    if not normalized_hash:
        return Assistant1ContextBundle(warnings=("assistant_context_fallback:no_file_hash",))

    shadow_match = _find_latest_shadow_match(settings, normalized_hash)
    source_match = _find_source_match(settings, normalized_hash, extraction_cfg)

    file_name = str(source_match.get("file_name") or shadow_match.get("file_name") or "").strip()
    track = str(source_match.get("track") or shadow_match.get("track") or "").strip()
    result_fields = tuple(_extract_result_fields(shadow_match.get("document")))
    trace_hits = tuple(_extract_trace_hits(shadow_match.get("document"), limit=top_k))
    source_excerpt, source_refs = _read_source_excerpt(
        source_match.get("markdown_path"),
        max_chars=extraction_cfg.assistant1_context_max_source_chars,
        max_refs=extraction_cfg.assistant1_context_max_refs,
    )
    evidence_items = tuple(_build_context_evidence_items(trace_hits, source_refs, file_name=file_name, top_k=top_k))

    warnings: list[str] = []
    if not shadow_match:
        warnings.append("assistant_context_fallback:no_shadow_snapshot")
    if not source_match:
        warnings.append("assistant_context_fallback:no_source_markdown")
    if not result_fields and not trace_hits and not source_excerpt:
        warnings.append("assistant_context_fallback:no_document_context")

    metadata = {
        "shadow_found": bool(shadow_match),
        "source_found": bool(source_match),
        "shadow_path": str(shadow_match.get("snapshot_path") or ""),
        "source_meta_path": str(source_match.get("meta_path") or ""),
    }
    return Assistant1ContextBundle(
        file_hash=normalized_hash,
        file_name=file_name,
        track=track,
        job_id=str(shadow_match.get("job_id") or "").strip(),
        extraction_status=str(shadow_match.get("status") or "").strip(),
        source_excerpt=source_excerpt,
        source_artifact_path=str(source_match.get("markdown_artifact_path") or "").strip(),
        source_artifact_url=str(source_match.get("markdown_artifact_url") or "").strip(),
        result_fields=result_fields,
        trace_hits=trace_hits,
        evidence_items=evidence_items,
        warnings=tuple(warnings),
        metadata=metadata,
    )


def resolve_extraction_artifact_root(
    settings: Settings,
    extraction_settings: ExtractionSettings | None = None,
) -> Path:
    extraction_settings = extraction_settings or get_extraction_settings()
    configured = str(extraction_settings.artifact_root_dir or "").strip()
    default_path = (settings.data_root_dir / "module2" / "artifacts").resolve()
    return _resolve_module2_path(settings, configured, default_path)


def candidate_shadow_roots(settings: Settings) -> tuple[Path, ...]:
    roots = [
        (settings.data_root_dir / "module2" / "runlogs" / "unified_extraction_shadow_jobs").resolve(),
        (settings.runtime_root_dir / "module2" / "runlogs" / "unified_extraction_shadow_jobs").resolve(),
        (settings.runtime_root_dir / "backend" / "app" / "modules" / "module2" / "runlogs" / "unified_extraction_shadow_jobs").resolve(),
        # Legacy fallback path (kept during migration window).
        (settings.runtime_root_dir / "backend" / "module2" / "runlogs" / "unified_extraction_shadow_jobs").resolve(),
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return tuple(unique)


def _resolve_module2_path(settings: Settings, raw_value: str, default_path: Path) -> Path:
    raw = str(raw_value or "").strip()
    if not raw:
        return default_path.resolve()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    module2_root = (settings.runtime_root_dir / "backend" / "app" / "modules" / "module2").resolve()
    candidate_module2 = (module2_root / path).resolve()
    candidate_repo = (settings.runtime_root_dir / path).resolve()
    normalized = raw.replace("\\", "/").lower()
    if normalized.startswith("backend/app/modules/module2/"):
        return candidate_repo
    if candidate_repo.exists() and not candidate_module2.exists():
        return candidate_repo
    return candidate_module2


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _find_latest_shadow_match(settings: Settings, file_hash: str) -> dict[str, Any]:
    best_match: dict[str, Any] = {}
    best_updated_at = -1.0
    for root in candidate_shadow_roots(settings):
        if not root.exists() or not root.is_dir():
            continue
        for path in root.glob("*.json"):
            raw_snapshot = _read_json_file(path)
            payload = raw_snapshot.get("payload") if isinstance(raw_snapshot.get("payload"), dict) else raw_snapshot
            if not isinstance(payload, dict):
                continue
            document_match = _find_document_by_hash(payload.get("documents"), file_hash)
            file_match = _find_document_by_hash(payload.get("files"), file_hash)
            if not document_match and not file_match:
                continue
            updated_at = float(payload.get("updated_at") or 0.0)
            if updated_at < best_updated_at:
                continue
            best_updated_at = updated_at
            best_match = {
                "job_id": str(payload.get("job_id") or "").strip(),
                "status": str(payload.get("status") or "").strip(),
                "track": str((document_match or file_match or {}).get("track") or "").strip(),
                "file_name": str((document_match or file_match or {}).get("file_name") or "").strip(),
                "document": document_match,
                "file": file_match,
                "snapshot_path": str(path),
            }
    return best_match


def _find_document_by_hash(items: Any, file_hash: str) -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    normalized_hash = str(file_hash or "").strip().lower()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_hash = str(item.get("file_hash") or "").strip().lower()
        if item_hash == normalized_hash:
            return item
    return {}


def _find_source_match(
    settings: Settings,
    file_hash: str,
    extraction_settings: ExtractionSettings | None = None,
) -> dict[str, Any]:
    artifact_root = resolve_extraction_artifact_root(settings, extraction_settings)
    source_root = artifact_root / "assistant_1_source"
    candidate_dirs = [source_root / file_hash[:12]]
    if not candidate_dirs[0].exists():
        candidate_dirs = [source_root]

    for base_dir in candidate_dirs:
        if not base_dir.exists() or not base_dir.is_dir():
            continue
        iterator = base_dir.rglob("*_meta_*.json") if base_dir == source_root else base_dir.glob("*_meta_*.json")
        for meta_path in iterator:
            payload = _read_json_file(meta_path)
            if str(payload.get("file_hash") or "").strip().lower() != file_hash:
                continue
            markdown_artifact_path = str(payload.get("markdown_artifact_path") or "").strip()
            markdown_artifact_url = str(payload.get("markdown_artifact_url") or "").strip()
            markdown_path = (artifact_root / markdown_artifact_path).resolve() if markdown_artifact_path else Path()
            return {
                "meta_path": str(meta_path),
                "markdown_path": str(markdown_path) if markdown_artifact_path else "",
                "markdown_artifact_path": markdown_artifact_path,
                "markdown_artifact_url": markdown_artifact_url,
                "file_name": str(payload.get("file_name") or "").strip(),
                "track": str(payload.get("track") or "").strip(),
            }
    return {}


def _extract_result_fields(document: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    raw_result = document.get("result")
    if not isinstance(raw_result, dict):
        return []
    result_map = raw_result.get("root") if isinstance(raw_result.get("root"), dict) else raw_result
    if not isinstance(result_map, dict):
        return []
    result_fields: list[dict[str, Any]] = []
    for field_name, entity in result_map.items():
        if not isinstance(entity, dict):
            continue
        value = entity.get("value")
        if value in (None, "", [], {}):
            continue
        result_fields.append(
            {
                "field_name": str(field_name),
                "value": _clean_text(value, max_len=140),
                "confidence": float(entity.get("confidence") or 0.0),
                "source_ref_id": str(entity.get("source_ref_id") or "").strip(),
            }
        )
        if len(result_fields) >= limit:
            break
    return result_fields


def _extract_trace_hits(document: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    hits = document.get("trace_hits")
    if not isinstance(hits, list):
        return []
    out: list[dict[str, Any]] = []
    for item in hits:
        if not isinstance(item, dict):
            continue
        snippet = _clean_text(item.get("snippet"), max_len=180)
        if not snippet:
            continue
        out.append(
            {
                "file_name": str(item.get("file_name") or document.get("file_name") or "").strip(),
                "file_hash": str(item.get("file_hash") or document.get("file_hash") or "").strip(),
                "object_type": str(item.get("object_type") or "").strip(),
                "object_id": str(item.get("object_id") or "").strip(),
                "ref_id": str(item.get("ref_id") or "").strip(),
                "page": item.get("page"),
                "snippet": snippet,
            }
        )
        if len(out) >= limit:
            break
    return out


def _read_source_excerpt(markdown_path_raw: Any, *, max_chars: int, max_refs: int) -> tuple[str, list[dict[str, Any]]]:
    markdown_path = Path(str(markdown_path_raw or "").strip())
    if not markdown_path.exists() or not markdown_path.is_file():
        return "", []
    text = markdown_path.read_text(encoding="utf-8", errors="ignore")
    refs: list[dict[str, Any]] = []
    for match in _REF_PATTERN.finditer(text):
        ref_id = str(match.group(1) or "").strip()
        ref_text = _clean_text(match.group(2), max_len=220)
        if not ref_id or not ref_text:
            continue
        refs.append(
            {
                "ref_id": ref_id,
                "title": ref_id,
                "snippet": ref_text,
                "unit_id": ref_id,
                "unit_type": "source_ref",
            }
        )
        if len(refs) >= max_refs:
            break
    compact_excerpt = _clean_text(text, max_len=max_chars)
    return compact_excerpt, refs


def _build_context_evidence_items(
    trace_hits: tuple[dict[str, Any], ...],
    source_refs: list[dict[str, Any]],
    *,
    file_name: str,
    top_k: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for hit in trace_hits[:top_k]:
        items.append(
            {
                "title": str(hit.get("object_id") or hit.get("object_type") or file_name or "trace"),
                "snippet": str(hit.get("snippet") or "").strip(),
                "ref_id": str(hit.get("ref_id") or "").strip(),
                "unit_id": str(hit.get("object_id") or hit.get("ref_id") or "").strip(),
                "unit_type": str(hit.get("object_type") or "field").strip(),
                "page_start": hit.get("page"),
            }
        )
    if items:
        return items[:top_k]
    return source_refs[:top_k]


def _clean_text(value: Any, *, max_len: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3].rstrip() + "..."


class Assistant1SSEEmitter:
    def __init__(self, *, session_id: str = "", debug: bool = False) -> None:
        self.session_id = str(session_id or "").strip() or _new_id("sess")
        self.run_id = _new_id("run")
        self.turn_id = _new_id("turn")
        self.assistant_message_id = _new_id("msg")
        self.debug = bool(debug)
        self._seq = 0

    def event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        phase: str = "",
        visibility: str = "user",
    ) -> bytes | None:
        normalized_visibility = str(visibility or "user").strip().lower() or "user"
        if normalized_visibility == "debug" and not self.debug:
            return None
        self._seq += 1
        envelope = {
            "version": ASSISTANT1_STREAM_PROTOCOL,
            "type": str(event_type or "message").strip() or "message",
            "seq": self._seq,
            "run_id": self.run_id,
            "turn_id": self.turn_id,
            "ts": _now_iso(),
            "visibility": normalized_visibility,
            "phase": str(phase or "").strip(),
            "payload": payload,
        }
        return _sse_event(envelope["type"], envelope)

    def stream_open(self) -> bytes | None:
        return self.event(
            "stream.open",
            {
                "protocol": ASSISTANT1_STREAM_PROTOCOL,
                "session_id": self.session_id,
                "assistant_message_id": self.assistant_message_id,
            },
            phase="init",
        )

    def assistant_start(self) -> bytes | None:
        return self.event(
            "assistant.start",
            {
                "session_id": self.session_id,
                "assistant_message_id": self.assistant_message_id,
            },
            phase="init",
        )

    def status(self, code: str, label: str, detail: str = "", *, phase: str = "") -> bytes | None:
        return self.event(
            "status",
            {
                "code": str(code or "").strip(),
                "label": str(label or "").strip(),
                "detail": str(detail or "").strip(),
                "blocking": False,
            },
            phase=phase or code,
        )

    def evidence_bundle(self, items: list[dict[str, Any]], *, phase: str = "retrieving") -> bytes | None:
        return self.event(
            "evidence.bundle",
            {
                "render_hint": "side_panel_only",
                "items": items if isinstance(items, list) else [],
            },
            phase=phase,
        )

    def delta(self, text: str, *, phase: str = "answering") -> bytes | None:
        return self.event("assistant.delta", {"text": str(text or "")}, phase=phase)

    def replace(self, text: str, *, reason: str = "final_cleanup", phase: str = "finalizing") -> bytes | None:
        return self.event(
            "assistant.replace",
            {"text": str(text or ""), "reason": str(reason or "final_cleanup").strip()},
            phase=phase,
        )

    def warning(self, code: str, message: str, *, phase: str = "warning") -> bytes | None:
        return self.event(
            "warning",
            {"code": str(code or "").strip(), "message": str(message or "").strip(), "recoverable": True},
            phase=phase,
        )

    def heartbeat(self, idle_ms: int, *, phase: str = "heartbeat") -> bytes | None:
        return self.event(
            "heartbeat",
            {"idle_ms": max(0, int(idle_ms or 0))},
            phase=phase,
            visibility="debug",
        )

    def error(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool = True,
        can_retry: bool = True,
        phase: str = "error",
    ) -> bytes | None:
        return self.event(
            "error",
            {
                "code": str(code or "").strip(),
                "message": str(message or "").strip(),
                "recoverable": bool(recoverable),
                "can_retry": bool(can_retry),
            },
            phase=phase,
        )

    def done(
        self,
        *,
        final_text: str,
        finish_reason: str = "completed",
        warnings: list[str] | None = None,
        phase: str = "done",
    ) -> bytes | None:
        payload: dict[str, Any] = {
            "final_text": str(final_text or ""),
            "finish_reason": str(finish_reason or "completed").strip() or "completed",
            "requires_followup": False,
        }
        cleaned_warnings = [str(item).strip() for item in warnings or [] if str(item or "").strip()]
        if cleaned_warnings:
            payload["warnings"] = cleaned_warnings
        return self.event("assistant.done", payload, phase=phase)


class ExtractionAssistant1Provider:
    @property
    def configured(self) -> bool:
        raise NotImplementedError

    @property
    def model(self) -> str:
        raise NotImplementedError

    @property
    def base_url(self) -> str:
        raise NotImplementedError

    @property
    def endpoint_path(self) -> str:
        raise NotImplementedError

    def stream_text(self, *, messages: list[dict[str, Any]], instructions: str) -> Iterator[str]:
        raise NotImplementedError

    def complete_text(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_verbosity: str | None = None,
    ) -> str:
        raise NotImplementedError


class OpenAIExtractionAssistant1Provider(ExtractionAssistant1Provider):
    def __init__(
        self,
        provider: AssistantResponsesProvider | None = None,
        settings: AssistantSettings | None = None,
    ) -> None:
        self._provider = provider or AssistantResponsesProvider(settings or AssistantSettings.from_env())
        self.settings = self._provider.settings

    @property
    def configured(self) -> bool:
        return bool(self._provider.configured)

    @property
    def model(self) -> str:
        return str(self._provider.model or "")

    @property
    def base_url(self) -> str:
        return str(self._provider.base_url or "")

    @property
    def endpoint_path(self) -> str:
        return str(self._provider.endpoint_path or "")

    def stream_text(self, *, messages: list[dict[str, Any]], instructions: str) -> Iterator[str]:
        return self._provider.stream_text(messages=messages, instructions=instructions)

    def complete_text(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_verbosity: str | None = None,
    ) -> str:
        return self._provider.complete_text(
            messages=messages,
            instructions=instructions,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
        )


@dataclass(frozen=True)
class _ProviderPlan:
    max_output_tokens: int | None
    reasoning_effort: str | None
    text_verbosity: str | None


class NativeAssistant1Runtime:
    def __init__(
        self,
        extraction_settings: ExtractionSettings | None = None,
        *,
        provider: ExtractionAssistant1Provider | None = None,
    ) -> None:
        self.extraction_settings = extraction_settings or get_extraction_settings()
        self.provider = provider or OpenAIExtractionAssistant1Provider()
        self.heartbeat_interval_sec = 4.0

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        readiness = self.request_readiness_payload(settings)
        runtime_ready = bool(readiness.get("runtime_ready"))
        return {
            "ok": runtime_ready,
            "configured": bool(self.provider.configured),
            "runtime_ready": runtime_ready,
            "model": str(self.provider.model or ""),
            "base_url": str(self.provider.base_url or ""),
            "endpoint_path": str(self.provider.endpoint_path or ""),
            "tavily_configured": False,
            "context_required": False,
            "context_found": True,
            "fallback_recommended": False,
        }

    def request_readiness_payload(self, settings: Settings, *, file_hash: str = "") -> dict[str, Any]:
        normalized_hash = str(file_hash or "").strip().lower()
        context_required = bool(normalized_hash)
        bundle = (
            build_assistant1_context_bundle(
                settings,
                file_hash=normalized_hash,
                top_k=5,
                extraction_settings=self.extraction_settings,
            )
            if context_required
            else Assistant1ContextBundle()
        )
        context_found = has_grounded_context(bundle) if context_required else True
        runtime_ready = bool(self.provider.configured)
        fallback_recommended = runtime_ready and context_required and not context_found
        return {
            "ok": runtime_ready and (not context_required or context_found),
            "configured": bool(self.provider.configured),
            "runtime_ready": runtime_ready,
            "context_required": context_required,
            "context_found": context_found,
            "fallback_recommended": fallback_recommended,
            "warnings": list(bundle.warnings),
            "metadata": dict(bundle.metadata),
            "file_hash": normalized_hash,
        }

    async def stream_chat(
        self,
        *,
        settings: Settings,
        user_message: str,
        file_hash: str = "",
        history: list[dict[str, Any]] | None = None,
        max_steps: int = 6,
        top_k: int = 5,
        session_id: str = "",
        debug: bool = False,
        client_supports_replace: bool = True,
        extra_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[bytes]:
        del max_steps
        emitter = Assistant1SSEEmitter(session_id=session_id, debug=debug)
        warnings: list[str] = []
        for packet in (emitter.stream_open(), emitter.assistant_start()):
            if packet:
                yield packet

        question = str(user_message or "").strip()
        if not question:
            error_packet = emitter.error("empty_message", "这次没有收到有效问题，请直接输入你想问的内容。")
            if error_packet:
                yield error_packet
            done_packet = emitter.done(final_text="", finish_reason="error_recovered")
            if done_packet:
                yield done_packet
            return

        if not self.provider.configured:
            error_packet = emitter.error(
                "provider_not_configured",
                "当前 Assistant1 模型尚未配置完成，暂时无法开始回答。",
                recoverable=False,
                can_retry=False,
            )
            if error_packet:
                yield error_packet
            done_packet = emitter.done(final_text="", finish_reason="error_recovered")
            if done_packet:
                yield done_packet
            return

        direct_snapshot_answer = self._build_frontend_snapshot_answer(
            user_message=question,
            extra_context=extra_context,
        )
        if self._should_short_circuit_with_frontend_snapshot(
            user_message=question,
            snapshot_answer=direct_snapshot_answer,
            extra_context=extra_context,
        ):
            preparing_packet = emitter.status(
                "preparing",
                "正在准备文档上下文",
                "我先对齐当前文档快照里的关键字段和摘要。",
                phase="preparing",
            )
            if preparing_packet:
                yield preparing_packet
            answer_packet = emitter.status(
                "answering",
                "正在整理回答",
                "我先基于当前文档快照直接给你返回可以确定的结果。",
                phase="answering",
            )
            if answer_packet:
                yield answer_packet
            delta_packet = emitter.delta(direct_snapshot_answer, phase="answering")
            if delta_packet:
                yield delta_packet
            finalizing_packet = emitter.status(
                "finalizing",
                "正在收尾",
                "我把这一轮的结果再对齐一下，确保表述和证据一致。",
                phase="finalizing",
            )
            if finalizing_packet:
                yield finalizing_packet
            done_packet = emitter.done(
                final_text=direct_snapshot_answer,
                finish_reason="frontend_snapshot_short_circuit",
                warnings=warnings,
            )
            if done_packet:
                yield done_packet
            return

        context_bundle = self._build_context(settings, file_hash=file_hash, top_k=top_k)
        preparing_packet = emitter.status(
            "preparing",
            "正在准备文档上下文",
            "我先对齐当前文件的抽取结果、证据片段和原文摘录。",
            phase="preparing",
        )
        if preparing_packet:
            yield preparing_packet

        evidence_items = self._build_stream_evidence_items(context_bundle, top_k=top_k)
        if evidence_items:
            evidence_packet = emitter.evidence_bundle(evidence_items, phase="retrieving")
            if evidence_packet:
                yield evidence_packet
        elif str(file_hash or "").strip():
            warnings.append("assistant_context_missing")
            warning_packet = emitter.warning(
                "missing_context",
                "当前文件还没有可用的抽取上下文，我会尽量基于你的问题给出保守回答。",
            )
            if warning_packet:
                yield warning_packet

        answer_packet = emitter.status(
            "answering",
            "正在整理回答",
            "我会优先依据当前文件证据，用简体中文给出可核对的结论。",
            phase="answering",
        )
        if answer_packet:
            yield answer_packet

        plan = self._provider_plan()
        messages = self._trim_history(history) + [{"role": "user", "content": question}]
        instructions = self._build_instructions(
            context_bundle,
            extra_context=extra_context,
        )
        emitted_text = ""
        emitted_any = False

        try:
            async for chunk in self._stream_provider_text_async(messages=messages, instructions=instructions):
                if not chunk:
                    continue
                emitted_any = True
                emitted_text += chunk
                delta_packet = emitter.delta(chunk, phase="answering")
                if delta_packet:
                    yield delta_packet
        except Exception as exc:
            warnings.append(f"stream_error:{type(exc).__name__}")
            if emitted_any:
                warning_packet = emitter.warning(
                    "stream_interrupted",
                    "流式输出中途出现波动，我先保留已生成的内容。",
                )
                if warning_packet:
                    yield warning_packet
            else:
                recovered_text = await self._recover_full_text(
                    messages=messages,
                    instructions=instructions,
                    plan=plan,
                )
                if recovered_text:
                    emitted_text = recovered_text
                    packet = (
                        emitter.replace(recovered_text, reason="stream_recovery")
                        if client_supports_replace
                        else emitter.delta(recovered_text, phase="answering")
                    )
                    if packet:
                        yield packet
                else:
                    error_packet = emitter.error("provider_error", "本次回答暂时失败，请稍后再试。")
                    if error_packet:
                        yield error_packet
                    done_packet = emitter.done(final_text="", finish_reason="error_recovered", warnings=warnings)
                    if done_packet:
                        yield done_packet
                    return

        final_text = self._finalize_answer(emitted_text, context_bundle)
        final_text = self._ground_answer_with_frontend_context(
            user_message=question,
            answer=final_text,
            extra_context=extra_context,
        )
        if client_supports_replace and final_text and final_text != emitted_text:
            replace_packet = emitter.replace(final_text, reason="final_cleanup", phase="finalizing")
            if replace_packet:
                yield replace_packet

        finalizing_packet = emitter.status(
            "finalizing",
            "正在收尾",
            "我把这一轮结果再对齐一下，确保表达和证据一致。",
            phase="finalizing",
        )
        if finalizing_packet:
            yield finalizing_packet

        done_packet = emitter.done(final_text=final_text, finish_reason="completed", warnings=warnings)
        if done_packet:
            yield done_packet

    def _build_context(self, settings: Settings, *, file_hash: str, top_k: int) -> Assistant1ContextBundle:
        normalized_hash = str(file_hash or "").strip().lower()
        if not normalized_hash:
            return Assistant1ContextBundle()
        return build_assistant1_context_bundle(
            settings,
            file_hash=normalized_hash,
            top_k=max(1, min(8, int(top_k or 5))),
            extraction_settings=self.extraction_settings,
        )

    def _trim_history(self, history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        history_window = max(1, min(24, int(self.extraction_settings.assistant1_history_window or 12)))
        trimmed = list(history or [])[-history_window:]
        normalized: list[dict[str, Any]] = []
        for item in trimmed:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user").strip().lower() or "user"
            if role not in {"system", "user", "assistant", "developer"}:
                role = "user"
            content = str(item.get("content") or "").strip()
            if content:
                normalized.append({"role": role, "content": content})
        return normalized

    def _provider_plan(self) -> _ProviderPlan:
        settings = getattr(self.provider, "settings", None)
        return _ProviderPlan(
            max_output_tokens=getattr(settings, "chat_max_output_tokens", None),
            reasoning_effort=getattr(settings, "chat_reasoning_effort", None),
            text_verbosity=getattr(settings, "chat_text_verbosity", None),
        )

    def _build_instructions(
        self,
        bundle: Assistant1ContextBundle,
        *,
        extra_context: dict[str, Any] | None,
    ) -> str:
        sections = [
            "你是 smart-doc-flow 的文档抽取助手。",
            "请始终使用简体中文回答。",
            "优先依据当前文件的结构化抽取结果、trace 证据和原文摘录回答。",
            "如果证据不足，请明确说明“目前证据不足”，不要编造。",
            self._format_context_block(bundle),
            self._format_extra_context(extra_context),
        ]
        return _join_non_empty(sections, sep="\n\n")

    def _format_context_block(self, bundle: Assistant1ContextBundle) -> str:
        if not has_grounded_context(bundle):
            return "当前没有可用的文档证据上下文。若用户问题依赖文件内容，请明确说明证据不足。"
        lines: list[str] = []
        if bundle.file_name:
            lines.append(f"文件名: {bundle.file_name}")
        if bundle.track:
            lines.append(f"抽取链路: {bundle.track}")
        if bundle.result_fields:
            lines.append("结构化抽取结果:")
            for item in bundle.result_fields[:6]:
                field_name = str(item.get('field_name') or '').strip()
                value = str(item.get('value') or '').strip()
                confidence = float(item.get("confidence") or 0.0)
                ref_id = str(item.get("source_ref_id") or "").strip()
                suffix = f" (confidence={confidence:.2f})" if confidence else ""
                if ref_id:
                    suffix += f" [ref={ref_id}]"
                if field_name and value:
                    lines.append(f"- {field_name}: {value}{suffix}")
        if bundle.trace_hits:
            lines.append("证据片段:")
            for item in bundle.trace_hits[:5]:
                ref_id = str(item.get("ref_id") or "").strip()
                snippet = str(item.get("snippet") or "").strip()
                if snippet:
                    prefix = f"[{ref_id}] " if ref_id else ""
                    lines.append(f"- {prefix}{snippet}")
        if bundle.source_excerpt:
            lines.append("原文摘录:")
            lines.append(bundle.source_excerpt)
        return "\n".join(lines).strip()

    @staticmethod
    def _format_extra_context(extra_context: dict[str, Any] | None) -> str:
        if not isinstance(extra_context, dict) or not extra_context:
            return ""
        lines = ["附加上下文:"]
        for key, value in list(extra_context.items())[:8]:
            text = str(value or "").strip()
            if text:
                lines.append(f"- {key}: {text}")
        return "\n".join(lines).strip()

    @classmethod
    def _ground_answer_with_frontend_context(
        cls,
        *,
        user_message: str,
        answer: str,
        extra_context: dict[str, Any] | None,
    ) -> str:
        cleaned_answer = str(answer or "").strip()
        snapshot_answer = cls._build_frontend_snapshot_answer(
            user_message=user_message,
            extra_context=extra_context,
        )
        if not snapshot_answer:
            return cleaned_answer
        if cls._should_short_circuit_with_frontend_snapshot(
            user_message=user_message,
            snapshot_answer=snapshot_answer,
            extra_context=extra_context,
        ):
            return snapshot_answer
        if cls._should_prefer_snapshot_grounding(user_message) or cls._looks_like_placeholder_answer(cleaned_answer):
            return snapshot_answer
        return cleaned_answer

    @classmethod
    def _build_frontend_snapshot_answer(
        cls,
        *,
        user_message: str,
        extra_context: dict[str, Any] | None,
    ) -> str:
        frontend_grounding = _load_frontend_grounding_module()
        if frontend_grounding is not None:
            build_fn = getattr(frontend_grounding, "build_frontend_snapshot_answer", None)
            if callable(build_fn):
                try:
                    bridged_answer = str(
                        build_fn(user_message=user_message, extra_context=extra_context) or ""
                    ).strip()
                except Exception:
                    bridged_answer = ""
                if bridged_answer:
                    return bridged_answer

        if not isinstance(extra_context, dict):
            return ""
        current_document = extra_context.get("current_document")
        if not isinstance(current_document, dict):
            return ""

        summary = _clean_text(current_document.get("summary"), max_len=900)
        file_name = _clean_text(current_document.get("file_name"), max_len=200)
        top_fields = cls._extract_frontend_top_fields(current_document.get("top_fields"))
        table_row_samples = (
            current_document.get("table_row_samples")
            if isinstance(current_document.get("table_row_samples"), list)
            else []
        )
        question = str(user_message or "").strip()

        conditional_lookup_answer = cls._build_frontend_conditional_lookup_answer(
            question=question,
            table_row_samples=table_row_samples,
        )
        if conditional_lookup_answer:
            return conditional_lookup_answer

        matched_fields = cls._match_frontend_fields(question, top_fields)
        matched_field = matched_fields[0] if matched_fields else None
        if len(matched_fields) >= 2:
            return cls._format_frontend_multi_field_answer(
                question=question,
                file_name=file_name,
                summary=summary,
                top_fields=top_fields,
                matched_fields=matched_fields,
            )
        if matched_field and cls._should_short_circuit_with_frontend_snapshot(
            user_message=question,
            snapshot_answer=str(matched_field.get("value") or ""),
            extra_context=extra_context,
        ):
            return cls._format_frontend_field_value(question, matched_field)

        if matched_field and cls._looks_like_exact_field_question(question):
            return cls._format_frontend_field_answer(matched_field)

        if cls._should_prefer_snapshot_grounding(question):
            summary_line = summary or (f"当前选中文档《{file_name}》已完成解析。" if file_name else "当前选中文档已完成解析。")
            lines = [f"当前选中文档的核心内容：{summary_line}"]
            if top_fields:
                lines.append("当前最确定的3个字段：")
                for index, field in enumerate(top_fields[:3], start=1):
                    label = str(field.get("label") or "").strip() or f"字段{index}"
                    value = str(field.get("value") or "").strip() or "暂无可用值"
                    page = field.get("page")
                    confidence = field.get("confidence")
                    meta_parts: list[str] = []
                    if isinstance(page, int) and page > 0:
                        meta_parts.append(f"第{page}页")
                    if isinstance(confidence, int) and confidence > 0:
                        meta_parts.append(f"置信度{confidence}%")
                    meta = f"（{'，'.join(meta_parts)}）" if meta_parts else ""
                    lines.append(f"{index}. {label}：{value}{meta}")
            return "\n".join([line for line in lines if line.strip()]).strip()

        return ""

    @staticmethod
    def _should_short_circuit_with_frontend_snapshot(
        *,
        user_message: str,
        snapshot_answer: str,
        extra_context: dict[str, Any] | None = None,
    ) -> bool:
        frontend_grounding = _load_frontend_grounding_module()
        if frontend_grounding is not None:
            gate_fn = getattr(frontend_grounding, "should_short_circuit_with_frontend_snapshot", None)
            if callable(gate_fn):
                try:
                    return bool(
                        gate_fn(
                            user_message=user_message,
                            snapshot_answer=snapshot_answer,
                            extra_context=extra_context,
                        )
                    )
                except Exception:
                    pass

        if not str(snapshot_answer or "").strip():
            return False
        text = str(user_message or "").strip()
        if re.search(r"(只回答|只回|仅回答|仅返回)", text):
            return True
        if re.search(r"(only|just)\s+(the\s+)?(answer|number|digits?)", text, flags=re.IGNORECASE):
            return True
        if NativeAssistant1Runtime._is_conditional_row_lookup_question(text):
            lowered_snapshot = str(snapshot_answer or "").lower()
            if (
                "未找到" in snapshot_answer
                or "不唯一" in snapshot_answer
                or "证据" in snapshot_answer
                or "无法确认" in snapshot_answer
                or "ref_id" in lowered_snapshot
            ):
                return True
            return False
        if "只回答" in text:
            return True
        return NativeAssistant1Runtime._should_prefer_snapshot_grounding(text)

    @staticmethod
    def _should_prefer_snapshot_grounding(user_message: str) -> bool:
        text = str(user_message or "").strip()
        lowered = text.lower()
        if "字段" in text:
            return True
        if any(marker in lowered for marker in ("current document", "selected document", "summary", "summarize")):
            return True
        if any(
            marker in text
            for marker in (
                "当前选中文档",
                "当前选中的文档",
                "选中文档",
                "核心内容",
                "主要讲了什么",
                "重点是什么",
                "摘要",
                "概括",
                "总结",
            )
        ):
            return True
        if "字段" in text:
            return True
        markers = (
            "当前选中文档",
            "当前选中的文档",
            "选中文档",
            "核心内容",
            "主要讲了什么",
            "重点是什么",
            "摘要",
            "概括",
            "总结",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _looks_like_placeholder_answer(answer: str) -> bool:
        text = str(answer or "").strip()
        if not text:
            return False
        markers = (
            "此处填入",
            "文档顶部或封面上原文标题",
            "文档主要描述了",
            "主题/项目/事件/合同/报告等",
            "涉及的主体（人或机构）",
            "金额、数量、版本号、状态等",
            "标题、正文段落和若干条目/表格/签署信息",
            "当前值：[",
            "〈文档顶部或封面上原文标题〉",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _extract_frontend_top_fields(raw_fields: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        if not isinstance(raw_fields, list):
            return normalized
        for item in raw_fields[:12]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or "").strip()
            if not label or not value:
                continue
            confidence_raw = item.get("confidence")
            page_raw = item.get("page")
            normalized.append(
                {
                    "label": label,
                    "value": value,
                    "confidence": int(confidence_raw) if isinstance(confidence_raw, (int, float)) else None,
                    "page": int(page_raw) if isinstance(page_raw, (int, float)) else None,
                }
            )
        return normalized

    @staticmethod
    def _frontend_field_match_score(question: str, field: dict[str, Any]) -> int:
        label = re.sub(r"\s+", "", str(field.get("label") or ""))
        value = re.sub(r"\s+", "", str(field.get("value") or ""))
        if not label:
            return 0
        score = 0
        if label in question:
            score += 12 + len(label)
        if question and question in label:
            score += 4
        for token in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", label):
            token = token.strip()
            if len(token) >= 2 and token in question:
                score += 3
        if value and len(value) <= 24 and value in question:
            score += 1
        return score

    @classmethod
    def _match_frontend_fields(
        cls,
        question: str,
        fields: list[dict[str, Any]],
        *,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        normalized_question = re.sub(r"\s+", "", str(question or ""))
        ranked: list[tuple[int, int, int, dict[str, Any]]] = []
        for field in fields:
            label = re.sub(r"\s+", "", str(field.get("label") or ""))
            score = cls._frontend_field_match_score(normalized_question, field)
            if not label or score <= 0:
                continue
            position = normalized_question.find(label)
            if position < 0:
                position = 10**6
            ranked.append((position, -score, -len(label), field))

        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        matched_fields: list[dict[str, Any]] = []
        seen_labels: set[str] = set()
        for _, _, _, field in ranked:
            label = str(field.get("label") or "").strip()
            if not label or label in seen_labels:
                continue
            seen_labels.add(label)
            matched_fields.append(field)
            if len(matched_fields) >= max(1, int(limit or 1)):
                break
        return matched_fields

    @staticmethod
    def _looks_like_exact_field_question(question: str) -> bool:
        text = str(question or "").strip()
        lowered = text.lower()
        if any(marker in lowered for marker in ("what is", "how many", "value", "number", "title", "file name")):
            return True
        if any(marker in text for marker in ("是什么", "是多少", "哪一年", "多少", "数值", "值", "标题", "文件名")):
            return True
        markers = ("是什么", "是多少", "哪一年", "多少", "数值", "值", "标题", "文件名")
        return any(marker in text for marker in markers)

    @staticmethod
    def _format_frontend_field_value(question: str, field: dict[str, Any]) -> str:
        value = str(field.get("value") or "").strip()
        question_text = str(question or "")
        if re.search(r"(只回答|只回|仅回答|仅返回).*?(数字|数值)", question_text):
            numeric = re.search(r"[-+]?\d+(?:\.\d+)?", value)
            if numeric:
                return numeric.group(0)
        if re.search(r"(only|just)\s+(the\s+)?(number|digits?)", question_text, flags=re.IGNORECASE):
            numeric = re.search(r"[-+]?\d+(?:\.\d+)?", value)
            if numeric:
                return numeric.group(0)
        if not value:
            return ""
        if "只回答数字" in str(question or ""):
            numeric = re.search(r"[-+]?\d+(?:\.\d+)?", value)
            if numeric:
                return numeric.group(0)
        return value

    @staticmethod
    def _format_frontend_field_answer(field: dict[str, Any]) -> str:
        label = str(field.get("label") or "").strip() or "字段"
        value = str(field.get("value") or "").strip() or "暂无可用值"
        meta_parts: list[str] = []
        page = field.get("page")
        confidence = field.get("confidence")
        if isinstance(page, int) and page > 0:
            meta_parts.append(f"第{page}页")
        if isinstance(confidence, int) and confidence > 0:
            meta_parts.append(f"置信度{confidence}%")
        meta = f"（{'，'.join(meta_parts)}）" if meta_parts else ""
        return f"{label}是 {value}{meta}。"

    @classmethod
    def _format_frontend_multi_field_answer(
        cls,
        *,
        question: str,
        file_name: str,
        summary: str,
        top_fields: list[dict[str, Any]],
        matched_fields: list[dict[str, Any]],
    ) -> str:
        if not matched_fields:
            return ""

        direct_pairs = [
            f"{str(field.get('label') or '').strip()}是{str(field.get('value') or '').strip()}"
            for field in matched_fields
            if str(field.get("label") or "").strip() and str(field.get("value") or "").strip()
        ]
        if not direct_pairs:
            return ""

        question_text = str(question or "").strip()
        if cls._should_prefer_snapshot_grounding(question_text):
            key_labels = [
                str(field.get("label") or "").strip()
                for field in top_fields[:6]
                if str(field.get("label") or "").strip()
            ]
            lines: list[str] = []
            if summary:
                lines.append(f"当前文档《{file_name or '当前文档'}》的核心内容是：{summary}")
            if key_labels:
                lines.append(f"当前样例里最关键的字段包括：{'、'.join(key_labels)}。")
            lines.append(f"你这次特别问到的字段里，{'，'.join(direct_pairs)}。")
            return "\n".join(line for line in lines if line.strip()).strip()

        return "，".join(direct_pairs) + "。"

    @staticmethod
    def _normalize_entity_key(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[\u3000`~!@#$%^&*()_\-+=\[\]{}|\\:;\"'<>,.?/，。；：、（）《》！？]+", "", text)
        return text

    @classmethod
    def _is_conditional_row_lookup_question(cls, question: str) -> bool:
        text = str(question or "").strip()
        if not text:
            return False
        lowered = text.lower()
        strict_asks_value = bool(
            re.search(
                r"(是什么|是多少|多少|数值|值|页码|行号|表格|what\s+is|value|ref_id|table|row)",
                text,
                flags=re.IGNORECASE,
            )
        )
        if not strict_asks_value:
            return False
        strict_zh_condition = bool(
            re.search(r"[\u4e00-\u9fffA-Za-z0-9_]{1,30}\s*(?:为|等于|=)\s*[^，。；;]{1,80}\s*的", text)
        )
        strict_en_condition = bool(
            re.search(r"\b(?:where|whose|with)\b", lowered)
            and re.search(r"\b(?:is|equals|=)\b", lowered)
        )
        return strict_zh_condition or strict_en_condition
        asks_value = (
            any(marker in text for marker in ("是什么", "是多少", "多少", "数值", "值", "页码", "行号", "表格"))
            or any(marker in lowered for marker in ("what is", "value", "ref_id", "table", "row"))
        )
        if not asks_value:
            return False
        chinese_condition = bool(
            re.search(r"[\u4e00-\u9fffA-Za-z0-9_]{1,30}\s*(?:为|等于|=)\s*[^，,。；;]{1,80}\s*的", text)
        )
        english_condition = (
            bool(re.search(r"\bwhere\b", lowered))
            or bool(re.search(r"\bwhose\b", lowered))
            or bool(re.search(r"\bwith\b", lowered))
        ) and bool(re.search(r"\b(?:is|equals|=)\b", lowered))
        return chinese_condition or english_condition

    @staticmethod
    def _extract_conditional_lookup_parts(question: str) -> dict[str, str]:
        text = str(question or "").strip()
        if not text:
            return {}
        zh_match = re.search(
            r"(?P<condition_field>[\u4e00-\u9fffA-Za-z0-9_.（）()]{1,40}?)\s*(?:为|等于|=)\s*"
            r"(?P<condition_value>[^，。；;]{1,80}?)\s*的\s*(?P<rest>.+)$",
            text,
        )
        if zh_match:
            condition_field = str(zh_match.group("condition_field") or "").strip()
            condition_value = str(zh_match.group("condition_value") or "").strip()
            rest = str(zh_match.group("rest") or "").strip()
            rest = re.split(r"[，。？?；;\n]", rest, maxsplit=1)[0]
            rest = re.sub(r"(?:是多少|多少|是什么|是啥|为多少)\s*$", "", rest).strip()
            if condition_field and condition_value and rest:
                return {
                    "condition_field": condition_field,
                    "condition_value": condition_value,
                    "target_field": rest,
                }
            return {}
        en_match = re.search(
            r"\bwhere\s+(?P<condition_field>[a-z0-9_ ]{1,40})\s*(?:=|is|equals)\s*"
            r"(?P<condition_value>[a-z0-9_ .-]{1,80})\b.*?\b(?:(?:what is)|(?:value of))\s+"
            r"(?P<target_field>[a-z0-9_ ]{1,40})",
            text.lower(),
        )
        if en_match:
            condition_field = str(en_match.group("condition_field") or "").strip()
            condition_value = str(en_match.group("condition_value") or "").strip()
            target_field = str(en_match.group("target_field") or "").strip()
            if condition_field and condition_value and target_field:
                return {
                    "condition_field": condition_field,
                    "condition_value": condition_value,
                    "target_field": target_field,
                }
        return {}

        zh_match = re.search(
            r"(?P<condition_field>[\u4e00-\u9fffA-Za-z0-9_.（）()]{1,40}?)\s*(?:为|等于|=)\s*"
            r"(?P<condition_value>[^，,。；;]{1,80}?)\s*的\s*(?P<rest>.+)$",
            text,
        )
        if zh_match:
            condition_field = str(zh_match.group("condition_field") or "").strip()
            condition_value = str(zh_match.group("condition_value") or "").strip()
            rest = str(zh_match.group("rest") or "").strip()
            rest = re.split(r"[？?。!！,，;；\n]", rest, maxsplit=1)[0]
            rest = re.sub(r"(?:是多少|多少|是什么|是啥|为多少)\s*$", "", rest).strip()
            if condition_field and condition_value and rest:
                return {
                    "condition_field": condition_field,
                    "condition_value": condition_value,
                    "target_field": rest,
                }

        en_match = re.search(
            r"\bwhere\s+(?P<condition_field>[a-z0-9_ ]{1,40})\s*(?:=|is|equals)\s*"
            r"(?P<condition_value>[a-z0-9_ .-]{1,80})\b.*?\b(?:(?:what is)|(?:value of))\s+"
            r"(?P<target_field>[a-z0-9_ ]{1,40})",
            text.lower(),
        )
        if en_match:
            condition_field = str(en_match.group("condition_field") or "").strip()
            condition_value = str(en_match.group("condition_value") or "").strip()
            target_field = str(en_match.group("target_field") or "").strip()
            if condition_field and condition_value and target_field:
                return {
                    "condition_field": condition_field,
                    "condition_value": condition_value,
                    "target_field": target_field,
                }
        return {}

    @classmethod
    def _match_frontend_header_index(cls, headers: list[str], target: str) -> int:
        target_key = cls._normalize_entity_key(target)
        if not target_key:
            return -1
        best_score = -1
        best_index = -1
        for index, header in enumerate(headers):
            header_key = cls._normalize_entity_key(header)
            if not header_key:
                continue
            score = 0
            if header_key == target_key:
                score = 100
            elif target_key in header_key:
                score = 80
            elif header_key in target_key:
                score = 70
            if score > best_score:
                best_score = score
                best_index = index
        return best_index if best_score > 0 else -1

    @classmethod
    def _build_frontend_conditional_lookup_answer(
        cls,
        *,
        question: str,
        table_row_samples: Any,
    ) -> str:
        if not cls._is_conditional_row_lookup_question(question):
            return ""
        parts = cls._extract_conditional_lookup_parts(question)
        if not parts:
            return ""
        if not isinstance(table_row_samples, list) or len(table_row_samples) == 0:
            return (
                f"当前快照未包含可核验的行级表格证据，无法确认“{parts['condition_field']}={parts['condition_value']}”对应的"
                f"{parts['target_field']}。请先提供可定位到页码/行号/ref_id 的表格证据。"
            )

        condition_field = parts["condition_field"]
        condition_value = parts["condition_value"]
        target_field = parts["target_field"]
        condition_value_key = cls._normalize_entity_key(condition_value)
        if not condition_value_key:
            return ""

        matches: list[dict[str, Any]] = []
        for sample in table_row_samples[:6]:
            if not isinstance(sample, dict):
                continue
            headers = [str(item or "").strip() for item in sample.get("headers", []) if str(item or "").strip()]
            if not headers:
                continue
            condition_col_index = cls._match_frontend_header_index(headers, condition_field)
            target_col_index = cls._match_frontend_header_index(headers, target_field)
            if condition_col_index < 0 or target_col_index < 0:
                continue
            rows_raw = sample.get("rows")
            if not isinstance(rows_raw, list):
                continue
            for row_pos, row_item in enumerate(rows_raw[:80], start=1):
                row_cells: list[str] = []
                row_index = row_pos
                if isinstance(row_item, dict):
                    cells_value = row_item.get("cells")
                    if isinstance(cells_value, list):
                        row_cells = [str(cell or "").strip() for cell in cells_value]
                    row_index_raw = row_item.get("row_index")
                    if isinstance(row_index_raw, (int, float)):
                        row_index = max(1, int(row_index_raw))
                elif isinstance(row_item, list):
                    row_cells = [str(cell or "").strip() for cell in row_item]
                if not row_cells:
                    continue
                condition_cell = row_cells[condition_col_index] if condition_col_index < len(row_cells) else ""
                condition_cell_key = cls._normalize_entity_key(condition_cell)
                if not condition_cell_key:
                    continue
                if condition_value_key not in condition_cell_key and condition_cell_key not in condition_value_key:
                    continue
                target_value = row_cells[target_col_index] if target_col_index < len(row_cells) else ""
                matches.append(
                    {
                        "target_value": str(target_value or "").strip(),
                        "table_id": str(sample.get("table_id") or "").strip(),
                        "ref_id": str(sample.get("ref_id") or "").strip(),
                        "page": sample.get("page"),
                        "row_index": row_index,
                    }
                )

        if not matches:
            return (
                f"在当前可见表格证据中未找到“{condition_field}={condition_value}”的记录，"
                f"暂时无法给出 {target_field}。请补充可定位到页码/行号/ref_id 的证据。"
            )

        if len(matches) > 1:
            preview_items = []
            for item in matches[:3]:
                preview_items.append(
                    f"page={item.get('page')}, row_index={item.get('row_index')}, ref_id={item.get('ref_id') or 'N/A'}"
                )
            return (
                f"命中结果不唯一：当前找到 {len(matches)} 条“{condition_field}={condition_value}”记录，"
                f"无法唯一确定 {target_field}。候选证据：{'; '.join(preview_items)}。"
            )

        match = matches[0]
        target_value = str(match.get("target_value") or "").strip()
        if not target_value:
            return (
                f"已定位到“{condition_field}={condition_value}”对应行，但 {target_field} 为空值。"
                f"证据：page={match.get('page')}, row_index={match.get('row_index')}, ref_id={match.get('ref_id') or 'N/A'}。"
            )

        return (
            f"{target_field}={target_value}。"
            f"证据：table_id={match.get('table_id') or 'N/A'}, page={match.get('page')}, "
            f"row_index={match.get('row_index')}, ref_id={match.get('ref_id') or 'N/A'}。"
        )

    def _build_stream_evidence_items(self, bundle: Assistant1ContextBundle, *, top_k: int) -> list[dict[str, Any]]:
        if bundle.evidence_items:
            return [dict(item) for item in bundle.evidence_items[:top_k]]
        if not bundle.source_excerpt:
            return []
        return [
            {
                "kind": "source_excerpt",
                "title": bundle.file_name or "source_excerpt",
                "snippet": bundle.source_excerpt,
                "ref_id": "",
                "unit_id": bundle.file_hash,
                "unit_type": "source_excerpt",
            }
        ]

    async def _stream_provider_text_async(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
    ) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        def _worker() -> None:
            try:
                for item in self.provider.stream_text(messages=messages, instructions=instructions):
                    asyncio.run_coroutine_threadsafe(queue.put(("chunk", item)), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(("error", exc)), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)

        threading.Thread(target=_worker, daemon=True).start()
        while True:
            kind, payload = await queue.get()
            if kind == "chunk":
                yield str(payload or "")
                continue
            if kind == "error":
                if isinstance(payload, Exception):
                    raise payload
                raise RuntimeError(str(payload or "assistant1 stream failed"))
            break

    async def _recover_full_text(
        self,
        *,
        messages: list[dict[str, Any]],
        instructions: str,
        plan: _ProviderPlan,
    ) -> str:
        try:
            text = await asyncio.to_thread(
                self.provider.complete_text,
                messages=messages,
                instructions=instructions,
                max_output_tokens=plan.max_output_tokens,
                reasoning_effort=plan.reasoning_effort,
                text_verbosity=plan.text_verbosity,
            )
        except Exception:
            return ""
        return str(text or "").strip()

    def _finalize_answer(self, text: str, bundle: Assistant1ContextBundle) -> str:
        cleaned = str(text or "").strip()
        if cleaned:
            return cleaned
        if bundle.result_fields:
            fields = [f"{item.get('field_name')}: {item.get('value')}" for item in bundle.result_fields[:3]]
            return f"我已定位到当前文件的抽取结果：{'；'.join(fields)}。如果你愿意，我可以继续解释对应证据。"
        if bundle.source_excerpt:
            return "我已找到当前文件的相关原文片段，但这轮还没有生成稳定答案。你可以继续追问具体字段或结论。"
        return "这轮还没有拿到足够稳定的最终答案。你可以继续追问，我会接着帮你整理。"


class Assistant1Facade:
    def __init__(
        self,
        extraction_settings: ExtractionSettings | None = None,
        *,
        legacy_runtime_factory: Any | None = None,
        native_runtime: NativeAssistant1Runtime | None = None,
        upstream_runtime: Assistant1UpstreamRuntime | None = None,
    ) -> None:
        self.extraction_settings = extraction_settings or get_extraction_settings()
        self.legacy_runtime_factory = legacy_runtime_factory or get_legacy_assistant1_runtime
        self.native_runtime = native_runtime or NativeAssistant1Runtime(self.extraction_settings)
        self.upstream_runtime = upstream_runtime or Assistant1UpstreamRuntime()

    def build_stream_response(
        self,
        settings: Settings,
        *,
        request: Request,
        payload: Any,
        additional_headers: dict[str, str] | None = None,
    ) -> Any:
        requested_mode = self.extraction_settings.assistant1_mode
        if requested_mode == "upstream":
            return self.upstream_runtime.build_stream_response(
                settings,
                request=request,
                payload=payload,
                additional_headers=additional_headers,
            )
        return StreamingResponse(
            self.stream_chat(settings, payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    def stream_chat(self, settings: Settings, payload: Any) -> AsyncIterator[bytes]:
        requested_mode = self.extraction_settings.assistant1_mode
        if requested_mode == "upstream":
            raise RuntimeError("assistant1 upstream mode must be served via build_stream_response()")
        if requested_mode == "native":
            return self._stream_native_with_optional_fallback(settings, payload)
        return self._legacy_stream(payload)

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        requested_mode = self.extraction_settings.assistant1_mode
        fallback_to_legacy = self.extraction_settings.assistant1_fallback_to_legacy
        legacy_payload = self._legacy_health_payload()
        native_payload = self.native_runtime.health_payload(settings)
        upstream_payload = self.upstream_runtime.health_payload(settings)

        active_mode = requested_mode
        fallback_active = False
        if requested_mode == "native" and not bool(native_payload.get("runtime_ready")) and fallback_to_legacy:
            if bool(legacy_payload.get("ok")):
                active_mode = "legacy"
                fallback_active = True

        if active_mode == "upstream":
            active_payload = upstream_payload
        elif active_mode == "native":
            active_payload = native_payload
        else:
            active_payload = legacy_payload
        return {
            "ok": bool(active_payload.get("ok")),
            "requested_mode": requested_mode,
            "active_mode": active_mode,
            "fallback_to_legacy": fallback_to_legacy,
            "fallback_active": fallback_active,
            "configured": bool(active_payload.get("configured")),
            "model": str(active_payload.get("model") or ""),
            "base_url": str(active_payload.get("base_url") or ""),
            "endpoint_path": str(active_payload.get("endpoint_path") or ""),
            "tavily_configured": bool(active_payload.get("tavily_configured")),
            "legacy": legacy_payload,
            "native": native_payload,
            "upstream": upstream_payload,
        }

    async def _stream_native_with_optional_fallback(self, settings: Settings, payload: Any) -> AsyncIterator[bytes]:
        native_payload = self.native_runtime.health_payload(settings)
        if not bool(native_payload.get("runtime_ready")) and self.extraction_settings.assistant1_fallback_to_legacy:
            legacy_payload = self._legacy_health_payload()
            if bool(legacy_payload.get("ok")):
                async for chunk in self._legacy_stream(payload):
                    yield chunk
                return

        request_readiness = getattr(self.native_runtime, "request_readiness_payload", None)
        if callable(request_readiness):
            readiness_payload = request_readiness(settings, file_hash=payload.file_hash)
            if (
                bool(readiness_payload.get("fallback_recommended"))
                and self.extraction_settings.assistant1_fallback_to_legacy
            ):
                legacy_payload = self._legacy_health_payload()
                if bool(legacy_payload.get("ok")):
                    async for chunk in self._legacy_stream(payload):
                        yield chunk
                    return

        emitted_any = False
        try:
            async for chunk in self.native_runtime.stream_chat(
                settings=settings,
                user_message=payload.message,
                file_hash=payload.file_hash,
                history=[item.model_dump(mode="json") for item in payload.history],
                max_steps=payload.max_steps,
                top_k=payload.top_k,
                session_id=payload.session_id or "",
                debug=payload.debug,
                client_supports_replace=bool(payload.client_caps.supports_replace),
                extra_context=payload.extra_context,
            ):
                emitted_any = True
                yield chunk
            return
        except Exception:
            if not self.extraction_settings.assistant1_fallback_to_legacy or emitted_any:
                raise

        async for chunk in self._legacy_stream(payload):
            yield chunk

    async def _legacy_stream(self, payload: Any) -> AsyncIterator[bytes]:
        runtime = self.legacy_runtime_factory()
        history = [item.model_dump(mode="json") for item in payload.history]
        async for chunk in runtime.stream_chat(
            user_message=payload.message,
            file_hash=payload.file_hash,
            history=history,
            max_steps=payload.max_steps,
            top_k=payload.top_k,
            session_id=payload.session_id or "",
            debug=payload.debug,
            client_supports_replace=bool(payload.client_caps.supports_replace),
            extra_context=payload.extra_context,
        ):
            yield chunk

    def _legacy_health_payload(self) -> dict[str, Any]:
        try:
            runtime = self.legacy_runtime_factory()
            provider = getattr(runtime, "provider", None)
            tavily_client = getattr(runtime, "tavily", None)
            return {
                "ok": True,
                "configured": bool(getattr(provider, "configured", False)),
                "model": str(getattr(provider, "model", "") or ""),
                "base_url": str(getattr(provider, "base_url", "") or ""),
                "endpoint_path": str(getattr(provider, "endpoint_path", "") or ""),
                "tavily_configured": bool(getattr(getattr(tavily_client, "settings", None), "tavily_api_key", "")),
            }
        except Exception as exc:
            return {
                "ok": False,
                "configured": False,
                "model": "",
                "base_url": "",
                "endpoint_path": "",
                "tavily_configured": False,
                "error": f"{type(exc).__name__}: {exc}",
            }


@lru_cache(maxsize=1)
def get_assistant1_facade() -> Assistant1Facade:
    return Assistant1Facade()


__all__ = [
    "Assistant1Facade",
    "Assistant1ContextBundle",
    "ExtractionAssistant1Provider",
    "NativeAssistant1Runtime",
    "build_assistant1_context_bundle",
    "get_assistant1_facade",
    "get_legacy_assistant1_runtime",
    "has_grounded_context",
]
