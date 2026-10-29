from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_provider_bundle_runtime_module = import_module("app.modules.module2.core.parsers.parser_bootstrap_runtime")

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
        model="test-vision-model",
        base_url="https://provider.test/v1",
        endpoint_style="openai_chat_completions",
        timeout_sec=25.0,
        max_output_tokens=4096,
        retry_count=2,
        cache_dir="cache/vision",
        enable_cache=True,
        reasoning_effort="medium",
    )

    assert kwargs == {
        "api_key": "openai-key",
        "model": "test-vision-model",
        "base_url": "https://provider.test/v1",
        "endpoint_style": "openai_chat_completions",
        "timeout_sec": 25.0,
        "max_output_tokens": 4096,
        "retry_count": 2,
        "cache_dir": "cache/vision",
        "enable_cache": True,
        "reasoning_effort": "medium",
    }




def test_parser_provider_bundle_runtime_reports_visual_backend_missing_packages() -> None:
    runtime = ParserProviderBundleRuntime()

    available, missing = runtime.visual_backend_available(find_spec=lambda name: None)

    assert available is False
    assert missing == "pymupdf, rapidocr-onnxruntime"
