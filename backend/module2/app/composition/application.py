from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .foundation import build_module2_default_bootstrap_components

MODULE2_ROOT = Path(__file__).resolve().parents[2]
CUSTOM_MODULE2_ENV_FILE = str(os.getenv("MODULE2_ENV_FILE", "") or "").strip()

# Always load Module 2's own env file so uvicorn startup from repo root
# does not silently miss the module-specific LLM/timeout settings.
# Keep process environment variables authoritative for runtime overrides;
# the bundled .env should only fill missing keys.
load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)
if CUSTOM_MODULE2_ENV_FILE:
    load_dotenv(dotenv_path=CUSTOM_MODULE2_ENV_FILE, override=True)

logger = logging.getLogger(__name__)
module2_bootstrap_components = build_module2_default_bootstrap_components(
    logger=logger,
    module2_root=MODULE2_ROOT,
)

_SCHEMA_NOISE_RULES = module2_bootstrap_components.schema_noise_rules
_FIELD_TYPE_RULES = module2_bootstrap_components.field_type_rules
_SCHEMA_SELECTION_RULES = module2_bootstrap_components.schema_selection_rules
_SCHEMA_SEMANTIC_RULES = module2_bootstrap_components.schema_semantic_rules
_SCHEMA_RULE_VERSIONS = module2_bootstrap_components.schema_rule_versions
AUTO_SCHEMA_LOGIC_REVISION = module2_bootstrap_components.auto_schema_logic_revision

module2_main_foundation_bundle = module2_bootstrap_components.foundation_bundle
module2_main_repository_bundle = module2_main_foundation_bundle.repository_bundle
runtime_state_repository = module2_main_repository_bundle.runtime_state_repository
extraction_cache_repository = module2_main_repository_bundle.extraction_cache_repository
module4_sync_outbox_repository = module2_main_repository_bundle.module4_sync_outbox_repository
assistant_session_repository = module2_main_repository_bundle.assistant_session_repository
# Backward-compatible alias for legacy imports.
storage = module2_main_repository_bundle.legacy_storage
graph = module2_main_foundation_bundle.graph
module2_main_support_bundle = module2_main_foundation_bundle.support_bundle
module2_main_platform_bundle = module2_main_foundation_bundle.platform_bundle
module2_main_schema_primitives_bundle = module2_main_foundation_bundle.schema_primitives_bundle
module2_main_policy_bundle = module2_main_foundation_bundle.policy_bundle
module2_main_document_io_bundle = module2_main_foundation_bundle.document_io_bundle
module2_main_value_guard_bundle = module2_main_foundation_bundle.value_guard_bundle
module2_main_nonpdf_bundle = module2_main_foundation_bundle.nonpdf_bundle
module2_main_quick_extract_bundle = module2_main_foundation_bundle.quick_extract_bundle
module2_main_quality_bundle = module2_main_foundation_bundle.quality_bundle
module2_main_progress_bundle = module2_main_foundation_bundle.progress_bundle
module2_main_service_bundle = module2_main_foundation_bundle.service_bundle
module2_main_extraction_bundle = module2_main_foundation_bundle.extraction_bundle
module2_http_runtime_bundle = module2_main_foundation_bundle.http_runtime_bundle

module4_sync_task_runtime = module2_main_support_bundle.module4_sync_task_runtime
module4_sync_metrics_runtime = module2_main_support_bundle.module4_sync_metrics_runtime
module4_sync_config_runtime = module2_main_support_bundle.module4_sync_config_runtime
module2_health_runtime = module2_main_support_bundle.module2_health_runtime
module2_app_lifecycle_runtime = module2_main_support_bundle.module2_app_lifecycle_runtime
startup_task_runtime = module2_main_support_bundle.startup_task_runtime
cached_extraction_restore_runtime = module2_main_support_bundle.cached_extraction_restore_runtime
nonpdf_budget_runtime = module2_main_support_bundle.nonpdf_budget_runtime
visual_parse_policy_runtime = module2_main_support_bundle.visual_parse_policy_runtime
word_conversion_policy_runtime = module2_main_support_bundle.word_conversion_policy_runtime
word_input_preparation_runtime = module2_main_support_bundle.word_input_preparation_runtime
document_parse_attempt_runtime = module2_main_support_bundle.document_parse_attempt_runtime
document_input_plan_runtime = module2_main_support_bundle.document_input_plan_runtime
document_parse_recovery_runtime = module2_main_support_bundle.document_parse_recovery_runtime
document_parse_session_runtime = module2_main_support_bundle.document_parse_session_runtime
diagnostics_builder_runtime = module2_main_support_bundle.diagnostics_builder_runtime
docx_native_recovery_runtime = module2_main_support_bundle.docx_native_recovery_runtime
extraction_response_runtime = module2_main_support_bundle.extraction_response_runtime
extraction_graph_runtime = module2_main_support_bundle.extraction_graph_runtime
fasttrack_fallback_runtime = module2_main_support_bundle.fasttrack_fallback_runtime
post_parse_artifact_runtime = module2_main_support_bundle.post_parse_artifact_runtime
post_parse_quality_runtime = module2_main_support_bundle.post_parse_quality_runtime
parse_fallback_coordinator_runtime = module2_main_support_bundle.parse_fallback_coordinator_runtime
parse_preparation_runtime = module2_main_support_bundle.parse_preparation_runtime
schema_session_runtime = module2_main_support_bundle.schema_session_runtime

module2_bootstrap_runtime = module2_main_platform_bundle.module2_bootstrap_runtime
assistant1_runtime = module2_main_service_bundle.assistant1_runtime
artifact_file_runtime = module2_main_service_bundle.artifact_file_runtime
artifact_support_runtime = module2_main_service_bundle.artifact_support_runtime
office_preview_runtime = module2_main_service_bundle.office_preview_runtime
module4_sync_outbox_runtime = module2_main_service_bundle.module4_sync_outbox_runtime
module4_sync_callback_bundle = module2_main_service_bundle.module4_sync_callback_bundle
trace_semantics_runtime = module2_main_service_bundle.trace_semantics_runtime
document_trace_hits_runtime = module2_main_service_bundle.document_trace_hits_runtime
polymorphic_links_runtime = module2_main_service_bundle.polymorphic_links_runtime

cache_clear_runtime = module2_http_runtime_bundle.cache_clear_runtime
extraction_job_runtime = module2_http_runtime_bundle.extraction_job_runtime
extraction_request_runtime = module2_http_runtime_bundle.extraction_request_runtime
office_preview_request_runtime = module2_http_runtime_bundle.office_preview_request_runtime
document_tools_runtime = module2_http_runtime_bundle.document_tools_runtime
extraction_jobs = module2_http_runtime_bundle.extraction_jobs
extraction_lock = module2_http_runtime_bundle.extraction_lock
extraction_job_runtime_specs = module2_http_runtime_bundle.extraction_job_runtime_specs
extraction_job_tasks = module2_http_runtime_bundle.extraction_job_tasks
extraction_job_persist_markers = module2_http_runtime_bundle.extraction_job_persist_markers

extraction_word_pdf_semaphore = module2_main_extraction_bundle.extraction_word_pdf_semaphore
extraction_llm_semaphore = module2_main_extraction_bundle.extraction_llm_semaphore
_current_extraction_logic_components = module2_main_extraction_bundle.current_extraction_logic_components
_current_extraction_logic_version = module2_main_extraction_bundle.current_extraction_logic_version

module2_main_schema_pipeline_bundle = module2_bootstrap_components.schema_pipeline_bundle
module2_main_result_filter_bundle = module2_main_schema_pipeline_bundle.result_filter_bundle
module2_main_schema_context_bundle = module2_main_schema_pipeline_bundle.schema_context_bundle
module2_main_schema_fields_bundle = module2_main_schema_pipeline_bundle.schema_fields_bundle
module2_main_schema_request_bundle = module2_main_schema_pipeline_bundle.schema_request_bundle
module2_main_schema_resolution_bundle = module2_main_schema_pipeline_bundle.schema_resolution_bundle
module2_main_schema_timeout_bundle = module2_main_schema_pipeline_bundle.schema_timeout_bundle

module2_main_workflow_bundle = module2_bootstrap_components.workflow_bundle
document_workflow_runtime = module2_main_workflow_bundle.document_workflow_runtime
module2_main_entry_bundle = module2_bootstrap_components.entry_bundle

CORS_ORIGINS = module2_main_platform_bundle.cors_origins
CORS_ALLOW_ALL = module2_main_platform_bundle.cors_allow_all


async def extract_batch(
    *,
    request: Any = None,
    files: Sequence[UploadFile],
    schema_form: str,
    tenant_id: str = "",
) -> Any:
    """Expose the legacy batch entrypoint for compat subprocess workers."""

    return await extraction_request_runtime.extract_batch(
        request=request,
        files=files,
        schema_form=schema_form,
        tenant_id=tenant_id,
    )


async def extract_cache_clear(scope: str = "results") -> Any:
    """Expose the legacy cache-clear entrypoint for compat subprocess workers."""

    return await module2_main_entry_bundle.module2_app_callback_bundle.clear_cache_request(scope)


def create_app() -> FastAPI:
    app = FastAPI(
        title="A23 Module 2 - Unstructured Document Extraction",
        version="1.0.0",
        lifespan=module2_main_entry_bundle.lifespan(),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if CORS_ALLOW_ALL else CORS_ORIGINS,
        allow_credentials=not CORS_ALLOW_ALL,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    module2_main_entry_bundle.register_app(app)
    return app


app = create_app()
