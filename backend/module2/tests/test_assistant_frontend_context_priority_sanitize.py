from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1 import frontend_grounding


def test_conditional_lookup_keeps_table_row_samples_when_keys_are_late() -> None:
    current_document = {
        # Fill many keys first to simulate noisy frontend payload ordering.
        **{f"noise_{i}": f"value_{i}" for i in range(1, 18)},
        "table_row_samples": [
            {
                "table_id": "xlsx_t1",
                "ref_id": "xlsx_t1_r5_c2",
                "page": 1,
                "headers": ["站点名称", "PM10监测值", "污染类型"],
                "rows": [
                    {
                        "row_index": 5,
                        "source_row_index": 5,
                        "cells": ["滨州新二中", "54", "优"],
                    }
                ],
            }
        ],
    }
    context = {"current_document": current_document}

    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message="请直接查看 xlsx_t1 表格，站点名称为滨州新二中的 PM10监测值是多少？请给出 ref_id。",
        extra_context=context,
    )

    assert "PM10监测值=54" in answer
    assert "ref_id=xlsx_t1_r5_c2" in answer
    assert "当前快照未包含可核验的行级表格证据" not in answer


def test_conditional_lookup_uses_xlsx_manifest_fallback(monkeypatch) -> None:
    manifest_payload = {
        "sheets": [
            {
                "sheet_index": 1,
                "rows_artifact_path": "mock_rows.json",
            }
        ]
    }
    rows_payload = {
        "headers": ["站点名称", "PM10监测值", "污染类型"],
        "rows": [
            {
                "row_index": 5,
                "source_row_index": 5,
                "cells": [
                    {"col_index": 1, "text": "滨州新二中", "ref_id": "xlsx_t1_r5_c1"},
                    {"col_index": 2, "text": "54", "ref_id": "xlsx_t1_r5_c2"},
                    {"col_index": 3, "text": "优", "ref_id": "xlsx_t1_r5_c3"},
                ],
            }
        ],
    }

    monkeypatch.setattr(
        frontend_grounding,
        "load_xlsx_workbook_manifest",
        lambda _path: manifest_payload,
    )
    monkeypatch.setattr(
        frontend_grounding,
        "load_xlsx_sheet_rows_artifact",
        lambda _path: rows_payload,
    )

    context = {
        "current_document": {
            "file_name": "mock.xlsx",
            "file_hash": "mock_hash",
            "diagnostics": {
                "xlsx_workbook_manifest_path": "mock_manifest.json",
            },
        }
    }

    answer = frontend_grounding.build_frontend_snapshot_answer(
        user_message="请直接查看 xlsx_t1 表格，站点名称为滨州新二中的 PM10监测值是多少？请给出 ref_id。",
        extra_context=context,
    )

    assert "PM10监测值=54" in answer
    assert "ref_id=xlsx_t1_r5_c2" in answer
