from __future__ import annotations

import asyncio
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.schema.field_naming import detect_domain_template
from app.composition.application import module2_main_schema_resolution_bundle


def test_visual_context_schema_resolution_keeps_narrative_metrics_over_chart_axis_headers() -> None:
    markdown = """
<ref id="p3_c11">类标准比例为100%。</ref>
<ref id="p3_c12">年均高锰酸盐指数为2.1毫克/升。</ref>
<ref id="p11_c10">新媒体平台累计发文679条、阅读量1600万、总粉丝量51.87万，总粉丝量 同比增长 37.5%。</ref>
"""
    table_blocks = [
        {
            "source": "pdf_mineru_gemini",
            "headers": ["年度", "非酸雨", "轻度", "中度"],
            "header_meta": [
                {"col_index": 1, "name": "年度", "unit": None},
                {"col_index": 2, "name": "非酸雨", "unit": None},
                {"col_index": 3, "name": "轻度", "unit": None},
                {"col_index": 4, "name": "中度", "unit": None},
            ],
            "rows": [],
        }
    ]
    figure_blocks = [
        {
            "caption": "图 2024年杭州市各区域环境空气质量示意图",
            "key_points": [
                "2024年杭州市区降尘量年平均浓度较2023年有所下降，从2.73降至2.56 t/km²·30d。"
            ],
            "text_blocks": ["优良天数", "优良率"],
            "dataframe": {
                "headers": ["区域", "优良天数", "优良率"],
                "rows": [["杭州市区", "299", "81.7%"]],
            },
        }
    ]

    effective, _meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 12},
            file_name="2024年杭州市生态环境状况公报（节选）.docx",
            markdown=markdown,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            profile_hint="chart_heavy",
            naming_template="common_document",
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert "类标准比例" in fields
    assert "年均高锰酸盐指数" in fields
    assert "总粉丝量 同比增长" not in fields
    assert "非酸雨" not in fields
    assert "轻度" not in fields
    assert "中度" not in fields
    assert "区域" not in fields


def test_environment_template_and_rule_candidates_activate_for_visual_context() -> None:
    markdown = """
<ref id="p1_c1">2024年杭州市生态环境状况公报（节选）</ref>
<ref id="p1_c2">杭州市环境空气质量优良天数为299天，优良率为81.7%。</ref>
<ref id="p1_c3">PM2.5浓度为30微克/立方米，PM10浓度为52微克/立方米。</ref>
<ref id="p1_c4">全市监测点数量为54个。</ref>
"""
    table_blocks = [
        {
            "source": "pdf_mineru_gemini",
            "headers": ["区域", "优良天数", "优良率", "PM2.5浓度", "PM10浓度", "监测点数量"],
            "header_meta": [
                {"col_index": 1, "name": "区域", "unit": None},
                {"col_index": 2, "name": "优良天数", "unit": "天"},
                {"col_index": 3, "name": "优良率", "unit": "%"},
                {"col_index": 4, "name": "PM2.5浓度", "unit": "微克/立方米"},
                {"col_index": 5, "name": "PM10浓度", "unit": "微克/立方米"},
                {"col_index": 6, "name": "监测点数量", "unit": "个"},
            ],
            "rows": [["杭州市区", "299", "81.7%", "30", "52", "54"]],
        }
    ]
    figure_blocks = [
        {
            "caption": "图1 2024年杭州市空气质量优良天数和优良率",
            "text_blocks": ["优良天数", "优良率", "PM2.5浓度", "PM10浓度", "监测点数量"],
            "dataframe": {
                "headers": ["区域", "优良天数", "优良率", "PM2.5浓度", "PM10浓度", "监测点数量"],
                "rows": [["杭州市区", "299", "81.7%", "30", "52", "54"]],
            },
        }
    ]

    detected = detect_domain_template(
        file_name="2024年杭州市生态环境状况公报（节选）.docx",
        markdown=markdown,
        table_blocks=table_blocks,
        figure_blocks=figure_blocks,
    )

    assert detected == "environment_monitoring_report"

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 10},
            file_name="2024年杭州市生态环境状况公报（节选）.docx",
            markdown=markdown,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            profile_hint="chart_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert meta["rule_field_count"] >= 4
    assert "优良天数" in fields
    assert "PM2.5浓度" in fields
    assert "PM10浓度" in fields
    assert "监测点数量" in fields
