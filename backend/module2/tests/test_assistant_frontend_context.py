from __future__ import annotations

import json
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.agent_runtime import Assistant1AgentRuntime


def make_runtime_without_init() -> Assistant1AgentRuntime:
    return Assistant1AgentRuntime.__new__(Assistant1AgentRuntime)


def test_frontend_context_block_preserves_grounded_document_snapshot() -> None:
    block = Assistant1AgentRuntime._frontend_context_block(
        {
            "workspace": {
                "documents_count": 2,
                "active_document_index": 1,
                "active_panel": "assistant",
            },
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "file_hash": "abc123",
                "summary": "这是一份关于 2021 年民政事业发展的统计公报。",
                "top_fields": [
                    {
                        "label": "统计年份",
                        "value": "2021",
                        "confidence": 98,
                        "page": 1,
                    },
                    {
                        "label": "基金会总数",
                        "value": "8877",
                        "confidence": 98,
                        "page": 12,
                    },
                ],
            },
        }
    )

    assert "Frontend active document snapshot" in block
    assert "2021年民政事业发展统计公报.docx" in block
    assert "统计年份" in block
    assert "2021" in block
    assert "基金会总数" in block
    assert "8877" in block


def test_frontend_context_block_drops_empty_values_and_limits_noise() -> None:
    normalized = Assistant1AgentRuntime._normalize_frontend_context(
        {
            "empty": "",
            "none_value": None,
            "nested": {
                "summary": "  多个   空白 字符   会被清理  ",
                "items": ["", None, "保留这一项"],
            },
        }
    )

    assert "empty" not in normalized
    assert "none_value" not in normalized
    assert normalized["nested"]["summary"] == "多个 空白 字符 会被清理"
    assert normalized["nested"]["items"] == ["保留这一项"]


def test_plan_response_uses_document_tools_for_selected_document_summary_question() -> None:
    runtime = make_runtime_without_init()

    plan = runtime._plan_response(
        user_message="请用中文概括当前选中文档的核心内容，并列出你当前最确定的3个字段。",
        default_file_hash="abc123",
    )

    assert plan.use_tools is True
    assert plan.text_verbosity == "low"
    assert plan.tool_names == ("search_knowledge_base_grouped", "ingest_document")


def test_plan_response_keeps_tools_for_strict_minimal_document_lookup() -> None:
    runtime = make_runtime_without_init()

    plan = runtime._plan_response(
        user_message="当前文档的统计年份是什么？只回答数字。",
        default_file_hash="abc123",
    )

    assert plan.use_tools is True
    assert plan.text_verbosity == "low"
    assert plan.max_output_tokens == 220
    assert plan.tool_names == ("search_knowledge_base", "ingest_document")


def test_ground_answer_with_frontend_context_replaces_placeholder_summary() -> None:
    answer = Assistant1AgentRuntime._ground_answer_with_frontend_context(
        user_message="请用中文概括当前选中文档的核心内容，并列出你当前最确定的3个字段。",
        answer=(
            "我已基于当前会话绑定的默认文档进行阅读与理解。\n\n"
            "文档主要描述了……（此处填入文档主题、目的与核心结论）。\n"
            "1) 字段名：文档标题 / 主旨\n"
            "- 当前值：[\"示例标题或主旨文本的一句关键短语\"]"
        ),
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "summary": "该文档概述了 2021 年民政事业发展总体情况，并给出机构设施、老年人口、基金会等统计数据。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                    {"label": "民政服务床位总数", "value": "530.5", "confidence": 99, "page": 4},
                ],
            }
        },
    )

    assert "此处填入" not in answer
    assert "示例标题或主旨文本" not in answer
    assert "当前选中文档的核心内容" in answer
    assert "统计年份：2021" in answer
    assert "基金会总数：8877" in answer


def test_build_frontend_snapshot_answer_returns_direct_numeric_value_for_strict_request() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="当前文档的统计年份是什么？只回答数字。",
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                ],
            }
        },
    )

    assert answer == "2021"


def test_build_frontend_snapshot_answer_returns_risk_review_guidance() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="如果我是第一次核对这份文档，最应该先核对哪 3 类信息？",
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "summary": "该文档概述了 2021 年民政事业发展总体情况，并给出机构设施、老年人口、基金会等统计数据。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                    {"label": "民政服务床位总数", "value": "530.5", "confidence": 99, "page": 4},
                ],
                "table_column_headers": ["指标", "数量", "同比增长"],
                "figure_key_points": ["基金会数量保持增长", "床位资源持续扩充"],
            }
        },
    )

    assert "先优先看这 3 类信息" in answer
    assert "统计年份" in answer
    assert "基金会总数=8877" in answer
    assert "表头、单位、同比或变化口径" in answer


def test_build_frontend_snapshot_answer_returns_card_field_selection_guidance() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="如果我只能够保留两个最稳妥的字段做首页卡片，你建议保留哪两个？",
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "summary": "该文档概述了 2021 年民政事业发展总体情况，并给出机构设施、老年人口、基金会等统计数据。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                    {"label": "民政服务床位总数", "value": "530.5", "confidence": 99, "page": 4},
                ],
            }
        },
    )

    assert "两个最稳妥的字段" in answer
    assert "统计年份：2021" in answer
    assert "基金会总数：8877" in answer


def test_build_frontend_snapshot_answer_returns_field_provenance_guidance() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="基金会总数这个数字来自文档里的哪一类信息？",
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                ],
                "table_column_headers": ["指标", "数量", "同比增长"],
            }
        },
    )

    assert "基金会总数=8877" in answer
    assert "关键统计字段/指标项" in answer
    assert "指标、数量、同比增长" in answer


def test_build_frontend_snapshot_answer_returns_temporal_gap_answer_for_missing_year() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="这份文档能直接告诉我 2022 年的基金会总数吗？",
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "summary": "该文档概述了 2021 年民政事业发展总体情况。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                ],
            }
        },
    )

    assert "没有直接给出 2022 年的数据依据" in answer
    assert "只明确覆盖 2021 年相关内容" in answer


def test_build_frontend_snapshot_answer_returns_temporal_gap_answer_for_missing_quarter() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="请告诉我这份文档里的第三季度基金会新增数量。",
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "summary": "该文档概述了 2021 年民政事业发展总体情况。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                ],
            }
        },
    )

    assert "没有看到明确的季度级信息" in answer


def test_ground_answer_with_frontend_context_overrides_off_topic_risk_review_answer() -> None:
    answer = Assistant1AgentRuntime._ground_answer_with_frontend_context(
        user_message="如果我是第一次核对这份文档，最应该先核对哪 3 类信息？",
        answer="你问的是 2021 年某个文件中第 3 季度的情况吗？",
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "summary": "该文档概述了 2021 年民政事业发展总体情况，并给出机构设施、老年人口、基金会等统计数据。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                    {"label": "民政服务床位总数", "value": "530.5", "confidence": 99, "page": 4},
                ],
                "table_column_headers": ["指标", "数量", "同比增长"],
            }
        },
    )

    assert "第 3 季度" not in answer
    assert "统计口径" in answer
    assert "基金会总数=8877" in answer


def test_frontend_snapshot_short_circuit_does_not_short_circuit_broad_summary_requests() -> None:
    # After Fix 1: broad document summary questions must go through real retrieval,
    # not be answered from the UI snapshot. short-circuit only fires for strict minimal requests.
    assert Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="请用中文概括当前选中文档的核心内容，并列出你当前最确定的3个字段。",
        snapshot_answer="当前选中文档的核心内容：示例。",
    ) is False


def test_frontend_snapshot_short_circuit_now_allows_risk_review_guidance() -> None:
    assert Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="如果我是第一次核对这份文档，最应该先核对哪 3 类信息？",
        snapshot_answer="如果你是第一次核对这份文档，我建议先优先看这 3 类信息：",
    ) is True


def test_frontend_snapshot_short_circuit_allows_card_selection_and_provenance() -> None:
    assert Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="如果我只能够保留两个最稳妥的字段做首页卡片，你建议保留哪两个？",
        snapshot_answer="如果首页只能保留两个最稳妥的字段，我建议优先保留这两个：",
    ) is True
    assert Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="基金会总数这个数字来自文档里的哪一类信息？",
        snapshot_answer="就当前文档快照看，基金会总数=8877 这个数字来自文档里已经抽取出来的关键统计字段/指标项。",
    ) is True


def test_frontend_snapshot_short_circuit_allows_summary_plus_3_fields_with_sufficient_context() -> None:
    assert Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
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
    ) is True


def test_build_instructions_includes_frontend_evidence_dossier_block() -> None:
    runtime = make_runtime_without_init()
    plan = runtime._plan_response(
        user_message="请用中文概括当前选中文档的核心内容，并列出你当前最确定的3个字段。",
        default_file_hash="abc123",
    )
    instructions = runtime._build_instructions(
        user_message="请用中文概括当前选中文档的核心内容，并列出你当前最确定的3个字段。",
        default_file_hash="abc123",
        response_plan=plan,
        extra_context={
            "current_document": {
                "file_name": "2021年民政事业发展统计公报.docx",
                "file_hash": "abc123",
                "summary": "该文档概述了 2021 年民政事业发展总体情况。",
                "top_fields": [
                    {"label": "统计年份", "value": "2021"},
                    {"label": "基金会总数", "value": "8877"},
                    {"label": "民政服务床位总数", "value": "530.5"},
                ],
                "table_column_headers": ["指标", "数量", "同比增长"],
            }
        },
    )
    assert "Frontend evidence dossier" in instructions
    assert '"coverage"' in instructions
    assert "must_not_invent_field_values" in instructions


def test_build_frontend_snapshot_answer_entity_extraction_json_with_missing() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="请从当前文档抽取统计年份、基金会总数和不存在字段，并按JSON输出",
        extra_context={
            "current_document": {
                "file_name": "2021年民政统计公报.docx",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                ],
            }
        },
    )

    payload = json.loads(answer)
    assert payload["intent"] == "entity_extraction"
    assert payload["requested_entities"] == ["统计年份", "基金会总数", "不存在字段"]
    assert payload["extracted"]["统计年份"] == "2021"
    assert payload["extracted"]["基金会总数"] == "8877"
    assert "不存在字段" in payload["missing"]


def test_build_frontend_snapshot_answer_entity_extraction_json_english_request_entities_clean() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="Please extract fields year, fund_count, missing_field from current document and return JSON only.",
        extra_context={
            "current_document": {
                "file_name": "demo.docx",
                "top_fields": [
                    {"label": "year", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "fund_count", "value": "8877", "confidence": 98, "page": 12},
                ],
            }
        },
    )

    payload = json.loads(answer)
    assert payload["requested_entities"] == ["year", "fund_count", "missing_field"]
    assert payload["missing"] == ["missing_field"]


def test_frontend_snapshot_short_circuit_allows_entity_extraction() -> None:
    snapshot_answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="请从当前文档抽取统计年份和基金会总数，并按JSON输出",
        extra_context={
            "current_document": {
                "file_name": "2021年民政统计公报.docx",
                "top_fields": [
                    {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
                ],
            }
        },
    )
    assert Assistant1AgentRuntime._should_short_circuit_with_frontend_snapshot(
        user_message="请从当前文档抽取统计年份和基金会总数，并按JSON输出",
        snapshot_answer=snapshot_answer,
    ) is True
