from __future__ import annotations

from app.core.assistant_config import AssistantSettings, get_platform_assistant_config_metadata
from app.modules.platform_assistant.services.chat_service import PlatformAssistantService


class _DummyProvider:
    configured = False

    def provider_info(self) -> dict[str, str]:
        return {
            "baseUrl": "",
            "endpointPath": "",
            "endpointStyle": "",
            "model": "",
        }


def _clear_assistant_env(monkeypatch) -> None:
    for name in [
        "PLATFORM_ASSISTANT_API_KEY",
        "PLATFORM_ASSISTANT_BASE_URL",
        "PLATFORM_ASSISTANT_ENDPOINT_PATH",
        "PLATFORM_ASSISTANT_ENDPOINT_STYLE",
        "PLATFORM_ASSISTANT_MODEL",
        "PLATFORM_ASSISTANT_TEMPERATURE",
        "PLATFORM_ASSISTANT_TIMEOUT_SEC",
        "PLATFORM_ASSISTANT_MAX_OUTPUT_TOKENS",
        "PLATFORM_ASSISTANT_REASONING_EFFORT",
        "PLATFORM_ASSISTANT_TEXT_VERBOSITY",
        "PLATFORM_ASSISTANT_SMOKE_TEST_ENABLED",
        "PLATFORM_ASSISTANT_SMOKE_TEST_TTL_SEC",
        "PLATFORM_ASSISTANT_EXTRA_PROMPT",
        "ASSISTANT1_CHAT_API_KEY",
        "ASSISTANT1_CHAT_BASE_URL",
        "ASSISTANT1_CHAT_ENDPOINT_PATH",
        "ASSISTANT1_CHAT_ENDPOINT_STYLE",
        "ASSISTANT1_CHAT_MODEL",
        "ASSISTANT1_CHAT_TEMPERATURE",
        "ASSISTANT1_CHAT_TIMEOUT_SEC",
        "ASSISTANT1_CHAT_MAX_OUTPUT_TOKENS",
        "ASSISTANT1_CHAT_REASONING_EFFORT",
        "ASSISTANT1_CHAT_TEXT_VERBOSITY",
        "ASSISTANT1_CHAT_SMOKE_TEST_ENABLED",
        "ASSISTANT1_CHAT_SMOKE_TEST_TTL_SEC",
        "AI_CHAT_EXTRA_PROMPT",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "AI_CHAT_MODEL",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_platform_assistant_settings_prefer_platform_assistant_env_keys(monkeypatch) -> None:
    _clear_assistant_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_ASSISTANT_API_KEY", "platform-key")
    monkeypatch.setenv("PLATFORM_ASSISTANT_BASE_URL", "https://platform.example")
    monkeypatch.setenv("PLATFORM_ASSISTANT_MODEL", "test-platform-model")
    monkeypatch.setenv("PLATFORM_ASSISTANT_TEXT_VERBOSITY", "high")
    monkeypatch.setenv("PLATFORM_ASSISTANT_EXTRA_PROMPT", "platform prompt")
    monkeypatch.setenv("ASSISTANT1_CHAT_API_KEY", "legacy-key")
    monkeypatch.setenv("ASSISTANT1_CHAT_BASE_URL", "https://legacy.example")
    monkeypatch.setenv("ASSISTANT1_CHAT_MODEL", "test-compat-model")
    monkeypatch.setenv("AI_CHAT_EXTRA_PROMPT", "legacy prompt")

    platform_settings = AssistantSettings.from_platform_assistant_env()
    legacy_settings = AssistantSettings.from_env()

    assert platform_settings.chat_api_key == "platform-key"
    assert platform_settings.chat_base_url == "https://platform.example"
    assert platform_settings.chat_model == "test-platform-model"
    assert platform_settings.chat_text_verbosity == "high"
    assert platform_settings.extra_prompt == "platform prompt"
    assert legacy_settings.chat_api_key == "legacy-key"
    assert legacy_settings.chat_base_url == "https://legacy.example"
    assert legacy_settings.chat_model == "test-compat-model"
    assert legacy_settings.extra_prompt == "legacy prompt"


def test_platform_assistant_settings_ignore_legacy_assistant1_env_keys(monkeypatch) -> None:
    _clear_assistant_env(monkeypatch)
    monkeypatch.setenv("ASSISTANT1_CHAT_API_KEY", "legacy-key")
    monkeypatch.setenv("ASSISTANT1_CHAT_BASE_URL", "https://legacy.example")
    monkeypatch.setenv("ASSISTANT1_CHAT_ENDPOINT_PATH", "v1/chat/completions")
    monkeypatch.setenv("ASSISTANT1_CHAT_MODEL", "test-compat-model")
    monkeypatch.setenv("ASSISTANT1_CHAT_SMOKE_TEST_ENABLED", "0")
    monkeypatch.setenv("AI_CHAT_EXTRA_PROMPT", "legacy prompt")

    settings = AssistantSettings.from_platform_assistant_env()

    assert settings.chat_api_key == ""
    assert settings.chat_base_url == "https://quanzil.com/v1"
    assert settings.chat_endpoint_path == "/chat/completions"
    assert settings.chat_model == "qwen-plus"
    assert settings.smoke_test_enabled is True
    assert settings.extra_prompt == ""


def test_platform_assistant_settings_ignore_openai_compat_env_keys(monkeypatch) -> None:
    _clear_assistant_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.example")
    monkeypatch.setenv("AI_CHAT_MODEL", "test-compatible-model")

    settings = AssistantSettings.from_platform_assistant_env()

    assert settings.chat_api_key == ""
    assert settings.chat_base_url == "https://quanzil.com/v1"
    assert settings.chat_model == "qwen-plus"
    assert settings.extra_prompt == ""


def test_platform_assistant_service_defaults_to_platform_assistant_env_loader(monkeypatch) -> None:
    _clear_assistant_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_ASSISTANT_API_KEY", "platform-key")
    monkeypatch.setenv("PLATFORM_ASSISTANT_BASE_URL", "https://platform.example")
    monkeypatch.setenv("PLATFORM_ASSISTANT_MODEL", "test-platform-model")
    monkeypatch.setenv("ASSISTANT1_CHAT_API_KEY", "legacy-key")
    monkeypatch.setenv("ASSISTANT1_CHAT_BASE_URL", "https://legacy.example")
    monkeypatch.setenv("ASSISTANT1_CHAT_MODEL", "test-compat-model")

    service = PlatformAssistantService(provider=_DummyProvider())

    assert service.settings.chat_api_key == "platform-key"
    assert service.settings.chat_base_url == "https://platform.example"
    assert service.settings.chat_model == "test-platform-model"


def test_platform_assistant_config_metadata_reports_platform_namespace(monkeypatch) -> None:
    _clear_assistant_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_ASSISTANT_API_KEY", "platform-key")

    metadata = get_platform_assistant_config_metadata()

    assert metadata["namespace"] == "platform_assistant"
    assert metadata["usesLegacyCompat"] is False
    assert metadata["supportsLegacyFallback"] is False
    assert metadata["legacyConfigFallbackEnabled"] is False
    assert metadata["legacyConfigPresent"] is False
    assert metadata["ignoredLegacyCompat"] is False
    assert metadata["canonicalPrefix"] == "PLATFORM_ASSISTANT"


def test_platform_assistant_config_metadata_reports_ignored_legacy_namespace(monkeypatch) -> None:
    _clear_assistant_env(monkeypatch)
    monkeypatch.setenv("ASSISTANT1_CHAT_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    metadata = get_platform_assistant_config_metadata()

    assert metadata["namespace"] == "defaults_only"
    assert metadata["usesLegacyCompat"] is False
    assert metadata["supportsLegacyFallback"] is False
    assert metadata["legacyConfigFallbackEnabled"] is False
    assert metadata["legacyConfigPresent"] is True
    assert metadata["ignoredLegacyCompat"] is True
