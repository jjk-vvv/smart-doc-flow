from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import APIRouter


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))


def _build_kwargs() -> dict:
    return {
        "extraction_request_runtime": object(),
        "office_preview_request_runtime": object(),
        "document_tools_runtime": object(),
        "clear_cache_request": lambda scope: {"ok": True, "scope": scope},
        "serve_layout_preview": lambda artifact_name, method: object(),
        "serve_artifact": lambda artifact_path, method: object(),
        "build_health_payload": lambda: {"status": "ok"},
        "assistant1_runtime": object(),
        "list_outbox_rows": lambda **kwargs: [],
        "get_outbox_row": lambda outbox_id: None,
        "build_list_response": lambda rows, **kwargs: {"rows": rows},
        "serialize_outbox_row": lambda row: {},
        "metrics_snapshot": lambda: {},
    }


def test_module2_legacy_router_build_emits_deprecation_warning() -> None:
    compat_module = import_module("app.api.compat.router_bundle")
    with pytest.warns(DeprecationWarning):
        routers = compat_module.build_module2_routers(**_build_kwargs())
    assert isinstance(routers, tuple)
    assert all(isinstance(router, APIRouter) for router in routers)


def test_module2_routes_router_bundle_is_thin_shim() -> None:
    routes_module = import_module("app.routes.router_bundle")
    compat_module = import_module("app.api.compat.router_bundle")
    assert routes_module.build_module2_routers is compat_module.build_module2_routers

