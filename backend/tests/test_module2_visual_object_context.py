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


visual_planning_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_planning_runtime.py"],
    "_smart_doc_flow_module2_visual_planning_runtime_for_object_context",
)

VisualObjectContextRuntime = visual_planning_module.VisualObjectContextRuntime


def _build_runtime(*, max_chars: int = 40) -> VisualObjectContextRuntime:
    return VisualObjectContextRuntime(
        visual_context_max_chars=max_chars,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        safe_text_list=lambda values, max_items=8, max_len=180: [
            str(item)[:max_len]
            for item in (values if isinstance(values, list) else ([values] if values else []))
        ][:max_items],
    )


def test_visual_object_context_runtime_builds_context_and_truncates_page_text() -> None:
    runtime = _build_runtime(max_chars=20)

    result = runtime.build_visual_object_context(
        file_name="economic-report.pdf",
        page_no=2,
        object_type="table",
        item={
            "caption": ["GDP by region"],
            "footnote": ["statistical bulletin"],
            "object_subtype": "table",
        },
        page_lines={2: ["economic statistical bulletin data with many extra words for truncation"]},
    )

    assert result["doc_name"] == "economic-report.pdf"
    assert result["page"] == 2
    assert result["artifact_subtype"] == "table"
    assert result["caption_hint"] == "GDP by region"
    assert len(result["nearby_text"]) == 20
    assert any("structured numeric fields" in hint for hint in result["domain_hints"])


def test_visual_object_context_runtime_adds_formula_preservation_hints() -> None:
    runtime = _build_runtime()

    result = runtime.build_visual_object_context(
        file_name="chem.pdf",
        page_no=1,
        object_type="figure",
        item={
            "caption": ["compound figure"],
            "footnote": ["reagent notes"],
            "object_subtype": "formula",
        },
        page_lines={1: ["chem reagent context"]},
    )

    assert result["artifact_subtype"] == "formula"
    assert any("chemical formulas verbatim" in hint for hint in result["domain_hints"])
    assert any("Do not paraphrase formulas into prose" in hint for hint in result["domain_hints"])


def test_visual_object_context_runtime_infers_nuclear_domain_hints() -> None:
    runtime = _build_runtime()

    hints = runtime.infer_domain_hints("nuclear reactor isotope table")

    assert any("nuclide and isotope notation" in hint for hint in hints)
    assert any("scientific notation unchanged" in hint for hint in hints)
