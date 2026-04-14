from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional


class AssistantSessionRepository:
    """Repository wrapper for assistant session/message/tool persistence operations."""

    def __init__(self, *, legacy_storage: Any | None = None, **legacy_kwargs: Any) -> None:
        if "storage" in legacy_kwargs:
            if legacy_storage is not None:
                raise TypeError("Pass only one of legacy_storage=... or storage=...")
            legacy_storage = legacy_kwargs.pop("storage")
            warnings.warn(
                "AssistantSessionRepository(storage=...) is deprecated; "
                "pass legacy_storage=... instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected keyword argument(s): {unexpected}")
        if legacy_storage is None:
            raise ValueError("legacy_storage is required")
        self._legacy_storage = legacy_storage

    @property
    def legacy_storage(self) -> Any:
        return self._legacy_storage

    @property
    def storage(self) -> Any:
        warnings.warn(
            "AssistantSessionRepository.storage is deprecated; "
            "use AssistantSessionRepository.legacy_storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._legacy_storage

    async def fetch_assistant_session(
        self,
        session_id: str,
        *,
        expected_tenant_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        return await self._legacy_storage.fetch_assistant_session(
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
        await self._legacy_storage.upsert_assistant_session(
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
        return await self._legacy_storage.list_assistant_messages(
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
        await self._legacy_storage.save_assistant_message(
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
        await self._legacy_storage.save_tool_invocation(
            session_id=session_id,
            message_id=message_id,
            tool_name=tool_name,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            latency_ms=latency_ms,
            tenant_id=tenant_id,
        )
