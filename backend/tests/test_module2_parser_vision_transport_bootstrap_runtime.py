from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_vision_transport_bootstrap_module = import_module("app.modules.module2.core.parsers.parser_vision_transport_bootstrap_runtime")
parser_vision_bundle_module = parser_vision_transport_bootstrap_module

ParserVisionTransportBootstrapRuntime = (
    parser_vision_transport_bootstrap_module.ParserVisionTransportBootstrapRuntime
)
ParserVisionBundleRuntime = parser_vision_bundle_module.ParserVisionBundleRuntime


def test_parser_vision_transport_bootstrap_runtime_builds_expected_runtime_attrs() -> None:
    attrs = ParserVisionTransportBootstrapRuntime().build_vision_transport_runtime_attrs(
        parser_vision_bundle_runtime=ParserVisionBundleRuntime(),
        normalize_text=lambda text: str(text).strip(), normalize_token_for_compare=lambda text: str(text).lower(),
        vision_dpi=144, vision_max_side_px=1600, vision_model="test-vision-model",
        vision_base_url="https://provider.test/v1", vision_endpoint_style="openai_chat_completions",
        vision_timeout_sec=30.0, vision_max_output_tokens=2048, resolve_api_key=lambda: "test-key",
    )
    assert set(attrs) == {"_vision_response_runtime", "_vision_request_runtime", "_figure_matching_runtime"}
    assert attrs["_vision_request_runtime"].vision_model == "test-vision-model"
    assert attrs["_vision_request_runtime"].vision_base_url == "https://provider.test/v1"
    assert hasattr(attrs["_vision_response_runtime"], "extract_json_object")
    assert hasattr(attrs["_figure_matching_runtime"], "find_matching_pdf_figure_index")
