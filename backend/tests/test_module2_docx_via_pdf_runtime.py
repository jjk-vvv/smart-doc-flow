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


docx_via_pdf_runtime_module = _load_module(
    ["module2", "app", "core", "format", "docx_document_runtime.py"],
    "_smart_doc_flow_module2_docx_document_runtime_for_via_pdf",
)

DocxViaPdfRuntime = docx_via_pdf_runtime_module.DocxViaPdfRuntime


def test_docx_via_pdf_runtime_converts_docx_and_calls_pdf_parse_with_source_signals() -> None:
    captured: dict[str, object] = {}
    runtime = DocxViaPdfRuntime(
        word_pdf_timeout_sec=180,
        word_pdf_parse_use_source_signals=True,
        word_pdf_docx_chart_xml_merge_enable=True,
        convert_word_bytes_to_pdf=lambda **kwargs: (
            captured.update(convert_kwargs=kwargs)
            or (b"%PDF-converted", {"converter": "soffice", "elapsed_ms": 456, "cache_hit": True})
        ),
        parse_pdf=lambda file_name, file_bytes, track, **kwargs: (
            captured.update(
                parse_file_name=file_name,
                parse_file_bytes=file_bytes,
                parse_track=track,
                parse_kwargs=kwargs,
            )
            or ("markdown", {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "pdf_t1"}])
        ),
    )

    result = runtime.parse_docx_via_pdf(
        file_name="report.docx",
        file_bytes=b"docx-bytes",
    )

    assert captured["convert_kwargs"] == {
        "file_name": "report.docx",
        "file_bytes": b"docx-bytes",
        "timeout_sec": 180,
    }
    assert captured["parse_file_name"] == "report.pdf"
    assert captured["parse_file_bytes"] == b"%PDF-converted"
    assert captured["parse_track"] == "VisualTrack"
    assert captured["parse_kwargs"] == {
        "source_file_name": "report.docx",
        "source_file_bytes": b"docx-bytes",
        "source_cache_identity": hashlib.sha256(b"docx-bytes").hexdigest(),
    }
    assert result["markdown"] == "markdown"
    assert result["table_blocks"] == [{"table_id": "pdf_t1"}]
    assert result["stats_patch"]["office_pdf_converter"] == "soffice"
    assert result["stats_patch"]["office_pdf_elapsed_ms"] == 456
    assert result["stats_patch"]["office_pdf_cache_hit"] is True
    assert result["stats_patch"]["word_pdf_docx_chart_xml_merge_enabled"] is True
    assert result["stats_patch"]["source_cache_identity_file_name"] == "report.docx"


def test_docx_via_pdf_runtime_can_skip_source_signals() -> None:
    captured: dict[str, object] = {}
    runtime = DocxViaPdfRuntime(
        word_pdf_timeout_sec=60,
        word_pdf_parse_use_source_signals=False,
        word_pdf_docx_chart_xml_merge_enable=False,
        convert_word_bytes_to_pdf=lambda **kwargs: (b"%PDF-converted", {"converter": "libreoffice"}),
        parse_pdf=lambda file_name, file_bytes, track, **kwargs: (
            captured.update(kwargs=kwargs)
            or ("markdown", {}, [])
        ),
    )

    result = runtime.parse_docx_via_pdf(
        file_name="report.docx",
        file_bytes=b"docx-bytes",
    )

    assert captured["kwargs"] == {
        "source_file_name": None,
        "source_file_bytes": None,
        "source_cache_identity": hashlib.sha256(b"docx-bytes").hexdigest(),
    }
    assert result["stats_patch"]["word_pdf_parse_source_signals_applied"] is False
    assert result["stats_patch"]["word_pdf_docx_chart_xml_merge_enabled"] is False
