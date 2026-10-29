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


figure_vision_payload_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "figure_vision_payload.py"],
    "_smart_doc_flow_module2_figure_vision_payload",
)

FigureVisionPayloadRuntime = figure_vision_payload_module.FigureVisionPayloadRuntime


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _infer_figure_type_from_text(text: str) -> str:
    probe = _normalize_text(text).lower()
    if any(token in probe for token in ("diagram", "flow", "scheme")):
        return "diagram"
    if any(token in probe for token in ("chart", "trend", "revenue", "bar", "line")):
        return "chart"
    if any(token in probe for token in ("photo", "image")):
        return "photo"
    return "other"


def _safe_text_list(values: Any, max_items: int = 8, max_len: int = 180) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values[:max_items]:
        text = _normalize_text(item)
        if not text:
            continue
        out.append(text[:max_len])
    return out


def _figure_text_is_low_signal(text: str) -> bool:
    probe = _normalize_text(text).lower()
    return probe in {"", "figure", "image", "chart"}


def _normalize_dataframe_headers(headers: Any, *, max_len: int = 120) -> list[str]:
    if not isinstance(headers, list):
        return []
    return [_normalize_text(item)[:max_len] for item in headers if _normalize_text(item)]


def _normalize_dataframe_matrix(rows: Any, *, max_cell_len: int = 160) -> list[list[str]]:
    if not isinstance(rows, list):
        return []
    matrix: list[list[str]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        normalized = [_normalize_text(item)[:max_cell_len] for item in row]
        if any(normalized):
            matrix.append(normalized)
    return matrix


def _normalize_figure_key_values(values: Any, *, max_items: int = 8) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    out: list[dict[str, str]] = []
    for item in values[:max_items]:
        if not isinstance(item, dict):
            continue
        name = _normalize_text(item.get("name", ""))
        value = _normalize_text(item.get("value", ""))
        unit = _normalize_text(item.get("unit", ""))
        if not name and not value:
            continue
        out.append({"name": name, "value": value, "unit": unit})
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
        if headers:
            return headers, rows, "model"
        if len(rows[0]) == 2 and (x_axis or y_axis):
            return [x_axis or "dimension", y_axis or "value"], rows, "model"
        return [f"col_{idx + 1}" for idx in range(len(rows[0]))], rows, "model"
    if key_values:
        return ["metric", "value", "unit"], [[item["name"], item["value"], item["unit"]] for item in key_values], "key_values"
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
    if not normalized_title:
        normalized_title = normalized_caption or (key_points[0] if key_points else "")
    if not normalized_caption:
        normalized_caption = normalized_title or (text_blocks[0] if text_blocks else "")
    return normalized_title, normalized_caption


def _to_float_or_none(value: Any):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count_figure_markers_in_text(text: str) -> int:
    return len(re.findall(r"\bfig(?:ure)?\.?\s*[a-z0-9]", _normalize_text(text), flags=re.IGNORECASE))


def _build_runtime() -> FigureVisionPayloadRuntime:
    return FigureVisionPayloadRuntime(
        vision_enable_figures=True,
        vision_max_figures_per_page=4,
        vision_min_figure_quality=0.5,
        normalize_text=_normalize_text,
        infer_figure_type_from_text=_infer_figure_type_from_text,
        safe_text_list=_safe_text_list,
        figure_text_is_low_signal=_figure_text_is_low_signal,
        normalize_dataframe_headers=_normalize_dataframe_headers,
        normalize_dataframe_matrix=_normalize_dataframe_matrix,
        normalize_figure_key_values=_normalize_figure_key_values,
        coerce_figure_dataframe=_coerce_figure_dataframe,
        recover_figure_title_and_caption=_recover_figure_title_and_caption,
        to_float_or_none=_to_float_or_none,
        count_figure_markers_in_text=_count_figure_markers_in_text,
    )


def test_figure_vision_payload_runtime_builds_structured_figure_block() -> None:
    runtime = _build_runtime()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    figures, next_idx = runtime.build_figures_from_vision_payload(
        {
            "figures": [
                {
                    "title": "Revenue trend",
                    "type": "other",
                    "caption": "",
                    "content_modes": ["visual"],
                    "key_points": ["Quarterly revenue increases"],
                    "key_values": [{"name": "Peak", "value": "42", "unit": "M"}],
                    "axes": {"x": "Quarter", "y": "Revenue"},
                    "legend": ["North"],
                    "text_blocks": ["Revenue by quarter"],
                    "dataframe": {
                        "headers": ["quarter", "revenue"],
                        "rows": [["Q1", "10"], ["Q2", "20"]],
                    },
                    "topology": {
                        "nodes": [{"id": "n1", "label": "Start", "type": "step"}],
                        "edges": [{"source": "n1", "target": "n2", "label": "next"}],
                    },
                    "confidence": 0.88,
                }
            ]
        },
        3,
        4,
        parts,
        bbox_map,
        "vision",
    )

    assert next_idx == 5
    assert len(figures) == 1
    assert figures[0]["figure_id"] == "vision_f4"
    assert figures[0]["figure_type"] == "chart"
    assert figures[0]["caption"] == "Revenue trend"
    assert figures[0]["dataframe"]["rows"] == [["Q1", "10"], ["Q2", "20"]]
    assert figures[0]["dataframe_source"] == "model"
    assert figures[0]["content_modes"] == ["visual", "dataframe", "topology", "text"]
    assert figures[0]["topology"]["nodes"][0]["label"] == "Start"
    assert 'ref id="vision_f4_caption"' in "".join(parts)
    assert "vision_f4_caption" in bbox_map


def test_figure_vision_payload_runtime_skips_low_confidence_uncaptioned_figure() -> None:
    runtime = _build_runtime()

    figures, next_idx = runtime.build_figures_from_vision_payload(
        {
            "figures": [
                {
                    "title": "",
                    "caption": "",
                    "type": "other",
                    "axes": {"x": "Quarter", "y": "Revenue"},
                    "confidence": 0.2,
                }
            ]
        },
        1,
        1,
        [],
        {},
        "vision",
    )

    assert figures == []
    assert next_idx == 1


def test_figure_vision_payload_runtime_skips_ambiguous_multi_marker_caption_without_structure() -> None:
    runtime = _build_runtime()

    figures, next_idx = runtime.build_figures_from_vision_payload(
        {
            "figures": [
                {
                    "caption": "Figure 1 Figure 2",
                    "type": "other",
                    "confidence": 0.9,
                }
            ]
        },
        2,
        7,
        [],
        {},
        "vision",
    )

    assert figures == []
    assert next_idx == 7
