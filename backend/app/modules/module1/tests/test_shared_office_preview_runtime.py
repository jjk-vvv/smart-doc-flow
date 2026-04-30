from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.shared.office.preview_runtime import OfficePreviewRuntime


def test_shared_office_preview_runtime_recovers_disk_job_by_job_id(tmp_path: Path) -> None:
    def _convert_word_to_pdf(*, file_name: str, file_bytes: bytes, timeout_sec: float):
        return b"%PDF-1.4\npreview\n", {
            "converter": "unit-test",
            "elapsed_ms": 7,
        }

    file_bytes = b"demo-docx-bytes"
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    preview_root = tmp_path / "office-preview"

    writer_runtime = OfficePreviewRuntime(
        preview_root=preview_root,
        word_pdf_converter=_convert_word_to_pdf,
    )
    created = writer_runtime.start(file_name="demo.docx", file_bytes=file_bytes)
    job_id = str(created["job_id"])
    assert job_id == f"preview_{file_hash[:16]}"

    for _ in range(50):
        status = writer_runtime.get_status(job_id)
        if status["status"] == "completed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("preview job did not complete")

    reader_runtime = OfficePreviewRuntime(
        preview_root=preview_root,
        word_pdf_converter=_convert_word_to_pdf,
    )

    recovered_status = reader_runtime.get_status(job_id)
    assert recovered_status["status"] == "completed"
    assert recovered_status["job_id"] == job_id
    assert recovered_status["file_hash"] == file_hash
    assert recovered_status["converter"] == "unit-test"

    content, content_type, output_name = reader_runtime.get_artifact(job_id)
    assert content.startswith(b"%PDF-")
    assert content_type == "application/pdf"
    assert output_name == "artifact.pdf"

    disk_job_id = f"preview_disk_{file_hash[:16]}"
    disk_status = reader_runtime.get_status(disk_job_id)
    assert disk_status["status"] == "completed"
    assert disk_status["job_id"] == disk_job_id
    assert disk_status["file_hash"] == file_hash

    content, content_type, output_name = reader_runtime.get_artifact(disk_job_id)
    assert content.startswith(b"%PDF-")
    assert content_type == "application/pdf"
    assert output_name == "artifact.pdf"

    fresh_runtime = OfficePreviewRuntime(
        preview_root=preview_root,
        word_pdf_converter=_convert_word_to_pdf,
    )
    reused = fresh_runtime.start(file_name="demo.docx", file_bytes=file_bytes)
    assert reused["job_id"] == job_id
    assert reused["status"] == "completed"
    assert reused["file_hash"] == file_hash
