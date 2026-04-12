from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.parsers.native_document_parser import NativeDocumentParser


def _build_parser() -> NativeDocumentParser:
    return NativeDocumentParser(max_pages=1)


def test_extract_headers_from_table_payload_prefers_header_rows_when_inline_headers_are_placeholders() -> None:
    parser = _build_parser()
    payload = {
        "headers": ["??", "??"],
        "header_rows": [["年份", "金额"]],
    }

    assert parser._table_payload.extract_headers_from_table_payload(payload) == ["年份", "金额"]


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

    headers, recovered_rows = parser._table_header.recover_low_signal_headers(
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

    headers, data_rows = parser._table_header.infer_headers_and_data_rows(rows_payload)

    assert headers == ["地区", "数值"]
    assert len(data_rows) == 2


def test_build_tables_from_vision_payload_recovers_placeholder_headers() -> None:
    parser = _build_parser()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    built, next_idx = parser._table_vision_payload.build_tables_from_vision_payload(
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


def test_recover_low_signal_headers_replaces_data_like_numeric_headers() -> None:
    parser = _build_parser()
    rows_payload = [
        {
            "row_index": 1,
            "cells": [
                {"col_index": 1, "text": "衣着"},
                {"col_index": 2, "text": "2642"},
                {"col_index": 3, "text": "1.6"},
            ],
        },
        {
            "row_index": 2,
            "cells": [
                {"col_index": 1, "text": "居住"},
                {"col_index": 2, "text": "5581"},
                {"col_index": 3, "text": "0.8"},
            ],
        },
    ]

    headers, recovered_rows = parser._table_header.recover_low_signal_headers(
        ["食品烟酒", "10482", "2.9"],
        rows_payload,
    )

    assert headers == ["类别", "数值_1", "数值_2"]
    assert len(recovered_rows) == 2
    assert parser._table_header.row_payload_texts(recovered_rows[0], 3) == ["衣着", "2642", "1.6"]


def test_recover_low_signal_headers_promotes_temporal_header_row_after_caption_header() -> None:
    parser = _build_parser()
    rows_payload = [
        {
            "row_index": 1,
            "cells": [
                {"col_index": 1, "text": "指标名称"},
                {"col_index": 2, "text": "2020 年"},
                {"col_index": 3, "text": "2021 年"},
            ],
        },
        {
            "row_index": 2,
            "cells": [
                {"col_index": 1, "text": "居民消费价格"},
                {"col_index": 2, "text": "2.4"},
                {"col_index": 3, "text": "1.7"},
            ],
        },
    ]

    headers, recovered_rows = parser._table_header.recover_low_signal_headers(
        ["表1 2021 年居民消费和商品零售价格涨跌幅度（单位：%）", "col_2", "col_3"],
        rows_payload,
        caption="表1 2021 年居民消费和商品零售价格涨跌幅度（单位：%）",
    )

    assert headers == ["指标名称", "2020 年", "2021 年"]
    assert len(recovered_rows) == 1
    assert parser._table_header.row_payload_texts(recovered_rows[0], 3) == ["居民消费价格", "2.4", "1.7"]
