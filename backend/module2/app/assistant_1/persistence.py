from __future__ import annotations

import inspect
import logging
import time
import uuid
from typing import Any, Dict, Optional


class Assistant1PersistenceAdapter:
    """Best-effort persistence bridge for assistant stream runtime."""

    def __init__(
        self,
        storage: Any | None = None,
        *,
        repository: Any | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if storage is not None and repository is not None:
            raise TypeError("Pass only one of storage=... or repository=...")
        self._storage = repository if repository is not None else storage
        self._logger = logger or logging.getLogger(__name__)

    @property
    def enabled(self) -> bool:
        return self._storage is not None

    def _resolve_method(self, name: str) -> Any | None:
        if self._storage is None:
            return None
        method = getattr(self._storage, str(name or "").strip(), None)
        return method if callable(method) else None

    async def _invoke(self, method_name: str, **kwargs: Any) -> bool:
        method = self._resolve_method(method_name)
        if method is None:
            return False
        try:
            out = method(**kwargs)
            if inspect.isawaitable(out):
                await out
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning(
                "assistant_1 persistence call failed: method=%s error=%s",
                method_name,
                exc,
            )
            return False

    @staticmethod
    def _new_message_id(prefix: str) -> str:
        return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:10]}"

    async def upsert_session(
        self,
        *,
        session_id: str,
        file_hash: str = "",
        file_name: str = "",
        summary_text: str = "",
        current_object_lock: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return False
        return await self._invoke(
            "upsert_assistant_session",
            session_id=normalized_session_id,
            file_hash=str(file_hash or "").strip(),
            file_name=str(file_name or "").strip(),
            summary_text=str(summary_text or ""),
            current_object_lock=dict(current_object_lock or {}),
            metadata=dict(metadata or {}),
        )

    async def fetch_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return None
        method = self._resolve_method("fetch_assistant_session")
        if method is None:
            return None
        try:
            out = method(normalized_session_id)
            if inspect.isawaitable(out):
                out = await out
            return dict(out) if isinstance(out, dict) else None
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning(
                "assistant_1 persistence fetch_session failed: session_id=%s error=%s",
                normalized_session_id,
                exc,
            )
            return None

    async def list_messages(self, session_id: str, *, limit: int = 40) -> list[Dict[str, Any]]:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return []
        method = self._resolve_method("list_assistant_messages")
        if method is None:
            return []
        try:
            out = method(normalized_session_id, limit=max(1, int(limit or 40)))
            if inspect.isawaitable(out):
                out = await out
            if not isinstance(out, list):
                return []
            return [dict(item) for item in out if isinstance(item, dict)]
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.warning(
                "assistant_1 persistence list_messages failed: session_id=%s error=%s",
                normalized_session_id,
                exc,
            )
            return []

    async def save_message(
        self,
        *,
        session_id: str,
        role: str,
        message_type: str,
        content: str,
        payload: Optional[Dict[str, Any]] = None,
        message_id: str = "",
    ) -> str:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return ""
        normalized_message_id = str(message_id or "").strip() or self._new_message_id(str(role or "msg").strip() or "msg")
        await self._invoke(
            "save_assistant_message",
            session_id=normalized_session_id,
            message_id=normalized_message_id,
            role=str(role or "assistant").strip() or "assistant",
            message_type=str(message_type or "assistant_text").strip() or "assistant_text",
            content=str(content or ""),
            payload=dict(payload or {}),
        )
        return normalized_message_id

    async def save_tool_invocation(
        self,
        *,
        session_id: str,
        message_id: str,
        tool_name: str,
        status: str,
        input_summary: Optional[Dict[str, Any]] = None,
        output_summary: Optional[Dict[str, Any]] = None,
        latency_ms: int = 0,
    ) -> bool:
        normalized_session_id = str(session_id or "").strip()
        normalized_tool_name = str(tool_name or "").strip()
        if not normalized_session_id or not normalized_tool_name:
            return False
        return await self._invoke(
            "save_tool_invocation",
            session_id=normalized_session_id,
            message_id=str(message_id or "").strip(),
            tool_name=normalized_tool_name,
            status=str(status or "").strip() or "done",
            input_summary=dict(input_summary or {}),
            output_summary=dict(output_summary or {}),
            latency_ms=max(0, int(latency_ms or 0)),
        )
