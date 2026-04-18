from __future__ import annotations

import inspect
from importlib import import_module


def test_round11_repository_bundle_builder_no_longer_accepts_storage_compat_param() -> None:
    repository_module = import_module("app.modules.module2.repositories.bundle")
    params = inspect.signature(repository_module.build_module2_repository_bundle).parameters

    assert "legacy_kwargs" not in params
    assert "storage" in params
    assert "legacy_storage" not in params


def test_round11_repository_wrappers_no_longer_accept_storage_keyword_compat() -> None:
    runtime_state_repo = import_module("app.modules.module2.repositories.runtime_state_repository")
    extraction_cache_repo = import_module("app.modules.module2.repositories.extraction_cache_repository")
    outbox_repo = import_module("app.modules.module2.repositories.module4_sync_outbox_repository")
    assistant_repo = import_module("app.modules.module2.repositories.assistant_session_repository")

    runtime_params = inspect.signature(runtime_state_repo.RuntimeStateRepository).parameters
    cache_params = inspect.signature(extraction_cache_repo.ExtractionCacheRepository).parameters
    outbox_params = inspect.signature(outbox_repo.Module4SyncOutboxRepository).parameters
    assistant_params = inspect.signature(assistant_repo.AssistantSessionRepository).parameters

    assert "legacy_kwargs" not in runtime_params
    assert "legacy_kwargs" not in cache_params
    assert "legacy_kwargs" not in outbox_params
    assert "legacy_kwargs" not in assistant_params

    assert "storage" in runtime_params
    assert "storage" in cache_params
    assert "storage" in outbox_params
    assert "storage" in assistant_params

    assert "legacy_storage" not in runtime_params
    assert "legacy_storage" not in cache_params
    assert "legacy_storage" not in outbox_params
    assert "legacy_storage" not in assistant_params
