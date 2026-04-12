from __future__ import annotations

import logging
import sys
from importlib import import_module
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_foundation_bundle_module = import_module("module2.app.bootstrap.foundation")


class _StorageStub:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def check_cache(self, **kwargs):
        return None


class _GraphStub:
    def diagnostics(self):
        return {}


def test_build_module2_main_foundation_bundle_exposes_expected_runtime_clusters() -> None:
    logger = logging.getLogger("test.module2.main_foundation_bundle")
    bundle = main_foundation_bundle_module.build_module2_main_foundation_bundle(
        logger=logger,
        module2_root=BACKEND_ROOT / "module2",
        module2_database_dsn="postgresql://example",
        extraction_storage_factory=_StorageStub,
        extraction_graph_factory=_GraphStub,
        getenv=lambda name, default=None: default,
        parse_document_in_subprocess=lambda *args, **kwargs: {"ok": True},
        build_module2_llm_provider_fn=lambda **kwargs: object(),
        convert_word_bytes_to_pdf_fn=lambda **kwargs: (b"%PDF-1.4", {"engine": "stub"}),
        convert_doc_bytes_to_docx_fn=lambda **kwargs: (b"DOCX", {"engine": "stub"}),
        is_word_file=lambda file_name: str(file_name or "").lower().endswith((".doc", ".docx")),
        auto_schema_stopwords_en={"and", "the"},
        field_naming_version="field-v1",
        schema_rule_versions={"rules": "v1"},
        auto_schema_logic_revision="logic-v1",
        job_state_factory=lambda **kwargs: kwargs,
        job_file_state_factory=lambda **kwargs: kwargs,
        document_validate=lambda item: item,
        extraction_result_factory=lambda payload: payload,
        document_response_factory=lambda **kwargs: kwargs,
        batch_response_factory=lambda **kwargs: kwargs,
        summarize_response_factory=lambda **kwargs: kwargs,
        trace_locate_response_factory=lambda **kwargs: kwargs,
        process_single_doc_bytes=lambda **kwargs: kwargs,
        parse_schema_form_json=lambda raw_schema: {"raw_schema": raw_schema},
        is_low_value_auto_schema_field_name=lambda field_name: False,
    )

    assert bundle.repository_bundle.legacy_storage.dsn == "postgresql://example"
    with pytest.warns(DeprecationWarning):
        assert bundle.storage.dsn == "postgresql://example"
    assert bundle.repository_bundle.runtime_state_repository is not None
    assert bundle.repository_bundle.extraction_cache_repository is not None
    assert bundle.repository_bundle.module4_sync_outbox_repository is not None
    assert bundle.graph is not None
    assert bundle.support_bundle.module2_health_runtime is not None
    assert bundle.platform_bundle.module2_bootstrap_runtime is not None
    assert bundle.schema_primitives_bundle.schema_hash is not None
    assert bundle.policy_bundle.build_preflight_provider is not None
    assert bundle.geometry_bundle.normalize_bbox is not None
    assert bundle.document_io_bundle.convert_word_to_pdf_with_timeout is not None
    assert bundle.value_guard_bundle.is_low_value_quick_fallback_value is not None
    assert bundle.nonpdf_bundle.resolve_nonpdf_budgets is not None
    assert bundle.quick_extract_bundle.quick_extract_from_tables is not None
    assert bundle.quality_bundle.result_quality_snapshot is not None
    assert bundle.progress_bundle.resolve_extract_progress_ramp_sec is not None
    assert bundle.service_bundle.assistant1_runtime is not None
    assert bundle.extraction_bundle.current_extraction_cache_version()
    assert bundle.http_runtime_bundle.extraction_request_runtime is not None
