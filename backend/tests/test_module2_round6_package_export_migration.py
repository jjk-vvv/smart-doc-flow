from __future__ import annotations

from importlib import import_module


def test_module2_runtime_package_exports_round6_are_static_and_cycle_safe() -> None:
    runtime_module = import_module("app.modules.module2.runtime")

    assert "__getattr__" not in runtime_module.__dict__
    assert callable(runtime_module.build_module2_main_extraction_bundle)
    assert callable(runtime_module.build_module2_main_document_io_bundle)
    assert callable(runtime_module.build_module2_main_geometry_bundle)
    assert callable(runtime_module.build_module2_main_workflow_bundle)

    assert not hasattr(runtime_module, "build_module2_main_foundation_bundle")
    assert not hasattr(runtime_module, "build_module2_main_entry_bundle")
    assert not hasattr(runtime_module, "build_module2_main_service_bundle")
    assert not hasattr(runtime_module, "build_module2_main_support_bundle")
    assert not hasattr(runtime_module, "build_module2_main_schema_pipeline_bundle")


def test_module2_bootstrap_package_exports_are_static_without_dynamic_getattr() -> None:
    bootstrap_module = import_module("app.modules.module2.bootstrap")
    assert callable(bootstrap_module.build_module2_main_foundation_bundle)
    assert callable(bootstrap_module.build_module2_main_schema_pipeline_bundle)
    assert callable(bootstrap_module.build_module2_main_service_bundle)
    assert callable(bootstrap_module.build_module2_main_support_bundle)
