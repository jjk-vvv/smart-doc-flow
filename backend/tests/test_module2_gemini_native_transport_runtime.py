from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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


transport_module = _load_module(
    ["app", "modules", "module2", "core", "integration", "gemini_native_transport_runtime.py"],
    "_smart_doc_flow_module2_gemini_native_transport_runtime",
)

GeminiNativeTransportRuntime = transport_module.GeminiNativeTransportRuntime


def test_gemini_native_transport_runtime_builds_google_url_and_applies_model_override() -> None:
    runtime = GeminiNativeTransportRuntime(
        resolve_native_api_url=lambda: "",
        user_agent="test-agent",
        default_model="gemini-default",
    )

    google_url = runtime.build_google_native_url("")
    patched_url = runtime.apply_model_to_native_url(
        "https://example.com/v1beta/models/old-model:generateContent",
        "gpt-5-mini",
    )

    assert google_url.endswith("/models/gemini-default:generateContent")
    assert patched_url == "https://example.com/v1beta/models/gpt-5-mini:generateContent"


def test_gemini_native_transport_runtime_resolves_native_url_from_provider() -> None:
    runtime = GeminiNativeTransportRuntime(
        resolve_native_api_url=lambda: "https://proxy.test/v1beta/models/base-model:generateContent",
        user_agent="test-agent",
        default_model="gemini-default",
    )

    assert runtime.resolve_native_url("gemini-2.5-flash") == (
        "https://proxy.test/v1beta/models/gemini-2.5-flash:generateContent"
    )


def test_gemini_native_transport_runtime_builds_google_and_bearer_headers() -> None:
    runtime = GeminiNativeTransportRuntime(
        resolve_native_api_url=lambda: "",
        user_agent="test-agent",
        default_model="gemini-default",
        connection_close=True,
    )

    google_headers = runtime.build_headers(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent",
        "AIza-test-key",
    )
    bearer_headers = runtime.build_headers(
        "https://proxy.test/v1beta/models/gemini:generateContent",
        "token-123",
    )

    assert google_headers["User-Agent"] == "test-agent"
    assert google_headers["Connection"] == "close"
    assert google_headers["x-goog-api-key"] == "AIza-test-key"
    assert "Authorization" not in google_headers
    assert bearer_headers["Authorization"] == "Bearer token-123"
