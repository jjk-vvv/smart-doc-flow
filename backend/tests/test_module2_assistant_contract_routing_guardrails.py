from __future__ import annotations

from app.modules.module2.assistant_1.agent_runtime import Assistant1AgentRuntime
from app.modules.module2.assistant_1.frontend_grounding import (
    cleanup_answer_text,
    enforce_answer_with_frontend_contracts,
    looks_like_exact_field_question,
    should_short_circuit_with_frontend_snapshot,
)
from app.modules.module2.assistant_1.response_planner import Assistant1ResponsePlanner


def _extra_context(*, with_lock: bool = False) -> dict[str, object]:
    current_document: dict[str, object] = {
        "file_name": "demo.docx",
        "summary": "当前文档围绕 2023 和 2024 年地区发展指标展开。",
        "top_fields": [
            {"label": "统计年份", "value": "2024", "confidence": 99, "page": 1},
            {"label": "地区生产总值", "value": "12345.6", "confidence": 97, "page": 2},
            {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 3},
        ],
        "table_column_headers": ["年份", "地区生产总值", "同比增速"],
        "figure_key_points": ["2024 年地区生产总值较 2023 年上升"],
    }
    if with_lock:
        current_document["current_locked_object"] = {
            "lock_type": "row",
            "table_id": "table_1",
            "row_index": 2,
            "ref_id": "ref-row-2",
        }
    return {"current_document": current_document}


def test_exact_field_detector_does_not_treat_label_suffix_value_as_plain_value_lookup() -> None:
    question = "\u8bf7\u5206\u6790\u5730\u533a\u751f\u4ea7\u603b\u503c\u7684\u53d8\u5316\u8d8b\u52bf\u3002"

    assert looks_like_exact_field_question(question) is False


def test_snapshot_short_circuit_is_disabled_for_temporal_comparison_questions() -> None:
    question = "\u8bf7\u5bf9\u6bd4 2023 \u5e74\u548c 2024 \u5e74\u7684\u5730\u533a\u751f\u4ea7\u603b\u503c\u53d8\u5316\u8d8b\u52bf\u3002"

    assert (
        should_short_circuit_with_frontend_snapshot(
            user_message=question,
            snapshot_answer="\u7edf\u8ba1\u5e74\u4efd\u662f 2024\u3002",
            extra_context=_extra_context(),
        )
        is False
    )


def test_snapshot_short_circuit_is_disabled_for_preview_only_write_requests() -> None:
    question = (
        "\u8bf7\u628a\u5f53\u524d\u6587\u6863\u6574\u7406\u6210\u5f85\u5165\u5e93\u8bb0\u5f55\uff0c"
        "\u5148\u7ed9\u52a8\u4f5c\u9884\u89c8\uff0c\u4e0d\u8981\u6267\u884c\u3002"
    )

    assert (
        should_short_circuit_with_frontend_snapshot(
            user_message=question,
            snapshot_answer="\u5730\u533a\u751f\u4ea7\u603b\u503c\u662f 12345.6\u3002",
            extra_context=_extra_context(),
        )
        is False
    )


def test_answer_contract_guard_adds_provenance_when_answer_only_contains_value() -> None:
    question = "\u57fa\u91d1\u4f1a\u603b\u6570\u8fd9\u4e2a\u6570\u5b57\u6765\u81ea\u54ea\u91cc\uff1f"

    answer = enforce_answer_with_frontend_contracts(
        user_message=question,
        answer="\u57fa\u91d1\u4f1a\u603b\u6570\u662f 8877\u3002",
        extra_context=_extra_context(),
    )

    assert "\u6765\u81ea" in answer or "\u8bc1\u636e" in answer or "\u5b57\u6bb5" in answer


def test_answer_contract_guard_keeps_substantive_provenance_style_answer() -> None:
    question = "\u57fa\u91d1\u4f1a\u603b\u6570\u8fd9\u4e2a\u6570\u5b57\u6765\u81ea\u54ea\u91cc\uff1f"
    original_answer = (
        "\u8fd9\u4e2a\u6570\u5b57\u4e0d\u662f\u6211\u989d\u5916\u63a8\u51fa\u7684\uff0c"
        "\u800c\u662f\u5f53\u524d\u6587\u6863\u5df2\u7ecf\u62bd\u53d6\u51fa\u6765\u7684\u7edf\u8ba1\u9879\uff1b"
        "\u5982\u679c\u4f60\u8981\u7ee7\u7eed\u7cbe\u5b9a\u5230\u539f\u6587\u5b9a\u4f4d\uff0c\u6211\u53ef\u4ee5\u518d\u5f80\u4e0b\u7ee7\u7eed\u627e\u3002"
    )

    answer = enforce_answer_with_frontend_contracts(
        user_message=question,
        answer=original_answer,
        extra_context=_extra_context(),
    )

    assert answer == cleanup_answer_text(original_answer)


def test_answer_contract_guard_clarifies_generic_deictic_without_lock() -> None:
    answer = enforce_answer_with_frontend_contracts(
        user_message="\u8fd9\u4e2a\u503c\u662f\u591a\u5c11\uff1f",
        answer="\u7edf\u8ba1\u5e74\u4efd\u662f 2024\u3002",
        extra_context=_extra_context(with_lock=False),
    )

    assert "\u4e0d\u80fd\u786e\u5b9a" in answer or "\u8bf7\u518d\u544a\u8bc9\u6211" in answer


def test_answer_contract_guard_rejects_single_field_answer_for_temporal_comparison() -> None:
    question = "\u8bf7\u6bd4\u8f83 2023 \u5e74\u548c 2024 \u5e74\u5730\u533a\u751f\u4ea7\u603b\u503c\u7684\u53d8\u5316\u8d8b\u52bf\u3002"

    answer = enforce_answer_with_frontend_contracts(
        user_message=question,
        answer="\u7edf\u8ba1\u5e74\u4efd\u662f 2024\u3002",
        extra_context=_extra_context(),
    )

    assert "\u8d8b\u52bf" in answer or "\u6bd4\u8f83" in answer or "\u4e0d\u8db3\u4ee5" in answer


def test_answer_contract_guard_keeps_substantive_temporal_reasoning_answer() -> None:
    question = "\u8bf7\u6bd4\u8f83 2023 \u5e74\u548c 2024 \u5e74\u5730\u533a\u751f\u4ea7\u603b\u503c\u7684\u53d8\u5316\u8d8b\u52bf\u3002"
    original_answer = (
        "\u4f60\u95ee\u7684\u5176\u5b9e\u662f\u4e24\u4e2a\u65f6\u95f4\u70b9\u4e4b\u95f4\u7684\u5173\u7cfb\uff0c"
        "\u4e0d\u662f\u67d0\u4e00\u4e2a\u65f6\u70b9\u7684\u8bfb\u6570\uff1b"
        "\u73b0\u6709\u5feb\u7167\u53ea\u80fd\u652f\u6301\u65b9\u5411\u6027\u5224\u65ad\uff0c\u8fd8\u4e0d\u591f\u76f4\u63a5\u4e0b\u7cbe\u786e\u7ed3\u8bba\u3002"
    )

    answer = enforce_answer_with_frontend_contracts(
        user_message=question,
        answer=original_answer,
        extra_context=_extra_context(),
    )

    assert answer == cleanup_answer_text(original_answer)


def test_response_planner_routes_action_preview_request_to_sql_draft() -> None:
    planner = Assistant1ResponsePlanner()
    question = (
        "\u8bf7\u628a\u5f53\u524d\u6587\u6863\u6574\u7406\u6210\u5f85\u5165\u5e93\u8bb0\u5f55\uff0c"
        "\u5148\u7ed9\u52a8\u4f5c\u9884\u89c8\uff0c\u4e0d\u8981\u6267\u884c\u3002"
    )

    plan = planner.plan(user_message=question, default_file_hash="file-hash-1")

    assert plan.intent == "sql_request"
    assert "draft_sql_from_nl" in plan.tool_names
    assert "execute_sql_with_audit" not in plan.tool_names


def test_write_request_detector_keeps_preview_only_write_intent_in_write_draft_mode() -> None:
    question = (
        "\u8bf7\u628a\u5f53\u524d\u6587\u6863\u6574\u7406\u6210\u5f85\u5165\u5e93\u8bb0\u5f55\uff0c"
        "\u5148\u7ed9\u52a8\u4f5c\u9884\u89c8\uff0c\u4e0d\u8981\u6267\u884c\u3002"
    )

    assert Assistant1AgentRuntime._looks_like_write_request(question) is True
