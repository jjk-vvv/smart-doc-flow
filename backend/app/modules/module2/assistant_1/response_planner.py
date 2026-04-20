from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .intent_router import (
    Assistant1IntentSignals,
    collect_intent_signals,
    contains_any,
    is_broad_document_question,
    is_action_preview_request,
    is_strict_minimal_request,
    looks_like_fact_lookup,
    prefers_active_document_grounding,
    should_prefer_frontend_grounding,
)
from .task_policy import intent_requires_tool_call, prefers_tool_first_execution, primary_tool_for_intent


def _tool_choice_for_name(name: str) -> dict[str, Any]:
    return {"type": "function", "name": str(name or "").strip()}


def _text_verbosity(*, low: bool = False, high: bool = False) -> str:
    if low:
        return "low"
    if high:
        return "high"
    return "medium"


def _max_tokens(low: int, medium: int, high: int, *, low_mode: bool, high_mode: bool) -> int:
    if low_mode:
        return low
    if high_mode:
        return high
    return medium


@dataclass(frozen=True)
class Assistant1ResponsePlan:
    use_tools: bool = True
    text_verbosity: str = "medium"
    max_output_tokens: int = 900
    reasoning_effort: str = "minimal"
    tool_names: tuple[str, ...] = ()
    intent: str = "general_chat"
    must_clarify: bool = False
    clarification_reason: str = ""
    tool_choice: str | dict[str, Any] = "auto"
    requires_tool_call: bool = False
    primary_tool_name: str = ""
    tool_execution_mode: str = "model_first"


class Assistant1ResponsePlanner:
    def plan(self, *, user_message: str, default_file_hash: str) -> Assistant1ResponsePlan:
        question = str(user_message or "").strip()
        has_default_file = bool(str(default_file_hash or "").strip())
        signals = collect_intent_signals(question, has_default_file=has_default_file)

        document_context_question = self._is_document_context_question(signals)
        if (signals.document_specific or signals.entity_extraction) and not has_default_file:
            return Assistant1ResponsePlan(
                use_tools=False,
                text_verbosity="low",
                max_output_tokens=220,
                reasoning_effort="minimal",
                tool_names=(),
                intent="missing_document",
            )

        if signals.capability:
            return self._plan_free_text(
                intent="capability",
                signals=signals,
                low_tokens=260,
                medium_tokens=900,
                high_tokens=1300,
            )

        if signals.action_preview or is_action_preview_request(signals.question):
            tool_names = ["inspect_database_schema", "draft_sql_from_nl"]
            if self._document_available_for_tool(signals):
                tool_names.append("search_knowledge_base")
            return self._plan_tool_call(
                intent="sql_request",
                signals=signals,
                tool_names=tuple(dict.fromkeys(tool_names)),
                low_tokens=850,
                medium_tokens=1150,
                high_tokens=1450,
            )

        if signals.schema_design:
            tool_names = ["inspect_database_schema", "design_schema_draft"]
            if self._document_available_for_tool(signals):
                tool_names.append("search_knowledge_base_grouped" if signals.broad_document else "search_knowledge_base")
            return self._plan_tool_call(
                intent="schema_design",
                signals=signals,
                tool_names=tuple(dict.fromkeys(tool_names)),
                low_tokens=900,
                medium_tokens=1200,
                high_tokens=1500,
            )

        if signals.sql_request:
            tool_names = ["inspect_database_schema", "draft_sql_from_nl"]
            if self._looks_like_execution_request(signals.question):
                tool_names.append("execute_sql_with_audit")
            if self._document_available_for_tool(signals):
                tool_names.append("search_knowledge_base")
            return self._plan_tool_call(
                intent="sql_request",
                signals=signals,
                tool_names=tuple(dict.fromkeys(tool_names)),
                low_tokens=850,
                medium_tokens=1150,
                high_tokens=1450,
                must_clarify=signals.ambiguous_record_lookup,
                clarification_reason=(
                    "当前问题可能同时对应多条记录或多个时间点，先补一个时间或范围限定更稳。"
                    if signals.ambiguous_record_lookup
                    else ""
                ),
            )

        if signals.web_search:
            return self._plan_tool_call(
                intent="web_search",
                signals=signals,
                tool_names=("web_search_tavily",),
                low_tokens=700,
                medium_tokens=950,
                high_tokens=1200,
            )

        if signals.general_method:
            return self._plan_free_text(
                intent="general_method",
                signals=signals,
                low_tokens=320,
                medium_tokens=920,
                high_tokens=1250,
            )

        if signals.entity_extraction:
            tool_names = ["search_knowledge_base", "ingest_document"]
            if signals.broad_document:
                tool_names.insert(1, "search_knowledge_base_grouped")
            return self._plan_tool_call(
                intent="entity_extraction",
                signals=signals,
                tool_names=tuple(dict.fromkeys(tool_names)),
                low_tokens=420,
                medium_tokens=900,
                high_tokens=1200,
            )

        if document_context_question:
            if signals.document_risk_review:
                return self._plan_tool_call(
                    intent="document_risk_review",
                    signals=signals,
                    tool_names=("search_knowledge_base_grouped", "ingest_document"),
                    low_tokens=700,
                    medium_tokens=980,
                    high_tokens=1250,
                )
            if signals.broad_document:
                return self._plan_tool_call(
                    intent="document_summary",
                    signals=signals,
                    tool_names=("search_knowledge_base_grouped", "ingest_document"),
                    low_tokens=650,
                    medium_tokens=900,
                    high_tokens=1200,
                    prefer_low_verbosity=not signals.detailed,
                )
            return self._plan_tool_call(
                intent="document_lookup",
                signals=signals,
                tool_names=("search_knowledge_base", "ingest_document"),
                low_tokens=220,
                medium_tokens=820,
                high_tokens=1100,
                must_clarify=signals.ambiguous_record_lookup,
                clarification_reason=(
                    "当前问题还缺少能唯一锁定记录的限定条件，比如时间点、记录范围或统计口径。"
                    if signals.ambiguous_record_lookup
                    else ""
                ),
            )

        if signals.strict_minimal:
            return Assistant1ResponsePlan(
                use_tools=False,
                text_verbosity="low",
                max_output_tokens=120,
                reasoning_effort="minimal",
                tool_names=(),
                intent="minimal_answer",
            )

        return self._plan_free_text(
            intent="general_chat",
            signals=signals,
            low_tokens=260,
            medium_tokens=850,
            high_tokens=1200,
        )

    @staticmethod
    def _is_document_context_question(signals: Assistant1IntentSignals) -> bool:
        if not signals.has_default_file:
            return False
        if signals.capability or signals.web_search or signals.schema_design or signals.sql_request:
            return False
        return (
            signals.document_specific
            or signals.broad_document
            or signals.field_lookup
            or prefers_active_document_grounding(signals.question, signals.has_default_file)
            or looks_like_fact_lookup(signals.question)
        )

    @staticmethod
    def _document_available_for_tool(signals: Assistant1IntentSignals) -> bool:
        """True when a file is bound AND the question appears to reference document content.
        Used for schema/SQL branches which are excluded from _is_document_context_question
        to allow document-driven schema design and NL2SQL to access KB retrieval tools."""
        if not signals.has_default_file:
            return False
        return (
            signals.document_specific
            or signals.broad_document
            or signals.field_lookup
            or prefers_active_document_grounding(signals.question, signals.has_default_file)
            or looks_like_fact_lookup(signals.question)
        )

    @staticmethod
    def _looks_like_execution_request(question: str) -> bool:
        lowered = str(question or "").lower()
        if contains_any(
            lowered,
            (
                "不要执行",
                "别执行",
                "先别执行",
                "不要运行",
                "do not execute",
                "don't execute",
                "do not run",
                "don't run",
                "without executing",
            ),
        ):
            return False
        return contains_any(
            lowered,
            (
                "执行",
                "运行",
                "写入",
                "入库",
                "落库",
                "create table",
                "insert ",
                "update ",
                "delete ",
                "alter table",
                "drop table",
                "run ",
                "execute ",
            ),
        )

    def _plan_free_text(
        self,
        *,
        intent: str,
        signals: Assistant1IntentSignals,
        low_tokens: int,
        medium_tokens: int,
        high_tokens: int,
    ) -> Assistant1ResponsePlan:
        low_mode = signals.strict_minimal or signals.brief
        high_mode = signals.detailed and not low_mode
        return Assistant1ResponsePlan(
            use_tools=False,
            text_verbosity=_text_verbosity(low=low_mode, high=high_mode),
            max_output_tokens=_max_tokens(
                low_tokens,
                medium_tokens,
                high_tokens,
                low_mode=low_mode,
                high_mode=high_mode,
            ),
            reasoning_effort="minimal",
            tool_names=(),
            intent=intent,
        )

    def _plan_tool_call(
        self,
        *,
        intent: str,
        signals: Assistant1IntentSignals,
        tool_names: tuple[str, ...],
        low_tokens: int,
        medium_tokens: int,
        high_tokens: int,
        must_clarify: bool = False,
        clarification_reason: str = "",
        prefer_low_verbosity: bool = False,
    ) -> Assistant1ResponsePlan:
        low_mode = signals.strict_minimal or signals.brief or prefer_low_verbosity
        high_mode = signals.detailed and not low_mode
        primary_tool_name = primary_tool_for_intent(intent)
        tool_choice: str | dict[str, Any] = "auto"
        if primary_tool_name:
            tool_choice = _tool_choice_for_name(primary_tool_name)
        return Assistant1ResponsePlan(
            use_tools=bool(tool_names),
            text_verbosity=_text_verbosity(low=low_mode, high=high_mode),
            max_output_tokens=_max_tokens(
                low_tokens,
                medium_tokens,
                high_tokens,
                low_mode=low_mode,
                high_mode=high_mode,
            ),
            reasoning_effort="minimal",
            tool_names=tool_names,
            intent=intent,
            must_clarify=must_clarify,
            clarification_reason=clarification_reason,
            tool_choice=tool_choice,
            requires_tool_call=intent_requires_tool_call(intent),
            primary_tool_name=primary_tool_name,
            tool_execution_mode="tool_first" if prefers_tool_first_execution(intent) else "model_first",
        )
