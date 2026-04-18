from __future__ import annotations

import inspect
from importlib import import_module


def test_round10_module2_runtime_package_has_no_dynamic_getattr_and_no_removed_lazy_exports() -> None:
    runtime_module = import_module("app.modules.module2.runtime")

    assert "__getattr__" not in runtime_module.__dict__
    assert not hasattr(runtime_module, "build_module2_main_foundation_bundle")
    assert not hasattr(runtime_module, "build_module2_main_entry_bundle")
    assert not hasattr(runtime_module, "build_module2_main_service_bundle")
    assert not hasattr(runtime_module, "build_module2_main_support_bundle")
    assert not hasattr(runtime_module, "build_module2_main_schema_pipeline_bundle")


def test_round10_module2_module4_sync_config_default_guard_mode_is_strict() -> None:
    runtime_module = import_module("app.modules.module2.core.integration.module4_sync_config_runtime")
    runtime = runtime_module.Module4SyncConfigRuntime(env_get=lambda key, default="": default)

    assert runtime.tenant_guard_mode() == "authenticated_required"


def test_round10_module4_runtime_default_guard_mode_is_strict(monkeypatch) -> None:
    runtime_module = import_module("app.modules.module4.core.app_runtime")
    monkeypatch.delenv("MODULE4_TENANT_GUARD_MODE", raising=False)

    assert runtime_module.module4_tenant_guard_mode() == "authenticated_required"


def test_round10_removed_compat_parameters_are_not_in_public_signatures() -> None:
    service_builder = import_module("app.modules.module2.services.extraction.service_builder")
    entry_builder = import_module("app.modules.module2.services.extraction.entry_builder")
    app_callback_bundle = import_module("app.modules.module2.composition.app_callback_bundle")
    sync_callback_bundle = import_module("app.modules.module2.runtime.sync_callback_bundle")
    outbox_runtime = import_module("app.modules.module2.core.integration.module4_sync_outbox_runtime")

    service_params = inspect.signature(service_builder.build_module2_main_service_bundle).parameters
    entry_params = inspect.signature(entry_builder.build_module2_main_entry_bundle).parameters
    callback_params = inspect.signature(app_callback_bundle.build_module2_app_callback_bundle).parameters
    sync_params = inspect.signature(sync_callback_bundle.build_sync_callback_bundle).parameters
    outbox_params = inspect.signature(outbox_runtime.Module4SyncOutboxRuntime).parameters

    assert "legacy_storage" not in service_params
    assert "legacy_storage" not in entry_params
    assert "legacy_storage" not in callback_params
    assert "legacy_storage" not in sync_params
    assert "legacy_storage" not in outbox_params
    assert "storage" not in outbox_params
