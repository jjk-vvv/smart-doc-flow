from __future__ import annotations

from typing import Any, Callable, Dict

from ..visual.figure_semantics import FigureMatchingRuntime
from ..integration.gemini_native_transport_runtime import GeminiNativeTransportRuntime
from ..visual.vision_request_runtime import VisionRequestRuntime
from ..visual.vision_response_runtime import VisionResponseRuntime


RuntimeCallback = Callable[..., Any]


class ParserVisionBundleRuntime:
    """Build pure kwargs for parser-owned Gemini vision transport components."""

    def build_gemini_native_transport_kwargs(
        self,
        *,
        resolve_native_api_url: RuntimeCallback,
        user_agent: str,
        default_model: str,
    ) -> Dict[str, Any]:
        return {
            "resolve_native_api_url": resolve_native_api_url,
            "user_agent": user_agent,
            "default_model": default_model,
        }

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
        gemini_vision_dpi: int,
        gemini_vision_max_side_px: int,
        gemini_vision_model: str,
        gemini_vision_timeout_sec: float,
        gemini_vision_max_output_tokens: int,
        gemini_native_fallback_enabled: bool,
        resolve_api_key: RuntimeCallback,
        resolve_native_api_key: RuntimeCallback,
        resolve_native_url: RuntimeCallback,
        build_google_native_url: RuntimeCallback,
        build_headers: RuntimeCallback,
        extract_json_object: RuntimeCallback,
        extract_candidate_text: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "gemini_vision_dpi": gemini_vision_dpi,
            "gemini_vision_max_side_px": gemini_vision_max_side_px,
            "gemini_vision_model": gemini_vision_model,
            "gemini_vision_timeout_sec": gemini_vision_timeout_sec,
            "gemini_vision_max_output_tokens": gemini_vision_max_output_tokens,
            "gemini_native_fallback_enabled": gemini_native_fallback_enabled,
            "resolve_api_key": resolve_api_key,
            "resolve_native_api_key": resolve_native_api_key,
            "resolve_native_url": resolve_native_url,
            "build_google_native_url": build_google_native_url,
            "build_headers": build_headers,
            "extract_json_object": extract_json_object,
            "extract_candidate_text": extract_candidate_text,
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
    """Build Gemini vision transport runtimes so parser.py keeps only bootstrap sequencing."""

    def build_vision_transport_runtime_attrs(
        self,
        *,
        parser_vision_bundle_runtime: Any,
        resolve_native_api_url: RuntimeCallback,
        user_agent: str,
        default_model: str,
        normalize_text: RuntimeCallback,
        normalize_token_for_compare: RuntimeCallback,
        gemini_vision_dpi: int,
        gemini_vision_max_side_px: int,
        gemini_vision_model: str,
        gemini_vision_timeout_sec: float,
        gemini_vision_max_output_tokens: int,
        gemini_native_fallback_enabled: bool,
        resolve_api_key: RuntimeCallback,
        resolve_native_api_key: RuntimeCallback,
    ) -> Dict[str, Any]:
        gemini_native_transport_runtime = GeminiNativeTransportRuntime(
            **parser_vision_bundle_runtime.build_gemini_native_transport_kwargs(
                resolve_native_api_url=resolve_native_api_url,
                user_agent=user_agent,
                default_model=default_model,
            )
        )
        vision_response_runtime = VisionResponseRuntime(
            **parser_vision_bundle_runtime.build_vision_response_kwargs(
                normalize_text=normalize_text,
            )
        )
        vision_request_runtime = VisionRequestRuntime(
            **parser_vision_bundle_runtime.build_vision_request_kwargs(
                gemini_vision_dpi=gemini_vision_dpi,
                gemini_vision_max_side_px=gemini_vision_max_side_px,
                gemini_vision_model=gemini_vision_model,
                gemini_vision_timeout_sec=gemini_vision_timeout_sec,
                gemini_vision_max_output_tokens=gemini_vision_max_output_tokens,
                gemini_native_fallback_enabled=gemini_native_fallback_enabled,
                resolve_api_key=resolve_api_key,
                resolve_native_api_key=resolve_native_api_key,
                resolve_native_url=gemini_native_transport_runtime.resolve_native_url,
                build_google_native_url=gemini_native_transport_runtime.build_google_native_url,
                build_headers=gemini_native_transport_runtime.build_headers,
                extract_json_object=vision_response_runtime.extract_json_object,
                extract_candidate_text=vision_response_runtime.extract_candidate_text,
            )
        )
        figure_matching_runtime = FigureMatchingRuntime(
            **parser_vision_bundle_runtime.build_figure_matching_kwargs(
                normalize_text=normalize_text,
                normalize_token_for_compare=normalize_token_for_compare,
            )
        )
        return {
            "_gemini_native_transport_runtime": gemini_native_transport_runtime,
            "_vision_response_runtime": vision_response_runtime,
            "_vision_request_runtime": vision_request_runtime,
            "_figure_matching_runtime": figure_matching_runtime,
        }
