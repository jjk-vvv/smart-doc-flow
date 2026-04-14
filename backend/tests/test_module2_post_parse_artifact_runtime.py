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


post_parse_artifact_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "pipeline", "document_postprocess_runtime.py"],
    "_smart_doc_flow_module2_post_parse_artifact_runtime",
)

PostParseArtifactRuntime = post_parse_artifact_runtime_module.PostParseArtifactRuntime


def test_post_parse_artifact_runtime_builds_pdf_preview_and_trace_context() -> None:
    runtime = PostParseArtifactRuntime()
    calls: dict[str, object] = {}

    def _write_artifact_bytes(**kwargs):
        calls["write_artifact_bytes"] = dict(kwargs)
        return ("preview/pdf/demo_hash.pdf", "/extract/artifact/preview/pdf/demo_hash.pdf")

    def _build_document_trace_hits(**kwargs):
        calls["trace_hits"] = dict(kwargs)
        return [{"object_type": "field", "object_id": "invoice_total"}]

    def _trace_stats_builder(trace_hits):
        calls["trace_stats_input"] = list(trace_hits)
        return {"trace_hit_count": len(trace_hits)}

    def _build_polymorphic_links(**kwargs):
        calls["polymorphic_links"] = dict(kwargs)
        return [{"field": "invoice_total", "ref_id": "r1"}]

    outcome = runtime.build_context(
        file_name="invoice.docx",
        file_hash="hash123",
        parse_input_name="invoice.pdf",
        parse_input_bytes=b"%PDF",
        final_results={"invoice_total": {"value": 100, "source_ref_id": "r1"}},
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
        markdown="markdown",
        bbox_map={"r1": [1.0, 0.1, 0.2, 0.3, 0.4]},
        conversion_diag={"seed": "ok"},
        soft_warnings=["seed_warning"],
        write_artifact_bytes=_write_artifact_bytes,
        crop_pdf_region_png=None,
        build_document_trace_hits=_build_document_trace_hits,
        trace_stats_builder=_trace_stats_builder,
        build_polymorphic_links=_build_polymorphic_links,
        normalize_soft_warnings=lambda value: list(dict.fromkeys(str(item) for item in value if str(item).strip())),
    )

    assert outcome.soft_warnings == ["seed_warning"]
    assert outcome.conversion_diag["seed"] == "ok"
    assert outcome.conversion_diag["pdf_preview_path"] == "preview/pdf/demo_hash.pdf"
    assert outcome.conversion_diag["pdf_preview_url"] == "/extract/artifact/preview/pdf/demo_hash.pdf"
    assert outcome.trace_hits == [{"object_type": "field", "object_id": "invoice_total"}]
    assert outcome.trace_stats == {"trace_hit_count": 1}
    assert outcome.polymorphic_links == [{"field": "invoice_total", "ref_id": "r1"}]
    assert calls["write_artifact_bytes"]["file_name"] == "invoice.pdf"
    assert calls["trace_hits"]["file_hash"] == "hash123"
    assert calls["polymorphic_links"]["trace_hits"] == outcome.trace_hits


def test_post_parse_artifact_runtime_handles_pdf_preview_failure_and_enriches_diagnostics() -> None:
    runtime = PostParseArtifactRuntime()

    def _write_artifact_bytes(**kwargs):
        raise RuntimeError("disk full")

    outcome = runtime.build_context(
        file_name="report.pdf",
        file_hash="hash456",
        parse_input_name="report.pdf",
        parse_input_bytes=b"%PDF",
        final_results={},
        table_blocks=[],
        figure_blocks=[],
        markdown="markdown",
        bbox_map={},
        conversion_diag={},
        soft_warnings=["seed"],
        write_artifact_bytes=_write_artifact_bytes,
        crop_pdf_region_png=None,
        build_document_trace_hits=lambda **kwargs: [],
        trace_stats_builder=lambda trace_hits: {"trace_hit_count": len(trace_hits)},
        build_polymorphic_links=lambda **kwargs: [],
        normalize_soft_warnings=lambda value: list(dict.fromkeys(str(item) for item in value if str(item).strip())),
    )

    assert outcome.soft_warnings == ["seed", "pdf_preview_cache_failed:RuntimeError"]
    assert outcome.conversion_diag == {}

    diagnostics = runtime.enrich_diagnostics(
        file_name="report.pdf",
        file_hash="hash456",
        markdown_text="# hello",
        track="VisualTrack",
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[],
        diagnostics={"seed": True},
        persist_assistant1_source_markdown_artifact=lambda **kwargs: (
            "assistant_1_source/hash456/source.md",
            "/extract/artifact/assistant_1_source/hash456/source.md",
            "assistant_1_source/hash456/meta.json",
            "/extract/artifact/assistant_1_source/hash456/meta.json",
        ),
        persist_assistant_payload_artifact=lambda **kwargs: (
            "assistant_payload/hash456/payload.json",
            "/extract/artifact/assistant_payload/hash456/payload.json",
        ),
        promote_visual_diagnostics=lambda payload: {**payload, "promoted": True},
    )

    assert diagnostics["seed"] is True
    assert diagnostics["assistant1_source_markdown_artifact_path"] == "assistant_1_source/hash456/source.md"
    assert diagnostics["assistant1_source_manifest_path"] == "assistant_1_source/hash456/meta.json"
    assert diagnostics["assistant_payload_artifact_path"] == "assistant_payload/hash456/payload.json"
    assert diagnostics["assistant_payload_version"] == "module2-assistant-payload-v1"
    assert diagnostics["promoted"] is True


def test_post_parse_artifact_runtime_disables_pdf_roi_table_fallback_by_default(monkeypatch) -> None:
    monkeypatch.delenv("MODULE2_TRACE_TABLE_PDF_ROI_FALLBACK_ENABLED", raising=False)
    runtime = PostParseArtifactRuntime()
    calls = {"crop": 0, "write": 0}
    table_blocks = [{"table_id": "t1", "page": 1, "bbox_norm": [0.1, 0.2, 0.3, 0.4]}]

    def _crop_pdf_region_png(*args, **kwargs):
        calls["crop"] += 1
        return b"png"

    def _write_artifact_bytes(**kwargs):
        calls["write"] += 1
        return ("trace/table/hash/t1.png", "/extract/artifact/trace/table/hash/t1.png")

    runtime.materialize_pdf_table_artifacts(
        file_name="report.pdf",
        file_hash="hash123",
        parse_input_name="report.pdf",
        parse_input_bytes=b"%PDF",
        table_blocks=table_blocks,
        crop_pdf_region_png=_crop_pdf_region_png,
        write_artifact_bytes=_write_artifact_bytes,
    )

    assert calls == {"crop": 0, "write": 0}
    assert "artifact_path" not in table_blocks[0]
    assert "artifact_url" not in table_blocks[0]


def test_post_parse_artifact_runtime_allows_pdf_roi_table_fallback_when_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_TRACE_TABLE_PDF_ROI_FALLBACK_ENABLED", "true")
    runtime = PostParseArtifactRuntime()
    calls = {"crop": 0, "write": 0}
    table_blocks = [{"table_id": "t1", "page": 1, "bbox_norm": [0.1, 0.2, 0.3, 0.4]}]

    def _crop_pdf_region_png(*args, **kwargs):
        calls["crop"] += 1
        return b"png"

    def _write_artifact_bytes(**kwargs):
        calls["write"] += 1
        return ("trace/table/hash/t1.png", "/extract/artifact/trace/table/hash/t1.png")

    runtime.materialize_pdf_table_artifacts(
        file_name="report.pdf",
        file_hash="hash123",
        parse_input_name="report.pdf",
        parse_input_bytes=b"%PDF",
        table_blocks=table_blocks,
        crop_pdf_region_png=_crop_pdf_region_png,
        write_artifact_bytes=_write_artifact_bytes,
    )

    assert calls == {"crop": 1, "write": 1}
    assert table_blocks[0]["artifact_path"] == "trace/table/hash/t1.png"
    assert table_blocks[0]["artifact_url"] == "/extract/artifact/trace/table/hash/t1.png"
