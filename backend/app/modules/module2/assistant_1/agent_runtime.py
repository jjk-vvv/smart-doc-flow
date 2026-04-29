from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .config import Assistant1Settings
from .frontend_grounding import (
    build_frontend_snapshot_answer,
    cleanup_answer_text,
    enforce_answer_with_frontend_contracts,
    frontend_context_block,
    ground_answer_with_frontend_context,
    normalize_frontend_context,
    should_short_circuit_with_frontend_snapshot,
    trim_text,
)
from .ingest_pipeline import Assistant1IngestPipeline
from .intent_router import is_action_preview_request
from .prompt_blocks import build_assistant_instructions
from .response_planner import Assistant1ResponsePlan, Assistant1ResponsePlanner
from .responses_provider import Assistant1ResponsesProvider, ResponsesCompletionResult, ResponsesFunctionCall
from .retrieval_pipeline import Assistant1RetrievalPipeline
from .sql_tools import Assistant1SchemaTools, Assistant1SqlTools
from .task_policy import is_database_intent
from .tavily_client import TavilySearchClient
from .tool_router import Assistant1ToolContext, Assistant1ToolRouter
from .warmup_runtime import Assistant1WarmupRuntime


class Assistant1AgentRuntime:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.provider = Assistant1ResponsesProvider(self.settings)
        self.retrieval = Assistant1RetrievalPipeline(self.settings)
        self.ingest = Assistant1IngestPipeline(self.settings)
        self.schema_tools = Assistant1SchemaTools(self.settings, self.provider)
        self.sql_tools = Assistant1SqlTools(self.settings, self.provider)
        self.tavily = TavilySearchClient(self.settings) if self.settings.web_search_enabled else None
        self.warmup = Assistant1WarmupRuntime(
            self.settings,
            retrieval=self.retrieval,
            ingest=self.ingest,
        )
        self.response_planner = Assistant1ResponsePlanner(
            web_search_enabled=bool(getattr(self.tavily, "ready", False))
        )
        self.tool_router = Assistant1ToolRouter(
            retrieval=self.retrieval,
            ingest=self.ingest,
            schema_tools=self.schema_tools,
            sql_tools=self.sql_tools,
            tavily=self.tavily,
        )

    def chat(
        self,
        user_message: str,
        *,
        file_hash: str = "",
        history: Optional[List[Dict[str, Any]]] = None,
        max_steps: int = 6,
        top_k: int = 5,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        question = str(user_message or "").strip()
        if not question:
            raise ValueError("user_message is required")
        resolved_file_hash = self._resolve_bound_file_hash(
            default_file_hash=file_hash,
            extra_context=extra_context,
        )

        context = Assistant1ToolContext(
            default_file_hash=resolved_file_hash,
            top_k=max(1, min(8, int(top_k or 5))),
            current_user_message=question,
        )
        response_plan = self._plan_response(
            user_message=question,
            default_file_hash=context.default_file_hash,
        )
        self._maybe_schedule_document_warmup(
            file_hash=context.default_file_hash,
            intent=response_plan.intent,
            reason="chat_start",
        )
        direct_snapshot_answer = self._build_frontend_snapshot_answer(
            user_message=question,
            extra_context=extra_context,
        )
        if not response_plan.must_clarify and self._should_short_circuit_with_frontend_snapshot(
            user_message=question,
            snapshot_answer=direct_snapshot_answer,
            extra_context=extra_context,
        ):
            self._maybe_schedule_document_warmup(
                file_hash=context.default_file_hash,
                intent=response_plan.intent,
                reason="frontend_snapshot_short_circuit",
            )
            return {
                "answer": direct_snapshot_answer,
                "response_id": "",
                "status": "completed",
                "file_hash": context.default_file_hash,
                "tool_steps": [],
                "final_output_types": ["frontend_snapshot"],
            }
        if response_plan.must_clarify:
            self._maybe_schedule_document_warmup(
                file_hash=context.default_file_hash,
                intent=response_plan.intent,
                reason="clarification_turn",
            )
            return self._clarification_payload(
                question=question,
                response_plan=response_plan,
                context=context,
                extra_context=extra_context,
            )
        if not self.provider.configured:
            raise RuntimeError("assistant_1 chat provider is not configured")
        instructions = self._build_instructions(
            user_message=question,
            default_file_hash=context.default_file_hash,
            response_plan=response_plan,
            extra_context=extra_context,
        )
        input_messages = list(history or []) + [{"role": "user", "content": question}]
        tools = self._tool_definitions(response_plan.tool_names) if response_plan.use_tools else None
        if self._uses_tool_first_execution(response_plan):
            return self._run_tool_first_chat(
                question=question,
                instructions=instructions,
                response_plan=response_plan,
                context=context,
                extra_context=extra_context,
            )

        response = self.provider.complete(
            messages=input_messages,
            instructions=instructions,
            tools=tools,
            tool_choice=response_plan.tool_choice,
            max_output_tokens=response_plan.max_output_tokens,
            reasoning_effort=response_plan.reasoning_effort,
            text_verbosity=response_plan.text_verbosity,
            metadata={
                "assistant_runtime": "assistant_1",
                "phase": "initial",
                "text_verbosity": response_plan.text_verbosity,
                "use_tools": str(response_plan.use_tools).lower(),
            },
        )

        tool_steps: List[Dict[str, Any]] = []
        direct_payload = None
        if response_plan.requires_tool_call and not response.function_calls:
            direct_payload, response, enforced_tool_steps = self._recover_missing_required_tool(
                question=question,
                input_messages=input_messages,
                instructions=instructions,
                tools=tools,
                response_plan=response_plan,
                context=context,
                extra_context=extra_context,
            )
            tool_steps.extend(enforced_tool_steps)
            if isinstance(direct_payload, dict):
                return direct_payload
        final_response = response
        consumed_steps = len(tool_steps)
        for step_index in range(consumed_steps, max(1, int(max_steps or 1))):
            if not final_response.function_calls:
                break
            tool_outputs: List[Dict[str, Any]] = []
            executed_tools: List[Dict[str, Any]] = []
            for call in final_response.function_calls:
                result = self._execute_tool(call, context)
                executed_tools.append(
                    {
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "result_preview": self._tool_result_preview(result),
                    }
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )
            tool_steps.append(
                {
                    "step": step_index + 1,
                    "response_id": final_response.response_id,
                    "executed_tools": executed_tools,
                }
            )
            final_response = self.provider.complete(
                input_items=tool_outputs,
                previous_response_id=final_response.response_id,
                instructions=instructions,
                tools=tools,
                tool_choice="auto",
                max_output_tokens=response_plan.max_output_tokens,
                reasoning_effort=response_plan.reasoning_effort,
                text_verbosity=response_plan.text_verbosity,
                metadata={
                    "assistant_runtime": "assistant_1",
                    "phase": f"tool_step_{step_index + 1}",
                    "text_verbosity": response_plan.text_verbosity,
                    "use_tools": str(response_plan.use_tools).lower(),
                },
            )

        answer = str(final_response.output_text or "").strip()
        if not answer:
            if final_response.function_calls:
                answer = (
                    "这一步我已经拿到了工具结果，但最后的自然语言总结还没有完整产出。"
                    "你可以让我继续整理，或者我也可以先把现有结果直接说给你。"
                )
            else:
                answer = "这次还没有得到稳定的最终答案。你可以换个问法，或者告诉我想优先确认哪一部分。"
        answer = self._finalize_answer_text(
            user_message=question,
            answer=answer,
            extra_context=extra_context,
            allow_snapshot_override=not response_plan.must_clarify,
        )

        return {
            "answer": answer,
            "response_id": final_response.response_id,
            "status": final_response.status,
            "file_hash": context.default_file_hash,
            "tool_steps": tool_steps,
            "final_output_types": [
                str(item.get("type") or "")
                for item in final_response.raw.get("output", [])
                if isinstance(item, dict)
            ],
        }

    def _build_instructions(
        self,
        *,
        user_message: str,
        default_file_hash: str,
        response_plan: Assistant1ResponsePlan,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        return build_assistant_instructions(
            user_message=user_message,
            default_file_hash=default_file_hash,
            response_plan=response_plan,
            extra_context=extra_context,
        )

    @staticmethod
    def _frontend_context_block(extra_context: Optional[Dict[str, Any]]) -> str:
        return frontend_context_block(extra_context)

    @staticmethod
    def _normalize_frontend_context(extra_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return normalize_frontend_context(extra_context)

    def _resolve_bound_file_hash(
        self,
        *,
        default_file_hash: str,
        extra_context: Optional[Dict[str, Any]],
    ) -> str:
        normalized_default = str(default_file_hash or "").strip()
        if normalized_default:
            return normalized_default
        compact = self._normalize_frontend_context(extra_context)
        current_document = compact.get("current_document") if isinstance(compact.get("current_document"), dict) else {}
        fallback_file_hash = str(current_document.get("file_hash") or "").strip()
        return fallback_file_hash

    def _maybe_schedule_document_warmup(self, *, file_hash: str, intent: str, reason: str = "") -> bool:
        normalized_file_hash = str(file_hash or "").strip()
        normalized_intent = str(intent or "").strip()
        if not normalized_file_hash:
            return False
        if normalized_intent in {
            "general_chat",
            "general_method",
            "capability",
            "minimal_answer",
            "missing_document",
            "web_search",
        }:
            return False
        warmup = getattr(self, "warmup", None)
        if warmup is None:
            return False
        return bool(
            warmup.schedule(
                normalized_file_hash,
                reason=reason or normalized_intent or "chat_turn",
            )
        )

    @staticmethod
    def _ground_answer_with_frontend_context(
        *,
        user_message: str,
        answer: str,
        extra_context: Optional[Dict[str, Any]],
        allow_snapshot_override: bool = True,
    ) -> str:
        return ground_answer_with_frontend_context(
            user_message=user_message,
            answer=answer,
            extra_context=extra_context,
            allow_snapshot_override=allow_snapshot_override,
        )

    @staticmethod
    def _enforce_answer_with_frontend_contracts(
        *,
        user_message: str,
        answer: str,
        extra_context: Optional[Dict[str, Any]],
        has_action_preview: bool = False,
    ) -> str:
        return enforce_answer_with_frontend_contracts(
            user_message=user_message,
            answer=answer,
            extra_context=extra_context,
            has_action_preview=has_action_preview,
        )

    def _finalize_answer_text(
        self,
        *,
        user_message: str,
        answer: str,
        extra_context: Optional[Dict[str, Any]],
        allow_snapshot_override: bool = True,
        has_action_preview: bool = False,
    ) -> str:
        grounded = self._ground_answer_with_frontend_context(
            user_message=user_message,
            answer=answer,
            extra_context=extra_context,
            allow_snapshot_override=allow_snapshot_override,
        )
        return self._enforce_answer_with_frontend_contracts(
            user_message=user_message,
            answer=grounded,
            extra_context=extra_context,
            has_action_preview=has_action_preview,
        )

    @staticmethod
    def _build_frontend_snapshot_answer(
        *,
        user_message: str,
        extra_context: Optional[Dict[str, Any]],
    ) -> str:
        return build_frontend_snapshot_answer(
            user_message=user_message,
            extra_context=extra_context,
        )

    @staticmethod
    def _should_short_circuit_with_frontend_snapshot(
        *,
        user_message: str,
        snapshot_answer: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return should_short_circuit_with_frontend_snapshot(
            user_message=user_message,
            snapshot_answer=snapshot_answer,
            extra_context=extra_context,
        )

    def _plan_response(
        self,
        *,
        user_message: str,
        default_file_hash: str,
    ) -> Assistant1ResponsePlan:
        planner = getattr(self, "response_planner", None) or Assistant1ResponsePlanner(
            web_search_enabled=bool(getattr(getattr(self, "tavily", None), "ready", False))
        )
        return planner.plan(
            user_message=user_message,
            default_file_hash=default_file_hash,
        )

    def _tool_definitions(self, tool_names: tuple[str, ...] = ()) -> List[Dict[str, Any]]:
        router = getattr(self, "tool_router", None)
        if router is None:
            router = Assistant1ToolRouter(
                retrieval=getattr(self, "retrieval", None),
                ingest=getattr(self, "ingest", None),
                schema_tools=getattr(self, "schema_tools", None),
                sql_tools=getattr(self, "sql_tools", None),
                tavily=getattr(self, "tavily", None),
            )
        return router.tool_definitions(tool_names)

    def _execute_tool(self, call: ResponsesFunctionCall, context: Assistant1ToolContext) -> Dict[str, Any]:
        router = getattr(self, "tool_router", None)
        if router is None:
            router = Assistant1ToolRouter(
                retrieval=getattr(self, "retrieval", None),
                ingest=getattr(self, "ingest", None),
                schema_tools=getattr(self, "schema_tools", None),
                sql_tools=getattr(self, "sql_tools", None),
                tavily=getattr(self, "tavily", None),
            )
        return router.execute_tool(call, context)

    @staticmethod
    def _tool_result_preview(result: Dict[str, Any]) -> Dict[str, Any]:
        return Assistant1ToolRouter.tool_result_preview(result)

    @staticmethod
    def _cleanup_answer_text(answer: str) -> str:
        return cleanup_answer_text(answer)

    @staticmethod
    def _trim_text(value: Any, limit: int) -> str:
        return trim_text(value, limit)

    @staticmethod
    def _extract_year_tokens(text: str) -> List[str]:
        hits = sorted(set(re.findall(r"\b(20\d{2})\b", str(text or ""))))
        return hits[:6]

    @staticmethod
    def _uses_tool_first_execution(response_plan: Assistant1ResponsePlan) -> bool:
        return (
            str(response_plan.tool_execution_mode or "").strip() == "tool_first"
            and bool(str(response_plan.primary_tool_name or "").strip())
        )

    def _grounded_synthesis_messages(
        self,
        *,
        question: str,
        intent: str,
        grounding_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        compact_grounding_result = self._compact_grounding_result_for_synthesis(
            question=question,
            intent=intent,
            grounding_result=grounding_result,
        )
        return [
            {
                "role": "user",
                "content": self._render_grounded_synthesis_prompt(
                    question=question,
                    intent=intent,
                    grounding_result=compact_grounding_result,
                ),
            }
        ]

    def _complete_grounded_synthesis(
        self,
        *,
        question: str,
        instructions: str,
        response_plan: Assistant1ResponsePlan,
        grounding_result: Dict[str, Any],
        phase: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str | Dict[str, Any] = "none",
    ) -> ResponsesCompletionResult:
        return self.provider.complete(
            messages=self._grounded_synthesis_messages(
                question=question,
                intent=response_plan.intent,
                grounding_result=grounding_result,
            ),
            instructions=instructions,
            tools=tools,
            tool_choice=tool_choice,
            max_output_tokens=response_plan.max_output_tokens,
            reasoning_effort=response_plan.reasoning_effort,
            text_verbosity=response_plan.text_verbosity,
            metadata={
                "assistant_runtime": "assistant_1",
                "phase": phase,
                "intent": response_plan.intent,
            },
        )

    def _run_tool_first_chat(
        self,
        *,
        question: str,
        instructions: str,
        response_plan: Assistant1ResponsePlan,
        context: Assistant1ToolContext,
        extra_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        manual_step = self._run_primary_tool_manually(
            question=question,
            response_plan=response_plan,
            context=context,
            response_id="",
        )
        if not manual_step:
            raise RuntimeError(f"tool-first execution unavailable for intent={response_plan.intent}")

        synthesized = self._complete_grounded_synthesis(
            question=question,
            instructions=instructions,
            response_plan=response_plan,
            grounding_result=manual_step["result"],
            phase="tool_first_grounded_synthesis",
        )
        tool_step = dict(manual_step["tool_step"]) if isinstance(manual_step.get("tool_step"), dict) else {}
        if tool_step:
            tool_step["response_id"] = synthesized.response_id

        answer = str(synthesized.output_text or "").strip()
        if not answer:
            answer = "这次外部资料已经补充到了，但最终自然语言整理没有稳定产出。你可以让我继续整理，或者换一个更具体的问法。"
        answer = self._finalize_answer_text(
            user_message=question,
            answer=answer,
            extra_context=extra_context,
            allow_snapshot_override=not response_plan.must_clarify,
        )

        return {
            "answer": answer,
            "response_id": synthesized.response_id,
            "status": synthesized.status or "completed",
            "file_hash": context.default_file_hash,
            "tool_steps": [tool_step] if tool_step else [],
            "final_output_types": [
                str(item.get("type") or "")
                for item in synthesized.raw.get("output", [])
                if isinstance(item, dict)
            ] or ["grounded_synthesis"],
        }

    def _recover_missing_required_tool(
        self,
        *,
        question: str,
        input_messages: List[Dict[str, Any]],
        instructions: str,
        tools: Optional[List[Dict[str, Any]]],
        response_plan: Assistant1ResponsePlan,
        context: Assistant1ToolContext,
        extra_context: Optional[Dict[str, Any]],
    ) -> tuple[Optional[Dict[str, Any]], Any, List[Dict[str, Any]]]:
        enforced_tool_steps: List[Dict[str, Any]] = []
        if response_plan.must_clarify and response_plan.clarification_reason:
            payload = self._clarification_payload(
                question=question,
                response_plan=response_plan,
                context=context,
                extra_context=extra_context,
            )
            return payload, None, enforced_tool_steps
        retry_response = self.provider.complete(
            messages=input_messages,
            instructions=instructions,
            tools=tools,
            tool_choice="required" if response_plan.use_tools else "none",
            max_output_tokens=response_plan.max_output_tokens,
            reasoning_effort=response_plan.reasoning_effort,
            text_verbosity=response_plan.text_verbosity,
            metadata={
                "assistant_runtime": "assistant_1",
                "phase": "required_tool_retry",
                "intent": response_plan.intent,
            },
        )
        if retry_response.function_calls:
            return None, retry_response, enforced_tool_steps

        if is_database_intent(response_plan.intent):
            payload = self._database_grounded_fallback_payload(
                question=question,
                response_plan=response_plan,
                context=context,
                extra_context=extra_context,
                response_id=retry_response.response_id,
                status=retry_response.status,
            )
            return payload, retry_response, enforced_tool_steps

        manual_step = self._run_primary_tool_manually(
            question=question,
            response_plan=response_plan,
            context=context,
            response_id=retry_response.response_id,
        )
        if not manual_step:
            return None, retry_response, enforced_tool_steps

        enforced_tool_steps.append(manual_step["tool_step"])
        synthesized = self._complete_grounded_synthesis(
            question=question,
            instructions=instructions,
            response_plan=response_plan,
            grounding_result=manual_step["result"],
            phase="grounded_synthesis",
        )
        return None, synthesized, enforced_tool_steps

    def _database_grounded_fallback_payload(
        self,
        *,
        question: str,
        response_plan: Assistant1ResponsePlan,
        context: Assistant1ToolContext,
        extra_context: Optional[Dict[str, Any]],
        response_id: str,
        status: str,
    ) -> Dict[str, Any]:
        if response_plan.must_clarify and response_plan.clarification_reason:
            return self._clarification_payload(
                question=question,
                response_plan=response_plan,
                context=context,
                extra_context=extra_context,
                response_id=response_id,
                status=status,
            )
        executed_tools: List[Dict[str, Any]] = []
        schema_snapshot = self.sql_tools.inspect_database_schema(include_columns=True)
        executed_tools.append(
            {
                "tool_name": "inspect_database_schema",
                "arguments": {"include_columns": True},
                "result_preview": self._tool_result_preview(schema_snapshot),
            }
        )

        if response_plan.intent == "schema_design":
            file_context = self._load_optional_file_context(question=question, context=context)
            design_result = self.schema_tools.design_schema_draft(
                objective=question,
                file_context=file_context,
            )
            executed_tools.append(
                {
                    "tool_name": "design_schema_draft",
                    "arguments": {"objective": question, "file_context": self._trim_text(file_context, 240)},
                    "result_preview": self._tool_result_preview(design_result),
                }
            )
            answer = self._render_schema_design_answer(schema_snapshot=schema_snapshot, design_result=design_result)
        else:
            mode = "read_write_draft" if self._looks_like_write_request(question) else "read_only"
            sql_result = self.sql_tools.draft_sql_from_nl(
                request=question,
                mode=mode,
            )
            executed_tools.append(
                {
                    "tool_name": "draft_sql_from_nl",
                    "arguments": {"request": question, "mode": mode},
                    "result_preview": self._tool_result_preview(sql_result),
                }
            )
            answer = self._render_sql_draft_answer(schema_snapshot=schema_snapshot, sql_result=sql_result)

        answer = self._finalize_answer_text(
            user_message=question,
            answer=answer,
            extra_context=extra_context,
            allow_snapshot_override=not response_plan.must_clarify,
        )
        return {
            "answer": answer,
            "response_id": response_id,
            "status": status or "completed",
            "file_hash": context.default_file_hash,
            "tool_steps": [
                {
                    "step": 1,
                    "response_id": response_id,
                    "executed_tools": executed_tools,
                }
            ],
            "final_output_types": ["grounded_fallback"],
        }

    def _run_primary_tool_manually(
        self,
        *,
        question: str,
        response_plan: Assistant1ResponsePlan,
        context: Assistant1ToolContext,
        response_id: str,
    ) -> Optional[Dict[str, Any]]:
        tool_name = str(response_plan.primary_tool_name or "").strip()
        if not tool_name:
            return None
        arguments = self._manual_tool_arguments(
            tool_name=tool_name,
            question=question,
            response_plan=response_plan,
            context=context,
        )
        call = ResponsesFunctionCall(
            id=f"manual_{tool_name}",
            call_id=f"manual_{tool_name}",
            name=tool_name,
            arguments=arguments,
            raw_arguments=json.dumps(arguments, ensure_ascii=False),
        )
        result = self._execute_tool(call, context)
        return {
            "call": call,
            "result": result,
            "tool_step": {
                "step": 1,
                "response_id": response_id,
                "executed_tools": [
                    {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "result_preview": self._tool_result_preview(result),
                    }
                ],
            },
        }

    def _manual_tool_arguments(
        self,
        *,
        tool_name: str,
        question: str,
        response_plan: Assistant1ResponsePlan,
        context: Assistant1ToolContext,
    ) -> Dict[str, Any]:
        if tool_name in {"search_knowledge_base", "search_knowledge_base_grouped"}:
            payload: Dict[str, Any] = {"query": question, "top_k": context.top_k}
            if context.default_file_hash:
                payload["file_hash"] = context.default_file_hash
            preferred_unit_types = self._preferred_unit_types_for_intent(
                intent=response_plan.intent,
                question=question,
            )
            if preferred_unit_types:
                payload["unit_types"] = preferred_unit_types
            return payload
        if tool_name == "web_search_tavily":
            return {
                "query": question,
                "max_results": 5,
            }
        if tool_name == "inspect_database_schema":
            return {"include_columns": True}
        return {}

    @staticmethod
    def _preferred_unit_types_for_intent(*, intent: str, question: str) -> List[str]:
        normalized_intent = str(intent or "").strip()
        lowered = str(question or "").lower()
        if normalized_intent == "document_summary":
            preferred = ["narrative_chunk", "table_overview", "figure_overview"]
            if any(marker in lowered for marker in ("table", "表格")):
                return ["table_overview", "narrative_chunk", "figure_overview"]
            if any(marker in lowered for marker in ("figure", "chart", "图", "图表")):
                return ["figure_overview", "narrative_chunk", "table_overview"]
            return preferred
        if normalized_intent == "document_risk_review":
            preferred = ["table_overview", "figure_overview", "narrative_chunk"]
            if any(marker in lowered for marker in ("document", "文档", "report", "公报")):
                return ["narrative_chunk", "table_overview", "figure_overview"]
            return preferred
        return []

    def _load_optional_file_context(self, *, question: str, context: Assistant1ToolContext) -> str:
        if not context.default_file_hash:
            return ""
        tool_name = "search_knowledge_base_grouped"
        arguments = {
            "query": question,
            "file_hash": context.default_file_hash,
            "top_k": min(4, context.top_k),
        }
        call = ResponsesFunctionCall(
            id="manual_file_context",
            call_id="manual_file_context",
            name=tool_name,
            arguments=arguments,
            raw_arguments=json.dumps(arguments, ensure_ascii=False),
        )
        result = self._execute_tool(call, context)
        return self._summarize_search_result(result)

    @staticmethod
    def _summarize_search_result(result: Dict[str, Any]) -> str:
        if not isinstance(result, dict) or not bool(result.get("ok")):
            return ""
        lines: List[str] = []
        year_groups = result.get("year_groups")
        for group in year_groups if isinstance(year_groups, list) else []:
            if not isinstance(group, dict):
                continue
            label = str(group.get("year_label") or "").strip()
            if label:
                lines.append(f"年份分组：{label}")
        matches = result.get("matches")
        for match in matches if isinstance(matches, list) else []:
            if not isinstance(match, dict):
                continue
            title = str(match.get("title") or "").strip()
            preview = str(match.get("content_preview") or "").strip()
            row = " - ".join(part for part in (title, preview) if part)
            if row:
                lines.append(row)
            if len(lines) >= 4:
                break
        return "\n".join(lines[:4]).strip()

    def _compact_grounding_result_for_synthesis(
        self,
        *,
        question: str,
        intent: str,
        grounding_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(grounding_result, dict):
            return {"ok": False, "error": "invalid_grounding_result"}

        compact: Dict[str, Any] = {"ok": bool(grounding_result.get("ok"))}
        for key in ("error", "answer", "recommended_response", "preferred_title", "preferred_url"):
            value = str(grounding_result.get(key) or "").strip()
            if value:
                compact[key] = self._trim_text(value, 600)

        warnings = [
            self._trim_text(item, 220)
            for item in grounding_result.get("warnings", [])
            if str(item or "").strip()
        ] if isinstance(grounding_result.get("warnings"), list) else []
        if warnings:
            compact["warnings"] = warnings[:4]

        if isinstance(grounding_result.get("preferred_result"), dict):
            preferred_result = grounding_result.get("preferred_result") or {}
            compact["preferred_result"] = {
                "title": self._trim_text(preferred_result.get("title"), 220),
                "url": self._trim_text(preferred_result.get("url"), 220),
                "content": self._trim_text(
                    preferred_result.get("content") or preferred_result.get("snippet"),
                    500,
                ),
            }

        if isinstance(grounding_result.get("results"), list):
            web_results: List[Dict[str, Any]] = []
            for item in grounding_result.get("results", [])[:5]:
                if not isinstance(item, dict):
                    continue
                title = self._trim_text(item.get("title"), 220)
                url = self._trim_text(item.get("url"), 220)
                content = self._trim_text(item.get("content") or item.get("snippet"), 360)
                if title or content or url:
                    web_results.append({"title": title, "url": url, "content": content})
            if web_results:
                compact["results"] = web_results

        compact_matches = self._compact_matches_for_synthesis(
            intent=intent,
            matches=grounding_result.get("matches"),
        )
        if compact_matches:
            compact["matches"] = compact_matches

        compact_year_groups = self._compact_year_groups_for_synthesis(grounding_result.get("year_groups"))
        if compact_year_groups:
            compact["year_groups"] = compact_year_groups

        if str(intent or "").strip() == "document_summary":
            compact["summary_focus"] = self._build_summary_focus(
                question=question,
                matches=compact_matches,
                year_groups=compact_year_groups,
            )
        if str(intent or "").strip() == "document_risk_review":
            compact["verification_focus"] = self._build_verification_focus(
                question=question,
                matches=compact_matches,
                year_groups=compact_year_groups,
            )
        return compact

    def _compact_matches_for_synthesis(self, *, intent: str, matches: Any) -> List[Dict[str, Any]]:
        if not isinstance(matches, list):
            return []
        selected: List[Dict[str, Any]] = []
        seen_signatures: set[tuple[str, str]] = set()
        for item in matches:
            if not isinstance(item, dict):
                continue
            unit_type = str(item.get("unit_type") or "").strip()
            title = str(item.get("title") or "").strip()
            preview = str(item.get("content_preview") or "").strip()
            if not title and not preview:
                continue
            if str(intent or "").strip() in {"document_summary", "document_risk_review"}:
                if self._looks_like_low_value_summary_match(title=title, preview=preview):
                    continue
            signature = (unit_type, title or self._trim_text(preview, 80))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            payload = {
                "rank": int(item.get("rank") or len(selected) + 1),
                "unit_type": unit_type,
                "title": self._trim_text(title, 180),
                "content_preview": self._trim_text(preview, 320),
            }
            year_hints = [str(value).strip() for value in item.get("year_hints", []) if str(value).strip()]
            if year_hints:
                payload["year_hints"] = year_hints[:4]
            if title or preview:
                selected.append(payload)
            if len(selected) >= 6:
                break
        return selected

    def _compact_year_groups_for_synthesis(self, year_groups: Any) -> List[Dict[str, Any]]:
        if not isinstance(year_groups, list):
            return []
        compact: List[Dict[str, Any]] = []
        for item in year_groups[:4]:
            if not isinstance(item, dict):
                continue
            compact_item = {
                "year_label": str(item.get("year_label") or "").strip(),
                "match_count": int(item.get("match_count") or 0),
                "titles": [
                    self._trim_text(title, 120)
                    for title in item.get("titles", [])[:4]
                    if str(title or "").strip()
                ],
            }
            snippets = [
                self._trim_text(snippet, 180)
                for snippet in item.get("snippets", [])[:2]
                if str(snippet or "").strip()
            ]
            if snippets:
                compact_item["snippets"] = snippets
            compact.append(compact_item)
        return compact

    def _build_summary_focus(
        self,
        *,
        question: str,
        matches: List[Dict[str, Any]],
        year_groups: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        del question
        titles: List[str] = []
        supporting_points: List[str] = []
        for item in matches:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            preview = str(item.get("content_preview") or "").strip()
            if title and title not in titles:
                titles.append(title)
            if preview and preview not in supporting_points:
                supporting_points.append(preview)
        time_scope = [
            str(item.get("year_label") or "").strip()
            for item in year_groups
            if isinstance(item, dict) and str(item.get("year_label") or "").strip() not in {"", "unknown", "multi_year"}
        ]
        return {
            "first_answer_should_cover": ["整体主题", "对象范围", "时间范围"],
            "priority_titles": titles[:4],
            "time_scope": time_scope[:4],
            "supporting_points": supporting_points[:3],
        }

    def _build_verification_focus(
        self,
        *,
        question: str,
        matches: List[Dict[str, Any]],
        year_groups: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        focus_points: List[str] = []
        normalized_question = str(question or "").lower()
        if len(year_groups) > 1 or any(
            str(item.get("year_label") or "").strip() == "multi_year"
            for item in year_groups
            if isinstance(item, dict)
        ):
            focus_points.append("先核对是否混入了不同年份、版本或统计口径的内容。")
        if any(str(item.get("unit_type") or "").strip().startswith("table_") for item in matches):
            focus_points.extend(
                [
                    "先看表头和列名是否真的对齐，避免答对数字但答错指标列。",
                    "再看对象列、时间列、单位列是否锁定到同一行上下文，避免串行或串列。",
                ]
            )
        if any(str(item.get("unit_type") or "").strip().startswith("figure_") for item in matches):
            focus_points.append("需要核对图表结论和正文叙述是否一致，尤其是趋势判断和极值描述。")
        if not focus_points:
            focus_points.extend(
                [
                    "先核对对象范围和时间范围是否唯一。",
                    "再核对关键指标的统计口径、单位和是否来自同一段依据。",
                ]
            )
        if any(marker in normalized_question for marker in ("table", "表格", "当前表")):
            focus_points.insert(0, "优先检查当前表格是否存在表头歧义、列错位或相邻行串读。")
        return {
            "meaning_of_risk_point": "这里的风险点默认指最值得优先核对的验证风险，不是业务后果大小。",
            "priority_checks": focus_points[:4],
        }

    @staticmethod
    def _looks_like_low_value_summary_match(*, title: str, preview: str) -> bool:
        normalized_title = str(title or "").strip()
        normalized_preview = str(preview or "").strip()
        if not normalized_title and not normalized_preview:
            return True
        if normalized_title in {"2024年度", "2023年度", "综述", "目录"}:
            return True
        if normalized_title and len(normalized_title) <= 2:
            return True
        compact_preview = re.sub(r"\s+", " ", normalized_preview)
        if compact_preview and re.fullmatch(r"(?:\d+\s*){6,}", compact_preview):
            return True
        return False

    @staticmethod
    def _render_grounded_synthesis_prompt(
        *,
        question: str,
        intent: str,
        grounding_result: Dict[str, Any],
    ) -> str:
        lines = [
            "请只基于下面已经整理好的依据回答用户原始问题。",
            "回答要自然、直接，像真人同事在继续解释，不要写成系统日志。",
            "不要暴露工具名、函数调用、检索链路、内部 id 或系统过程。",
            "如果依据仍然不够，就直接说明还缺什么，不要猜。",
        ]
        if str(intent or "").strip() == "web_search":
            if bool(grounding_result.get("ok")):
                lines.append(
                    "这批依据来自你本轮刚拿到的外部检索结果。"
                    "如果用户追问“你是否真的联网了”“是不是刚查的”，可以直接诚实回答“是，我刚才查了外部资料”，"
                    "但不要展开工具实现细节。"
                )
                lines.append(
                    "不要再说自己无法联网、不能访问互联网，除非下面的依据明确显示这次外部检索失败。"
                )
                if str(grounding_result.get("recommended_response") or "").strip():
                    lines.append(
                        "如果依据里已经有 recommended_response、preferred_result、preferred_title 或 answer，"
                        "优先吸收这些高置信线索，不要无视它们再说“没有找到相关资料”。"
                    )
            else:
                lines.append(
                    "这次外部检索没有成功。如果用户追问是否联网，就如实说明这次尝试失败，不要假装已经查到。"
                )
        if str(intent or "").strip() in {"document_summary", "document_risk_review"}:
            lines.append(
                "如果依据里包含 matches、year_groups 或表格/图表摘要，优先抓主轴内容，不要把零散定义、边角说明或次要注释写成主结论。"
            )
            lines.append(
                "如果原始问题是在问“这份文档主要讲什么”“主要描述什么”，先回答文档的整体主题、对象和时间范围，"
                "再补关键内容，不要一上来铺很多零散字段定义。"
            )
        if str(intent or "").strip() == "document_summary":
            lines.append(
                "如果依据里已经给了 summary_focus，就先围绕那几个主点组织成一段自然概括，不要把目录项或孤立标题当成总结本身。"
            )
        if str(intent or "").strip() == "document_risk_review":
            lines.append(
                "这里说的“风险点”默认是当前文档/表格里最值得优先核对的验证风险，"
                "比如年份版本混用、对象或时间没锁定、表头列错位、统计口径或单位不一致、图表和正文不一致。"
            )
            lines.append(
                "除非用户明确在问业务后果、健康危害或经营风险，否则不要把“哪个数值最高/最异常”直接当成风险点本身。"
            )
        if str(intent or "").strip() == "document_lookup":
            lines.append(
                "如果已经锁定到了值，就直接回答；如果还存在多个时间点、多个对象或多个口径，就明确指出还缺哪一个限定条件。"
            )
        lines.extend(
            [
                "",
                f"原始问题：{question}",
                f"任务类型：{intent}",
                "依据(JSON)：",
                json.dumps(grounding_result, ensure_ascii=False, indent=2),
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _render_schema_design_answer(*, schema_snapshot: Dict[str, Any], design_result: Dict[str, Any]) -> str:
        if not bool(design_result.get("ok")):
            return (
                "这次我还没有整理出一版稳定可用的表结构草案。"
                f"主要原因是：{design_result.get('error') or '设计结果暂时不可用'}。"
            )

        parts: List[str] = []
        table_count = int(schema_snapshot.get("table_count") or 0)
        summary = str(design_result.get("design_summary") or "").strip()
        tables = design_result.get("tables", []) if isinstance(design_result.get("tables"), list) else []

        if table_count > 0:
            parts.append(
                f"我先看了一遍当前库里已经存在的 {table_count} 张表，再按你这次的目标收成一版更适合落库和后续查询的方案。"
            )
        elif tables:
            parts.append("如果先以稳定入库和后续查询为目标，这份数据可以先按下面这版结构落。")

        if summary:
            parts.append(summary)

        for table in tables[:3]:
            if not isinstance(table, dict):
                continue
            name = str(table.get("name") or "").strip()
            purpose = str(table.get("purpose") or "").strip()
            columns = table.get("columns") if isinstance(table.get("columns"), list) else []
            column_names = [str(item.get("name") or "").strip() for item in columns[:8] if isinstance(item, dict)]
            primary_key = [str(item).strip() for item in table.get("primary_key", []) if str(item).strip()]
            has_unique = bool(table.get("unique_constraints"))
            has_indexes = bool(table.get("indexes"))
            if not name:
                continue

            sentence = f"比较稳的做法是先落一张 `{name}`"
            if purpose:
                sentence += f"，用来承接{purpose}"
            if column_names:
                sentence += f"，首批字段可以先放 {', '.join(column_names)}"
            if primary_key:
                sentence += f"，主键先用 {', '.join(primary_key)}"
            if has_unique:
                sentence += "，再补一层唯一约束来防止重复入库"
            if has_indexes:
                sentence += "，常查字段建议顺手建索引"
            parts.append(sentence + "。")

        ddl_statements = [
            str(item).strip()
            for item in design_result.get("ddl_statements", [])[:3]
            if str(item or "").strip()
        ]
        if ddl_statements:
            parts.append("```sql\n" + "\n\n".join(ddl_statements) + "\n```")

        assumptions = [str(item).strip() for item in design_result.get("assumptions", [])[:4] if str(item or "").strip()]
        if assumptions:
            parts.append("这版草案默认基于这些前提：" + "；".join(assumptions) + "。")

        return "\n\n".join(part for part in parts if part).strip()

    @staticmethod
    def _render_sql_draft_answer(*, schema_snapshot: Dict[str, Any], sql_result: Dict[str, Any]) -> str:
        if not bool(sql_result.get("ok")):
            error_text = str(sql_result.get("error") or "").strip()
            return (
                "这次我还没有拿到一条稳定可用的 SQL 草案，当前草案不可用。"
                f"主要原因是：{error_text or 'SQL 草案暂时不可用'}。"
            )

        sql_text = str(sql_result.get("sql") or "").strip()
        explanation = str(sql_result.get("explanation") or "").strip()
        parts: List[str] = []
        table_count = int(schema_snapshot.get("table_count") or 0)

        if table_count > 0:
            parts.append(f"我先看了当前库结构，现有可见表一共 {table_count} 张，下面这条 SQL 是按这层结构整理出来的草案。")
        elif sql_result.get("schema_offline"):
            parts.append("当前数据库结构暂时拿不到，下面这条 SQL 是按你的请求先整理出的草案，真正执行前最好再核一下表名和字段。")

        if explanation:
            parts.append(explanation)
        if sql_text:
            parts.append("```sql\n" + sql_text + "\n```")
        else:
            parts.append("这次还不能直接给出 SQL，因为当前信息还不够完整。")

        assumptions = [str(item).strip() for item in sql_result.get("assumptions", [])[:4] if str(item or "").strip()]
        if assumptions:
            parts.append("我这边暂时按这些前提理解：" + "；".join(assumptions) + "。")
        if bool(sql_result.get("requires_confirmation")):
            parts.append("这一步涉及写操作或结构变更，我先不直接执行，等你确认之后再继续。")

        return "\n\n".join(part for part in parts if part).strip()

    @staticmethod
    def _looks_like_write_request(question: str) -> bool:
        lowered = str(question or "").lower()
        if is_action_preview_request(question):
            return True
        if any(
            marker in lowered
            for marker in (
                "不要执行",
                "别执行",
                "先别执行",
                "do not execute",
                "don't execute",
                "do not run",
                "don't run",
            )
        ):
            return False
        return any(
            marker in lowered
            for marker in (
                "插入",
                "新增",
                "写入",
                "更新",
                "修改",
                "删除",
                "建表",
                "create table",
                "insert ",
                "update ",
                "delete ",
                "alter table",
                "drop table",
            )
        )

    def _clarification_payload(
        self,
        *,
        question: str,
        response_plan: Assistant1ResponsePlan,
        context: Assistant1ToolContext,
        extra_context: Optional[Dict[str, Any]],
        response_id: str = "",
        status: str = "completed",
    ) -> Dict[str, Any]:
        answer = (
            "这个问题可能对应多条记录。"
            f"{response_plan.clarification_reason} "
            "告诉我时间点、记录范围或统计口径，我马上帮你定位。"
        )
        answer = self._finalize_answer_text(
            user_message=question,
            answer=answer,
            extra_context=extra_context,
            allow_snapshot_override=False,
        )
        return {
            "answer": answer,
            "response_id": response_id,
            "status": status or "completed",
            "file_hash": context.default_file_hash,
            "tool_steps": [],
            "final_output_types": ["clarification_required"],
        }
