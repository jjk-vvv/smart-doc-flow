from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1 import frontend_grounding


def test_conditional_row_lookup_short_circuit_requires_evidence_style_answer() -> None:
    question = (
        "请直接查看 xlsx_t1 表格，站点名称为滁州新二中的 PM10 监测值是多少？"
        "请写明表格、页码、表内行号、原始行号和 ref_id。"
    )
    # Generic one-field answer should not be trusted for conditional row lookup.
    assert frontend_grounding.should_short_circuit_with_frontend_snapshot(
        user_message=question,
        snapshot_answer="站点名称是 滕州北辛中学。",
    ) is False
    # Missing-evidence answer can be short-circuited to avoid hallucination.
    assert frontend_grounding.should_short_circuit_with_frontend_snapshot(
        user_message=question,
        snapshot_answer="在当前可见表格证据中未找到对应记录，暂时无法给出该字段。",
    ) is True


def test_snapshot_answer_returns_missing_when_row_level_evidence_absent() -> None:
    question = (
        "请直接查看 xlsx_t1 表格，站点名称为滁州新二中的 PM10 监测值是多少？"
        "请写明表格、页码、表内行号、原始行号和 ref_id。"
    )
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message=question,
        extra_context={
            "current_document": {
                "file_name": "2025山东省环境空气质量监测数据信息.xlsx",
                "top_fields": [
                    {"label": "站点名称", "value": "滕州北辛中学", "confidence": 97, "page": 1},
                    {"label": "PM10 监测值", "value": "34", "confidence": 95, "page": 1},
                ],
            }
        },
    )
    assert "未包含可核验的行级表格证据" in answer
    assert "页码/行号/ref_id" in answer


def test_snapshot_answer_returns_value_with_provenance_for_conditional_row_lookup() -> None:
    question = (
        "请直接查看 xlsx_t1 表格，站点名称为滕州北辛中学的 PM10 监测值是多少？"
        "请写明表格、页码、表内行号、原始行号和 ref_id。"
    )
    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message=question,
        extra_context={
            "current_document": {
                "file_name": "2025山东省环境空气质量监测数据信息.xlsx",
                "table_row_samples": [
                    {
                        "table_id": "xlsx_t1",
                        "ref_id": "ref_table_xlsx_t1",
                        "page": 1,
                        "headers": ["站点名称", "PM10 监测值", "城市"],
                        "rows": [
                            {"row_index": 17, "cells": ["滕州北辛中学", "34", "枣庄市"]},
                            {"row_index": 18, "cells": ["嘉祥县政府", "22", "济宁市"]},
                        ],
                    }
                ],
            }
        },
    )
    assert "PM10 监测值=34" in answer
    assert "table_id=xlsx_t1" in answer
    assert "row_index=17" in answer
    assert "ref_id=ref_table_xlsx_t1" in answer
