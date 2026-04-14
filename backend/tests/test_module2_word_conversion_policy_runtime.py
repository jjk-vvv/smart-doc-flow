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


word_conversion_policy_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "format", "word_input_preparation_runtime.py"],
    "_smart_doc_flow_module2_word_conversion_policy_runtime",
)

WordConversionPolicyRuntime = word_conversion_policy_runtime_module.WordConversionPolicyRuntime


class _PreviewJob:
    def __init__(self) -> None:
        self.converter = "job-converter"
        self.elapsed_ms = 88
        self.artifact_path = "preview/op/demo.pdf"
        self.artifact_url = "/extract/artifact/preview/op/demo.pdf"
        self.job_id = "job-123"


def test_word_conversion_policy_runtime_validates_preconditions() -> None:
    runtime = WordConversionPolicyRuntime()

    disabled_pdf = runtime.validate_preconditions(
        word_parse_via_pdf=True,
        office_convert_enabled=False,
        word_suffix=".docx",
    )
    disabled_doc = runtime.validate_preconditions(
        word_parse_via_pdf=False,
        office_convert_enabled=False,
        word_suffix=".doc",
    )
    ok = runtime.validate_preconditions(
        word_parse_via_pdf=False,
        office_convert_enabled=True,
        word_suffix=".docx",
    )

    assert disabled_pdf.should_raise is True
    assert disabled_pdf.terminal_status_code == 503
    assert "必须先转为 PDF 后再解析" in disabled_pdf.terminal_detail
    assert disabled_doc.should_raise is True
    assert disabled_doc.terminal_status_code == 503
    assert "DOC->DOCX 预处理" in disabled_doc.terminal_detail
    assert ok.should_raise is False


def test_word_conversion_policy_runtime_builds_word_pdf_success_diag() -> None:
    runtime = WordConversionPolicyRuntime()
    preview_job = _PreviewJob()

    result = runtime.build_word_pdf_success(
        file_name="report.docx",
        convert_timeout_sec=24.5,
        total_elapsed_ms=1400,
        preview_meta={
            "converter": "preview-runtime",
            "elapsed_ms": 55,
            "artifact_path": "preview/op/runtime.pdf",
            "artifact_url": "/extract/artifact/preview/op/runtime.pdf",
            "office_pdf_preview_job_id": "job-999",
            "waited_ms": 230,
            "office_pdf_preview_error": "",
        },
        preview_job=preview_job,
    )

    assert result["parse_input_name"] == "report.pdf"
    assert result["parse_track"] == "VisualTrack"
    assert result["conversion_diag"] == {
        "office_pdf_converted": True,
        "office_pdf_converter": "preview-runtime",
        "office_pdf_elapsed_ms": 55,
        "office_pdf_timeout_sec": 24.5,
        "office_pdf_preview_path": "preview/op/runtime.pdf",
        "office_pdf_preview_url": "/extract/artifact/preview/op/runtime.pdf",
        "office_pdf_preview_reused": True,
        "office_pdf_preview_job_id": "job-999",
        "office_pdf_preview_waited_ms": 230,
        "office_pdf_total_ms": 1400,
    }


def test_word_conversion_policy_runtime_resolves_word_pdf_failure_to_native_docx_recovery() -> None:
    runtime = WordConversionPolicyRuntime()

    decision = runtime.resolve_word_pdf_failure(
        file_name="report.docx",
        word_suffix=".docx",
        exc=RuntimeError("preview failed"),
        convert_timeout_sec=30.0,
        total_elapsed_ms=1200,
        word_parse_via_pdf=True,
        docx_native_recovery_enabled=True,
        allow_native_fallback=False,
    )

    assert decision.should_raise is False
    assert decision.parse_track == "NativeDocx"
    assert decision.parse_warning == "docx_native_recovery_after_pdf_failure"
    assert decision.use_original_input is True
    assert decision.emit_progress_message == "Word PDF 链路失败，已切换 DOCX 原生恢复解析"
    assert decision.conversion_diag["office_pdf_converted"] is False
    assert decision.conversion_diag["docx_native_recovery_requested"] is True
    assert "RuntimeError: preview failed" in decision.conversion_diag["docx_native_recovery_reason"]


def test_word_conversion_policy_runtime_resolves_word_pdf_failure_to_fasttrack_fallback() -> None:
    runtime = WordConversionPolicyRuntime()

    decision = runtime.resolve_word_pdf_failure(
        file_name="report.docx",
        word_suffix=".docx",
        exc=TimeoutError("preview timeout"),
        convert_timeout_sec=18.0,
        total_elapsed_ms=900,
        word_parse_via_pdf=False,
        docx_native_recovery_enabled=False,
        allow_native_fallback=True,
    )

    assert decision.should_raise is False
    assert decision.parse_track == "FastTrack"
    assert decision.parse_warning == "doc_to_pdf_fallback_native:TimeoutError"
    assert decision.use_original_input is True
    assert decision.emit_progress_message == ""


def test_word_conversion_policy_runtime_resolves_word_pdf_failure_to_terminal_error() -> None:
    runtime = WordConversionPolicyRuntime()

    decision = runtime.resolve_word_pdf_failure(
        file_name="report.doc",
        word_suffix=".doc",
        exc=RuntimeError("convert failed"),
        convert_timeout_sec=20.0,
        total_elapsed_ms=700,
        word_parse_via_pdf=True,
        docx_native_recovery_enabled=False,
        allow_native_fallback=False,
    )

    assert decision.should_raise is True
    assert decision.terminal_status_code == 422
    assert "Word 转 PDF 失败，无法处理 report.doc" in decision.terminal_detail


def test_word_conversion_policy_runtime_builds_doc_to_docx_diags() -> None:
    runtime = WordConversionPolicyRuntime()

    success = runtime.build_doc_to_docx_success(
        file_name="legacy.doc",
        convert_timeout_sec=16.2,
        total_elapsed_ms=640,
        convert_meta={"converter": "soffice", "elapsed_ms": 222},
    )
    failure = runtime.build_doc_to_docx_failure(
        file_name="legacy.doc",
        exc=RuntimeError("office unavailable"),
        convert_timeout_sec=16.2,
        total_elapsed_ms=800,
    )

    assert success["parse_input_name"] == "legacy.docx"
    assert success["conversion_diag"] == {
        "doc_to_docx_converted": True,
        "doc_to_docx_converter": "soffice",
        "doc_to_docx_elapsed_ms": 222,
        "doc_to_docx_timeout_sec": 16.2,
        "doc_to_docx_total_ms": 640,
    }
    assert failure["conversion_diag"]["doc_to_docx_converted"] is False
    assert failure["terminal_status_code"] == 422
    assert "DOC 转 DOCX 失败，无法处理 legacy.doc" in failure["terminal_detail"]
