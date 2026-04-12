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
                    "headers": ["国家/地区", "日期", "病例数", "死亡数"],
                    "rows": [
                        {
                            "row_index": 1,
                            "source_row_index": 1,
                            "ref_id": "xlsx_t1_r1_c1",
                            "cells": ["Albania", "2020-02-25 00:00:00", "2", ""],
                        },
                        {
                            "row_index": 2,
                            "source_row_index": 2,
                            "ref_id": "xlsx_t1_r2_c1",
                            "cells": ["Albania", "2020-02-26 00:00:00", "5", ""],
                        },
                        {
                            "row_index": 3,
                            "source_row_index": 3,
                            "ref_id": "xlsx_t1_r3_c1",
                            "cells": ["Algeria", "2020-02-25 00:00:00", "1", ""],
                        },
                    ],
                }
            ]
        }
    }


def test_extract_conditional_lookup_parts_supports_slash_and_multi_conditions() -> None:
    question = "请在 xlsx_t1 表格中定位“国家/地区=Albania 且 日期=2020-02-25”这一行，返回 病例数 的值和 ref_id。"
    parts = frontend_grounding._extract_conditional_lookup_parts(question)

    assert parts.get("condition_field") == "国家/地区"
    assert parts.get("condition_value") == "Albania"
    assert parts.get("target_field") == "病例数"
    pairs = parts.get("condition_pairs")
    assert isinstance(pairs, list)
    assert len(pairs) >= 2
    assert pairs[0] == {"field": "国家/地区", "value": "Albania"}
    assert pairs[1] == {"field": "日期", "value": "2020-02-25"}


def test_conditional_lookup_uses_all_conditions_for_unique_row_match() -> None:
    question = "请在 xlsx_t1 表格中定位“国家/地区=Albania 且 日期=2020-02-25”这一行，返回 病例数 的值和 ref_id。"
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message=question,
        extra_context=_build_context(),
    )

    assert "病例数=2" in answer
    assert "table_id=xlsx_t1" in answer
    assert "row_index=1" in answer
    assert "source_row_index=1" in answer
    assert "ref_id=xlsx_t1_r1_c3" in answer

