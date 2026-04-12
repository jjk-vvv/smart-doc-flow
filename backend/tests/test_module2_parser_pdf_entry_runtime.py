from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_pdf_entry_module = import_module("module2.app.core.parsers.parser_pdf_bootstrap_runtime")
ParserPdfEntryRuntime = parser_pdf_entry_module.ParserPdfEntryRuntime


class _FakeReader:
    def __init__(self, page_count: int) -> None:
        self.pages = [object()] * page_count


def test_parser_pdf_entry_runtime_prepares_reader_and_tracks_page_count() -> None:
    runtime = ParserPdfEntryRuntime()
    captured: dict[str, int] = {}

    reader, total_pages = runtime.prepare_pdf_reader(
        file_name="demo.pdf",
        file_bytes=b"%PDF-1.7",
        pdf_reader_factory=lambda payload: _FakeReader(3),
        set_runtime_page_count=lambda page_count: captured.setdefault("page_count", page_count),
    )

    assert isinstance(reader, _FakeReader)
    assert total_pages == 3
    assert captured["page_count"] == 3


def test_parser_pdf_entry_runtime_rejects_zero_page_pdf() -> None:
    runtime = ParserPdfEntryRuntime()

    try:
        runtime.prepare_pdf_reader(
            file_name="empty.pdf",
            file_bytes=b"%PDF-1.7",
            pdf_reader_factory=lambda payload: _FakeReader(0),
            set_runtime_page_count=lambda page_count: None,
        )
    except ValueError as exc:
        assert str(exc) == "PDF has no pages: empty.pdf"
    else:
        raise AssertionError("expected zero-page PDF to raise")


def test_parser_pdf_entry_runtime_parse_pdf_applies_state_update() -> None:
    runtime = ParserPdfEntryRuntime()
    captured: dict[str, object] = {}

    class _FakePdfParseRuntime:
        def parse_pdf(self, **kwargs):
            captured["parse_pdf_kwargs"] = dict(kwargs)
            return {"kind": "native_result", "result": ("runtime", {}, [])}

    def _build_pdf_runtime_state(**kwargs):
        captured["build_pdf_runtime_state_kwargs"] = dict(kwargs)
        return {
            "stats": {"native": True},
            "figure_blocks": [{"id": "figure-1"}],
            "result": ("markdown", {"ref-1": [1, 2, 3, 4]}, [{"table_id": "table-1"}]),
        }

    def _apply_state_update(state_update):
        captured["state_update"] = dict(state_update)
        return state_update["result"]

    result = runtime.parse_pdf(
        file_name="demo.pdf",
        file_bytes=b"%PDF-1.7",
        track="accurate",
        pdf_reader_factory=lambda payload: _FakeReader(2),
        set_runtime_page_count=lambda page_count: captured.setdefault("page_count", page_count),
        pdf_parse_runtime=_FakePdfParseRuntime(),
        source_file_name="source.docx",
        source_file_bytes=b"source",
        source_cache_identity="cache-key",
        last_figure_blocks=[{"id": "seed"}],
        parse_pdf_with_ocr=lambda **kwargs: ("ocr", {}, []),
        current_stats={"existing": True},
        build_pdf_runtime_state=_build_pdf_runtime_state,
        apply_state_update=_apply_state_update,
    )

    assert result == ("markdown", {"ref-1": [1, 2, 3, 4]}, [{"table_id": "table-1"}])
    assert captured["page_count"] == 2
    parse_pdf_kwargs = captured["parse_pdf_kwargs"]
    assert parse_pdf_kwargs["total_pages"] == 2
    assert parse_pdf_kwargs["source_file_name"] == "source.docx"
    assert parse_pdf_kwargs["source_cache_identity"] == "cache-key"
    assert parse_pdf_kwargs["last_figure_blocks"] == [{"id": "seed"}]
    assert captured["build_pdf_runtime_state_kwargs"]["current_stats"] == {"existing": True}
    assert captured["state_update"]["figure_blocks"] == [{"id": "figure-1"}]


def test_parser_pdf_entry_runtime_parse_pdf_refreshes_visual_stats_before_state_update() -> None:
    runtime = ParserPdfEntryRuntime()
    captured: dict[str, object] = {}
    latest_stats = {"existing": True}

    class _FakePdfParseRuntime:
        def parse_pdf(self, **kwargs):
            latest_stats.clear()
            latest_stats.update({"pipeline": "visual_first", "chain_status": "success"})
            return {
                "kind": "visual_result",
                "result": ("visual", {}, []),
                "stats_patch": {"source_cache_identity_applied": True},
            }

    def _build_pdf_runtime_state(**kwargs):
        captured["build_pdf_runtime_state_kwargs"] = dict(kwargs)
        return {
            "stats": dict(kwargs["current_stats"]),
            "figure_blocks": [],
            "result": ("visual", {}, []),
        }

    result = runtime.parse_pdf(
        file_name="demo.pdf",
        file_bytes=b"%PDF-1.7",
        track="VisualTrack",
        pdf_reader_factory=lambda payload: _FakeReader(1),
        set_runtime_page_count=lambda page_count: None,
        pdf_parse_runtime=_FakePdfParseRuntime(),
        last_figure_blocks=[],
        parse_pdf_with_ocr=lambda **kwargs: ("ocr", {}, []),
        current_stats={"existing": True},
        get_current_stats=lambda: latest_stats,
        build_pdf_runtime_state=_build_pdf_runtime_state,
        apply_state_update=lambda state_update: state_update["result"],
    )

    assert result == ("visual", {}, [])
    assert captured["build_pdf_runtime_state_kwargs"]["current_stats"] == {
        "pipeline": "visual_first",
        "chain_status": "success",
    }


def test_parser_pdf_entry_runtime_parse_pdf_visual_first_updates_mineru_meta() -> None:
    runtime = ParserPdfEntryRuntime()
    captured: dict[str, object] = {}

    class _FakePdfVisualParseRuntime:
        def parse_pdf_visual_first(self, **kwargs):
            captured["parse_pdf_visual_first_kwargs"] = dict(kwargs)
            return {
                "mineru_run_meta": {"status": "ok", "pages": 2},
                "outcome": {"result": ("visual", {}, []), "stats": {"mode": "visual"}},
            }

    def _set_last_mineru_run_meta(meta):
        captured["mineru_run_meta"] = dict(meta or {})

    def _build_visual_parse_state(outcome):
        captured["visual_outcome"] = dict(outcome)
        return {"result": ("visual", {}, []), "stats": {"mode": "visual"}, "figure_blocks": []}

    def _apply_state_update(state_update):
        captured["state_update"] = dict(state_update)
        return state_update["result"]

    result = runtime.parse_pdf_visual_first(
        pdf_visual_parse_runtime=_FakePdfVisualParseRuntime(),
        file_name="demo.pdf",
        file_bytes=b"%PDF-1.7",
        reader=_FakeReader(2),
        page_count=2,
        layout_extractor=object(),
        vision=object(),
        set_last_mineru_run_meta=_set_last_mineru_run_meta,
        build_visual_parse_state=_build_visual_parse_state,
        apply_state_update=_apply_state_update,
        source_cache_identity="cache-key",
        source_file_name="source.docx",
        source_file_bytes=b"source",
    )

    assert result == ("visual", {}, [])
    assert captured["mineru_run_meta"] == {"status": "ok", "pages": 2}
    assert captured["visual_outcome"] == {"result": ("visual", {}, []), "stats": {"mode": "visual"}}
    assert captured["parse_pdf_visual_first_kwargs"]["page_count"] == 2


def test_parser_pdf_entry_runtime_parse_pdf_with_ocr_tracks_figure_blocks() -> None:
    runtime = ParserPdfEntryRuntime()
    captured: dict[str, object] = {}

    class _FakePdfOcrRuntime:
        def parse_pdf_with_ocr(self, **kwargs):
            captured["parse_pdf_with_ocr_kwargs"] = dict(kwargs)
            return ("ocr-markdown", {"ref-1": [1, 2, 3, 4]}, [{"table_id": "table-1"}], [{"figure_id": "figure-1"}])

    def _set_last_figure_blocks(figure_blocks):
        captured["figure_blocks"] = list(figure_blocks or [])

    result = runtime.parse_pdf_with_ocr(
        pdf_ocr_runtime=_FakePdfOcrRuntime(),
        file_bytes=b"%PDF-1.7",
        page_count=4,
        set_last_figure_blocks=_set_last_figure_blocks,
        cue_pages=[2, 3],
    )

    assert result == ("ocr-markdown", {"ref-1": [1, 2, 3, 4]}, [{"table_id": "table-1"}])
    assert captured["figure_blocks"] == [{"figure_id": "figure-1"}]
    assert captured["parse_pdf_with_ocr_kwargs"]["cue_pages"] == [2, 3]
