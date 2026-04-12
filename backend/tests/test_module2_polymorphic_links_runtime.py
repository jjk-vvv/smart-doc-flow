from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "module2"
        / "app"
        / "services"
        / "document_tools_service.py"
    )
    module_name = "_smart_doc_flow_module2_polymorphic_links_service"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


runtime_module = _load_module()
PolymorphicLinksRuntime = runtime_module.PolymorphicLinksRuntime


def test_polymorphic_links_runtime_builds_links_from_ref_and_page_matches() -> None:
    runtime = PolymorphicLinksRuntime(
        normalize_bbox=lambda bbox, page_hint=None: list(bbox or []),
        page_from_bbox=lambda bbox: int(bbox[0]) if isinstance(bbox, list) and len(bbox) == 5 else None,
    )

    links = runtime.build_links(
        results={
            "amount": {
                "source_ref_id": "ref-1",
                "bbox": [2.0, 0.1, 0.2, 0.3, 0.4],
            }
        },
        trace_hits=[
            {
                "object_type": "table",
                "object_id": "table-1",
                "ref_id": "ref-1",
                "page": 2,
                "confidence": 0.7,
            },
            {
                "object_type": "figure",
                "object_id": "fig-1",
                "page": 2,
                "confidence": 0.8,
            },
            {
                "object_type": "table",
                "object_id": "table-2",
                "ref_id": "ref-x",
                "page": 9,
                "confidence": 0.99,
            },
        ],
    )

    assert links == [
        {
            "field": "amount",
            "ref_id": "ref-1",
            "page": 2,
            "targets": [
                {
                    "type": "figure",
                    "id": "fig-1",
                    "page": 2,
                    "confidence": 0.8,
                    "match": "page",
                },
                {
                    "type": "table",
                    "id": "table-1",
                    "page": 2,
                    "confidence": 0.7,
                    "match": "ref_id",
                },
            ],
        }
    ]


def test_polymorphic_links_runtime_returns_empty_for_non_matching_inputs() -> None:
    runtime = PolymorphicLinksRuntime(
        normalize_bbox=lambda bbox, page_hint=None: list(bbox or []),
        page_from_bbox=lambda bbox: None,
    )

    assert runtime.build_links(results={}, trace_hits=[]) == []
