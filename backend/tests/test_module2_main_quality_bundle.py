from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_module(module_name: str, relative_path: str):
    module_path = BACKEND_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


main_quality_bundle_module = _load_module(
    "_smart_doc_flow_test_main_quality_bundle",
    "module2/app/bootstrap/quality_builder.py",
)


def test_build_module2_main_quality_bundle_exposes_expected_quality_helpers() -> None:
    bundle = main_quality_bundle_module.build_module2_main_quality_bundle(
        visual_chain_required=lambda: True,
    )

    table_blocks = [
        {"rows": [{"cells": [{}, {}]}, {"cells": [{}]}], "quality": 0.8, "source": "pdf_native"},
        {"rows": [{"cells": [{}, {}, {}]}], "quality": "0.6", "source": "gemini_table"},
    ]
    figure_blocks = [
        {
            "page": 3,
            "source": "gemini_vision",
            "dataframe": {
                "headers": ["year", "value"],
                "rows": [[2024, 100], [2025, 110]],
            },
        },
        {"page": 1, "source": "mineru"},
    ]

    assert bundle.count_table_cells(table_blocks) == 6
    assert bundle.count_figure_dataframe_cells(figure_blocks) == 6
    assert bundle.has_meaningful_value(0) is True
    assert bundle.has_meaningful_value(" n/a ") is False
    assert bundle.has_meaningful_value("ready") is True
    assert bundle.table_quality_avg(table_blocks) == 0.7
    assert bundle.table_source_counts(table_blocks) == {"pdf_native": 1, "gemini_table": 1}
    assert bundle.figure_source_counts(figure_blocks) == {"gemini_vision": 1, "mineru": 1}
    assert bundle.figure_pages(figure_blocks) == [1, 3]
    assert bundle.source_counts_have_gemini({"gemini_table": 2, "mineru": 1}) is True
    assert bundle.source_counts_all_gemini({"gemini_table": 2, "gemini_vision": 1}) is True
    assert bundle.source_counts_all_gemini({"gemini_table": 2, "mineru": 1}) is False


def test_module2_main_quality_bundle_builds_quality_snapshot() -> None:
    bundle = main_quality_bundle_module.build_module2_main_quality_bundle(
        visual_chain_required=lambda: True,
    )

    snapshot = bundle.result_quality_snapshot(
        results={
            "amount": {"value": 128, "confidence": 0.9, "source_ref_id": "r1"},
            "customer": {"value": "Acme", "confidence": "0.6"},
            "ignored": {"value": None},
        },
        schema_fields={
            "amount": {"type": "number"},
            "customer": {"type": "string"},
            "date": {"type": "string"},
        },
    )

    assert snapshot == {
        "target_fields": 3,
        "filled_fields": 2,
        "all_result_fields": 3,
        "all_filled_fields": 2,
        "coverage_ratio": 0.6667,
        "trace_ratio": 0.3333,
        "avg_confidence": 0.75,
    }


def test_module2_main_quality_bundle_builds_visual_chain_contract_for_visual_word_pipeline() -> None:
    bundle = main_quality_bundle_module.build_module2_main_quality_bundle(
        visual_chain_required=lambda: True,
    )

    contract = bundle.build_visual_chain_contract(
        file_name="demo.docx",
        parse_input_name="demo.pdf",
        parse_track="VisualTrack",
        word_parse_via_pdf=True,
        conversion_diag={"office_pdf_converted": True},
        parse_stats={
            "pipeline": "visual_first",
            "chain_status": "success",
            "artifact_status": "ready",
            "vision_status": "ok",
            "visual_baseline_artifact_ready": True,
            "mineru_run": {"status": "ok"},
        },
        table_blocks=[{"source": "pdf_native"}],
        figure_blocks=[{"source": "gemini_vision"}],
    )

    assert contract["required"] is True
    assert contract["satisfied"] is True
    assert contract["reasons"] == []
    assert contract["requires_word_pdf"] is True
    assert contract["parse_input_is_pdf"] is True
    assert contract["table_source_counts"] == {"pdf_native": 1}
    assert contract["figure_source_counts"] == {"gemini_vision": 1}


def test_module2_main_quality_bundle_reports_visual_chain_break_reasons() -> None:
    bundle = main_quality_bundle_module.build_module2_main_quality_bundle(
        visual_chain_required=lambda: True,
    )

    contract = bundle.build_visual_chain_contract(
        file_name="demo.docx",
        parse_input_name="demo.docx",
        parse_track="FastTrack",
        word_parse_via_pdf=True,
        conversion_diag={},
        parse_stats={
            "pipeline": "fasttrack",
            "chain_status": "failed",
            "visual_baseline_artifact_ready": False,
            "mineru_run": {"status": "error"},
            "visual_first_fallback_reason": "timeout",
        },
        table_blocks=[],
        figure_blocks=[],
    )

    assert contract["required"] is True
    assert contract["satisfied"] is False
    assert "word_pdf_conversion_missing" in contract["reasons"]
    assert "word_parse_input_not_pdf" in contract["reasons"]
    assert "parse_track_not_visual:FastTrack" in contract["reasons"]
    assert "fasttrack_fallback_detected" in contract["reasons"]
    assert "pipeline_not_visual_first:fasttrack" in contract["reasons"]
    assert "mineru_status_not_ok:error" in contract["reasons"]
    assert "chain_status_not_success:failed" in contract["reasons"]
    assert "baseline_artifact_missing" in contract["reasons"]
    assert "visual_first_fallback:timeout" in contract["reasons"]


def test_module2_main_quality_bundle_infers_visual_contract_for_docx_pdf_visual_sources() -> None:
    bundle = main_quality_bundle_module.build_module2_main_quality_bundle(
        visual_chain_required=lambda: True,
    )

    contract = bundle.build_visual_chain_contract(
        file_name="2021年民政事业发展统计公报.docx",
        parse_input_name="2021年民政事业发展统计公报.pdf",
        parse_track="VisualTrack",
        word_parse_via_pdf=True,
        conversion_diag={"office_pdf_converted": True},
        parse_stats={
            "mineru_run": {"status": "ok"},
        },
        table_blocks=[{"source": "pdf_mineru_gemini"}],
        figure_blocks=[{"source": "pdf_mineru_gemini"}],
    )

    assert contract["required"] is True
    assert contract["satisfied"] is True
    assert contract["reasons"] == []
    assert contract["pipeline"] == "visual_first"
    assert contract["chain_status"] == "success"
    assert contract["artifact_status"] == "ready"
    assert contract["vision_status"] == "ok"
    assert contract["baseline_artifact_ready"] is True
    assert contract["mineru_status"] == "ok"
    assert contract["inferred_visual_contract"] is True


def test_module2_main_quality_bundle_infers_visual_contract_for_direct_pdf_visual_sources() -> None:
    bundle = main_quality_bundle_module.build_module2_main_quality_bundle(
        visual_chain_required=lambda: True,
    )

    contract = bundle.build_visual_chain_contract(
        file_name="demo.pdf",
        parse_input_name="demo.pdf",
        parse_track="VisualTrack",
        word_parse_via_pdf=False,
        conversion_diag={},
        parse_stats={
            "mineru_run": {"status": "ok"},
        },
        table_blocks=[{"source": "pdf_mineru_gemini"}],
        figure_blocks=[{"source": "pdf_mineru_gemini"}],
    )

    assert contract["required"] is True
    assert contract["satisfied"] is True
    assert contract["reasons"] == []
    assert contract["pipeline"] == "visual_first"
    assert contract["chain_status"] == "success"
    assert contract["artifact_status"] == "ready"
    assert contract["vision_status"] == "ok"
    assert contract["baseline_artifact_ready"] is True
    assert contract["inferred_visual_contract"] is True


def test_module2_main_quality_bundle_infers_visual_contract_for_direct_pdf_text_only_stats() -> None:
    bundle = main_quality_bundle_module.build_module2_main_quality_bundle(
        visual_chain_required=lambda: True,
    )

    contract = bundle.build_visual_chain_contract(
        file_name="X.pdf",
        parse_input_name="X.pdf",
        parse_track="VisualTrack",
        word_parse_via_pdf=False,
        conversion_diag={},
        parse_stats={
            "visual_mode": "text_only",
            "visual_text_only": True,
            "visual_text_char_count": 128,
            "visual_ref_count": 4,
            "mineru_content_list_present": True,
            "mineru_markdown_present": True,
            "visual_baseline_artifact_ready": False,
            "mineru_run": {"status": "ok"},
        },
        table_blocks=[],
        figure_blocks=[],
    )

    assert contract["required"] is True
    assert contract["satisfied"] is True
    assert contract["reasons"] == []
    assert contract["pipeline"] == "visual_first"
    assert contract["chain_status"] == "success"
    assert contract["artifact_status"] == "artifact_text_only"
    assert contract["vision_status"] == "not_needed"
    assert contract["baseline_artifact_ready"] is True
    assert contract["inferred_visual_contract"] is True
