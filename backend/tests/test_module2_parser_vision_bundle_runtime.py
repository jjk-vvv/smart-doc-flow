from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_vision_bundle_runtime_module = import_module("app.modules.module2.core.parsers.parser_vision_transport_bootstrap_runtime")

ParserVisionBundleRuntime = parser_vision_bundle_runtime_module.ParserVisionBundleRuntime


def test_parser_vision_bundle_runtime_builds_response_kwargs() -> None:
    kwargs = ParserVisionBundleRuntime().build_vision_response_kwargs(normalize_text=lambda text: str(text).strip())
    assert kwargs["normalize_text"]("  value  ") == "value"


def test_parser_vision_bundle_runtime_builds_request_and_matching_kwargs() -> None:
    runtime = ParserVisionBundleRuntime()
    kwargs = runtime.build_vision_request_kwargs(
        vision_dpi=150, vision_max_side_px=1800, vision_model="test-vision-model",
        vision_base_url="https://provider.test/v1", vision_endpoint_style="openai_chat_completions",
        vision_timeout_sec=42.5, vision_max_output_tokens=4096,
        resolve_api_key=lambda: "test-key", extract_json_object=lambda text: {"raw": text},
    )
    assert kwargs["vision_model"] == "test-vision-model"
    assert kwargs["vision_base_url"] == "https://provider.test/v1"
    assert kwargs["vision_timeout_sec"] == 42.5
    assert kwargs["resolve_api_key"]() == "test-key"
    assert kwargs["extract_json_object"]("json") == {"raw": "json"}
    matching = runtime.build_figure_matching_kwargs(
        normalize_text=lambda text: str(text).strip(), normalize_token_for_compare=lambda text: str(text).lower(),
    )
    assert matching["normalize_text"]("  chart  ") == "chart"
    assert matching["normalize_token_for_compare"]("Chart") == "chart"
