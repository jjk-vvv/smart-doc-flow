from __future__ import annotations

from module2.app.assistant_1.agent_runtime import Assistant1AgentRuntime


def test_legacy_runtime_builds_multi_field_snapshot_answer_for_compound_question() -> None:
    answer = Assistant1AgentRuntime._build_frontend_snapshot_answer(
        user_message="请基于当前表格，概括订单样例里最关键的字段，并指出当前这条样例记录的订单状态和销售部门。",
        extra_context={
            "current_document": {
                "file_name": "电商销售数据.xlsx",
                "summary": "当前文档为电商销售订单样例表，已抽取出订单编号、用户编号、订单日期、销售部门、商品数量、订单状态等字段。",
                "top_fields": [
                    {"label": "用户编号", "value": "US377677", "confidence": 99},
                    {"label": "订单编号", "value": "P1696644", "confidence": 99},
                    {"label": "订单日期", "value": "2023-09-08", "confidence": 99},
                    {"label": "销售部门", "value": "销售三部", "confidence": 99},
                    {"label": "商品数量", "value": "6", "confidence": 95},
                    {"label": "订单状态", "value": "已付款", "confidence": 95},
                ],
            }
        },
    )

    assert "订单状态是已付款" in answer
    assert "销售部门是销售三部" in answer
    assert "最关键的字段包括" in answer
