from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_vision_transport_bootstrap_module = import_module("module2.app.core.parsers.parser_vision_transport_bootstrap_runtime")
parser_vision_bundle_module = parser_vision_transport_bootstrap_module

ParserVisionTransportBootstrapRuntime = (
    parser_vision_transport_bootstrap_module.ParserVisionTransportBootstrapRuntime
)
ParserVisionBundleRuntime = parser_vision_bundle_module.ParserVisionBundleRuntime


def test_parser_vision_transport_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    runtime = ParserVisionTransportBootstrapRuntime()

    attrs = runtime.build_vision_transport_runtime_attrs(
        parser_vision_bundle_runtime=ParserVisionBundleRuntime(),
        resolve_native_api_url=lambda: "https://example.com/v1beta/models/gpt-5-mini:generateContent",
        user_agent="smart-doc-flow-module2-parser/1.0",
        default_model="gpt-5-mini",
        normalize_text=lambda text: str(text).strip(),
        normalize_token_for_compare=lambda text: str(text).lower(),
        gemini_vision_dpi=144,
        gemini_vision_max_side_px=1600,
        gemini_vision_model="gpt-5-mini",
        gemini_vision_timeout_sec=30.0,
        gemini_vision_max_output_tokens=2048,
        gemini_native_fallback_enabled=True,
        resolve_api_key=lambda: "api-key",
        resolve_native_api_key=lambda: "native-key",
    )

    expected_keys = {
        "_gemini_native_transport_runtime",
        "_vision_response_runtime",
        "_vision_request_runtime",
        "_figure_matching_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_gemini_native_transport_runtime"], "build_headers")
    assert hasattr(attrs["_vision_response_runtime"], "extract_json_object")
    assert hasattr(attrs["_vision_request_runtime"], "extract_payload")
    assert hasattr(attrs["_figure_matching_runtime"], "find_matching_pdf_figure_index")
    assert attrs["_gemini_native_transport_runtime"].default_model == "gpt-5-mini"
    assert attrs["_vision_request_runtime"]._resolve_native_url.__self__ is attrs["_gemini_native_transport_runtime"]
    assert attrs["_vision_request_runtime"]._build_headers.__self__ is attrs["_gemini_native_transport_runtime"]
