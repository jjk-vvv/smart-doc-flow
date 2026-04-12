from __future__ import annotations

import asyncio
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.agent.graph import ExtractionGraph
from app.core.schema.field_naming import detect_domain_template, normalize_field_name
from app.composition.application import module2_bootstrap_components
from app.composition.application import module2_main_schema_resolution_bundle


def test_ratio_like_xlsx_column_is_inferred_as_string() -> None:
    bundle = module2_bootstrap_components.schema_pipeline_bundle.schema_inference_bundle
    table_blocks = [
        {
            "source": "xlsx",
            "headers": ["地区", "招考人数", "面试人员比例"],
            "header_meta": [
                {"col_index": 1, "name": "地区", "unit": None},
                {"col_index": 2, "name": "招考人数", "unit": None},
                {"col_index": 3, "name": "面试人员比例", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "江苏"},
                        {"col_index": 2, "text": "2"},
                        {"col_index": 3, "text": "3:1"},
                    ],
                }
            ],
        }
    ]

    inferred = bundle.infer_schema_fields_heuristic("", table_blocks, [], max_fields=6)

    assert inferred["招考人数"] == "integer"
    assert inferred["面试人员比例"] == "string"


def test_spreadsheet_table_prefill_can_skip_llm_when_headers_are_strong_matches() -> None:
    graph = ExtractionGraph()

    async def _should_not_run(*args, **kwargs):
        raise AssertionError("LLM table extraction should be skipped for resolved spreadsheet fields")

    graph._invoke_with_model_fallback = _should_not_run  # type: ignore[method-assign]

    state = {
        "markdown": "",
        "bbox_map": {
            "xlsx_t1_r1_c1": [1.0, 0.0, 0.0, 0.1, 0.1],
            "xlsx_t1_r1_c2": [1.0, 0.1, 0.0, 0.1, 0.1],
            "xlsx_t1_r1_c3": [1.0, 0.2, 0.0, 0.1, 0.1],
        },
        "table_blocks": [
            {
                "table_id": "xlsx_t1",
                "source": "xlsx",
                "page": 1,
                "quality": 0.98,
                "headers": ["地区", "招考人数", "面试人员比例"],
                "header_meta": [
                    {"col_index": 1, "name": "地区", "unit": None},
                    {"col_index": 2, "name": "招考人数", "unit": None},
                    {"col_index": 3, "name": "面试人员比例", "unit": None},
                ],
                "rows": [
                    {
                        "row_index": 1,
                        "cells": [
                            {
                                "col_index": 1,
                                "text": "江苏",
                                "ref_id": "xlsx_t1_r1_c1",
                                "header": "地区",
                            },
                            {
                                "col_index": 2,
                                "text": "2",
                                "ref_id": "xlsx_t1_r1_c2",
                                "header": "招考人数",
                                "numeric_value": 2.0,
                            },
                            {
                                "col_index": 3,
                                "text": "3:1",
                                "ref_id": "xlsx_t1_r1_c3",
                                "header": "面试人员比例",
                            },
                        ],
                    }
                ],
            }
        ],
        "table_summary": "",
        "field_hints": {},
        "schema": {
            "fields": {
                "地区": "string",
                "招考人数": "integer",
                "面试人员比例": "string",
            }
        },
        "results": {},
        "errors": [],
        "soft_warnings": [],
        "retries": 0,
        "max_retries": 2,
    }

    updated = asyncio.run(graph.table_extract_node(state))

    assert updated["results"]["地区"]["value"] == "江苏"
    assert updated["results"]["招考人数"]["value"] == 2
    assert updated["results"]["面试人员比例"]["value"] == "3:1"


def test_ratio_like_auto_result_is_not_filtered_as_low_value() -> None:
    bundle = module2_bootstrap_components.schema_pipeline_bundle.result_filter_bundle

    filtered, removed = bundle.filter_low_value_auto_results(
        {
            "面试人员比例": {
                "value": "3:1",
                "confidence": 0.94,
                "source_ref_id": "xlsx_t1_r1_c3",
                "bbox": [1.0, 0.2, 0.0, 0.1, 0.1],
            }
        }
    )

    assert "面试人员比例" in filtered
    assert not removed


def test_xlsx_field_naming_normalizes_business_abbreviations() -> None:
    com_id = normalize_field_name("com id", template_hint="xlsx_business_ledger")
    order_time = normalize_field_name("order time", template_hint="xlsx_business_ledger")
    special_discount = normalize_field_name("spe discount", template_hint="xlsx_business_ledger")

    assert com_id["canonical_label"] == "SKU"
    assert order_time["canonical_label"] == "订单时间"
    assert special_discount["canonical_label"] == "优惠折扣"
    assert special_discount["field_type"] == "number"


def test_xlsx_schema_resolution_prefers_canonical_business_labels() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": ["order_id", "com id", "order_date", "order time", "spe discount"],
            "header_meta": [
                {"col_index": 1, "name": "order_id", "unit": None},
                {"col_index": 2, "name": "com id", "unit": None},
                {"col_index": 3, "name": "order_date", "unit": None},
                {"col_index": 4, "name": "order time", "unit": None},
                {"col_index": 5, "name": "spe discount", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "P1696644"},
                        {"col_index": 2, "text": "SP06691157"},
                        {"col_index": 3, "text": "2023-09-08"},
                        {"col_index": 4, "text": "08:49:08"},
                        {"col_index": 5, "text": "0"},
                    ],
                }
            ],
        }
    ]

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 8},
            file_name="电商销售数据.xlsx",
            markdown="",
            table_blocks=table_blocks,
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template="xlsx_business_ledger",
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert "SKU" in fields
    assert "订单日期" in fields
    assert "订单时间" in fields
    assert "优惠折扣" in fields
    assert "com id" not in fields
    assert "order time" not in fields
    assert "spe discount" not in fields
    assert meta["rule_field_count"] >= 4
    assert meta["source"] == "rules+heuristic"
    assert meta["field_name_mappings"]["com id"] == "SKU"
    assert meta["field_name_mappings"]["order time"] == "订单时间"
    assert meta["field_name_mappings"]["spe discount"] == "优惠折扣"


def test_recruitment_template_and_rule_candidates_activate_for_job_sheet() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": [
                "\u5730\u533a",
                "\u90e8\u95e8\u4ee3\u7801",
                "\u90e8\u95e8\u540d\u79f0",
                "\u62db\u8003\u804c\u4f4d",
                "\u804c\u4f4d\u4ee3\u7801",
                "\u62db\u8003\u4eba\u6570",
                "\u4e13\u4e1a",
                "\u5b66\u5386",
                "\u5b66\u4f4d",
                "\u9762\u8bd5\u4eba\u5458\u6bd4\u4f8b",
            ],
            "header_meta": [
                {"col_index": 1, "name": "\u5730\u533a", "unit": None},
                {"col_index": 2, "name": "\u90e8\u95e8\u4ee3\u7801", "unit": None},
                {"col_index": 3, "name": "\u90e8\u95e8\u540d\u79f0", "unit": None},
                {"col_index": 4, "name": "\u62db\u8003\u804c\u4f4d", "unit": None},
                {"col_index": 5, "name": "\u804c\u4f4d\u4ee3\u7801", "unit": None},
                {"col_index": 6, "name": "\u62db\u8003\u4eba\u6570", "unit": None},
                {"col_index": 7, "name": "\u4e13\u4e1a", "unit": None},
                {"col_index": 8, "name": "\u5b66\u5386", "unit": None},
                {"col_index": 9, "name": "\u5b66\u4f4d", "unit": None},
                {"col_index": 10, "name": "\u9762\u8bd5\u4eba\u5458\u6bd4\u4f8b", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "\u6c5f\u82cf"},
                        {"col_index": 2, "text": "1791300101"},
                        {"col_index": 3, "text": "\u7a0e\u52a1\u603b\u5c40"},
                        {"col_index": 4, "text": "\u7efc\u5408\u7ba1\u7406\u5c97"},
                        {"col_index": 5, "text": "300110001"},
                        {"col_index": 6, "text": "2"},
                        {"col_index": 7, "text": "\u7ecf\u6d4e\u5b66"},
                        {"col_index": 8, "text": "\u672c\u79d1"},
                        {"col_index": 9, "text": "\u5b66\u58eb"},
                        {"col_index": 10, "text": "3:1"},
                    ],
                }
            ],
        }
    ]

    detected = detect_domain_template(
        file_name="2025\u5e74\u56fd\u8003\u804c\u4f4d\u8868\uff08\u8282\u9009\uff09.xlsx",
        markdown="",
        table_blocks=table_blocks,
        figure_blocks=[],
    )

    assert detected == "recruitment_hr_table"

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 10},
            file_name="2025\u5e74\u56fd\u8003\u804c\u4f4d\u8868\uff08\u8282\u9009\uff09.xlsx",
            markdown="",
            table_blocks=table_blocks,
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert meta["rule_field_count"] >= 6
    assert meta["source"] == "rules+heuristic"
    assert "\u90e8\u95e8\u4ee3\u7801" in fields
    assert "\u90e8\u95e8\u540d\u79f0" in fields
    assert "\u62db\u8003\u804c\u4f4d" in fields
    assert "\u804c\u4f4d\u4ee3\u7801" in fields
    assert "\u62db\u8003\u4eba\u6570" in fields
    assert "\u9762\u8bd5\u4eba\u5458\u6bd4\u4f8b" in fields


def test_clinical_patient_template_and_rule_candidates_activate_for_diabetes_sheet() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": [
                "\u5c31\u8bcaID",
                "\u60a3\u8005\u7f16\u53f7",
                "\u6027\u522b",
                "\u5e74\u9f84",
                "\u4f53\u91cd",
                "\u4f4f\u9662\u5929\u6570",
                "\u8bca\u65ad\u6570\u91cf",
                "\u8840\u6e05\u8461\u8404\u7cd6\u6700\u5927\u503c",
                "\u7cd6\u5316\u8840\u7ea2\u86cb\u767d\u7ed3\u679c",
            ],
            "header_meta": [
                {"col_index": 1, "name": "\u5c31\u8bcaID", "unit": None},
                {"col_index": 2, "name": "\u60a3\u8005\u7f16\u53f7", "unit": None},
                {"col_index": 3, "name": "\u6027\u522b", "unit": None},
                {"col_index": 4, "name": "\u5e74\u9f84", "unit": None},
                {"col_index": 5, "name": "\u4f53\u91cd", "unit": None},
                {"col_index": 6, "name": "\u4f4f\u9662\u5929\u6570", "unit": None},
                {"col_index": 7, "name": "\u8bca\u65ad\u6570\u91cf", "unit": None},
                {"col_index": 8, "name": "\u8840\u6e05\u8461\u8404\u7cd6\u6700\u5927\u503c", "unit": None},
                {"col_index": 9, "name": "\u7cd6\u5316\u8840\u7ea2\u86cb\u767d\u7ed3\u679c", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "12522"},
                        {"col_index": 2, "text": "P001"},
                        {"col_index": 3, "text": "\u7537"},
                        {"col_index": 4, "text": "56"},
                        {"col_index": 5, "text": "82.5"},
                        {"col_index": 6, "text": "7"},
                        {"col_index": 7, "text": "6"},
                        {"col_index": 8, "text": "286"},
                        {"col_index": 9, "text": "8.4"},
                    ],
                }
            ],
        }
    ]

    detected = detect_domain_template(
        file_name="\u7cd6\u5c3f\u75c5\u60a3\u8005\u6570\u636e.xlsx",
        markdown="",
        table_blocks=table_blocks,
        figure_blocks=[],
    )

    assert detected == "clinical_patient_dataset"

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 10},
            file_name="\u7cd6\u5c3f\u75c5\u60a3\u8005\u6570\u636e.xlsx",
            markdown="",
            table_blocks=table_blocks,
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert meta["rule_field_count"] >= 6
    assert meta["source"] == "rules+heuristic"
    assert "\u5c31\u8bcaID" in fields
    assert "\u60a3\u8005\u7f16\u53f7" in fields
    assert "\u6027\u522b" in fields
    assert "\u5e74\u9f84" in fields
    assert "\u4f4f\u9662\u5929\u6570" in fields
    assert "\u8bca\u65ad\u6570\u91cf" in fields
    assert "\u8840\u6e05\u8461\u8404\u7cd6\u6700\u5927\u503c" in fields
    assert "\u7cd6\u5316\u8840\u7ea2\u86cb\u767d\u7ed3\u679c" in fields
    assert "\u4f53\u91cd" in fields


def test_epidemic_template_and_rule_candidates_activate_for_covid_sheet() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": [
                "\u56fd\u5bb6/\u5730\u533a",
                "\u5927\u6d32",
                "\u6bcf\u5343\u4eba\u533b\u9662\u5e8a\u4f4d\u6570",
                "\u6bcf\u5343\u4eba\u533b\u751f\u6570",
                "65\u5c81\u53ca\u4ee5\u4e0a\u4eba\u53e3\u5360\u6bd4",
                "\u65e5\u671f",
                "\u6bcf\u65e5\u68c0\u6d4b\u6570",
                "\u75c5\u4f8b\u6570",
                "\u6b7b\u4ea1\u6570",
            ],
            "header_meta": [
                {"col_index": 1, "name": "\u56fd\u5bb6/\u5730\u533a", "unit": None},
                {"col_index": 2, "name": "\u5927\u6d32", "unit": None},
                {"col_index": 3, "name": "\u6bcf\u5343\u4eba\u533b\u9662\u5e8a\u4f4d\u6570", "unit": None},
                {"col_index": 4, "name": "\u6bcf\u5343\u4eba\u533b\u751f\u6570", "unit": None},
                {"col_index": 5, "name": "65\u5c81\u53ca\u4ee5\u4e0a\u4eba\u53e3\u5360\u6bd4", "unit": None},
                {"col_index": 6, "name": "\u65e5\u671f", "unit": None},
                {"col_index": 7, "name": "\u6bcf\u65e5\u68c0\u6d4b\u6570", "unit": None},
                {"col_index": 8, "name": "\u75c5\u4f8b\u6570", "unit": None},
                {"col_index": 9, "name": "\u6b7b\u4ea1\u6570", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "\u4e2d\u56fd"},
                        {"col_index": 2, "text": "\u4e9a\u6d32"},
                        {"col_index": 3, "text": "4.34"},
                        {"col_index": 4, "text": "1.98"},
                        {"col_index": 5, "text": "11.9%"},
                        {"col_index": 6, "text": "2020-08-01"},
                        {"col_index": 7, "text": "52311"},
                        {"col_index": 8, "text": "89654"},
                        {"col_index": 9, "text": "4720"},
                    ],
                }
            ],
        }
    ]

    detected = detect_domain_template(
        file_name="COVID-19\u5168\u7403\u6570\u636e\u96c6\uff08\u8282\u9009\uff09.xlsx",
        markdown="",
        table_blocks=table_blocks,
        figure_blocks=[],
    )

    assert detected == "epidemic_surveillance_dataset"

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 10},
            file_name="COVID-19\u5168\u7403\u6570\u636e\u96c6\uff08\u8282\u9009\uff09.xlsx",
            markdown="",
            table_blocks=table_blocks,
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert meta["rule_field_count"] >= 6
    assert meta["source"] == "rules+heuristic"
    assert "\u56fd\u5bb6/\u5730\u533a" in fields
    assert "\u6bcf\u65e5\u68c0\u6d4b\u6570" in fields
    assert "\u75c5\u4f8b\u6570" in fields
    assert "\u6b7b\u4ea1\u6570" in fields


def test_rule_rich_epidemic_sheet_is_not_truncated_to_base_table_cap() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": [
                "\u56fd\u5bb6/\u5730\u533a",
                "\u5927\u6d32",
                "\u6bcf\u5343\u4eba\u533b\u9662\u5e8a\u4f4d\u6570",
                "\u6bcf\u5343\u4eba\u533b\u751f\u6570",
                "65\u5c81\u53ca\u4ee5\u4e0a\u4eba\u53e3\u5360\u6bd4",
                "\u65e5\u671f",
                "\u6bcf\u65e5\u68c0\u6d4b\u6570",
                "\u75c5\u4f8b\u6570",
                "\u6b7b\u4ea1\u6570",
            ],
            "header_meta": [
                {"col_index": 1, "name": "\u56fd\u5bb6/\u5730\u533a", "unit": None},
                {"col_index": 2, "name": "\u5927\u6d32", "unit": None},
                {"col_index": 3, "name": "\u6bcf\u5343\u4eba\u533b\u9662\u5e8a\u4f4d\u6570", "unit": None},
                {"col_index": 4, "name": "\u6bcf\u5343\u4eba\u533b\u751f\u6570", "unit": None},
                {"col_index": 5, "name": "65\u5c81\u53ca\u4ee5\u4e0a\u4eba\u53e3\u5360\u6bd4", "unit": None},
                {"col_index": 6, "name": "\u65e5\u671f", "unit": None},
                {"col_index": 7, "name": "\u6bcf\u65e5\u68c0\u6d4b\u6570", "unit": None},
                {"col_index": 8, "name": "\u75c5\u4f8b\u6570", "unit": None},
                {"col_index": 9, "name": "\u6b7b\u4ea1\u6570", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "\u4e2d\u56fd"},
                        {"col_index": 2, "text": "\u4e9a\u6d32"},
                        {"col_index": 3, "text": "4.34"},
                        {"col_index": 4, "text": "1.98"},
                        {"col_index": 5, "text": "11.9%"},
                        {"col_index": 6, "text": "2020-08-01"},
                        {"col_index": 7, "text": "52311"},
                        {"col_index": 8, "text": "89654"},
                        {"col_index": 9, "text": "4720"},
                    ],
                }
            ],
        }
    ]

    detected = detect_domain_template(
        file_name="COVID-19\u5168\u7403\u6570\u636e\u96c6\uff08\u8282\u9009\uff09.xlsx",
        markdown="",
        table_blocks=table_blocks,
        figure_blocks=[],
    )

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 12},
            file_name="COVID-19\u5168\u7403\u6570\u636e\u96c6\uff08\u8282\u9009\uff09.xlsx",
            markdown="",
            table_blocks=table_blocks,
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert meta["rule_field_count"] >= 8
    assert len(fields) >= 8
    assert "\u5927\u6d32" in fields
    assert "\u65e5\u671f" in fields
    assert "65\u5c81\u53ca\u4ee5\u4e0a\u4eba\u53e3\u5360\u6bd4" in fields


def test_environment_monitoring_sheet_activates_domain_specific_rules() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": [
                "\u5e8f\u53f7",
                "\u76d1\u6d4b\u65f6\u95f4",
                "\u57ce\u5e02",
                "\u533a",
                "\u7ad9\u70b9\u7f16\u7801",
                "\u7ad9\u70b9\u540d\u79f0",
                "\u7a7a\u6c14\u8d28\u91cf\u6307\u6570",
                "\u4e8c\u6c27\u5316\u786b\u76d1\u6d4b\u503c",
                "\u4e8c\u6c27\u5316\u6c2e\u76d1\u6d4b\u503c",
                "PM10\u76d1\u6d4b\u503c",
                "PM2.5\u76d1\u6d4b\u503c",
                "\u4e00\u6c27\u5316\u78b3\u76d1\u6d4b\u503c",
                "\u81ed\u6c27\u76d1\u6d4b\u503c",
                "\u9996\u8981\u6c61\u67d3\u7269",
                "\u6c61\u67d3\u7c7b\u578b",
            ],
            "header_meta": [
                {"col_index": 1, "name": "\u5e8f\u53f7", "unit": None},
                {"col_index": 2, "name": "\u76d1\u6d4b\u65f6\u95f4", "unit": None},
                {"col_index": 3, "name": "\u57ce\u5e02", "unit": None},
                {"col_index": 4, "name": "\u533a", "unit": None},
                {"col_index": 5, "name": "\u7ad9\u70b9\u7f16\u7801", "unit": None},
                {"col_index": 6, "name": "\u7ad9\u70b9\u540d\u79f0", "unit": None},
                {"col_index": 7, "name": "\u7a7a\u6c14\u8d28\u91cf\u6307\u6570", "unit": None},
                {"col_index": 8, "name": "\u4e8c\u6c27\u5316\u786b\u76d1\u6d4b\u503c", "unit": None},
                {"col_index": 9, "name": "\u4e8c\u6c27\u5316\u6c2e\u76d1\u6d4b\u503c", "unit": None},
                {"col_index": 10, "name": "PM10\u76d1\u6d4b\u503c", "unit": None},
                {"col_index": 11, "name": "PM2.5\u76d1\u6d4b\u503c", "unit": None},
                {"col_index": 12, "name": "\u4e00\u6c27\u5316\u78b3\u76d1\u6d4b\u503c", "unit": None},
                {"col_index": 13, "name": "\u81ed\u6c27\u76d1\u6d4b\u503c", "unit": None},
                {"col_index": 14, "name": "\u9996\u8981\u6c61\u67d3\u7269", "unit": None},
                {"col_index": 15, "name": "\u6c61\u67d3\u7c7b\u578b", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "1"},
                        {"col_index": 2, "text": "2025-01-01 10:00:00"},
                        {"col_index": 3, "text": "\u6d4e\u5357"},
                        {"col_index": 4, "text": "\u5386\u4e0b\u533a"},
                        {"col_index": 5, "text": "37010001"},
                        {"col_index": 6, "text": "\u6cc9\u57ce\u5e7f\u573a"},
                        {"col_index": 7, "text": "92"},
                        {"col_index": 8, "text": "8"},
                        {"col_index": 9, "text": "24"},
                        {"col_index": 10, "text": "61"},
                        {"col_index": 11, "text": "33"},
                        {"col_index": 12, "text": "0.8"},
                        {"col_index": 13, "text": "117"},
                        {"col_index": 14, "text": "PM10"},
                        {"col_index": 15, "text": "\u8f7b\u5ea6\u6c61\u67d3"},
                    ],
                }
            ],
        }
    ]

    detected = detect_domain_template(
        file_name="2025\u5c71\u4e1c\u7701\u73af\u5883\u7a7a\u6c14\u8d28\u91cf\u76d1\u6d4b\u6570\u636e\u4fe1\u606f.xlsx",
        markdown="",
        table_blocks=table_blocks,
        figure_blocks=[],
    )

    assert detected == "environment_monitoring_report"

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 12},
            file_name="2025\u5c71\u4e1c\u7701\u73af\u5883\u7a7a\u6c14\u8d28\u91cf\u76d1\u6d4b\u6570\u636e\u4fe1\u606f.xlsx",
            markdown="",
            table_blocks=table_blocks,
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert meta["rule_field_count"] >= 10
    assert len(fields) >= 10
    assert "\u76d1\u6d4b\u65f6\u95f4" in fields
    assert "\u57ce\u5e02" in fields
    assert "\u7ad9\u70b9\u7f16\u7801" in fields
    assert "\u7ad9\u70b9\u540d\u79f0" in fields
    assert "\u7a7a\u6c14\u8d28\u91cf\u6307\u6570" in fields
    assert "\u4e8c\u6c27\u5316\u786b\u76d1\u6d4b\u503c" in fields
    assert "\u4e8c\u6c27\u5316\u6c2e\u76d1\u6d4b\u503c" in fields
    assert "PM10\u6d53\u5ea6" in fields
    assert "PM2.5\u6d53\u5ea6" in fields
    assert "\u4e00\u6c27\u5316\u78b3\u76d1\u6d4b\u503c" in fields
    assert "\u81ed\u6c27\u76d1\u6d4b\u503c" in fields
    assert "\u9996\u8981\u6c61\u67d3\u7269" in fields
    assert "\u6c61\u67d3\u7c7b\u578b" in fields


def test_business_ledger_sheet_uses_clean_domain_labels_for_service_columns() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": [
                "order_id",
                "com_id",
                "user_id",
                "order_date",
                "order_time",
                "com_num",
                "spe_discount",
                "order_status",
                "ret_policy",
                "aft_sale",
                "cus_evalu",
                "spe_need",
                "pay_type",
                "del_type",
                "order_origin",
                "promition",
                "order_hand",
                "id",
                "sale_dep",
            ],
            "header_meta": [
                {"col_index": 1, "name": "order_id", "unit": None},
                {"col_index": 2, "name": "com_id", "unit": None},
                {"col_index": 3, "name": "user_id", "unit": None},
                {"col_index": 4, "name": "order_date", "unit": None},
                {"col_index": 5, "name": "order_time", "unit": None},
                {"col_index": 6, "name": "com_num", "unit": None},
                {"col_index": 7, "name": "spe_discount", "unit": None},
                {"col_index": 8, "name": "order_status", "unit": None},
                {"col_index": 9, "name": "ret_policy", "unit": None},
                {"col_index": 10, "name": "aft_sale", "unit": None},
                {"col_index": 11, "name": "cus_evalu", "unit": None},
                {"col_index": 12, "name": "spe_need", "unit": None},
                {"col_index": 13, "name": "pay_type", "unit": None},
                {"col_index": 14, "name": "del_type", "unit": None},
                {"col_index": 15, "name": "order_origin", "unit": None},
                {"col_index": 16, "name": "promition", "unit": None},
                {"col_index": 17, "name": "order_hand", "unit": None},
                {"col_index": 18, "name": "id", "unit": None},
                {"col_index": 19, "name": "sale_dep", "unit": None},
            ],
            "rows": [
                {
                    "row_index": 1,
                    "cells": [
                        {"col_index": 1, "text": "P1696644"},
                        {"col_index": 2, "text": "SP06691157"},
                        {"col_index": 3, "text": "US377677"},
                        {"col_index": 4, "text": "2023-09-08"},
                        {"col_index": 5, "text": "08:49:08"},
                        {"col_index": 6, "text": "6"},
                        {"col_index": 7, "text": "0"},
                        {"col_index": 8, "text": "已付款"},
                        {"col_index": 9, "text": "可退"},
                        {"col_index": 10, "text": "15天无理由退换"},
                        {"col_index": 11, "text": "非常满意"},
                        {"col_index": 12, "text": "无特殊要求"},
                        {"col_index": 13, "text": "微信"},
                        {"col_index": 14, "text": "快递"},
                        {"col_index": 15, "text": "京东"},
                        {"col_index": 16, "text": "无促销"},
                        {"col_index": 17, "text": "张三二"},
                        {"col_index": 18, "text": "28051"},
                        {"col_index": 19, "text": "销售三部"},
                    ],
                }
            ],
        }
    ]

    detected = detect_domain_template(
        file_name="电商销售数据.xlsx",
        markdown="",
        table_blocks=table_blocks,
        figure_blocks=[],
    )

    assert detected == "xlsx_business_ledger"

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 12},
            file_name="电商销售数据.xlsx",
            markdown="",
            table_blocks=table_blocks,
            figure_blocks=[],
            profile_hint="table_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert "售后政策" in fields
    assert "订单编号" in fields
    assert "SKU" in fields
    assert "用户编号" in fields
    assert "t sale（AF）" not in fields
    assert "订单数" not in fields
    assert all("（AF）" not in name for name in fields)
    assert meta["field_count"] == len(fields)


def test_environment_city_result_is_not_filtered_as_low_value() -> None:
    bundle = module2_bootstrap_components.schema_pipeline_bundle.result_filter_bundle

    filtered, removed = bundle.filter_low_value_auto_results(
        {
            "城市": {
                "value": "枣庄市",
                "confidence": 0.94,
                "source_ref_id": "xlsx_t1_r2_c3",
                "bbox": [1.0, 0.1, 0.0, 0.1, 0.1],
            }
        }
    )

    assert "城市" in filtered
    assert not removed


def test_clinical_patient_age_is_modeled_as_string_for_age_ranges() -> None:
    meta = normalize_field_name("年龄", template_hint="clinical_patient_dataset")

    assert meta["canonical_label"] == "年龄"
    assert meta["field_type"] == "string"


def test_table_prefill_skips_question_mark_placeholders_for_clinical_columns() -> None:
    graph = ExtractionGraph()

    async def _should_not_run(*args, **kwargs):
        raise AssertionError("LLM table extraction should be skipped for deterministic clinical prefill")

    graph._invoke_with_model_fallback = _should_not_run  # type: ignore[method-assign]

    state = {
        "markdown": "",
        "bbox_map": {
            "xlsx_t1_r1_c1": [1.0, 0.0, 0.0, 0.1, 0.1],
            "xlsx_t1_r1_c2": [1.0, 0.1, 0.0, 0.1, 0.1],
            "xlsx_t1_r1_c3": [1.0, 0.2, 0.0, 0.1, 0.1],
            "xlsx_t1_r2_c1": [1.0, 0.0, 0.1, 0.1, 0.1],
            "xlsx_t1_r2_c2": [1.0, 0.1, 0.1, 0.1, 0.1],
            "xlsx_t1_r2_c3": [1.0, 0.2, 0.1, 0.1, 0.1],
        },
        "table_blocks": [
            {
                "table_id": "xlsx_t1",
                "source": "xlsx",
                "page": 1,
                "quality": 0.98,
                "headers": ["年龄", "诊断2", "诊断3"],
                "header_meta": [
                    {"col_index": 1, "name": "年龄", "unit": None},
                    {"col_index": 2, "name": "诊断2", "unit": None},
                    {"col_index": 3, "name": "诊断3", "unit": None},
                ],
                "rows": [
                    {
                        "row_index": 1,
                        "cells": [
                            {"col_index": 1, "text": "[0-10)", "ref_id": "xlsx_t1_r1_c1", "header": "年龄"},
                            {"col_index": 2, "text": "?", "ref_id": "xlsx_t1_r1_c2", "header": "诊断2"},
                            {"col_index": 3, "text": "?", "ref_id": "xlsx_t1_r1_c3", "header": "诊断3"},
                        ],
                    },
                    {
                        "row_index": 2,
                        "cells": [
                            {"col_index": 1, "text": "[10-20)", "ref_id": "xlsx_t1_r2_c1", "header": "年龄"},
                            {"col_index": 2, "text": "250.01", "ref_id": "xlsx_t1_r2_c2", "header": "诊断2"},
                            {"col_index": 3, "text": "255", "ref_id": "xlsx_t1_r2_c3", "header": "诊断3"},
                        ],
                    },
                ],
            }
        ],
        "table_summary": "",
        "field_hints": {},
        "schema": {
            "fields": {
                "年龄": "string",
                "诊断2": "string",
                "诊断3": "string",
            }
        },
        "results": {},
        "errors": [],
        "soft_warnings": [],
        "retries": 0,
        "max_retries": 2,
    }

    updated = asyncio.run(graph.table_extract_node(state))

    assert updated["results"]["年龄"]["value"] == "[0-10)"
    assert updated["results"]["年龄"]["source_ref_id"] == "xlsx_t1_r1_c1"
    assert updated["results"]["诊断2"]["value"] == "250.01"
    assert updated["results"]["诊断2"]["source_ref_id"] == "xlsx_t1_r2_c2"
    assert updated["results"]["诊断3"]["value"] == "255"
    assert updated["results"]["诊断3"]["source_ref_id"] == "xlsx_t1_r2_c3"
