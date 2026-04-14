from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


router_module = _load_module(
    ["app", "modules", "module2", "api", "v1", "endpoints", "extraction_assistant.py"],
    "_smart_doc_flow_module2_api_v1_extraction_assistant_endpoint",
)

build_extraction_assistant_router = router_module.build_router


class _FakeAssistantRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def stream_chat(self, **kwargs):
        self.calls.append(dict(kwargs))
        return iter([b"event: assistant.done\ndata: {\"final_text\":\"ok\"}\n\n"])


def test_extraction_assistant_router_streams_and_delegates_payload() -> None:
    runtime = _FakeAssistantRuntime()
    app = FastAPI()
    app.include_router(build_extraction_assistant_router(assistant1_runtime=runtime))

    with TestClient(app) as client:
        response = client.post(
            "/extract/assistant1/chat/stream",
            json={
                "message": "请总结",
                "file_hash": "hash-demo",
                "history": [{"role": "user", "content": "hello"}],
                "max_steps": 4,
                "top_k": 6,
                "session_id": "session-1",
                "debug": True,
                "client_caps": {"supports_replace": True},
            },
        )

    assert response.status_code == 200
    assert "assistant.done" in response.text
    assert runtime.calls == [
        {
            "user_message": "请总结",
            "file_hash": "hash-demo",
            "history": [{"role": "user", "content": "hello"}],
            "max_steps": 4,
            "top_k": 6,
            "session_id": "session-1",
            "debug": True,
            "resume_run_id": "",
            "after_seq": 0,
            "extra_context": {},
            "client_supports_replace": True,
        }
    ]
