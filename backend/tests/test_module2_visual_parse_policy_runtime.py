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


document_parse_recovery_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_parse_recovery_runtime.py"],
    "_smart_doc_flow_module2_document_parse_recovery_runtime_for_policy",
)

VisualParsePolicyRuntime = document_parse_recovery_runtime_module.VisualParsePolicyRuntime


def test_visual_parse_policy_runtime_appends_warning_fragments() -> None:
    runtime = VisualParsePolicyRuntime()

    assert runtime.append_warning(None, "first_warning") == "first_warning"
    assert runtime.append_warning("first_warning", "second_warning") == "first_warning|second_warning"


def test_visual_parse_policy_runtime_classifies_backend_missing_and_backend_unavailable() -> None:
    runtime = VisualParsePolicyRuntime()

    profile = runtime.classify_exception(
        "VisualTrack OCR backend is unavailable. Please install pymupdf and rapidocr_onnxruntime."
    )

    assert profile.visual_backend_missing is True
    assert profile.backend_unavailable is True
    assert profile.visual_pipeline_unusable is False
    assert profile.unsupported_file_type is False


def test_visual_parse_policy_runtime_resolves_required_visual_timeout_to_terminal_error() -> None:
    runtime = VisualParsePolicyRuntime()

    decision = runtime.resolve_timeout_fallback(
        file_name="report.pdf",
        parse_track="VisualTrack",
        parse_input_name="report.pdf",
        original_file_is_word=False,
        word_suffix=".pdf",
        parse_timeout_sec=90.0,
        visual_chain_required=True,
        nonpdf_total_budget_sec=None,
        elapsed_sec=0.0,
        nonpdf_guard_sec=2.0,
    )

    assert decision.terminal_status_code == 504
    assert "Required visual PDF chain timed out for report.pdf." in decision.terminal_detail
    assert decision.should_attempt_fasttrack_fallback is False


def test_visual_parse_policy_runtime_resolves_word_pdf_timeout_with_recovery_and_fallback_budget() -> None:
    runtime = VisualParsePolicyRuntime()

    decision = runtime.resolve_timeout_fallback(
        file_name="report.docx",
        parse_track="VisualTrack",
        parse_input_name="report.pdf",
        original_file_is_word=True,
        word_suffix=".docx",
        parse_timeout_sec=100.0,
        visual_chain_required=False,
        nonpdf_total_budget_sec=80.0,
        elapsed_sec=20.0,
        nonpdf_guard_sec=2.0,
    )

    assert decision.terminal_status_code is None
    assert decision.try_docx_native_recovery is True
    assert decision.docx_native_recovery_reason == "word_pdf_parse_timeout"
    assert decision.should_attempt_fasttrack_fallback is True
    assert decision.fallback_track == "VisualTrack->WordPdfFastTrackFallback"
    assert decision.fallback_hint == "word_pdf_parse_timeout_fallback_fasttrack"
    assert decision.fallback_context_label == "report.docx:FastTrackTimeoutFallback"
    assert decision.fallback_timeout_sec == 54.0


def test_visual_parse_policy_runtime_resolves_visual_error_to_docx_recovery_then_fasttrack_fallback() -> None:
    runtime = VisualParsePolicyRuntime()

    decision = runtime.resolve_exception_fallback(
        file_name="report.docx",
        parse_track="VisualTrack",
        parse_input_name="report.pdf",
        word_suffix=".docx",
        message="rapidocr_onnxruntime missing",
        visual_chain_required=False,
        visual_strict=False,
        disable_fasttrack_fallback=False,
    )

    assert decision.terminal_status_code is None
    assert decision.try_docx_native_recovery is True
    assert decision.docx_native_recovery_reason == "word_pdf_visual_error"
    assert decision.should_attempt_fasttrack_fallback is True
    assert decision.fallback_track == "VisualTrack->FastTrackFallback"
    assert decision.fallback_context_label == "report.docx:FastTrackFallback"
    assert (
        decision.fallback_warning
        == "VisualTrack OCR backend unavailable, auto-fallback to native FastTrack parsing."
    )


def test_visual_parse_policy_runtime_keeps_strict_visual_error_as_terminal_after_recovery_attempt() -> None:
    runtime = VisualParsePolicyRuntime()

    decision = runtime.resolve_exception_fallback(
        file_name="report.docx",
        parse_track="VisualTrack",
        parse_input_name="report.pdf",
        word_suffix=".docx",
        message="pymupdf import failed",
        visual_chain_required=False,
        visual_strict=True,
        disable_fasttrack_fallback=False,
    )

    assert decision.try_docx_native_recovery is True
    assert decision.should_attempt_fasttrack_fallback is False
    assert decision.terminal_status_code == 503
    assert "strict mode is enabled" in decision.terminal_detail


def test_visual_parse_policy_runtime_resolves_required_visual_error_without_recovery() -> None:
    runtime = VisualParsePolicyRuntime()

    decision = runtime.resolve_exception_fallback(
        file_name="report.docx",
        parse_track="VisualTrack",
        parse_input_name="report.pdf",
        word_suffix=".docx",
        message="mineru failed to produce a usable output",
        visual_chain_required=True,
        visual_strict=False,
        disable_fasttrack_fallback=False,
    )

    assert decision.try_docx_native_recovery is False
    assert decision.should_attempt_fasttrack_fallback is False
    assert decision.terminal_status_code == 503
    assert "Required visual PDF chain failed" in decision.terminal_detail
