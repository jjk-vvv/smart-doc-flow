from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


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


figure_inference_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "figure_inference.py"],
    "_smart_doc_flow_module2_figure_inference",
)

FigureInferenceRuntime = figure_inference_module.FigureInferenceRuntime


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _normalize_token_for_compare(text: str) -> str:
    normalized = _normalize_text(text).lower()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _contains_figure_marker(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(
        re.search(r"\bfig(?:ure)?\.?\s*[a-z0-9]", normalized, flags=re.IGNORECASE)
        or re.search("图\\s*[0-9A-Za-z\u4e00-\u9fff]", normalized)
    )


def _contains_catalog_marker(text: str) -> bool:
    normalized = _normalize_text(text)
    lower = normalized.lower()
    return any(token in lower for token in ("catalog", "contents", "list of figures")) or ("目录" in normalized)


def _strip_figure_caption_noise(text: str) -> str:
    normalized = _normalize_text(text)
    normalized = re.sub(
        r"^\s*fig(?:ure)?\.?\s*[a-z0-9.\-]+\s*[:.\-]?\s*",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return re.sub(
        "^\\s*" + "图" + "\\s*[0-9A-Za-z\u4e00-\u9fff.\\-]+\\s*[:：.\\-]?\\s*",
        "",
        normalized,
    )


def _count_figure_markers_in_text(text: str) -> int:
    normalized = _normalize_text(text)
    english_hits = len(re.findall(r"\bfig(?:ure)?\.?\s*[a-z0-9]", normalized, flags=re.IGNORECASE))
    chinese_hits = len(re.findall("图\\s*[0-9A-Za-z\u4e00-\u9fff]", normalized))
    return english_hits + chinese_hits


def _next_figure_index(figure_blocks: list[dict], prefix: str) -> int:
    max_idx = 0
    for figure in figure_blocks:
        figure_id = str(figure.get("figure_id", "") or "")
        if not figure_id.startswith(prefix):
            continue
        match = re.search(r"(\d+)$", figure_id)
        if not match:
            continue
        max_idx = max(max_idx, int(match.group(1)))
    return max_idx + 1


def _build_runtime(*, figures_enabled: bool = True):
    return FigureInferenceRuntime(
        vision_enable_figures=figures_enabled,
        normalize_text=_normalize_text,
        normalize_token_for_compare=_normalize_token_for_compare,
        contains_figure_marker=_contains_figure_marker,
        contains_catalog_marker=_contains_catalog_marker,
        strip_figure_caption_noise=_strip_figure_caption_noise,
        count_figure_markers_in_text=_count_figure_markers_in_text,
        next_figure_index=_next_figure_index,
    )


def test_figure_runtime_extracts_captions_and_emits_page_figures() -> None:
    runtime = _build_runtime()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    figures = runtime.infer_figures_from_page_lines(
        {
            1: [
                "Introduction",
                "Figure 1: Flow diagram of process",
                "Further explanation",
            ]
        },
        parts,
        bbox_map,
        "native",
        [],
    )

    assert len(figures) == 1
    assert figures[0]["figure_id"] == "native_f1"
    assert figures[0]["caption"] == "Figure 1: Flow diagram of process"
    assert figures[0]["figure_type"] == "diagram"
    assert 'ref id="native_f1_caption"' in "".join(parts)
    assert "native_f1_caption" in bbox_map


def test_figure_runtime_merge_prefers_richer_duplicate() -> None:
    runtime = _build_runtime()
    merged = runtime.merge_figure_blocks(
        [
            {
                "figure_id": "native_f1",
                "source": "native_caption",
                "page": 2,
                "caption": "Figure 2: Annual trend",
                "quality": 0.58,
            }
        ],
        [
            {
                "figure_id": "vision_f1",
                "source": "vision",
                "page": 2,
                "title": "Annual trend",
                "caption": "Figure 2: Annual trend",
                "quality": 0.92,
                "insights": ["Revenue grows each quarter"],
                "dataframe": {
                    "headers": ["quarter", "revenue"],
                    "rows": [["Q1", "10"], ["Q2", "12"]],
                },
            }
        ],
    )

    assert len(merged) == 1
    assert merged[0]["figure_id"] == "vision_f1"
    assert merged[0]["dataframe"]["rows"] == [["Q1", "10"], ["Q2", "12"]]


def test_figure_runtime_vision_decision_depends_on_depth() -> None:
    runtime = _build_runtime(figures_enabled=True)

    shallow = [
        {
            "figure_id": "native_f1",
            "source": "native_caption",
            "page": 1,
            "caption": "Figure 1: Overview",
            "quality": 0.58,
        }
    ]
    rich = [
        {
            "figure_id": "vision_f1",
            "source": "vision",
            "page": 1,
            "title": "Overview",
            "caption": "Figure 1: Overview",
            "quality": 0.9,
            "insights": ["Contains step-by-step structure"],
            "dataframe": {"headers": ["step", "value"], "rows": [["A", "1"]]},
        }
    ]

    assert runtime.figure_blocks_need_vision(shallow) is True
    assert runtime.figure_blocks_need_vision(rich) is False


def test_figure_runtime_normalizes_text_lists_and_key_values() -> None:
    runtime = _build_runtime()

    texts = runtime.safe_text_list([" alpha  ", "", "beta", "x" * 220], max_items=4, max_len=12)
    key_values = runtime.normalize_figure_key_values(
        [
            {"name": " series ", "value": " 42 ", "unit": " kg "},
            {"name": "", "value": "", "unit": ""},
        ],
        max_items=4,
    )

    assert texts == ["alpha", "beta", "xxxxxxxxxxxx"]
    assert key_values == [{"name": "series", "value": "42", "unit": "kg"}]


def test_figure_runtime_payload_content_checks() -> None:
    runtime = _build_runtime()

    assert runtime.table_payload_has_content({"headers": ["year", "value"]}, table_max_cols=8) is True
    assert runtime.table_payload_has_content({"rows": [["", ""]]}, table_max_cols=8) is False
    assert runtime.figure_payload_has_content({"caption": "Figure 3: Summary"}) is True
    assert runtime.figure_payload_has_content({"topology": {"nodes": [{"id": "n1"}], "edges": []}}) is True
    assert runtime.figure_payload_has_content({}) is False


def test_figure_runtime_keeps_chinese_figure_compatibility() -> None:
    runtime = _build_runtime()
    lines = [
        "引言",
        "图1：流程图",
        "后续说明",
    ]

    captions = runtime.extract_figure_captions_from_lines(lines)

    assert runtime.looks_like_figure_cue_text("示意图") is True
    assert runtime.infer_figure_type_from_text("图2：趋势图") == "chart"
    assert captions == ["图1: 流程图"]
