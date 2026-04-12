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


vision_response_module = _load_module(
    ["module2", "app", "core", "visual", "vision_response_runtime.py"],
    "_smart_doc_flow_module2_vision_response_runtime",
)

VisionResponseRuntime = vision_response_module.VisionResponseRuntime


def _build_runtime() -> VisionResponseRuntime:
    return VisionResponseRuntime(
        normalize_text=lambda text: " ".join(str(text or "").split()),
    )


def test_vision_response_runtime_extracts_candidate_text_from_generate_response() -> None:
    raw = """
    {
      "candidates": [
        {
          "content": {
            "parts": [
              {"text": "first"},
              {"text": "second"}
            ]
          }
        }
      ]
    }
    """

    assert VisionResponseRuntime.extract_candidate_text(raw) == "first\nsecond"


def test_vision_response_runtime_extracts_json_object_from_fenced_or_embedded_text() -> None:
    payload = _build_runtime().extract_json_object(
        '```json\n{"tables":[],"insights":["alpha"]}\n```\nextra ignored'
    )
    embedded = _build_runtime().extract_json_object(
        'prefix text {"figures":[{"caption":"ok"}],"insights":["beta"]} suffix'
    )

    assert payload == {"tables": [], "insights": ["alpha"]}
    assert embedded == {"figures": [{"caption": "ok"}], "insights": ["beta"]}


def test_vision_response_runtime_extracts_vision_insights_and_skips_existing_refs() -> None:
    runtime = _build_runtime()
    result = runtime.extract_vision_insights(
        payload={"insights": ["  first insight  ", "", "third insight"]},
        page_no=2,
        bbox_map={"gv_p2_s1": [2.0, 0.0, 0.0, 1.0, 1.0]},
        max_insights=4,
    )

    assert result == [("gv_p2_s3", "third insight")]
