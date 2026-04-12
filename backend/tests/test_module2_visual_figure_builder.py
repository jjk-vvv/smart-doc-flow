from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any


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


visual_payload_builder_module = _load_module(
    ["module2", "app", "core", "visual", "visual_payload_builder.py"],
    "_smart_doc_flow_module2_visual_payload_builder_for_figure_tests",
)

VisualFigureBuilderRuntime = visual_payload_builder_module.VisualFigureBuilderRuntime


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _safe_text_list(values: Any, max_items: int = 8, max_len: int = 180) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values[:max_items]:
        text = _normalize_text(str(item or ""))
        if text:
            out.append(text[:max_len])
    return out


def _infer_figure_type_from_text(text: str) -> str:
    probe = _normalize_text(text).lower()
    if "formula" in probe:
        return "formula"
    if any(token in probe for token in ("chart", "trend", "revenue")):
        return "chart"
    if any(token in probe for token in ("diagram", "flow", "scheme")):
        return "diagram"
    if "photo" in probe:
        return "photo"
    return "other"


def _figure_text_is_low_signal(text: str) -> bool:
    return _normalize_text(text).lower() in {"", "figure", "chart", "image", "图", "图表"}


def _normalize_dataframe_headers(headers: Any, *, max_len: int = 120) -> list[str]:
    if not isinstance(headers, list):
        return []
    return [_normalize_text(str(item or ""))[:max_len] for item in headers if _normalize_text(str(item or ""))]


def _normalize_dataframe_matrix(rows: Any, *, max_cell_len: int = 160) -> list[list[str]]:
    if not isinstance(rows, list):
        return []
    out: list[list[str]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        out.append([_normalize_text(str(cell or ""))[:max_cell_len] for cell in row])
    return out


def _normalize_figure_key_values(values: Any, *, max_items: int = 6) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    out: list[dict[str, str]] = []
    for item in values[:max_items]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "name": _normalize_text(item.get("name", "")),
                "value": _normalize_text(item.get("value", "")),
                "unit": _normalize_text(item.get("unit", "")),
            }
        )
    return out


def _coerce_figure_dataframe(
    *,
    headers: list[str],
    rows: list[list[str]],
    key_values: list[dict[str, str]],
    fallback_texts: list[str],
    caption_hint: str = "",
    series_labels: list[str] | None = None,
    x_axis: str = "",
    y_axis: str = "",
) -> tuple[list[str], list[list[str]], str]:
    if rows:
        return headers or [x_axis or "类别", y_axis or "数值"], rows, "model"
    if key_values:
        return ["指标", "值", "单位"], [[item["name"], item["value"], item["unit"]] for item in key_values], "key_values"
    return headers, [], "none"


def _recover_figure_title_and_caption(
    *,
    title: str,
    caption: str,
    key_points: list[str],
    text_blocks: list[str],
    fallback_texts: list[str],
    dataframe_headers: list[str],
    series_labels: list[str],
    x_axis: str = "",
    y_axis: str = "",
) -> tuple[str, str]:
    normalized_title = _normalize_text(title)
    normalized_caption = _normalize_text(caption)
    if not normalized_title and dataframe_headers:
        normalized_title = dataframe_headers[-1]
    if not normalized_caption:
        normalized_caption = normalized_title or (text_blocks[0] if text_blocks else "")
    return normalized_title, normalized_caption


def _count_figure_markers_in_text(text: str) -> int:
    return len(re.findall(r"\bfig(?:ure)?\.?\s*[a-z0-9]", _normalize_text(text), flags=re.IGNORECASE))


def _to_float_or_none(value: Any):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_ref(parts: list[str], bbox_map: dict[str, list[float]], ref_id: str, text: str, bbox: list[float]) -> None:
    if ref_id in bbox_map:
        return
    parts.append(f'<ref id="{ref_id}">{text}</ref>')
    bbox_map[ref_id] = bbox


def _layout_bbox_to_ref_bbox(*, page_no: int, raw_bbox: Any, page_dims: dict[int, tuple[float, float]]) -> list[float]:
    return [float(page_no), 0.1, 0.2, 0.3, 0.4]


def _build_runtime() -> VisualFigureBuilderRuntime:
    return VisualFigureBuilderRuntime(
        normalize_text=_normalize_text,
        safe_text_list=_safe_text_list,
        infer_figure_type_from_text=_infer_figure_type_from_text,
        figure_text_is_low_signal=_figure_text_is_low_signal,
        normalize_dataframe_headers=_normalize_dataframe_headers,
        normalize_dataframe_matrix=_normalize_dataframe_matrix,
        normalize_figure_key_values=_normalize_figure_key_values,
        coerce_figure_dataframe=_coerce_figure_dataframe,
        recover_figure_title_and_caption=_recover_figure_title_and_caption,
        count_figure_markers_in_text=_count_figure_markers_in_text,
        to_float_or_none=_to_float_or_none,
        append_ref=_append_ref,
        layout_bbox_to_ref_bbox=_layout_bbox_to_ref_bbox,
    )


def test_visual_figure_builder_runtime_builds_visual_first_figure_block() -> None:
    runtime = _build_runtime()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    figure = runtime.build_figure_from_visual_payload(
        figure_id="pdf_mineru_gemini_f3",
        page_no=2,
        payload={
            "title": "",
            "caption": "",
            "type": "other",
            "content_modes": ["visual"],
            "insights": ["Quarterly revenue increases"],
            "legend": ["North"],
            "axes": {"x": "Quarter", "y": "Revenue"},
            "text_blocks": ["Revenue by quarter"],
            "dataframe": {
                "headers": ["Quarter", "Revenue"],
                "rows": [["Q1", "10"], ["Q2", "20"]],
            },
            "topology": {
                "nodes": [{"id": "n1", "label": "Start", "type": "step"}],
                "edges": [{"source": "n1", "target": "n2", "label": "next"}],
            },
            "key_values": [{"name": "Peak", "value": "42", "unit": "M"}],
            "confidence": 0.88,
        },
        item={
            "caption": ["Fallback caption"],
            "bbox": [10, 20, 30, 40],
            "img_path": "artifacts/roi.png",
            "object_subtype": "chart",
            "source_object_type": "image",
            "object_type": "image",
        },
        parts=parts,
        bbox_map=bbox_map,
        page_dims={2: (1000.0, 800.0)},
        source="pdf_mineru_gemini",
    )

    assert figure is not None
    assert figure["figure_type"] == "chart"
    assert figure["title"] == "Revenue"
    assert figure["caption"] == "Fallback caption"
    assert figure["bbox_norm"] == [2.0, 0.1, 0.2, 0.3, 0.4]
    assert figure["image_path"] == "artifacts/roi.png"
    assert figure["artifact_subtype"] == "chart"
    assert figure["dataframe_source"] == "model"
    assert "dataframe" in figure["content_modes"]
    assert "topology" in figure["content_modes"]
    assert "text" in figure["content_modes"]
    assert figure["ref_ids"][0] == "pdf_mineru_gemini_f3_caption"
    assert any("Quarterly revenue increases" in item for item in figure["insights"])
    assert "pdf_mineru_gemini_f3_caption" in bbox_map
    assert parts


def test_visual_figure_builder_runtime_skips_ambiguous_low_signal_figure() -> None:
    runtime = _build_runtime()

    figure = runtime.build_figure_from_visual_payload(
        figure_id="pdf_mineru_gemini_f9",
        page_no=1,
        payload={
            "caption": "Figure 1 Figure 2",
            "type": "other",
            "confidence": 0.9,
        },
        item={},
        parts=[],
        bbox_map={},
        page_dims={1: (1000.0, 800.0)},
    )

    assert figure is None
