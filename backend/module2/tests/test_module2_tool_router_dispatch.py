from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.tool_router import Assistant1ToolContext, Assistant1ToolRouter
from app.assistant_1.responses_provider import ResponsesFunctionCall


def _make_router() -> Assistant1ToolRouter:
    return Assistant1ToolRouter(
        retrieval=MagicMock(),
        ingest=MagicMock(),
        schema_tools=MagicMock(),
        sql_tools=MagicMock(),
        tavily=MagicMock(),
    )


def _make_call(name: str, arguments: dict | None = None) -> ResponsesFunctionCall:
    return ResponsesFunctionCall(
        call_id=f"call_{name}",
        name=name,
        arguments=arguments or {},
    )


# ---------------------------------------------------------------------------
# tool_definitions() — schema format
# ---------------------------------------------------------------------------

def test_tool_definitions_search_kb_has_openai_schema() -> None:
    router = _make_router()
    defs = router.tool_definitions(("search_knowledge_base",))
    assert len(defs) == 1
    d = defs[0]
    assert d["type"] == "function"
    assert d["name"] == "search_knowledge_base"
    assert "description" in d
    assert "parameters" in d
    assert "query" in d["parameters"]["properties"]


def test_tool_definitions_empty_names_returns_all() -> None:
    # When no names are specified, tool_definitions returns ALL defined tools
    router = _make_router()
    defs = router.tool_definitions(())
    assert len(defs) >= 8  # all 8 tools defined


def test_tool_definitions_nonexistent_tool_is_skipped() -> None:
    router = _make_router()
    defs = router.tool_definitions(("nonexistent_tool_xyz",))
    assert defs == []


def test_tool_definitions_multiple_tools() -> None:
    router = _make_router()
    defs = router.tool_definitions(("search_knowledge_base", "web_search_tavily", "inspect_database_schema"))
    names = [d["name"] for d in defs]
    assert "search_knowledge_base" in names
    assert "web_search_tavily" in names
    assert "inspect_database_schema" in names


def test_tool_definitions_all_have_required_query_field() -> None:
    router = _make_router()
    for tool_name in ("search_knowledge_base", "search_knowledge_base_grouped"):
        defs = router.tool_definitions((tool_name,))
        assert len(defs) == 1
        params = defs[0]["parameters"]
        assert "query" in params.get("required", [])


# ---------------------------------------------------------------------------
# execute_tool() — unknown tool returns error
# ---------------------------------------------------------------------------

def test_execute_tool_unknown_name_returns_error() -> None:
    router = _make_router()
    ctx = Assistant1ToolContext(default_file_hash="abc123")
    # The router needs a ResponsesFunctionCall with id field
    call = ResponsesFunctionCall(id="id_1", call_id="call_1", name="nonexistent_tool_xyz")
    result = router.execute_tool(call, ctx)
    assert result.get("ok") is False
    assert "unknown tool" in str(result.get("error", "")).lower()


# ---------------------------------------------------------------------------
# tool_result_preview()
# ---------------------------------------------------------------------------

def test_tool_result_preview_retrieval_result() -> None:
    router = _make_router()
    retrieval_result = {
        "ok": True,
        "match_count": 2,
        "matches": [
            {"title": "第一段内容", "content": "这是内容摘要", "score": 0.9},
            {"title": "第二段内容", "content": "另一段内容", "score": 0.8},
        ],
    }
    preview = router.tool_result_preview(retrieval_result)
    assert isinstance(preview, dict)
    assert preview.get("ok") is True
    assert "match_count" in preview or "top_titles" in preview


def test_tool_result_preview_sql_result() -> None:
    router = _make_router()
    sql_result = {
        "ok": True,
        "sql": "SELECT COUNT(*) FROM t;",
        "statement_type": "select",
        "row_count": 1,
    }
    preview = router.tool_result_preview(sql_result)
    assert isinstance(preview, dict)
    assert preview.get("ok") is True


def test_tool_result_preview_schema_result() -> None:
    router = _make_router()
    schema_result = {
        "ok": True,
        "table_count": 3,
        "tables": [{"table_name": "t1"}, {"table_name": "t2"}, {"table_name": "t3"}],
    }
    preview = router.tool_result_preview(schema_result)
    assert isinstance(preview, dict)


def test_tool_result_preview_empty_result() -> None:
    router = _make_router()
    preview = router.tool_result_preview({"ok": False, "error": "failed"})
    assert isinstance(preview, dict)
    assert preview.get("ok") is False


# ---------------------------------------------------------------------------
# group_matches_by_year()
# ---------------------------------------------------------------------------

def test_group_matches_by_year_groups_correctly() -> None:
    router = _make_router()
    matches = [
        {"title": "2021年报告", "content": "内容A", "year_hints": ["2021"]},
        {"title": "2022年报告", "content": "内容B", "year_hints": ["2022"]},
        {"title": "也是2021年", "content": "内容C", "year_hints": ["2021"]},
    ]
    grouped = router.group_matches_by_year(matches)
    assert isinstance(grouped, list)
    year_labels = {item["year_label"] for item in grouped}
    assert "2021" in year_labels
    assert "2022" in year_labels
    # The 2021 group should have match_count=2
    group_2021 = next(item for item in grouped if item["year_label"] == "2021")
    assert group_2021["match_count"] == 2


def test_group_matches_by_year_no_year_hint_goes_to_unknown() -> None:
    router = _make_router()
    matches = [
        {"title": "无年份数据", "content": "内容X", "year_hints": []},
    ]
    grouped = router.group_matches_by_year(matches)
    assert isinstance(grouped, list)
    assert len(grouped) == 1
    assert grouped[0]["year_label"] == "unknown"


# ---------------------------------------------------------------------------
# Assistant1ToolContext defaults
# ---------------------------------------------------------------------------

def test_tool_context_default_values() -> None:
    ctx = Assistant1ToolContext()
    assert ctx.default_file_hash == ""
    assert ctx.top_k == 5
    assert ctx.max_snippet_chars == 700


def test_tool_context_custom_values() -> None:
    ctx = Assistant1ToolContext(default_file_hash="abc123", top_k=3)
    assert ctx.default_file_hash == "abc123"
    assert ctx.top_k == 3
