from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.agent_runtime import Assistant1AgentRuntime
from app.assistant_1.frontend_grounding import should_short_circuit_with_frontend_snapshot


# ---------------------------------------------------------------------------
# Tests for the repaired short-circuit gate (Fix 1)
# ---------------------------------------------------------------------------

def test_broad_summary_does_not_short_circuit() -> None:
    """Broad document questions must go through retrieval, not snapshot exit."""
    result = should_short_circuit_with_frontend_snapshot(
        user_message="这份文档的摘要是什么",
        snapshot_answer="文档主要介绍了 2021 年民政事业发展情况。",
    )
    assert result is False


def test_summary_keyword_does_not_short_circuit() -> None:
    """'总结一下文档的核心字段' previously triggered short-circuit; must not after fix."""
    result = should_short_circuit_with_frontend_snapshot(
        user_message="总结一下文档的核心字段",
        snapshot_answer="文档包含以下核心字段。",
    )
    assert result is False


def test_summary_english_keyword_does_not_short_circuit() -> None:
    """English 'summary' keyword should also no longer trigger short-circuit."""
    result = should_short_circuit_with_frontend_snapshot(
        user_message="Give me a summary of this document",
        snapshot_answer="The document covers...",
    )
    assert result is False


def test_summary_plus_field_inventory_short_circuits_when_frontend_evidence_is_sufficient() -> None:
    result = should_short_circuit_with_frontend_snapshot(
        user_message="请用中文概括当前选中文档的核心内容，并列出你当前最确定的3个字段。",
        snapshot_answer=(
            "当前选中文档的核心内容：该文档概述了 2021 年民政事业发展情况。\n"
            "当前最确定的 3 个字段：\n"
            "统计年份：2021\n"
            "基金会总数：8877\n"
            "民政服务床位总数：530.5"
        ),
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "summary": "该文档概述了 2021 年民政事业发展总体情况。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021"},
                    {"label": "基金会总数", "value": "8877"},
                    {"label": "民政服务床位总数", "value": "530.5"},
                ],
            }
        },
    )
    assert result is True


def test_strict_minimal_still_short_circuits() -> None:
    """Explicitly terse requests (只回答数字) should still short-circuit."""
    result = should_short_circuit_with_frontend_snapshot(
        user_message="只回答数字，这份文档是哪一年的",
        snapshot_answer="2021",
    )
    assert result is True


def test_empty_snapshot_answer_does_not_short_circuit() -> None:
    """No snapshot answer → never short-circuit regardless of question type."""
    result = should_short_circuit_with_frontend_snapshot(
        user_message="只回答数字",
        snapshot_answer="",
    )
    assert result is False


def test_agent_runtime_delegates_to_same_gate() -> None:
    """Agent runtime's static wrapper should return identical result."""
    broad_result = Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="请概括当前选中文档的核心内容",
        snapshot_answer="文档核心内容。",
    )
    assert broad_result is False

    strict_result = Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="只给数字",
        snapshot_answer="42",
    )
    assert strict_result is True


def test_risk_review_question_now_short_circuits() -> None:
    result = should_short_circuit_with_frontend_snapshot(
        user_message="如果我是第一次核对这份文档，最应该先核对哪 3 类信息？",
        snapshot_answer="如果你是第一次核对这份文档，我建议先优先看这 3 类信息：",
    )
    assert result is True


def test_card_selection_question_now_short_circuits() -> None:
    result = should_short_circuit_with_frontend_snapshot(
        user_message="如果我只能够保留两个最稳妥的字段做首页卡片，你建议保留哪两个？",
        snapshot_answer="如果首页只能保留两个最稳妥的字段，我建议优先保留这两个：",
    )
    assert result is True


def test_field_provenance_question_now_short_circuits() -> None:
    result = should_short_circuit_with_frontend_snapshot(
        user_message="基金会总数这个数字来自文档里的哪一类信息？",
        snapshot_answer="就当前文档快照看，基金会总数=8877 这个数字来自文档里已经抽取出来的关键统计字段/指标项。",
    )
    assert result is True


def test_entity_extraction_question_now_short_circuits() -> None:
    result = should_short_circuit_with_frontend_snapshot(
        user_message="请从当前文档抽取统计年份和基金会总数，并按JSON输出",
        snapshot_answer='{"intent":"entity_extraction","extracted":{"统计年份":"2021","基金会总数":"8877"}}',
    )
    assert result is True
