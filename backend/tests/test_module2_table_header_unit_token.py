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


table_header_module = _load_module(
    ["app", "modules", "module2", "core", "table", "table_header_runtime.py"],
    "_smart_doc_flow_module2_table_header_unit_token_runtime",
)

TableHeaderRuntime = table_header_module.TableHeaderRuntime


def test_table_header_runtime_detects_unit_like_tokens_without_parser_callback() -> None:
    assert TableHeaderRuntime.is_unit_like_token("kg") is True
    assert TableHeaderRuntime.is_unit_like_token("(mg/L)") is True
    assert TableHeaderRuntime.is_unit_like_token("ppm") is True
    assert TableHeaderRuntime.is_unit_like_token("Annual total") is False
