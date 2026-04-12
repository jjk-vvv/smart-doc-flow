from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.runtime.main_extraction_bundle import _EXTRACTION_RUNTIME_FINGERPRINT_FILES


def test_extraction_runtime_fingerprint_tracks_table_postprocess_runtime_files() -> None:
    tracked = set(_EXTRACTION_RUNTIME_FINGERPRINT_FILES)

    assert "app/core/table/table_header_runtime.py" in tracked
    assert "app/core/table/table_merge_runtime.py" in tracked
    assert "app/core/parsers/parser_document_table_bootstrap_runtime.py" in tracked
    assert "app/core/pdf/pdf_fitz_table_runtime.py" in tracked


def test_extraction_runtime_fingerprint_tracks_service_backed_extraction_bundle_builders() -> None:
    tracked = set(_EXTRACTION_RUNTIME_FINGERPRINT_FILES)

    assert "app/services/extraction/extraction_builder.py" in tracked
    assert "app/services/extraction/document_io_builder.py" in tracked
    assert "app/services/extraction/geometry_builder.py" in tracked
    assert "app/services/extraction/progress_builder.py" in tracked
    assert "app/services/extraction/nonpdf_builder.py" in tracked
    assert "app/services/extraction/quick_extract_builder.py" in tracked
    assert "app/services/extraction/quality_builder.py" in tracked
    assert "app/services/extraction/service_builder.py" in tracked
    assert "app/services/extraction/support_builder.py" in tracked
