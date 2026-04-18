from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace


runtime_module = import_module("app.modules.module2.services.document.tools")
DocumentToolsSupportRuntime = runtime_module.DocumentToolsSupportRuntime


def test_document_tools_support_runtime_filters_trace_hits() -> None:
    runtime = DocumentToolsSupportRuntime(trace_display_kind_from_hit=lambda hit: "field")

    hits = [
        {
            "file_name": "demo.pdf",
            "file_hash": "hash-1",
            "object_type": "field",
            "object_id": "amount",
            "ref_id": "ref-1",
            "snippet": "amount: 100",
            "confidence": 0.9,
        },
        {
            "file_name": "other.pdf",
            "file_hash": "hash-2",
            "object_type": "field",
            "object_id": "amount",
            "ref_id": "ref-2",
            "snippet": "amount: 80",
            "confidence": 0.8,
        },
    ]

    filtered = runtime.filter_trace_hits(
        hits,
        field_name="amount",
        file_name="demo.pdf",
        file_hash="hash-1",
        ref_id="ref-1",
        object_type="field",
        keyword="100",
    )

    assert filtered == [hits[0]]


def test_document_tools_support_runtime_summarizes_document_payload() -> None:
    runtime = DocumentToolsSupportRuntime(trace_display_kind_from_hit=lambda hit: str(hit.get("display_kind") or "other"))

    payload = SimpleNamespace(
        file_name="demo.pdf",
        result={
            "contract_amount": {"value": "100万元", "confidence": 0.93},
        },
        trace_hits=[
            {
                "display_kind": "field",
                "object_id": "contract_amount",
                "snippet": "合同金额 100万元",
                "locator": {},
            },
            {
                "display_kind": "table",
                "object_id": "table-1",
                "snippet": "付款计划表",
                "locator": {
                    "sheet_name": "付款计划",
                    "table_preview": {"headers": ["日期", "金额", "备注"]},
                },
            },
            {
                "display_kind": "image",
                "object_id": "fig-1",
                "snippet": "流程图",
                "locator": {
                    "caption": "业务流程图",
                    "key_points": ["审批节点"],
                },
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

    summary = runtime.summarize_document_payload(payload)

    assert "文档《demo.pdf》已完成内容解析" in summary
    assert "合同金额为100万元" in summary
    assert "付款计划表格包含 日期 / 金额 / 备注" in summary
    assert "业务流程图" in summary
    assert "复杂表格抽取超时" in summary


def test_document_tools_support_runtime_summarizes_empty_payload_with_fallback_notice() -> None:
    runtime = DocumentToolsSupportRuntime(trace_display_kind_from_hit=lambda hit: "other")

    payload = SimpleNamespace(
        file_name="empty.pdf",
        result={},
        trace_hits=[],
        diagnostics={},
        errors=[],
        soft_warnings=[],
        max_chars=120,
    )

    summary = runtime.summarize_document_payload(payload)

    assert "当前已完成基础解析，但尚未形成足够稳定的内容摘要" in summary
    assert len(summary) <= 120
