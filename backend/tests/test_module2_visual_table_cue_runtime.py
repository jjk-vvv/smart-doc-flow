from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


visual_table_cue_module = import_module("module2.app.core.visual.visual_planning_runtime")

VisualTableCueRuntime = visual_table_cue_module.VisualTableCueRuntime


class _FakePage:
    def __init__(self, text: str, *, broken: bool = False) -> None:
        self._text = text
        self._broken = broken

    def extract_text(self) -> str:
        if self._broken:
            raise RuntimeError("extract failed")
        return self._text


class _FakeReader:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


def _build_runtime(*, cue_max_pages: int = 3) -> VisualTableCueRuntime:
    return VisualTableCueRuntime(
        ocr_cue_max_pages=cue_max_pages,
        visual_weak_table_min=4,
        visual_weak_table_quality=0.35,
        normalize_text=lambda text: " ".join(str(text or "").split()),
    )


def test_visual_table_cue_runtime_detects_table_cue_text() -> None:
    assert VisualTableCueRuntime.looks_like_table_cue_text("Table 2 Revenue by Year") is True
    assert VisualTableCueRuntime.looks_like_table_cue_text("附表A 数据汇总") is True
    assert VisualTableCueRuntime.looks_like_table_cue_text("Narrative paragraph only") is False


def test_visual_table_cue_runtime_collects_and_samples_cue_pages() -> None:
    runtime = _build_runtime(cue_max_pages=3)
    reader = _FakeReader(
        [
            _FakePage("Table 1 summary"),
            _FakePage("narrative"),
            _FakePage("Appendix table"),
            _FakePage("Table 4 data"),
            _FakePage("Table 5 data"),
        ]
    )

    result = runtime.collect_table_cue_pages(reader, page_count=5)

    assert result == [0, 3, 4]


def test_visual_table_cue_runtime_handles_empty_tables_with_cues_as_weak() -> None:
    runtime = _build_runtime()

    result = runtime.is_weak_native_table_result([], [0, 1])

    assert result is True


def test_visual_table_cue_runtime_marks_low_quality_fitz_tables_as_weak() -> None:
    runtime = _build_runtime()

    result = runtime.is_weak_native_table_result(
        [
            {"source": "pdf_fitz", "quality": 0.2},
            {"source": "pdf_fitz", "quality": 0.3},
        ],
        list(range(8)),
    )

    assert result is True


def test_visual_table_cue_runtime_keeps_stronger_non_fitz_tables() -> None:
    runtime = _build_runtime()

    result = runtime.is_weak_native_table_result(
        [
            {"source": "pdf_native", "quality": 0.9},
            {"source": "pdf_native", "quality": 0.8},
            {"source": "pdf_native", "quality": 0.85},
            {"source": "pdf_native", "quality": 0.88},
        ],
        list(range(8)),
    )

    assert result is False
