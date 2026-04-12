from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

from .assistant_session_repository import AssistantSessionRepository
from .extraction_cache_repository import ExtractionCacheRepository
from .module4_sync_outbox_repository import Module4SyncOutboxRepository
from .runtime_state_repository import RuntimeStateRepository


@dataclass(frozen=True)
class Module2RepositoryBundle:
    legacy_storage: Any
    runtime_state_repository: RuntimeStateRepository
    extraction_cache_repository: ExtractionCacheRepository
    module4_sync_outbox_repository: Module4SyncOutboxRepository
    assistant_session_repository: AssistantSessionRepository

    @property
    def storage(self) -> Any:
        warnings.warn(
            "Module2RepositoryBundle.storage is deprecated; "
            "use Module2RepositoryBundle.legacy_storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.legacy_storage


def build_module2_repository_bundle(legacy_storage: Any | None = None, **legacy_kwargs: Any) -> Module2RepositoryBundle:
    if "storage" in legacy_kwargs:
        if legacy_storage is not None:
            raise TypeError("Pass only one of legacy_storage=... or storage=...")
        legacy_storage = legacy_kwargs.pop("storage")
        warnings.warn(
            "build_module2_repository_bundle(storage=...) is deprecated; "
            "pass legacy_storage=... instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    if legacy_kwargs:
        unexpected = ", ".join(sorted(legacy_kwargs))
        raise TypeError(f"Unexpected keyword argument(s): {unexpected}")
    if legacy_storage is None:
        raise ValueError("legacy_storage is required")

    return Module2RepositoryBundle(
        legacy_storage=legacy_storage,
        runtime_state_repository=RuntimeStateRepository(legacy_storage=legacy_storage),
        extraction_cache_repository=ExtractionCacheRepository(legacy_storage=legacy_storage),
        module4_sync_outbox_repository=Module4SyncOutboxRepository(legacy_storage=legacy_storage),
        assistant_session_repository=AssistantSessionRepository(legacy_storage=legacy_storage),
    )
