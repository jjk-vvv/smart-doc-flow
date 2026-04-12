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


ocr_engine_runtime_module = _load_module(
    ["module2", "app", "core", "pdf", "ocr_engine_runtime.py"],
    "_smart_doc_flow_module2_ocr_engine_runtime",
)

OcrEngineRuntime = ocr_engine_runtime_module.OcrEngineRuntime


@pytest.fixture(autouse=True)
def _reset_ocr_engine_runtime() -> None:
    OcrEngineRuntime.reset()
    yield
    OcrEngineRuntime.reset()


def test_ocr_engine_runtime_caches_successful_engine(monkeypatch) -> None:
    state = {"calls": 0}
    sentinel = object()

    def _build_engine():
        state["calls"] += 1
        return sentinel

    monkeypatch.setitem(
        sys.modules,
        "rapidocr_onnxruntime",
        types.SimpleNamespace(RapidOCR=_build_engine),
    )

    first = OcrEngineRuntime.get_ocr_engine()
    second = OcrEngineRuntime.get_ocr_engine()

    assert first is sentinel
    assert second is sentinel
    assert state["calls"] == 1


def test_ocr_engine_runtime_caches_init_error(monkeypatch) -> None:
    state = {"calls": 0}

    def _raise_engine_error():
        state["calls"] += 1
        raise RuntimeError("boom")

    monkeypatch.setitem(
        sys.modules,
        "rapidocr_onnxruntime",
        types.SimpleNamespace(RapidOCR=_raise_engine_error),
    )
    monkeypatch.setenv("MODULE2_OCR_ENGINE_INIT_TIMEOUT_SEC", "2")

    with pytest.raises(RuntimeError, match="OCR engine init failed within 2.0s: RuntimeError: boom"):
        OcrEngineRuntime.get_ocr_engine()

    with pytest.raises(RuntimeError, match="OCR engine init failed within 2.0s: RuntimeError: boom"):
        OcrEngineRuntime.get_ocr_engine()

    assert state["calls"] == 1
