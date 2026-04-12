from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "module2"
        / "app"
        / "services"
        / "document_tools_service.py"
    )
    module_name = "_smart_doc_flow_module2_document_tools_service"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


runtime_module = _load_module()
DocumentToolsRuntime = runtime_module.DocumentToolsRuntime
TraceLocatorPayloadRuntime = runtime_module.TraceLocatorPayloadRuntime
TraceLocatorTextRuntime = runtime_module.TraceLocatorTextRuntime


def test_trace_locator_payload_runtime_distinguishes_parser_artifact_sources() -> None:
    runtime = TraceLocatorPayloadRuntime()

    assert runtime.artifact_source_key({"image_path": "runtime-data/module2/work/mineru/table.png"}) == "pdf_mineru"
    assert runtime.artifact_source_key(
        {
            "artifact_path": "runtime-data/module2/artifacts/docx_media/img.png",
            "source": "docx_media_vision",
        }
    ) == "docx_media_vision"
    assert runtime.artifact_source_key(
        {
            "artifact_path": "runtime-data/module2/artifacts/trace/t1.png",
            "source": "pdf_fitz",
        }
    ) == "pdf_roi_crop"
    assert runtime.artifact_source_key(
        {
            "artifact_path": "runtime-data/module2/artifacts/custom/out.png",
            "source": "custom_parser",
        }
    ) == "custom_parser"


def test_document_tools_runtime_summarize_uses_callback() -> None:
    calls: list[str] = []

    runtime = DocumentToolsRuntime(
        summarize_document_payload=lambda payload: calls.append(payload.file_name) or "summary-text",
        build_document_trace_hits=lambda **kwargs: [],
        filter_trace_hits=lambda hits, **kwargs: hits,
        summarize_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        trace_locate_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    payload = runtime.summarize(SimpleNamespace(file_name="demo.pdf"))

    assert calls == ["demo.pdf"]
    assert payload.summary == "summary-text"


def test_document_tools_runtime_trace_locate_uses_existing_hits_and_filters() -> None:
    filter_calls: list[dict] = []

    runtime = DocumentToolsRuntime(
        summarize_document_payload=lambda payload: "unused",
        build_document_trace_hits=lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected build")),
        filter_trace_hits=lambda hits, **kwargs: filter_calls.append(dict(kwargs)) or hits,
        summarize_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        trace_locate_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    doc = SimpleNamespace(
        file_name="demo.pdf",
        file_hash="hash-1",
        trace_hits=[{"object_id": "amount", "confidence": 0.9}],
        result=SimpleNamespace(model_dump=lambda mode="json": {}),
    )
    payload = runtime.trace_locate(
        SimpleNamespace(
            document=doc,
            field_name="amount",
            file_name="demo.pdf",
            file_hash="hash-1",
            ref_id="",
            object_type="",
            keyword="",
            top_k=1,
        )
    )

    assert filter_calls == [
        {
            "field_name": "amount",
            "file_name": "demo.pdf",
            "file_hash": "hash-1",
            "ref_id": "",
            "object_type": "",
            "keyword": "",
        }
    ]
    assert payload.hit_count == 1
    assert payload.truncated is False
    assert payload.hits == [{"object_id": "amount", "confidence": 0.9}]


def test_document_tools_runtime_trace_locate_builds_hits_when_missing() -> None:
    build_calls: list[dict] = []

    runtime = DocumentToolsRuntime(
        summarize_document_payload=lambda payload: "unused",
        build_document_trace_hits=lambda **kwargs: build_calls.append(dict(kwargs)) or [{"object_id": "fallback"}],
        filter_trace_hits=lambda hits, **kwargs: hits,
        summarize_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        trace_locate_response_factory=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    doc = SimpleNamespace(
        file_name="demo.pdf",
        file_hash="hash-1",
        trace_hits=[],
        result=SimpleNamespace(model_dump=lambda mode="json": {"root": {"amount": {"value": "100"}}}),
    )
    payload = runtime.trace_locate(
        SimpleNamespace(
            document=doc,
            field_name="",
            file_name="",
            file_hash="",
            ref_id="",
            object_type="",
            keyword="",
            top_k=5,
        )
    )

    assert build_calls and build_calls[0]["file_name"] == "demo.pdf"
    assert build_calls[0]["results"] == {"amount": {"value": "100"}}
    assert payload.hit_count == 1
    assert payload.hits == [{"object_id": "fallback"}]


def test_trace_locator_text_runtime_builds_table_and_figure_locator_summaries() -> None:
    runtime = TraceLocatorTextRuntime()

    table_locator = runtime.table_locator_texts(
        {
            "table_id": "docx_t2",
            "caption": "付款计划（gemini_vision_table）",
            "headers": ["日期", "金额", "备注"],
            "rows": [
                {
                    "cells": [
                        {"text": "2024-01-01"},
                        {"text": "100"},
                    ]
                }
            ],
        }
    )
    figure_locator = runtime.figure_locator_texts(
        {
            "figure_id": "docx_f1",
            "title": "figure: 流程图",
            "caption": "流程图（pdf_mineru）",
            "key_points": ["审批", "归档"],
            "legend": ["开始", "结束"],
            "axes": {"x": "阶段", "y": "时长"},
            "dataframe": {
                "headers": ["阶段", "时长"],
                "rows": [["审批", "1天"]],
            },
        }
    )

    assert table_locator["title"] == "付款计划"
    assert "表头" in table_locator["summary"]
    assert figure_locator["title"] == "流程图"
    assert figure_locator["summary"] in {"流程图", "审批；归档"}


def test_trace_locator_payload_runtime_builds_nonpdf_hints_and_payloads() -> None:
    runtime = TraceLocatorPayloadRuntime()

    locator = runtime.nonpdf_locator_from_ref("docx_t2_r1_c3", "report.docx")
    table_hint = runtime.table_locator_hint({"table_id": "docx_t2"}, "report.docx")
    figure_hint = runtime.figure_locator_hint({"figure_id": "note_f3"}, "note.md")
    table_payload = runtime.table_preview_payload(
        {
            "headers": ["日期", "金额", "备注"],
            "rows": [
                {"cells": [{"text": "2024-01-01"}, {"text": "100"}, {"text": "已付"}]},
            ],
        }
    )
    figure_payload = runtime.figure_dataframe_payload(
        {
            "dataframe": {
                "headers": ["阶段", "时长"],
                "rows": [["审批", "1天"]],
            },
            "source": "gemini_vision_figure",
        }
    )

    assert locator == {
        "table_index": 2,
        "row_index": 1,
        "col_index": 3,
        "ref_scope": "cell",
    }
    assert table_hint == {"table_index": 2}
    assert figure_hint == {"figure_index": 3}
    assert table_payload["headers"] == ["日期", "金额", "备注"]
    assert table_payload["rows"] == [["2024-01-01", "100", "已付"]]
    assert figure_payload["headers"] == ["阶段", "时长"]
