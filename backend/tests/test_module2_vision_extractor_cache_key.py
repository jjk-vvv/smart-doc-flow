from __future__ import annotations

from importlib import import_module


vision_extractor_module = import_module("app.modules.module2.core.visual.vision_extractor")

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
