from __future__ import annotations

import sys
from pathlib import Path

MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.runtime.document_trace_runtime import TraceLocatorTextRuntime


def test_table_header_labels_dedupes_semantically_equivalent_unit_labels() -> None:
    runtime = TraceLocatorTextRuntime()
    table = {
        "table_id": "pdf_fitz_t13",
        "headers": ["类别", "绝对值（元）", "比上年增长（%）"],
        "header_meta": [
            {"name": "类别", "unit": None},
            {"name": "绝对值", "unit": "元"},
            {"name": "比上年增长", "unit": "%"},
        ],
    }

    assert runtime.table_header_labels(table, max_items=4) == [
        "类别",
        "绝对值（元）",
        "比上年增长（%）",
    ]


def test_table_locator_texts_summary_uses_deduped_header_labels() -> None:
    runtime = TraceLocatorTextRuntime()
    table = {
        "table_id": "pdf_fitz_t13",
        "headers": ["类别", "绝对值（元）", "比上年增长（%）"],
        "header_meta": [
            {"name": "类别", "unit": None},
            {"name": "绝对值", "unit": "元"},
            {"name": "比上年增长", "unit": "%"},
        ],
        "rows": [
            {
                "cells": [
                    {"text": "居民人均消费支出"},
                    {"text": "40313"},
                    {"text": "3.1"},
                ]
            }
        ],
    }

    locator = runtime.table_locator_texts(table)

    assert locator["header_labels"] == ["类别", "绝对值（元）", "比上年增长（%）"]
    assert "类别 | 绝对值（元） | 比上年增长（%）" in locator["summary"]
    assert "绝对值 (元)" not in locator["summary"]
    assert "比上年增长 (%)" not in locator["summary"]
