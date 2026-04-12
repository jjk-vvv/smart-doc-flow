from __future__ import annotations

import json

from app.modules.extraction import summary_runtime
from app.modules.extraction.schemas import (
    DocumentExtractionResponse,
    SummarizeRequest,
    TraceLocateRequest,
)
from app.modules.extraction.summary_runtime import summarize_document, trace_locate


def test_extraction_summary_runtime_summarize_returns_non_empty_summary() -> None:
    payload = SummarizeRequest(
        file_name="demo.pdf",
        result={
            "contract_amount": {
                "value": "1000",
                "confidence": 0.95,
                "source_ref_id": "field-ref-1",
                "bbox": [1, 10, 20, 30, 40],
            }
        },
        diagnostics={
            "table_count": 1,
            "figure_count": 1,
            "trace_display_counts": {"table": 1, "image": 1},
        },
        trace_hits=[
            {
                "file_name": "demo.pdf",
                "file_hash": "hash-demo-1",
                "object_type": "field",
                "object_id": "contract_amount",
                "ref_id": "field-ref-1",
                "page": 1,
                "snippet": "Contract amount is 1000",
                "confidence": 0.95,
                "locator": {"page": 1, "ref_id": "field-ref-1"},
                "bbox": [1, 10, 20, 30, 40],
                "match_reason": "field_match",
            },
            {
                "file_name": "demo.pdf",
                "file_hash": "hash-demo-1",
                "object_type": "figure",
                "object_id": "fig-1",
                "ref_id": "fig-ref-1",
                "page": 2,
                "snippet": "Revenue trend chart",
                "confidence": 0.86,
                "locator": {
                    "caption": "Revenue trend chart",
                    "content_modes": ["visual"],
                    "figure_type": "chart",
                },
                "bbox": [2, 10, 20, 30, 40],
                "match_reason": "figure_match",
            },
        ],
        max_chars=400,
    )

    summary = summarize_document(payload).summary

    assert summary
    assert "demo.pdf" in summary
    assert "1000" in summary
    assert len(summary) <= 400


def test_extraction_summary_runtime_trace_locate_builds_hits_from_document_result() -> None:
    document = DocumentExtractionResponse.model_validate(
        {
            "file_name": "demo.pdf",
            "file_hash": "hash-demo-2",
            "track": "done",
            "cached": False,
            "result": {
                "contract_amount": {
                    "value": "2000",
                    "confidence": 0.91,
                    "source_ref_id": "ref-1",
                    "bbox": [3, 11, 21, 31, 41],
                }
            },
            "errors": [],
            "soft_warnings": [],
            "trace_hits": [],
            "trace_stats": {},
            "diagnostics": {},
        }
    )

    response = trace_locate(
        TraceLocateRequest(
            document=document,
            field_name="contract_amount",
            file_name="demo.pdf",
            object_type="field",
            top_k=5,
        )
    )

    assert response.hit_count == 1
    assert response.truncated is False
    assert len(response.hits) == 1
    assert response.hits[0].object_id == "contract_amount"
    assert response.hits[0].ref_id == "ref-1"
    assert response.hits[0].page == 3


def test_extraction_summary_runtime_trace_locate_enriches_sparse_hits_from_assistant_payload(
    tmp_path,
    monkeypatch,
) -> None:
    file_hash = "7205100d63522791a831642c8591ec8ac7ece38ab68abddb73f145e2e7576725"
    artifact_root = tmp_path / "artifacts"
    payload_dir = artifact_root / "assistant_payload" / file_hash[:12]
    payload_dir.mkdir(parents=True, exist_ok=True)

    image_path = tmp_path / "source-image.jpg"
    image_path.write_bytes(b"fake-image")

    assistant_payload = {
        "version": "module2-assistant-payload-v1",
        "file_hash": file_hash,
        "tables": [
            {
                "table_id": "pdf_mineru_gemini_t1",
                "page": 2,
                "headers": ["A", "B"],
                "rows": [
                    {
                        "cells": [
                            {"text": "r1c1", "ref_id": "pdf_mineru_gemini_t1_r1_c1"},
                            {"text": "r1c2", "ref_id": "pdf_mineru_gemini_t1_r1_c2"},
                        ]
                    }
                ],
                "quality": 0.95,
                "caption": "示例表格",
                "image_path": str(image_path),
            }
        ],
        "figures": [
            {
                "figure_id": "pdf_mineru_gemini_f1",
                "page": 3,
                "figure_type": "chart",
                "caption": "示例图像",
                "ref_ids": ["pdf_mineru_gemini_f1_caption"],
                "quality": 0.92,
                "image_path": str(image_path),
                "dataframe": {"headers": ["x", "y"], "rows": [["1", "2"]]},
                "content_modes": ["visual", "dataframe"],
            }
        ],
    }
    payload_path = payload_dir / "assistant_payload_test.json"
    payload_path.write_text(json.dumps(assistant_payload, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(summary_runtime, "_artifact_root_dir", lambda: artifact_root.resolve())

    document = DocumentExtractionResponse.model_validate(
        {
            "file_name": "demo.docx",
            "file_hash": file_hash,
            "track": "VisualTrack",
            "cached": True,
            "result": {
                "contract_amount": {
                    "value": "123",
                    "confidence": 0.9,
                    "source_ref_id": "field-ref-1",
                    "bbox": [1, 0, 0, 1, 1],
                }
            },
            "errors": [],
            "soft_warnings": [],
            "trace_hits": [
                {
                    "file_name": "demo.docx",
                    "file_hash": file_hash,
                    "object_type": "table",
                    "ref_id": "pdf_mineru_gemini_t1_r1_c1",
                    "page": 2,
                    "snippet": "sparse-table-hit",
                    "confidence": 0.8,
                },
                {
                    "file_name": "demo.docx",
                    "file_hash": file_hash,
                    "object_type": "figure",
                    "ref_id": "pdf_mineru_gemini_f1_caption",
                    "page": 3,
                    "snippet": "sparse-figure-hit",
                    "confidence": 0.8,
                },
            ],
            "trace_stats": {},
            "diagnostics": {},
        }
    )

    response = trace_locate(TraceLocateRequest(document=document, top_k=20))

    assert response.hit_count >= 2
    table_hit = next((hit for hit in response.hits if hit.object_type == "table"), None)
    assert table_hit is not None
    assert table_hit.object_id == "pdf_mineru_gemini_t1"
    assert str(table_hit.artifact_url or "").startswith("/extract/artifact/linked/")
    assert isinstance(table_hit.locator.get("dataframe"), dict)
    assert table_hit.locator.get("dataframe", {}).get("rows")

    figure_hit = next((hit for hit in response.hits if hit.object_type == "figure"), None)
    assert figure_hit is not None
    assert figure_hit.object_id == "pdf_mineru_gemini_f1"
    assert str(figure_hit.artifact_url or "").startswith("/extract/artifact/linked/")
    assert isinstance(figure_hit.locator.get("dataframe"), dict)
    assert figure_hit.locator.get("dataframe", {}).get("rows")


def test_extraction_summary_runtime_preserves_rich_summary_semantics() -> None:
    payload = SummarizeRequest(
        file_name="demo.pdf",
        result={
            "contract_amount": {"value": "100万元", "confidence": 0.93},
        },
        trace_hits=[
            {
                "file_name": "demo.pdf",
                "file_hash": "hash-demo-3",
                "object_type": "field",
                "object_id": "contract_amount",
                "ref_id": "field-ref-2",
                "page": 1,
                "snippet": "合同金额 100万元",
                "confidence": 0.93,
                "locator": {},
                "bbox": [1, 10, 20, 30, 40],
                "match_reason": "field_match",
            },
            {
                "file_name": "demo.pdf",
                "file_hash": "hash-demo-3",
                "object_type": "figure",
                "object_id": "table-1",
                "ref_id": "table-ref-1",
                "page": 2,
                "snippet": "付款计划表",
                "confidence": 0.88,
                "locator": {
                    "figure_type": "spreadsheet",
                    "sheet_name": "付款计划",
                    "table_preview": {"headers": ["日期", "金额", "备注"]},
                },
                "bbox": [2, 10, 20, 30, 40],
                "match_reason": "figure_match",
            },
            {
                "file_name": "demo.pdf",
                "file_hash": "hash-demo-3",
                "object_type": "figure",
                "object_id": "fig-2",
                "ref_id": "fig-ref-2",
                "page": 3,
                "snippet": "流程图",
                "confidence": 0.86,
                "locator": {
                    "caption": "业务流程图",
                    "content_modes": ["visual"],
                    "key_points": ["审批节点"],
                },
                "bbox": [3, 10, 20, 30, 40],
                "match_reason": "figure_match",
            },
        ],
        diagnostics={
            "table_count": 1,
            "figure_count": 1,
            "trace_display_counts": {"table": 1, "image": 1},
        },
        errors=[],
        soft_warnings=["table_extract_timeout: retry exceeded"],
        max_chars=400,
    )

    summary = summarize_document(payload).summary

    assert "文档《demo.pdf》已完成内容解析" in summary
    assert "合同金额为100万元" in summary
    assert "付款计划表格包含 日期 / 金额 / 备注" in summary
    assert "业务流程图" in summary
    assert "复杂表格抽取超时" in summary
