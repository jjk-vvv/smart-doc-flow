from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.module1.services.conversion_service import (
    convert_doc_bytes_to_docx,
    convert_word_bytes_to_pdf,
    download_office_preview_artifact,
    get_office_preview_status,
    is_word_file,
    start_office_preview,
)


class ConversionServiceTestCase(unittest.TestCase):
    def test_is_word_file_delegates_to_shared_detector(self) -> None:
        with patch(
            "app.modules.module1.services.conversion_service._shared_is_word_file",
            return_value=True,
        ) as detector:
            result = is_word_file("sample.docx")

        self.assertTrue(result)
        detector.assert_called_once_with("sample.docx")

    def test_convert_word_bytes_to_pdf_delegates_to_shared_converter(self) -> None:
        expected = (b"%PDF-demo", {"converter": "libreoffice"})
        with patch(
            "app.modules.module1.services.conversion_service._shared_convert_word_bytes_to_pdf",
            return_value=expected,
        ) as converter:
            result = convert_word_bytes_to_pdf(
                file_name="sample.docx",
                file_bytes=b"demo",
                timeout_sec=45.0,
            )

        self.assertEqual(result, expected)
        converter.assert_called_once_with(
            file_name="sample.docx",
            file_bytes=b"demo",
            timeout_sec=45.0,
        )

    def test_convert_doc_bytes_to_docx_delegates_to_shared_converter(self) -> None:
        expected = (b"docx-demo", {"converter": "word_com"})
        with patch(
            "app.modules.module1.services.conversion_service._shared_convert_doc_bytes_to_docx",
            return_value=expected,
        ) as converter:
            result = convert_doc_bytes_to_docx(
                file_name="legacy.doc",
                file_bytes=b"demo",
                timeout_sec=30.0,
            )

        self.assertEqual(result, expected)
        converter.assert_called_once_with(
            file_name="legacy.doc",
            file_bytes=b"demo",
            timeout_sec=30.0,
        )

    def test_start_office_preview_uses_shared_runtime(self) -> None:
        runtime = Mock()
        runtime.start.return_value = {"ok": True, "job_id": "preview_123", "status": "queued"}

        with patch(
            "app.modules.module1.services.conversion_service.get_office_preview_runtime",
            return_value=runtime,
        ):
            payload = start_office_preview(file_name="sample.docx", file_bytes=b"demo")

        self.assertEqual(payload["job_id"], "preview_123")
        runtime.start.assert_called_once_with(file_name="sample.docx", file_bytes=b"demo")

    def test_get_office_preview_status_uses_shared_runtime(self) -> None:
        runtime = Mock()
        runtime.get_status.return_value = {"ok": True, "job_id": "preview_123", "status": "completed"}

        with patch(
            "app.modules.module1.services.conversion_service.get_office_preview_runtime",
            return_value=runtime,
        ):
            payload = get_office_preview_status(job_id="preview_123")

        self.assertEqual(payload["status"], "completed")
        runtime.get_status.assert_called_once_with("preview_123")

    def test_download_office_preview_artifact_uses_shared_runtime(self) -> None:
        runtime = Mock()
        runtime.get_artifact.return_value = (b"%PDF-demo", "application/pdf", "artifact.pdf")

        with patch(
            "app.modules.module1.services.conversion_service.get_office_preview_runtime",
            return_value=runtime,
        ):
            payload = download_office_preview_artifact(job_id="preview_123")

        self.assertEqual(payload, (b"%PDF-demo", "application/pdf", "artifact.pdf"))
        runtime.get_artifact.assert_called_once_with("preview_123")


if __name__ == "__main__":
    unittest.main()
