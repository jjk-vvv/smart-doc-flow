from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("path_parts", "build_name", "kwargs"),
    [
        (
            ["module2", "app", "routes", "extraction_request_router.py"],
            "build_extraction_request_router",
            {"extraction_request_runtime": object()},
        ),
        (
            ["module2", "app", "routes", "extraction_support_router.py"],
            "build_extraction_support_router",
            {
                "office_preview_request_runtime": object(),
                "document_tools_runtime": object(),
                "clear_cache_request": lambda scope: {"scope": scope},
                "serve_layout_preview": lambda artifact_name, request_method: None,
                "serve_artifact": lambda artifact_path, request_method: None,
                "build_health_payload": lambda: {"status": "ok"},
            },
        ),
        (
            ["module2", "app", "routes", "extraction_assistant_router.py"],
            "build_extraction_assistant_router",
            {"assistant1_runtime": object()},
        ),
        (
            ["module2", "app", "routes", "module4_sync_router.py"],
            "build_module4_sync_router",
            {
                "list_outbox_rows": lambda **kwargs: [],
                "get_outbox_row": lambda outbox_id: None,
                "build_list_response": lambda **kwargs: {"items": [], "count": 0},
                "serialize_outbox_row": lambda row, include_payload=False: {},
                "metrics_snapshot": lambda: {},
            },
        ),
    ],
)
def test_module2_legacy_routes_delegate_to_api_endpoints_with_warning(
    path_parts: list[str],
    build_name: str,
    kwargs: dict[str, object],
) -> None:
    module = _load_module(
        path_parts,
        f"_smart_doc_flow_module2_compat_{path_parts[-1].replace('.', '_')}",
    )
    build_fn = getattr(module, build_name)
    with pytest.warns(DeprecationWarning):
        router = build_fn(**kwargs)
    assert isinstance(router, APIRouter)
