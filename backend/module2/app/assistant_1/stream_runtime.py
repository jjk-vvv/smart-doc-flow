from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from .agent_runtime import Assistant1AgentRuntime, Assistant1ToolContext
from .responses_provider import ResponsesCompletionResult, ResponsesFunctionCall, ResponsesStreamEvent
from .streaming import Assistant1SSEEmitter, Assistant1TextBuffer


class Assistant1StreamingRuntime(Assistant1AgentRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.heartbeat_interval_sec = 4.0

    async def stream_chat(
        self,
        *,
        user_message: str,
        file_hash: str = "",
        history: Optional[List[Dict[str, Any]]] = None,
        max_steps: int = 6,
        top_k: int = 5,
        session_id: str = "",
        debug: bool = False,
        client_supports_replace: bool = True,
    ) -> AsyncIterator[bytes]:
        emitter = Assistant1SSEEmitter(session_id=session_id, debug=debug)
        for packet in (emitter.stream_open(), emitter.assistant_start()):
            if packet:
                yield packet

        question = str(user_message or "").strip()
        if not question:
            error_packet = emitter.error(
                "empty_message",
                "这次没有收到有效问题，你可以直接输入想问的内容。",
                can_retry=True,
            )
            if error_packet:
                yield error_packet
            done_packet = emitter.done(
                final_text="",
                finish_reason="error_recovered",
                requires_followup=False,
            )
            if done_packet:
                yield done_packet
            return

        if not self.provider.configured:
            error_packet = emitter.error(
                "provider_not_configured",
                "当前对话模型还没有配置好，暂时不能开始回答。",
                recoverable=False,
                can_retry=False,
            )
            if error_packet:
                yield error_packet
            done_packet = emitter.done(
                final_text="",
                finish_reason="error_recovered",
                requires_followup=False,
            )
            if done_packet:
                yield done_packet
            return

        preparing_packet = emitter.status(
            "preparing",
            "正在准备上下文",
            "我先把这轮问题和当前上下文整理一下。",
            phase="preparing",
        )
        if preparing_packet:
            yield preparing_packet
        planning_packet = emitter.status(
            "planning",
            "正在理解你的问题",
            "我会先判断这轮是否需要检索、联网或数据库工具。",
            phase="planning",
        )
        if planning_packet:
            yield planning_packet

        context = Assistant1ToolContext(
            default_file_hash=str(file_hash or "").strip(),
            top_k=max(1, min(8, int(top_k or 5))),
        )
        response_plan = self._plan_response(
            user_message=question,
            default_file_hash=context.default_file_hash,
        )
        instructions = self._build_instructions(
            user_message=question,
            default_file_hash=context.default_file_hash,
            response_plan=response_plan,
        )
        input_messages = list(history or []) + [{"role": "user", "content": question}]
        tools = self._tool_definitions(response_plan.tool_names) if response_plan.use_tools else None

        text_buffer = Assistant1TextBuffer(
            flush_chars=52 if response_plan.text_verbosity == "high" else 36,
            flush_timeout_ms=140 if response_plan.text_verbosity == "high" else 110,
        )
        emitted_text = ""
        current_response_id = ""
        warnings: List[str] = []
        emitted_evidence_keys: set[str] = set()
        action_preview_payload: Optional[Dict[str, Any]] = None
        finish_reason = "completed"
        answering_status_sent = False

        previous_response_id = ""
        pending_input_items: Optional[List[Dict[str, Any]]] = None
        last_provider_completion: Optional[ResponsesCompletionResult] = None

        for step_index in range(max(1, int(max_steps or 1))):
            current_calls: List[ResponsesFunctionCall] = []
            stream_error: Exception | None = None
            current_response_id = ""

            try:
                async for event in self._stream_provider_events_async(
                    messages=input_messages if pending_input_items is None else None,
                    input_items=pending_input_items,
                    instructions=instructions,
                    tools=tools,
                    tool_choice="auto",
                    max_output_tokens=response_plan.max_output_tokens,
                    reasoning_effort=response_plan.reasoning_effort,
                    text_verbosity=response_plan.text_verbosity,
                    previous_response_id=previous_response_id,
                    metadata={
                        "assistant_runtime": "assistant_1",
                        "delivery": "sse",
                        "phase": "initial" if step_index == 0 else f"tool_step_{step_index}",
                    },
                ):
                    if event.type == "heartbeat":
                        heartbeat_packet = emitter.heartbeat(
                            int(event.raw.get("idle_ms") or 0),
                            phase="heartbeat",
                        )
                        if heartbeat_packet:
                            yield heartbeat_packet
                        continue
                    if event.response_id:
                        current_response_id = event.response_id
                    if event.output_text_delta:
                        if not answering_status_sent:
                            answer_status = emitter.status(
                                "answering",
                                "正在整理回答",
                                "我会直接把能确定的内容流式输出给你。",
                                phase="answering",
                            )
                            if answer_status:
                                yield answer_status
                            answering_status_sent = True
                        emitted_text, packet = self._append_stream_text(
                            emitter=emitter,
                            buffer=text_buffer,
                            emitted_text=emitted_text,
                            delta_text=event.output_text_delta,
                        )
                        if packet:
                            yield packet
                    if (
                        event.function_call
                        and event.type in {"response.function_call_arguments.done", "response.output_item.done"}
                        and (event.function_call.raw_arguments or event.function_call.arguments)
                    ):
                        if not any(existing.id == event.function_call.id for existing in current_calls):
                            current_calls.append(event.function_call)
            except Exception as exc:
                stream_error = exc

            emitted_text, packet = self._flush_text_buffer(
                emitter=emitter,
                buffer=text_buffer,
                emitted_text=emitted_text,
                force=True,
            )
            if packet:
                yield packet

            previous_response_id = current_response_id or previous_response_id

            if stream_error is not None:
                recovered_completion = self._recover_step_completion(
                    messages=input_messages if pending_input_items is None else None,
                    input_items=pending_input_items,
                    instructions=instructions,
                    tools=tools,
                    response_plan=response_plan,
                    previous_response_id=previous_response_id,
                    step_index=step_index,
                )
                if recovered_completion is not None:
                    last_provider_completion = recovered_completion
                    if recovered_completion.response_id:
                        previous_response_id = recovered_completion.response_id
                    if recovered_completion.output_text:
                        if not answering_status_sent:
                            answer_status = emitter.status(
                                "answering",
                                "正在整理回答",
                                "我已经切换到恢复模式，继续把结果整理出来。",
                                phase="answering",
                            )
                            if answer_status:
                                yield answer_status
                            answering_status_sent = True
                        emitted_text, packet = self._append_stream_text(
                            emitter=emitter,
                            buffer=text_buffer,
                            emitted_text=emitted_text,
                            delta_text=recovered_completion.output_text,
                            force_flush=True,
                        )
                        if packet:
                            yield packet
                    current_calls = list(recovered_completion.function_calls or [])
                else:
                    warnings.append(f"stream_error:{type(stream_error).__name__}")
                    warning_packet = emitter.warning(
                        "stream_interrupted",
                        "这次输出中途有些不稳定，我先保留已经生成的部分。",
                        recoverable=True,
                        phase="warning",
                    )
                    if warning_packet:
                        yield warning_packet
                    finish_reason = "degraded_fallback"
                    break

            if not current_calls:
                break

            tool_outputs: List[Dict[str, Any]] = []
            for call in current_calls:
                start_packet = emitter.tool_status(
                    call.name,
                    "started",
                    summary="tool call started",
                    phase="tool",
                )
                if start_packet:
                    yield start_packet
                status_packet = self._status_packet_for_tool(emitter, call.name)
                if status_packet:
                    yield status_packet
                started_at = time.perf_counter()
                result = await asyncio.to_thread(self._execute_tool, call, context)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                done_packet = emitter.tool_status(
                    call.name,
                    "done" if bool(result.get("ok")) else "error",
                    summary=json.dumps(self._tool_result_preview(result), ensure_ascii=False),
                    latency_ms=latency_ms,
                    phase="tool",
                )
                if done_packet:
                    yield done_packet

                evidence_items = self._build_evidence_items(call.name, result)
                for item in evidence_items:
                    evidence_key = json.dumps(item, ensure_ascii=False, sort_keys=True)
                    if evidence_key in emitted_evidence_keys:
                        continue
                    emitted_evidence_keys.add(evidence_key)
                    evidence_packet = emitter.evidence_bundle([item], phase="retrieving")
                    if evidence_packet:
                        yield evidence_packet

                tool_warning_messages = self._collect_tool_warning_messages(result)
                for message in tool_warning_messages:
                    warnings.append(message)
                    warning_packet = emitter.warning(
                        "tool_warning",
                        message,
                        recoverable=True,
                        phase="warning",
                    )
                    if warning_packet:
                        yield warning_packet

                preview = self._build_action_preview(call, result)
                if preview and not action_preview_payload:
                    action_preview_payload = preview
                    finish_reason = "awaiting_confirmation"
                    preview_packet = emitter.action_preview(preview, phase="awaiting_confirmation")
                    if preview_packet:
                        yield preview_packet

                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

            pending_input_items = tool_outputs

        emitted_text, packet = self._flush_text_buffer(
            emitter=emitter,
            buffer=text_buffer,
            emitted_text=emitted_text,
            force=True,
        )
        if packet:
            yield packet

        final_text = self._cleanup_answer_text(emitted_text)
        if not final_text and action_preview_payload:
            final_text = "我已经把这一步的执行草案整理好了。你确认之后，我再继续执行真正的数据库操作。"
        if not final_text and finish_reason == "degraded_fallback":
            final_text = "这次输出中途不太稳定，我先保留已经拿到的结果。你可以直接继续追问，或者把问题再收紧一点。"
        if not final_text and last_provider_completion and last_provider_completion.output_text:
            final_text = self._cleanup_answer_text(last_provider_completion.output_text)
        if not final_text:
            final_text = "这次还没有拿到足够稳定的最终答案。你可以直接继续追问，我会接着帮你整理。"

        if client_supports_replace and final_text != emitted_text.strip():
            replace_packet = emitter.replace(final_text, reason="final_cleanup", phase="finalizing")
            if replace_packet:
                yield replace_packet

        finalizing_packet = emitter.status(
            "finalizing",
            "正在收尾",
            "我把这一轮的结果再对齐一下。",
            phase="finalizing",
        )
        if finalizing_packet:
            yield finalizing_packet

        done_packet = emitter.done(
            final_text=final_text,
            finish_reason=finish_reason,
            requires_followup=bool(action_preview_payload),
            action_preview=action_preview_payload,
            warnings=warnings,
            phase="done",
        )
        if done_packet:
            yield done_packet

    async def _stream_provider_events_async(self, **kwargs: Any) -> AsyncIterator[ResponsesStreamEvent]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        heartbeat_interval_sec = max(1.0, float(self.heartbeat_interval_sec))

        def _worker() -> None:
            try:
                for item in self.provider.stream_events(**kwargs):
                    asyncio.run_coroutine_threadsafe(queue.put(("event", item)), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(("error", exc)), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)

        threading.Thread(target=_worker, daemon=True).start()
        last_activity = time.monotonic()
        while True:
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval_sec)
            except asyncio.TimeoutError:
                idle_ms = int((time.monotonic() - last_activity) * 1000)
                yield ResponsesStreamEvent(
                    event="heartbeat",
                    type="heartbeat",
                    raw={"idle_ms": idle_ms},
                )
                continue
            if kind == "event":
                last_activity = time.monotonic()
                if isinstance(payload, ResponsesStreamEvent):
                    yield payload
                continue
            if kind == "error":
                if isinstance(payload, Exception):
                    raise payload
                raise RuntimeError(str(payload or "assistant_1 stream worker failed"))
            break

    def _recover_step_completion(
        self,
        *,
        messages: Optional[List[Dict[str, Any]]],
        input_items: Optional[List[Dict[str, Any]]],
        instructions: str,
        tools: Optional[List[Dict[str, Any]]],
        response_plan: Any,
        previous_response_id: str,
        step_index: int,
    ) -> Optional[ResponsesCompletionResult]:
        try:
            return self.provider.complete(
                messages=messages,
                input_items=input_items,
                instructions=instructions,
                tools=tools,
                tool_choice="auto",
                max_output_tokens=response_plan.max_output_tokens,
                reasoning_effort=response_plan.reasoning_effort,
                text_verbosity=response_plan.text_verbosity,
                previous_response_id=previous_response_id,
                metadata={
                    "assistant_runtime": "assistant_1",
                    "delivery": "sse_recovery",
                    "phase": f"recovery_step_{step_index}",
                },
            )
        except Exception:
            return None

    def _append_stream_text(
        self,
        *,
        emitter: Assistant1SSEEmitter,
        buffer: Assistant1TextBuffer,
        emitted_text: str,
        delta_text: str,
        force_flush: bool = False,
    ) -> tuple[str, Optional[bytes]]:
        now = time.monotonic()
        normalized = str(delta_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized:
            return emitted_text, None
        buffer.append(normalized, now)
        if not buffer.should_flush(now, force=force_flush):
            return emitted_text, None
        chunk = buffer.pop()
        emitted_text += chunk
        return emitted_text, emitter.delta(chunk, phase="answering")

    def _flush_text_buffer(
        self,
        *,
        emitter: Assistant1SSEEmitter,
        buffer: Assistant1TextBuffer,
        emitted_text: str,
        force: bool,
    ) -> tuple[str, Optional[bytes]]:
        if not buffer.should_flush(time.monotonic(), force=force):
            return emitted_text, None
        chunk = buffer.pop()
        if not chunk:
            return emitted_text, None
        emitted_text += chunk
        return emitted_text, emitter.delta(chunk, phase="answering")

    @staticmethod
    def _status_packet_for_tool(emitter: Assistant1SSEEmitter, tool_name: str) -> Optional[bytes]:
        normalized = str(tool_name or "").strip()
        mapping: Dict[str, tuple[str, str, str]] = {
            "search_knowledge_base": ("retrieving", "正在检索当前文档", "我先把当前文档里最相关的内容找出来。"),
            "search_knowledge_base_grouped": ("retrieving", "正在按时间和版本整理内容", "我会先把可能混在一起的年份和版本拆开。"),
            "ingest_document": ("preparing", "正在准备文档知识底座", "我先把文档整理成后续可检索的结构。"),
            "web_search_tavily": ("web_searching", "正在补充外部资料", "我会补一些当前文档之外的必要背景。"),
            "inspect_database_schema": ("inspecting_schema", "正在检查数据库结构", "我先确认现有表结构，再继续往下做。"),
            "design_schema_draft": ("drafting_schema", "正在整理表结构草案", "我先把建表思路和字段设计整理出来。"),
            "draft_sql_from_nl": ("drafting_sql", "正在生成 SQL 草案", "我会先把自然语言需求收成一条可读可审的 SQL。"),
            "execute_sql_with_audit": ("executing_sql", "正在校验并执行 SQL", "我会先走审计和安全校验，再决定是否真正执行。"),
        }
        item = mapping.get(normalized)
        if not item:
            return None
        code, label, detail = item
        return emitter.status(code, label, detail, phase=code)

    @staticmethod
    def _build_evidence_items(tool_name: str, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        if str(tool_name or "").strip() not in {"search_knowledge_base", "search_knowledge_base_grouped"}:
            return []
        if not bool(result.get("ok")):
            return []
        items: List[Dict[str, Any]] = []
        for match in result.get("matches", []) if isinstance(result.get("matches"), list) else []:
            if not isinstance(match, dict):
                continue
            item = {
                "kind": "retrieval_match",
                "title": str(match.get("title") or ""),
                "snippet": str(match.get("content_preview") or ""),
                "score": round(max(0.0, 1.0 - float(match.get("distance") or 0.0)), 6),
                "unit_id": str(match.get("unit_id") or ""),
                "unit_type": str(match.get("unit_type") or ""),
                "page_start": match.get("page_start"),
                "page_end": match.get("page_end"),
            }
            if item["title"] or item["snippet"] or item["unit_id"]:
                items.append(item)
            if len(items) >= 5:
                break
        return items

    @staticmethod
    def _collect_tool_warning_messages(result: Dict[str, Any]) -> List[str]:
        messages: List[str] = []
        if not isinstance(result, dict):
            return messages
        for item in result.get("warnings", []) if isinstance(result.get("warnings"), list) else []:
            text = str(item or "").strip()
            if text:
                messages.append(text)
        if not bool(result.get("ok")) and result.get("error"):
            messages.append(str(result.get("error") or "").strip())
        return messages[:3]

    @staticmethod
    def _build_action_preview(call: ResponsesFunctionCall, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        call_name = str(call.name or "").strip()
        if call_name == "draft_sql_from_nl" and bool(result.get("ok")) and bool(result.get("requires_confirmation")):
            sql_preview = str(result.get("sql") or "").strip()
            return {
                "action_kind": "sql_write_draft",
                "title": "准备执行数据库写入",
                "summary": str(result.get("explanation") or "这条 SQL 草案涉及写操作或 DDL，执行前需要你确认。").strip(),
                "requires_confirmation": True,
                "confirmation_token": call.call_id or call.id,
                "risk_level": "high",
                "sql_preview": sql_preview,
                "notes": "确认后我再继续执行真正的数据库操作。",
            }
        if call_name == "execute_sql_with_audit":
            error_text = str(result.get("error") or "").strip().lower()
            statement_type = str(result.get("statement_type") or "").strip().lower()
            if "require confirmed=true" in error_text or (statement_type and statement_type not in {"select", "with", "show", "explain"}):
                raw_sql = str(call.arguments.get("sql") or "").strip()
                return {
                    "action_kind": "sql_execution_confirmation",
                    "title": "这一步需要确认后才能执行",
                    "summary": "这条 SQL 会修改数据库内容，所以我先停在预览状态。",
                    "requires_confirmation": True,
                    "confirmation_token": call.call_id or call.id,
                    "risk_level": "high",
                    "sql_preview": raw_sql,
                    "notes": "确认后我再进入真正执行。",
                }
        return None
