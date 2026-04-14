from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


runtime_module = import_module("app.modules.module2.runtime.document_trace_hits_runtime")
DocumentTraceHitsRuntime = runtime_module.DocumentTraceHitsRuntime


def _build_runtime() -> DocumentTraceHitsRuntime:
    def _normalize_bbox(bbox, page_hint=None):
        if not isinstance(bbox, list):
            return []
        if len(bbox) == 5:
            try:
                return [float(value) for value in bbox[:5]]
            except (TypeError, ValueError):
                return []
        if len(bbox) == 4 and page_hint is not None:
            try:
                return [
                    float(page_hint),
                    float(bbox[0]),
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                ]
            except (TypeError, ValueError):
                return []
        return []

    def _page_from_bbox(bbox):
        if not isinstance(bbox, list) or len(bbox) != 5:
            return None
        try:
            page_no = int(round(float(bbox[0])))
        except (TypeError, ValueError):
            return None
        return page_no if page_no >= 1 else None

    def _is_meaningful_bbox(bbox):
        if len(bbox) != 5:
            return False
        try:
            _, x, y, w, h = [float(value) for value in bbox[:5]]
        except Exception:
            return False
        if w <= 0 or h <= 0:
            return False
        if x <= 0.0001 and y <= 0.0001 and w >= 0.995 and h >= 0.995:
            return False
        return True

    def _resolve_trace_artifact_ref(payload):
        artifact_path = str(payload.get("artifact_path") or "").strip() or None
        artifact_url = str(payload.get("artifact_url") or "").strip() or None
        if artifact_path and not artifact_url:
            artifact_url = f"/extract/artifact/{artifact_path}"
        return artifact_path, artifact_url

    return DocumentTraceHitsRuntime(
        normalize_bbox=_normalize_bbox,
        page_from_bbox=_page_from_bbox,
        is_meaningful_bbox=_is_meaningful_bbox,
        resolve_trace_artifact_ref=_resolve_trace_artifact_ref,
        trace_hits_max_factory=lambda: 420,
    )


def test_document_trace_hits_runtime_builds_field_table_and_figure_hits() -> None:
    runtime = _build_runtime()

    hits = runtime.build_document_trace_hits(
        file_name="report.docx",
        file_hash="hash-1",
        results={
            "amount": {
                "value": "100",
                "source_ref_id": "docx_3",
                "bbox": [1, 0, 0, 1, 1],
                "confidence": 0.91,
            }
        },
        table_blocks=[
            {
                "table_id": "docx_t2",
                "headers": ["日期", "金额", "备注"],
                "rows": [
                    {
                        "cells": [
                            {
                                "text": "2024-01-01",
                                "ref_id": "docx_t2_r1_c1",
                                "bbox": [2, 0.15, 0.2, 0.3, 0.1],
                            },
                            {"text": "100"},
                        ]
                    }
                ],
                "row_count": 1,
                "col_count": 3,
                "source": "gemini_vision_table",
                "page": 2,
                "caption": "付款计划",
                "quality": 0.72,
                "artifact_path": "tables/table-1.png",
            }
        ],
        figure_blocks=[
            {
                "figure_id": "docx_f1",
                "page": 5,
                "ref_ids": ["docx_6"],
                "caption": "流程图",
                "figure_type": "chart",
                "source": "gemini_vision_figure",
                "quality": 0.83,
                "bbox": [5, 0.2, 0.2, 0.45, 0.35],
                "key_points": ["审批", "归档"],
                "content_modes": ["visual", "text"],
                "dataframe": {
                    "headers": ["阶段", "时长"],
                    "rows": [["审批", "1天"]],
                },
                "dataframe_source": "gemini_vision_chart",
                "topology": {
                    "nodes": [{"id": "n1"}],
                    "edges": [{"from": "n1", "to": "n2"}],
                },
                "text_blocks": ["开始", "结束"],
                "artifact_url": "/extract/artifact/figures/figure-1.png",
            }
        ],
        markdown=(
            '<ref id="docx_3">合同金额字段</ref>'
            '<ref id="docx_t2_r1_c1">付款计划表首行</ref>'
            '<ref id="docx_6">流程图说明</ref>'
        ),
        bbox_map={"docx_3": [4, 0.1, 0.2, 0.3, 0.4]},
    )

    assert [hit["object_type"] for hit in hits] == ["field", "figure", "table"]

    field_hit = hits[0]
    assert field_hit["bbox"] == [4.0, 0.1, 0.2, 0.3, 0.4]
    assert field_hit["page"] == 4
    assert "合同金额字段" in field_hit["snippet"]
    assert field_hit["locator"]["paragraph_index"] == 3
    assert field_hit["locator"]["ref_scope"] == "paragraph"

    figure_hit = hits[1]
    assert figure_hit["artifact_url"] == "/extract/artifact/figures/figure-1.png"
    assert figure_hit["locator"]["figure_index"] == 1
    assert figure_hit["locator"]["dataframe_source"] == "gemini_vision_chart"
    assert figure_hit["locator"]["caption"] == "流程图"
    assert figure_hit["locator"]["dataframe"]["headers"] == ["阶段", "时长"]

    table_hit = hits[2]
    assert table_hit["artifact_path"] == "tables/table-1.png"
    assert table_hit["artifact_url"] == "/extract/artifact/tables/table-1.png"
    assert table_hit["locator"]["table_index"] == 2
    assert table_hit["locator"]["row_index"] == 1
    assert table_hit["locator"]["col_index"] == 1
    assert table_hit["locator"]["dataframe_source"] == "gemini_vision_table"
    assert table_hit["locator"]["table_preview"]["headers"] == ["日期", "金额", "备注"]
    assert "付款计划表首行" in table_hit["snippet"]


def test_document_trace_hits_runtime_deduplicates_by_higher_confidence() -> None:
    runtime = _build_runtime()

    hits = runtime.build_document_trace_hits(
        file_name="demo.pdf",
        file_hash="hash-2",
        results={},
        table_blocks=[
            {
                "table_id": "t-1",
                "headers": ["列1"],
                "rows": [{"cells": [{"text": "值1", "ref_id": "pdf_t1_r1_c1"}]}],
                "row_count": 1,
                "col_count": 1,
                "source": "table_structured",
                "page": 1,
                "caption": "重复表格",
                "quality": 0.40,
            },
            {
                "table_id": "t-1",
                "headers": ["列1"],
                "rows": [{"cells": [{"text": "值1", "ref_id": "pdf_t1_r1_c1"}]}],
                "row_count": 1,
                "col_count": 1,
                "source": "table_structured",
                "page": 1,
                "caption": "重复表格",
                "quality": 0.88,
            },
        ],
        figure_blocks=[],
        markdown="",
    )

    assert len(hits) == 1
    assert hits[0]["object_type"] == "table"
    assert hits[0]["confidence"] == 0.88
