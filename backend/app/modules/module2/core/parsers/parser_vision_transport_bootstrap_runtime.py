from __future__ import annotations

from typing import Any, Callable, Dict

from ..visual.figure_semantics import FigureMatchingRuntime
from ..visual.vision_request_runtime import VisionRequestRuntime
from ..visual.vision_response_runtime import VisionResponseRuntime


RuntimeCallback = Callable[..., Any]


class ParserVisionBundleRuntime:
    """Build pure kwargs for parser-owned vision transport components."""


    def build_vision_response_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
        }

    def build_vision_request_kwargs(
        self,
        *,
        vision_dpi: int,
        vision_max_side_px: int,
        vision_model: str,
        vision_base_url: str,
        vision_endpoint_style: str,
        vision_timeout_sec: float,
        vision_max_output_tokens: int,
        resolve_api_key: RuntimeCallback,
        extract_json_object: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "vision_dpi": vision_dpi,
            "vision_max_side_px": vision_max_side_px,
            "vision_model": vision_model,
            "vision_base_url": vision_base_url,
            "vision_endpoint_style": vision_endpoint_style,
            "vision_timeout_sec": vision_timeout_sec,
            "vision_max_output_tokens": vision_max_output_tokens,
            "resolve_api_key": resolve_api_key,
            "extract_json_object": extract_json_object,
        }

    def build_figure_matching_kwargs(
        self,
        *,
        normalize_text: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "normalize_text": normalize_text,
            "normalize_token_for_compare": normalize_token_for_compare,
        }


class ParserVisionTransportBootstrapRuntime:
    """Build vision transport runtimes so parser.py keeps only bootstrap sequencing."""

    def build_vision_transport_runtime_attrs(
        self,
        *,
        parser_vision_bundle_runtime: Any,
        normalize_text: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
        vision_dpi: int,
        vision_max_side_px: int,
        vision_model: str,
        vision_base_url: str,
        vision_endpoint_style: str,
        vision_timeout_sec: float,
        vision_max_output_tokens: int,
        resolve_api_key: RuntimeCallback,
    ) -> Dict[str, Any]:
        vision_response_runtime = VisionResponseRuntime(
            **parser_vision_bundle_runtime.build_vision_response_kwargs(
                normalize_text=normalize_text,
            )
        )
        vision_request_runtime = VisionRequestRuntime(
            **parser_vision_bundle_runtime.build_vision_request_kwargs(
                vision_dpi=vision_dpi,
                vision_max_side_px=vision_max_side_px,
                vision_model=vision_model,
                vision_base_url=vision_base_url,
                vision_endpoint_style=vision_endpoint_style,
                vision_timeout_sec=vision_timeout_sec,
                vision_max_output_tokens=vision_max_output_tokens,
                resolve_api_key=resolve_api_key,
                extract_json_object=vision_response_runtime.extract_json_object,
            )
        )
        figure_matching_runtime = FigureMatchingRuntime(
            **parser_vision_bundle_runtime.build_figure_matching_kwargs(
                normalize_text=normalize_text,
                normalize_token_for_compare=normalize_token_for_compare,
            )
        )
        return {
            "_vision_response_runtime": vision_response_runtime,
            "_vision_request_runtime": vision_request_runtime,
            "_figure_matching_runtime": figure_matching_runtime,
        }
