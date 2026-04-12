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


block_index_module = _load_module(
    ["module2", "app", "core", "pipeline", "block_index_runtime.py"],
    "_smart_doc_flow_module2_block_index_runtime",
)

BlockIndexRuntime = block_index_module.BlockIndexRuntime


def test_block_index_runtime_computes_next_table_index_from_suffix() -> None:
    table_blocks = [
        {"table_id": "pdf_gv_t2"},
        {"table_id": "pdf_gv_t7"},
        {"table_id": "other_t9"},
    ]

    assert BlockIndexRuntime.next_table_index(table_blocks, "pdf_gv_t") == 8


def test_block_index_runtime_computes_next_figure_index_from_suffix() -> None:
    figure_blocks = [
        {"figure_id": "pdf_gv_f1"},
        {"figure_id": "pdf_gv_f4"},
        {"figure_id": "pdf_gv_f12"},
    ]

    assert BlockIndexRuntime.next_figure_index(figure_blocks, "pdf_gv_f") == 13
