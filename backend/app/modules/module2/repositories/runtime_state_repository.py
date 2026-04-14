from __future__ import annotations

import inspect
import warnings
from typing import Any, Dict


class RuntimeStateRepository:
    """Repository wrapper for runtime lifecycle and diagnostics storage operations."""

    def __init__(self, *, legacy_storage: Any | None = None, **legacy_kwargs: Any) -> None:
        if "storage" in legacy_kwargs:
            if legacy_storage is not None:
                raise TypeError("Pass only one of legacy_storage=... or storage=...")
            legacy_storage = legacy_kwargs.pop("storage")
            warnings.warn(
                "RuntimeStateRepository(storage=...) is deprecated; "
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
            "RuntimeStateRepository.storage is deprecated; "
            "use RuntimeStateRepository.legacy_storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._legacy_storage

    async def connect(self) -> None:
        await self._legacy_storage.connect()

    async def close(self) -> None:
        await self._legacy_storage.close()

    async def clear_runtime_cache(self, tenant_id: str = "") -> Dict[str, int]:
        clear_runtime_cache_params = inspect.signature(self._legacy_storage.clear_runtime_cache).parameters
        if "tenant_id" in clear_runtime_cache_params:
            return await self._legacy_storage.clear_runtime_cache(tenant_id=tenant_id)
        return await self._legacy_storage.clear_runtime_cache()

    def diagnostics(self) -> Dict[str, Any]:
        return dict(self._legacy_storage.diagnostics() or {})
