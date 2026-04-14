from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.modules.module2.core.assistant1_runtime import build_assistant1_context_bundle
from app.modules.module2.core.config import ExtractionSettings


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=60.0,
        stream_chunk_size=4096,
        runtime_root_dir=tmp_path,
        config_root_dir=tmp_path,
        data_root_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url="http://127.0.0.1:8000",
        module4_upstream_url="http://127.0.0.1:8100",
    )


def _extraction_settings() -> ExtractionSettings:
    return ExtractionSettings(
        module2_port_hint="",
        artifact_root_dir="",
        module2_execution_mode="auto",
        module2_fallback_to_upstream=True,
        module2_worker_timeout_sec=900.0,
        module2_worker_python="",
        module2_sidecar_mode="auto",
        module2_sidecar_python="",
        module2_sidecar_startup_timeout_sec=120.0,
        max_file_mb=25,
        doc_to_pdf_enable=True,
        office_preview_timeout_sec=120.0,
        office_preview_job_ttl_sec=1800.0,
        office_preview_job_cap=240,
        extract_job_ttl_sec=7200.0,
        extract_job_cap=240,
        shadow_poll_timeout_sec=2700.0,
        shadow_poll_interval_sec=1.2,
        assistant1_mode="legacy",
        assistant1_fallback_to_legacy=True,
        assistant1_context_max_source_chars=12000,
        assistant1_context_max_refs=6,
        assistant1_history_window=12,
    )


def test_build_assistant1_context_bundle_merges_shadow_and_source_artifacts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    extraction_settings = _extraction_settings()
    file_hash = "abc123def456abc123def456abc123def456abc123def456abc123def456abcd"

    shadow_root = settings.data_root_dir / "module2" / "runlogs" / "unified_extraction_shadow_jobs"
    shadow_root.mkdir(parents=True, exist_ok=True)
    shadow_payload = {
        "payload": {
            "job_id": "extract_job_demo_1",
            "status": "completed",
            "updated_at": 123.0,
            "documents": [
                {
                    "file_name": "demo.pdf",
                    "file_hash": file_hash,
                    "track": "VisualTrack",
                    "result": {
                        "invoice_number": {
                            "value": "INV-001",
                            "confidence": 0.98,
                            "source_ref_id": "ref-1",
                        }
                    },
                    "trace_hits": [
                        {
                            "file_name": "demo.pdf",
                            "file_hash": file_hash,
                            "object_type": "field",
                            "object_id": "invoice_number",
                            "ref_id": "ref-1",
                            "page": 2,
                            "snippet": "发票号码为 INV-001",
                        }
                    ],
                }
            ],
        }
    }
    (shadow_root / "extract_job_demo_1.json").write_text(
        json.dumps(shadow_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    artifact_root = settings.data_root_dir / "module2" / "artifacts" / "assistant_1_source" / file_hash[:12]
    artifact_root.mkdir(parents=True, exist_ok=True)
    markdown_rel = f"assistant_1_source/{file_hash[:12]}/demo_assistant1_source.md"
    markdown_path = settings.data_root_dir / "module2" / "artifacts" / markdown_rel
    markdown_path.write_text(
        '<ref id="ref-1">这是源文片段，包含发票号码 INV-001。</ref>',
        encoding="utf-8",
    )
    meta_path = artifact_root / "demo_source_meta_123.json"
    meta_path.write_text(
        json.dumps(
            {
                "file_name": "demo.pdf",
                "file_hash": file_hash,
                "track": "VisualTrack",
                "markdown_artifact_path": markdown_rel.replace("\\", "/"),
                "markdown_artifact_url": "/extract/artifact/" + markdown_rel.replace("\\", "/"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = build_assistant1_context_bundle(
        settings,
        file_hash=file_hash,
        top_k=5,
        extraction_settings=extraction_settings,
    )

    assert bundle.file_name == "demo.pdf"
    assert bundle.track == "VisualTrack"
    assert bundle.job_id == "extract_job_demo_1"
    assert bundle.result_fields[0]["field_name"] == "invoice_number"
    assert "INV-001" in bundle.source_excerpt
    assert bundle.evidence_items[0]["ref_id"] == "ref-1"
    assert bundle.warnings == ()
