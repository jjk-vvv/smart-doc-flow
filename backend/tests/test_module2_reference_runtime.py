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


reference_module = _load_module(
    ["module2", "app", "core", "schema", "reference_runtime.py"],
    "_smart_doc_flow_module2_reference_runtime",
)

ReferenceRuntime = reference_module.ReferenceRuntime


def test_reference_runtime_appends_escaped_ref_once() -> None:
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    ReferenceRuntime.append_ref(parts, bbox_map, "ref_1", "<alpha>", [1, 0.1, 0.2, 0.3, 0.4, 9])
    ReferenceRuntime.append_ref(parts, bbox_map, "ref_1", "ignored", [9, 9, 9, 9, 9])

    assert parts == ['<ref id="ref_1">&lt;alpha&gt;</ref>']
    assert bbox_map == {"ref_1": [1.0, 0.1, 0.2, 0.3, 0.4]}
