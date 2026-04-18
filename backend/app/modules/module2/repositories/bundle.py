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
    storage: Any
    runtime_state_repository: RuntimeStateRepository
    extraction_cache_repository: ExtractionCacheRepository
    module4_sync_outbox_repository: Module4SyncOutboxRepository
    assistant_session_repository: AssistantSessionRepository

    @property
    def legacy_storage(self) -> Any:
        warnings.warn(
            "Module2RepositoryBundle.legacy_storage is deprecated; use Module2RepositoryBundle.storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.storage


def build_module2_repository_bundle(storage: Any | None = None) -> Module2RepositoryBundle:
    if storage is None:
        raise ValueError("storage is required")

    return Module2RepositoryBundle(
        storage=storage,
        runtime_state_repository=RuntimeStateRepository(storage=storage),
        extraction_cache_repository=ExtractionCacheRepository(storage=storage),
        module4_sync_outbox_repository=Module4SyncOutboxRepository(storage=storage),
        assistant_session_repository=AssistantSessionRepository(storage=storage),
    )
