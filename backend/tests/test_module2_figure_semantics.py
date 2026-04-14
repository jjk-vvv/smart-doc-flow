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


figure_semantics_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "figure_semantics.py"],
    "_smart_doc_flow_module2_figure_semantics",
)

FigureSemanticsRuntime = figure_semantics_module.FigureSemanticsRuntime


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _figure_text_is_low_signal(text: str) -> bool:
    cleaned = _normalize_text(text).lower()
    return cleaned in {"", "figure", "chart", "image", "图", "图片", "图表"}


def _strip_figure_caption_noise(text: str) -> str:
    cleaned = _normalize_text(text)
    cleaned = re.sub(r"^\s*fig(?:ure)?\.?\s*[a-z0-9.\-]+\s*[:.\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*图\s*[0-9A-Za-z一二三四五六七八九十.\-]+\s*[:：.\-]?\s*", "", cleaned)
    return _normalize_text(cleaned)


def _header_token_is_generic(text: str) -> bool:
    cleaned = _normalize_text(text).lower()
    if not cleaned:
        return True
    compact = re.sub(r"[\s_\-/:|]+", "", cleaned)
    return compact in {"col1", "col2", "col3", "列1", "列2", "列3", "value", "metric", "category"}


def _normalize_dataframe_headers(headers, *, max_len: int = 120) -> list[str]:
    normalized: list[str] = []
    for item in headers if isinstance(headers, list) else []:
        text = _normalize_text(str(item or ""))
        if text:
            normalized.append(text[:max_len])
    return normalized


def _normalize_dataframe_matrix(rows, *, max_cell_len: int = 160) -> list[list[str]]:
    normalized_rows: list[list[str]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, list):
            continue
        normalized_rows.append([_normalize_text(str(cell or ""))[:max_cell_len] for cell in row])
    return normalized_rows


def _figure_axis_dimension_label(values: list[str], *, fallback: str = "类别") -> str:
    normalized = [_normalize_text(item) for item in values if _normalize_text(item)]
    year_hits = sum(1 for item in normalized if re.fullmatch(r"(?:19|20)\d{2}年?", item))
    if normalized and (year_hits / float(len(normalized))) >= 0.6:
        return "年份"
    return fallback


def _headers_need_recovery(headers: list[str]) -> bool:
    normalized = [_normalize_text(item) for item in headers if _normalize_text(item)]
    if not normalized:
        return True
    generic_count = sum(1 for item in normalized if _header_token_is_generic(item))
    return generic_count / float(len(normalized)) >= 0.5


def _recover_low_signal_headers(headers, rows_payload, *, caption: str = "", notes=None):
    return ["地区", "占比"], rows_payload


def _build_runtime() -> FigureSemanticsRuntime:
    return FigureSemanticsRuntime(
        normalize_text=_normalize_text,
        figure_text_is_low_signal=_figure_text_is_low_signal,
        strip_figure_caption_noise=_strip_figure_caption_noise,
        header_token_is_generic=_header_token_is_generic,
        normalize_dataframe_headers=_normalize_dataframe_headers,
        normalize_dataframe_matrix=_normalize_dataframe_matrix,
        figure_axis_dimension_label=_figure_axis_dimension_label,
        headers_need_recovery=_headers_need_recovery,
        recover_low_signal_headers=_recover_low_signal_headers,
    )


def test_figure_semantics_runtime_coerces_axis_headers_for_two_column_rows() -> None:
    runtime = _build_runtime()

    headers, rows, source = runtime.coerce_figure_dataframe(
        headers=[],
        rows=[["Q1", "10"], ["Q2", "20"]],
        key_values=[],
        fallback_texts=[],
        x_axis="季度",
        y_axis="营收",
    )

    assert headers == ["季度", "营收"]
    assert rows == [["Q1", "10"], ["Q2", "20"]]
    assert source == "model"


def test_figure_semantics_runtime_recovers_low_signal_headers_via_callback() -> None:
    runtime = _build_runtime()

    headers, rows, source = runtime.coerce_figure_dataframe(
        headers=["col_1", "col_2"],
        rows=[["华东", "25%"], ["华南", "31%"]],
        key_values=[],
        fallback_texts=["图表说明"],
    )

    assert headers == ["地区", "占比"]
    assert rows == [["华东", "25%"], ["华南", "31%"]]
    assert source == "model"


def test_figure_semantics_runtime_uses_key_values_when_model_dataframe_missing() -> None:
    runtime = _build_runtime()

    headers, rows, source = runtime.coerce_figure_dataframe(
        headers=[],
        rows=[],
        key_values=[{"name": "峰值", "value": "42", "unit": "M"}],
        fallback_texts=[],
    )

    assert headers == ["指标", "值", "单位"]
    assert rows == [["峰值", "42", "M"]]
    assert source == "key_values"


def test_figure_semantics_runtime_parses_metric_rows_from_fallback_texts() -> None:
    runtime = _build_runtime()

    headers, rows, source = runtime.coerce_figure_dataframe(
        headers=[],
        rows=[],
        key_values=[],
        fallback_texts=["峰值: 42 M", "增速: 12%"],
    )

    assert headers == ["指标", "值", "单位"]
    assert rows == [["峰值", "42", "M"], ["增速", "12%", ""]]
    assert source == "text_blocks"


def test_figure_semantics_runtime_recovers_title_and_caption_from_headers() -> None:
    runtime = _build_runtime()

    title, caption = runtime.recover_figure_title_and_caption(
        title="",
        caption="",
        key_points=[],
        text_blocks=[],
        fallback_texts=[],
        dataframe_headers=["年份", "营收"],
        series_labels=["华东"],
    )

    assert title == "营收"
    assert caption == "营收"
