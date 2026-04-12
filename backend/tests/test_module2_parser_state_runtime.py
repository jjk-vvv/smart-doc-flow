from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


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


parser_state_runtime_module = _load_module(
    ["module2", "app", "core", "parsers", "parser_state_runtime.py"],
    "_smart_doc_flow_module2_parser_state_runtime",
)

ParserStateRuntime = parser_state_runtime_module.ParserStateRuntime


def test_parser_state_runtime_builds_visual_parse_state() -> None:
    state = ParserStateRuntime.build_visual_parse_state(
        {
            "stats": {"visual_mode": True},
            "figure_blocks": [{"figure_id": "f1"}],
            "result": ("visual_md", {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}]),
        }
    )

    assert state == {
        "stats": {"visual_mode": True},
        "figure_blocks": [{"figure_id": "f1"}],
        "result": ("visual_md", {"p1_c1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}]),
    }


def test_parser_state_runtime_builds_pdf_runtime_state_for_visual_result() -> None:
    state = ParserStateRuntime.build_pdf_runtime_state(
        runtime_outcome={
            "kind": "visual_result",
            "result": ("visual_md", {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]}, []),
            "stats": {"pipeline": "visual_first"},
            "stats_patch": {"source_cache_identity_applied": True},
        },
        current_stats={"visual_mode": True},
    )

    assert state == {
        "stats": {
            "visual_mode": True,
            "pipeline": "visual_first",
            "source_cache_identity_applied": True,
        },
        "figure_blocks": None,
        "result": ("visual_md", {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]}, []),
    }


def test_parser_state_runtime_builds_pdf_runtime_state_for_native_early_result() -> None:
    state = ParserStateRuntime.build_pdf_runtime_state(
        runtime_outcome={
            "kind": "native_early_result",
            "result": ("early_md", {}, []),
        },
        current_stats={"keep": True},
    )

    assert state == {
        "stats": None,
        "figure_blocks": None,
        "result": ("early_md", {}, []),
    }


def test_parser_state_runtime_builds_pdf_runtime_state_for_native_result() -> None:
    state = ParserStateRuntime.build_pdf_runtime_state(
        runtime_outcome={
            "kind": "native_result",
            "result": ("native_md", {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}]),
            "stats": {"native_mode": True},
            "stats_patch": {"fallback_reason": "no_layout"},
            "figure_blocks": [{"figure_id": "f1"}],
        },
        current_stats={"ignored": True},
    )

    assert state == {
        "stats": {"native_mode": True, "fallback_reason": "no_layout"},
        "figure_blocks": [{"figure_id": "f1"}],
        "result": ("native_md", {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}]),
    }


def test_parser_state_runtime_raises_when_pdf_runtime_returns_no_result() -> None:
    with pytest.raises(ValueError, match="PDF parse runtime returned no result."):
        ParserStateRuntime.build_pdf_runtime_state(
            runtime_outcome={"kind": "native_result", "result": None},
            current_stats={},
        )


def test_parser_state_runtime_builds_named_runtime_state() -> None:
    state = ParserStateRuntime.build_named_runtime_state(
        {
            "markdown": "docx_md",
            "bbox_map": {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]},
            "table_blocks": [{"table_id": "t1"}],
            "stats": {"docx_mode": True},
            "figure_blocks": [{"figure_id": "f1"}],
        }
    )

    assert state == {
        "stats": {"docx_mode": True},
        "figure_blocks": [{"figure_id": "f1"}],
        "result": ("docx_md", {"p1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "t1"}]),
    }


def test_parser_state_runtime_builds_named_runtime_state_without_stats() -> None:
    state = ParserStateRuntime.build_named_runtime_state(
        {
            "markdown": "image_md",
            "bbox_map": {},
            "table_blocks": [],
            "figure_blocks": [{"figure_id": "f1"}],
        },
        include_stats=False,
    )

    assert state == {
        "stats": None,
        "figure_blocks": [{"figure_id": "f1"}],
        "result": ("image_md", {}, []),
    }


def test_parser_state_runtime_builds_xlsx_state() -> None:
    state = ParserStateRuntime.build_xlsx_state(
        markdown="xlsx_md",
        bbox_map={"sheet1": [1.0, 0.0, 0.0, 1.0, 1.0]},
        table_blocks=[{"table_id": "xlsx_t1"}],
        used_zip_fallback=1,
    )

    assert state == {
        "stats": {"xlsx_zip_fallback": True},
        "figure_blocks": [],
        "result": ("xlsx_md", {"sheet1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "xlsx_t1"}]),
    }


def test_parser_state_runtime_builds_plain_text_state() -> None:
    plain_result = SimpleNamespace(
        text="plain body",
        markdown="plain_md",
        bbox_map={"text_1": [1.0, 0.0, 0.0, 1.0, 1.0]},
        table_blocks=[{"table_id": "plain_t1"}],
        figure_blocks=[{"figure_id": "plain_f1"}],
    )

    state = ParserStateRuntime.build_plain_text_state(
        ext=".md",
        plain_result=plain_result,
        merged_figure_blocks=[{"figure_id": "merged_f1"}],
    )

    assert state == {
        "stats": {
            "plain_ext": ".md",
            "plain_text_chars": 10,
            "plain_ref_count": 1,
            "plain_table_count": 1,
            "plain_figure_count": 1,
        },
        "figure_blocks": [{"figure_id": "merged_f1"}],
        "result": ("plain_md", {"text_1": [1.0, 0.0, 0.0, 1.0, 1.0]}, [{"table_id": "plain_t1"}]),
    }
