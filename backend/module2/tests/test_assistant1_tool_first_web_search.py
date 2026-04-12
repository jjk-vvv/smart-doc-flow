from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.agent_runtime import Assistant1AgentRuntime
from app.assistant_1.response_planner import Assistant1ResponsePlan, Assistant1ResponsePlanner
from app.assistant_1.responses_provider import ResponsesCompletionResult, ResponsesFunctionCall, ResponsesStreamEvent
from app.assistant_1.stream_runtime import Assistant1StreamingRuntime


class StubSyncProvider:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    @property
    def configured(self) -> bool:
        return True

    def complete(self, **kwargs: Any) -> ResponsesCompletionResult:
        self.calls.append(dict(kwargs))
        return ResponsesCompletionResult(
            response_id="resp-sync-1",
            status="completed",
            output_text="这是基于真实联网结果整理后的回答。",
            raw={"output": [{"type": "message"}]},
        )


class StubStreamProvider(StubSyncProvider):
    def __init__(self) -> None:
        super().__init__()
        self.stream_calls: List[Dict[str, Any]] = []

    def stream_events(self, **kwargs: Any):
        self.stream_calls.append(dict(kwargs))
        yield ResponsesStreamEvent(
            event="response.created",
            type="response.created",
            response_id="resp-stream-1",
            response_status="in_progress",
            raw={"id": "resp-stream-1"},
        )
        yield ResponsesStreamEvent(
            event="response.output_text.delta",
            type="response.output_text.delta",
            response_id="resp-stream-1",
            response_status="in_progress",
            output_text_delta="流式联网回答片段。",
            raw={"id": "resp-stream-1"},
        )
        yield ResponsesStreamEvent(
            event="response.done",
            type="response.done",
            response_id="resp-stream-1",
            response_status="completed",
            raw={"id": "resp-stream-1"},
        )


def _tool_first_plan() -> Assistant1ResponsePlan:
    return Assistant1ResponsePlan(
        use_tools=True,
        text_verbosity="medium",
        max_output_tokens=900,
        reasoning_effort="minimal",
        tool_names=("web_search_tavily",),
        intent="web_search",
        tool_choice={"type": "function", "name": "web_search_tavily"},
        requires_tool_call=True,
        primary_tool_name="web_search_tavily",
        tool_execution_mode="tool_first",
    )


def _manual_web_search_step() -> Dict[str, Any]:
    call = ResponsesFunctionCall(
        id="manual_web_search_tavily",
        call_id="manual_web_search_tavily",
        name="web_search_tavily",
        arguments={"query": "Please search the web for the latest official API docs entry.", "max_results": 5},
        raw_arguments='{"query":"Please search the web for the latest official API docs entry.","max_results":5}',
    )
    result = {
        "ok": True,
        "answer": "https://platform.openai.com/docs",
        "preferred_title": "API Documentation",
        "preferred_url": "https://platform.openai.com/docs",
        "results": [
            {
                "title": "API Documentation",
                "url": "https://platform.openai.com/docs",
                "content": "Official OpenAI API documentation.",
                "score": 0.99,
            }
        ],
    }
    return {
        "call": call,
        "result": result,
        "tool_step": {
            "step": 1,
            "response_id": "",
            "executed_tools": [
                {
                    "tool_name": "web_search_tavily",
                    "arguments": call.arguments,
                    "result_preview": {
                        "ok": True,
                        "preferred_title": "API Documentation",
                        "preferred_url": "https://platform.openai.com/docs",
                    },
                }
            ],
        },
    }


class ToolFirstChatRuntime(Assistant1AgentRuntime):
    def __init__(self) -> None:
        self.provider = StubSyncProvider()

    def _plan_response(self, *, user_message: str, default_file_hash: str) -> Assistant1ResponsePlan:
        del user_message, default_file_hash
        return _tool_first_plan()

    def _build_instructions(
        self,
        *,
        user_message: str,
        default_file_hash: str,
        response_plan: Assistant1ResponsePlan,
        extra_context: Dict[str, Any] | None = None,
    ) -> str:
        del user_message, default_file_hash, response_plan, extra_context
        return "test instructions"

    def _build_frontend_snapshot_answer(self, *, user_message: str, extra_context: Dict[str, Any] | None) -> str:
        del user_message, extra_context
        return ""

    def _should_short_circuit_with_frontend_snapshot(self, *, user_message: str, snapshot_answer: str) -> bool:
        del user_message, snapshot_answer
        return False

    def _run_primary_tool_manually(
        self,
        *,
        question: str,
        response_plan: Assistant1ResponsePlan,
        context,
        response_id: str,
    ) -> Dict[str, Any] | None:
        del question, response_plan, context, response_id
        return _manual_web_search_step()

    def _ground_answer_with_frontend_context(
        self,
        *,
        user_message: str,
        answer: str,
        extra_context: Dict[str, Any] | None,
        allow_snapshot_override: bool = True,
    ) -> str:
        del user_message, extra_context, allow_snapshot_override
        return answer


class ToolFirstStreamRuntime(Assistant1StreamingRuntime):
    def __init__(self) -> None:
        self.provider = StubStreamProvider()
        self.heartbeat_interval_sec = 4.0

    def _plan_response(self, *, user_message: str, default_file_hash: str) -> Assistant1ResponsePlan:
        del user_message, default_file_hash
        return _tool_first_plan()

    def _build_instructions(
        self,
        *,
        user_message: str,
        default_file_hash: str,
        response_plan: Assistant1ResponsePlan,
        extra_context: Dict[str, Any] | None = None,
    ) -> str:
        del user_message, default_file_hash, response_plan, extra_context
        return "test instructions"

    def _build_frontend_snapshot_answer(self, *, user_message: str, extra_context: Dict[str, Any] | None) -> str:
        del user_message, extra_context
        return ""

    def _should_short_circuit_with_frontend_snapshot(self, *, user_message: str, snapshot_answer: str) -> bool:
        del user_message, snapshot_answer
        return False

    def _run_primary_tool_manually(
        self,
        *,
        question: str,
        response_plan: Assistant1ResponsePlan,
        context,
        response_id: str,
    ) -> Dict[str, Any] | None:
        del question, response_plan, context, response_id
        return _manual_web_search_step()

    def _ground_answer_with_frontend_context(
        self,
        *,
        user_message: str,
        answer: str,
        extra_context: Dict[str, Any] | None,
        allow_snapshot_override: bool = True,
    ) -> str:
        del user_message, extra_context, allow_snapshot_override
        return answer


def test_web_search_plan_prefers_tool_first_execution() -> None:
    planner = Assistant1ResponsePlanner()

    plan = planner.plan(
        user_message="请联网搜索 OpenAI 官方 API 文档入口，并直接给我链接。",
        default_file_hash="",
    )

    assert plan.intent == "web_search"
    assert plan.primary_tool_name == "web_search_tavily"
    assert plan.requires_tool_call is True
    assert plan.tool_execution_mode == "tool_first"


def test_chat_runtime_executes_web_search_before_synthesis() -> None:
    runtime = ToolFirstChatRuntime()

    payload = runtime.chat("请联网搜索 OpenAI 官方 API 文档入口，并直接给我链接。")

    assert payload["answer"] == "这是基于真实联网结果整理后的回答。"
    assert payload["tool_steps"][0]["executed_tools"][0]["tool_name"] == "web_search_tavily"
    assert len(runtime.provider.calls) == 1
    assert runtime.provider.calls[0]["tools"] is None
    assert runtime.provider.calls[0]["tool_choice"] == "none"
    grounded_prompt = runtime.provider.calls[0]["messages"][0]["content"]
    assert "原始问题" in grounded_prompt


def test_stream_runtime_emits_tool_status_before_streaming_answer() -> None:
    runtime = ToolFirstStreamRuntime()

    async def collect() -> str:
        chunks: List[str] = []
        async for chunk in runtime.stream_chat(
            user_message="请联网搜索 OpenAI 官方 API 文档入口，并直接给我链接。",
            history=[],
            extra_context=None,
            debug=True,
            client_supports_replace=True,
        ):
            chunks.append(chunk.decode("utf-8"))
        return "".join(chunks)

    payload = asyncio.run(collect())

    assert "event: tool.status" in payload
    assert "web_search_tavily" in payload
    assert "event: assistant.delta" in payload
    assert "流式联网回答片段" in payload
    assert len(runtime.provider.stream_calls) == 1
    assert runtime.provider.stream_calls[0]["tools"] is None
    assert runtime.provider.stream_calls[0]["tool_choice"] == "none"
