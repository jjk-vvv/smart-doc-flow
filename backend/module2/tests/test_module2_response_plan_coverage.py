from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.response_planner import Assistant1ResponsePlanner


def _plan(message: str, file_hash: str = "") -> object:
    return Assistant1ResponsePlanner().plan(user_message=message, default_file_hash=file_hash)


# --- missing_document ---

def test_missing_document_no_file_doc_specific() -> None:
    plan = _plan("这份文档里的 PM10 是多少", file_hash="")
    assert plan.intent == "missing_document"
    assert plan.use_tools is False
    assert plan.max_output_tokens == 220


# --- capability ---

def test_capability_intent_no_tools() -> None:
    plan = _plan("你能做什么")
    assert plan.intent == "capability"
    assert plan.use_tools is False
    assert 260 <= plan.max_output_tokens <= 1300


# --- web_search ---

def test_web_search_forces_tavily_tool() -> None:
    plan = _plan("联网搜索最新政策")
    assert plan.intent == "web_search"
    assert "web_search_tavily" in plan.tool_names
    assert plan.requires_tool_call is True
    assert plan.use_tools is True


# --- schema_design ---

def test_schema_design_no_doc_no_kb_tool() -> None:
    plan = _plan("请设计一张统计指标的 PostgreSQL 表，支持按年份检索", file_hash="")
    assert plan.intent == "schema_design"
    assert "inspect_database_schema" in plan.tool_names
    assert "design_schema_draft" in plan.tool_names
    assert "search_knowledge_base" not in plan.tool_names
    assert "search_knowledge_base_grouped" not in plan.tool_names


def test_schema_design_with_doc_and_doc_language_adds_kb() -> None:
    plan = _plan("根据这份文档里的统计指标设计一张 PostgreSQL 表", file_hash="abc123")
    assert plan.intent == "schema_design"
    assert ("search_knowledge_base" in plan.tool_names or "search_knowledge_base_grouped" in plan.tool_names)


def test_schema_design_always_has_core_db_tools() -> None:
    plan = _plan("帮我建表存储环境数据", file_hash="abc123")
    assert plan.intent == "schema_design"
    assert "inspect_database_schema" in plan.tool_names
    assert "design_schema_draft" in plan.tool_names


# --- sql_request ---

def test_sql_request_basic_tools() -> None:
    plan = _plan("把这个需求转成 SQL：统计每个地区的 PM10 平均浓度", file_hash="abc123")
    assert plan.intent == "sql_request"
    assert "inspect_database_schema" in plan.tool_names
    assert "draft_sql_from_nl" in plan.tool_names
    assert plan.requires_tool_call is True


def test_sql_request_with_execution_word_adds_execute_tool() -> None:
    plan = _plan("帮我写一条 SQL 并执行入库", file_hash="abc123")
    assert plan.intent == "sql_request"
    assert "execute_sql_with_audit" in plan.tool_names


def test_sql_request_with_doc_language_adds_kb() -> None:
    plan = _plan("为这个文档里的数据写一条 SELECT 语句", file_hash="abc123")
    assert plan.intent == "sql_request"
    assert "search_knowledge_base" in plan.tool_names


def test_sql_request_ambiguous_record_must_clarify() -> None:
    plan = _plan("这条记录的 PM10 转成 SQL 查询", file_hash="abc123")
    assert plan.intent == "sql_request"
    assert plan.must_clarify is True


# --- document_risk_review ---

def test_risk_review_uses_grouped_search() -> None:
    plan = _plan("这份表格最值得优先核对的风险点是什么", file_hash="abc123")
    assert plan.intent == "document_risk_review"
    assert "search_knowledge_base_grouped" in plan.tool_names
    assert plan.primary_tool_name == "search_knowledge_base_grouped"


# --- document_summary ---

def test_document_summary_broad_uses_grouped_search() -> None:
    plan = _plan("总结一下这份文档的核心内容", file_hash="abc123")
    assert plan.intent == "document_summary"
    assert "search_knowledge_base_grouped" in plan.tool_names


# --- entity_extraction ---

def test_entity_extraction_uses_document_tools() -> None:
    plan = _plan("请从当前文档抽取统计年份和基金会总数，并按JSON输出", file_hash="abc123")
    assert plan.intent == "entity_extraction"
    assert "search_knowledge_base" in plan.tool_names
    assert "ingest_document" in plan.tool_names
    assert plan.requires_tool_call is True


# --- document_lookup ---

def test_document_lookup_uses_single_search() -> None:
    plan = _plan("这份文档里 PM10 的精确值是多少", file_hash="abc123")
    assert plan.intent == "document_lookup"
    assert "search_knowledge_base" in plan.tool_names
    assert plan.primary_tool_name == "search_knowledge_base"


def test_document_lookup_ambiguous_must_clarify() -> None:
    plan = _plan("这条记录的 PM10 是多少", file_hash="abc123")
    assert plan.intent == "document_lookup"
    assert plan.must_clarify is True
    assert plan.clarification_reason != ""


# --- strict_minimal / general_chat ---

def test_strict_minimal_no_file_no_tools() -> None:
    plan = _plan("只回答数字", file_hash="")
    assert plan.intent == "minimal_answer"
    assert plan.use_tools is False
    assert plan.max_output_tokens == 120


def test_general_chat_fallback_no_tools() -> None:
    plan = _plan("你好，有什么可以帮我的吗", file_hash="")
    assert plan.intent == "general_chat"
    assert plan.use_tools is False


# --- verbosity modifiers ---

def test_detailed_modifier_increases_tokens() -> None:
    plan_normal = _plan("总结一下这份文档", file_hash="abc123")
    plan_detailed = _plan("详细总结一下这份文档，分阶段展开", file_hash="abc123")
    assert plan_detailed.max_output_tokens >= plan_normal.max_output_tokens


def test_brief_modifier_decreases_tokens() -> None:
    plan_normal = _plan("总结一下这份文档", file_hash="abc123")
    plan_brief = _plan("简要总结一下，一句话", file_hash="abc123")
    assert plan_brief.max_output_tokens <= plan_normal.max_output_tokens
