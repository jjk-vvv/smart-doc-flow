from __future__ import annotations

import json

from app.core.assistant_config import AssistantSettings
from app.integrations.assistant_provider import AssistantResponsesProvider


class _FakeResponse:
    def __init__(
        self,
        *,
        json_payload: dict | None = None,
        stream_lines: list[bytes] | None = None,
        status_code: int = 200,
    ) -> None:
        self._json_payload = json_payload or {}
        self._stream_lines = list(stream_lines or [])
        self.status_code = status_code
        self.text = json.dumps(self._json_payload, ensure_ascii=False)
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_payload

    def iter_lines(self, decode_unicode: bool = False):
        del decode_unicode
        for line in self._stream_lines:
            yield line

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False


def _settings(*, endpoint_path: str, endpoint_style: str) -> AssistantSettings:
    return AssistantSettings(
        chat_api_key="test-key",
        chat_base_url="https://provider.example",
        chat_endpoint_path=endpoint_path,
        chat_endpoint_style=endpoint_style,
        chat_model="glm-test",
        chat_temperature=0.2,
        chat_timeout_sec=30.0,
        chat_max_output_tokens=512,
        chat_reasoning_effort="minimal",
        chat_text_verbosity="medium",
        smoke_test_enabled=False,
        smoke_test_ttl_sec=600,
        extra_prompt="",
    )


def test_provider_complete_text_supports_openai_responses_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_post(url, *, json=None, headers=None, timeout=None, stream=False):
        captured.update(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
                "stream": stream,
            }
        )
        return _FakeResponse(
            json_payload={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "链路正常",
                            }
                        ],
                    }
                ]
            }
        )

    monkeypatch.setattr("app.integrations.assistant_provider.requests.post", _fake_post)
    provider = AssistantResponsesProvider(_settings(endpoint_path="/v1/responses", endpoint_style="openai_responses"))

    text = provider.complete_text(
        messages=[{"role": "user", "content": "你好"}],
        instructions="仅返回四个字",
    )

    assert text == "链路正常"
    assert captured["url"] == "https://provider.example/v1/responses"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "glm-test"
    assert payload["instructions"] == "仅返回四个字"
    assert payload["max_output_tokens"] == 512
    assert isinstance(payload["input"], list)


def test_provider_complete_text_supports_chat_completions_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_post(url, *, json=None, headers=None, timeout=None, stream=False):
        captured.update(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
                "stream": stream,
            }
        )
        return _FakeResponse(
            json_payload={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "平台助手已切到智谱通道。",
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("app.integrations.assistant_provider.requests.post", _fake_post)
    provider = AssistantResponsesProvider(
        _settings(endpoint_path="/chat/completions", endpoint_style="openai_chat_completions")
    )

    text = provider.complete_text(
        messages=[{"role": "user", "content": "现在走哪个模型通道"}],
        instructions="请直接回答",
    )

    assert text == "平台助手已切到智谱通道。"
    assert captured["url"] == "https://provider.example/chat/completions"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "glm-test"
    assert payload["max_tokens"] == 512
    assert "stream" not in payload
    assert payload["messages"][0] == {"role": "system", "content": "请直接回答"}
    assert payload["messages"][1] == {"role": "user", "content": "现在走哪个模型通道"}
    assert "input" not in payload
    assert "instructions" not in payload


def test_provider_stream_text_supports_chat_completions_sse(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_post(url, *, json=None, headers=None, timeout=None, stream=False):
        captured.update(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
                "stream": stream,
            }
        )
        return _FakeResponse(
            stream_lines=[
                b'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                b"",
                'data: {"choices":[{"delta":{"content":"你"}}]}'.encode("utf-8"),
                b"",
                'data: {"choices":[{"delta":{"content":"好"}}]}'.encode("utf-8"),
                b"",
                b"data: [DONE]",
                b"",
            ]
        )

    monkeypatch.setattr("app.integrations.assistant_provider.requests.post", _fake_post)
    provider = AssistantResponsesProvider(
        _settings(endpoint_path="/chat/completions", endpoint_style="openai_chat_completions")
    )

    chunks = list(
        provider.stream_text(
            messages=[{"role": "user", "content": "你好"}],
            instructions="请直接回答",
        )
    )

    assert chunks == ["你", "好"]
    assert captured["url"] == "https://provider.example/chat/completions"
    assert captured["stream"] is True
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["messages"][0] == {"role": "system", "content": "请直接回答"}
