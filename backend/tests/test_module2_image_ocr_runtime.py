from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


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


image_ocr_runtime_module = _load_module(
    ["module2", "app", "core", "format", "image_document_runtime.py"],
    "_smart_doc_flow_module2_image_document_runtime_for_ocr",
)

ImageOcrRuntime = image_ocr_runtime_module.ImageOcrRuntime


class _FakeArray:
    def reshape(self, *shape):
        return self

    def __getitem__(self, key):
        return self


class _FakeNumpy:
    uint8 = "uint8"

    @staticmethod
    def frombuffer(*args, **kwargs):
        return _FakeArray()


class _FakePixmap:
    def __init__(self, *, width: int = 8, height: int = 8, n: int = 1):
        self.width = width
        self.height = height
        self.n = n
        self.samples = b"\x00" * (width * height * n)


class _FakePage:
    def __init__(self, *, pixmap_n: int = 1):
        self._pixmap_n = pixmap_n

    def get_pixmap(self, matrix=None, alpha: bool = False):
        return _FakePixmap(n=self._pixmap_n)


class _FakeDoc:
    def __init__(self, pages: list[_FakePage]):
        self._pages = pages
        self.closed = False

    def __len__(self):
        return len(self._pages)

    def load_page(self, page_idx: int):
        return self._pages[page_idx]

    def close(self):
        self.closed = True


def _build_runtime(state: dict[str, Any]) -> ImageOcrRuntime:
    def _set_runtime_page_count(page_count: int) -> None:
        state["runtime_page_count"] = page_count

    def _append_ref(parts, bbox_map, ref_id, text, bbox) -> None:
        parts.append(f'<ref id="{ref_id}">{text}</ref>')
        bbox_map[ref_id] = [float(item) for item in bbox[:5]]

    return ImageOcrRuntime(
        max_pages_visual=4,
        set_runtime_page_count=_set_runtime_page_count,
        append_ref=_append_ref,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        normalize_box=lambda box, width, height: (0.1, 0.2, 0.3, 0.4),
    )


def test_image_ocr_runtime_emits_vision_probe_placeholder_without_visual_backend() -> None:
    state: dict[str, Any] = {}
    runtime = _build_runtime(state)
    doc = _FakeDoc([_FakePage()])

    parts, bbox_map, page_lines, page_cells = runtime.collect_page_ocr(
        doc=doc,
        np_module=None,
        mat={"scale": 1.0},
        engine=None,
        min_conf=0.45,
        visual_backend_ready=False,
    )

    assert state["runtime_page_count"] == 1
    assert doc.closed is True
    assert parts == ['<ref id="img_p1_vision_probe">[Image page 1] OCR backend unavailable, trying Gemini Vision.</ref>']
    assert bbox_map["img_p1_vision_probe"] == [1.0, 0.0, 0.0, 1.0, 1.0]
    assert page_lines == {1: ["[Image page 1] OCR backend unavailable, trying Gemini Vision."]}
    assert page_cells == {}


def test_image_ocr_runtime_collects_ocr_lines_and_cells() -> None:
    state: dict[str, Any] = {}
    runtime = _build_runtime(state)
    doc = _FakeDoc([_FakePage(pixmap_n=4)])

    class _FakeEngine:
        def __call__(self, image):
            return (
                [
                    ([[0, 0], [1, 0], [1, 1], [0, 1]], " Revenue ", 0.96),
                    ([[0, 1], [1, 1], [1, 2], [0, 2]], " 2024 ", 0.93),
                    ([[0, 2], [1, 2], [1, 3], [0, 3]], "", 0.99),
                ],
                None,
            )

    parts, bbox_map, page_lines, page_cells = runtime.collect_page_ocr(
        doc=doc,
        np_module=_FakeNumpy(),
        mat={"scale": 1.0},
        engine=_FakeEngine(),
        min_conf=0.45,
        visual_backend_ready=True,
    )

    assert state["runtime_page_count"] == 1
    assert doc.closed is True
    assert '<ref id="img_p1_ocr1">Revenue</ref>' in parts
    assert '<ref id="img_p1_ocr2">2024</ref>' in parts
    assert bbox_map["img_p1_ocr1"] == [1.0, 0.1, 0.2, 0.3, 0.4]
    assert page_lines == {1: ["Revenue", "2024"]}
    assert len(page_cells[1]) == 2
    assert page_cells[1][0]["x_center"] == 0.25
    assert page_cells[1][0]["y_center"] == 0.4


def test_image_ocr_runtime_emits_no_text_placeholder_when_ocr_result_empty() -> None:
    state: dict[str, Any] = {}
    runtime = _build_runtime(state)
    doc = _FakeDoc([_FakePage()])

    class _FakeEngine:
        def __call__(self, image):
            return ([], None)

    parts, bbox_map, page_lines, page_cells = runtime.collect_page_ocr(
        doc=doc,
        np_module=_FakeNumpy(),
        mat={"scale": 1.0},
        engine=_FakeEngine(),
        min_conf=0.45,
        visual_backend_ready=True,
    )

    assert doc.closed is True
    assert parts == ['<ref id="img_p1_ocr1">[Image page 1] OCR found no text.</ref>']
    assert bbox_map["img_p1_ocr1"] == [1.0, 0.0, 0.0, 1.0, 1.0]
    assert page_lines == {}
    assert page_cells == {}
