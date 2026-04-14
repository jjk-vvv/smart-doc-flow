from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Callable, Dict, List

_GEO_HEADER_RE = re.compile(
    r"(?:^|[\s_\-])(lat|latitude|lon|lng|longitude|geo|coordinate|province|city|district|county|region)(?:$|[\s_\-])",
    flags=re.IGNORECASE,
)

_IDENTIFIER_HEADER_RE = re.compile(
    r"(?:^|[\s_\-])(id|code|no|number|serial)(?:$|[\s_\-])|"
    r"编号|编码|序号|流水号|单号|票号|订单号|客户号|账号|账户号|证件号|身份证号|手机号|电话",
    flags=re.IGNORECASE,
)
_TEMPORAL_HEADER_RE = re.compile(
    r"(?:^|[\s_\-])(date|time|datetime|timestamp|year|month|day|week|hour|minute|min|second|sec)(?:$|[\s_\-])|"
    r"日期|时间|时段|时刻|年份|年月|年|月|日|周|时|分|秒",
    flags=re.IGNORECASE,
)

class CachedExtractionRestoreRuntime:
    """Restore a cached extraction response without re-entering the parse pipeline."""

    @staticmethod
    def _looks_like_xlsx_file(file_name: str) -> bool:
        lower_name = str(file_name or "").strip().lower()
        return lower_name.endswith(".xlsx") or lower_name.endswith(".xls")

    @staticmethod
    def _parse_maybe_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = str(value or "").strip()
        if not text:
            return None
        compact = text.replace(",", "").replace("%", "").strip()
        if not compact:
            return None
        try:
            return float(compact)
        except Exception:
            pass
        match = re.search(r"[-+]?\d+(?:\.\d+)?", compact)
        if not match:
            return None
        try:
            return float(match.group(0))
        except Exception:
            return None

    @staticmethod
    def _parse_maybe_datetime_text(value: Any) -> str | None:
        text = str(value or "").strip()
        if len(text) < 8:
            return None
        normalized = text.replace("/", "-").replace("T", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        for pattern in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
        ):
            try:
                parsed = datetime.strptime(normalized, pattern)
                if pattern == "%Y-%m-%d":
                    return parsed.strftime("%Y-%m-%d")
                if pattern in {"%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"}:
                    return parsed.strftime("%Y-%m-%d %H:%M")
                return parsed.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        return None

    @classmethod
    def _build_chart_specs_from_table_hit(cls, hit: Dict[str, Any], max_specs: int = 3) -> List[Dict[str, Any]]:
        # Delegate to v2 implementation while keeping legacy body in place for rollback safety.
        return cls._build_chart_specs_from_table_hit_v2(hit=hit, max_specs=max_specs)

        locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
        dataframe = locator.get("dataframe") if isinstance(locator.get("dataframe"), dict) else {}
        table_preview = locator.get("table_preview") if isinstance(locator.get("table_preview"), dict) else {}

        headers_raw = dataframe.get("headers") if isinstance(dataframe.get("headers"), list) else table_preview.get("headers", [])
        headers = [str(item or "").strip() for item in (headers_raw if isinstance(headers_raw, list) else [])]
        headers = [item if item else f"col_{idx + 1}" for idx, item in enumerate(headers)]

        rows_raw = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else table_preview.get("rows", [])
        rows = rows_raw if isinstance(rows_raw, list) else []
        if not headers or not rows:
            return []

        max_profile_rows = 1800
        max_points = 180
        col_stats: Dict[int, Dict[str, Any]] = {}
        row_records: List[Dict[int, Dict[str, Any]]] = []

        for row in rows[:max_profile_rows]:
            if not isinstance(row, list):
                continue
            row_map: Dict[int, Dict[str, Any]] = {}
            for col_idx, raw_cell in enumerate(row, start=1):
                text = str(raw_cell or "").strip()
                if not text:
                    continue
                numeric_value = cls._parse_maybe_number(raw_cell)
                if numeric_value is None:
                    numeric_value = cls._parse_maybe_number(text)
                date_value = cls._parse_maybe_datetime_text(text)
                row_map[col_idx] = {
                    "text": text,
                    "numeric": numeric_value,
                    "datetime": date_value,
                }
                stats = col_stats.setdefault(
                    col_idx,
                    {"nonempty": 0, "numeric": 0, "datetime": 0, "unique": set()},
                )
                stats["nonempty"] += 1
                if numeric_value is not None:
                    stats["numeric"] += 1
                if date_value is not None:
                    stats["datetime"] += 1
                if len(stats["unique"]) < 500:
                    stats["unique"].add(text)
            if row_map:
                row_records.append(row_map)

        if not row_records or not col_stats:
            return []

        def header_for(col_idx: int) -> str:
            if 1 <= col_idx <= len(headers):
                return headers[col_idx - 1]
            return f"col_{col_idx}"

        def format_number(value: float) -> str:
            raw = float(value)
            abs_value = abs(raw)
            if abs_value >= 1000:
                return f"{raw:,.2f}"
            if abs_value >= 1:
                return f"{raw:.2f}"
            return f"{raw:.4f}".rstrip("0").rstrip(".")

        def is_identifier_like_header(header_text: str) -> bool:
            cleaned = str(header_text or "").strip().lower()
            if not cleaned:
                return False
            return bool(_IDENTIFIER_HEADER_RE.search(cleaned))

        def is_temporal_like_header(header_text: str) -> bool:
            cleaned = str(header_text or "").strip().lower()
            if not cleaned:
                return False
            return bool(_TEMPORAL_HEADER_RE.search(cleaned))

        def is_identifier_like_numeric_column(col_idx: int, stats: Dict[str, Any]) -> bool:
            if is_identifier_like_header(header_for(col_idx)):
                return True
            nonempty = int(stats.get("nonempty", 0) or 0)
            if nonempty < 8:
                return False
            values: List[float] = []
            for row_map in row_records:
                numeric = (row_map.get(col_idx) or {}).get("numeric")
                if numeric is None:
                    continue
                values.append(float(numeric))
            if len(values) < 6:
                return False
            integer_like = sum(1 for item in values if abs(item - round(item)) < 1e-9) / float(len(values))
            unique_ratio = len({round(item, 6) for item in values}) / float(len(values))
            if integer_like < 0.95 or unique_ratio < 0.95:
                return False
            diffs = [values[idx + 1] - values[idx] for idx in range(len(values) - 1)]
            if not diffs:
                return False
            non_decreasing = sum(1 for item in diffs if item >= 0) / float(len(diffs))
            strict_increasing = sum(1 for item in diffs if item > 0) / float(len(diffs))
            return non_decreasing >= 0.9 and strict_increasing >= 0.75

        def is_low_signal_metric_column(col_idx: int) -> bool:
            values: List[float] = []
            for row_map in row_records:
                numeric = (row_map.get(col_idx) or {}).get("numeric")
                if numeric is None:
                    continue
                values.append(float(numeric))
            if len(values) < 8:
                return False
            rounded_unique = {round(item, 6) for item in values}
            if len(rounded_unique) <= 1:
                return True
            q_low = quantile(values, 0.05)
            q_high = quantile(values, 0.95)
            if q_low is None or q_high is None:
                return False
            spread = abs(float(q_high) - float(q_low))
            baseline = max(abs(float(q_low)), abs(float(q_high)), 1.0)
            return (spread / baseline) < 0.01

        def build_line_summary(*, x_name: str, series_name: str, x_values: List[str], points: List[float]) -> str:
            finite_points = [
                (idx, float(value))
                for idx, value in enumerate(points)
                if isinstance(value, (int, float))
            ]
            if len(finite_points) < 2:
                return f"{series_name}按{x_name}聚合后已生成趋势图。"
            start_val = finite_points[0][1]
            end_val = finite_points[-1][1]
            delta = end_val - start_val
            baseline = max(abs(start_val), 1.0)
            if abs(delta) / baseline < 0.05:
                direction_text = "整体较为平稳"
            elif delta > 0:
                direction_text = "整体呈上升趋势"
            else:
                direction_text = "整体呈下降趋势"
            peak_idx, peak_val = max(finite_points, key=lambda item: item[1])
            trough_idx, trough_val = min(finite_points, key=lambda item: item[1])
            peak_label = x_values[peak_idx] if 0 <= peak_idx < len(x_values) else "峰值点"
            trough_label = x_values[trough_idx] if 0 <= trough_idx < len(x_values) else "谷值点"
            return (
                f"{series_name}按{x_name}聚合后{direction_text}，"
                f"峰值出现在{peak_label}（{format_number(peak_val)}），"
                f"谷值出现在{trough_label}（{format_number(trough_val)}）。"
            )

        def build_category_summary(*, category_name: str, metric_name: str, ordered: List[tuple[str, float]]) -> str:
            if not ordered:
                return ""
            top_name, top_value = ordered[0]
            total_value = sum(float(item[1]) for item in ordered)
            top3_value = sum(float(item[1]) for item in ordered[:3])
            share = (top3_value / total_value * 100.0) if total_value > 0 else 0.0
            return (
                f"{category_name}维度中，{top_name}的{metric_name}最高（{format_number(top_value)}），"
                f"前3个类别合计占比{share:.1f}%。"
            )

        def build_count_summary(*, category_name: str, ordered: List[tuple[str, int]]) -> str:
            if not ordered:
                return ""
            top_name, top_value = ordered[0]
            total_value = sum(int(item[1]) for item in ordered)
            top3_value = sum(int(item[1]) for item in ordered[:3])
            share = (float(top3_value) / float(total_value) * 100.0) if total_value > 0 else 0.0
            return (
                f"{category_name}维度中，{top_name}记录数最多（{int(top_value)}条），"
                f"前3个类别合计占比{share:.1f}%。"
            )

        def build_scatter_summary(*, x_name: str, y_name: str, points: List[List[float]]) -> str:
            if not points:
                return ""
            x_values = [float(item[0]) for item in points if isinstance(item, list) and len(item) >= 2]
            y_values = [float(item[1]) for item in points if isinstance(item, list) and len(item) >= 2]
            if not x_values or not y_values:
                return f"{x_name}与{y_name}关系图已生成。"
            return (
                f"共采样{len(points)}个点，{x_name}范围为{format_number(min(x_values))}至{format_number(max(x_values))}，"
                f"{y_name}范围为{format_number(min(y_values))}至{format_number(max(y_values))}。"
            )

        date_cols: List[tuple[int, float]] = []
        numeric_cols: List[tuple[int, float]] = []
        category_cols: List[tuple[int, int]] = []
        for col_idx, stats in col_stats.items():
            nonempty = int(stats.get("nonempty", 0) or 0)
            if nonempty <= 0:
                continue
            numeric_ratio = float(stats.get("numeric", 0) or 0) / float(nonempty)
            date_ratio = float(stats.get("datetime", 0) or 0) / float(nonempty)
            unique_count = len(stats.get("unique") or [])
            if date_ratio >= 0.6:
                date_cols.append((col_idx, date_ratio))
                continue
            if numeric_ratio >= 0.72:
                if is_temporal_like_header(header_for(col_idx)):
                    continue
                numeric_cols.append((col_idx, numeric_ratio))
                continue
            if 2 <= unique_count <= 200 and not is_identifier_like_header(header_for(col_idx)):
                category_cols.append((col_idx, unique_count))

        date_cols.sort(key=lambda item: item[1], reverse=True)
        numeric_cols.sort(key=lambda item: item[1], reverse=True)
        category_cols.sort(key=lambda item: item[1])

        filtered_numeric_cols: List[tuple[int, float]] = []
        for col_idx, numeric_ratio in numeric_cols:
            stats = col_stats.get(col_idx) if isinstance(col_stats.get(col_idx), dict) else {}
            if is_identifier_like_numeric_column(col_idx, stats):
                continue
            header_name = header_for(col_idx)
            if is_geo_like_header(header_name):
                continue
            if is_low_signal_metric_column(col_idx):
                continue
            filtered_numeric_cols.append((col_idx, numeric_ratio))
        numeric_cols = filtered_numeric_cols

        specs: List[Dict[str, Any]] = []

        if date_cols and numeric_cols:
            x_col = date_cols[0][0]
            y_cols = [item[0] for item in numeric_cols[:2]]
            series_map: Dict[str, Dict[str, float]] = {header_for(col_idx): {} for col_idx in y_cols}
            for row_map in row_records:
                x_obj = row_map.get(x_col)
                x_key = str((x_obj or {}).get("datetime") or "").strip()
                if not x_key:
                    continue
                for col_idx in y_cols:
                    y_val = (row_map.get(col_idx) or {}).get("numeric")
                    if y_val is None:
                        continue
                    key = header_for(col_idx)
                    series_map[key][x_key] = series_map[key].get(x_key, 0.0) + float(y_val)
            x_values: List[str] = []
            seen_x: set[str] = set()
            for row_map in row_records:
                x_obj = row_map.get(x_col)
                x_key = str((x_obj or {}).get("datetime") or "").strip()
                if not x_key or x_key in seen_x:
                    continue
                if any(x_key in series_values for series_values in series_map.values()):
                    seen_x.add(x_key)
                    x_values.append(x_key)
            if not x_values:
                x_values = sorted({x_key for series in series_map.values() for x_key in series.keys()})
            if x_values:
                def _parse_temporal_ts(raw_value: str) -> float | None:
                    text = str(raw_value or "").strip()
                    if not text:
                        return None
                    text = text.replace("Z", "+00:00")
                    try:
                        return datetime.fromisoformat(text).timestamp()
                    except Exception:
                        pass
                    for fmt in (
                        "%Y-%m-%d",
                        "%Y/%m/%d",
                        "%Y.%m.%d",
                        "%Y-%m",
                        "%Y/%m",
                        "%Y-%m-%d %H:%M:%S",
                        "%Y/%m/%d %H:%M:%S",
                        "%Y.%m.%d %H:%M:%S",
                    ):
                        try:
                            return datetime.strptime(text, fmt).timestamp()
                        except Exception:
                            continue
                    return None

                sortable_keys: List[tuple[int, float, str]] = []
                parseable_count = 0
                for idx, key in enumerate(x_values):
                    parsed_ts = _parse_temporal_ts(key)
                    if parsed_ts is None:
                        sortable_keys.append((1, float(idx), key))
                        continue
                    parseable_count += 1
                    sortable_keys.append((0, parsed_ts, key))
                if parseable_count >= max(2, int(len(x_values) * 0.6)):
                    sortable_keys.sort(key=lambda item: (item[0], item[1]))
                    x_values = [item[2] for item in sortable_keys]

                if len(x_values) > max_points:
                    stride = max(1, len(x_values) // max_points)
                    x_values = x_values[::stride][:max_points]
                series_payload = []
                for series_name, series_values in series_map.items():
                    points = [round(float(series_values.get(x_val, 0.0)), 6) for x_val in x_values]
                    if any(point != 0 for point in points):
                        series_payload.append({"name": series_name, "data": points})
                if series_payload:
                    x_name = header_for(x_col)
                    primary_metric = str(series_payload[0].get("name") or "").strip() or "指标"
                    y_names = [str(item.get("name") or "").strip() for item in series_payload if str(item.get("name") or "").strip()]
                    y_axis_label = " / ".join(y_names[:2]) if y_names else "指标值"
                    trend_summary = build_line_summary(
                        x_name=x_name,
                        series_name=primary_metric,
                        x_values=x_values,
                        points=[float(item) for item in series_payload[0].get("data", [])],
                    )
                    title_text = f"{primary_metric}时间趋势"
                    description_text = f"按{x_name}聚合后展示{y_axis_label}的变化。"
                    specs.append(
                        {
                            "chart_type": "line",
                            "title": title_text,
                            "title_zh": title_text,
                            "description": description_text,
                            "description_zh": description_text,
                            "x_field": x_name,
                            "y_fields": [item["name"] for item in series_payload],
                            "x_values": x_values,
                            "series": series_payload,
                            "x_axis_label": x_name,
                            "y_axis_label": y_axis_label,
                            "trend_summary": trend_summary,
                            "trend_summary_zh": trend_summary,
                            "point_count": len(x_values),
                            "aggregation": "sum_by_time",
                        }
                    )

        if category_cols:
            cat_col = category_cols[0][0]
            cat_name = header_for(cat_col)
            if numeric_cols:
                metric_col = numeric_cols[0][0]
                metric_name = header_for(metric_col)
                aggregate: Dict[str, float] = {}
                for row_map in row_records:
                    cat_value = str((row_map.get(cat_col) or {}).get("text") or "").strip()
                    metric_value = (row_map.get(metric_col) or {}).get("numeric")
                    if not cat_value or metric_value is None:
                        continue
                    aggregate[cat_value] = aggregate.get(cat_value, 0.0) + float(metric_value)
                if aggregate:
                    ordered = sorted(aggregate.items(), key=lambda item: item[1], reverse=True)[:20]
                    trend_summary = build_category_summary(
                        category_name=cat_name,
                        metric_name=metric_name,
                        ordered=[(str(item[0]), float(item[1])) for item in ordered],
                    )
                    title_text = f"{metric_name}按{cat_name}分布"
                    description_text = f"按{cat_name}分组后，对{metric_name}求和并展示前{len(ordered)}项。"
                    specs.append(
                        {
                            "chart_type": "bar",
                            "title": title_text,
                            "title_zh": title_text,
                            "description": description_text,
                            "description_zh": description_text,
                            "x_field": cat_name,
                            "y_fields": [metric_name],
                            "x_values": [item[0] for item in ordered],
                            "series": [{"name": metric_name, "data": [round(float(item[1]), 6) for item in ordered]}],
                            "x_axis_label": cat_name,
                            "y_axis_label": metric_name,
                            "trend_summary": trend_summary,
                            "trend_summary_zh": trend_summary,
                            "point_count": len(ordered),
                            "aggregation": "sum_by_category",
                        }
                    )
            else:
                counts: Dict[str, int] = {}
                for row_map in row_records:
                    cat_value = str((row_map.get(cat_col) or {}).get("text") or "").strip()
                    if not cat_value:
                        continue
                    counts[cat_value] = counts.get(cat_value, 0) + 1
                if counts:
                    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20]
                    trend_summary = build_count_summary(
                        category_name=cat_name,
                        ordered=[(str(item[0]), int(item[1])) for item in ordered],
                    )
                    title_text = f"{cat_name}记录数分布"
                    description_text = f"按{cat_name}统计记录数并展示前{len(ordered)}项。"
                    specs.append(
                        {
                            "chart_type": "bar",
                            "title": title_text,
                            "title_zh": title_text,
                            "description": description_text,
                            "description_zh": description_text,
                            "x_field": cat_name,
                            "y_fields": ["count"],
                            "x_values": [item[0] for item in ordered],
                            "series": [{"name": "count", "data": [int(item[1]) for item in ordered]}],
                            "x_axis_label": cat_name,
                            "y_axis_label": "记录数",
                            "trend_summary": trend_summary,
                            "trend_summary_zh": trend_summary,
                            "point_count": len(ordered),
                            "aggregation": "count_by_category",
                        }
                    )

        if len(numeric_cols) >= 2:
            x_col = numeric_cols[0][0]
            y_col = numeric_cols[1][0]
            points: List[List[float]] = []
            for row_map in row_records:
                x_val = (row_map.get(x_col) or {}).get("numeric")
                y_val = (row_map.get(y_col) or {}).get("numeric")
                if x_val is None or y_val is None:
                    continue
                points.append([round(float(x_val), 6), round(float(y_val), 6)])
                if len(points) >= 240:
                    break
            if points:
                x_name = header_for(x_col)
                y_name = header_for(y_col)
                trend_summary = build_scatter_summary(x_name=x_name, y_name=y_name, points=points)
                title_text = f"{y_name}与{x_name}关系"
                description_text = f"展示{x_name}与{y_name}的配对样本点。"
                specs.append(
                    {
                        "chart_type": "scatter",
                        "title": title_text,
                        "title_zh": title_text,
                        "description": description_text,
                        "description_zh": description_text,
                        "x_field": x_name,
                        "y_fields": [y_name],
                        "points": points,
                        "x_axis_label": x_name,
                        "y_axis_label": y_name,
                        "trend_summary": trend_summary,
                        "trend_summary_zh": trend_summary,
                        "point_count": len(points),
                        "aggregation": "raw_sample",
                    }
                )

        deduped: List[Dict[str, Any]] = []
        seen_titles: set[str] = set()
        for spec in specs:
            title = str(spec.get("title") or "").strip().lower()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            deduped.append(spec)
            if len(deduped) >= max_specs:
                break
        return deduped

    @classmethod
    def _build_chart_specs_from_table_hit_v2(
        cls,
        hit: Dict[str, Any],
        max_specs: int = 3,
    ) -> List[Dict[str, Any]]:
        locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
        dataframe = locator.get("dataframe") if isinstance(locator.get("dataframe"), dict) else {}
        table_preview = locator.get("table_preview") if isinstance(locator.get("table_preview"), dict) else {}

        headers_raw = (
            dataframe.get("headers")
            if isinstance(dataframe.get("headers"), list)
            else table_preview.get("headers", [])
        )
        headers = [str(item or "").strip() for item in (headers_raw if isinstance(headers_raw, list) else [])]
        headers = [item if item else f"col_{idx + 1}" for idx, item in enumerate(headers)]

        rows_raw = (
            dataframe.get("rows")
            if isinstance(dataframe.get("rows"), list)
            else table_preview.get("rows", [])
        )
        rows = rows_raw if isinstance(rows_raw, list) else []
        if not headers or not rows:
            return []

        max_profile_rows = 1800
        max_points = 180
        max_scatter_points = 240
        placeholder_tokens = {
            "",
            "-",
            "--",
            "—",
            "–",
            "/",
            "\\",
            "n/a",
            "na",
            "none",
            "null",
            "nil",
            "unknown",
            "未知",
            "无",
            "暂无",
            "空",
            "不详",
        }

        col_stats: Dict[int, Dict[str, Any]] = {}
        row_records: List[Dict[int, Dict[str, Any]]] = []

        for row in rows[:max_profile_rows]:
            if not isinstance(row, list):
                continue
            row_map: Dict[int, Dict[str, Any]] = {}
            for col_idx, raw_cell in enumerate(row, start=1):
                text = str(raw_cell or "").strip()
                if not text:
                    continue
                numeric_value = cls._parse_maybe_number(raw_cell)
                if numeric_value is None:
                    numeric_value = cls._parse_maybe_number(text)
                date_value = cls._parse_maybe_datetime_text(text)
                row_map[col_idx] = {
                    "text": text,
                    "numeric": numeric_value,
                    "datetime": date_value,
                }
                stats = col_stats.setdefault(
                    col_idx,
                    {"nonempty": 0, "numeric": 0, "datetime": 0, "unique": set()},
                )
                stats["nonempty"] += 1
                if numeric_value is not None:
                    stats["numeric"] += 1
                if date_value is not None:
                    stats["datetime"] += 1
                if len(stats["unique"]) < 500:
                    stats["unique"].add(text)
            if row_map:
                row_records.append(row_map)

        if not row_records or not col_stats:
            return []

        def header_for(col_idx: int) -> str:
            if 1 <= col_idx <= len(headers):
                return headers[col_idx - 1]
            return f"col_{col_idx}"

        def format_number(value: float) -> str:
            raw = float(value)
            abs_value = abs(raw)
            if abs_value >= 1000:
                return f"{raw:,.2f}"
            if abs_value >= 1:
                return f"{raw:.2f}"
            return f"{raw:.4f}".rstrip("0").rstrip(".")

        def is_identifier_like_header(header_text: str) -> bool:
            cleaned = str(header_text or "").strip().lower()
            if not cleaned:
                return False
            return bool(_IDENTIFIER_HEADER_RE.search(cleaned))

        def is_temporal_like_header(header_text: str) -> bool:
            cleaned = str(header_text or "").strip().lower()
            if not cleaned:
                return False
            return bool(_TEMPORAL_HEADER_RE.search(cleaned))

        def is_geo_like_header(header_text: str) -> bool:
            cleaned = str(header_text or "").strip().lower()
            if not cleaned:
                return False
            return bool(_GEO_HEADER_RE.search(cleaned))

        def is_placeholder_category(value: Any) -> bool:
            text = str(value or "").strip().lower()
            if not text:
                return True
            compact = re.sub(r"\s+", "", text)
            return compact in placeholder_tokens

        def quantile(values: List[float], q: float) -> float | None:
            finite_values = [float(item) for item in values if isinstance(item, (int, float))]
            if not finite_values:
                return None
            ordered = sorted(finite_values)
            if len(ordered) == 1:
                return ordered[0]
            safe_q = max(0.0, min(1.0, float(q)))
            pos = safe_q * float(len(ordered) - 1)
            lower_idx = int(pos)
            upper_idx = min(lower_idx + 1, len(ordered) - 1)
            frac = pos - float(lower_idx)
            if upper_idx == lower_idx:
                return ordered[lower_idx]
            return ordered[lower_idx] * (1.0 - frac) + ordered[upper_idx] * frac

        def build_domain(values: List[float]) -> List[float] | None:
            finite_values = [float(item) for item in values if isinstance(item, (int, float))]
            if not finite_values:
                return None
            full_min = min(finite_values)
            full_max = max(finite_values)
            if full_max <= full_min:
                pad = max(1.0, abs(full_min) * 0.1)
                return [round(full_min - pad, 6), round(full_max + pad, 6)]

            q_low = quantile(finite_values, 0.02)
            q_high = quantile(finite_values, 0.98)
            if q_low is None or q_high is None:
                q_low = full_min
                q_high = full_max
            if q_high <= q_low:
                q_low = full_min
                q_high = full_max

            full_span = full_max - full_min
            robust_span = max(0.0, q_high - q_low)
            use_robust = robust_span > 0 and full_span / robust_span >= 4.0
            domain_min = q_low if use_robust else full_min
            domain_max = q_high if use_robust else full_max
            span = max(domain_max - domain_min, 1e-9)
            pad = span * 0.06
            return [round(domain_min - pad, 6), round(domain_max + pad, 6)]

        def downsample_points(points: List[List[float]], cap: int) -> List[List[float]]:
            if len(points) <= cap:
                return points
            stride = max(1, len(points) // cap)
            sampled = points[::stride]
            if len(sampled) > cap:
                sampled = sampled[:cap]
            return sampled

        def is_identifier_like_numeric_column(col_idx: int, stats: Dict[str, Any]) -> bool:
            if is_identifier_like_header(header_for(col_idx)):
                return True
            nonempty = int(stats.get("nonempty", 0) or 0)
            if nonempty < 8:
                return False
            values: List[float] = []
            for row_map in row_records:
                numeric = (row_map.get(col_idx) or {}).get("numeric")
                if numeric is None:
                    continue
                values.append(float(numeric))
            if len(values) < 6:
                return False
            integer_like = sum(1 for item in values if abs(item - round(item)) < 1e-9) / float(len(values))
            unique_ratio = len({round(item, 6) for item in values}) / float(len(values))
            if integer_like < 0.95 or unique_ratio < 0.95:
                return False
            diffs = [values[idx + 1] - values[idx] for idx in range(len(values) - 1)]
            if not diffs:
                return False
            non_decreasing = sum(1 for item in diffs if item >= 0) / float(len(diffs))
            strict_increasing = sum(1 for item in diffs if item > 0) / float(len(diffs))
            return non_decreasing >= 0.9 and strict_increasing >= 0.75

        def build_line_summary(*, x_name: str, series_name: str, x_values: List[str], points: List[float]) -> str:
            finite_points = [
                (idx, float(value))
                for idx, value in enumerate(points)
                if isinstance(value, (int, float))
            ]
            if len(finite_points) < 2:
                return f"{series_name} trend is generated across {x_name}."
            start_val = finite_points[0][1]
            end_val = finite_points[-1][1]
            delta = end_val - start_val
            baseline = max(abs(start_val), 1.0)
            if abs(delta) / baseline < 0.05:
                direction_text = "mostly stable"
            elif delta > 0:
                direction_text = "overall increasing"
            else:
                direction_text = "overall decreasing"
            peak_idx, peak_val = max(finite_points, key=lambda item: item[1])
            trough_idx, trough_val = min(finite_points, key=lambda item: item[1])
            peak_label = x_values[peak_idx] if 0 <= peak_idx < len(x_values) else "peak"
            trough_label = x_values[trough_idx] if 0 <= trough_idx < len(x_values) else "trough"
            return (
                f"{series_name} is {direction_text}; "
                f"peak at {peak_label} ({format_number(peak_val)}), "
                f"trough at {trough_label} ({format_number(trough_val)})."
            )

        def build_category_summary(*, category_name: str, metric_name: str, ordered: List[tuple[str, float]]) -> str:
            if not ordered:
                return ""
            top_name, top_value = ordered[0]
            if len(ordered) == 1:
                return (
                    f"Within {category_name}, {top_name} has the highest {metric_name} "
                    f"({format_number(top_value)})."
                )
            second_name, second_value = ordered[1]
            gap = float(top_value) - float(second_value)
            return (
                f"Within {category_name}, {top_name} has the highest {metric_name} "
                f"({format_number(top_value)}), {format_number(gap)} higher than {second_name}."
            )

        def build_count_summary(*, category_name: str, ordered: List[tuple[str, int]]) -> str:
            if not ordered:
                return ""
            top_name, top_value = ordered[0]
            if len(ordered) == 1:
                return f"In {category_name}, {top_name} has the largest record count ({int(top_value)})."
            second_name, second_value = ordered[1]
            gap = int(top_value) - int(second_value)
            return (
                f"In {category_name}, {top_name} has the largest record count ({int(top_value)}). "
                f"It has {gap} more records than {second_name}."
            )

        def build_scatter_summary(*, x_name: str, y_name: str, points: List[List[float]]) -> str:
            if not points:
                return ""
            x_values = [float(item[0]) for item in points if isinstance(item, list) and len(item) >= 2]
            y_values = [float(item[1]) for item in points if isinstance(item, list) and len(item) >= 2]
            if not x_values or not y_values:
                return f"{x_name} vs {y_name} scatter view generated."
            return (
                f"{len(points)} points sampled. {x_name} ranges {format_number(min(x_values))}-{format_number(max(x_values))}, "
                f"{y_name} ranges {format_number(min(y_values))}-{format_number(max(y_values))}."
            )

        date_cols: List[tuple[int, float]] = []
        numeric_cols: List[tuple[int, float]] = []
        category_cols: List[tuple[int, int]] = []
        for col_idx, stats in col_stats.items():
            nonempty = int(stats.get("nonempty", 0) or 0)
            if nonempty <= 0:
                continue
            numeric_ratio = float(stats.get("numeric", 0) or 0) / float(nonempty)
            date_ratio = float(stats.get("datetime", 0) or 0) / float(nonempty)
            unique_count = len(stats.get("unique") or [])
            if date_ratio >= 0.6:
                date_cols.append((col_idx, date_ratio))
                continue
            if numeric_ratio >= 0.72:
                if is_temporal_like_header(header_for(col_idx)):
                    continue
                numeric_cols.append((col_idx, numeric_ratio))
                continue
            if 2 <= unique_count <= 200 and not is_identifier_like_header(header_for(col_idx)):
                category_cols.append((col_idx, unique_count))

        date_cols.sort(key=lambda item: item[1], reverse=True)
        numeric_cols.sort(key=lambda item: item[1], reverse=True)
        category_cols.sort(key=lambda item: item[1])

        filtered_numeric_cols: List[tuple[int, float]] = []
        for col_idx, numeric_ratio in numeric_cols:
            stats = col_stats.get(col_idx) if isinstance(col_stats.get(col_idx), dict) else {}
            if is_identifier_like_numeric_column(col_idx, stats):
                continue
            filtered_numeric_cols.append((col_idx, numeric_ratio))
        numeric_cols = filtered_numeric_cols

        specs: List[Dict[str, Any]] = []

        if date_cols and numeric_cols:
            x_col = date_cols[0][0]
            y_cols = [item[0] for item in numeric_cols[:2]]
            series_buckets: Dict[str, Dict[str, List[float]]] = {header_for(col_idx): {} for col_idx in y_cols}
            for row_map in row_records:
                x_obj = row_map.get(x_col)
                x_key = str((x_obj or {}).get("datetime") or "").strip()
                if not x_key:
                    continue
                for col_idx in y_cols:
                    y_val = (row_map.get(col_idx) or {}).get("numeric")
                    if y_val is None:
                        continue
                    key = header_for(col_idx)
                    bucket = series_buckets[key].setdefault(x_key, [])
                    bucket.append(float(y_val))

            series_map: Dict[str, Dict[str, float]] = {}
            for series_name, x_bucket in series_buckets.items():
                reduced: Dict[str, float] = {}
                for x_key, values in x_bucket.items():
                    if not values:
                        continue
                    reduced[x_key] = float(sum(values) / max(1, len(values)))
                if reduced:
                    series_map[series_name] = reduced

            x_values: List[str] = []
            seen_x: set[str] = set()
            for row_map in row_records:
                x_obj = row_map.get(x_col)
                x_key = str((x_obj or {}).get("datetime") or "").strip()
                if not x_key or x_key in seen_x:
                    continue
                if any(x_key in series_values for series_values in series_map.values()):
                    seen_x.add(x_key)
                    x_values.append(x_key)
            if not x_values:
                x_values = sorted({x_key for series in series_map.values() for x_key in series.keys()})

            if x_values:
                def _parse_temporal_ts(raw_value: str) -> float | None:
                    text = str(raw_value or "").strip()
                    if not text:
                        return None
                    text = text.replace("Z", "+00:00")
                    try:
                        return datetime.fromisoformat(text).timestamp()
                    except Exception:
                        pass
                    for fmt in (
                        "%Y-%m-%d",
                        "%Y/%m/%d",
                        "%Y.%m.%d",
                        "%Y-%m",
                        "%Y/%m",
                        "%Y-%m-%d %H:%M:%S",
                        "%Y/%m/%d %H:%M:%S",
                        "%Y.%m.%d %H:%M:%S",
                    ):
                        try:
                            return datetime.strptime(text, fmt).timestamp()
                        except Exception:
                            continue
                    return None

                sortable_keys: List[tuple[int, float, str]] = []
                parseable_count = 0
                for idx, key in enumerate(x_values):
                    parsed_ts = _parse_temporal_ts(key)
                    if parsed_ts is None:
                        sortable_keys.append((1, float(idx), key))
                        continue
                    parseable_count += 1
                    sortable_keys.append((0, parsed_ts, key))
                if parseable_count >= max(2, int(len(x_values) * 0.6)):
                    sortable_keys.sort(key=lambda item: (item[0], item[1]))
                    x_values = [item[2] for item in sortable_keys]

                if len(x_values) > max_points:
                    stride = max(1, len(x_values) // max_points)
                    x_values = x_values[::stride][:max_points]

                series_payload = []
                for series_name, series_values in series_map.items():
                    if is_geo_like_header(series_name):
                        continue
                    points = []
                    finite_count = 0
                    for x_val in x_values:
                        value = series_values.get(x_val)
                        if value is None:
                            points.append(None)
                            continue
                        rounded = round(float(value), 6)
                        points.append(rounded)
                        finite_count += 1
                    if finite_count >= 2:
                        series_payload.append({"name": series_name, "data": points})

                if series_payload:
                    x_name = header_for(x_col)
                    primary_metric = str(series_payload[0].get("name") or "").strip() or "metric"
                    y_names = [
                        str(item.get("name") or "").strip()
                        for item in series_payload
                        if str(item.get("name") or "").strip()
                    ]
                    y_axis_label = " / ".join(y_names[:2]) if y_names else "metric"
                    trend_summary = build_line_summary(
                        x_name=x_name,
                        series_name=primary_metric,
                        x_values=x_values,
                        points=[
                            float(item)
                            for item in series_payload[0].get("data", [])
                            if isinstance(item, (int, float))
                        ],
                    )
                    title_text = f"{primary_metric} trend over time"
                    description_text = f"Grouped by {x_name} using mean aggregation to show {y_axis_label}."
                    specs.append(
                        {
                            "chart_type": "line",
                            "title": title_text,
                            "title_zh": title_text,
                            "description": description_text,
                            "description_zh": description_text,
                            "x_field": x_name,
                            "y_fields": [item["name"] for item in series_payload],
                            "x_values": x_values,
                            "series": series_payload,
                            "x_axis_label": x_name,
                            "y_axis_label": y_axis_label,
                            "trend_summary": trend_summary,
                            "trend_summary_zh": trend_summary,
                            "point_count": len(x_values),
                            "aggregation": "mean_by_time",
                        }
                    )

        if category_cols:
            cat_col = category_cols[0][0]
            cat_name = header_for(cat_col)
            if numeric_cols:
                metric_col = numeric_cols[0][0]
                metric_name = header_for(metric_col)
                aggregate_sum: Dict[str, float] = {}
                aggregate_count: Dict[str, int] = {}
                for row_map in row_records:
                    cat_value = str((row_map.get(cat_col) or {}).get("text") or "").strip()
                    metric_value = (row_map.get(metric_col) or {}).get("numeric")
                    if is_placeholder_category(cat_value) or metric_value is None:
                        continue
                    aggregate_sum[cat_value] = aggregate_sum.get(cat_value, 0.0) + float(metric_value)
                    aggregate_count[cat_value] = aggregate_count.get(cat_value, 0) + 1
                if aggregate_sum:
                    aggregate_mean = {
                        key: float(aggregate_sum[key] / max(1, aggregate_count.get(key, 1)))
                        for key in aggregate_sum.keys()
                    }
                    ordered = sorted(aggregate_mean.items(), key=lambda item: item[1], reverse=True)[:20]
                    trend_summary = build_category_summary(
                        category_name=cat_name,
                        metric_name=metric_name,
                        ordered=[(str(item[0]), float(item[1])) for item in ordered],
                    )
                    title_text = f"{metric_name} by {cat_name}"
                    description_text = (
                        f"Grouped by {cat_name}, showing mean {metric_name}; placeholder categories are filtered out."
                    )
                    specs.append(
                        {
                            "chart_type": "bar",
                            "title": title_text,
                            "title_zh": title_text,
                            "description": description_text,
                            "description_zh": description_text,
                            "x_field": cat_name,
                            "y_fields": [metric_name],
                            "x_values": [item[0] for item in ordered],
                            "series": [{"name": metric_name, "data": [round(float(item[1]), 6) for item in ordered]}],
                            "x_axis_label": cat_name,
                            "y_axis_label": metric_name,
                            "trend_summary": trend_summary,
                            "trend_summary_zh": trend_summary,
                            "point_count": len(ordered),
                            "aggregation": "mean_by_category",
                        }
                    )
            else:
                counts: Dict[str, int] = {}
                for row_map in row_records:
                    cat_value = str((row_map.get(cat_col) or {}).get("text") or "").strip()
                    if is_placeholder_category(cat_value):
                        continue
                    counts[cat_value] = counts.get(cat_value, 0) + 1
                if counts:
                    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20]
                    trend_summary = build_count_summary(
                        category_name=cat_name,
                        ordered=[(str(item[0]), int(item[1])) for item in ordered],
                    )
                    title_text = f"{cat_name} distribution"
                    description_text = f"Record count grouped by {cat_name}; placeholder categories are filtered out."
                    specs.append(
                        {
                            "chart_type": "bar",
                            "title": title_text,
                            "title_zh": title_text,
                            "description": description_text,
                            "description_zh": description_text,
                            "x_field": cat_name,
                            "y_fields": ["count"],
                            "x_values": [item[0] for item in ordered],
                            "series": [{"name": "count", "data": [int(item[1]) for item in ordered]}],
                            "x_axis_label": cat_name,
                            "y_axis_label": "count",
                            "trend_summary": trend_summary,
                            "trend_summary_zh": trend_summary,
                            "point_count": len(ordered),
                            "aggregation": "count_by_category",
                        }
                    )

        if len(numeric_cols) >= 2:
            x_col = numeric_cols[0][0]
            y_col = numeric_cols[1][0]
            points: List[List[float]] = []
            for row_map in row_records:
                x_val = (row_map.get(x_col) or {}).get("numeric")
                y_val = (row_map.get(y_col) or {}).get("numeric")
                if x_val is None or y_val is None:
                    continue
                points.append([round(float(x_val), 6), round(float(y_val), 6)])
            sampled_points = downsample_points(points, max_scatter_points)
            x_name = header_for(x_col)
            y_name = header_for(y_col)
            if is_geo_like_header(x_name) and is_geo_like_header(y_name):
                sampled_points = []
            if sampled_points:
                trend_summary = build_scatter_summary(x_name=x_name, y_name=y_name, points=sampled_points)
                x_domain = build_domain([item[0] for item in sampled_points])
                y_domain = build_domain([item[1] for item in sampled_points])
                title_text = f"{y_name} vs {x_name}"
                description_text = "Scatter view with robust visible-domain recommendations for outlier-heavy data."
                spec_payload: Dict[str, Any] = {
                    "chart_type": "scatter",
                    "title": title_text,
                    "title_zh": title_text,
                    "description": description_text,
                    "description_zh": description_text,
                    "x_field": x_name,
                    "y_fields": [y_name],
                    "points": sampled_points,
                    "x_axis_label": x_name,
                    "y_axis_label": y_name,
                    "trend_summary": trend_summary,
                    "trend_summary_zh": trend_summary,
                    "point_count": len(sampled_points),
                    "aggregation": "raw_sample",
                }
                if x_domain:
                    spec_payload["x_domain"] = x_domain
                if y_domain:
                    spec_payload["y_domain"] = y_domain
                specs.append(spec_payload)

        deduped: List[Dict[str, Any]] = []
        seen_titles: set[str] = set()
        for spec in specs:
            title = str(spec.get("title") or "").strip().lower()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            deduped.append(spec)
            if len(deduped) >= max_specs:
                break
        return deduped

    @classmethod
    def _augment_cached_trace_hits_with_chart_hits(
        cls,
        *,
        file_name: str,
        file_hash: str,
        trace_hits: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not trace_hits:
            return []

        file_is_xlsx = cls._looks_like_xlsx_file(file_name)
        xlsx_table_hits: List[Dict[str, Any]] = []
        for hit in trace_hits:
            if not isinstance(hit, dict):
                continue
            object_type = str(hit.get("object_type") or "").strip().lower()
            if object_type != "table":
                continue
            locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
            ref_id = str(hit.get("ref_id") or locator.get("ref_id") or "").strip()
            data_source = str(locator.get("dataframe_source") or locator.get("artifact_source") or "").strip().lower()
            table_id = str(hit.get("object_id") or locator.get("table_id") or "").strip().lower()
            is_xlsx_table = (
                file_is_xlsx
                or ("xlsx" in data_source)
                or ref_id.startswith("xlsx_")
                or table_id.startswith("xlsx_")
            )
            if not is_xlsx_table:
                continue
            xlsx_table_hits.append(hit)

        # For xlsx tables we regenerate chart hits on restore so old cache snapshots
        # can be upgraded with the latest chart spec heuristics.
        if not xlsx_table_hits:
            return trace_hits

        passthrough_hits: List[Dict[str, Any]] = []
        for hit in trace_hits:
            if not isinstance(hit, dict):
                passthrough_hits.append(hit)
                continue
            if str(hit.get("object_type") or "").strip().lower() == "chart":
                continue
            passthrough_hits.append(hit)

        generated_chart_hits: List[Dict[str, Any]] = []
        for hit in xlsx_table_hits:
            locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
            ref_id = str(hit.get("ref_id") or locator.get("ref_id") or "").strip()
            specs = cls._build_chart_specs_from_table_hit(hit)
            if not specs:
                continue

            table_id = str(hit.get("object_id") or locator.get("table_id") or "xlsx_sheet").strip() or "xlsx_sheet"
            page_value = hit.get("page", locator.get("page", 1))
            try:
                page = int(page_value or 1)
            except Exception:
                page = 1
            if page <= 0:
                page = 1

            bbox = hit.get("bbox")
            if not (isinstance(bbox, list) and bbox):
                bbox = locator.get("bbox")
            artifact_path = hit.get("artifact_path")
            artifact_url = hit.get("artifact_url")
            try:
                base_conf = float(hit.get("confidence", 0.72) or 0.72)
            except Exception:
                base_conf = 0.72
            base_conf = max(0.68, min(0.92, base_conf))

            for idx, spec in enumerate(specs, start=1):
                chart_type = str(spec.get("chart_type") or "").strip().lower() or "bar"
                chart_title = str(spec.get("title_zh") or spec.get("title") or "").strip() or f"图表 {idx}"
                chart_locator = {
                    "page": page,
                    "ref_id": ref_id or None,
                    "sheet_index": locator.get("sheet_index"),
                    "sheet_name": locator.get("sheet_name"),
                    "table_id": table_id,
                    "bbox": bbox,
                    "chart_spec": spec,
                    "artifact_source": "xlsx_chart_spec",
                    "dataframe_source": "xlsx_sheet_rows",
                }
                chart_locator = {
                    key: value
                    for key, value in chart_locator.items()
                    if value not in ("", None, [], {})
                }
                generated_chart_hits.append(
                    {
                        "file_name": file_name,
                        "file_hash": file_hash,
                        "object_type": "chart",
                        "object_id": f"{table_id}_chart_{idx}",
                        "ref_id": ref_id or None,
                        "page": page,
                        "snippet": f"{chart_title}（{chart_type}）",
                        "confidence": base_conf,
                        "locator": chart_locator,
                        "bbox": bbox if isinstance(bbox, list) else [],
                        "artifact_path": artifact_path,
                        "artifact_url": artifact_url,
                        "match_reason": "xlsx_chart_recommendation",
                    }
                )

        if not generated_chart_hits:
            return trace_hits
        return passthrough_hits + generated_chart_hits

    @staticmethod
    def _build_trace_stats(trace_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        object_counts: Dict[str, int] = {}
        display_counts: Dict[str, int] = {}
        pages: set[int] = set()
        for hit in trace_hits:
            if not isinstance(hit, dict):
                continue
            object_type = str(hit.get("object_type") or "").strip().lower() or "other"
            object_counts[object_type] = object_counts.get(object_type, 0) + 1

            if object_type == "figure":
                display_type = "image"
            elif object_type in {"field", "table", "chart"}:
                display_type = object_type
            else:
                display_type = "other"
            display_counts[display_type] = display_counts.get(display_type, 0) + 1

            try:
                page = int(hit.get("page", 0) or 0)
            except Exception:
                page = 0
            if page > 0:
                pages.add(page)
        return {
            "trace_hit_count": len(trace_hits),
            "trace_pages": sorted(pages),
            "trace_object_counts": object_counts,
            "trace_display_counts": display_counts,
        }

    def restore_response(
        self,
        *,
        file_name: str,
        file_hash: str,
        default_track: str,
        cached_payload: Dict[str, Any],
        normalize_soft_warnings: Callable[[Any], List[str]],
        promote_visual_diagnostics: Callable[[Dict[str, Any]], Dict[str, Any]],
        persist_assistant_payload_artifact: Callable[..., tuple[str, str]],
        persist_field_results_artifact: Callable[..., tuple[str, str]] | None = None,
        extraction_result_factory: Callable[[Dict[str, Any]], Any],
        document_response_factory: Callable[..., Any],
    ) -> Any:
        cached_result = cached_payload.get("result", {})
        cached_errors_raw = cached_payload.get("errors", [])
        cached_errors = [str(item) for item in cached_errors_raw] if isinstance(cached_errors_raw, list) else []
        cached_soft_warnings = normalize_soft_warnings(cached_payload.get("soft_warnings", []))
        cached_trace_hits_raw = cached_payload.get("trace_hits", [])
        cached_trace_hits = cached_trace_hits_raw if isinstance(cached_trace_hits_raw, list) else []
        cached_trace_hits = self._augment_cached_trace_hits_with_chart_hits(
            file_name=file_name,
            file_hash=file_hash,
            trace_hits=cached_trace_hits,
        )
        cached_trace_stats_raw = cached_payload.get("trace_stats", {})
        cached_trace_stats = cached_trace_stats_raw if isinstance(cached_trace_stats_raw, dict) else {}
        if cached_trace_hits:
            cached_trace_stats = {
                **cached_trace_stats,
                **self._build_trace_stats(cached_trace_hits),
            }
        cached_track = str(cached_payload.get("track", default_track))
        cached_diag_raw = cached_payload.get("diagnostics", cached_payload.get("metrics", {}))
        cached_diag = promote_visual_diagnostics(dict(cached_diag_raw) if isinstance(cached_diag_raw, dict) else {})
        for key in ("trace_hit_count", "trace_pages", "trace_object_counts", "trace_display_counts"):
            if key in cached_trace_stats:
                cached_diag[key] = cached_trace_stats.get(key)
        cached_tables = cached_payload.get("tables") if isinstance(cached_payload.get("tables"), list) else []
        cached_figures = cached_payload.get("figures") if isinstance(cached_payload.get("figures"), list) else []
        if (cached_tables or cached_figures) and not str(cached_diag.get("assistant_payload_artifact_path") or "").strip():
            artifact_path, artifact_url = persist_assistant_payload_artifact(
                file_name=file_name,
                file_hash=file_hash,
                table_blocks=cached_tables,
                figure_blocks=cached_figures,
            )
            if artifact_path:
                cached_diag["assistant_payload_artifact_path"] = artifact_path
                cached_diag["assistant_payload_artifact_url"] = artifact_url
                cached_diag["assistant_payload_version"] = "module2-assistant-payload-v1"
        if (
            callable(persist_field_results_artifact)
            and isinstance(cached_result, dict)
            and cached_result
            and not str(cached_diag.get("field_results_artifact_path") or "").strip()
        ):
            artifact_path, artifact_url = persist_field_results_artifact(
                file_name=file_name,
                file_hash=file_hash,
                track=cached_track,
                final_results=cached_result,
            )
            if artifact_path:
                cached_diag["field_results_artifact_path"] = artifact_path
                cached_diag["field_results_artifact_url"] = artifact_url
                cached_diag["field_results_artifact_version"] = "module2-field-results-v1"
                cached_diag["field_results_artifact_count"] = len(cached_result)
        return document_response_factory(
            file_name=file_name,
            file_hash=file_hash,
            track=cached_track,
            cached=True,
            result=extraction_result_factory(cached_result if isinstance(cached_result, dict) else {}),
            errors=cached_errors,
            soft_warnings=cached_soft_warnings,
            trace_hits=cached_trace_hits,
            trace_stats=cached_trace_stats,
            diagnostics=cached_diag,
        )
