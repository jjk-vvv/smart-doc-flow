from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from .agent_runtime import Assistant1AgentRuntime, Assistant1ToolContext
from .persistence import Assistant1PersistenceAdapter
from .responses_provider import ResponsesCompletionResult, ResponsesFunctionCall, ResponsesStreamEvent
from .stream_feedback import emit_status, emit_tool_status
from .streaming import Assistant1SSEEmitter, Assistant1TextBuffer


class Assistant1StreamingRuntime(Assistant1AgentRuntime):
    def __init__(
        self,
        *,
        persistence: Assistant1PersistenceAdapter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__()
        self.heartbeat_interval_sec = 4.0
        self.logger = logger or logging.getLogger(__name__)
        self.persistence = persistence or Assistant1PersistenceAdapter(logger=self.logger)

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
        resume_run_id: str = "",
        after_seq: int = 0,
        extra_context: Optional[Dict[str, Any]] = None,
        client_supports_replace: bool = True,
    ) -> AsyncIterator[bytes]:
        resume_run_value = str(resume_run_id or "").strip()
        resume_after_seq = max(0, int(after_seq or 0))
        emitter = Assistant1SSEEmitter(
            session_id=session_id,
            run_id=resume_run_value,
            initial_seq=resume_after_seq,
            debug=debug,
        )
        effective_session_id = str(emitter.session_id or "").strip()
        assistant_message_id = str(emitter.assistant_message_id or "").strip()
        resolved_file_hash = self._resolve_bound_file_hash(
            default_file_hash=file_hash,
            extra_context=extra_context,
        )
        frontend_file_name = self._resolve_frontend_file_name(extra_context)
        current_object_lock = self._resolve_frontend_current_object_lock(extra_context)
        authenticated_tenant_id = self._resolve_authenticated_tenant_id(extra_context)
        session_metadata = {
            "stream_run_id": str(emitter.run_id or "").strip(),
            "stream_turn_id": str(emitter.turn_id or "").strip(),
            "resume_run_id": resume_run_value,
            "resume_after_seq": resume_after_seq,
            "delivery": "sse",
        }
        if authenticated_tenant_id:
            session_metadata["tenant_id"] = authenticated_tenant_id
        background_persistence_tasks: List[asyncio.Task[Any]] = []
        background_persistence_tasks.append(
            asyncio.create_task(
                self._persist_assistant_session(
                    session_id=effective_session_id,
                    file_hash=resolved_file_hash,
                    file_name=frontend_file_name,
                    current_object_lock=current_object_lock,
                    metadata=session_metadata,
                    tenant_id=authenticated_tenant_id,
                )
            )
        )
        for packet in (emitter.stream_open(), emitter.assistant_start()):
            if packet:
                yield packet

        question = str(user_message or "").strip()
        user_message_id = ""
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
                current_object_lock=current_object_lock,
            )
            if done_packet:
                yield done_packet
            await self._persist_assistant_message(
                session_id=effective_session_id,
                message_id=assistant_message_id,
                role="assistant",
                message_type="assistant_error",
                content="",
                payload={
                    "finish_reason": "error_recovered",
                    "error_code": "empty_message",
                    "run_id": str(emitter.run_id or "").strip(),
                },
                tenant_id=authenticated_tenant_id,
            )
            await self._drain_background_persistence_tasks(background_persistence_tasks)
            return

        user_message_id = f"user_{int(time.time() * 1000)}_{uuid.uuid4().hex[:10]}"
        background_persistence_tasks.append(
            asyncio.create_task(
                self._persist_assistant_message(
                    session_id=effective_session_id,
                    message_id=user_message_id,
                    role="user",
                    message_type="user_message",
                    content=question,
                    payload={
                        "file_hash": resolved_file_hash,
                        "run_id": str(emitter.run_id or "").strip(),
                        "turn_id": str(emitter.turn_id or "").strip(),
                        "resume_run_id": resume_run_value,
                        "resume_after_seq": resume_after_seq,
                    },
                    tenant_id=authenticated_tenant_id,
                )
            )
        )

        preparing_packet = emit_status(emitter, "preparing")
        if preparing_packet:
            yield preparing_packet
        planning_packet = emit_status(emitter, "planning")
        if planning_packet:
            yield planning_packet

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
            reason="stream_chat_start",
        )
        direct_snapshot_answer = self._build_frontend_snapshot_answer(
            user_message=question,
            extra_context=extra_context,
        )
        try:
            should_short_circuit = self._should_short_circuit_with_frontend_snapshot(
                user_message=question,
                snapshot_answer=direct_snapshot_answer,
                extra_context=extra_context,
            )
        except TypeError:
            # Backward compatibility for test/runtime overrides that still expose
            # the older two-argument signature.
            should_short_circuit = self._should_short_circuit_with_frontend_snapshot(
                user_message=question,
                snapshot_answer=direct_snapshot_answer,
            )
        if not response_plan.must_clarify and should_short_circuit:
            self._maybe_schedule_document_warmup(
                file_hash=context.default_file_hash,
                intent=response_plan.intent,
                reason="stream_frontend_snapshot_short_circuit",
            )
            answer_status = emit_status(emitter, "answering")
            if answer_status:
                yield answer_status
            direct_packet = emitter.delta(direct_snapshot_answer, phase="answering")
            if direct_packet:
                yield direct_packet
            finalizing_packet = emit_status(emitter, "finalizing")
            if finalizing_packet:
                yield finalizing_packet
            done_packet = emitter.done(
                final_text=direct_snapshot_answer,
                finish_reason="frontend_snapshot_short_circuit",
                requires_followup=False,
                current_object_lock=current_object_lock,
                phase="done",
            )
            if done_packet:
                yield done_packet
            await self._persist_assistant_message(
                session_id=effective_session_id,
                message_id=assistant_message_id,
                role="assistant",
                message_type="assistant_text",
                content=direct_snapshot_answer,
                payload={
                    "finish_reason": "frontend_snapshot_short_circuit",
                    "user_message_id": user_message_id,
                    "run_id": str(emitter.run_id or "").strip(),
                },
                tenant_id=authenticated_tenant_id,
            )
            await self._drain_background_persistence_tasks(background_persistence_tasks)
            return
        if response_plan.must_clarify:
            self._maybe_schedule_document_warmup(
                file_hash=context.default_file_hash,
                intent=response_plan.intent,
                reason="stream_clarification_turn",
            )
            clarification_payload = self._clarification_payload(
                question=question,
                response_plan=response_plan,
                context=context,
                extra_context=extra_context,
            )
            answer_status = emit_status(emitter, "answering")
            if answer_status:
                yield answer_status
            direct_packet = emitter.delta(str(clarification_payload.get("answer") or ""), phase="answering")
            if direct_packet:
                yield direct_packet
            finalizing_packet = emit_status(emitter, "finalizing")
            if finalizing_packet:
                yield finalizing_packet
            done_packet = emitter.done(
                final_text=str(clarification_payload.get("answer") or ""),
                finish_reason="clarification_required",
                requires_followup=True,
                current_object_lock=current_object_lock,
                phase="done",
            )
            if done_packet:
                yield done_packet
            await self._persist_assistant_message(
                session_id=effective_session_id,
                message_id=assistant_message_id,
                role="assistant",
                message_type="assistant_text",
                content=str(clarification_payload.get("answer") or ""),
                payload={
                    "finish_reason": "clarification_required",
                    "requires_followup": True,
                    "user_message_id": user_message_id,
                    "run_id": str(emitter.run_id or "").strip(),
                },
                tenant_id=authenticated_tenant_id,
            )
            await self._drain_background_persistence_tasks(background_persistence_tasks)
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
                current_object_lock=current_object_lock,
            )
            if done_packet:
                yield done_packet
            await self._persist_assistant_message(
                session_id=effective_session_id,
                message_id=assistant_message_id,
                role="assistant",
                message_type="assistant_error",
                content="",
                payload={
                    "finish_reason": "error_recovered",
                    "error_code": "provider_not_configured",
                    "user_message_id": user_message_id,
                    "run_id": str(emitter.run_id or "").strip(),
                },
                tenant_id=authenticated_tenant_id,
            )
            await self._drain_background_persistence_tasks(background_persistence_tasks)
            return
        instructions = self._build_instructions(
            user_message=question,
            default_file_hash=context.default_file_hash,
            response_plan=response_plan,
            extra_context=extra_context,
        )
        input_messages = list(history or []) + [{"role": "user", "content": question}]
        tools = self._tool_definitions(response_plan.tool_names) if response_plan.use_tools else None
        initial_tool_choice: str | Dict[str, Any] = response_plan.tool_choice
        requires_tool_call_in_loop = response_plan.requires_tool_call

        text_buffer = Assistant1TextBuffer(
            flush_chars=52 if response_plan.text_verbosity == "high" else 36,
            flush_timeout_ms=140 if response_plan.text_verbosity == "high" else 110,
        )
        emitted_text = ""
        last_partial_persist_content = ""
        last_partial_persist_at = 0.0
        current_response_id = ""
        warnings: List[str] = []
        emitted_evidence_keys: set[str] = set()
        action_preview_payload: Optional[Dict[str, Any]] = None
        finish_reason = "completed"
        answering_status_sent = False

        async def maybe_persist_partial_stream(*, force: bool = False, response_id: str = "") -> None:
            nonlocal last_partial_persist_content, last_partial_persist_at
            last_partial_persist_content, last_partial_persist_at = await self._maybe_persist_partial_assistant_message(
                session_id=effective_session_id,
                message_id=assistant_message_id,
                content=emitted_text,
                user_message_id=user_message_id,
                run_id=str(emitter.run_id or "").strip(),
                response_id=response_id,
                last_persisted_content=last_partial_persist_content,
                last_persisted_at=last_partial_persist_at,
                tenant_id=authenticated_tenant_id,
                force=force,
            )

        previous_response_id = ""
        pending_input_items: Optional[List[Dict[str, Any]]] = None
        last_provider_completion: Optional[ResponsesCompletionResult] = None
        recovered_chat_payload: Optional[Dict[str, Any]] = None
        suppressed_initial_text = ""

        if self._uses_tool_first_execution(response_plan):
            started_at = time.perf_counter()
            manual_step = await asyncio.to_thread(
                self._run_primary_tool_manually,
                question=question,
                response_plan=response_plan,
                context=context,
                response_id="",
            )
            manual_latency_ms = int((time.perf_counter() - started_at) * 1000)
            if not manual_step:
                warning_packet = emitter.warning(
                    "tool_first_unavailable",
                    "这次原本应该先补外部资料，但预取工具没有成功启动，我先退回到常规回答路径继续处理。",
                    recoverable=True,
                    phase="warning",
                )
                if warning_packet:
                    yield warning_packet
            else:
                manual_call = manual_step.get("call")
                manual_result = manual_step.get("result")
                if isinstance(manual_call, ResponsesFunctionCall) and isinstance(manual_result, dict):
                    start_packet = emitter.tool_status(
                        manual_call.name,
                        "started",
                        summary="tool call started",
                        phase="tool",
                    )
                    if start_packet:
                        yield start_packet
                    status_packet = self._status_packet_for_tool(emitter, manual_call.name)
                    if status_packet:
                        yield status_packet
                    done_packet = emitter.tool_status(
                        manual_call.name,
                        "done" if bool(manual_result.get("ok")) else "error",
                        summary=json.dumps(self._tool_result_preview(manual_result), ensure_ascii=False),
                        latency_ms=manual_latency_ms,
                        phase="tool",
                    )
                    if done_packet:
                        yield done_packet
                    await self._persist_tool_invocation(
                        session_id=effective_session_id,
                        message_id=assistant_message_id,
                        call=manual_call,
                        result=manual_result,
                        latency_ms=manual_latency_ms,
                        tenant_id=authenticated_tenant_id,
                    )

                    evidence_items = self._build_evidence_items(manual_call.name, manual_result)
                    for item in evidence_items:
                        evidence_key = json.dumps(item, ensure_ascii=False, sort_keys=True)
                        if evidence_key in emitted_evidence_keys:
                            continue
                        emitted_evidence_keys.add(evidence_key)
                        evidence_packet = emitter.evidence_bundle([item], phase="retrieving")
                        if evidence_packet:
                            yield evidence_packet

                    tool_warning_messages = self._collect_tool_warning_messages(manual_result)
                    for message in tool_warning_messages:
                        warnings.append(message)
                        user_visible_warning = self._to_user_visible_warning_message(message)
                        if user_visible_warning:
                            warning_packet = emitter.warning(
                                "tool_warning",
                                user_visible_warning,
                                recoverable=True,
                                phase="warning",
                            )
                            if warning_packet:
                                yield warning_packet

                    preview = self._build_action_preview(manual_call, manual_result)
                    if preview and not action_preview_payload:
                        action_preview_payload = preview
                        finish_reason = "awaiting_confirmation"
                        preview_packet = emitter.action_preview(preview, phase="awaiting_confirmation")
                        if preview_packet:
                            yield preview_packet

                    input_messages = self._grounded_synthesis_messages(
                        question=question,
                        intent=response_plan.intent,
                        grounding_result=manual_result,
                    )
                    tools = None
                    initial_tool_choice = "none"
                    requires_tool_call_in_loop = False

        for step_index in range(max(1, int(max_steps or 1))):
            current_calls: List[ResponsesFunctionCall] = []
            stream_error: Exception | None = None
            current_response_id = ""
            current_tool_choice = initial_tool_choice if step_index == 0 else "auto"
            hold_text_until_grounded = requires_tool_call_in_loop and step_index == 0

            try:
                async for event in self._stream_provider_events_async(
                    messages=input_messages if pending_input_items is None else None,
                    input_items=pending_input_items,
                    instructions=instructions,
                    tools=tools,
                    tool_choice=current_tool_choice,
                    max_output_tokens=response_plan.max_output_tokens,
                    reasoning_effort=response_plan.reasoning_effort,
                    text_verbosity=response_plan.text_verbosity,
                    previous_response_id=previous_response_id,
                    metadata={
                        "assistant_runtime": "assistant_1",
                        "delivery": "sse",
                        "phase": "initial" if step_index == 0 else f"tool_step_{step_index}",
                        "stream_run_id": str(emitter.run_id or "").strip(),
                        "stream_turn_id": str(emitter.turn_id or "").strip(),
                        "session_id": effective_session_id,
                        "resume_after_seq": str(resume_after_seq),
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
                        if hold_text_until_grounded:
                            suppressed_initial_text += event.output_text_delta
                        else:
                            if not answering_status_sent:
                                answer_status = emit_status(emitter, "answering")
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
                                await maybe_persist_partial_stream(response_id=current_response_id or previous_response_id)
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
                await maybe_persist_partial_stream(force=True, response_id=current_response_id or previous_response_id)

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
                        if hold_text_until_grounded:
                            suppressed_initial_text += recovered_completion.output_text
                        else:
                            if not answering_status_sent:
                                answer_status = emit_status(emitter, "answering")
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
                                await maybe_persist_partial_stream(force=True, response_id=current_response_id or previous_response_id)
                    current_calls = list(recovered_completion.function_calls or [])
                else:
                    warnings.append(f"stream_error:{type(stream_error).__name__}")
                    recovered_chat_payload = await asyncio.to_thread(
                        self._recover_full_chat_payload,
                        question=question,
                        file_hash=context.default_file_hash,
                        history=history,
                        max_steps=max_steps,
                        top_k=top_k,
                        extra_context=extra_context,
                    )
                    if recovered_chat_payload:
                        finish_reason = "nonstream_recovered"
                        break
                    warning_packet = emitter.warning(
                        "stream_interrupted",
                        "这次输出流中途断开，我正在尝试整理一版稳定结果。",
                        recoverable=True,
                        phase="warning",
                    )
                    if warning_packet:
                        yield warning_packet
                    finish_reason = "degraded_fallback"
                    break

            if not current_calls:
                if hold_text_until_grounded:
                    recovery_outcome = await asyncio.to_thread(
                        self._recover_required_tool_stream_step,
                        question=question,
                        input_messages=input_messages,
                        instructions=instructions,
                        tools=tools,
                        response_plan=response_plan,
                        context=context,
                        extra_context=extra_context,
                    )
                    if isinstance(recovery_outcome, dict):
                        recovery_payload = recovery_outcome.get("direct_payload")
                        recovery_response = recovery_outcome.get("response")
                        manual_call = recovery_outcome.get("manual_call")
                        manual_result = recovery_outcome.get("manual_result")
                        manual_latency_ms = int(recovery_outcome.get("manual_latency_ms") or 0)

                        if isinstance(manual_call, ResponsesFunctionCall) and isinstance(manual_result, dict):
                            start_packet = emitter.tool_status(
                                manual_call.name,
                                "started",
                                summary="tool call started",
                                phase="tool",
                            )
                            if start_packet:
                                yield start_packet
                            status_packet = self._status_packet_for_tool(emitter, manual_call.name)
                            if status_packet:
                                yield status_packet
                            done_packet = emitter.tool_status(
                                manual_call.name,
                                "done" if bool(manual_result.get("ok")) else "error",
                                summary=json.dumps(self._tool_result_preview(manual_result), ensure_ascii=False),
                                latency_ms=manual_latency_ms,
                                phase="tool",
                            )
                            if done_packet:
                                yield done_packet
                            await self._persist_tool_invocation(
                                session_id=effective_session_id,
                                message_id=assistant_message_id,
                                call=manual_call,
                                result=manual_result,
                                latency_ms=manual_latency_ms,
                                tenant_id=authenticated_tenant_id,
                            )

                            evidence_items = self._build_evidence_items(manual_call.name, manual_result)
                            for item in evidence_items:
                                evidence_key = json.dumps(item, ensure_ascii=False, sort_keys=True)
                                if evidence_key in emitted_evidence_keys:
                                    continue
                                emitted_evidence_keys.add(evidence_key)
                                evidence_packet = emitter.evidence_bundle([item], phase="retrieving")
                                if evidence_packet:
                                    yield evidence_packet

                            tool_warning_messages = self._collect_tool_warning_messages(manual_result)
                            for message in tool_warning_messages:
                                warnings.append(message)
                                user_visible_warning = self._to_user_visible_warning_message(message)
                                if user_visible_warning:
                                    warning_packet = emitter.warning(
                                        "tool_warning",
                                        user_visible_warning,
                                        recoverable=True,
                                        phase="warning",
                                    )
                                    if warning_packet:
                                        yield warning_packet

                            preview = self._build_action_preview(manual_call, manual_result)
                            if preview and not action_preview_payload:
                                action_preview_payload = preview
                                finish_reason = "awaiting_confirmation"
                                preview_packet = emitter.action_preview(preview, phase="awaiting_confirmation")
                                if preview_packet:
                                    yield preview_packet

                        if isinstance(recovery_payload, dict):
                            recovered_chat_payload = recovery_payload
                            finish_reason = "required_tool_recovered"
                            break

                        if isinstance(recovery_response, ResponsesCompletionResult):
                            last_provider_completion = recovery_response
                            if recovery_response.response_id:
                                previous_response_id = recovery_response.response_id
                            if recovery_response.output_text:
                                if hold_text_until_grounded and recovery_response.function_calls:
                                    suppressed_initial_text += recovery_response.output_text
                                else:
                                    if not answering_status_sent:
                                        answer_status = emit_status(emitter, "answering")
                                        if answer_status:
                                            yield answer_status
                                        answering_status_sent = True
                                    emitted_text, packet = self._append_stream_text(
                                        emitter=emitter,
                                        buffer=text_buffer,
                                        emitted_text=emitted_text,
                                        delta_text=recovery_response.output_text,
                                        force_flush=not bool(recovery_response.function_calls),
                                    )
                                    if packet:
                                        yield packet
                                        await maybe_persist_partial_stream(
                                            force=not bool(recovery_response.function_calls),
                                            response_id=recovery_response.response_id or previous_response_id,
                                        )
                            current_calls = list(recovery_response.function_calls or [])
                            if current_calls:
                                if hold_text_until_grounded:
                                    suppressed_initial_text = ""
                            else:
                                finish_reason = "required_tool_recovered"
                                break

                    if not current_calls and recovered_chat_payload is None:
                        recovered_chat_payload = await asyncio.to_thread(
                            self._recover_full_chat_payload,
                            question=question,
                            file_hash=context.default_file_hash,
                            history=history,
                            max_steps=max_steps,
                            top_k=top_k,
                            extra_context=extra_context,
                        )
                    if recovered_chat_payload:
                        finish_reason = "required_tool_recovered"
                        break
                    if suppressed_initial_text.strip():
                        if not answering_status_sent:
                            answer_status = emit_status(emitter, "answering")
                            if answer_status:
                                yield answer_status
                            answering_status_sent = True
                        emitted_text, packet = self._append_stream_text(
                            emitter=emitter,
                            buffer=text_buffer,
                            emitted_text=emitted_text,
                            delta_text=suppressed_initial_text,
                            force_flush=True,
                        )
                        if packet:
                            yield packet
                            await maybe_persist_partial_stream(force=True, response_id=previous_response_id)
                break

            tool_outputs: List[Dict[str, Any]] = []
            if hold_text_until_grounded:
                suppressed_initial_text = ""
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
                await self._persist_tool_invocation(
                    session_id=effective_session_id,
                    message_id=assistant_message_id,
                    call=call,
                    result=result,
                    latency_ms=latency_ms,
                    tenant_id=authenticated_tenant_id,
                )

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
                    user_visible_warning = self._to_user_visible_warning_message(message)
                    if user_visible_warning:
                        warning_packet = emitter.warning(
                            "tool_warning",
                            user_visible_warning,
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
            await maybe_persist_partial_stream(force=True, response_id=previous_response_id)

        final_text = self._cleanup_answer_text(emitted_text)
        if not final_text and isinstance(recovered_chat_payload, dict):
            final_text = self._cleanup_answer_text(recovered_chat_payload.get("answer", ""))
        if not final_text and action_preview_payload:
            final_text = self._cleanup_answer_text(str(action_preview_payload.get("summary") or ""))
        if not final_text and last_provider_completion and last_provider_completion.output_text:
            final_text = self._cleanup_answer_text(last_provider_completion.output_text)
        if self._should_attempt_full_chat_recovery(
            final_text=final_text,
            finish_reason=finish_reason,
            action_preview_payload=action_preview_payload,
        ):
            if recovered_chat_payload is None:
                recovered_chat_payload = await asyncio.to_thread(
                    self._recover_full_chat_payload,
                    question=question,
                    file_hash=context.default_file_hash,
                    history=history,
                    max_steps=max_steps,
                    top_k=top_k,
                    extra_context=extra_context,
                )
            if isinstance(recovered_chat_payload, dict):
                recovered_answer = self._cleanup_answer_text(recovered_chat_payload.get("answer", ""))
                if recovered_answer:
                    final_text = recovered_answer
                    finish_reason = "nonstream_recovered"
        if not final_text and action_preview_payload:
            final_text = "我已经整理出这一步的执行预览，确认之后我再继续执行。"
        if not final_text:
            final_text = "这次没有拿到稳定结果，你可以换个更具体的问法，我继续帮你接着查。"
        final_text = self._finalize_answer_text(
            user_message=question,
            answer=final_text,
            extra_context=extra_context,
            allow_snapshot_override=not response_plan.must_clarify,
            has_action_preview=bool(action_preview_payload),
        )

        user_visible_warnings = self._user_visible_warning_messages(warnings)

        if client_supports_replace and final_text != emitted_text.strip():
            replace_packet = emitter.replace(final_text, reason="final_cleanup", phase="finalizing")
            if replace_packet:
                yield replace_packet

        finalizing_packet = emit_status(emitter, "finalizing")
        if finalizing_packet:
            yield finalizing_packet

        done_packet = emitter.done(
            final_text=final_text,
            finish_reason=finish_reason,
            requires_followup=bool(action_preview_payload),
            action_preview=action_preview_payload,
            current_object_lock=current_object_lock,
            warnings=warnings,
            user_visible_warnings=user_visible_warnings,
            phase="done",
        )
        if done_packet:
            yield done_packet
        await self._persist_assistant_message(
            session_id=effective_session_id,
            message_id=assistant_message_id,
            role="assistant",
            message_type="assistant_text",
            content=final_text,
            payload={
                "finish_reason": finish_reason,
                "requires_followup": bool(action_preview_payload),
                "warnings": list(warnings),
                "user_visible_warnings": list(user_visible_warnings),
                "action_preview": dict(action_preview_payload or {}),
                "current_object_lock": dict(current_object_lock or {}),
                "user_message_id": user_message_id,
                "run_id": str(emitter.run_id or "").strip(),
                "response_id": previous_response_id,
            },
            tenant_id=authenticated_tenant_id,
        )
        await self._persist_assistant_session(
            session_id=effective_session_id,
            file_hash=resolved_file_hash,
            file_name=frontend_file_name,
            current_object_lock=current_object_lock,
            metadata=session_metadata,
            tenant_id=authenticated_tenant_id,
        )
        await self._drain_background_persistence_tasks(background_persistence_tasks)

    async def _persist_assistant_session(
        self,
        *,
        session_id: str,
        file_hash: str = "",
        file_name: str = "",
        current_object_lock: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tenant_id: str = "",
    ) -> None:
        adapter = getattr(self, "persistence", None)
        if not isinstance(adapter, Assistant1PersistenceAdapter):
            return
        metadata_payload = dict(metadata or {})
        resolved_tenant_id = str(tenant_id or "").strip() or str(metadata_payload.get("tenant_id") or "").strip()
        await adapter.upsert_session(
            session_id=session_id,
            file_hash=file_hash,
            file_name=file_name,
            summary_text="",
            current_object_lock=dict(current_object_lock or {}),
            metadata=metadata_payload,
            tenant_id=resolved_tenant_id,
        )

    async def _persist_assistant_message(
        self,
        *,
        session_id: str,
        role: str,
        message_type: str,
        content: str,
        payload: Optional[Dict[str, Any]] = None,
        message_id: str = "",
        tenant_id: str = "",
    ) -> str:
        adapter = getattr(self, "persistence", None)
        if not isinstance(adapter, Assistant1PersistenceAdapter):
            return str(message_id or "").strip()
        payload_data = dict(payload or {})
        resolved_tenant_id = str(tenant_id or "").strip() or str(payload_data.get("tenant_id") or "").strip()
        if resolved_tenant_id and "tenant_id" not in payload_data:
            payload_data["tenant_id"] = resolved_tenant_id
        return await adapter.save_message(
            session_id=session_id,
            role=role,
            message_type=message_type,
            content=content,
            payload=payload_data,
            message_id=message_id,
            tenant_id=resolved_tenant_id,
        )

    async def _maybe_persist_partial_assistant_message(
        self,
        *,
        session_id: str,
        message_id: str,
        content: str,
        user_message_id: str,
        run_id: str,
        response_id: str,
        last_persisted_content: str,
        last_persisted_at: float,
        tenant_id: str = "",
        force: bool = False,
    ) -> tuple[str, float]:
        normalized_session_id = str(session_id or "").strip()
        normalized_message_id = str(message_id or "").strip()
        normalized_content = self._cleanup_answer_text(content)
        if not normalized_session_id or not normalized_message_id or not normalized_content:
            return last_persisted_content, last_persisted_at

        now = time.monotonic()
        grew_by = len(normalized_content) - len(last_persisted_content)
        is_first_partial = not bool(last_persisted_content)
        if not force and normalized_content == last_persisted_content:
            return last_persisted_content, last_persisted_at
        if not force and not is_first_partial and grew_by < 80 and (now - last_persisted_at) < 1.2:
            return last_persisted_content, last_persisted_at

        await self._persist_assistant_message(
            session_id=normalized_session_id,
            message_id=normalized_message_id,
            role="assistant",
            message_type="assistant_text",
            content=normalized_content,
            payload={
                "finish_reason": "streaming_partial",
                "partial": True,
                "user_message_id": str(user_message_id or "").strip(),
                "run_id": str(run_id or "").strip(),
                "response_id": str(response_id or "").strip(),
            },
            tenant_id=tenant_id,
        )
        return normalized_content, now

    async def _persist_tool_invocation(
        self,
        *,
        session_id: str,
        message_id: str,
        call: ResponsesFunctionCall,
        result: Dict[str, Any],
        latency_ms: int,
        tenant_id: str = "",
    ) -> None:
        adapter = getattr(self, "persistence", None)
        if not isinstance(adapter, Assistant1PersistenceAdapter):
            return
        await adapter.save_tool_invocation(
            session_id=session_id,
            message_id=message_id,
            tool_name=str(call.name or "").strip(),
            status="done" if bool(result.get("ok")) else "error",
            input_summary=self._tool_input_summary(call),
            output_summary=self._tool_result_preview(result),
            latency_ms=latency_ms,
            tenant_id=tenant_id,
        )

    async def _drain_background_persistence_tasks(
        self,
        tasks: List[asyncio.Task[Any]] | None,
        *,
        timeout_sec: float = 0.35,
    ) -> None:
        active_tasks = [task for task in list(tasks or []) if isinstance(task, asyncio.Task)]
        if not active_tasks:
            return
        try:
            done, pending = await asyncio.wait(
                active_tasks,
                timeout=max(0.05, float(timeout_sec or 0.0)),
                return_when=asyncio.ALL_COMPLETED,
            )
        except Exception:
            return
        for task in done:
            try:
                task.result()
            except Exception:
                continue
        for task in pending:
            task.cancel()

    @staticmethod
    def _resolve_frontend_file_name(extra_context: Optional[Dict[str, Any]]) -> str:
        normalized = Assistant1AgentRuntime._normalize_frontend_context(extra_context)
        current_document = normalized.get("current_document") if isinstance(normalized.get("current_document"), dict) else {}
        for key in ("file_name", "name", "title"):
            value = str(current_document.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _resolve_authenticated_tenant_id(extra_context: Optional[Dict[str, Any]]) -> str:
        normalized = Assistant1AgentRuntime._normalize_frontend_context(extra_context)
        authenticated_user = (
            normalized.get("authenticated_user")
            if isinstance(normalized.get("authenticated_user"), dict)
            else {}
        )
        for key in ("tenant_id", "tenant", "id"):
            value = str(authenticated_user.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _resolve_frontend_current_object_lock(extra_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        normalized = Assistant1AgentRuntime._normalize_frontend_context(extra_context)
        current_document = normalized.get("current_document") if isinstance(normalized.get("current_document"), dict) else {}
        candidates = [
            current_document.get("current_locked_object"),
            current_document.get("current_object_lock"),
            normalized.get("current_object_lock"),
        ]
        raw_lock = next((item for item in candidates if isinstance(item, dict)), None)
        if not isinstance(raw_lock, dict):
            return {}

        normalized_lock: Dict[str, Any] = {}
        for key in ("lock_type", "lock_quality", "object_id", "label", "ref_id", "table_id"):
            value = str(raw_lock.get(key) or "").strip()
            if value:
                normalized_lock[key] = value

        page_raw = raw_lock.get("page")
        if isinstance(page_raw, (int, float)):
            page = int(page_raw)
            if page > 0:
                normalized_lock["page"] = page

        row_index_raw = raw_lock.get("row_index")
        if isinstance(row_index_raw, (int, float)):
            row_index = int(row_index_raw)
            if row_index > 0:
                normalized_lock["row_index"] = row_index

        source_row_index_raw = raw_lock.get("source_row_index")
        if isinstance(source_row_index_raw, (int, float)):
            source_row_index = int(source_row_index_raw)
            if source_row_index > 0:
                normalized_lock["source_row_index"] = source_row_index

        metadata = raw_lock.get("metadata")
        if isinstance(metadata, dict) and metadata:
            normalized_lock["metadata"] = dict(metadata)

        return normalized_lock

    def _tool_input_summary(self, call: ResponsesFunctionCall) -> Dict[str, Any]:
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        summary_arguments: Dict[str, Any] = {}
        for key, value in list(arguments.items())[:6]:
            key_name = str(key or "").strip()
            if not key_name:
                continue
            if isinstance(value, (int, float, bool)) or value is None:
                summary_arguments[key_name] = value
                continue
            if isinstance(value, str):
                summary_arguments[key_name] = self._trim_text(value, 220)
                continue
            summary_arguments[key_name] = self._trim_text(json.dumps(value, ensure_ascii=False), 220)
        return {
            "call_id": str(call.call_id or "").strip(),
            "name": str(call.name or "").strip(),
            "arguments": summary_arguments,
        }

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
            current_tool_choice = response_plan.tool_choice if step_index == 0 else "auto"
            return self.provider.complete(
                messages=messages,
                input_items=input_items,
                instructions=instructions,
                tools=tools,
                tool_choice=current_tool_choice,
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

    def _recover_required_tool_stream_step(
        self,
        *,
        question: str,
        input_messages: List[Dict[str, Any]],
        instructions: str,
        tools: Optional[List[Dict[str, Any]]],
        response_plan: Any,
        context: Assistant1ToolContext,
        extra_context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if response_plan.must_clarify and response_plan.clarification_reason:
            return {
                "direct_payload": self._clarification_payload(
                    question=question,
                    response_plan=response_plan,
                    context=context,
                    extra_context=extra_context,
                )
            }
        try:
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
                    "delivery": "sse_required_tool_recovery",
                    "phase": "required_tool_retry",
                    "intent": response_plan.intent,
                },
            )
        except Exception:
            return None

        if retry_response.function_calls:
            return {"response": retry_response}

        if self._looks_like_database_intent(response_plan.intent):
            return {
                "direct_payload": self._database_grounded_fallback_payload(
                    question=question,
                    response_plan=response_plan,
                    context=context,
                    extra_context=extra_context,
                    response_id=retry_response.response_id,
                    status=retry_response.status,
                )
            }

        started_at = time.perf_counter()
        manual_step = self._run_primary_tool_manually(
            question=question,
            response_plan=response_plan,
            context=context,
            response_id=retry_response.response_id,
        )
        manual_latency_ms = int((time.perf_counter() - started_at) * 1000)
        if not manual_step:
            return {"response": retry_response}

        synthesized = self._complete_grounded_synthesis(
            question=question,
            instructions=instructions,
            response_plan=response_plan,
            grounding_result=manual_step["result"],
            phase="grounded_synthesis",
        )
        return {
            "response": synthesized,
            "manual_call": manual_step.get("call"),
            "manual_result": manual_step.get("result"),
            "manual_latency_ms": manual_latency_ms,
        }

    def _recover_full_chat_payload(
        self,
        *,
        question: str,
        file_hash: str,
        history: Optional[List[Dict[str, Any]]],
        max_steps: int,
        top_k: int,
        extra_context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        try:
            return super().chat(
                question,
                file_hash=file_hash,
                history=history,
                max_steps=max_steps,
                top_k=top_k,
                extra_context=extra_context,
            )
        except Exception:
            return None

    @staticmethod
    def _looks_like_database_intent(intent: str) -> bool:
        return str(intent or "").strip() in {"schema_design", "sql_request"}

    @staticmethod
    def _should_attempt_full_chat_recovery(
        *,
        final_text: str,
        finish_reason: str,
        action_preview_payload: Optional[Dict[str, Any]],
    ) -> bool:
        if action_preview_payload:
            return False
        if finish_reason == "degraded_fallback":
            return True
        normalized = str(final_text or "").strip()
        if not normalized:
            return True
        weak_markers = (
            "这次还没有拿到足够稳定的最终答案",
            "这次输出中途不太稳定",
            "请把问题用中文完整描述一次",
            "你的问题不够具体",
            "我没有看到你提到的那张",
        )
        return any(marker in normalized for marker in weak_markers)

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
        return emit_tool_status(emitter, str(tool_name or "").strip())

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
    def _to_user_visible_warning_message(message: str) -> str:
        text = str(message or "").strip()
        if not text:
            return ""
        lowered = text.lower()

        mapped_pairs = (
            (
                "auto_ingest_completed_but_no_units_built",
                "系统已自动补做文档索引，但暂时还没有形成稳定的可检索片段，我先基于当前可见内容继续回答。",
            ),
            (
                "initial_unit_type_filter_returned_no_matches; broadened_to_all_unit_types",
                "第一次检索没有命中最相关内容，我已自动扩大检索范围继续查找。",
            ),
            (
                "content_list unavailable; fell back to markdown-only content items",
                "结构化内容清单暂不可用，本次回答主要基于正文内容。",
            ),
            (
                "assistant payload artifact is missing or unreadable",
                "文档的部分结构化解析产物暂不可用，本次回答可能更依赖正文内容。",
            ),
            (
                "assistant payload artifact not found",
                "文档的部分结构化解析产物暂不可用，本次回答可能更依赖正文内容。",
            ),
            (
                "mineru markdown artifact is missing or unreadable",
                "文档正文解析产物暂不可用，本次回答可能不够完整。",
            ),
            (
                "mineru markdown path missing",
                "文档正文解析产物暂不可用，本次回答可能不够完整。",
            ),
            (
                "stream_error:",
                "生成过程里出现了一次非致命波动，我已经尽量整理当前可用结果。",
            ),
            (
                "broadened_retry_failed:",
                "扩大检索范围时遇到了一些问题，我先基于当前已命中的内容继续回答。",
            ),
            (
                "retrieval_stats_unavailable:",
                "本次检索统计信息暂不可用，但不影响继续回答。",
            ),
        )
        for marker, replacement in mapped_pairs:
            if marker in text or marker in lowered:
                return replacement

        if lowered.startswith("assistant_provider_fallback:") or lowered.startswith("assistant_context_fallback:"):
            return ""

        if any("\u4e00" <= char <= "\u9fff" for char in text):
            return text

        if any(token in text for token in ("_", ";")) or ":" in text:
            return "处理中出现了一条非致命提示，我已继续完成当前回答。"

        return text

    @classmethod
    def _user_visible_warning_messages(cls, warnings: List[str]) -> List[str]:
        visible: List[str] = []
        seen: set[str] = set()
        for item in warnings:
            text = cls._to_user_visible_warning_message(item)
            if not text or text in seen:
                continue
            seen.add(text)
            visible.append(text)
        return visible[:3]

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
