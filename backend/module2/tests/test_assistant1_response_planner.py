from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.response_planner import Assistant1ResponsePlanner


def test_schema_design_request_routes_to_database_tools() -> None:
    planner = Assistant1ResponsePlanner()

    plan = planner.plan(
        user_message="请你为文档抽取后的统计指标设计一张 PostgreSQL 表，要求支持按年份、地区、指标名称检索，并说明主键和索引怎么放。",
        default_file_hash="",
    )

    assert plan.intent == "schema_design"
    assert plan.use_tools is True
    assert plan.requires_tool_call is True
    assert plan.primary_tool_name == "inspect_database_schema"
    assert "design_schema_draft" in plan.tool_names


def test_sql_request_routes_to_nl2sql_pipeline() -> None:
    planner = Assistant1ResponsePlanner()

    plan = planner.plan(
        user_message="请把这个自然语言需求转成 SQL：统计 public.doc_knowledge_unit 里每个 file_hash 的知识单元数量。",
        default_file_hash="",
    )

    assert plan.intent == "sql_request"
    assert plan.use_tools is True
    assert plan.requires_tool_call is True
    assert plan.primary_tool_name == "inspect_database_schema"
    assert "draft_sql_from_nl" in plan.tool_names


def test_general_method_question_is_not_swallowed_by_document_lookup() -> None:
    planner = Assistant1ResponsePlanner()

    plan = planner.plan(
        user_message="如果用户上传的是一份质量一般、版式也不规整的扫描文档，你通常会怎么分阶段处理，才能让后面的抽取、问答和落库都更稳？",
        default_file_hash="abc123",
    )

    assert plan.intent == "general_method"
    assert plan.use_tools is False


def test_risk_review_question_uses_grouped_document_grounding() -> None:
    planner = Assistant1ResponsePlanner()

    plan = planner.plan(
        user_message="这份表格现在最值得优先核对的风险点是什么？不要泛泛而谈，请给我具体判断点。",
        default_file_hash="abc123",
    )

    assert plan.intent == "document_risk_review"
    assert plan.use_tools is True
    assert plan.requires_tool_call is True
    assert plan.primary_tool_name == "search_knowledge_base_grouped"


def test_ambiguous_row_lookup_requires_clarification() -> None:
    planner = Assistant1ResponsePlanner()

    plan = planner.plan(
        user_message="滕州新二中这条记录的 PM10 现在是多少？",
        default_file_hash="abc123",
    )

    assert plan.intent == "document_lookup"
    assert plan.must_clarify is True
    assert "限定条件" in plan.clarification_reason


def test_entity_extraction_routes_to_document_tools() -> None:
    planner = Assistant1ResponsePlanner()

    plan = planner.plan(
        user_message="请从当前文档抽取统计年份和基金会总数，并按JSON返回",
        default_file_hash="abc123",
    )

    assert plan.intent == "entity_extraction"
    assert plan.use_tools is True
    assert plan.requires_tool_call is True
    assert "search_knowledge_base" in plan.tool_names
    assert "ingest_document" in plan.tool_names
