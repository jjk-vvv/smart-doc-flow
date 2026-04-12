from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from module2.app.core.schema.field_naming import (
    detect_domain_template,
    infer_rule_backed_schema_fields,
    normalize_field_name,
)


def test_government_statistical_bulletin_rule_fallbacks_cover_common_macro_fields() -> None:
    markdown = "\n".join(
        [
            "中华人民共和国2024年国民经济和社会发展统计公报",
            "国家统计局",
            "2025年2月28日",
            "全年国内生产总值1349084亿元，比上年增长5.0%。",
            "年末全国人口140828万人。",
            "全年全国城镇新增就业1256万人。",
            "全年全部工业增加值405442亿元。",
            "全年社会消费品零售总额487895亿元。",
            "全年全社会固定资产投资520916亿元。",
            "全年货物进出口总额438468亿元。",
            "全国一般公共预算收入219702亿元。",
            "全国居民人均可支配收入41314元。",
        ]
    )

    template = detect_domain_template(
        file_name="2024年国民经济和社会发展统计公报.txt",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )
    fields = infer_rule_backed_schema_fields(
        file_name="2024年国民经济和社会发展统计公报.txt",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
        template_hint=template,
        max_fields=12,
    )

    assert template == "government_statistical_bulletin"
    assert fields["统计年份"] == "integer"
    assert fields["发布机构"] == "string"
    assert fields["发布日期"] == "date"
    assert fields["生产总值"] == "number"
    assert fields["年末人口"] == "number"
    assert fields["新增就业（城市）"] == "number"
    assert fields["全部工业增加值"] == "number"
    assert fields["社会消费品零售总额"] == "number"
    assert fields["固定资产投资"] == "number"
    assert fields["货物进出口总额"] == "number"
    assert fields["一般公共预算收入"] == "number"
    assert fields["居民人均可支配收入"] == "number"
    assert "医疗卫生机构总数" not in fields
    assert "空气质量优良天数" not in fields


def test_healthcare_statistical_bulletin_does_not_inject_macro_economic_fallback_fields() -> None:
    markdown = "\n".join(
        [
            "2024年卫生健康事业发展统计公报",
            "国家卫生健康委员会",
            "2025年4月1日",
            "2024年末，全国医疗卫生机构总数1093551个。",
            "2024年末，全国卫生人员总数1578.0万人。",
            "2024年全国卫生总费用90895.5亿元。",
        ]
    )

    template = detect_domain_template(
        file_name="2024年卫生健康事业发展统计公报.md",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )
    fields = infer_rule_backed_schema_fields(
        file_name="2024年卫生健康事业发展统计公报.md",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
        template_hint=template,
        max_fields=12,
    )

    assert template == "healthcare_statistical_bulletin"
    assert fields["医疗卫生机构总数"] == "integer"
    assert fields["卫生人员总数"] == "number"
    assert fields["卫生总费用"] == "number"
    assert "生产总值" not in fields
    assert "固定资产投资" not in fields
    assert "货物进出口总额" not in fields


def test_culture_tourism_bulletin_rule_candidates_activate_for_domain_metrics() -> None:
    markdown = "\n".join(
        [
            "2023年文化和旅游发展统计公报",
            "中华人民共和国文化和旅游部",
            "发布时间：2024年08月30日",
            "2023年末，纳入统计报送的全国各类文化和旅游单位30.4万个，从业人员72.9万人。",
            "2023年末，全国共有艺术表演团体1.8万个。",
            "全年共演出254.2万场，国内观众9.0亿人次，演出收入207.8亿元。",
            "2023年末，全国共有公共美术馆707个。",
        ]
    )

    template = detect_domain_template(
        file_name="2023年文化和旅游发展统计公报.md",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )
    fields = infer_rule_backed_schema_fields(
        file_name="2023年文化和旅游发展统计公报.md",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
        template_hint=template,
        max_fields=10,
    )

    assert template == "culture_tourism_statistical_bulletin"
    assert fields["发布日期"] == "date"
    assert fields["文化和旅游单位数量"] == "number"
    assert fields["艺术表演团体数量"] == "number"
    assert fields["国内观众人次"] == "number"
    assert fields["演出收入"] == "number"


def test_industrial_census_bulletin_rule_candidates_activate_for_domain_metrics() -> None:
    markdown = "\n".join(
        [
            "第三次全国工业普查主要数据公报",
            "中华人民共和国国家统计局",
            "第三次全国工业普查办公室",
            "1995年末，全国工业企业和工业生产单位为734.2万个；从业人员14735.5万人；资产总额为88374.4亿元。",
            "1995年工业产品销售收入77231.2亿元，上交税金4643.6亿元。",
            "工业增加值为24353.7亿元，工业总产值为91893.7亿元。",
        ]
    )

    template = detect_domain_template(
        file_name="第三次全国工业普查主要数据公报.md",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )
    fields = infer_rule_backed_schema_fields(
        file_name="第三次全国工业普查主要数据公报.md",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
        template_hint=template,
        max_fields=10,
    )

    assert template == "industrial_census_bulletin"
    assert fields["工业企业和工业生产单位数量"] == "number"
    assert fields["资产总额"] == "number"
    assert fields["工业产品销售收入"] == "number"
    assert fields["工业增加值"] == "number"
    assert fields["工业总产值"] == "number"


def test_pharmaceutical_distribution_report_does_not_fall_back_to_recruitment_template() -> None:
    markdown = "\n".join(
        [
            "2024年药品流通行业运行统计分析报告",
            "2024年，全国七大类医药商品销售总额29470亿元。",
            "药品零售市场销售额6500亿元；药品批发市场销售额22970亿元。",
            "全国拥有执业药师81.43万人。",
            "主营业务收入22431亿元；利润总额468亿元；平均毛利率7.2%。",
            "应收账款回款天数平均154天。",
        ]
    )

    template = detect_domain_template(
        file_name="2024年药品流通行业运行统计分析报告.txt",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )
    fields = infer_rule_backed_schema_fields(
        file_name="2024年药品流通行业运行统计分析报告.txt",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
        template_hint=template,
        max_fields=10,
    )

    assert template == "pharmaceutical_distribution_report"
    assert fields["七大类医药商品销售总额"] == "number"
    assert fields["药品零售市场销售额"] == "number"
    assert fields["药品批发市场销售额"] == "number"
    assert fields["执业药师人数"] == "number"
    assert fields["主营业务收入"] == "number"
    assert fields["利润总额"] == "number"
    assert fields["平均毛利率"] == "number"
    assert fields["应收账款回款天数"] == "number"
    assert "学历" not in fields
    assert "专业" not in fields


def test_local_government_bulletin_rule_candidates_cover_resident_metrics() -> None:
    markdown = "\n".join(
        [
            "合肥市2024年国民经济和社会发展统计公报",
            "合肥市统计局 国家统计局合肥调查队",
            "2025年3月28日",
            "初步核算，全年生产总值（GDP）13507.69亿元，按不变价格计算，比上年增长6.1%。",
            "按常住人口计算，人均GDP136063元，比上年增长4.1%。",
            "常住人口1000.2万人，增加14.9万人；常住人口城镇化率86.38%，提高0.83个百分点。",
            "2024年城镇新增就业21.43万人。全年城镇调查失业率平均值为5.1%。",
            "年末全市户籍人口812.7万人，比上年末增加6.1万人。",
        ]
    )

    template = detect_domain_template(
        file_name="合肥市2024年国民经济和社会发展统计公报.txt",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
    )
    fields = infer_rule_backed_schema_fields(
        file_name="合肥市2024年国民经济和社会发展统计公报.txt",
        markdown=markdown,
        table_blocks=[],
        figure_blocks=[],
        template_hint=template,
        max_fields=16,
    )

    assert template == "government_statistical_bulletin"
    assert fields["生产总值"] == "number"
    assert fields["人均生产总值"] == "number"
    assert fields["常住人口"] == "number"
    assert fields["常住人口城镇化率"] == "number"
    assert fields["城镇调查失业率"] == "number"
    assert fields["户籍人口"] == "number"


def test_business_ledger_short_stream_dimension_does_not_pollute_after_sales_field() -> None:
    meta = normalize_field_name("aft_sale", template_hint="xlsx_business_ledger")

    assert meta["canonical_label"] == "售后政策"
    assert meta["normalization_rule_id"] == "after_sales_policy"
    assert meta["dimensions"] == {}


def test_business_ledger_rule_candidates_cover_real_english_headers_without_false_order_count() -> None:
    table_blocks = [
        {
            "source": "xlsx",
            "headers": [
                "order_id",
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
                "sale_dep",
            ],
            "header_meta": [
                {"col_index": 1, "name": "order_id", "unit": None},
                {"col_index": 2, "name": "order_status", "unit": None},
                {"col_index": 3, "name": "ret_policy", "unit": None},
                {"col_index": 4, "name": "aft_sale", "unit": None},
                {"col_index": 5, "name": "cus_evalu", "unit": None},
                {"col_index": 6, "name": "spe_need", "unit": None},
                {"col_index": 7, "name": "pay_type", "unit": None},
                {"col_index": 8, "name": "del_type", "unit": None},
                {"col_index": 9, "name": "order_origin", "unit": None},
                {"col_index": 10, "name": "promition", "unit": None},
                {"col_index": 11, "name": "order_hand", "unit": None},
                {"col_index": 12, "name": "sale_dep", "unit": None},
            ],
            "rows": [],
        }
    ]

    fields = infer_rule_backed_schema_fields(
        file_name="电商销售数据.xlsx",
        markdown="",
        table_blocks=table_blocks,
        figure_blocks=[],
        template_hint="xlsx_business_ledger",
        max_fields=16,
    )

    assert fields["订单编号"] == "string"
    assert fields["订单状态"] == "string"
    assert fields["退换政策"] == "string"
    assert fields["售后政策"] == "string"
    assert fields["客户评价"] == "string"
    assert fields["特殊需求"] == "string"
    assert fields["支付方式"] == "string"
    assert fields["配送方式"] == "string"
    assert fields["订单来源"] == "string"
    assert fields["促销活动"] == "string"
    assert fields["订单处理人"] == "string"
    assert fields["销售部门"] == "string"
    assert "订单数" not in fields
