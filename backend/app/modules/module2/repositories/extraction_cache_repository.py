from __future__ import annotations

import inspect
import warnings
from typing import Any, Dict, List, Optional


class ExtractionCacheRepository:
    """Repository wrapper for extraction cache persistence/query operations."""

    def __init__(self, *, storage: Any | None = None) -> None:
        if storage is None:
            raise ValueError("storage is required")
        self._storage = storage

    @property
    def legacy_storage(self) -> Any:
        warnings.warn(
            "ExtractionCacheRepository.legacy_storage is deprecated; use ExtractionCacheRepository.storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._storage

    @property
    def storage(self) -> Any:
        return self._storage

    async def check_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        return await self._storage.check_cache(cache_key)

    async def find_recent_document_caches(
        self,
        file_hash: str,
        *,
        limit: int = 8,
        tenant_id: str = "",
    ) -> List[Dict[str, Any]]:
        method = self._storage.find_recent_document_caches
        try:
            parameters = inspect.signature(method).parameters
        except (TypeError, ValueError):
            parameters = {}

        if "tenant_id" in parameters:
            return await method(file_hash, limit=limit, tenant_id=tenant_id)
        return await method(file_hash, limit=limit)

    async def save_extraction_result(self, cache_key: str, payload: Dict[str, Any]) -> None:
        await self._storage.save_extraction_result(cache_key, payload)
