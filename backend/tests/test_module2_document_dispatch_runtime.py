from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


document_dispatch_runtime_module = import_module("module2.app.core.parsers.parser_docx_bootstrap_runtime")

DocumentDispatchRuntime = document_dispatch_runtime_module.DocumentDispatchRuntime


def _build_runtime(**overrides) -> DocumentDispatchRuntime:
    config = {
        "word_parse_via_pdf": True,
        "office_convert_enabled": True,
        "word_convert_allow_native_fallback": True,
        "text_extensions": {".txt", ".md"},
        "image_extensions": {".png", ".jpg"},
        "parse_pdf": lambda *args, **kwargs: ("pdf", {}, []),
        "parse_docx_via_pdf": lambda **kwargs: ("docx_pdf", {}, []),
        "parse_docx": lambda file_bytes: ("docx_native", {}, []),
        "parse_xlsx": lambda file_bytes: ("xlsx", {}, []),
        "parse_plain": lambda file_bytes, ext=".txt": (f"plain:{ext}", {}, []),
        "parse_image": lambda file_name, file_bytes: ("image", {}, []),
    }
    config.update(overrides)
    return DocumentDispatchRuntime(**config)


def test_document_dispatch_runtime_routes_pdf_with_source_metadata() -> None:
    captured: dict[str, object] = {}
    runtime = _build_runtime(
        parse_pdf=lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs) or ("pdf", {}, [])
    )

    result = runtime.parse_document(
        file_name="demo.pdf",
        file_bytes=b"%PDF",
        track="VisualTrack",
        source_file_name="source.docx",
        source_file_bytes=b"docx",
        source_cache_identity="hash",
    )

    assert result["result"][0] == "pdf"
    assert captured["args"] == ("demo.pdf", b"%PDF", "VisualTrack")
    assert captured["kwargs"] == {
        "source_file_name": "source.docx",
        "source_file_bytes": b"docx",
        "source_cache_identity": "hash",
    }


def test_document_dispatch_runtime_falls_back_to_native_docx_with_stats_patch() -> None:
    runtime = _build_runtime(
        parse_docx_via_pdf=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("convert failed")),
        parse_docx=lambda file_bytes: ("docx_native", {}, []),
    )

    result = runtime.parse_document(
        file_name="demo.docx",
        file_bytes=b"docx",
        track="FastTrack",
    )

    assert result["result"][0] == "docx_native"
    assert result["stats_patch"]["docx_pdf_conversion_failed"] is True
    assert result["stats_patch"]["docx_pdf_native_fallback"] is True
    assert "RuntimeError: convert failed" in result["stats_patch"]["docx_pdf_conversion_error"]


def test_document_dispatch_runtime_marks_forced_native_docx_track() -> None:
    runtime = _build_runtime()

    result = runtime.parse_document(
        file_name="demo.docx",
        file_bytes=b"docx",
        track="docx_native",
    )

    assert result["result"][0] == "docx_native"
    assert result["stats_patch"] == {
        "docx_native_forced": True,
        "docx_native_forced_track": "docx_native",
    }


def test_document_dispatch_runtime_raises_when_docx_pdf_route_fails_without_fallback() -> None:
    runtime = _build_runtime(
        word_convert_allow_native_fallback=False,
        parse_docx_via_pdf=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("convert failed")),
    )

    with pytest.raises(ValueError, match=r"DOCX->PDF parse route failed for demo\.docx: RuntimeError: convert failed"):
        runtime.parse_document(
            file_name="demo.docx",
            file_bytes=b"docx",
            track="FastTrack",
        )


def test_document_dispatch_runtime_routes_text_image_and_xlsx() -> None:
    runtime = _build_runtime()

    assert runtime.parse_document(file_name="demo.txt", file_bytes=b"text")["result"][0] == "plain:.txt"
    assert runtime.parse_document(file_name="demo.png", file_bytes=b"img")["result"][0] == "image"
    assert runtime.parse_document(file_name="demo.xlsx", file_bytes=b"xlsx")["result"][0] == "xlsx"


def test_document_dispatch_runtime_rejects_unknown_extension() -> None:
    runtime = _build_runtime()

    with pytest.raises(ValueError, match="Unsupported file type: .bin"):
        runtime.parse_document(file_name="demo.bin", file_bytes=b"bin")
