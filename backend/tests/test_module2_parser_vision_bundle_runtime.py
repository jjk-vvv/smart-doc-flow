from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_vision_bundle_runtime_module = import_module("module2.app.core.parsers.parser_vision_transport_bootstrap_runtime")

ParserVisionBundleRuntime = parser_vision_bundle_runtime_module.ParserVisionBundleRuntime


def test_parser_vision_bundle_runtime_builds_transport_and_response_kwargs() -> None:
    runtime = ParserVisionBundleRuntime()

    resolve_native_api_url = lambda: "https://example.com/models/default:generateContent"
    normalize_text = lambda text: str(text).strip()

    transport_kwargs = runtime.build_gemini_native_transport_kwargs(
        resolve_native_api_url=resolve_native_api_url,
        user_agent="smart-doc-flow-module2-parser/1.0",
        default_model="gemini-3.1-pro-preview",
    )
    response_kwargs = runtime.build_vision_response_kwargs(
        normalize_text=normalize_text,
    )

    assert transport_kwargs["resolve_native_api_url"]() == "https://example.com/models/default:generateContent"
    assert transport_kwargs["user_agent"] == "smart-doc-flow-module2-parser/1.0"
    assert transport_kwargs["default_model"] == "gemini-3.1-pro-preview"
    assert response_kwargs["normalize_text"]("  value  ") == "value"


def test_parser_vision_bundle_runtime_builds_request_and_matching_kwargs() -> None:
    runtime = ParserVisionBundleRuntime()

    resolve_api_key = lambda: "api-key"
    resolve_native_api_key = lambda: "native-key"
    resolve_native_url = lambda model: f"https://example.com/models/{model}:generateContent"
    build_google_native_url = lambda model: f"https://googleapis.com/models/{model}:generateContent"
    build_headers = lambda url, key: {"Authorization": f"Bearer {key}", "X-Url": url}
    extract_json_object = lambda text: {"raw": text}
    extract_candidate_text = lambda raw: f"candidate:{raw}"
    normalize_text = lambda text: str(text).strip()
    normalize_token_for_compare = lambda text: str(text).lower()

    request_kwargs = runtime.build_vision_request_kwargs(
        gemini_vision_dpi=150,
        gemini_vision_max_side_px=1800,
        gemini_vision_model="gpt-5-mini",
        gemini_vision_timeout_sec=42.5,
        gemini_vision_max_output_tokens=4096,
        gemini_native_fallback_enabled=True,
        resolve_api_key=resolve_api_key,
        resolve_native_api_key=resolve_native_api_key,
        resolve_native_url=resolve_native_url,
        build_google_native_url=build_google_native_url,
        build_headers=build_headers,
        extract_json_object=extract_json_object,
        extract_candidate_text=extract_candidate_text,
    )
    matching_kwargs = runtime.build_figure_matching_kwargs(
        normalize_text=normalize_text,
        normalize_token_for_compare=normalize_token_for_compare,
    )

    assert request_kwargs["gemini_vision_dpi"] == 150
    assert request_kwargs["gemini_vision_max_side_px"] == 1800
    assert request_kwargs["gemini_vision_model"] == "gpt-5-mini"
    assert request_kwargs["gemini_vision_timeout_sec"] == 42.5
    assert request_kwargs["gemini_vision_max_output_tokens"] == 4096
    assert request_kwargs["gemini_native_fallback_enabled"] is True
    assert request_kwargs["resolve_api_key"]() == "api-key"
    assert request_kwargs["resolve_native_api_key"]() == "native-key"
    assert request_kwargs["resolve_native_url"]("gpt-5-mini") == "https://example.com/models/gpt-5-mini:generateContent"
    assert request_kwargs["build_google_native_url"]("gpt-5-mini") == "https://googleapis.com/models/gpt-5-mini:generateContent"
    assert request_kwargs["build_headers"]("https://example.com", "token") == {
        "Authorization": "Bearer token",
        "X-Url": "https://example.com",
    }
    assert request_kwargs["extract_json_object"]("json") == {"raw": "json"}
    assert request_kwargs["extract_candidate_text"]("raw") == "candidate:raw"
    assert matching_kwargs["normalize_text"]("  chart  ") == "chart"
    assert matching_kwargs["normalize_token_for_compare"]("Chart") == "chart"
