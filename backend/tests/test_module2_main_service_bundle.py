from __future__ import annotations

import logging
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_service_bundle_module = import_module("app.modules.module2.bootstrap.service")


class _Module4SyncConfigStub:
    def base_url(self) -> str:
        return "http://localhost:8000"

    def headers(self, tenant_id: str) -> dict[str, str]:
        return {"X-Tenant-ID": tenant_id}

    def timeout_sec(self) -> float:
        return 5.0

    def retries(self) -> int:
        return 2

    def retryable_status(self, status_code: int) -> bool:
        return int(status_code or 0) >= 500

    def delay_sec(self, attempt_index: int) -> float:
        return float(attempt_index)

    def default_tenant(self) -> str:
        return "default"

    def sync_enabled(self) -> bool:
        return True

    def document_sync_enabled(self) -> bool:
        return True


def test_build_module2_main_service_bundle_exposes_expected_runtime_fields() -> None:
    logger = logging.getLogger("test.module2.main_service_bundle")
    config_runtime = _Module4SyncConfigStub()

    bundle = main_service_bundle_module.build_module2_main_service_bundle(
        logger=logger,
        outbox_repository=object(),
        artifact_root_factory=lambda: Path.cwd(),
        convert_word_to_pdf=lambda **kwargs: None,
        office_preview_timeout_sec_factory=lambda: 30.0,
        module4_sync_config_runtime=config_runtime,
        module4_sync_metrics_runtime=object(),
        module4_sync_task_runtime=object(),
        normalize_bbox=lambda bbox, page_hint=None: list(bbox or []),
        page_from_bbox=lambda bbox: 1,
        is_meaningful_bbox=lambda bbox: bool(bbox),
        utcnow_factory=lambda: None,
    )

    assert bundle.assistant1_runtime is not None
    assert bundle.artifact_file_runtime is not None
    assert bundle.artifact_support_runtime is not None
    assert bundle.office_preview_runtime is not None
    assert bundle.module4_sync_outbox_runtime is not None
    assert bundle.module4_sync_callback_bundle is not None
    assert bundle.trace_semantics_runtime is not None
    assert bundle.trace_locator_text_runtime is not None
    assert bundle.trace_locator_payload_runtime is not None
    assert bundle.document_trace_hits_runtime is not None
    assert bundle.polymorphic_links_runtime is not None
    assert bundle.document_tools_support_runtime is not None
