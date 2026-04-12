from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.repositories import AssistantSessionRepository, build_module2_repository_bundle


def test_module2_repository_bundle_exposes_assistant_session_repository() -> None:
    storage = object()
    bundle = build_module2_repository_bundle(legacy_storage=storage)
    assert bundle.assistant_session_repository.legacy_storage is storage


def test_assistant_session_repository_forwards_persistence_calls() -> None:
    class _FakeStorage:
        def __init__(self) -> None:
            self.calls: List[Dict[str, Any]] = []

        async def upsert_assistant_session(self, **kwargs: Any) -> None:
            self.calls.append({"method": "upsert_assistant_session", "kwargs": dict(kwargs)})

        async def save_assistant_message(self, **kwargs: Any) -> None:
            self.calls.append({"method": "save_assistant_message", "kwargs": dict(kwargs)})

        async def save_tool_invocation(self, **kwargs: Any) -> None:
            self.calls.append({"method": "save_tool_invocation", "kwargs": dict(kwargs)})

    fake_storage = _FakeStorage()
    repository = AssistantSessionRepository(legacy_storage=fake_storage)

    asyncio.run(
        repository.upsert_assistant_session(
            session_id="sess_1",
            file_hash="hash_1",
            file_name="demo.pdf",
            summary_text="",
            metadata={"from": "test"},
        )
    )
    asyncio.run(
        repository.save_assistant_message(
            session_id="sess_1",
            message_id="msg_1",
            role="user",
            message_type="user_message",
            content="hello",
            payload={"x": 1},
        )
    )
    asyncio.run(
        repository.save_tool_invocation(
            session_id="sess_1",
            message_id="msg_1",
            tool_name="search_knowledge_base",
            status="done",
            input_summary={"query": "hello"},
            output_summary={"ok": True},
            latency_ms=12,
        )
    )

    assert [item["method"] for item in fake_storage.calls] == [
        "upsert_assistant_session",
        "save_assistant_message",
        "save_tool_invocation",
    ]
    assert fake_storage.calls[1]["kwargs"]["role"] == "user"
    assert fake_storage.calls[2]["kwargs"]["tool_name"] == "search_knowledge_base"


def test_module2_foundation_builder_wires_assistant_repository_in_service_bundle() -> None:
    source_path = Path(__file__).resolve().parents[1] / "app" / "services" / "extraction" / "foundation_builder.py"
    source = source_path.read_text(encoding="utf-8")
    assert "assistant_repository=repository_bundle.assistant_session_repository" in source
