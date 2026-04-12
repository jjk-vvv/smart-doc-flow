from __future__ import annotations

import asyncio
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.agent.graph import ExtractionGraph
from app.core.schema.field_naming import detect_domain_template
from app.composition.application import module2_bootstrap_components, module2_main_schema_resolution_bundle


def _resolve_plain_text_auto_schema(
    *,
    file_name: str,
    markdown: str,
    max_auto_fields: int = 8,
) -> tuple[str, dict[str, object], dict[str, object]]:
    template = detect_domain_template(
        file_name=file_name,
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )
    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": max_auto_fields},
            file_name=file_name,
            markdown=markdown,
            table_blocks=[],
            figure_blocks=[],
            profile_hint="text_heavy",
            naming_template=template,
            allow_llm=False,
        )
    )
    return template, effective, meta


def test_government_bulletin_schema_resolution_keeps_macro_critical_fields() -> None:
    markdown = """
2024年国民经济和社会发展统计公报
国家统计局
2025年2月28日
2024年国内生产总值1349084亿元，比上年增长5.0%。
全年全部工业增加值405442亿元。
全年货物进出口总额438468亿元。
年末全国人口140828万人。
社会消费品零售总额487895亿元。
全国居民人均可支配收入41314元。
""".strip()

    template, effective, meta = _resolve_plain_text_auto_schema(
        file_name="2024年国民经济和社会发展统计公报.txt",
        markdown=markdown,
        max_auto_fields=12,
    )

    fields = effective["fields"]
    assert template == "government_statistical_bulletin"
    assert meta["rule_field_count"] >= 6
    assert "发布日期" in fields
    assert "生产总值" in fields
    assert "全部工业增加值" in fields
    assert "货物进出口总额" in fields
    assert "年末人口" in fields
    assert "居民人均可支配收入" in fields


def test_plain_text_business_report_activates_pharmaceutical_distribution_template() -> None:
    markdown = "\n".join(
        [
            '<ref id="text_1">2024年，全国七大类医药商品销售总额29470亿元。</ref>',
            '<ref id="text_2">订单总数39276万笔。</ref>',
            '<ref id="text_3">平均毛利率7.2%。</ref>',
        ]
    )

    detected = detect_domain_template(
        file_name="2024年药品流通行业运行统计分析报告.txt",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )

    assert detected == "pharmaceutical_distribution_report"


def test_plain_text_heuristic_prefers_metric_labels_over_section_titles() -> None:
    bundle = module2_bootstrap_components.schema_pipeline_bundle.schema_inference_bundle
    markdown = """
一、发展概况
（五）标准引领行业高质量发展
2024年，全国七大类医药商品销售总额29470亿元。
利润总额468亿元；平均毛利率7.2%；平均费用率6.2%；净利润率1.4%。
"""

    inferred = bundle.infer_schema_fields_heuristic(markdown, [], [], max_fields=8)

    assert "标准引领行业高质量发展" not in inferred
    assert "七大类医药商品销售总额" in inferred
    assert "利润总额" in inferred
    assert "平均毛利率" in inferred


def test_text_rule_extract_handles_connector_words_before_numeric_values() -> None:
    graph = ExtractionGraph()
    state = {
        "markdown": "\n".join(
            [
                '<ref id="text_1">平均毛利率为7.2%。</ref>',
                '<ref id="text_2">对医疗机构应收账款回款天数平均154天。</ref>',
            ]
        ),
        "bbox_map": {
            "text_1": [1.0, 0.0, 0.0, 1.0, 1.0],
            "text_2": [1.0, 0.0, 0.0, 1.0, 1.0],
        },
        "table_blocks": [],
        "table_summary": "",
        "field_hints": {},
        "schema": {
            "fields": {
                "平均毛利率": "number",
                "回款天数": "integer",
            }
        },
        "results": {},
        "errors": [],
        "soft_warnings": [],
        "retries": 0,
        "max_retries": 2,
    }

    updated = asyncio.run(graph.text_rule_extract_node(state))

    assert updated["results"]["平均毛利率"]["value"] == 7.2
    assert updated["results"]["平均毛利率"]["source_ref_id"] == "text_1"
    assert updated["results"]["回款天数"]["value"] == 154
    assert updated["results"]["回款天数"]["source_ref_id"] == "text_2"


def test_health_bulletin_heuristic_filters_generic_growth_candidates() -> None:
    bundle = module2_bootstrap_components.schema_pipeline_bundle.schema_inference_bundle
    markdown = """
### （三）卫生人员总数
2024年末，全国卫生人员总数1578.0万人，比上年增加54.2万人（增长3.6%）。

### （四）卫生总费用
2024年全国卫生总费用初步核算为90895.5亿元，其中：政府卫生支出22608.0亿元，社会卫生支出43280.0亿元，个人卫生支出25007.5亿元。

### （一）门诊和住院量
2024年，全国医疗卫生机构总诊疗人次101.5亿，比上年增加6.0亿人次。
"""

    inferred = bundle.infer_schema_fields_heuristic(markdown, [], [], max_fields=12)

    assert "增长" not in inferred
    assert "万人增长" not in inferred
    assert "亿人次增长" not in inferred
    assert inferred["卫生总费用"] == "number"
    assert inferred["政府卫生支出"] == "number"
    assert inferred["个人卫生支出"] == "number"
    assert inferred["医疗卫生机构总诊疗人次"] == "number"


def test_health_bulletin_schema_resolution_prefers_real_metrics_over_growth_placeholders() -> None:
    markdown = """
### （一）医疗卫生机构总数
2024年末，全国医疗卫生机构总数1093551个，比上年增加22766个。

### （二）床位数
2024年末，全国医疗卫生机构床位1029.8万张，其中：公立医院床位占69.0%，民营医院床位占31.0%。

### （三）卫生人员总数
2024年末，全国卫生人员总数1578.0万人，比上年增加54.2万人（增长3.6%）。

### （四）卫生总费用
2024年全国卫生总费用初步核算为90895.5亿元，其中：个人卫生支出25007.5亿元。

### （一）门诊和住院量
2024年，全国医疗卫生机构总诊疗人次101.5亿，比上年增加6.0亿人次。
"""

    effective, _meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 12},
            file_name="2024年卫生健康事业发展统计公报.md",
            markdown=markdown,
            table_blocks=[],
            figure_blocks=[],
            profile_hint="text_heavy",
            naming_template="government_statistical_bulletin",
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert "增长" not in fields
    assert "亿人次增长" not in fields
    assert "医疗卫生机构总数" in fields
    assert "卫生人员总数" in fields
    assert "卫生总费用" in fields
    assert "医疗卫生机构床位" in fields


def test_healthcare_template_and_rule_candidates_activate_for_health_bulletin() -> None:
    markdown = """
### （一）医疗卫生机构总数
2024年末，全国医疗卫生机构总数1093551个，比上年增加2766个。
### （二）床位数
2024年末，全国医疗卫生机构床位1029.8万张。
### （三）卫生人员总数
2024年末，全国卫生人员总数1578.0万人。
### （四）卫生总费用
2024年全国卫生总费用初步核算为90895.5亿元，其中：政府卫生支出22608.0亿元，个人卫生支出25007.5亿元。
### （五）门诊和住院量
2024年，全国医疗卫生机构总诊疗人次101.5亿人次。
"""

    detected = detect_domain_template(
        file_name="2024年卫生健康事业发展统计公报.md",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )

    assert detected == "healthcare_statistical_bulletin"

    effective, meta = asyncio.run(
        module2_main_schema_resolution_bundle.resolve_effective_schema(
            requested_schema={"auto_infer": True, "prefer_llm": False, "max_auto_fields": 12},
            file_name="2024年卫生健康事业发展统计公报.md",
            markdown=markdown,
            table_blocks=[],
            figure_blocks=[],
            profile_hint="text_heavy",
            naming_template=detected,
            allow_llm=False,
        )
    )

    fields = effective["fields"]
    assert meta["rule_field_count"] >= 5
    assert "医疗卫生机构总数" in fields
    assert "医疗卫生机构床位" in fields
    assert "卫生人员总数" in fields
    assert "卫生总费用" in fields
    assert "政府卫生支出" in fields
    assert "个人卫生支出" in fields
    assert "总诊疗人次" in fields


def test_auto_schema_fields_merge_cjk_connector_variants_and_drop_separated_trend_fragments() -> None:
    bundle = module2_bootstrap_components.schema_pipeline_bundle.schema_fields_bundle

    filtered = bundle.filter_auto_schema_fields(
        {
            "类标准比例": "number",
            "类标准的比例": "number",
            "总粉丝量 同比增长": "number",
            "年均高锰酸盐指数": "number",
        },
        max_fields=8,
    )

    assert "类标准比例" in filtered
    assert "类标准的比例" not in filtered
    assert "总粉丝量 同比增长" not in filtered
    assert "年均高锰酸盐指数" in filtered


def test_schema_selection_prunes_negative_weak_labels_even_without_max_field_pressure() -> None:
    selection_bundle = module2_bootstrap_components.schema_pipeline_bundle.schema_selection_bundle

    canonical_fields = {
        "类标准比例": "number",
        "年均高锰酸盐指数": "number",
        "杭州市国家数字生态文": "string",
        "总粉丝量 同比增长": "number",
    }
    field_meta = {
        name: {
            "aliases": [name],
            "raw_names": [name],
            "normalization_confidence": 0.55,
            "unit_norm": "",
            "dimensions": {},
            "normalization_rule_id": "",
        }
        for name in canonical_fields.keys()
    }

    selected_fields, _selected_meta = selection_bundle.select_best_canonical_schema_fields(
        canonical_fields,
        field_meta,
        max_fields=8,
        template_hint="common_document",
    )

    assert "类标准比例" in selected_fields
    assert "年均高锰酸盐指数" in selected_fields
    assert "杭州市国家数字生态文" not in selected_fields
    assert "总粉丝量 同比增长" not in selected_fields


def test_culture_tourism_schema_resolution_prefers_domain_rule_fields_over_dirty_per_capita_labels() -> None:
    markdown = """
2023年文化和旅游发展统计公报
中华人民共和国文化和旅游部
发布时间：2024年08月30日
2023年末，纳入统计报送的全国各类文化和旅游单位30.4万个，从业人员72.9万人。
2023年末，全国共有艺术表演团体1.8万个。全年共演出254.2万场，国内观众9.0亿人次，演出收入207.8亿元。
2023年末，全国共有公共美术馆707个，从业人员0.6万人。
2023年末，全国共有公共图书馆3246个，从业人员6.1万人。
2023年末，全国平均每万人公共图书馆建筑面积160.3平方米。
全年公共图书馆总流通人次116061万人次；外借人次33044万人次；参加人次21380万人次。
2023年末，全国共有群众文化机构4.4万个，从业人员19.9万人。
年末全国平均每万人群众文化设施建筑面积399.5平方米。
全年全国群众文化机构共组织开展各类文化活动412万场；服务人次183537万人次。
""".strip()

    template, effective, meta = _resolve_plain_text_auto_schema(
        file_name="2023年文化和旅游发展统计公报.md",
        markdown=markdown,
        max_auto_fields=8,
    )

    fields = effective["fields"]
    assert template == "culture_tourism_statistical_bulletin"
    assert meta["rule_field_count"] >= 6
    assert "文化和旅游单位数量" in fields
    assert "文化和旅游单位从业人员" in fields
    assert "艺术表演团体数量" in fields
    assert "国内观众人次" in fields
    assert "演出收入" in fields
    assert "发布日期" in fields
    assert "年末全国平均每 群众文化设施建筑面积" not in fields
    assert "平均每 公共图书馆建筑面积" not in fields
    assert "参加人次" not in fields
    assert "外借人次" not in fields
    assert "服务人次" not in fields


def test_industrial_census_schema_resolution_prefers_domain_rule_fields_over_total_placeholder() -> None:
    markdown = """
第三次全国工业普查主要数据公报
中华人民共和国国家统计局
第三次全国工业普查办公室
1995年末，全国工业企业和工业生产单位为734.2万个；从业人员14735.5万人；资产总额为88374.4亿元。
1995年工业产品销售收入77231.2亿元，上交税金4643.6亿元。
工业增加值为24353.7亿元，工业总产值为91893.7亿元。
表5：东、中、西部地区工业总产值经济类型结构对比（％）
在总计中：国有、集体、私营、个体、股份制、其他、乡镇工业、三资工业。
""".strip()

    template, effective, meta = _resolve_plain_text_auto_schema(
        file_name="第三次全国工业普查主要数据公报.md",
        markdown=markdown,
        max_auto_fields=8,
    )

    fields = effective["fields"]
    assert template == "industrial_census_bulletin"
    assert meta["rule_field_count"] >= 6
    assert "工业企业和工业生产单位数量" in fields
    assert "工业从业人员" in fields
    assert "资产总额" in fields
    assert "工业产品销售收入" in fields
    assert "工业增加值" in fields
    assert "工业总产值" in fields
    assert "在 中（总体）" not in fields


def test_pharmaceutical_distribution_schema_resolution_prefers_domain_rule_fields_over_long_logistics_labels() -> None:
    markdown = """
2024年药品流通行业运行统计分析报告
2024年，全国七大类医药商品销售总额29470亿元。其中，药品零售市场销售额6500亿元；药品批发市场销售额22970亿元。
全国拥有执业药师81.43万人。
2024年，全国药品流通直报企业主营业务收入22431亿元；利润总额468亿元；平均毛利率7.2%。
数据显示，对医疗机构应收账款回款天数平均154天。
据不完全统计，2024年全国医药物流直报企业（448家）配送货值（无税销售额）21883亿元。
据不完全统计，2024年医药电商直报企业销售总额2488亿元（含第三方交易服务平台交易额）。
""".strip()

    template, effective, meta = _resolve_plain_text_auto_schema(
        file_name="2024年药品流通行业运行统计分析报告.txt",
        markdown=markdown,
        max_auto_fields=8,
    )

    fields = effective["fields"]
    assert template == "pharmaceutical_distribution_report"
    assert meta["rule_field_count"] >= 8
    assert "七大类医药商品销售总额" in fields
    assert "药品零售市场销售额" in fields
    assert "药品批发市场销售额" in fields
    assert "执业药师人数" in fields
    assert "主营业务收入" in fields
    assert "利润总额" in fields
    assert "平均毛利率" in fields
    assert "应收账款回款天数" in fields
    assert "年全国医药物流直报企业448家配送货值无税销售额" not in fields
    assert "年医药电商直报企业销售总额" not in fields


def test_human_resources_schema_resolution_activates_rule_fields() -> None:
    markdown = """
2024年人力资源和社会保障事业发展统计公报
2024年，全国城镇新增就业1256万人。
年末基本养老保险参保人数106764万人。
年末失业保险参保人数24589万人。
年末工伤保险参保人数30250万人。
社会保障卡持卡人数13.89亿人。
""".strip()

    template, effective, meta = _resolve_plain_text_auto_schema(
        file_name="2024年人力资源和社会保障事业发展统计公报.txt",
        markdown=markdown,
        max_auto_fields=8,
    )

    fields = effective["fields"]
    assert template == "human_resources_social_security_report"
    assert meta["rule_field_count"] >= 5
    assert "城镇新增就业" in fields
    assert "基本养老保险参保人数" in fields
    assert "失业保险参保人数" in fields
    assert "工伤保险参保人数" in fields
    assert "社会保障卡持卡人数" in fields
