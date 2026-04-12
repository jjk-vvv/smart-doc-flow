from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.answer_contracts import build_answer_contract_block

DEFINED_INTENTS = [
    "capability",
    "web_search",
    "schema_design",
    "sql_request",
    "document_lookup",
    "entity_extraction",
    "document_summary",
    "document_risk_review",
    "general_method",
    "missing_document",
]


def test_all_defined_intents_return_nonempty() -> None:
    for intent in DEFINED_INTENTS:
        block = build_answer_contract_block(intent)
        assert block, f"Expected non-empty block for intent={intent!r}"


def test_unknown_intent_returns_empty_string() -> None:
    assert build_answer_contract_block("nonexistent_intent") == ""


def test_empty_intent_returns_empty_string() -> None:
    assert build_answer_contract_block("") == ""


def test_document_lookup_mentions_uniqueness() -> None:
    block = build_answer_contract_block("document_lookup")
    assert "不唯一" in block


def test_sql_request_mentions_confirmation() -> None:
    block = build_answer_contract_block("sql_request")
    assert "确认" in block


def test_document_risk_review_instructs_against_generic() -> None:
    block = build_answer_contract_block("document_risk_review")
    assert ("泛泛而谈" in block) or ("具体" in block)


def test_missing_document_says_directly() -> None:
    block = build_answer_contract_block("missing_document")
    assert "直接说" in block


def test_schema_design_mentions_design_rationale() -> None:
    block = build_answer_contract_block("schema_design")
    assert ("设计" in block) or ("说明" in block)


def test_web_search_no_process_narration() -> None:
    block = build_answer_contract_block("web_search")
    assert ("过程" in block) or ("结论" in block)


def test_entity_extraction_mentions_missing_policy() -> None:
    block = build_answer_contract_block("entity_extraction")
    assert "missing" in block.lower()
    assert "编造" in block

