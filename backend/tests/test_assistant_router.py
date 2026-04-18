from __future__ import annotations

from collections.abc import Iterator

from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.core.assistant_config import AssistantSettings
from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.factory import create_app
from app.modules.platform_assistant.services.chat_service import (
    PlatformAssistantService,
    get_platform_assistant_service,
)


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


def test_platform_assistant_health_endpoint_returns_unified_payload() -> None:
    app = create_app()
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=False),
    )
    app.dependency_overrides[get_platform_assistant_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/platform-assistant/health")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["model"] == "gpt-5-mini"
    assert payload["config"]["canonicalPrefix"] == "PLATFORM_ASSISTANT"
    assert payload["config"]["supportsLegacyFallback"] is False
    assert payload["config"]["legacyConfigFallbackEnabled"] is False
    assert payload["config"]["ignoredLegacyCompat"] is False
    assert payload["unicodeSmoke"]["enabled"] is False
    assert payload["route"] == "/api/platform-assistant/health"


def test_platform_assistant_diagnostics_endpoint_returns_detailed_payload_for_authenticated_user() -> None:
    app = create_app()
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=False),
    )
    app.dependency_overrides[get_platform_assistant_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = _fake_user

    with TestClient(app) as client:
        response = client.get("/api/platform-assistant/diagnostics")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "platform_assistant"
    assert payload["model"] == "gpt-5-mini"
    assert payload["config"]["canonicalPrefix"] == "PLATFORM_ASSISTANT"
    assert payload["unicodeSmoke"]["enabled"] is False
    assert payload["route"] == "/api/platform-assistant/diagnostics"


def test_platform_assistant_bootstrap_endpoint_returns_structured_page_payload() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/platform-assistant/bootstrap?tab=doc-processing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["assistant"]["chatPath"] == "/api/platform-assistant/chat"
    assert payload["assistant"]["healthPath"] == "/api/platform-assistant/health"
    assert payload["assistant"]["diagnosticsPath"] == "/api/platform-assistant/diagnostics"
    assert payload["assistant"]["catalogPath"] == "/api/platform-assistant/catalog"
    assert payload["page"]["tab"] == "doc-processing"
    assert isinstance(payload["page"]["cue"], str)
    assert isinstance(payload["page"]["starter"]["steps"], list)
    assert payload["page"]["starter"]["primaryAction"]["targetTab"] == "doc-processing"
    assert payload["page"]["starter"]["secondaryAction"]["targetTab"] == "deepread_extraction"
    assert payload["page"]["primaryPromptCount"] == 2
    assert payload["page"]["prompts"][0]["id"] == "doc-processing-upload"
    assert payload["page"]["prompts"][0]["answer"]["primaryAction"]["targetTab"] == "doc-processing"


def test_platform_assistant_catalog_endpoint_returns_all_structured_pages() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/platform-assistant/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["assistant"]["catalogPath"] == "/api/platform-assistant/catalog"
    assert isinstance(payload["pages"], list)
    assert len(payload["pages"]) >= 6
    page_tabs = {page["tab"] for page in payload["pages"]}
    assert "dashboard" in page_tabs
    assert "doc-processing" in page_tabs
    assert "deepread_extraction" in page_tabs


def test_platform_assistant_chat_endpoint_streams_text_event_stream_response() -> None:
    app = create_app()
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=True, stream_chunks=["你", "好"]),
    )
    app.dependency_overrides[get_platform_assistant_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = _fake_user

    with TestClient(app) as client:
        response = client.post(
            "/api/platform-assistant/chat",
            json={
                "messages": [{"role": "user", "content": "你好"}],
                "context": {"activeTab": "doc-processing", "pageCue": "system_status:ok"},
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-ai-reply-source"] == "model"
    assert '0:"你"' in response.text
    assert '0:"好"' in response.text
    assert '0:"[DONE]"' in response.text


def test_platform_assistant_chat_overwrites_client_supplied_session_meta() -> None:
    app = create_app()
    captured_payload: dict[str, object] = {}

    class CapturingService:
        def stream_chat(self, payload: dict[str, object]) -> StreamingResponse:
            captured_payload.update(payload)

            def _stream() -> Iterator[str]:
                yield ":ka\n\n"
                yield '0:"[DONE]"\n'

            return StreamingResponse(_stream(), media_type="text/event-stream")

    app.dependency_overrides[get_platform_assistant_service] = lambda: CapturingService()
    app.dependency_overrides[require_authenticated_user] = _fake_user

    with TestClient(app) as client:
        response = client.post(
            "/api/platform-assistant/chat",
            json={
                "messages": [{"role": "user", "content": "你好"}],
                "context": {
                    "activeTab": "doc-processing",
                    "pageCue": "local-cue",
                    "sessionMeta": {
                        "userId": "forged-user",
                        "tenantId": "forged-tenant",
                        "requestId": "forged-request",
                    },
                },
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    context = captured_payload["context"]
    assert isinstance(context, dict)
    session_meta = context["sessionMeta"]
    assert isinstance(session_meta, dict)
    assert session_meta["userId"] == "user-123"
    assert session_meta["tenantId"] == "user-123"
    assert session_meta["requestId"] == "sess-123"
