from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _ensure_package(name: str) -> None:
    if name in sys.modules:
        return
    module = types.ModuleType(name)
    module.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = module


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part

    _ensure_package("_smart_doc_flow_module2")
    _ensure_package("_smart_doc_flow_module2.core")
    _ensure_package("_smart_doc_flow_module2.core.visual")
    _ensure_package("_smart_doc_flow_module2.core.integration")

    llm_provider_module = types.ModuleType("_smart_doc_flow_module2.core.llm_provider")
    llm_provider_module.resolve_llm_native_api_url = lambda *args, **kwargs: ""
    sys.modules["_smart_doc_flow_module2.core.llm_provider"] = llm_provider_module

    transport_module = types.ModuleType(
        "_smart_doc_flow_module2.core.integration.gemini_native_transport_runtime"
    )

    class _FakeGeminiNativeTransportRuntime:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def build_google_native_url(self, model: str) -> str:
            return ""

        def apply_model_to_native_url(self, url: str, model: str) -> str:
            return url

        def build_headers(self, api_key: str) -> dict[str, str]:
            return {}

    transport_module.GeminiNativeTransportRuntime = _FakeGeminiNativeTransportRuntime
    sys.modules[
        "_smart_doc_flow_module2.core.integration.gemini_native_transport_runtime"
    ] = transport_module

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


vision_extractor_module = _load_module(
    ["module2", "app", "core", "visual", "vision_extractor.py"],
    "_smart_doc_flow_module2.core.visual.vision_extractor",
)

GeminiVisionExtractor = vision_extractor_module.GeminiVisionExtractor


def _build_figure_prompt(extractor, context: dict[str, object]) -> str:
    return (
        "Analyze one cropped image-like ROI from a PDF. The ROI may be a chart, diagram, photo, or generic figure.\n"
        f"Context:\n{extractor._compact_json(context, max_chars=2000)}"
    )


def test_vision_cache_key_is_stable_across_upload_file_names() -> None:
    extractor = GeminiVisionExtractor(
        api_key="test-key",
        cache_dir=None,
        enable_cache=True,
    )
    image_bytes = b"same-roi-image"
    context_a = {
        "doc_name": "i.pdf",
        "page": 3,
        "object_type": "figure",
        "artifact_subtype": "chart",
        "caption_hint": "2019-2021 sales chart",
        "footnote_hint": ["unit: revenue"],
        "nearby_text": "2019 2020 2021 revenue growth rate",
        "domain_hints": ["Treat percentage and year columns as structured numeric fields."],
    }
    context_b = {
        "doc_name": "i_d097acacb9318172.pdf",
        "page": 3,
        "object_type": "figure",
        "artifact_subtype": "chart",
        "caption_hint": "2019-2021 sales chart",
        "footnote_hint": ["unit: revenue"],
        "nearby_text": "2019 2020 2021 revenue growth rate",
        "domain_hints": ["Keep number formats exactly as shown."],
    }

    key_a = extractor._build_cache_key(
        mode="figure",
        prompt=_build_figure_prompt(extractor, context_a),
        image_bytes=image_bytes,
        context=context_a,
    )
    key_b = extractor._build_cache_key(
        mode="figure",
        prompt=_build_figure_prompt(extractor, context_b),
        image_bytes=image_bytes,
        context=context_b,
    )

    assert key_a == key_b


def test_vision_cache_key_still_changes_when_visible_context_changes() -> None:
    extractor = GeminiVisionExtractor(
        api_key="test-key",
        cache_dir=None,
        enable_cache=True,
    )
    base_context = {
        "doc_name": "i.pdf",
        "page": 3,
        "object_type": "figure",
        "artifact_subtype": "chart",
        "caption_hint": "2019-2021 sales chart",
        "footnote_hint": ["unit: revenue"],
        "nearby_text": "2019 2020 2021 revenue growth rate",
        "domain_hints": ["Treat percentage and year columns as structured numeric fields."],
    }
    changed_context = {
        **base_context,
        "nearby_text": "2019 2020 2021 gross margin net margin profit rate",
    }

    key_a = extractor._build_cache_key(
        mode="figure",
        prompt=_build_figure_prompt(extractor, base_context),
        image_bytes=b"same-roi-image",
        context=base_context,
    )
    key_b = extractor._build_cache_key(
        mode="figure",
        prompt=_build_figure_prompt(extractor, changed_context),
        image_bytes=b"same-roi-image",
        context=changed_context,
    )

    assert key_a != key_b
