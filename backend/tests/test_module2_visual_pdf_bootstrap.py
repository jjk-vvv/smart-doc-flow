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


visual_pdf_bootstrap_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_pdf_bootstrap.py"],
    "_smart_doc_flow_module2_visual_pdf_bootstrap",
)

VisualPdfBootstrapRuntime = visual_pdf_bootstrap_module.VisualPdfBootstrapRuntime


class _FakePage:
    def __init__(self, text: str, *, broken: bool = False) -> None:
        self._text = text
        self._broken = broken

    def extract_text(self) -> str:
        if self._broken:
            raise RuntimeError("extract failed")
        return self._text


class _FakeReader:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages


class _FakeLayoutExtractor:
    def __init__(
        self,
        *,
        objects: list[dict[str, object]] | None = None,
        page_lines: dict[int, list[str]] | None = None,
        run_meta: dict[str, object] | None = None,
    ) -> None:
        self.objects = objects or []
        self.page_lines = page_lines or {}
        self.run_meta = run_meta or {"status": "ok"}
        self.calls: list[dict[str, object]] = []

    def extract_layout(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.objects, self.page_lines

    def get_last_run_meta(self) -> dict[str, object]:
        return self.run_meta


def _build_runtime(
    *,
    classify_profile,
    resolve_limits,
    summarize_metadata=None,
    visual_probe_pages: int = 5,
    visual_first_max_pages: int = 50,
    max_pages: int = 40,
    extreme_threshold: int = 20,
    office_cap: int = 6,
    mixed_cap: int = 8,
    docx_cap: int = 7,
) -> VisualPdfBootstrapRuntime:
    return VisualPdfBootstrapRuntime(
        visual_probe_pages=visual_probe_pages,
        visual_first_max_pages=visual_first_max_pages,
        max_pages=max_pages,
        mineru_method="auto",
        visual_runtime_extreme_doc_page_threshold=extreme_threshold,
        visual_runtime_office_text_layout_page_cap=office_cap,
        visual_runtime_mixed_text_layout_page_cap=mixed_cap,
        visual_runtime_extreme_doc_layout_page_cap=docx_cap,
        normalize_text=lambda text: " ".join(str(text or "").split()),
        summarize_pdf_metadata_signals=summarize_metadata or (lambda reader: {"office_like": False}),
        classify_pdf_visual_profile=classify_profile,
        resolve_visual_runtime_limits=resolve_limits,
    )


def test_visual_pdf_bootstrap_runtime_probes_text_and_extracts_layout() -> None:
    captured: dict[str, object] = {}

    def classify_profile(**kwargs):
        captured.update(kwargs)
        return {
            "profile": "mixed_visual_pdf",
            "reason": "configured_default",
            "method": "auto",
            "method_fallbacks": ["ocr"],
            "stop_on_usable_text": False,
            "page_count_cap": 4,
            "probe_chars_per_page": 4.0,
            "visual_cue_hits": 2,
            "office_like": False,
        }

    def resolve_limits(**kwargs):
        return {
            "profile": "default",
            "layout_page_count": kwargs["layout_page_count"],
            "object_count": len(kwargs["objects"]),
        }

    runtime = _build_runtime(classify_profile=classify_profile, resolve_limits=resolve_limits)
    reader = _FakeReader(
        [
            _FakePage("Alpha  beta"),
            _FakePage("Gamma"),
            _FakePage("ignored", broken=True),
            _FakePage("Delta"),
        ]
    )
    layout = _FakeLayoutExtractor(
        objects=[{"object_type": "table"}],
        page_lines={1: ["Mineru line"]},
        run_meta={"status": "ok", "engine": "mineru"},
    )

    result = runtime.bootstrap(
        file_name="report.pdf",
        file_bytes=b"%PDF-1.7",
        reader=reader,
        page_count=4,
        layout_extractor=layout,
        source_cache_identity="cache-key",
    )

    assert captured["probe_pages"] == 4
    assert captured["probe_chars"] == len("Alpha beta") + len("Gamma") + len("") + len("Delta")
    assert captured["probe_text"] == "Alpha beta\nGamma\nDelta"
    assert layout.calls[0]["end_page"] == 4
    assert layout.calls[0]["method"] == "auto"
    assert layout.calls[0]["method_fallbacks"] == ["ocr"]
    assert layout.calls[0]["source_cache_identity"] == "cache-key"
    assert result["native_page_count"] == 4
    assert result["mineru_page_lines"] == {1: ["Mineru line"]}
    assert result["runtime_limits"]["object_count"] == 1
    assert result["runtime_limits"]["visual_probe_chars"] == captured["probe_chars"]
    assert result["runtime_limits"]["visual_probe_pages"] == 4
    assert result["visual_method_stats"]["visual_pdf_profile"] == "mixed_visual_pdf"
    assert result["mineru_run_meta"] == {"status": "ok", "engine": "mineru"}


def test_visual_pdf_bootstrap_runtime_caps_office_text_layout_pages_for_extreme_docs() -> None:
    runtime = _build_runtime(
        classify_profile=lambda **kwargs: {
            "profile": "office_text_pdf",
            "reason": "office_pdf_strong_native_text",
            "method": "txt",
            "method_fallbacks": ["ocr"],
            "stop_on_usable_text": False,
            "page_count_cap": 30,
            "probe_chars_per_page": 30.0,
            "visual_cue_hits": 0,
            "office_like": True,
        },
        resolve_limits=lambda **kwargs: {"layout_page_count": kwargs["layout_page_count"]},
    )
    reader = _FakeReader([_FakePage("text")] * 30)
    layout = _FakeLayoutExtractor()

    result = runtime.bootstrap(
        file_name="office.pdf",
        file_bytes=b"%PDF-1.7",
        reader=reader,
        page_count=30,
        layout_extractor=layout,
    )

    assert layout.calls[0]["end_page"] == 6
    assert result["visual_method_stats"]["visual_layout_page_count"] == 6
    assert result["runtime_limits"]["layout_page_count"] == 6


def test_visual_pdf_bootstrap_runtime_caps_docx_source_layout_pages_for_extreme_docs() -> None:
    runtime = _build_runtime(
        classify_profile=lambda **kwargs: {
            "profile": "mixed_visual_pdf",
            "reason": "configured_default",
            "method": "auto",
            "method_fallbacks": ["txt"],
            "stop_on_usable_text": False,
            "page_count_cap": 50,
            "probe_chars_per_page": 18.0,
            "visual_cue_hits": 4,
            "office_like": False,
        },
        resolve_limits=lambda **kwargs: {"layout_page_count": kwargs["layout_page_count"]},
    )
    reader = _FakeReader([_FakePage("text")] * 50)
    layout = _FakeLayoutExtractor(run_meta={"status": "fallback"})

    result = runtime.bootstrap(
        file_name="visual.pdf",
        file_bytes=b"%PDF-1.7",
        reader=reader,
        page_count=50,
        layout_extractor=layout,
        source_file_name="report.docx",
    )

    assert layout.calls[0]["end_page"] == 7
    assert result["mineru_status"] == "fallback"
    assert result["visual_method_stats"]["visual_layout_page_count"] == 7
