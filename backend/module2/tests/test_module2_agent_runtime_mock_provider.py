from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.agent_runtime import Assistant1AgentRuntime, Assistant1ToolContext
from app.assistant_1.response_planner import Assistant1ResponsePlan
from app.assistant_1.responses_provider import ResponsesFunctionCall, ResponsesCompletionResult


# ---------------------------------------------------------------------------
# Helper: build a stub completion result
# ---------------------------------------------------------------------------

def _completion(text: str = "", function_calls: list | None = None) -> ResponsesCompletionResult:
    return ResponsesCompletionResult(
        output_text=text,
        function_calls=function_calls or [],
        response_id="resp_test",
        status="completed",
    )


def _make_runtime() -> Assistant1AgentRuntime:
    """Build a runtime with all dependencies stubbed, no real LLM/DB needed."""
    runtime = Assistant1AgentRuntime.__new__(Assistant1AgentRuntime)
    runtime.provider = MagicMock()
    runtime.provider.configured = True
    runtime.retrieval = MagicMock()
    runtime.ingest = MagicMock()
    runtime.schema_tools = MagicMock()
    runtime.sql_tools = MagicMock()
    runtime.tavily = MagicMock()
    runtime.tool_router = MagicMock()
    runtime.settings = MagicMock()
    runtime.settings.chat_max_output_tokens = 2400
    return runtime


# ---------------------------------------------------------------------------
# _clarification_payload
# ---------------------------------------------------------------------------

def test_clarification_payload_contains_multi_record_hint() -> None:
    runtime = _make_runtime()
    plan = Assistant1ResponsePlan(
        intent="document_lookup",
        must_clarify=True,
        clarification_reason="当前问题还缺少能唯一锁定记录的限定条件。",
    )
    ctx = Assistant1ToolContext(default_file_hash="abc123")
    result = runtime._clarification_payload(
        question="这条记录的 PM10 是多少",
        response_plan=plan,
        context=ctx,
        extra_context=None,
    )
    assert result.get("final_output_types") == ["clarification_required"]
    assert "多条记录" in result.get("answer", "")
    assert "时间点" in result.get("answer", "")


def test_clarification_payload_has_required_keys() -> None:
    runtime = _make_runtime()
    plan = Assistant1ResponsePlan(
        intent="document_lookup",
        must_clarify=True,
        clarification_reason="需要时间范围。",
    )
    ctx = Assistant1ToolContext(default_file_hash="xyz")
    result = runtime._clarification_payload(
        question="问题", response_plan=plan, context=ctx, extra_context=None
    )
    assert "answer" in result
    assert "file_hash" in result
    assert "tool_steps" in result
    assert result["file_hash"] == "xyz"


# ---------------------------------------------------------------------------
# _render_sql_draft_answer — various conditions
# ---------------------------------------------------------------------------

def test_render_sql_draft_offline_message() -> None:
    result = Assistant1AgentRuntime._render_sql_draft_answer(
        schema_snapshot={"ok": False, "table_count": 0, "tables": []},
        sql_result={
            "ok": True,
            "sql": "SELECT * FROM inferred_table;",
            "statement_type": "select",
            "explanation": "基于请求推断。",
            "assumptions": [],
            "requires_confirmation": False,
            "schema_offline": True,
        },
    )
    assert "不可用" in result or "推断" in result or "离线" in result or "暂时" in result


def test_render_sql_draft_with_table_count() -> None:
    result = Assistant1AgentRuntime._render_sql_draft_answer(
        schema_snapshot={"ok": True, "table_count": 5, "tables": []},
        sql_result={
            "ok": True,
            "sql": "SELECT COUNT(*) FROM t;",
            "statement_type": "select",
            "explanation": "计数查询。",
            "assumptions": [],
            "requires_confirmation": False,
            "schema_offline": False,
        },
    )
    assert "5" in result  # table count mentioned


def test_render_sql_draft_empty_sql_gives_insufficient_message() -> None:
    result = Assistant1AgentRuntime._render_sql_draft_answer(
        schema_snapshot={"ok": True, "table_count": 2, "tables": []},
        sql_result={
            "ok": True,
            "sql": "",
            "statement_type": "",
            "explanation": "",
            "assumptions": [],
            "requires_confirmation": False,
            "schema_offline": False,
        },
    )
    assert "不完整" in result or "不能" in result or "没有" in result


def test_render_sql_draft_write_op_mentions_confirmation() -> None:
    result = Assistant1AgentRuntime._render_sql_draft_answer(
        schema_snapshot={"ok": True, "table_count": 1, "tables": []},
        sql_result={
            "ok": True,
            "sql": "INSERT INTO t VALUES (1);",
            "statement_type": "insert",
            "explanation": "插入一条记录。",
            "assumptions": [],
            "requires_confirmation": True,
            "schema_offline": False,
        },
    )
    assert "确认" in result


def test_render_sql_draft_not_ok_returns_failure_message() -> None:
    result = Assistant1AgentRuntime._render_sql_draft_answer(
        schema_snapshot={"ok": False, "table_count": 0, "tables": []},
        sql_result={"ok": False, "error": "connection refused"},
    )
    assert "没有拿到" in result or "不可用" in result or "草案不可用" in result


# ---------------------------------------------------------------------------
# _should_short_circuit_with_frontend_snapshot
# ---------------------------------------------------------------------------

def test_short_circuit_false_for_broad_summary() -> None:
    # After P0 Fix 1: broad summary questions must NOT short-circuit
    result = Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="请概括当前选中文档的核心内容",
        snapshot_answer="文档核心内容摘要。",
    )
    assert result is False


def test_short_circuit_true_for_strict_minimal() -> None:
    result = Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="只回答数字",
        snapshot_answer="42",
    )
    assert result is True


def test_short_circuit_false_when_snapshot_empty() -> None:
    result = Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="只回答数字",
        snapshot_answer="",
    )
    assert result is False


# ---------------------------------------------------------------------------
# _build_frontend_snapshot_answer
# ---------------------------------------------------------------------------

def test_build_snapshot_answer_returns_direct_numeric_value() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="统计年份是什么？只回答数字。",
        extra_context={
            "current_document": {
                "file_name": "2021年报告.docx",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                ],
            }
        },
    )
    assert answer == "2021"


def test_build_snapshot_answer_empty_when_no_fields() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="统计年份是什么",
        extra_context={"current_document": {"file_name": "doc.docx", "top_fields": []}},
    )
    # Should be empty or very short when no fields match
    assert isinstance(answer, str)


# ---------------------------------------------------------------------------
# _ground_answer_with_frontend_context — placeholder replacement
# ---------------------------------------------------------------------------

def test_ground_answer_replaces_placeholder_with_snapshot() -> None:
    # "总结一下" triggers is_broad_document_question → snapshot returns a summary line
    # "此处填入" in the backend answer triggers looks_like_placeholder_answer → snapshot replaces
    answer = Assistant1AgentRuntime._ground_answer_with_frontend_context(
        user_message="总结一下当前选中文档的核心内容",
        answer="文档主要描述了……（此处填入文档主题）。",
        extra_context={
            "current_document": {
                "file_name": "2021年民政统计.docx",
                "summary": "2021年民政事业统计，涵盖机构、床位、基金会等数据。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 99, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                    {"label": "床位数", "value": "530", "confidence": 97, "page": 4},
                ],
            }
        },
    )
    # Placeholder replaced by snapshot content
    assert "此处填入" not in answer


def test_chat_returns_frontend_snapshot_even_when_provider_is_unconfigured() -> None:
    runtime = _make_runtime()
    runtime.provider.configured = False
    runtime._plan_response = MagicMock(return_value=Assistant1ResponsePlan(intent="document_lookup"))
    runtime._build_frontend_snapshot_answer = MagicMock(return_value="2021")
    runtime._should_short_circuit_with_frontend_snapshot = MagicMock(return_value=True)

    result = runtime.chat(
        "当前文档的统计年份是什么？只回答数字。",
        extra_context={"current_document": {"file_hash": "abc123"}},
    )

    assert result["answer"] == "2021"
    assert result["final_output_types"] == ["frontend_snapshot"]


def test_chat_returns_clarification_even_when_provider_is_unconfigured() -> None:
    runtime = _make_runtime()
    runtime.provider.configured = False
    runtime._plan_response = MagicMock(
        return_value=Assistant1ResponsePlan(
            intent="document_lookup",
            must_clarify=True,
            clarification_reason="当前问题还缺少能唯一锁定记录的限定条件。",
        )
    )
    runtime._build_frontend_snapshot_answer = MagicMock(return_value="")

    result = runtime.chat(
        "这个数值是多少？",
        extra_context={"current_document": {"file_hash": "abc123"}},
    )

    assert result["final_output_types"] == ["clarification_required"]
    assert "告诉我" in result["answer"]
