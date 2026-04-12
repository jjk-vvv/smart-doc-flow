from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))


def _load_parser_module():
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)
    return importlib.import_module("app.core.parsers.native_document_parser")


parser_module = _load_parser_module()


def test_parse_document_in_subprocess_applies_word_pdf_context_and_chart_merge(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeParser:
        def __init__(self) -> None:
            self.word_pdf_parse_use_source_signals = True
            self.word_pdf_docx_chart_xml_merge_enable = True
            self._last_parse_stats: dict[str, object] = {"native": True}
            self._last_figure_blocks = [{"figure_id": "before_merge"}]

        def parse_document(self, **kwargs):
            captured["parse_kwargs"] = kwargs
            return "markdown", {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}]

        def _overlay_last_parse_stats(self, stats_patch):
            self._last_parse_stats.update(dict(stats_patch or {}))

        def _merge_docx_chart_xml_into_pdf_figures(self, *, file_bytes: bytes) -> None:
            captured["merge_file_bytes"] = file_bytes
            self._last_parse_stats["chart_runtime_called"] = True
            self._last_figure_blocks = [{"figure_id": "after_merge"}]

        def get_last_figure_blocks(self):
            return list(self._last_figure_blocks)

        def get_last_parse_stats(self):
            return dict(self._last_parse_stats)

    monkeypatch.setattr(parser_module, "NativeDocumentParser", _FakeParser)

    markdown, bbox_map, table_blocks, figure_blocks, parse_stats = parser_module.parse_document_in_subprocess(
        file_bytes=b"%PDF-1.4 fake",
        file_name="report.pdf",
        track="VisualTrack",
        source_file_name="report.docx",
        source_file_bytes=b"docx-bytes",
    )

    assert markdown == "markdown"
    assert bbox_map == {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]}
    assert table_blocks == [{"table_id": "t1"}]
    assert figure_blocks == [{"figure_id": "after_merge"}]
    assert captured["merge_file_bytes"] == b"docx-bytes"
    assert captured["parse_kwargs"] == {
        "file_name": "report.pdf",
        "file_bytes": b"%PDF-1.4 fake",
        "track": "VisualTrack",
        "source_file_name": "report.docx",
        "source_file_bytes": b"docx-bytes",
        "source_cache_identity": hashlib.sha256(b"docx-bytes").hexdigest(),
    }
    assert parse_stats["word_pdf_parse_use_source_signals"] is True
    assert parse_stats["word_pdf_parse_source_signals_applied"] is True
    assert parse_stats["word_pdf_parse_source_cache_identity_seeded"] is True
    assert parse_stats["word_pdf_docx_chart_xml_merge_enabled"] is True
    assert parse_stats["source_cache_identity_applied"] is True
    assert parse_stats["source_cache_identity_file_name"] == "report.docx"
    assert parse_stats["docx_source_chart_merge_applied"] is True
    assert parse_stats["docx_source_file_name"] == "report.docx"
    assert parse_stats["chart_runtime_called"] is True


def test_parse_document_in_subprocess_skips_word_pdf_merge_for_non_docx_source(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeParser:
        def __init__(self) -> None:
            self.word_pdf_parse_use_source_signals = True
            self.word_pdf_docx_chart_xml_merge_enable = True
            self._last_parse_stats: dict[str, object] = {}
            self._last_figure_blocks = []

        def parse_document(self, **kwargs):
            captured["parse_kwargs"] = kwargs
            return "markdown", {}, []

        def _overlay_last_parse_stats(self, stats_patch):
            self._last_parse_stats.update(dict(stats_patch or {}))

        def _merge_docx_chart_xml_into_pdf_figures(self, *, file_bytes: bytes) -> None:
            raise AssertionError("chart merge should not run for non-docx source")

        def get_last_figure_blocks(self):
            return list(self._last_figure_blocks)

        def get_last_parse_stats(self):
            return dict(self._last_parse_stats)

    monkeypatch.setattr(parser_module, "NativeDocumentParser", _FakeParser)

    _, _, _, _, parse_stats = parser_module.parse_document_in_subprocess(
        file_bytes=b"%PDF-1.4 fake",
        file_name="report.pdf",
        track="VisualTrack",
        source_file_name="report.txt",
        source_file_bytes=b"plain-text",
    )

    assert captured["parse_kwargs"] == {
        "file_name": "report.pdf",
        "file_bytes": b"%PDF-1.4 fake",
        "track": "VisualTrack",
        "source_file_name": None,
        "source_file_bytes": None,
        "source_cache_identity": "",
    }
    assert parse_stats["word_pdf_parse_source_signals_applied"] is False
    assert parse_stats["word_pdf_parse_source_cache_identity_seeded"] is False
    assert "docx_source_chart_merge_applied" not in parse_stats
