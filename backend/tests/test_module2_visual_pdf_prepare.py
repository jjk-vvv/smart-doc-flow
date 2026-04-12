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


visual_pdf_prepare_module = _load_module(
    ["module2", "app", "core", "visual", "visual_pdf_bootstrap.py"],
    "_smart_doc_flow_module2_visual_pdf_prepare",
)

VisualPdfPrepareRuntime = visual_pdf_prepare_module.VisualPdfPrepareRuntime


class _FakeMediaBox:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class _FailingMediaBox:
    @property
    def width(self) -> float:
        raise RuntimeError("width unavailable")

    @property
    def height(self) -> float:
        raise RuntimeError("height unavailable")


class _FakePage:
    def __init__(
        self,
        text: str,
        *,
        width: float = 612.0,
        height: float = 792.0,
        broken_dims: bool = False,
        broken_text: bool = False,
    ) -> None:
        self._text = text
        self._broken_text = broken_text
        self.mediabox = _FailingMediaBox() if broken_dims else _FakeMediaBox(width, height)

    def extract_text(self) -> str:
        if self._broken_text:
            raise RuntimeError("extract failed")
        return self._text


class _FakeReader:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


def _build_runtime() -> VisualPdfPrepareRuntime:
    return VisualPdfPrepareRuntime(
        normalize_text=lambda text: " ".join(str(text or "").split()),
        split_page_text=lambda text: [part.strip() for part in str(text or "").split("##") if part.strip()],
        append_ref=lambda parts, bbox_map, ref_id, text, bbox: (
            parts.append(f'<ref id="{ref_id}">{text}</ref>'),
            bbox_map.__setitem__(ref_id, [float(x) for x in bbox[:5]]),
        ),
    )


def test_visual_pdf_prepare_runtime_builds_chunk_refs_from_native_text() -> None:
    runtime = _build_runtime()
    reader = _FakeReader([_FakePage("Alpha ## Beta ## Gamma")])

    prepared = runtime.prepare_context(reader=reader, page_count=1, mineru_page_lines={})
    bootstrapped = runtime.build_initial_refs(
        reader=reader,
        page_count=1,
        native_page_chunks=prepared["native_page_chunks"],
    )

    assert prepared["native_page_chunks"] == {1: ["Alpha", "Beta", "Gamma"]}
    assert len(bootstrapped["parts"]) == 3
    assert 'id="p1_c1"' in bootstrapped["parts"][0]
    assert 'id="p1_c2"' in bootstrapped["parts"][1]
    assert 'id="p1_c3"' in bootstrapped["parts"][2]
    assert bootstrapped["bbox_map"]["p1_c3"] == [1.0, 0.0, 0.0, 1.0, 1.0]


def test_visual_pdf_prepare_runtime_builds_placeholder_ref_for_empty_page() -> None:
    runtime = _build_runtime()
    reader = _FakeReader([_FakePage("")])

    prepared = runtime.prepare_context(reader=reader, page_count=1, mineru_page_lines={})
    bootstrapped = runtime.build_initial_refs(
        reader=reader,
        page_count=1,
        native_page_chunks=prepared["native_page_chunks"],
    )

    assert prepared["native_page_chunks"] == {}
    assert bootstrapped["parts"] == ['<ref id="p1_c1">[Page 1] No extractable native text.</ref>']
    assert bootstrapped["bbox_map"]["p1_c1"] == [1.0, 0.0, 0.0, 1.0, 1.0]


def test_visual_pdf_prepare_runtime_merges_and_dedupes_native_and_mineru_lines() -> None:
    runtime = _build_runtime()
    reader = _FakeReader([_FakePage("Revenue\nRevenue \nGross margin")])

    prepared = runtime.prepare_context(
        reader=reader,
        page_count=1,
        mineru_page_lines={1: [" Revenue", "Gross margin", "Visual hint"]},
    )

    assert prepared["native_page_lines"][1] == ["Revenue", "Revenue", "Gross margin"]
    assert prepared["page_lines"][1] == ["Revenue", "Gross margin", "Visual hint"]


def test_visual_pdf_prepare_runtime_falls_back_when_page_dimensions_fail() -> None:
    runtime = _build_runtime()
    reader = _FakeReader(
        [
            _FakePage("Alpha", width=500.0, height=700.0),
            _FakePage("Beta", broken_dims=True),
        ]
    )

    bootstrapped = runtime.build_initial_refs(
        reader=reader,
        page_count=2,
        native_page_chunks={1: ["Alpha"], 2: ["Beta"]},
    )

    assert bootstrapped["page_dims"][1] == (500.0, 700.0)
    assert bootstrapped["page_dims"][2] == (1.0, 1.0)
