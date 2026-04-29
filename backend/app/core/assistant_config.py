from __future__ import annotations

import os
from dataclasses import dataclass


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default


def _has_any_env(*names: str) -> bool:
    return any(str(os.getenv(name, "") or "").strip() for name in names)


def _env_float(*names: str, default: float) -> float:
    for name in names:
        raw_value = str(os.getenv(name, "") or "").strip()
        if not raw_value:
            continue
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            continue
    return default


def _env_int(*names: str, default: int) -> int:
    for name in names:
        raw_value = str(os.getenv(name, "") or "").strip()
        if not raw_value:
            continue
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            continue
    return default


def _env_bool(*names: str, default: bool) -> bool:
    raw_value = _env(*names, default="")
    if not raw_value:
        return default
    return raw_value.lower() not in {"0", "false", "no", "off"}


def _prefixed_names(prefixes: tuple[str, ...], suffix: str) -> tuple[str, ...]:
    return tuple(f"{prefix}_{suffix}" for prefix in prefixes)


def get_platform_assistant_config_metadata() -> dict[str, object]:
    platform_names = _prefixed_names(
        ("PLATFORM_ASSISTANT",),
        "API_KEY",
    ) + _prefixed_names(
        ("PLATFORM_ASSISTANT",),
        "BASE_URL",
    ) + _prefixed_names(
        ("PLATFORM_ASSISTANT",),
        "MODEL",
    ) + ("PLATFORM_ASSISTANT_EXTRA_PROMPT",)
    assistant1_names = _prefixed_names(
        ("ASSISTANT1_CHAT",),
        "API_KEY",
    ) + _prefixed_names(
        ("ASSISTANT1_CHAT",),
        "BASE_URL",
    ) + _prefixed_names(
        ("ASSISTANT1_CHAT",),
        "MODEL",
    ) + ("AI_CHAT_EXTRA_PROMPT",)
    openai_names = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "AI_CHAT_MODEL")
    platform_configured = _has_any_env(*platform_names)
    assistant1_configured = _has_any_env(*assistant1_names)
    openai_configured = _has_any_env(*openai_names)
    legacy_config_present = assistant1_configured or openai_configured

    namespace = "platform_assistant" if platform_configured else "defaults_only"

    return {
        "namespace": namespace,
        "usesLegacyCompat": False,
        "supportsLegacyFallback": False,
        "legacyConfigFallbackEnabled": False,
        "legacyConfigPresent": legacy_config_present,
        "ignoredLegacyCompat": legacy_config_present and not platform_configured,
        "canonicalPrefix": "PLATFORM_ASSISTANT",
    }


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
        return cls._from_chat_env(
            prefixes=("ASSISTANT1_CHAT",),
            extra_prompt_names=("AI_CHAT_EXTRA_PROMPT",),
        )

    @classmethod
    def from_platform_assistant_env(cls) -> "AssistantSettings":
        return cls._from_chat_env(
            prefixes=("PLATFORM_ASSISTANT",),
            extra_prompt_names=("PLATFORM_ASSISTANT_EXTRA_PROMPT",),
            allow_openai_compat=False,
        )

    @classmethod
    def _from_chat_env(
        cls,
        *,
        prefixes: tuple[str, ...],
        extra_prompt_names: tuple[str, ...],
        allow_openai_compat: bool = True,
    ) -> "AssistantSettings":
        endpoint_path = _env(
            *_prefixed_names(prefixes, "ENDPOINT_PATH"),
            default="/chat/completions",
        ).strip() or "/chat/completions"
        if not endpoint_path.startswith("/"):
            endpoint_path = f"/{endpoint_path}"

        endpoint_style = _env(
            *_prefixed_names(prefixes, "ENDPOINT_STYLE"),
            default="openai_chat_completions",
        ).strip().lower()
        if endpoint_style not in {"openai_responses", "openai_chat_completions"}:
            endpoint_style = "openai_chat_completions"

        reasoning_effort = _env(
            *_prefixed_names(prefixes, "REASONING_EFFORT"),
            default="minimal",
        ).lower()
        if reasoning_effort not in {"", "minimal", "low", "medium", "high"}:
            reasoning_effort = "minimal"

        text_verbosity = _env(
            *_prefixed_names(prefixes, "TEXT_VERBOSITY"),
            default="medium",
        ).lower()
        if text_verbosity not in {"", "low", "medium", "high"}:
            text_verbosity = "medium"

        api_key_names = _prefixed_names(prefixes, "API_KEY")
        base_url_names = _prefixed_names(prefixes, "BASE_URL")
        model_names = _prefixed_names(prefixes, "MODEL")
        if allow_openai_compat:
            api_key_names = api_key_names + ("OPENAI_API_KEY",)
            base_url_names = base_url_names + ("OPENAI_BASE_URL",)
            model_names = model_names + ("AI_CHAT_MODEL",)

        return cls(
            chat_api_key=_env(
                *api_key_names,
                default="",
            ),
            chat_base_url=_env(
                *base_url_names,
                default="https://jeniya.cn/v1",
            ),
            chat_endpoint_path=endpoint_path,
            chat_endpoint_style=endpoint_style,
            chat_model=_env(
                *model_names,
                default="qwen-plus",
            ),
            chat_temperature=max(
                0.0,
                min(2.0, _env_float(*_prefixed_names(prefixes, "TEMPERATURE"), default=0.2)),
            ),
            chat_timeout_sec=max(
                10.0,
                _env_float(*_prefixed_names(prefixes, "TIMEOUT_SEC"), default=120.0),
            ),
            chat_max_output_tokens=max(
                256,
                _env_int(*_prefixed_names(prefixes, "MAX_OUTPUT_TOKENS"), default=2400),
            ),
            chat_reasoning_effort=reasoning_effort,
            chat_text_verbosity=text_verbosity,
            smoke_test_enabled=_env_bool(*_prefixed_names(prefixes, "SMOKE_TEST_ENABLED"), default=True),
            smoke_test_ttl_sec=max(
                60,
                _env_int(*_prefixed_names(prefixes, "SMOKE_TEST_TTL_SEC"), default=600),
            ),
            extra_prompt=_env(*extra_prompt_names, default=""),
        )
