from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import APIRouter


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))


def _sync_kwargs() -> dict:
    async def _list_outbox_rows(**kwargs):  # noqa: ARG001
        return []

    async def _get_outbox_row(outbox_id: str):  # noqa: ARG001
        return None

    return {
        "list_outbox_rows": _list_outbox_rows,
        "get_outbox_row": _get_outbox_row,
        "build_list_response": lambda rows, **kwargs: {"rows": rows},  # noqa: ARG005
        "serialize_outbox_row": lambda row, **kwargs: {"row": row},  # noqa: ARG005
        "metrics_snapshot": lambda: {},
    }


def _support_kwargs() -> dict:
    async def _clear_cache_request(scope: str):  # noqa: ARG001
        return {"ok": True}

    return {
        "office_preview_request_runtime": object(),
        "document_tools_runtime": object(),
        "clear_cache_request": _clear_cache_request,
        "serve_layout_preview": lambda artifact_name, method: object(),  # noqa: ARG005
        "serve_artifact": lambda artifact_path, method: object(),  # noqa: ARG005
        "build_health_payload": lambda: {"status": "ok"},
    }


def test_module2_route_modules_are_thin_shims() -> None:
    shim_expectations = [
        ("app.routes.extraction_request_router", "build_extraction_request_router", "app.api.compat.extraction_request_router"),
        ("app.routes.extraction_support_router", "build_extraction_support_router", "app.api.compat.extraction_support_router"),
        (
            "app.routes.extraction_assistant_router",
            "build_extraction_assistant_router",
            "app.api.compat.extraction_assistant_router",
        ),
        ("app.routes.sync_router", "build_sync_router", "app.api.compat.sync_router"),
        ("app.routes.sync_router", "build_module4_sync_router", "app.api.compat.sync_router"),
        ("app.routes.module4_sync_router", "build_module4_sync_router", "app.api.compat.module4_sync_router"),
    ]

    for shim_module_name, attr_name, compat_module_name in shim_expectations:
        shim_module = import_module(shim_module_name)
        compat_module = import_module(compat_module_name)
        assert getattr(shim_module, attr_name) is getattr(compat_module, attr_name)


def test_module2_route_compat_builders_emit_deprecation_warning() -> None:
    extraction_request_module = import_module("app.api.compat.extraction_request_router")
    with pytest.warns(DeprecationWarning):
        extraction_request_router = extraction_request_module.build_extraction_request_router(extraction_request_runtime=object())
    assert isinstance(extraction_request_router, APIRouter)

    extraction_support_module = import_module("app.api.compat.extraction_support_router")
    with pytest.warns(DeprecationWarning):
        extraction_support_router = extraction_support_module.build_extraction_support_router(**_support_kwargs())
    assert isinstance(extraction_support_router, APIRouter)

    extraction_assistant_module = import_module("app.api.compat.extraction_assistant_router")
    with pytest.warns(DeprecationWarning):
        extraction_assistant_router = extraction_assistant_module.build_extraction_assistant_router(assistant1_runtime=object())
    assert isinstance(extraction_assistant_router, APIRouter)

    sync_module = import_module("app.api.compat.sync_router")
    with pytest.warns(DeprecationWarning):
        sync_router = sync_module.build_sync_router(**_sync_kwargs())
    assert isinstance(sync_router, APIRouter)

    module4_sync_module = import_module("app.api.compat.module4_sync_router")
    with pytest.warns(DeprecationWarning):
        module4_sync_router = module4_sync_module.build_module4_sync_router(**_sync_kwargs())
    assert isinstance(module4_sync_router, APIRouter)
