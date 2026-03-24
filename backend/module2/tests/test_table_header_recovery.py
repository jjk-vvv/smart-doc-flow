from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.parser import NativeDocumentParser


def _build_parser() -> NativeDocumentParser:
    return NativeDocumentParser(max_pages=1)


def test_extract_headers_from_table_payload_prefers_header_rows_when_inline_headers_are_placeholders() -> None:
    parser = _build_parser()
    payload = {
        "headers": ["??", "??"],
        "header_rows": [["年份", "金额"]],
    }

    assert parser._extract_headers_from_table_payload(payload) == ["年份", "金额"]


def test_recover_low_signal_headers_uses_column_semantics_and_caption_hint() -> None:
    parser = _build_parser()
    rows_payload = [
        {
            "row_index": 1,
            "cells": [
                {"col_index": 1, "text": "城市"},
                {"col_index": 2, "text": "120"},
            ],
        },
        {
            "row_index": 2,
            "cells": [
                {"col_index": 1, "text": "农村"},
                {"col_index": 2, "text": "80"},
            ],
        },
    ]

    headers, recovered_rows = parser._recover_low_signal_headers(
        ["??", "??"],
        rows_payload,
        caption="城乡低保支出统计",
    )

    assert headers == ["地区", "城乡低保支出"]
    assert len(recovered_rows) == 2


def test_infer_headers_and_data_rows_does_not_swallow_first_data_row_as_fake_header() -> None:
    parser = _build_parser()
    rows_payload = [
        {
            "row_index": 1,
            "cells": [
                {"col_index": 1, "text": "城市"},
                {"col_index": 2, "text": "120"},
            ],
        },
        {
            "row_index": 2,
            "cells": [
                {"col_index": 1, "text": "农村"},
                {"col_index": 2, "text": "80"},
            ],
        },
    ]

    headers, data_rows = parser._infer_headers_and_data_rows(rows_payload)

    assert headers == ["地区", "数值"]
    assert len(data_rows) == 2


def test_build_tables_from_vision_payload_recovers_placeholder_headers() -> None:
    parser = _build_parser()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    built, next_idx = parser._build_tables_from_vision_payload(
        payload={
            "tables": [
                {
                    "headers": ["??", "??"],
                    "rows": [["城市", "120"], ["农村", "80"]],
                    "caption": "城乡低保支出统计",
                    "confidence": 0.9,
                }
            ]
        },
        page_no=5,
        table_idx=1,
        parts=parts,
        bbox_map=bbox_map,
        source_prefix="gv_p5",
    )

    assert next_idx == 2
    assert len(built) == 1
    assert built[0]["headers"] == ["地区", "城乡低保支出"]
    assert built[0]["rows"][0]["cells"][0]["header"] == "地区"
    assert built[0]["rows"][0]["cells"][1]["header"] == "城乡低保支出"
