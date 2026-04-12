from __future__ import annotations


TOOL_REQUIRED_INTENTS = {
    "web_search",
    "schema_design",
    "sql_request",
    "entity_extraction",
    "document_summary",
    "document_risk_review",
    "document_lookup",
}

PRIMARY_TOOL_BY_INTENT = {
    "web_search": "web_search_tavily",
    "schema_design": "inspect_database_schema",
    "sql_request": "inspect_database_schema",
    "entity_extraction": "search_knowledge_base",
    "document_summary": "search_knowledge_base_grouped",
    "document_risk_review": "search_knowledge_base_grouped",
    "document_lookup": "search_knowledge_base",
}

DATABASE_INTENTS = {"schema_design", "sql_request"}
TOOL_FIRST_INTENTS = {"web_search", "document_summary", "document_risk_review"}


def intent_requires_tool_call(intent: str) -> bool:
    return str(intent or "").strip() in TOOL_REQUIRED_INTENTS


def primary_tool_for_intent(intent: str) -> str:
    return str(PRIMARY_TOOL_BY_INTENT.get(str(intent or "").strip()) or "")


def is_database_intent(intent: str) -> bool:
    return str(intent or "").strip() in DATABASE_INTENTS


def prefers_tool_first_execution(intent: str) -> bool:
    return str(intent or "").strip() in TOOL_FIRST_INTENTS
