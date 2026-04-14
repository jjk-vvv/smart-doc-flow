from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_docx_pdf_entry_module = import_module("app.modules.module2.core.parsers.parser_docx_bootstrap_runtime")
ParserDocxPdfEntryRuntime = parser_docx_pdf_entry_module.ParserDocxPdfEntryRuntime


def test_parser_docx_pdf_entry_runtime_parse_docx_via_pdf_applies_stats_and_chart_merge() -> None:
    runtime = ParserDocxPdfEntryRuntime()
    overlays: list[dict[str, object]] = []
    state = {
        "figure_blocks": [{"figure_id": "seed"}],
        "set_calls": [],
        "docx_via_pdf_calls": [],
        "docx_chart_merge_calls": [],
    }

    class _FakeDocxViaPdfRuntime:
        def parse_docx_via_pdf(self, **kwargs):
            state["docx_via_pdf_calls"].append(dict(kwargs))
            return {
                "markdown": "markdown",
                "bbox_map": {"r1": [1, 2, 3, 4]},
                "table_blocks": [{"table_id": "t1"}],
                "stats_patch": {"word_via_pdf": True},
            }

    class _FakeDocxChartMergeRuntime:
        def merge_docx_chart_xml_into_pdf_figures(self, **kwargs):
            state["docx_chart_merge_calls"].append(dict(kwargs))
            return {
                "figure_blocks": [{"figure_id": "merged"}],
                "stats_patch": {"docx_chart_xml_merged": 1},
            }

    result = runtime.parse_docx_via_pdf(
        docx_via_pdf_runtime=_FakeDocxViaPdfRuntime(),
        docx_chart_merge_runtime=_FakeDocxChartMergeRuntime(),
        file_name="report.docx",
        file_bytes=b"docx-bytes",
        word_pdf_docx_chart_xml_merge_enable=True,
        overlay_last_parse_stats=lambda patch: overlays.append(dict(patch or {})),
        peek_last_figure_blocks=lambda: list(state["figure_blocks"]),
        set_last_figure_blocks=lambda figure_blocks: state["set_calls"].append(list(figure_blocks)),
    )

    assert result == ("markdown", {"r1": [1, 2, 3, 4]}, [{"table_id": "t1"}])
    assert state["docx_via_pdf_calls"] == [{"file_name": "report.docx", "file_bytes": b"docx-bytes"}]
    assert state["docx_chart_merge_calls"] == [{"file_bytes": b"docx-bytes", "figure_blocks": [{"figure_id": "seed"}]}]
    assert state["set_calls"] == [[{"figure_id": "merged"}]]
    assert overlays[0] == {"word_via_pdf": True}
    assert overlays[1] == {"docx_chart_xml_merged": 1}
    assert overlays[2]["docx_source_chart_merge_applied"] is True
    assert overlays[2]["docx_source_file_name"] == "report.docx"


def test_parser_docx_pdf_entry_runtime_parse_docx_via_pdf_can_skip_chart_merge() -> None:
    runtime = ParserDocxPdfEntryRuntime()
    overlays: list[dict[str, object]] = []
    state = {"chart_merge_calls": 0}

    class _FakeDocxViaPdfRuntime:
        def parse_docx_via_pdf(self, **kwargs):
            return {
                "markdown": "markdown",
                "bbox_map": {},
                "table_blocks": [],
                "stats_patch": {"word_via_pdf": True},
            }

    class _FakeDocxChartMergeRuntime:
        def merge_docx_chart_xml_into_pdf_figures(self, **kwargs):
            state["chart_merge_calls"] += 1
            return {"figure_blocks": [], "stats_patch": {}}

    result = runtime.parse_docx_via_pdf(
        docx_via_pdf_runtime=_FakeDocxViaPdfRuntime(),
        docx_chart_merge_runtime=_FakeDocxChartMergeRuntime(),
        file_name="report.docx",
        file_bytes=b"docx-bytes",
        word_pdf_docx_chart_xml_merge_enable=False,
        overlay_last_parse_stats=lambda patch: overlays.append(dict(patch or {})),
        peek_last_figure_blocks=lambda: [],
        set_last_figure_blocks=lambda figure_blocks: None,
    )

    assert result == ("markdown", {}, [])
    assert state["chart_merge_calls"] == 0
    assert overlays[0] == {"word_via_pdf": True}
    assert overlays[1] == {
        "docx_source_chart_merge_applied": False,
        "docx_source_chart_merge_skipped": True,
        "docx_source_chart_merge_ms": 0,
        "docx_source_file_name": "report.docx",
    }


def test_parser_docx_pdf_entry_runtime_merge_docx_chart_xml_into_pdf_figures_updates_state() -> None:
    runtime = ParserDocxPdfEntryRuntime()
    overlays: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    class _FakeDocxChartMergeRuntime:
        def merge_docx_chart_xml_into_pdf_figures(self, **kwargs):
            captured["merge_kwargs"] = dict(kwargs)
            return {
                "figure_blocks": [{"figure_id": "merged"}],
                "stats_patch": {"docx_chart_xml_merged": 2},
            }

    result_state: dict[str, object] = {}
    runtime.merge_docx_chart_xml_into_pdf_figures(
        docx_chart_merge_runtime=_FakeDocxChartMergeRuntime(),
        file_bytes=b"docx-bytes",
        overlay_last_parse_stats=lambda patch: overlays.append(dict(patch or {})),
        peek_last_figure_blocks=lambda: [{"figure_id": "seed"}],
        set_last_figure_blocks=lambda figure_blocks: result_state.setdefault("figure_blocks", list(figure_blocks)),
    )

    assert captured["merge_kwargs"] == {"file_bytes": b"docx-bytes", "figure_blocks": [{"figure_id": "seed"}]}
    assert result_state["figure_blocks"] == [{"figure_id": "merged"}]
    assert overlays == [{"docx_chart_xml_merged": 2}]
