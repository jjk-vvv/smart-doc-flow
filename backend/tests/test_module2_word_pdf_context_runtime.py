from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path


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


word_pdf_context_runtime_module = _load_module(
    ["module2", "app", "core", "format", "word_input_preparation_runtime.py"],
    "_smart_doc_flow_module2_word_pdf_context_runtime",
)

WordPdfContextRuntime = word_pdf_context_runtime_module.WordPdfContextRuntime


def test_word_pdf_context_runtime_builds_parse_context_with_source_signals() -> None:
    context = WordPdfContextRuntime.build_parse_context(
        file_name="report.pdf",
        source_file_name="report.docx",
        source_file_bytes=b"docx-bytes",
        use_source_signals=True,
    )

    assert context["is_word_pdf_context"] is True
    assert context["parse_source_file_name"] == "report.docx"
    assert context["parse_source_file_bytes"] == b"docx-bytes"
    assert context["parse_source_cache_identity"] == hashlib.sha256(b"docx-bytes").hexdigest()


def test_word_pdf_context_runtime_can_disable_source_signal_forwarding() -> None:
    context = WordPdfContextRuntime.build_parse_context(
        file_name="report.pdf",
        source_file_name="report.docx",
        source_file_bytes=b"docx-bytes",
        use_source_signals=False,
    )

    assert context["is_word_pdf_context"] is True
    assert context["parse_source_file_name"] is None
    assert context["parse_source_file_bytes"] is None
    assert context["parse_source_cache_identity"] == hashlib.sha256(b"docx-bytes").hexdigest()


def test_word_pdf_context_runtime_builds_source_stats_patch() -> None:
    stats_patch = WordPdfContextRuntime.build_source_stats_patch(
        source_file_name="report.docx",
        parse_source_file_name="report.docx",
        parse_source_cache_identity=hashlib.sha256(b"docx-bytes").hexdigest(),
        use_source_signals=True,
        chart_xml_merge_enabled=True,
    )

    assert stats_patch["word_pdf_parse_use_source_signals"] is True
    assert stats_patch["word_pdf_parse_source_signals_applied"] is True
    assert stats_patch["word_pdf_parse_source_cache_identity_seeded"] is True
    assert stats_patch["word_pdf_docx_chart_xml_merge_enabled"] is True
    assert stats_patch["source_cache_identity_applied"] is True
    assert stats_patch["source_cache_identity_file_name"] == "report.docx"


def test_word_pdf_context_runtime_builds_docx_chart_merge_stats_patch() -> None:
    state = {"calls": 0}

    stats_patch = WordPdfContextRuntime.build_docx_chart_merge_stats_patch(
        enabled=True,
        source_file_name="report.docx",
        apply_docx_chart_merge=lambda: state.update(calls=state["calls"] + 1),
    )

    assert state["calls"] == 1
    assert stats_patch["docx_source_chart_merge_applied"] is True
    assert stats_patch["docx_source_file_name"] == "report.docx"
    assert isinstance(stats_patch["docx_source_chart_merge_ms"], int)


def test_word_pdf_context_runtime_marks_docx_chart_merge_skipped_when_disabled() -> None:
    stats_patch = WordPdfContextRuntime.build_docx_chart_merge_stats_patch(
        enabled=False,
        source_file_name="report.docx",
        apply_docx_chart_merge=lambda: None,
    )

    assert stats_patch == {
        "docx_source_chart_merge_applied": False,
        "docx_source_chart_merge_skipped": True,
        "docx_source_chart_merge_ms": 0,
        "docx_source_file_name": "report.docx",
    }
