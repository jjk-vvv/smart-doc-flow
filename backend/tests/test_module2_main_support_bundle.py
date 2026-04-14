from __future__ import annotations

import logging
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_support_bundle_module = import_module("app.modules.module2.bootstrap.support")


def test_build_module2_main_support_bundle_exposes_expected_runtime_fields() -> None:
    logger = logging.getLogger("test.module2.main_support_bundle")

    bundle = main_support_bundle_module.build_module2_main_support_bundle(logger=logger)

    assert bundle.module4_sync_task_runtime is not None
    assert bundle.module4_sync_metrics_runtime is not None
    assert bundle.module4_sync_config_runtime is not None
    assert bundle.mineru_warmup_runtime is not None
    assert bundle.provider_preflight_runtime is not None
    assert bundle.cached_extraction_restore_runtime is not None
    assert bundle.document_parse_attempt_runtime is not None
    assert bundle.document_input_plan_runtime is not None
    assert bundle.document_parse_recovery_runtime is not None
    assert bundle.document_parse_session_runtime is not None
    assert bundle.diagnostics_builder_runtime is not None
    assert bundle.docx_native_recovery_runtime is not None
    assert bundle.extraction_response_runtime is not None
    assert bundle.extraction_graph_runtime is not None
    assert bundle.fasttrack_fallback_runtime is not None
    assert bundle.post_parse_artifact_runtime is not None
    assert bundle.post_parse_quality_runtime is not None
    assert bundle.parse_fallback_coordinator_runtime is not None
    assert bundle.parse_preparation_runtime is not None
    assert bundle.schema_session_runtime is not None


def test_build_module2_bootstrap_runtime_bundle_wires_pool_and_bootstrap() -> None:
    logger = logging.getLogger("test.module2.bootstrap_bundle")
    provider_preflight_runtime = object()
    mineru_warmup_runtime = object()
    getenv = lambda name, default=None: default
    bounded_env_int = lambda *args, **kwargs: 3
    max_workers_provider = lambda: 4
    build_pool = lambda: "pool"
    parse_document_in_subprocess = lambda **kwargs: {"ok": True}

    bundle = main_support_bundle_module.build_module2_bootstrap_runtime_bundle(
        logger=logger,
        provider_preflight_runtime=provider_preflight_runtime,
        mineru_warmup_runtime=mineru_warmup_runtime,
        getenv=getenv,
        bounded_env_int=bounded_env_int,
        max_workers_provider=max_workers_provider,
        build_pool=build_pool,
        parse_document_in_subprocess=parse_document_in_subprocess,
    )

    assert bundle.document_process_pool_runtime is not None
    assert bundle.module2_bootstrap_runtime is not None
