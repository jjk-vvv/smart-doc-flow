from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.parser import NativeDocumentParser


def _build_parser() -> NativeDocumentParser:
    return NativeDocumentParser(max_pages=1)


def test_build_figure_from_visual_payload_recovers_title_and_series_headers() -> None:
    parser = _build_parser()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    figure = parser._build_figure_from_visual_payload(
        figure_id="pdf_mineru_gemini_f1",
        page_no=1,
        payload={
            "title": "近五年社会保障卡持卡情况",
            "caption": "",
            "type": "other",
            "legend": ["实体社保卡持卡人数", "电子社保卡领用人数"],
            "axes": {"x": "", "y": "亿人"},
            "dataframe": {
                "headers": ["??", "??", "??"],
                "rows": [
                    ["2018年", "12.3", "0.01"],
                    ["2019年", "13.1", "0.90"],
                ],
            },
            "confidence": 0.95,
        },
        item={
            "bbox": [100.0, 200.0, 900.0, 1100.0],
            "img_path": "artifacts/figure-1.png",
            "object_subtype": "chart",
            "source_object_type": "figure",
        },
        parts=parts,
        bbox_map=bbox_map,
        page_dims={1: (1000.0, 1400.0)},
    )

    assert figure is not None
    assert figure["title"] == "近五年社会保障卡持卡情况"
    assert figure["caption"] == "近五年社会保障卡持卡情况"
    assert figure["figure_type"] == "chart"
    assert figure["dataframe_source"] == "model"
    assert figure["dataframe"]["headers"] == ["年份", "实体社保卡持卡人数", "电子社保卡领用人数"]
    assert len(figure["dataframe"]["rows"]) == 2


def test_build_figure_from_visual_payload_drops_unit_only_noise() -> None:
    parser = _build_parser()

    figure = parser._build_figure_from_visual_payload(
        figure_id="pdf_mineru_gemini_f2",
        page_no=2,
        payload={
            "title": "",
            "caption": "",
            "type": "other",
            "text_blocks": ["单位：万人"],
            "insights": ["The unit of measurement is ten thousand people (万人)."],
            "confidence": 0.99,
        },
        item={
            "bbox": [50.0, 50.0, 300.0, 160.0],
            "img_path": "artifacts/figure-2.png",
            "object_subtype": "image",
            "source_object_type": "figure",
        },
        parts=[],
        bbox_map={},
        page_dims={2: (1000.0, 1400.0)},
    )

    assert figure is None


def test_merge_figure_blocks_drops_weak_semantic_duplicates() -> None:
    parser = _build_parser()

    rich_figure = {
        "figure_id": "pdf_mineru_gemini_f22",
        "page": 22,
        "title": "近五年社会保障卡持卡情况",
        "caption": "图 12 近五年社会保障卡持卡情况单位：亿人",
        "quality": 0.98,
        "key_points": ["实体社保卡持卡人数逐年增长"],
        "content_modes": ["dataframe"],
        "dataframe": {
            "headers": ["年份", "实体社保卡持卡人数", "电子社保卡领用人数"],
            "rows": [["2018年", "12.3", "0.01"]],
        },
        "topology": {"nodes": [], "edges": []},
    }
    weak_duplicate = {
        "figure_id": "pdf_mineru_gemini_f13",
        "page": 13,
        "title": "",
        "caption": "图 12 近五年社会保障卡持卡情况",
        "quality": 0.68,
        "key_points": [],
        "content_modes": ["visual"],
        "dataframe": {"headers": [], "rows": []},
        "topology": {"nodes": [], "edges": []},
    }

    merged = parser._merge_figure_blocks([], [rich_figure, weak_duplicate])

    assert len(merged) == 1
    assert merged[0]["figure_id"] == "pdf_mineru_gemini_f22"


def test_classify_pdf_visual_profile_prefers_ocr_for_scanned_pdf() -> None:
    parser = _build_parser()

    profile = parser._classify_pdf_visual_profile(
        file_name="scan-heavy.pdf",
        page_count=14,
        probe_pages=12,
        probe_chars=0,
        probe_text="",
        pdf_metadata_signals={"office_like": False},
    )

    assert profile["profile"] == "visual_scanned_pdf"
    assert profile["method"] == "ocr"
    assert profile["method_fallbacks"] == ["txt"]
