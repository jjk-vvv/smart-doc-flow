from __future__ import annotations

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


document_flow_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_pipeline_runtime.py"],
    "_smart_doc_flow_module2_document_pipeline_runtime_for_parse_session",
)

DocumentParseSessionRuntime = document_flow_runtime_module.DocumentParseSessionRuntime


def test_document_parse_session_runtime_builds_word_pdf_source_context_and_visual_timeout() -> None:
    runtime = DocumentParseSessionRuntime(
        getenv=lambda name, default="": "120" if name == "MODULE2_PDF_VISUAL_PARSE_TIMEOUT_SEC" else default
    )

    result = runtime.build_session(
        file_name="report.docx",
        file_bytes=b"docx-bytes",
        parse_input_name="report.pdf",
        parse_track="VisualTrack",
        parse_timeout_sec=60.0,
        original_file_is_word=True,
    )

    assert result["parse_timeout_sec"] == 120.0
    assert result["parse_source_file_name"] == "report.docx"
    assert result["parse_source_file_bytes"] == b"docx-bytes"
    assert result["progress_extra"] == {
        "parse_input_name": "report.pdf",
        "source_file_name": "report.docx",
        "parse_track": "VisualTrack",
    }
    assert "report.pdf" in result["progress_message"]


def test_document_parse_session_runtime_keeps_non_visual_timeout_and_no_source_context() -> None:
    runtime = DocumentParseSessionRuntime()

    result = runtime.build_session(
        file_name="report.txt",
        file_bytes=b"text",
        parse_input_name="report.txt",
        parse_track="FastTrack",
        parse_timeout_sec=24.0,
        original_file_is_word=False,
    )

    assert result["parse_timeout_sec"] == 24.0
    assert result["parse_source_file_name"] is None
    assert result["parse_source_file_bytes"] is None
    assert result["progress_extra"] == {
        "parse_input_name": "report.txt",
        "source_file_name": "",
        "parse_track": "FastTrack",
    }
