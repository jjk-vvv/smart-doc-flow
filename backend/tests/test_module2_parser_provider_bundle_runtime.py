from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_provider_bundle_runtime_module = import_module("module2.app.core.parsers.parser_bootstrap_runtime")

ParserProviderBundleRuntime = parser_provider_bundle_runtime_module.ParserProviderBundleRuntime


def test_parser_provider_bundle_runtime_builds_mineru_layout_kwargs() -> None:
    runtime = ParserProviderBundleRuntime()

    kwargs = runtime.build_mineru_layout_kwargs(
        backend="pipeline",
        method="auto",
        timeout_sec=1800,
        cache_dir="cache/mineru",
        enable_cache=True,
        enable_formula=False,
        enable_table=False,
        device="cuda",
        method_fallbacks="auto,ocr,txt",
    )

    assert kwargs == {
        "backend": "pipeline",
        "method": "auto",
        "timeout_sec": 1800,
        "cache_dir": "cache/mineru",
        "enable_cache": True,
        "enable_formula": False,
        "enable_table": False,
        "device": "cuda",
        "method_fallbacks": "auto,ocr,txt",
    }


def test_parser_provider_bundle_runtime_builds_roi_cropper_kwargs() -> None:
    runtime = ParserProviderBundleRuntime()

    kwargs = runtime.build_roi_cropper_kwargs(
        table_dpi=260,
        figure_dpi=220,
        expand_ratio=0.03,
        max_side_px=2800,
    )

    assert kwargs == {
        "table_dpi": 260,
        "figure_dpi": 220,
        "expand_ratio": 0.03,
        "max_side_px": 2800,
    }


def test_parser_provider_bundle_runtime_builds_visual_vision_kwargs() -> None:
    runtime = ParserProviderBundleRuntime()

    kwargs = runtime.build_visual_vision_kwargs(
        api_key="openai-key",
        native_api_key="AIza-native-key",
        model="gemini-2.5-flash",
        timeout_sec=25.0,
        max_output_tokens=4096,
        retry_count=2,
        cache_dir="cache/gemini",
        enable_cache=True,
        reasoning_effort="medium",
        native_fallback_enabled=True,
    )

    assert kwargs == {
        "api_key": "openai-key",
        "native_api_key": "AIza-native-key",
        "model": "gemini-2.5-flash",
        "timeout_sec": 25.0,
        "max_output_tokens": 4096,
        "retry_count": 2,
        "cache_dir": "cache/gemini",
        "enable_cache": True,
        "reasoning_effort": "medium",
        "native_fallback_enabled": True,
    }


def test_parser_provider_bundle_runtime_resolves_native_api_key_in_expected_priority_order() -> None:
    runtime = ParserProviderBundleRuntime()

    key = runtime.resolve_native_api_key(
        getenv=lambda name, default="": {
            "MODULE2_GEMINI_NATIVE_API_KEY": "",
            "GOOGLE_API_KEY": "AIza-google-priority",
            "GEMINI_API_KEY": "AIza-fallback",
        }.get(name, default),
    )

    assert key == "AIza-google-priority"


def test_parser_provider_bundle_runtime_reports_visual_backend_missing_packages() -> None:
    runtime = ParserProviderBundleRuntime()

    available, missing = runtime.visual_backend_available(find_spec=lambda name: None)

    assert available is False
    assert missing == "pymupdf, rapidocr-onnxruntime"
