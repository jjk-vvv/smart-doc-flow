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


pdf_visual_profile_module = _load_module(
    ["module2", "app", "core", "pdf", "pdf_visual_profile.py"],
    "_smart_doc_flow_module2_pdf_visual_profile",
)

PdfVisualProfileRuntime = pdf_visual_profile_module.PdfVisualProfileRuntime


class _FakeReader:
    def __init__(self, metadata: dict[str, str] | None = None) -> None:
        self.metadata = metadata or {}


def _build_runtime() -> PdfVisualProfileRuntime:
    return PdfVisualProfileRuntime(
        native_text_threshold=200,
        visual_probe_pages=12,
        mineru_method="auto",
        mineru_scanned_method="ocr",
        mineru_method_fallbacks="ocr,txt,auto",
        visual_first_max_pages_scanned=30,
        mineru_text_first_office_pdf_enable=True,
        mineru_text_first_office_pdf_min_pages=8,
        mineru_text_first_office_pdf_min_probe_chars=900,
        pdf_text_first_enable=True,
        pdf_text_heavy_min_probe_chars=1800,
        pdf_text_heavy_min_chars_per_page=850,
        pdf_text_heavy_max_visual_cues=1,
        pdf_mixed_text_pref_min_chars_per_page=520,
        pdf_mixed_text_pref_max_visual_cues=4,
        pdf_text_only_short_circuit_enable=True,
        normalize_text=lambda text: " ".join(str(text or "").split()),
    )


def test_pdf_visual_profile_runtime_summarizes_office_like_metadata() -> None:
    runtime = _build_runtime()

    result = runtime.summarize_pdf_metadata_signals(
        _FakeReader({"/Creator": "Microsoft Word", "/Producer": "Office PDF"})
    )

    assert result["creator"] == "Microsoft Word"
    assert result["producer"] == "Office PDF"
    assert result["office_like"] is True


def test_pdf_visual_profile_runtime_classifies_scanned_pdf() -> None:
    runtime = _build_runtime()

    result = runtime.classify_pdf_visual_profile(
        file_name="scan.pdf",
        page_count=20,
        probe_pages=5,
        probe_chars=120,
        probe_text="",
        pdf_metadata_signals={"office_like": False},
    )

    assert result["profile"] == "visual_scanned_pdf"
    assert result["method"] == "ocr"
    assert result["method_fallbacks"] == ["txt"]
    assert result["page_count_cap"] == 30


def test_pdf_visual_profile_runtime_classifies_office_text_pdf() -> None:
    runtime = _build_runtime()

    result = runtime.classify_pdf_visual_profile(
        file_name="office.pdf",
        page_count=12,
        probe_pages=4,
        probe_chars=1400,
        probe_text="plain paragraph text only",
        pdf_metadata_signals={"office_like": True},
    )

    assert result["profile"] == "office_text_pdf"
    assert result["method"] == "txt"
    assert result["reason"] == "office_pdf_strong_native_text"


def test_pdf_visual_profile_runtime_classifies_text_heavy_pdf() -> None:
    runtime = _build_runtime()

    result = runtime.classify_pdf_visual_profile(
        file_name="report.pdf",
        page_count=10,
        probe_pages=2,
        probe_chars=2000,
        probe_text="plain paragraph with very low cue density",
        pdf_metadata_signals={"office_like": False},
    )

    assert result["profile"] == "text_heavy_pdf"
    assert result["method"] == "txt"
    assert result["stop_on_usable_text"] is True


def test_pdf_visual_profile_runtime_classifies_mixed_text_pref_pdf() -> None:
    runtime = _build_runtime()

    result = runtime.classify_pdf_visual_profile(
        file_name="mixed.pdf",
        page_count=2,
        probe_pages=2,
        probe_chars=1100,
        probe_text="plain narrative page with no markers",
        pdf_metadata_signals={"office_like": False},
    )

    assert result["profile"] == "mixed_text_pref_pdf"
    assert result["method"] == "txt"
    assert result["stop_on_usable_text"] is True


def test_pdf_visual_profile_runtime_falls_back_to_mixed_visual_pdf() -> None:
    runtime = _build_runtime()

    result = runtime.classify_pdf_visual_profile(
        file_name="visual.pdf",
        page_count=14,
        probe_pages=2,
        probe_chars=900,
        probe_text="Figure 1 chart Table 2 diagram equation",
        pdf_metadata_signals={"office_like": False},
    )

    assert result["profile"] == "mixed_visual_pdf"
    assert result["method"] == "auto"
    assert result["stop_on_usable_text"] is False
