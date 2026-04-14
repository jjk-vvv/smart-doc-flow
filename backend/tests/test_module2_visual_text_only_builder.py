from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


visual_text_only_builder_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_parse_orchestrator.py"],
    "_smart_doc_flow_module2_visual_text_only_builder",
)

VisualTextOnlyBuilderRuntime = visual_text_only_builder_module.VisualTextOnlyBuilderRuntime


def _build_runtime(*, min_chars: int = 20) -> VisualTextOnlyBuilderRuntime:
    return VisualTextOnlyBuilderRuntime(
        visual_text_only_min_chars=min_chars,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        append_ref=lambda parts, bbox_map, ref_id, text, bbox: (
            parts.append(f'<ref id="{ref_id}">{text}</ref>'),
            bbox_map.__setitem__(ref_id, [float(x) for x in bbox[:5]]),
        ),
        split_page_text=lambda text: [part for part in str(text).split("\n\n") if part],
        build_visual_parse_status_fields=lambda **kwargs: {
            "status_marker": kwargs["visual_mode"],
            "visual_text_char_count_status": kwargs["text_char_count"],
        },
    )


def test_visual_text_only_builder_runtime_builds_text_only_result() -> None:
    runtime = _build_runtime(min_chars=5)

    result = runtime.build_result(
        page_lines={1: ["Alpha line", "Beta line"], 2: []},
        page_count=2,
        visual_t0=time.perf_counter(),
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        failure_reason="no_selected_objects",
        layout_object_count=3,
        mineru_run_meta={"status": "ok"},
        select_ms=13,
        object_selection_stats={"visual_selected_object_count": 0},
        extra_stats={"visual_pdf_profile": "mixed_visual_pdf"},
        runtime_limits={"profile": "default"},
    )

    assert result is not None
    markdown, bbox_map, table_blocks, stats = result
    assert '<ref id="p1_c1">' in markdown
    assert '<ref id="p2_c1">' in markdown
    assert "p1_c1" in bbox_map
    assert table_blocks == []
    assert stats["visual_mode"] == "text_only"
    assert stats["visual_text_only_recovery"] == "no_selected_objects"
    assert stats["status_marker"] == "text_only"
    assert stats["mineru_run"] == {"status": "ok"}


def test_visual_text_only_builder_runtime_returns_none_when_text_is_too_short_and_mineru_failed() -> None:
    runtime = _build_runtime(min_chars=50)

    result = runtime.build_result(
        page_lines={1: ["short"]},
        page_count=1,
        visual_t0=time.perf_counter(),
        layout_extract_ms=10,
        native_context_ms=11,
        merge_context_ms=12,
        failure_reason="no_layout_objects",
        layout_object_count=0,
        mineru_run_meta={"status": "failed"},
    )

    assert result is None
