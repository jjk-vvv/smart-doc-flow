from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_nonpdf_entry_module = import_module("app.modules.module2.core.parsers.parser_bootstrap_runtime")
ParserNonPdfEntryRuntime = parser_nonpdf_entry_module.ParserNonPdfEntryRuntime


def test_parser_nonpdf_entry_runtime_parse_docx_applies_named_state() -> None:
    runtime = ParserNonPdfEntryRuntime()
    captured: dict[str, object] = {}

    class _FakeDocxDocumentRuntime:
        def parse_docx(self, file_bytes):
            captured["file_bytes"] = file_bytes
            return {"markdown": "docx", "bbox_map": {"r1": [1, 2, 3, 4]}, "table_blocks": [{"table_id": "t1"}]}

    def _build_named_runtime_state(runtime_result, **kwargs):
        captured["build_kwargs"] = dict(kwargs)
        captured["runtime_result"] = dict(runtime_result)
        return {"result": ("docx", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}])}

    result = runtime.parse_docx(
        docx_document_runtime=_FakeDocxDocumentRuntime(),
        file_bytes=b"docx",
        build_named_runtime_state=_build_named_runtime_state,
        apply_state_update=lambda state_update: state_update["result"],
    )

    assert result == ("docx", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}])
    assert captured["file_bytes"] == b"docx"
    assert captured["build_kwargs"] == {}


def test_parser_nonpdf_entry_runtime_parse_docx_relaxed_raises_when_state_empty() -> None:
    runtime = ParserNonPdfEntryRuntime()

    class _FakeDocxDocumentRuntime:
        def parse_docx_relaxed(self, file_bytes):
            return {"markdown": "docx-relaxed", "bbox_map": {}, "table_blocks": []}

    try:
        runtime.parse_docx_relaxed(
            docx_document_runtime=_FakeDocxDocumentRuntime(),
            file_bytes=b"docx",
            build_named_runtime_state=lambda runtime_result, **kwargs: {"result": None},
            apply_state_update=lambda state_update: state_update["result"],
        )
    except ValueError as exc:
        assert str(exc) == "Relaxed DOCX parse state update returned no result."
    else:
        raise AssertionError("expected relaxed docx parse to raise on empty state update")


def test_parser_nonpdf_entry_runtime_parse_xlsx_applies_zip_fallback_state() -> None:
    runtime = ParserNonPdfEntryRuntime()
    captured: dict[str, object] = {}

    class _FakeXlsxParseRuntime:
        def parse_xlsx(self, **kwargs):
            captured["parse_kwargs"] = dict(kwargs)
            return ("xlsx", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}], True)

    def _build_xlsx_state(**kwargs):
        captured["state_kwargs"] = dict(kwargs)
        return {"result": ("xlsx", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}])}

    result = runtime.parse_xlsx(
        xlsx_parse_runtime=_FakeXlsxParseRuntime(),
        file_bytes=b"xlsx",
        build_xlsx_state=_build_xlsx_state,
        apply_state_update=lambda state_update: state_update["result"],
    )

    assert result == ("xlsx", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}])
    assert captured["parse_kwargs"] == {"file_bytes": b"xlsx"}
    assert captured["state_kwargs"]["used_zip_fallback"] is True


def test_parser_nonpdf_entry_runtime_parse_image_excludes_stats() -> None:
    runtime = ParserNonPdfEntryRuntime()
    captured: dict[str, object] = {}

    class _FakeImageDocumentRuntime:
        def parse_image(self, **kwargs):
            captured["parse_kwargs"] = dict(kwargs)
            return {"markdown": "image", "bbox_map": {"r1": [1, 2, 3, 4]}, "table_blocks": []}

    def _build_named_runtime_state(runtime_result, **kwargs):
        captured["build_kwargs"] = dict(kwargs)
        return {"result": ("image", {"r1": [1, 2, 3, 4]}, [])}

    result = runtime.parse_image(
        image_document_runtime=_FakeImageDocumentRuntime(),
        file_name="demo.png",
        file_bytes=b"png",
        last_figure_blocks=[{"figure_id": "f0"}],
        build_named_runtime_state=_build_named_runtime_state,
        apply_state_update=lambda state_update: state_update["result"],
        enable_gemini_enhance=True,
    )

    assert result == ("image", {"r1": [1, 2, 3, 4]}, [])
    assert captured["parse_kwargs"]["last_figure_blocks"] == [{"figure_id": "f0"}]
    assert captured["parse_kwargs"]["enable_gemini_enhance"] is True
    assert captured["build_kwargs"] == {"include_stats": False}


def test_parser_nonpdf_entry_runtime_parse_plain_builds_merged_figure_state() -> None:
    runtime = ParserNonPdfEntryRuntime()
    captured: dict[str, object] = {}

    def _parse_plain_payload(file_bytes, ext, **kwargs):
        captured["plain_args"] = {"file_bytes": file_bytes, "ext": ext, **kwargs}
        return SimpleNamespace(
            markdown="plain",
            bbox_map={"r1": [1, 2, 3, 4]},
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[{"figure_id": "f1"}],
            text="plain text",
        )

    def _merge_figure_blocks(seed, figure_blocks):
        captured["merge_args"] = {"seed": list(seed), "figure_blocks": list(figure_blocks)}
        return [{"figure_id": "merged"}]

    def _build_plain_text_state(**kwargs):
        captured["state_kwargs"] = dict(kwargs)
        return {"result": ("plain", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}])}

    result = runtime.parse_plain(
        file_bytes=b"plain",
        ext=".md",
        table_max_rows=12,
        table_max_cols=8,
        nonpdf_figure_max=4,
        parse_plain_payload=_parse_plain_payload,
        build_header_meta=lambda headers: headers,
        decorate_rows_with_meta=lambda rows, headers: rows,
        looks_like_figure_cue_text=lambda text: "chart" in str(text).lower(),
        merge_figure_blocks=_merge_figure_blocks,
        build_plain_text_state=_build_plain_text_state,
        apply_state_update=lambda state_update: state_update["result"],
    )

    assert result == ("plain", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}])
    assert captured["plain_args"]["ext"] == ".md"
    assert captured["plain_args"]["table_max_rows"] == 12
    assert captured["merge_args"] == {"seed": [], "figure_blocks": [{"figure_id": "f1"}]}
    assert captured["state_kwargs"]["merged_figure_blocks"] == [{"figure_id": "merged"}]
