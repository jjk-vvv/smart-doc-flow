from __future__ import annotations

import asyncio
import hashlib
from importlib import import_module
from pathlib import Path


office_preview_module = import_module("app.modules.module2.services.preview.office")
OfficePreviewRuntime = office_preview_module.OfficePreviewRuntime


def _safe_artifact_path_factory(root: Path):
    def _safe_artifact_path(path_fragment: str) -> Path:
        cleaned = str(path_fragment or "").replace("\\", "/").strip().strip("/")
        target = (root / cleaned).resolve()
        target.relative_to(root.resolve())
        return target

    return _safe_artifact_path


def _artifact_fragment_from_path(path_value) -> str:
    return str(path_value or "").strip().strip("/")


def _artifact_url_from_fragment(fragment: str) -> str:
    cleaned = str(fragment or "").strip().strip("/")
    return f"/extract/artifact/{cleaned}" if cleaned else ""


def test_office_preview_runtime_runs_job_and_reuses_disk_artifact(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    safe_artifact_path = _safe_artifact_path_factory(artifact_root)

    async def _convert_word_to_pdf(*, file_name: str, file_bytes: bytes, timeout_sec: float):
        pdf_bytes = b"%PDF-1.4\npreview\n"
        return pdf_bytes, {
            "converter": "unit-test",
            "elapsed_ms": 12,
        }

    runtime = OfficePreviewRuntime(
        convert_word_to_pdf=_convert_word_to_pdf,
        safe_artifact_path=safe_artifact_path,
        artifact_fragment_from_path=_artifact_fragment_from_path,
        artifact_url_from_fragment=_artifact_url_from_fragment,
        timeout_sec_factory=lambda: 30.0,
    )

    async def _scenario() -> None:
        file_bytes = b"demo-docx-bytes"
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        created = await runtime.ensure_job_started(
            file_name="demo.docx",
            file_bytes=file_bytes,
            file_hash=file_hash,
        )
        pdf_bytes, payload = await runtime.await_or_reuse_pdf(
            file_name="demo.docx",
            file_hash=file_hash,
            timeout_sec=5.0,
        )

        assert pdf_bytes == b"%PDF-1.4\npreview\n"
        assert payload["converter"] == "unit-test"
        assert payload["office_pdf_preview_job_id"] == created.job_id
        assert created.status == "completed"
        assert created.artifact_path

        await runtime.clear()
        reused_bytes, reused_payload = await runtime.await_or_reuse_pdf(
            file_name="demo.docx",
            file_hash=file_hash,
            timeout_sec=2.0,
        )

        assert reused_bytes == b"%PDF-1.4\npreview\n"
        assert reused_payload["office_pdf_preview_reused"] is True
        assert runtime.job_count() == 1

        status_payload = await runtime.get_status_payload(reused_payload["office_pdf_preview_job_id"])
        assert status_payload["status"] == "completed"
        assert status_payload["artifact_url"].startswith("/extract/artifact/preview/op/")

    asyncio.run(_scenario())
