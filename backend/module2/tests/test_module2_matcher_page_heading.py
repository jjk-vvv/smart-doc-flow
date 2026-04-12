from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.matcher import Assistant1Matcher, _Candidate
from app.assistant_1.bundle_builder import Assistant1BundleBuilder
from app.assistant_1.models import ContentItem, LoadedSources, VisualFigure, VisualTable, DocumentSourceBundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_content_item(
    item_id: str,
    item_type: str = "image",
    page_no: int = 1,
    img_path: str = "",
    image_caption: str = "",
    image_footnote: str = "",
) -> ContentItem:
    return ContentItem(
        item_id=item_id,
        item_type=item_type,
        page_no=page_no,
        img_path=img_path,
        image_caption=image_caption,
        image_footnote=image_footnote,
    )


def _make_table(
    object_id: str,
    page_no: int = 1,
    image_path: str = "",
    caption: str = "",
    title: str = "",
) -> VisualTable:
    return VisualTable(
        object_id=object_id,
        page_no=page_no,
        image_path=image_path,
        caption=caption,
        title=title,
    )


def _make_figure(
    object_id: str,
    page_no: int = 1,
    image_path: str = "",
    caption: str = "",
    title: str = "",
) -> VisualFigure:
    return VisualFigure(
        object_id=object_id,
        page_no=page_no,
        image_path=image_path,
        caption=caption,
        title=title,
    )


def _make_loaded_sources(
    content_items: list[ContentItem],
    tables: list[VisualTable] | None = None,
    figures: list[VisualFigure] | None = None,
) -> LoadedSources:
    return LoadedSources(
        source_bundle=DocumentSourceBundle(file_hash="testhash"),
        content_items=content_items,
        tables=tables or [],
        figures=figures or [],
    )


def _candidate(
    object_id: str = "t1",
    kind: str = "table",
    page_no: int = 1,
    image_key: str = "",
    caption: str = "",
    nearby_heading: str = "",
) -> _Candidate:
    return _Candidate(
        kind=kind,
        object_id=object_id,
        page_no=page_no,
        image_key=image_key,
        bbox_raw=[],
        caption=caption,
        nearby_heading=nearby_heading,
    )


# ---------------------------------------------------------------------------
# Fix 4: Matcher scoring tests
# ---------------------------------------------------------------------------

class TestMatcherPageHeadingScoring:
    def test_exact_image_basename_still_scores_high(self) -> None:
        """Image basename match alone should yield score >= 0.78 (exact)."""
        matcher = Assistant1Matcher()
        # normalize_image_key returns the filename including extension as lowercase
        item = _make_content_item("c1", img_path="imgs/table_001.png", page_no=3)
        cand = _candidate(image_key="table_001.png", page_no=3)  # normalize_image_key includes extension
        score, reasons = matcher._score(item, cand)
        assert score >= 0.78
        assert any("image basename" in r for r in reasons)

    def test_same_page_gives_015_credit(self) -> None:
        """Same page without image basename match → 0.15 credit."""
        matcher = Assistant1Matcher()
        item = _make_content_item("c1", img_path="", page_no=5)
        cand = _candidate(page_no=5)
        score, reasons = matcher._score(item, cand)
        assert abs(score - 0.15) < 0.01
        assert any("same page" in r for r in reasons)

    def test_adjacent_page_gives_007_credit(self) -> None:
        """Adjacent page (distance=1) should yield 0.07 credit."""
        matcher = Assistant1Matcher()
        item = _make_content_item("c1", img_path="", page_no=4)
        cand = _candidate(page_no=5)
        score, reasons = matcher._score(item, cand)
        assert abs(score - 0.07) < 0.01
        assert any("adjacent page" in r for r in reasons)

    def test_same_page_plus_heading_reaches_probable_threshold(self) -> None:
        """Same page + heading similarity should push score >= 0.45 (probable)."""
        matcher = Assistant1Matcher()
        item = _make_content_item("c1", img_path="", page_no=2, image_caption="年度统计汇总")
        cand = _candidate(page_no=2, nearby_heading="年度统计汇总")
        score, _ = matcher._score(item, cand)
        # Allow for floating-point imprecision: 0.15 + 0.30 = 0.45 may be 0.4499... in float
        assert score >= 0.44, f"Expected score near 0.45, got {score}"

    def test_match_result_resolves_same_page_heading(self) -> None:
        """Items with same page + heading match should be matched, not image_unresolved."""
        matcher = Assistant1Matcher()
        item = _make_content_item("c1", item_type="table", page_no=2, img_path="", image_caption="年度统计汇总")
        table = _make_table("t1", page_no=2, image_path="", caption="", title="年度统计汇总")
        assignments, unmatched_content, _ = matcher.match([item], [table], [])
        assert "c1" not in unmatched_content, "Item should have been matched, not left as image_unresolved"


class TestBundleBuilderImageUnresolved:
    def test_image_unresolved_content_includes_page_number(self) -> None:
        """image_unresolved blocks must include page number in content."""
        builder = Assistant1BundleBuilder()
        item = _make_content_item("c1", item_type="image", page_no=7, img_path="x.png", image_caption="")
        loaded = _make_loaded_sources([item], tables=[], figures=[])
        bundle = builder.build(loaded)
        unresolved = [b for b in bundle.blocks if b.kind == "image_unresolved"]
        assert len(unresolved) == 1
        assert "page 7" in unresolved[0].content

    def test_image_unresolved_content_preserves_caption_with_page(self) -> None:
        """When caption exists, content should include both caption and page number."""
        builder = Assistant1BundleBuilder()
        item = _make_content_item("c1", item_type="image", page_no=3, img_path="x.png", image_caption="总体趋势图")
        loaded = _make_loaded_sources([item], tables=[], figures=[])
        bundle = builder.build(loaded)
        unresolved = [b for b in bundle.blocks if b.kind == "image_unresolved"]
        assert len(unresolved) == 1
        assert "总体趋势图" in unresolved[0].content
        assert "page 3" in unresolved[0].content

