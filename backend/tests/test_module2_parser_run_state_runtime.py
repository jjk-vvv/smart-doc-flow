from __future__ import annotations

import importlib.util
import sys
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


parser_run_state_runtime_module = _load_module(
    ["module2", "app", "core", "parsers", "parser_state_runtime.py"],
    "_smart_doc_flow_module2_parser_run_state_runtime",
)

ParserRunStateRuntime = parser_run_state_runtime_module.ParserRunStateRuntime


def test_parser_run_state_runtime_resets_and_tracks_runtime_page_count() -> None:
    runtime = ParserRunStateRuntime()
    runtime.set_runtime_page_count(5)
    runtime.set_last_figure_blocks([{"figure_id": "f1"}])
    runtime.overlay_last_parse_stats({"mode": "visual"})
    runtime.set_last_mineru_run_meta({"backend": "mineru"})

    runtime.reset()

    assert runtime.runtime_page_count() == 0
    assert runtime.get_last_figure_blocks() == []
    assert runtime.get_last_parse_stats() == {}


def test_parser_run_state_runtime_applies_and_overlays_stats_with_existing_precedence_rules() -> None:
    runtime = ParserRunStateRuntime()
    runtime.overlay_last_parse_stats({"existing": 1, "keep": "yes"})
    runtime.apply_runtime_stats_patch({"existing": 2, "new": 3})

    assert runtime.get_last_parse_stats() == {
        "existing": 1,
        "new": 3,
        "keep": "yes",
    }

    runtime.overlay_last_parse_stats({"existing": 4, "overlay": True})

    assert runtime.get_last_parse_stats() == {
        "existing": 4,
        "new": 3,
        "keep": "yes",
        "overlay": True,
    }


def test_parser_run_state_runtime_applies_state_update_and_exports_parse_stats() -> None:
    runtime = ParserRunStateRuntime()
    result = runtime.apply_state_update(
        {
            "stats": {"native_mode": True},
            "figure_blocks": [{"figure_id": "f2"}],
            "result": ("md", {"r1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}]),
        }
    )
    runtime.set_last_mineru_run_meta({"page_count": 3})

    assert result == ("md", {"r1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}])
    assert runtime.get_last_figure_blocks() == [{"figure_id": "f2"}]
    assert runtime.get_last_parse_stats() == {
        "native_mode": True,
        "mineru_run": {"page_count": 3},
    }


def test_parser_run_state_runtime_returns_none_when_state_update_has_no_result() -> None:
    runtime = ParserRunStateRuntime()

    assert runtime.apply_state_update({"stats": {"a": 1}, "figure_blocks": [], "result": None}) is None
