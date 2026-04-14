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


pdf_parse_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pdf", "pdf_parse_runtime.py"],
    "_smart_doc_flow_module2_pdf_parse_runtime",
)

PdfParseRuntime = pdf_parse_runtime_module.PdfParseRuntime


def test_pdf_parse_runtime_returns_visual_result_and_source_cache_patch() -> None:
    captured = {"native_called": False}

    def _parse_pdf_visual_first(**kwargs):
        captured["source_cache_identity"] = kwargs["source_cache_identity"]
        return ("visual_md", {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [])

    runtime = PdfParseRuntime(
        enable_mineru_layout=True,
        pipeline_mode="visual_first",
        visual_first_allow_legacy_fallback=True,
        parse_pdf_visual_first=_parse_pdf_visual_first,
        visual_backend_available=lambda: (True, ""),
        parse_pdf_native=lambda **kwargs: captured.update(native_called=True) or {},
        get_last_mineru_run_meta=lambda: {},
    )

    result = runtime.parse_pdf(
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        track="VisualTrack",
        reader=object(),
        total_pages=2,
        source_cache_identity="",
        source_file_name="source.docx",
        source_file_bytes=b"demo-docx",
        last_figure_blocks=[],
        parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
    )

    assert result["kind"] == "visual_result"
    assert result["result"][0] == "visual_md"
    assert result["stats_patch"] == {
        "source_cache_identity_applied": True,
        "source_cache_identity_file_name": "source.docx",
    }
    assert captured["source_cache_identity"] == hashlib.sha256(b"demo-docx").hexdigest()
    assert captured["native_called"] is False


def test_pdf_parse_runtime_seeds_content_hash_for_direct_pdf_upload() -> None:
    captured = {}

    def _parse_pdf_visual_first(**kwargs):
        captured["source_cache_identity"] = kwargs["source_cache_identity"]
        return ("visual_md", {}, [])

    runtime = PdfParseRuntime(
        enable_mineru_layout=True,
        pipeline_mode="visual_first",
        visual_first_allow_legacy_fallback=True,
        parse_pdf_visual_first=_parse_pdf_visual_first,
        visual_backend_available=lambda: (True, ""),
        parse_pdf_native=lambda **kwargs: {},
        get_last_mineru_run_meta=lambda: {},
    )

    result = runtime.parse_pdf(
        file_name="renamed-upload.pdf",
        file_bytes=b"%PDF-direct-upload",
        track="VisualTrack",
        reader=object(),
        total_pages=2,
        source_cache_identity="",
        source_file_name="",
        source_file_bytes=None,
        last_figure_blocks=[],
        parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
    )

    assert result["kind"] == "visual_result"
    assert result["stats_patch"] == {
        "source_cache_identity_applied": True,
        "source_cache_identity_file_name": "renamed-upload.pdf",
    }
    assert captured["source_cache_identity"] == hashlib.sha256(b"%PDF-direct-upload").hexdigest()


def test_pdf_parse_runtime_raises_when_visual_first_required_and_returns_none() -> None:
    runtime = PdfParseRuntime(
        enable_mineru_layout=True,
        pipeline_mode="visual_first",
        visual_first_allow_legacy_fallback=False,
        parse_pdf_visual_first=lambda **kwargs: None,
        visual_backend_available=lambda: (True, ""),
        parse_pdf_native=lambda **kwargs: {},
        get_last_mineru_run_meta=lambda: {},
    )

    try:
        runtime.parse_pdf(
            file_name="demo.pdf",
            file_bytes=b"%PDF",
            track="VisualTrack",
            reader=object(),
            total_pages=2,
            last_figure_blocks=[],
            parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
        )
    except ValueError as exc:
        assert str(exc) == "Visual-first pipeline returned no usable result."
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected ValueError when visual-first returns no result.")


def test_pdf_parse_runtime_reraises_visual_first_error_when_legacy_fallback_disabled() -> None:
    runtime = PdfParseRuntime(
        enable_mineru_layout=True,
        pipeline_mode="visual_first",
        visual_first_allow_legacy_fallback=False,
        parse_pdf_visual_first=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("visual boom")),
        visual_backend_available=lambda: (True, ""),
        parse_pdf_native=lambda **kwargs: {},
        get_last_mineru_run_meta=lambda: {"status": "fatal"},
    )

    try:
        runtime.parse_pdf(
            file_name="demo.pdf",
            file_bytes=b"%PDF",
            track="VisualTrack",
            reader=object(),
            total_pages=2,
            last_figure_blocks=[],
            parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
        )
    except RuntimeError as exc:
        assert str(exc) == "visual boom"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected RuntimeError when visual-first raises.")


def test_pdf_parse_runtime_merges_visual_fallback_stats_into_native_result() -> None:
    captured = {}
    long_error = "x" * 300

    runtime = PdfParseRuntime(
        enable_mineru_layout=True,
        pipeline_mode="hybrid",
        visual_first_allow_legacy_fallback=True,
        parse_pdf_visual_first=lambda **kwargs: None,
        visual_backend_available=lambda: (True, ""),
        parse_pdf_native=lambda **kwargs: captured.update(kwargs)
        or {
            "markdown": "native_md",
            "bbox_map": {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]},
            "table_blocks": [{"table_id": "native_t1"}],
            "figure_blocks": [{"figure_id": "native_f1"}],
            "stats": {"native_mode": True},
        },
        get_last_mineru_run_meta=lambda: {
            "status": "no_layout",
            "runtime_error": long_error,
        },
    )

    result = runtime.parse_pdf(
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        track="VisualTrack",
        reader=object(),
        total_pages=2,
        source_cache_identity="",
        source_file_name="",
        source_file_bytes=None,
        last_figure_blocks=[{"figure_id": "prev_f1"}],
        parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
    )

    assert result["kind"] == "native_result"
    assert result["result"][0] == "native_md"
    assert result["stats"] == {"native_mode": True}
    assert result["stats_patch"]["source_cache_identity_applied"] is True
    assert result["stats_patch"]["source_cache_identity_file_name"] == "demo.pdf"
    assert result["stats_patch"]["visual_first_fallback_reason"] == "no_layout"
    assert result["stats_patch"]["visual_first_runtime_error"] == long_error[:240]
    assert captured["visual_backend_ready"] is True
    assert captured["last_figure_blocks"] == [{"figure_id": "prev_f1"}]
    assert result["figure_blocks"] == [{"figure_id": "native_f1"}]


def test_pdf_parse_runtime_returns_native_early_result() -> None:
    runtime = PdfParseRuntime(
        enable_mineru_layout=False,
        pipeline_mode="hybrid",
        visual_first_allow_legacy_fallback=True,
        parse_pdf_visual_first=lambda **kwargs: None,
        visual_backend_available=lambda: (False, "missing"),
        parse_pdf_native=lambda **kwargs: {"early_result": ("ocr_fallback", {}, [])},
        get_last_mineru_run_meta=lambda: {},
    )

    result = runtime.parse_pdf(
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        track="FastTrack",
        reader=object(),
        total_pages=1,
        last_figure_blocks=[],
        parse_pdf_with_ocr=lambda file_bytes, page_count, cue_pages=None: ("ocr", {}, []),
    )

    assert result == {
        "kind": "native_early_result",
        "result": ("ocr_fallback", {}, []),
    }
