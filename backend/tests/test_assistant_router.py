from __future__ import annotations

from fastapi.testclient import TestClient

from app.create_app import create_app
from app.modules.assistant.config import AssistantSettings
from app.modules.assistant.service import AssistantService, get_assistant_service
from app.modules.auth.deps import AuthenticatedUser, require_authenticated_user


class FakeProvider:
    def __init__(self, *, configured: bool, stream_chunks: list[str] | None = None) -> None:
        self.configured = configured
        self.stream_chunks = list(stream_chunks or [])

    def provider_info(self) -> dict[str, str]:
        return {
            "baseUrl": "https://example.test",
            "endpointPath": "/v1/responses",
            "endpointStyle": "openai_responses",
            "model": "gpt-5-mini",
        }

    def stream_text(self, *, messages, instructions):
        del messages, instructions
        for chunk in self.stream_chunks:
            yield chunk


def _assistant_settings(*, smoke_test_enabled: bool = False) -> AssistantSettings:
    return AssistantSettings(
        chat_api_key="",
        chat_base_url="https://example.test",
        chat_endpoint_path="/v1/responses",
        chat_endpoint_style="openai_responses",
        chat_model="gpt-5-mini",
        chat_temperature=0.2,
        chat_timeout_sec=120.0,
        chat_max_output_tokens=2400,
        chat_reasoning_effort="minimal",
        chat_text_verbosity="medium",
        smoke_test_enabled=smoke_test_enabled,
        smoke_test_ttl_sec=600,
        extra_prompt="",
    )


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user-123",
        name="Tester",
        email="tester@example.com",
        phone="13900000000",
        status="active",
        session_id="sess-123",
    )


def test_chat_health_endpoint_returns_unified_payload() -> None:
    app = create_app()
    service = AssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=False),
    )
    app.dependency_overrides[get_assistant_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/chat/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["model"] == "gpt-5-mini"
    assert payload["unicodeSmoke"]["enabled"] is False


def test_chat_endpoint_streams_text_event_stream_response() -> None:
    app = create_app()
    service = AssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=True, stream_chunks=["你", "好"]),
    )
    app.dependency_overrides[get_assistant_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = _fake_user

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "你好"}],
                "platformContext": "系统状态正常",
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-ai-reply-source"] == "model"
    assert '0:"你"' in response.text
    assert '0:"好"' in response.text
    assert '0:"[DONE]"' in response.text
