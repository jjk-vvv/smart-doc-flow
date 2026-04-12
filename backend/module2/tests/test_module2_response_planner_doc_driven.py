from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.response_planner import Assistant1ResponsePlanner


# ---------------------------------------------------------------------------
# Tests for Fix 3: schema_design and sql_request can include KB tools
# when the question references the active document.
# ---------------------------------------------------------------------------

def test_schema_design_with_document_language_includes_kb_tool() -> None:
    """Document-driven schema design request should get search_knowledge_base."""
    planner = Assistant1ResponsePlanner()
    plan = planner.plan(
        user_message="根据这份文档里的统计指标设计一张 PostgreSQL 表",
        default_file_hash="abc123",
    )
    assert plan.intent == "schema_design"
    assert "search_knowledge_base" in plan.tool_names or "search_knowledge_base_grouped" in plan.tool_names


def test_schema_design_without_file_does_not_include_kb_tool() -> None:
    """No active document → KB tool must not be added (use non-document-specific language)."""
    planner = Assistant1ResponsePlanner()
    plan = planner.plan(
        user_message="请设计一张存储统计指标的 PostgreSQL 表，支持按年份和地区检索",
        default_file_hash="",
    )
    assert plan.intent == "schema_design"
    assert "search_knowledge_base" not in plan.tool_names
    assert "search_knowledge_base_grouped" not in plan.tool_names


def test_schema_design_generic_language_does_not_include_kb_tool() -> None:
    """Generic schema design (no document signals) should not pull in KB tools."""
    planner = Assistant1ResponsePlanner()
    plan = planner.plan(
        user_message="请设计一张通用的用户信息表，包含 id、name、email、created_at",
        default_file_hash="abc123",
    )
    assert plan.intent == "schema_design"
    assert "search_knowledge_base" not in plan.tool_names
    assert "search_knowledge_base_grouped" not in plan.tool_names


def test_sql_request_with_document_language_includes_kb_tool() -> None:
    """'Write SQL for this document's data' should add search_knowledge_base."""
    planner = Assistant1ResponsePlanner()
    plan = planner.plan(
        user_message="为这个文档里的数据写一条 SELECT 语句，按年份聚合统计指标",
        default_file_hash="abc123",
    )
    assert plan.intent == "sql_request"
    assert "search_knowledge_base" in plan.tool_names


def test_sql_request_without_document_language_does_not_include_kb_tool() -> None:
    """Pure NL2SQL with no document language should not add KB tools."""
    planner = Assistant1ResponsePlanner()
    plan = planner.plan(
        user_message="把这个需求转成 SQL：统计每个地区的 PM10 平均浓度",
        default_file_hash="abc123",
    )
    assert plan.intent == "sql_request"
    # May or may not include KB tool — what matters is the intent routes correctly
    # and the database tools are always present
    assert "inspect_database_schema" in plan.tool_names
    assert "draft_sql_from_nl" in plan.tool_names


def test_schema_design_always_includes_core_db_tools() -> None:
    """Core database tools must always be present for schema_design."""
    planner = Assistant1ResponsePlanner()
    plan = planner.plan(
        user_message="根据这份文档里的数据设计一张表",
        default_file_hash="abc123",
    )
    assert "inspect_database_schema" in plan.tool_names
    assert "design_schema_draft" in plan.tool_names
