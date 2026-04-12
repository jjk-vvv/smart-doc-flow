from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional


class ExtractionCacheRepository:
    """Repository wrapper for extraction cache persistence/query operations."""

    def __init__(self, *, legacy_storage: Any | None = None, **legacy_kwargs: Any) -> None:
        if "storage" in legacy_kwargs:
            if legacy_storage is not None:
                raise TypeError("Pass only one of legacy_storage=... or storage=...")
            legacy_storage = legacy_kwargs.pop("storage")
            warnings.warn(
                "ExtractionCacheRepository(storage=...) is deprecated; "
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
            "ExtractionCacheRepository.storage is deprecated; "
            "use ExtractionCacheRepository.legacy_storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._legacy_storage

    async def check_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        return await self._legacy_storage.check_cache(cache_key)

    async def find_recent_document_caches(self, file_hash: str, *, limit: int = 8) -> List[Dict[str, Any]]:
        return await self._legacy_storage.find_recent_document_caches(file_hash, limit=limit)

    async def save_extraction_result(self, cache_key: str, payload: Dict[str, Any]) -> None:
        await self._legacy_storage.save_extraction_result(cache_key, payload)
