from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

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


image_document_runtime_module = _load_module(
    ["module2", "app", "core", "format", "image_document_runtime.py"],
    "_smart_doc_flow_module2_image_document_runtime",
)

ImageDocumentRuntime = image_document_runtime_module.ImageDocumentRuntime


class _FakeDoc:
    def __init__(self) -> None:
        self.opened = True


def test_image_document_runtime_requires_backend_or_gemini() -> None:
    runtime = ImageDocumentRuntime(
        enable_gemini_vision_enhance=True,
        visual_backend_available=lambda: (False, "pymupdf, rapidocr-onnxruntime"),
        resolve_api_key=lambda: "",
        get_ocr_engine=lambda: object(),
        collect_page_ocr=lambda **kwargs: ([], {}, {}, {}),
        build_parse_result=lambda **kwargs: ([], []),
    )

    with pytest.raises(ValueError, match="Image OCR backend is unavailable. Please install: pymupdf, rapidocr-onnxruntime"):
        runtime.parse_image(
            file_name="demo.png",
            file_bytes=b"fake",
            last_figure_blocks=[],
        )


def test_image_document_runtime_runs_vision_only_path_without_visual_backend(monkeypatch) -> None:
    fake_doc = _FakeDoc()
    monkeypatch.setitem(
        sys.modules,
        "fitz",
        types.SimpleNamespace(
            open=lambda **kwargs: fake_doc,
            Matrix=lambda x, y: ("matrix", x, y),
        ),
    )

    state: dict[str, object] = {}
    runtime = ImageDocumentRuntime(
        enable_gemini_vision_enhance=True,
        visual_backend_available=lambda: (False, "rapidocr-onnxruntime"),
        resolve_api_key=lambda: "valid-key",
        get_ocr_engine=lambda: state.update(engine_requested=True) or object(),
        collect_page_ocr=lambda **kwargs: (
            ['<ref id="img_p1_vision_probe">probe</ref>'],
            {"img_p1_vision_probe": [1.0, 0.0, 0.0, 1.0, 1.0]},
            {1: ["probe"]},
            {},
        ),
        build_parse_result=lambda **kwargs: (
            [{"table_id": "image_gemini_vision_t1"}],
            [{"figure_id": "image_gemini_vision_f1"}],
        ),
    )

    result = runtime.parse_image(
        file_name="demo.png",
        file_bytes=b"fake",
        last_figure_blocks=[],
    )

    assert "engine_requested" not in state
    assert result["markdown"] == '<ref id="img_p1_vision_probe">probe</ref>'
    assert result["table_blocks"] == [{"table_id": "image_gemini_vision_t1"}]
    assert result["figure_blocks"] == [{"figure_id": "image_gemini_vision_f1"}]


def test_image_document_runtime_raises_when_visual_ocr_extracts_no_text(monkeypatch) -> None:
    fake_doc = _FakeDoc()
    monkeypatch.setitem(
        sys.modules,
        "fitz",
        types.SimpleNamespace(
            open=lambda **kwargs: fake_doc,
            Matrix=lambda x, y: ("matrix", x, y),
        ),
    )
    monkeypatch.setitem(sys.modules, "numpy", types.SimpleNamespace())

    runtime = ImageDocumentRuntime(
        enable_gemini_vision_enhance=True,
        visual_backend_available=lambda: (True, ""),
        resolve_api_key=lambda: "",
        get_ocr_engine=lambda: object(),
        collect_page_ocr=lambda **kwargs: ([], {}, {}, {}),
        build_parse_result=lambda **kwargs: ([], []),
    )

    with pytest.raises(ValueError, match="Image OCR completed but no text was extracted."):
        runtime.parse_image(
            file_name="demo.png",
            file_bytes=b"fake",
            last_figure_blocks=[],
        )
