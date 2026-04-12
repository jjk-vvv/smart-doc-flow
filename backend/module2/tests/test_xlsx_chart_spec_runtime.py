from __future__ import annotations

import sys
from pathlib import Path

MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.integration.cached_extraction_restore_runtime import CachedExtractionRestoreRuntime
from app.runtime.document_trace_hits_runtime import DocumentTraceHitsRuntime


def _build_runtime() -> DocumentTraceHitsRuntime:
    return DocumentTraceHitsRuntime(
        normalize_bbox=lambda *_args, **_kwargs: [],
        page_from_bbox=lambda _bbox: 1,
        is_meaningful_bbox=lambda _bbox: False,
        resolve_trace_artifact_ref=lambda _payload: (None, None),
    )


def test_runtime_chart_specs_skip_identifier_metric_column() -> None:
    runtime = _build_runtime()
    table = {
        "source": "xlsx",
        "source_headers": ["order_id", "order_date", "sales_amount"],
        "rows": [
            {
                "cells": [
                    {"col_index": 1, "text": "1001", "numeric_value": 1001},
                    {"col_index": 2, "text": "2026-04-01"},
                    {"col_index": 3, "text": "120.5", "numeric_value": 120.5},
                ]
            },
            {
                "cells": [
                    {"col_index": 1, "text": "1002", "numeric_value": 1002},
                    {"col_index": 2, "text": "2026-04-02"},
                    {"col_index": 3, "text": "138.0", "numeric_value": 138.0},
                ]
            },
            {
                "cells": [
                    {"col_index": 1, "text": "1003", "numeric_value": 1003},
                    {"col_index": 2, "text": "2026-04-03"},
                    {"col_index": 3, "text": "149.2", "numeric_value": 149.2},
                ]
            },
        ],
    }

    specs = runtime._build_xlsx_chart_specs(table, max_specs=3)
    line_specs = [item for item in specs if str(item.get("chart_type")).lower() == "line"]
    assert line_specs, "expected at least one line chart spec"
    primary = line_specs[0]
    assert "order_id" not in [str(x).strip().lower() for x in primary.get("y_fields", [])]
    assert str(primary.get("x_axis_label") or "").strip()
    assert str(primary.get("y_axis_label") or "").strip()
    assert str(primary.get("trend_summary") or "").strip()


def test_cached_restore_chart_specs_align_with_runtime_fields() -> None:
    hit = {
        "object_type": "table",
        "locator": {
            "dataframe": {
                "headers": ["order_id", "order_date", "sales_amount"],
                "rows": [
                    ["1001", "2026-04-01", "120.5"],
                    ["1002", "2026-04-02", "138.0"],
                    ["1003", "2026-04-03", "149.2"],
                ],
            }
        },
    }

    specs = CachedExtractionRestoreRuntime._build_chart_specs_from_table_hit(hit, max_specs=3)
    line_specs = [item for item in specs if str(item.get("chart_type")).lower() == "line"]
    assert line_specs, "expected at least one line chart spec in cached restore path"
    primary = line_specs[0]
    assert "order_id" not in [str(x).strip().lower() for x in primary.get("y_fields", [])]
    assert str(primary.get("x_axis_label") or "").strip()
    assert str(primary.get("y_axis_label") or "").strip()
    assert str(primary.get("trend_summary") or "").strip()


def test_runtime_chart_specs_skip_time_like_metric_column() -> None:
    runtime = _build_runtime()
    table = {
        "source": "xlsx",
        "source_headers": ["order_date", "order_time", "sales_amount"],
        "rows": [
            {
                "cells": [
                    {"col_index": 1, "text": "2026-04-01"},
                    {"col_index": 2, "text": "08:00:00"},
                    {"col_index": 3, "text": "100", "numeric_value": 100},
                ]
            },
            {
                "cells": [
                    {"col_index": 1, "text": "2026-04-02"},
                    {"col_index": 2, "text": "09:30:00"},
                    {"col_index": 3, "text": "120", "numeric_value": 120},
                ]
            },
            {
                "cells": [
                    {"col_index": 1, "text": "2026-04-03"},
                    {"col_index": 2, "text": "10:15:00"},
                    {"col_index": 3, "text": "135", "numeric_value": 135},
                ]
            },
        ],
    }

    specs = runtime._build_xlsx_chart_specs(table, max_specs=3)
    line_specs = [item for item in specs if str(item.get("chart_type")).lower() == "line"]
    assert line_specs, "expected at least one line chart spec"
    primary = line_specs[0]
    metric_fields = [str(x).strip().lower() for x in primary.get("y_fields", [])]
    assert "order_time" not in metric_fields


def test_cached_restore_rebuilds_stale_xlsx_chart_hits() -> None:
    table_hit = {
        "object_type": "table",
        "object_id": "xlsx_table_1",
        "page": 1,
        "locator": {
            "table_id": "xlsx_table_1",
            "ref_id": "xlsx_t1_r2_c1",
            "dataframe_source": "xlsx_sheet_rows",
            "dataframe": {
                "headers": ["order_id", "order_date", "order_time", "sales_amount"],
                "rows": [
                    ["1001", "2026-04-01", "08:00:00", "100"],
                    ["1002", "2026-04-02", "09:30:00", "120"],
                    ["1003", "2026-04-03", "10:15:00", "135"],
                ],
            },
        },
    }
    stale_chart_hit = {
        "object_type": "chart",
        "object_id": "xlsx_table_1_chart_1",
        "page": 1,
        "locator": {
            "table_id": "xlsx_table_1",
            "chart_spec": {
                "chart_type": "line",
                "title": "order_id trend",
                "x_field": "order_date",
                "y_fields": ["order_id"],
            },
        },
    }

    rebuilt = CachedExtractionRestoreRuntime._augment_cached_trace_hits_with_chart_hits(
        file_name="demo.xlsx",
        file_hash="demo_hash",
        trace_hits=[table_hit, stale_chart_hit],
    )

    chart_hits = [item for item in rebuilt if str(item.get("object_type")).lower() == "chart"]
    assert chart_hits, "expected chart hits after cached restore rebuild"
    chart_spec = ((chart_hits[0].get("locator") or {}).get("chart_spec") or {})
    assert str(chart_spec.get("x_axis_label") or "").strip()
    assert str(chart_spec.get("y_axis_label") or "").strip()
    assert str(chart_spec.get("trend_summary") or "").strip()
    y_fields = [str(x).strip().lower() for x in chart_spec.get("y_fields", [])]
    assert "order_id" not in y_fields


def test_runtime_category_chart_filters_placeholder_values_and_uses_mean() -> None:
    runtime = _build_runtime()
    table = {
        "source": "xlsx",
        "source_headers": ["category", "metric_value"],
        "rows": [
            {"cells": [{"col_index": 1, "text": "A"}, {"col_index": 2, "text": "10", "numeric_value": 10}]},
            {"cells": [{"col_index": 1, "text": "A"}, {"col_index": 2, "text": "20", "numeric_value": 20}]},
            {"cells": [{"col_index": 1, "text": "B"}, {"col_index": 2, "text": "30", "numeric_value": 30}]},
            {"cells": [{"col_index": 1, "text": "-"}, {"col_index": 2, "text": "999", "numeric_value": 999}]},
            {"cells": [{"col_index": 1, "text": "—"}, {"col_index": 2, "text": "888", "numeric_value": 888}]},
        ],
    }

    specs = runtime._build_xlsx_chart_specs(table, max_specs=3)
    bar_specs = [item for item in specs if str(item.get("chart_type")).lower() == "bar"]
    assert bar_specs, "expected at least one bar chart spec"
    bar = bar_specs[0]
    x_values = [str(x).strip() for x in bar.get("x_values", [])]
    assert "-" not in x_values and "—" not in x_values
    assert str(bar.get("aggregation") or "") == "mean_by_category"
    first_series = (bar.get("series") or [{}])[0]
    values_by_x = dict(zip(x_values, list(first_series.get("data") or [])))
    assert values_by_x.get("A") == 15


def test_runtime_scatter_chart_emits_domain_for_outlier_heavy_data() -> None:
    runtime = _build_runtime()
    rows = []
    for idx in range(1, 61):
        rows.append(
            {
                "cells": [
                    {"col_index": 1, "text": str(1000 + idx), "numeric_value": 1000 + idx},
                    {"col_index": 2, "text": str(18 + (idx % 9)), "numeric_value": 18 + (idx % 9)},
                    {"col_index": 3, "text": str(10 + (idx % 7)), "numeric_value": 10 + (idx % 7)},
                ]
            }
        )
    rows.append(
        {
            "cells": [
                {"col_index": 1, "text": "1999", "numeric_value": 1999},
                {"col_index": 2, "text": "10000", "numeric_value": 10000},
                {"col_index": 3, "text": "5000", "numeric_value": 5000},
            ]
        }
    )
    table = {
        "source": "xlsx",
        "source_headers": ["sensor_id", "pm25", "no2"],
        "rows": rows,
    }

    specs = runtime._build_xlsx_chart_specs(table, max_specs=3)
    scatter_specs = [item for item in specs if str(item.get("chart_type")).lower() == "scatter"]
    assert scatter_specs, "expected at least one scatter chart spec"
    scatter = scatter_specs[0]
    assert isinstance(scatter.get("x_domain"), list)
    assert isinstance(scatter.get("y_domain"), list)
    x_domain = scatter.get("x_domain") or []
    y_domain = scatter.get("y_domain") or []
    assert len(x_domain) == 2 and x_domain[1] > x_domain[0]
    assert len(y_domain) == 2 and y_domain[1] > y_domain[0]
    assert float(y_domain[1]) < 5000
