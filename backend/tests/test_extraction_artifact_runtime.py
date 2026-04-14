from __future__ import annotations

import asyncio
import hashlib
import io
import json
from pathlib import Path

from starlette.datastructures import UploadFile

from app.core.config import Settings
from app.modules.module2.core.config import get_extraction_settings
from app.modules.module2.core import artifact_runtime as extraction_artifact_runtime_module
from app.modules.module2.core.artifact_runtime import ExtractionArtifactRuntime


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


def test_extraction_artifact_runtime_word_pdf_backend_order_supports_libreoffice_only(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "libreoffice_only")

    assert extraction_artifact_runtime_module._word_pdf_backend_order() == ("libreoffice",)


def test_extraction_artifact_runtime_runs_preview_and_recovers_from_disk(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime: ExtractionArtifactRuntime | None = None

    def _convert_word_bytes_to_pdf(*, file_name: str, file_bytes: bytes, timeout_sec: float):
        assert file_name == "demo.docx"
        assert file_bytes == b"demo-docx-bytes"
        assert runtime is not None
        assert timeout_sec == runtime.office_preview_timeout_sec()
        return (
            b"%PDF-1.4\npreview\n",
            {
                "converter": "libreoffice",
                "elapsed_ms": 12,
            },
        )

    runtime = ExtractionArtifactRuntime(
        word_file_detector=lambda _file_name: True,
        word_pdf_converter=_convert_word_bytes_to_pdf,
    )

    async def _scenario() -> None:
        created = await runtime.start_office_preview(
            settings,
            UploadFile(filename="demo.docx", file=io.BytesIO(b"demo-docx-bytes")),
        )
        assert created["status"] in {"queued", "running", "completed"}, created

        status = {}
        for _ in range(80):
            status = await runtime.get_office_preview_status(settings, created["job_id"])
            if status["status"] == "completed":
                break
            await asyncio.sleep(0.05)

        assert status["status"] == "completed"
        assert status["artifact_path"].startswith("preview/op/")
        assert status["artifact_url"].startswith("/extract/artifact/preview/op/")
        assert status["converter"] == "libreoffice"

        cleared = runtime.clear_office_preview_runtime_state()
        assert cleared["cleared_office_preview_jobs_memory"] >= 1
        assert runtime.office_preview_jobs == {}

        recovered = await runtime.start_office_preview(
            settings,
            UploadFile(filename="demo.docx", file=io.BytesIO(b"demo-docx-bytes")),
        )
        assert recovered["status"] == "completed"
        assert recovered["job_id"].startswith("preview_disk_")
        assert recovered["artifact_url"] == status["artifact_url"]
        assert recovered["converter"] == "libreoffice"

    asyncio.run(_scenario())


def test_extraction_artifact_runtime_ignores_incompatible_word_com_disk_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "libreoffice_only")
    settings = _settings(tmp_path)
    runtime = ExtractionArtifactRuntime()
    file_hash = hashlib.sha256(b"demo-docx-bytes").hexdigest()
    pdf_fragment, meta_fragment = runtime.office_preview_storage_fragments(file_hash)
    pdf_path = runtime.resolve_artifact_path(settings, pdf_fragment)
    meta_path = runtime.resolve_artifact_path(settings, meta_fragment)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\ncache\n")
    meta_path.write_text(
        json.dumps(
            {
                "file_name": "demo.docx",
                "file_hash": file_hash,
                "converter": "word_com",
                "elapsed_ms": 22,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert runtime.load_office_preview_record(settings, file_hash) == {}


def test_extraction_artifact_runtime_reads_legacy_sidecar_artifact_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    primary_root = (settings.data_root_dir / "module2" / "artifacts").resolve()
    monkeypatch.setenv("MODULE2_ARTIFACT_ROOT_DIR", str(primary_root))
    get_extraction_settings.cache_clear()

    runtime = ExtractionArtifactRuntime()
    file_hash = hashlib.sha256(b"legacy-root-demo").hexdigest()
    pdf_fragment, meta_fragment = runtime.office_preview_storage_fragments(file_hash)
    primary_pdf_path = runtime.resolve_artifact_path(settings, pdf_fragment)
    assert primary_pdf_path.exists() is False

    legacy_root = (
        settings.runtime_root_dir / "backend" / "app" / "modules" / "module2" / "runtime-data" / "module2" / "artifacts"
    ).resolve()
    legacy_pdf_path = (legacy_root / pdf_fragment).resolve()
    legacy_meta_path = (legacy_root / meta_fragment).resolve()
    legacy_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_pdf_path.write_bytes(b"%PDF-1.4\nlegacy\n")
    legacy_meta_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_meta_path.write_text(
        json.dumps(
                {
                    "file_name": "legacy.docx",
                    "file_hash": file_hash,
                    "converter": "libreoffice",
                    "elapsed_ms": 31,
                    "tenant_id": "",
                },
                ensure_ascii=False,
            ),
        encoding="utf-8",
    )

    recovered = runtime.load_office_preview_record(settings, file_hash)
    assert recovered.get("artifact_path") == pdf_fragment
    assert recovered.get("converter") == "libreoffice"

    response = runtime.serve_artifact(settings, pdf_fragment, "GET")
    assert response.status_code == 200
