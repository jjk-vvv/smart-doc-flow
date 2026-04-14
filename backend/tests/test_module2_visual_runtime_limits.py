from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
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


visual_runtime_limits_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "visual_pdf_bootstrap.py"],
    "_smart_doc_flow_module2_visual_runtime_limits",
)

VisualRuntimeLimitsRuntime = visual_runtime_limits_module.VisualRuntimeLimitsRuntime


def _build_runtime() -> VisualRuntimeLimitsRuntime:
    return VisualRuntimeLimitsRuntime(
        image_extensions={".png", ".jpg", ".jpeg"},
        visual_max_objects=220,
        visual_table_max_per_page=5,
        visual_figure_max_per_page=8,
        visual_figure_chart_score_min=4,
        visual_figure_cueless_fallback_max=2,
        visual_figure_refine_budget=6,
        visual_figure_refine_min_score=5,
        visual_runtime_large_doc_page_threshold=20,
        visual_runtime_large_doc_image_threshold=6,
        visual_runtime_large_doc_max_objects=80,
        visual_runtime_large_doc_figure_max_per_page=3,
        visual_runtime_large_doc_cueless_fallback_max=1,
        visual_runtime_large_doc_chart_score_min=6,
        visual_runtime_large_doc_refine_budget=3,
        visual_runtime_extreme_doc_page_threshold=40,
        visual_runtime_extreme_doc_max_objects=40,
        visual_runtime_extreme_doc_figure_max_per_page=2,
        visual_runtime_extreme_doc_cueless_fallback_max=0,
        visual_runtime_extreme_doc_chart_score_min=7,
        visual_runtime_extreme_doc_refine_budget=1,
    )


def _build_docx_bytes(*, media_count: int, chart_count: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for idx in range(media_count):
            zf.writestr(f"word/media/image{idx + 1}.png", b"fake")
        for idx in range(chart_count):
            zf.writestr(f"word/charts/chart{idx + 1}.xml", "<chart/>")
    return buf.getvalue()


def test_visual_runtime_limits_runtime_summarizes_docx_source_signals() -> None:
    runtime = _build_runtime()

    result = runtime.summarize_visual_source_signals(
        source_file_name="report.docx",
        source_file_bytes=_build_docx_bytes(media_count=3, chart_count=1),
    )

    assert result["source_suffix"] == ".docx"
    assert result["source_docx_media_count"] == 3
    assert result["source_docx_chart_xml_count"] == 1


def test_visual_runtime_limits_runtime_marks_large_visual_doc_profile() -> None:
    runtime = _build_runtime()

    result = runtime.resolve_visual_runtime_limits(
        file_name="report.pdf",
        source_file_name=None,
        source_file_bytes=None,
        page_count=24,
        layout_page_count=18,
        objects=[{"object_type": "image"} for _ in range(6)] + [{"object_type": "table"} for _ in range(2)],
    )

    assert result["profile"] == "large_visual_doc"
    assert result["max_objects"] == 80
    assert result["figure_max_per_page"] == 3
    assert result["chart_score_min"] == 6
    assert result["figure_refine_budget"] == 3
    assert result["layout_page_count"] == 18
    assert result["image_object_count"] == 6
    assert result["table_object_count"] == 2


def test_visual_runtime_limits_runtime_marks_extreme_doc_profile() -> None:
    runtime = _build_runtime()

    result = runtime.resolve_visual_runtime_limits(
        file_name="huge.pdf",
        source_file_name=None,
        source_file_bytes=None,
        page_count=48,
        layout_page_count=45,
        objects=[{"object_type": "image"} for _ in range(3)],
    )

    assert result["profile"] == "extreme_visual_doc"
    assert result["max_objects"] == 40
    assert result["figure_max_per_page"] == 2
    assert result["cueless_fallback_max"] == 0
    assert result["chart_score_min"] == 7
    assert result["figure_refine_budget"] == 1


def test_visual_runtime_limits_runtime_marks_docx_chart_heavy_profile() -> None:
    runtime = _build_runtime()

    result = runtime.resolve_visual_runtime_limits(
        file_name="converted.pdf",
        source_file_name="source.docx",
        source_file_bytes=_build_docx_bytes(media_count=9, chart_count=1),
        page_count=10,
        layout_page_count=10,
        objects=[{"object_type": "image"} for _ in range(4)],
    )

    assert result["profile"] == "docx_chart_heavy"
    assert result["source_signals"]["source_docx_media_count"] == 9
    assert result["source_signals"]["source_docx_chart_xml_count"] == 1
    assert result["source_doc_name"] == "source.docx"
    assert result["doc_name"] == "converted.pdf"
