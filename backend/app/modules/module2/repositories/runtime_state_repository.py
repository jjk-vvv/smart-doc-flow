from __future__ import annotations

import inspect
import warnings
from typing import Any, Dict


class RuntimeStateRepository:
    """Repository wrapper for runtime lifecycle and diagnostics storage operations."""

    def __init__(self, *, storage: Any | None = None) -> None:
        if storage is None:
            raise ValueError("storage is required")
        self._storage = storage

    @property
    def legacy_storage(self) -> Any:
        warnings.warn(
            "RuntimeStateRepository.legacy_storage is deprecated; use RuntimeStateRepository.storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._storage

    @property
    def storage(self) -> Any:
        return self._storage

    async def connect(self) -> None:
        await self._storage.connect()

    async def close(self) -> None:
        await self._storage.close()

    async def clear_runtime_cache(self, tenant_id: str = "") -> Dict[str, int]:
        clear_runtime_cache_params = inspect.signature(self._storage.clear_runtime_cache).parameters
        if "tenant_id" in clear_runtime_cache_params:
            return await self._storage.clear_runtime_cache(tenant_id=tenant_id)
        return await self._storage.clear_runtime_cache()

    def diagnostics(self) -> Dict[str, Any]:
        return dict(self._storage.diagnostics() or {})
