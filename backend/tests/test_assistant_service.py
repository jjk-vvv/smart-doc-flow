from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from app.core.assistant_config import AssistantSettings
from app.modules.platform_assistant.data.platform_facts import CHAT_FALLBACK_TEXT
from app.modules.platform_assistant.services.chat_service import (
    ASSISTANT_EMPTY_RESPONSE_TEXT,
    ASSISTANT_NO_KEY_TEXT,
    ASSISTANT_STREAM_ERROR_TEXT,
    PlatformAssistantService,
)


class FakeProvider:
    def __init__(
        self,
        *,
        configured: bool,
        stream_chunks: list[str] | None = None,
        stream_error: Exception | None = None,
        complete_text_reply: str = "链路正常",
    ) -> None:
        self.configured = configured
        self.stream_chunks = list(stream_chunks or [])
        self.stream_error = stream_error
        self.complete_text_reply = complete_text_reply
        self.complete_text_calls = 0
        self.stream_calls: list[dict[str, object]] = []

    def provider_info(self) -> dict[str, str]:
        return {
            "baseUrl": "https://example.test",
            "endpointPath": "/v1/responses",
            "endpointStyle": "openai_responses",
            "model": "test-chat-model",
        }

    def complete_text(self, **kwargs) -> str:
        self.complete_text_calls += 1
        return self.complete_text_reply

    def stream_text(self, *, messages, instructions):
        self.stream_calls.append(
            {
                "messages": messages,
                "instructions": instructions,
            }
        )
        if self.stream_error is not None:
            raise self.stream_error
        for chunk in self.stream_chunks:
            yield chunk


def _assistant_settings(*, smoke_test_enabled: bool = False) -> AssistantSettings:
    return AssistantSettings(
        chat_api_key="",
        chat_base_url="https://example.test",
        chat_endpoint_path="/v1/responses",
        chat_endpoint_style="openai_responses",
        chat_model="test-chat-model",
        chat_temperature=0.2,
        chat_timeout_sec=120.0,
        chat_max_output_tokens=2400,
        chat_reasoning_effort="minimal",
        chat_text_verbosity="medium",
        smoke_test_enabled=smoke_test_enabled,
        smoke_test_ttl_sec=600,
        extra_prompt="",
    )


async def _collect_stream_body(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


def _render_stream(response) -> tuple[str, str]:
    raw_stream = asyncio.run(_collect_stream_body(response))
    data_chunks: list[str] = []
    for line in raw_stream.splitlines():
        if not line.startswith("0:"):
            continue
        value = json.loads(line[2:])
        if value == "[DONE]":
            continue
        data_chunks.append(str(value))
    return raw_stream, "".join(data_chunks)


def test_assistant_health_payload_reports_disabled_smoke() -> None:
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=False),
    )

    payload = service.health_payload()

    assert payload["ok"] is True
    assert payload["model"] == "test-chat-model"
    assert payload["keyConfigured"] is False
    assert payload["unicodeSmoke"]["enabled"] is False


def test_assistant_health_payload_reuses_smoke_cache_until_forced() -> None:
    provider = FakeProvider(configured=True, complete_text_reply="链路正常。")
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=True),
        provider=provider,
    )

    first_payload = service.health_payload()
    cached_payload = service.health_payload()
    forced_payload = service.health_payload(force_smoke=True)

    assert first_payload["unicodeSmoke"]["ok"] is True
    assert cached_payload["unicodeSmoke"]["ok"] is True
    assert forced_payload["unicodeSmoke"]["ok"] is True
    assert provider.complete_text_calls == 2


def test_assistant_stream_chat_requires_messages() -> None:
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=False),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.stream_chat({"messages": []})

    assert exc_info.value.status_code == 400
    assert "messages is required" in str(exc_info.value.detail)


def test_assistant_stream_chat_returns_config_fallback_when_provider_missing() -> None:
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=FakeProvider(configured=False),
    )

    response = service.stream_chat({"messages": [{"role": "user", "content": "你好"}]})
    raw_stream, rendered_text = _render_stream(response)

    assert response.headers["X-AI-Reply-Source"] == "fallback_no_key"
    assert ASSISTANT_NO_KEY_TEXT in rendered_text
    assert "PLATFORM_ASSISTANT_API_KEY" in rendered_text
    assert '0:"[DONE]"' in raw_stream


def test_assistant_stream_chat_streams_model_chunks_and_builds_prompt() -> None:
    provider = FakeProvider(configured=True, stream_chunks=["你", "好"])
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=provider,
    )

    response = service.stream_chat(
        {
            "messages": [{"role": "user", "content": "请介绍模块2"}],
            "context": {
                "activeTab": "deepread_extraction",
                "pageCue": "模块2 状态：健康",
            },
        }
    )
    raw_stream, rendered_text = _render_stream(response)

    assert response.headers["X-AI-Reply-Source"] == "model"
    assert rendered_text == "你好"
    assert '0:"[DONE]"' in raw_stream
    assert provider.stream_calls
    assert provider.stream_calls[0]["messages"] == [{"role": "user", "content": "请介绍模块2"}]
    assert "[Platform Facts]" in str(provider.stream_calls[0]["instructions"])
    assert "模块2 状态：健康" in str(provider.stream_calls[0]["instructions"])


def test_assistant_stream_chat_falls_back_when_provider_errors() -> None:
    provider = FakeProvider(configured=True, stream_error=RuntimeError("boom"))
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=provider,
    )

    response = service.stream_chat({"messages": [{"role": "user", "content": "你好"}]})
    raw_stream, rendered_text = _render_stream(response)

    assert ASSISTANT_STREAM_ERROR_TEXT in rendered_text
    assert CHAT_FALLBACK_TEXT in rendered_text
    assert '0:"[DONE]"' in raw_stream


def test_assistant_stream_chat_falls_back_when_provider_returns_no_text() -> None:
    provider = FakeProvider(configured=True, stream_chunks=["", "", "  "])
    service = PlatformAssistantService(
        settings=_assistant_settings(smoke_test_enabled=False),
        provider=provider,
    )

    response = service.stream_chat({"messages": [{"role": "user", "content": "你好"}]})
    raw_stream, rendered_text = _render_stream(response)

    assert ASSISTANT_EMPTY_RESPONSE_TEXT in rendered_text
    assert CHAT_FALLBACK_TEXT in rendered_text
    assert '0:"[DONE]"' in raw_stream
