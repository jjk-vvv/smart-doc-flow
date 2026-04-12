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
                    "ref_id": "xlsx_t1_r2_c1",
                    "page": 1,
                    "headers": ["站点名称", "PM10监测值", "污染类型"],
                    "rows": [
                        {
                            "row_index": 1,
                            "source_row_index": 2,
                            "ref_id": "xlsx_t1_r2_c1",
                            "cells": ["滕州北辛中学", "32", "优"],
                        },
                        {
                            "row_index": 2,
                            "source_row_index": 4,
                            "ref_id": "xlsx_t1_r4_c1",
                            "cells": ["滕州新二中", "54", "良"],
                        },
                    ],
                }
            ]
        }
    }


def test_conditional_lookup_question_detects_loose_row_phrase() -> None:
    question = "请在 xlsx_t1 表格中定位“站点名称=滕州新二中”这一行，返回 PM10监测值 和 ref_id。"
    assert frontend_grounding.is_conditional_row_lookup_question(question) is True


def test_extract_conditional_lookup_parts_from_loose_row_phrase() -> None:
    question = "请在 xlsx_t1 表格中定位“站点名称=滕州新二中”这一行，返回 PM10监测值 和 ref_id。"
    parts = frontend_grounding._extract_conditional_lookup_parts(question)

    assert parts.get("condition_field") == "站点名称"
    assert parts.get("condition_value") == "滕州新二中"
    assert parts.get("target_field") == "PM10监测值"


def test_conditional_lookup_returns_row_value_and_resolved_ref_id() -> None:
    question = "请在 xlsx_t1 表格中定位“站点名称=滕州新二中”这一行，返回 PM10监测值 和 ref_id。"
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message=question,
        extra_context=_build_context(),
    )

    assert "PM10监测值=54" in answer
    assert "table_id=xlsx_t1" in answer
    assert "row_index=2" in answer
    assert "source_row_index=4" in answer
    assert "ref_id=xlsx_t1_r4_c2" in answer

