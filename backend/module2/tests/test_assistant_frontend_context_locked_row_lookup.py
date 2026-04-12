from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1 import frontend_grounding


def _build_context() -> dict:
    return {
        "current_document": {
            "table_row_samples": [
                {
                    "table_id": "xlsx_t1",
                    "ref_id": "xlsx_t1_r4_c10",
                    "page": 1,
                    "headers": ["station_name", "PM10", "pollution-type"],
                    "rows": [
                        {
                            "row_index": 3,
                            "source_row_index": 4,
                            "ref_id": "xlsx_t1_r4_c10",
                            "cells": ["tengzhou-new2", "54", "Good"],
                        }
                    ],
                }
            ],
            "current_locked_object": {
                "lock_type": "table_row",
                "lock_quality": "high",
                "object_id": "xlsx_t1",
                "table_id": "xlsx_t1",
                "row_index": 3,
                "source_row_index": 4,
                "ref_id": "xlsx_t1_r4_c10",
            },
        }
    }


def test_locked_row_lookup_short_circuit_returns_pm10_value() -> None:
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message="Same locked row: what is PM10 value? Return value and ref_id only.",
        extra_context=_build_context(),
    )

    assert "PM10=54" in answer
    assert "ref_id=xlsx_t1_r4_c2" in answer
    assert "source_row_index=4" in answer


def test_locked_row_lookup_short_circuit_returns_pollution_type_value() -> None:
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message="Same locked row: what is pollution-type value? Return value and ref_id only.",
        extra_context=_build_context(),
    )

    assert "pollution-type=Good" in answer
    assert "ref_id=xlsx_t1_r4_c3" in answer
    assert "row_index=3" in answer


def test_locked_row_lookup_snapshot_should_short_circuit() -> None:
    question = "Same locked row: what is PM10 value? Return value and ref_id only."
    snapshot_answer = "PM10=54。证据：table_id=xlsx_t1, page=1, row_index=3, source_row_index=4, ref_id=xlsx_t1_r4_c2。"
    assert frontend_grounding.should_short_circuit_with_frontend_snapshot(
        user_message=question,
        snapshot_answer=snapshot_answer,
        extra_context=_build_context(),
    ) is True


def test_locked_row_lookup_pollution_type_fallback_from_adjacent_pm_column() -> None:
    context = {
        "current_document": {
            "table_row_samples": [
                {
                    "table_id": "xlsx_t1",
                    "ref_id": "xlsx_t1_r4_c10",
                    "page": 1,
                    "headers": ["h1", "h2", "h3"],
                    "rows": [
                        {
                            "row_index": 3,
                            "source_row_index": 4,
                            "ref_id": "xlsx_t1_r4_c10",
                            "cells": ["x", "颗粒物(PM10)", "良"],
                        }
                    ],
                }
            ],
            "current_locked_object": {
                "lock_type": "table_row",
                "lock_quality": "high",
                "object_id": "xlsx_t1",
                "table_id": "xlsx_t1",
                "row_index": 3,
                "source_row_index": 4,
                "ref_id": "xlsx_t1_r4_c10",
            },
        }
    }
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message="Same locked row: what is pollution-type value? Return value and ref_id only.",
        extra_context=context,
    )

    assert "=良" in answer
    assert "ref_id=xlsx_t1_r4_c3" in answer


def test_locked_row_lookup_keeps_late_columns_after_context_sanitize() -> None:
    headers = [f"h{i}" for i in range(1, 19)]
    cells = [f"v{i}" for i in range(1, 19)]
    cells[13] = "颗粒物(PM10)"  # c14
    cells[14] = "良"  # c15 (target)
    context = {
        "current_document": {
            "table_row_samples": [
                {
                    "table_id": "xlsx_t1",
                    "ref_id": "xlsx_t1_r4_c10",
                    "page": 1,
                    "headers": headers,
                    "rows": [
                        {
                            "row_index": 3,
                            "source_row_index": 4,
                            "ref_id": "xlsx_t1_r4_c10",
                            "cells": cells,
                        }
                    ],
                }
            ],
            "current_locked_object": {
                "lock_type": "table_row",
                "lock_quality": "high",
                "object_id": "xlsx_t1",
                "table_id": "xlsx_t1",
                "row_index": 3,
                "source_row_index": 4,
                "ref_id": "xlsx_t1_r4_c10",
            },
        }
    }
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message="Same locked row: what is pollution-type value? Return value and ref_id only.",
        extra_context=context,
    )

    assert "=良" in answer
    assert "ref_id=xlsx_t1_r4_c15" in answer
