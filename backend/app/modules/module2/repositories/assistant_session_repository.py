from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional


class AssistantSessionRepository:
    """Repository wrapper for assistant session/message/tool persistence operations."""

    def __init__(self, *, storage: Any | None = None) -> None:
        if storage is None:
            raise ValueError("storage is required")
        self._storage = storage

    @property
    def legacy_storage(self) -> Any:
        warnings.warn(
            "AssistantSessionRepository.legacy_storage is deprecated; use AssistantSessionRepository.storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._storage

    @property
    def storage(self) -> Any:
        return self._storage

    async def fetch_assistant_session(
        self,
        session_id: str,
        *,
        expected_tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        return await self._storage.fetch_assistant_session(
            session_id,
            expected_tenant_id=expected_tenant_id,
        )

    async def upsert_assistant_session(
        self,
        *,
        session_id: str,
        file_hash: str,
        file_name: str,
        summary_text: str,
        current_object_lock: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: str = "",
    ) -> None:
        await self._storage.upsert_assistant_session(
            session_id=session_id,
            file_hash=file_hash,
            file_name=file_name,
            summary_text=summary_text,
            current_object_lock=current_object_lock,
            metadata=metadata,
            tenant_id=tenant_id,
        )

    async def list_assistant_messages(
        self,
        session_id: str,
        limit: int = 40,
        *,
        expected_tenant_id: str = "",
    ) -> List[Dict[str, Any]]:
        return await self._storage.list_assistant_messages(
            session_id,
            limit=limit,
            expected_tenant_id=expected_tenant_id,
        )

    async def save_assistant_message(
        self,
        *,
        session_id: str,
        message_id: str,
        role: str,
        message_type: str,
        content: str,
        payload: Optional[Dict[str, Any]] = None,
        tenant_id: str = "",
    ) -> None:
        await self._storage.save_assistant_message(
            session_id=session_id,
            message_id=message_id,
            role=role,
            message_type=message_type,
            content=content,
            payload=payload,
            tenant_id=tenant_id,
        )

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
        tenant_id: str = "",
    ) -> None:
        await self._storage.save_tool_invocation(
            session_id=session_id,
            message_id=message_id,
            tool_name=tool_name,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            latency_ms=latency_ms,
            tenant_id=tenant_id,
        )
