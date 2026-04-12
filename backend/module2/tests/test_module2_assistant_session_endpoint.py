from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.api.v1.endpoints.extraction_assistant import build_router


class _FakePersistence:
    async def fetch_session(self, session_id: str) -> dict[str, Any] | None:
        if session_id != "sess_1":
            return None
        return {
            "session_id": "sess_1",
            "summary_text": "当前文档摘要",
            "current_object_lock_json": {"lock_type": "field", "label": "统计年份"},
            "file_hash": "fh_1",
            "file_name": "sample.pdf",
            "metadata_json": {"stream_run_id": "run_1"},
        }

    async def list_messages(self, session_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
        if session_id != "sess_1":
            return []
        assert limit == 40
        return [
            {
                "message_id": "user_1",
                "role": "user",
                "message_type": "user_message",
                "content": "统计年份是什么？",
                "payload": {},
                "created_at": "2026-04-10T12:00:00+08:00",
            },
            {
                "message_id": "assistant_1",
                "role": "assistant",
                "message_type": "assistant_text",
                "content": "2021",
                "payload": {"finish_reason": "frontend_snapshot_short_circuit"},
                "created_at": "2026-04-10T12:00:01+08:00",
            },
        ]


class _FakeRuntime:
    def __init__(self) -> None:
        self.persistence = _FakePersistence()


def test_session_endpoint_returns_session_and_messages() -> None:
    app = FastAPI()
    app.include_router(build_router(assistant1_runtime=_FakeRuntime()))
    client = TestClient(app)

    response = client.get("/extract/assistant1/sessions/sess_1")
    assert response.status_code == 200
    payload = response.json()

    assert payload["session_id"] == "sess_1"
    assert payload["summary_used"] == "当前文档摘要"
    assert payload["file_hash"] == "fh_1"
    assert payload["file_name"] == "sample.pdf"
    assert payload["metadata"]["stream_run_id"] == "run_1"
    assert len(payload["messages"]) == 2
    assert payload["messages"][1]["content"] == "2021"


def test_session_endpoint_returns_404_when_missing() -> None:
    app = FastAPI()
    app.include_router(build_router(assistant1_runtime=_FakeRuntime()))
    client = TestClient(app)

    response = client.get("/extract/assistant1/sessions/missing")
    assert response.status_code == 404
