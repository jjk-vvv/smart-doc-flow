from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.intent_router import (
    collect_intent_signals,
    has_explicit_time_scope,
    is_ambiguous_record_lookup,
    is_broad_document_question,
    is_capability_question,
    is_document_risk_review_question,
    is_document_specific_question,
    is_entity_extraction_request,
    is_field_lookup_question,
    is_schema_design_request,
    is_sql_request,
    is_strict_minimal_request,
    is_web_search_request,
    prefers_active_document_grounding,
    wants_brief_answer,
    wants_detailed_answer,
)


# --- is_strict_minimal_request ---

def test_strict_minimal_only_answer_chinese() -> None:
    assert is_strict_minimal_request("只回答数字") is True

def test_strict_minimal_no_explanation() -> None:
    assert is_strict_minimal_request("不要解释，直接给我") is True

def test_strict_minimal_just_answer_english() -> None:
    assert is_strict_minimal_request("just answer with a number") is True

def test_strict_minimal_normal_not_triggered() -> None:
    assert is_strict_minimal_request("这份文档讲了什么") is False


# --- wants_brief_answer ---

def test_brief_jianyao() -> None:
    assert wants_brief_answer("请简要说明") is True

def test_brief_one_sentence() -> None:
    assert wants_brief_answer("用一句话概括") is True

def test_brief_briefly_english() -> None:
    assert wants_brief_answer("answer briefly") is True

def test_brief_normal_not_triggered() -> None:
    assert wants_brief_answer("请详细展开这份文档的内容") is False


# --- wants_detailed_answer ---

def test_detailed_xiangxi() -> None:
    assert wants_detailed_answer("请详细说明") is True

def test_detailed_step_by_step_english() -> None:
    assert wants_detailed_answer("explain step by step") is True

def test_detailed_normal_not_triggered() -> None:
    assert wants_detailed_answer("只回答数字") is False


# --- is_capability_question ---

def test_capability_neng_zuo_shenme() -> None:
    assert is_capability_question("你能做什么") is True

def test_capability_how_can_you_help() -> None:
    assert is_capability_question("how can you help me with this document") is True

def test_capability_normal_not_triggered() -> None:
    assert is_capability_question("PM10 的值是多少") is False


# --- is_web_search_request ---

def test_web_search_lianwang() -> None:
    assert is_web_search_request("联网搜索一下") is True

def test_web_search_guanfang() -> None:
    assert is_web_search_request("官方网站有什么说法") is True

def test_web_search_latest_english() -> None:
    assert is_web_search_request("what's the latest policy on this") is True

def test_web_search_normal_not_triggered() -> None:
    assert is_web_search_request("这份文档讲了什么") is False


# --- is_schema_design_request ---

def test_schema_design_jianbiao() -> None:
    assert is_schema_design_request("帮我建表") is True

def test_schema_design_biaojiegou() -> None:
    assert is_schema_design_request("表结构怎么设计") is True

def test_schema_design_ddl_english() -> None:
    assert is_schema_design_request("generate ddl for me") is True

def test_schema_design_schema_keyword() -> None:
    assert is_schema_design_request("schema design for this data") is True

def test_schema_design_composite_primary_key() -> None:
    # 主键 + 表 → composite check
    assert is_schema_design_request("这张表的主键应该怎么设计") is True

def test_schema_design_normal_not_triggered() -> None:
    assert is_schema_design_request("帮我看一下这份文档讲了什么") is False


# --- is_sql_request ---

def test_sql_request_nl2sql() -> None:
    assert is_sql_request("帮我 nl2sql 这个查询") is True

def test_sql_request_select_space() -> None:
    assert is_sql_request("select * from my_table") is True

def test_sql_request_zhuan_sql() -> None:
    assert is_sql_request("转sql：查询前10条记录") is True

def test_sql_request_ruku() -> None:
    assert is_sql_request("把这条记录入库") is True

def test_sql_request_regex_sql_word() -> None:
    assert is_sql_request("帮我写一条 SQL 查询") is True

def test_sql_request_normal_not_triggered() -> None:
    assert is_sql_request("这份文档讲了什么") is False


# --- is_document_specific_question ---

def test_doc_specific_zhefenwenjian() -> None:
    assert is_document_specific_question("这份文档里的数据") is True

def test_doc_specific_zhangbiao() -> None:
    assert is_document_specific_question("这张表里的第一行") is True

def test_doc_specific_this_document_english() -> None:
    assert is_document_specific_question("what does this document say") is True

def test_doc_specific_normal_not_triggered() -> None:
    assert is_document_specific_question("PM10 的全球平均值是多少") is False


# --- is_broad_document_question ---

def test_broad_doc_zongjie() -> None:
    assert is_broad_document_question("总结一下这份文档") is True

def test_broad_doc_zhuyao_jiang() -> None:
    assert is_broad_document_question("这份文档主要讲了什么") is True

def test_broad_doc_summarize_english() -> None:
    # The exact phrase needed is "summarize this document"
    assert is_broad_document_question("please summarize this document") is True

def test_broad_doc_normal_not_triggered() -> None:
    assert is_broad_document_question("PM10 的具体值是多少") is False


# --- is_document_risk_review_question ---

def test_risk_review_fengxiandian() -> None:
    assert is_document_risk_review_question("最值得先核对的风险点是什么") is True

def test_risk_review_english() -> None:
    assert is_document_risk_review_question("risk review: what should I check first") is True

def test_risk_review_normal_not_triggered() -> None:
    assert is_document_risk_review_question("总结一下这份文档") is False


# --- is_field_lookup_question ---

def test_field_lookup_duoshao() -> None:
    assert is_field_lookup_question("PM10 的值是多少") is True

def test_field_lookup_ziduan() -> None:
    assert is_field_lookup_question("这个字段的含义是什么") is True

def test_field_lookup_normal_not_triggered() -> None:
    assert is_field_lookup_question("帮我总结一下文档") is False


# --- is_entity_extraction_request ---

def test_entity_extraction_request_json_from_current_document() -> None:
    assert is_entity_extraction_request("请从当前文档抽取统计年份和基金会总数，并按JSON输出") is True


def test_entity_extraction_request_method_question_not_triggered() -> None:
    assert is_entity_extraction_request("如何系统提升实体抽取效果") is False


# --- has_explicit_time_scope ---

def test_time_scope_year_number() -> None:
    # regex requires 20XX年/月 — standalone "2024年" alone doesn't match; use with month
    assert has_explicit_time_scope("2024年3月的数据") is True

def test_time_scope_last_year() -> None:
    # "年份" IS in the keyword list
    assert has_explicit_time_scope("这个年份的统计数字") is True

def test_time_scope_english_year() -> None:
    # "year" IS in the keyword list
    assert has_explicit_time_scope("data from last year") is True

def test_time_scope_not_triggered() -> None:
    assert has_explicit_time_scope("这条记录的 PM10 是多少") is False


# --- is_ambiguous_record_lookup ---

def test_ambiguous_lookup_triggers() -> None:
    assert is_ambiguous_record_lookup("这条记录的 PM10 是多少", has_default_file=True) is True

def test_ambiguous_lookup_generic_deictic_value_triggers() -> None:
    assert is_ambiguous_record_lookup("这个数值是多少？", has_default_file=True) is True

def test_ambiguous_lookup_no_default_file() -> None:
    assert is_ambiguous_record_lookup("这条记录的 PM10 是多少", has_default_file=False) is False

def test_ambiguous_lookup_with_time_scope_not_triggered() -> None:
    # "2024年3月" triggers has_explicit_time_scope regex → suppresses ambiguity
    assert is_ambiguous_record_lookup("2024年3月这条记录的 PM10 是多少", has_default_file=True) is False

def test_ambiguous_lookup_with_specific_field_not_triggered() -> None:
    assert is_ambiguous_record_lookup("这个基金会总数是多少？", has_default_file=True) is False

def test_ambiguous_lookup_with_chinese_quotes_not_triggered() -> None:
    # Fix 7: quoted specific term suppresses clarification
    assert is_ambiguous_record_lookup("「滕州新二中」这条记录的 PM10 是多少", has_default_file=True) is False

def test_ambiguous_lookup_with_curly_quotes_not_triggered() -> None:
    assert is_ambiguous_record_lookup('"specific station" 的 PM10 值', has_default_file=True) is False


# --- collect_intent_signals (dataclass completeness) ---

def test_collect_signals_has_all_fields() -> None:
    signals = collect_intent_signals("这份文档的 PM10 是多少", has_default_file=True)
    assert hasattr(signals, "document_specific")
    assert hasattr(signals, "field_lookup")
    assert hasattr(signals, "entity_extraction")
    assert hasattr(signals, "has_default_file")
    assert signals.has_default_file is True

def test_collect_signals_strict_minimal_implies_brief() -> None:
    signals = collect_intent_signals("只回答数字", has_default_file=False)
    assert signals.strict_minimal is True
    assert signals.brief is True

def test_collect_signals_web_search() -> None:
    signals = collect_intent_signals("联网搜索最新政策", has_default_file=False)
    assert signals.web_search is True
    assert signals.capability is False

def test_collect_signals_schema_design() -> None:
    # "建表" IS a direct marker in is_schema_design_request
    signals = collect_intent_signals("帮我建表存储指标数据", has_default_file=True)
    assert signals.schema_design is True

def test_prefers_active_document_grounding_returns_bool() -> None:
    result = prefers_active_document_grounding("总结一下这份文档", has_default_file=True)
    assert isinstance(result, bool)
