from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "module2"
        / "app"
        / "core"
        / "table"
        / "table_metadata.py"
    )
    module_name = "_smart_doc_flow_module2_table_metadata"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


table_metadata = _load_module()


def test_table_metadata_extracts_header_units_and_tokens() -> None:
    assert table_metadata.normalize_token_for_compare("温度 (℃)") == "温度℃"
    assert table_metadata.normalize_token_for_compare_legacy("Flow / L-h") == "flowlh"
    assert table_metadata.extract_header_name_and_unit("温度 (℃)") == ("温度", "℃")
    assert table_metadata.extract_header_name_and_unit_legacy("流量/ L-h") == ("流量", "L-h")


def test_table_metadata_extract_number_meta_handles_percent_and_composite_text() -> None:
    percent_meta = table_metadata.extract_number_meta("12.5%", None)
    composite_meta = table_metadata.extract_number_meta("1730.4万人，固定资产原价8610.0亿", None)

    assert percent_meta["value_type"] == "number"
    assert percent_meta["numeric_value"] == 12.5
    assert percent_meta["ratio_value"] == 0.125
    assert percent_meta["detected_unit"] == "%"
    assert composite_meta["value_type"] == "text"
    assert composite_meta["numeric_value"] is None


def test_table_metadata_decorates_rows_with_numeric_fields() -> None:
    rows_payload = [
        {
            "row_index": 5,
            "cells": [
                {"col_index": 1, "text": "25", "ref_id": "r1c1"},
                {"col_index": 2, "text": "12.5%", "ref_id": "r1c2"},
            ],
        }
    ]

    decorated = table_metadata.decorate_rows_with_meta(rows_payload, ["温度(℃)", "占比"])

    assert decorated[0]["source_row_index"] == 5
    assert decorated[0]["cells"][0]["header"] == "温度"
    assert decorated[0]["cells"][0]["numeric_value"] == 25.0
    assert decorated[0]["cells"][0]["header_unit"] == "℃"
    assert decorated[0]["cells"][1]["header"] == "占比"
    assert decorated[0]["cells"][1]["ratio_value"] == 0.125
