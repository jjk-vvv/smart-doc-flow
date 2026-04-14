from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_dispatch_bundle_runtime_module = import_module("app.modules.module2.core.parsers.parser_docx_bootstrap_runtime")

ParserDispatchBundleRuntime = parser_dispatch_bundle_runtime_module.ParserDispatchBundleRuntime


def test_parser_dispatch_bundle_runtime_builds_docx_via_pdf_kwargs() -> None:
    runtime = ParserDispatchBundleRuntime()

    convert_word_bytes_to_pdf = lambda **kwargs: (b"%PDF", {"converter": "libreoffice"})
    parse_pdf = lambda *args, **kwargs: ("markdown", {}, [])

    kwargs = runtime.build_docx_via_pdf_kwargs(
        word_pdf_timeout_sec=180,
        word_pdf_parse_use_source_signals=True,
        word_pdf_docx_chart_xml_merge_enable=True,
        convert_word_bytes_to_pdf=convert_word_bytes_to_pdf,
        parse_pdf=parse_pdf,
    )

    assert kwargs["word_pdf_timeout_sec"] == 180
    assert kwargs["word_pdf_parse_use_source_signals"] is True
    assert kwargs["word_pdf_docx_chart_xml_merge_enable"] is True
    assert kwargs["convert_word_bytes_to_pdf"]() == (b"%PDF", {"converter": "libreoffice"})
    assert kwargs["parse_pdf"]() == ("markdown", {}, [])


def test_parser_dispatch_bundle_runtime_builds_document_dispatch_kwargs() -> None:
    runtime = ParserDispatchBundleRuntime()

    parse_pdf = lambda *args, **kwargs: ("pdf", {}, [])
    parse_docx_via_pdf = lambda *args, **kwargs: {"markdown": "docx-via-pdf"}
    parse_docx = lambda *args, **kwargs: ("docx", {}, [])
    parse_xlsx = lambda *args, **kwargs: ("xlsx", {}, [])
    parse_plain = lambda *args, **kwargs: ("plain", {}, [])
    parse_image = lambda *args, **kwargs: ("image", {}, [])

    kwargs = runtime.build_document_dispatch_kwargs(
        word_parse_via_pdf=True,
        office_convert_enabled=True,
        word_convert_allow_native_fallback=True,
        text_extensions={".txt", ".md"},
        image_extensions={".png", ".jpg"},
        parse_pdf=parse_pdf,
        parse_docx_via_pdf=parse_docx_via_pdf,
        parse_docx=parse_docx,
        parse_xlsx=parse_xlsx,
        parse_plain=parse_plain,
        parse_image=parse_image,
    )

    assert kwargs["word_parse_via_pdf"] is True
    assert kwargs["office_convert_enabled"] is True
    assert kwargs["word_convert_allow_native_fallback"] is True
    assert kwargs["text_extensions"] == {".txt", ".md"}
    assert kwargs["image_extensions"] == {".png", ".jpg"}
    assert kwargs["parse_pdf"]() == ("pdf", {}, [])
    assert kwargs["parse_docx_via_pdf"]() == {"markdown": "docx-via-pdf"}
    assert kwargs["parse_docx"]() == ("docx", {}, [])
    assert kwargs["parse_xlsx"]() == ("xlsx", {}, [])
    assert kwargs["parse_plain"]() == ("plain", {}, [])
    assert kwargs["parse_image"]() == ("image", {}, [])
