from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


nonpdf_table_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "format", "nonpdf_content_runtime.py"],
    "_smart_doc_flow_module2_nonpdf_table_runtime",
)

NonPdfTableRuntime = nonpdf_table_runtime_module.NonPdfTableRuntime


def _build_runtime() -> NonPdfTableRuntime:
    def infer_headers_and_data_rows(rows_payload: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
        return (
            ["地区", "数值"],
            [
                {"row_index": 1, "cells": rows_payload[0]["cells"]},
                {"row_index": 2, "cells": rows_payload[1]["cells"]},
            ],
        )

    def decorate_rows_with_meta(rows_payload: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
        decorated: list[dict[str, Any]] = []
        for row in rows_payload:
            cells = []
            for cell in row.get("cells", []):
                col_index = int(cell.get("col_index", 0) or 0)
                cells.append(
                    {
                        **cell,
                        "header": headers[col_index - 1] if 0 < col_index <= len(headers) else "",
                    }
                )
            if cells:
                decorated.append({"row_index": int(row.get("row_index", 0) or 0), "cells": cells})
        return decorated

    return NonPdfTableRuntime(
        infer_headers_and_data_rows=infer_headers_and_data_rows,
        drop_redundant_header_like_rows=lambda rows, headers: rows,
        decorate_rows_with_meta=decorate_rows_with_meta,
        build_header_meta=lambda headers: [
            {"col_index": idx, "raw": header, "name": header, "name_norm": header.lower(), "unit": None}
            for idx, header in enumerate(headers, start=1)
        ],
    )


def test_nonpdf_table_runtime_builds_table_block_with_extra_fields() -> None:
    runtime = _build_runtime()
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

    table = runtime.build_table_block(
        table_id="xlsx_t1",
        source="xlsx",
        page=1,
        rows_payload=rows_payload,
        extra_fields={"sheet_index": 1, "sheet_name": "Sheet1"},
    )

    assert table is not None
    assert table["table_id"] == "xlsx_t1"
    assert table["source"] == "xlsx"
    assert table["sheet_index"] == 1
    assert table["sheet_name"] == "Sheet1"
    assert table["headers"] == ["地区", "数值"]
    assert table["row_count"] == 2
    assert table["col_count"] == 2
    assert table["rows"][0]["cells"][0]["header"] == "地区"


def test_nonpdf_table_runtime_returns_none_when_no_rows_survive() -> None:
    runtime = NonPdfTableRuntime(
        infer_headers_and_data_rows=lambda rows_payload: (["地区"], rows_payload),
        drop_redundant_header_like_rows=lambda rows, headers: rows,
        decorate_rows_with_meta=lambda rows, headers: [],
        build_header_meta=lambda headers: [],
    )

    table = runtime.build_table_block(
        table_id="docx_t1",
        source="docx",
        page=1,
        rows_payload=[{"row_index": 1, "cells": [{"col_index": 1, "text": "城市"}]}],
    )

    assert table is None
