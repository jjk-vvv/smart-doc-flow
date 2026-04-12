from __future__ import annotations

import os
from dataclasses import dataclass


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, default) or "").strip())
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default) or "").strip())
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AssistantSettings:
    chat_api_key: str
    chat_base_url: str
    chat_endpoint_path: str
    chat_endpoint_style: str
    chat_model: str
    chat_temperature: float
    chat_timeout_sec: float
    chat_max_output_tokens: int
    chat_reasoning_effort: str
    chat_text_verbosity: str
    smoke_test_enabled: bool
    smoke_test_ttl_sec: int
    extra_prompt: str

    @classmethod
    def from_env(cls) -> "AssistantSettings":
        endpoint_path = _env(
            "ASSISTANT1_CHAT_ENDPOINT_PATH",
            default="/v1/responses",
        ).strip() or "/v1/responses"
        if not endpoint_path.startswith("/"):
            endpoint_path = f"/{endpoint_path}"

        endpoint_style = _env(
            "ASSISTANT1_CHAT_ENDPOINT_STYLE",
            default="openai_responses",
        ).strip().lower()
        if endpoint_style not in {"openai_responses", "openai_chat_completions"}:
            endpoint_style = "openai_responses"

        reasoning_effort = _env(
            "ASSISTANT1_CHAT_REASONING_EFFORT",
            default="minimal",
        ).lower()
        if reasoning_effort not in {"", "minimal", "low", "medium", "high"}:
            reasoning_effort = "minimal"

        text_verbosity = _env(
            "ASSISTANT1_CHAT_TEXT_VERBOSITY",
            default="medium",
        ).lower()
        if text_verbosity not in {"", "low", "medium", "high"}:
            text_verbosity = "medium"

        return cls(
            chat_api_key=_env(
                "ASSISTANT1_CHAT_API_KEY",
                "OPENAI_API_KEY",
                default="",
            ),
            chat_base_url=_env(
                "ASSISTANT1_CHAT_BASE_URL",
                "OPENAI_BASE_URL",
                default="https://api.openai.com",
            ),
            chat_endpoint_path=endpoint_path,
            chat_endpoint_style=endpoint_style,
            chat_model=_env(
                "ASSISTANT1_CHAT_MODEL",
                "AI_CHAT_MODEL",
                default="gpt-5-mini",
            ),
            chat_temperature=max(
                0.0,
                min(2.0, _env_float("ASSISTANT1_CHAT_TEMPERATURE", 0.2)),
            ),
            chat_timeout_sec=max(
                10.0,
                _env_float("ASSISTANT1_CHAT_TIMEOUT_SEC", 120.0),
            ),
            chat_max_output_tokens=max(
                256,
                _env_int("ASSISTANT1_CHAT_MAX_OUTPUT_TOKENS", 2400),
            ),
            chat_reasoning_effort=reasoning_effort,
            chat_text_verbosity=text_verbosity,
            smoke_test_enabled=_env("ASSISTANT1_CHAT_SMOKE_TEST_ENABLED", default="1").lower() not in {"0", "false", "no", "off"},
            smoke_test_ttl_sec=max(
                60,
                _env_int("ASSISTANT1_CHAT_SMOKE_TEST_TTL_SEC", 600),
            ),
            extra_prompt=_env("AI_CHAT_EXTRA_PROMPT", default=""),
        )
