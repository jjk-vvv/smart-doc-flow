from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.persistence import Assistant1PersistenceAdapter
from app.assistant_1.response_planner import Assistant1ResponsePlan
from app.assistant_1.responses_provider import ResponsesStreamEvent
from app.assistant_1.stream_runtime import Assistant1StreamingRuntime


class _FakeStorage:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def upsert_assistant_session(self, **kwargs: Any) -> None:
        self.calls.append({"method": "upsert_assistant_session", "kwargs": dict(kwargs)})

    async def save_assistant_message(self, **kwargs: Any) -> None:
        self.calls.append({"method": "save_assistant_message", "kwargs": dict(kwargs)})

    async def save_tool_invocation(self, **kwargs: Any) -> None:
        self.calls.append({"method": "save_tool_invocation", "kwargs": dict(kwargs)})


class _StubProvider:
    @property
    def configured(self) -> bool:
        return True

    def stream_events(self, **kwargs: Any):
        del kwargs
        yield ResponsesStreamEvent(
            event="response.created",
            type="response.created",
            response_id="resp-1",
            response_status="in_progress",
            raw={"id": "resp-1"},
        )
        yield ResponsesStreamEvent(
            event="response.output_text.delta",
            type="response.output_text.delta",
            response_id="resp-1",
            response_status="in_progress",
            output_text_delta="stream-persistence-ok",
            raw={"id": "resp-1"},
        )
        yield ResponsesStreamEvent(
            event="response.done",
            type="response.done",
            response_id="resp-1",
            response_status="completed",
            raw={"id": "resp-1"},
        )


class _PersistenceRuntime(Assistant1StreamingRuntime):
    def __init__(self, persistence: Assistant1PersistenceAdapter) -> None:
        self.provider = _StubProvider()
        self.heartbeat_interval_sec = 4.0
        self.persistence = persistence
        self.logger = logging.getLogger(__name__)

    def _plan_response(self, *, user_message: str, default_file_hash: str) -> Assistant1ResponsePlan:
        del user_message, default_file_hash
        return Assistant1ResponsePlan(
            use_tools=False,
            text_verbosity="low",
            max_output_tokens=220,
            reasoning_effort="minimal",
            tool_names=(),
            intent="general_chat",
            tool_choice="none",
            requires_tool_call=False,
        )

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


def test_stream_runtime_persists_session_and_messages() -> None:
    fake_storage = _FakeStorage()
    runtime = _PersistenceRuntime(Assistant1PersistenceAdapter(storage=fake_storage))

    async def _collect() -> str:
        chunks: List[str] = []
        async for chunk in runtime.stream_chat(
            user_message="hello persistence",
            session_id="sess_test",
            file_hash="",
            history=[],
            top_k=5,
            max_steps=2,
            debug=False,
            resume_run_id="run_resume_x",
            after_seq=17,
            extra_context={
                "current_document": {
                    "file_hash": "fh_1",
                    "file_name": "doc_a.pdf",
                    "current_locked_object": {
                        "lock_type": "table_row",
                        "table_id": "xlsx_t1",
                        "row_index": 17,
                        "source_row_index": 17,
                        "page": 1,
                    },
                }
            },
            client_supports_replace=True,
        ):
            chunks.append(chunk.decode("utf-8"))
        return "".join(chunks)

    payload = asyncio.run(_collect())

    assert "event: assistant.done" in payload

    methods = [item["method"] for item in fake_storage.calls]
    assert "upsert_assistant_session" in methods
    assert methods.count("save_assistant_message") >= 2

    session_call = next(item for item in fake_storage.calls if item["method"] == "upsert_assistant_session")
    assert session_call["kwargs"]["session_id"] == "sess_test"
    assert session_call["kwargs"]["file_hash"] == "fh_1"
    assert session_call["kwargs"]["file_name"] == "doc_a.pdf"
    assert session_call["kwargs"]["current_object_lock"]["lock_type"] == "table_row"
    assert session_call["kwargs"]["current_object_lock"]["table_id"] == "xlsx_t1"
    assert session_call["kwargs"]["current_object_lock"]["row_index"] == 17
    assert session_call["kwargs"]["current_object_lock"]["source_row_index"] == 17
    assert session_call["kwargs"]["metadata"]["resume_after_seq"] == 17

    message_roles = [item["kwargs"].get("role") for item in fake_storage.calls if item["method"] == "save_assistant_message"]
    assert "user" in message_roles
    assert "assistant" in message_roles

    assistant_message_calls = [
        item["kwargs"]
        for item in fake_storage.calls
        if item["method"] == "save_assistant_message" and item["kwargs"].get("role") == "assistant"
    ]
    assert any(bool(item.get("payload", {}).get("partial")) for item in assistant_message_calls)
    assert assistant_message_calls[-1]["payload"]["finish_reason"] == "completed"
    assert assistant_message_calls[-1]["payload"]["current_object_lock"]["lock_type"] == "table_row"

    assert '"current_object_lock"' in payload


def test_stream_runtime_humanizes_internal_warning_codes() -> None:
    assert (
        Assistant1StreamingRuntime._to_user_visible_warning_message("auto_ingest_completed_but_no_units_built")
        == "系统已自动补做文档索引，但暂时还没有形成稳定的可检索片段，我先基于当前可见内容继续回答。"
    )
    assert (
        Assistant1StreamingRuntime._to_user_visible_warning_message(
            "initial_unit_type_filter_returned_no_matches; broadened_to_all_unit_types"
        )
        == "第一次检索没有命中最相关内容，我已自动扩大检索范围继续查找。"
    )
