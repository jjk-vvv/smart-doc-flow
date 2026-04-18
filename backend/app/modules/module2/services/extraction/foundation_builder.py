from __future__ import annotations

import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict

from ...agent.graph import ExtractionGraph
from ...core.schema.field_naming import (
    FIELD_NAMING_VERSION,
    canonicalize_schema_fields,
    detect_domain_template,
    infer_rule_backed_schema_fields,
    normalize_field_name,
    normalize_schema_contracts,
)
from ...core.integration.mineru_layout import clear_mineru_process_runtime_cache
from ...core.format.office_pdf import convert_doc_bytes_to_docx, convert_word_bytes_to_pdf, is_word_file
from ...core.parsers.native_document_parser import parse_document_in_subprocess
from ...core.schema.schema_rule_assets import (
    load_field_type_rules,
    load_schema_coverage_profiles,
    load_schema_noise_rules,
    load_schema_semantic_rules,
    load_schema_selection_rules,
    schema_rule_versions,
)
from ...repositories import ExtractionStorage, Module2RepositoryBundle, build_module2_repository_bundle
from ...integrations.llm.provider import build_module2_llm_provider
from ...schemas import (
    BatchExtractionResponse,
    DocumentExtractionResponse,
    ExtractionResult,
    SummarizeResponse,
    TraceLocateResponse,
)
from .job import ExtractionJobFileState, ExtractionJobState
from ...composition.http_runtime_bundle import Module2HttpRuntimeBundle, build_module2_http_runtime_bundle
from .document_io_builder import Module2MainDocumentIoBundle, build_module2_main_document_io_bundle
from .entry_builder import Module2MainEntryBundle, build_module2_main_entry_bundle
from .extraction_builder import Module2MainExtractionBundle, build_module2_main_extraction_bundle
from .geometry_builder import Module2MainGeometryBundle, build_module2_main_geometry_bundle
from .nonpdf_builder import Module2MainNonPdfBundle, build_module2_main_nonpdf_bundle
from .platform_builder import Module2MainPlatformBundle, build_module2_main_platform_bundle
from .policy_builder import Module2MainPolicyBundle, build_module2_main_policy_bundle
from .progress_builder import Module2MainProgressBundle, build_module2_main_progress_bundle
from .quality_builder import Module2MainQualityBundle, build_module2_main_quality_bundle
from .quick_extract_builder import (
    Module2MainQuickExtractBundle,
    Module2MainValueGuardBundle,
    build_module2_main_quick_extract_bundle,
    build_module2_main_value_guard_bundle,
)
from .service_builder import Module2MainServiceBundle, build_module2_main_service_bundle
from .support_builder import Module2MainSupportBundle, build_module2_main_support_bundle
from .workflow_builder import Module2MainWorkflowBundle, build_module2_main_workflow_bundle
from ..schema.schema_pipeline_builder import (
    Module2MainSchemaPipelineBundle,
    build_module2_main_schema_pipeline_bundle_from_rules,
)
from ..schema.schema_primitives_builder import (
    Module2MainSchemaPrimitivesBundle,
    build_module2_main_schema_primitives_bundle,
)


GetEnvFn = Callable[[str, str | None], str | None]
_DEFAULT_AUTO_SCHEMA_LOGIC_REVISION = "20260323-figure-aware-schema-v4"


@dataclass(frozen=True)
class Module2MainFoundationBundle:
    repository_bundle: Module2RepositoryBundle
    graph: Any
    support_bundle: Module2MainSupportBundle
    platform_bundle: Module2MainPlatformBundle
    schema_primitives_bundle: Module2MainSchemaPrimitivesBundle
    policy_bundle: Module2MainPolicyBundle
    geometry_bundle: Module2MainGeometryBundle
    document_io_bundle: Module2MainDocumentIoBundle
    value_guard_bundle: Module2MainValueGuardBundle
    nonpdf_bundle: Module2MainNonPdfBundle
    quick_extract_bundle: Module2MainQuickExtractBundle
    quality_bundle: Module2MainQualityBundle
    progress_bundle: Module2MainProgressBundle
    service_bundle: Module2MainServiceBundle
    extraction_bundle: Module2MainExtractionBundle
    http_runtime_bundle: Module2HttpRuntimeBundle

    @property
    def storage(self) -> Any:
        warnings.warn(
            "Module2MainFoundationBundle.storage is deprecated; "
            "use Module2MainFoundationBundle.repository_bundle.storage instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.repository_bundle.storage


@dataclass(frozen=True)
class Module2BootstrapComponents:
    foundation_bundle: Module2MainFoundationBundle
    schema_pipeline_bundle: Module2MainSchemaPipelineBundle
    workflow_bundle: Module2MainWorkflowBundle
    entry_bundle: Module2MainEntryBundle
    schema_noise_rules: Dict[str, Any]
    field_type_rules: Dict[str, Any]
    schema_selection_rules: Dict[str, Any]
    schema_semantic_rules: Dict[str, Any]
    schema_coverage_profiles: Dict[str, Any]
    schema_rule_versions: Dict[str, Any]
    auto_schema_logic_revision: str


def build_module2_main_foundation_bundle(
    *,
    logger: Any,
    module2_root: Path,
    module2_database_dsn: str,
    extraction_storage_factory: Callable[[str], Any],
    extraction_graph_factory: Callable[[], Any],
    getenv: GetEnvFn,
    parse_document_in_subprocess: Callable[..., Any],
    build_module2_llm_provider_fn: Callable[..., Any],
    convert_word_bytes_to_pdf_fn: Callable[..., Any],
    convert_doc_bytes_to_docx_fn: Callable[..., Any],
    is_word_file: Callable[[str], bool],
    auto_schema_stopwords_en: set[str],
    field_naming_version: str,
    schema_rule_versions: Dict[str, Any],
    auto_schema_logic_revision: str,
    job_state_factory: Callable[..., Any],
    job_file_state_factory: Callable[..., Any],
    document_validate: Callable[[Any], Any],
    extraction_result_factory: Callable[[Dict[str, Any]], Any],
    document_response_factory: Callable[..., Any],
    batch_response_factory: Callable[..., Any],
    summarize_response_factory: Callable[..., Any],
    trace_locate_response_factory: Callable[..., Any],
    process_single_doc_bytes: Callable[..., Any],
    parse_schema_form_json: Callable[[str], Dict[str, Any]],
    is_low_value_auto_schema_field_name: Callable[[str], bool],
) -> Module2MainFoundationBundle:
    support_bundle = build_module2_main_support_bundle(logger=logger)
    platform_bundle = build_module2_main_platform_bundle(
        logger=logger,
        provider_preflight_runtime=support_bundle.provider_preflight_runtime,
        mineru_warmup_runtime=support_bundle.mineru_warmup_runtime,
        getenv=getenv,
        parse_document_in_subprocess=parse_document_in_subprocess,
    )
    storage = extraction_storage_factory(module2_database_dsn)
    repository_bundle = build_module2_repository_bundle(storage=storage)
    graph = extraction_graph_factory()
    schema_primitives_bundle = build_module2_main_schema_primitives_bundle()
    policy_bundle = build_module2_main_policy_bundle(
        module2_root=module2_root,
        getenv=getenv,
        build_module2_llm_provider_fn=build_module2_llm_provider_fn,
    )
    geometry_bundle = build_module2_main_geometry_bundle()
    document_io_bundle = build_module2_main_document_io_bundle(
        is_meaningful_bbox=geometry_bundle.is_meaningful_bbox,
        convert_word_bytes_to_pdf_fn=convert_word_bytes_to_pdf_fn,
        convert_doc_bytes_to_docx_fn=convert_doc_bytes_to_docx_fn,
    )
    quick_extract_bundle: Module2MainQuickExtractBundle | None = None

    def _to_number_or_none(value: Any) -> Any:
        if quick_extract_bundle is None:
            raise RuntimeError("Module2 quick extract bundle is not initialized")
        return quick_extract_bundle.to_number_or_none(value)

    value_guard_bundle = build_module2_main_value_guard_bundle(
        to_number_or_none=_to_number_or_none,
        auto_schema_stopwords_en=set(auto_schema_stopwords_en),
    )
    nonpdf_bundle = build_module2_main_nonpdf_bundle(getenv=getenv)
    quick_extract_bundle = build_module2_main_quick_extract_bundle(
        is_low_value_auto_schema_field_name=is_low_value_auto_schema_field_name,
        coerce_field_type=schema_primitives_bundle.coerce_field_type,
        is_low_value_quick_fallback_value=value_guard_bundle.is_low_value_quick_fallback_value,
        normalize_bbox=geometry_bundle.normalize_bbox,
    )
    quality_bundle = build_module2_main_quality_bundle(
        visual_chain_required=policy_bundle.visual_chain_required,
    )
    progress_bundle = build_module2_main_progress_bundle(getenv=getenv)
    service_bundle = build_module2_main_service_bundle(
        logger=logger,
        outbox_repository=repository_bundle.module4_sync_outbox_repository,
        assistant_repository=repository_bundle.assistant_session_repository,
        artifact_root_factory=policy_bundle.artifact_root_dir,
        convert_word_to_pdf=document_io_bundle.convert_word_to_pdf_with_timeout,
        office_preview_timeout_sec_factory=policy_bundle.office_preview_timeout_sec,
        module4_sync_config_runtime=support_bundle.module4_sync_config_runtime,
        module4_sync_metrics_runtime=support_bundle.module4_sync_metrics_runtime,
        module4_sync_task_runtime=support_bundle.module4_sync_task_runtime,
        normalize_bbox=geometry_bundle.normalize_bbox,
        page_from_bbox=geometry_bundle.page_from_bbox,
        is_meaningful_bbox=geometry_bundle.is_meaningful_bbox,
        utcnow_factory=policy_bundle.utcnow_factory,
    )
    extraction_bundle = build_module2_main_extraction_bundle(
        module2_root=module2_root,
        check_cache=repository_bundle.extraction_cache_repository.check_cache,
        find_recent_document_caches=repository_bundle.extraction_cache_repository.find_recent_document_caches,
        graph=graph,
        getenv=getenv,
        bounded_env_int=platform_bundle.bounded_env_int,
        schema_target_fields=schema_primitives_bundle.schema_target_fields,
        field_naming_version=field_naming_version,
        schema_rule_versions=schema_rule_versions,
        auto_schema_logic_revision=auto_schema_logic_revision,
    )
    http_runtime_bundle = build_module2_http_runtime_bundle(
        module2_root=module2_root,
        artifact_root_factory=policy_bundle.artifact_root_dir,
        resolve_module2_path=policy_bundle.resolve_module2_path,
        extraction_job_state_root_factory=policy_bundle.extraction_job_state_root_dir,
        safe_artifact_path=lambda path_fragment: service_bundle.artifact_file_runtime.safe_artifact_path(path_fragment),
        process_single_doc_bytes=process_single_doc_bytes,
        parse_schema_form_json=parse_schema_form_json,
        write_artifact_bytes=service_bundle.artifact_support_runtime.write_artifact_bytes,
        schema_hash=schema_primitives_bundle.schema_hash,
        build_stream_router=extraction_bundle.build_stream_router,
        ensure_provider_ready_for_job_create=lambda: platform_bundle.module2_bootstrap_runtime.ensure_provider_ready_for_job_create(
            build_provider=policy_bundle.build_preflight_provider,
            raise_unavailable=policy_bundle.provider_unavailable_http_exception,
        ),
        module4_tenant=lambda request, explicit="": support_bundle.module4_sync_config_runtime.tenant(
            request,
            explicit,
        ),
        job_state_factory=job_state_factory,
        job_file_state_factory=job_file_state_factory,
        document_validate=document_validate,
        extraction_result_factory=extraction_result_factory,
        document_response_factory=document_response_factory,
        batch_response_factory=batch_response_factory,
        module4_sync_callback_bundle=service_bundle.module4_sync_callback_bundle,
        office_preview_runtime=service_bundle.office_preview_runtime,
        is_word_file=is_word_file,
        office_convert_enabled=policy_bundle.office_convert_enabled,
        summarize_document_payload=service_bundle.document_tools_support_runtime.summarize_document_payload,
        build_document_trace_hits=service_bundle.document_trace_hits_runtime.build_document_trace_hits,
        filter_trace_hits=service_bundle.document_tools_support_runtime.filter_trace_hits,
        summarize_response_factory=summarize_response_factory,
        trace_locate_response_factory=trace_locate_response_factory,
        bounded_env_int=platform_bundle.bounded_env_int,
        logger=logger,
    )
    return Module2MainFoundationBundle(
        repository_bundle=repository_bundle,
        graph=graph,
        support_bundle=support_bundle,
        platform_bundle=platform_bundle,
        schema_primitives_bundle=schema_primitives_bundle,
        policy_bundle=policy_bundle,
        geometry_bundle=geometry_bundle,
        document_io_bundle=document_io_bundle,
        value_guard_bundle=value_guard_bundle,
        nonpdf_bundle=nonpdf_bundle,
        quick_extract_bundle=quick_extract_bundle,
        quality_bundle=quality_bundle,
        progress_bundle=progress_bundle,
        service_bundle=service_bundle,
        extraction_bundle=extraction_bundle,
        http_runtime_bundle=http_runtime_bundle,
    )


def build_module2_default_bootstrap_components(
    *,
    logger: Any,
    module2_root: Path,
    module2_database_dsn: str | None = None,
    getenv: GetEnvFn = os.getenv,
    python_executable: str | None = None,
    python_prefix: str | None = None,
    python_base_prefix: str | None = None,
    python_venv_active: bool | None = None,
    auto_schema_logic_revision: str = _DEFAULT_AUTO_SCHEMA_LOGIC_REVISION,
) -> Module2BootstrapComponents:
    schema_noise_rules = load_schema_noise_rules()
    field_type_rules = load_field_type_rules()
    schema_selection_rules = load_schema_selection_rules()
    schema_semantic_rules = load_schema_semantic_rules()
    schema_coverage_profiles = load_schema_coverage_profiles()
    resolved_schema_rule_versions = schema_rule_versions()
    resolved_module2_database_dsn = module2_database_dsn or str(
        getenv("MODULE2_DATABASE_DSN", "postgresql://postgres@127.0.0.1:5432/a23")
        or "postgresql://postgres@127.0.0.1:5432/a23"
    )

    document_workflow_runtime: Any = None
    schema_request_bundle: Any = None
    schema_fields_bundle: Any = None

    foundation_bundle = build_module2_main_foundation_bundle(
        logger=logger,
        module2_root=module2_root,
        module2_database_dsn=resolved_module2_database_dsn,
        extraction_storage_factory=ExtractionStorage,
        extraction_graph_factory=ExtractionGraph,
        getenv=getenv,
        parse_document_in_subprocess=parse_document_in_subprocess,
        build_module2_llm_provider_fn=build_module2_llm_provider,
        convert_word_bytes_to_pdf_fn=convert_word_bytes_to_pdf,
        convert_doc_bytes_to_docx_fn=convert_doc_bytes_to_docx,
        is_word_file=is_word_file,
        auto_schema_stopwords_en=set(schema_noise_rules["auto_schema_stopwords_en"]),
        field_naming_version=FIELD_NAMING_VERSION,
        schema_rule_versions=resolved_schema_rule_versions,
        auto_schema_logic_revision=auto_schema_logic_revision,
        job_state_factory=ExtractionJobState,
        job_file_state_factory=ExtractionJobFileState,
        document_validate=lambda item: DocumentExtractionResponse.model_validate(item),
        extraction_result_factory=ExtractionResult,
        document_response_factory=DocumentExtractionResponse,
        batch_response_factory=BatchExtractionResponse,
        summarize_response_factory=SummarizeResponse,
        trace_locate_response_factory=TraceLocateResponse,
        process_single_doc_bytes=lambda **kwargs: document_workflow_runtime.execute(**kwargs),
        parse_schema_form_json=lambda raw_schema: schema_request_bundle.parse_schema_form_json(raw_schema),
        is_low_value_auto_schema_field_name=lambda field_name: schema_fields_bundle.is_low_value_auto_schema_field_name(
            field_name
        ),
    )

    schema_pipeline_bundle = build_module2_main_schema_pipeline_bundle_from_rules(
        graph=foundation_bundle.graph,
        getenv=getenv,
        main_schema_primitives_bundle=foundation_bundle.schema_primitives_bundle,
        main_quality_bundle=foundation_bundle.quality_bundle,
        main_quick_extract_bundle=foundation_bundle.quick_extract_bundle,
        normalize_field_name_fn=normalize_field_name,
        canonicalize_schema_fields_fn=canonicalize_schema_fields,
        normalize_schema_contracts_fn=normalize_schema_contracts,
        infer_rule_backed_schema_fields=infer_rule_backed_schema_fields,
        is_word_file=is_word_file,
        schema_noise_rules=schema_noise_rules,
        schema_semantic_rules=schema_semantic_rules,
        schema_selection_rules=schema_selection_rules,
        field_type_rules=field_type_rules,
        schema_coverage_profiles=schema_coverage_profiles,
    )
    schema_request_bundle = schema_pipeline_bundle.schema_request_bundle
    schema_fields_bundle = schema_pipeline_bundle.schema_fields_bundle

    workflow_bundle = build_module2_main_workflow_bundle(
        build_stream_router=foundation_bundle.extraction_bundle.build_stream_router,
        cached_extraction_restore_runtime=foundation_bundle.support_bundle.cached_extraction_restore_runtime,
        normalize_soft_warnings=foundation_bundle.nonpdf_bundle.normalize_soft_warnings,
        promote_visual_diagnostics=foundation_bundle.nonpdf_bundle.promote_visual_diagnostics,
        persist_assistant_payload_artifact=foundation_bundle.service_bundle.artifact_support_runtime.persist_assistant_payload_artifact,
        persist_field_results_artifact=foundation_bundle.service_bundle.artifact_support_runtime.persist_field_results_artifact,
        extraction_result_factory=ExtractionResult,
        document_response_factory=DocumentExtractionResponse,
        save_extraction_result=foundation_bundle.repository_bundle.extraction_cache_repository.save_extraction_result,
        document_input_plan_runtime=foundation_bundle.support_bundle.document_input_plan_runtime,
        word_input_preparation_runtime=foundation_bundle.support_bundle.word_input_preparation_runtime,
        parse_preparation_runtime=foundation_bundle.support_bundle.parse_preparation_runtime,
        document_parse_recovery_runtime=foundation_bundle.support_bundle.document_parse_recovery_runtime,
        schema_session_runtime=foundation_bundle.support_bundle.schema_session_runtime,
        extraction_graph_runtime=foundation_bundle.support_bundle.extraction_graph_runtime,
        preflight_nonpdf_profile=foundation_bundle.nonpdf_bundle.preflight_nonpdf_profile,
        resolve_nonpdf_budgets=foundation_bundle.nonpdf_bundle.resolve_nonpdf_budgets,
        resolve_nonpdf_plan=foundation_bundle.support_bundle.nonpdf_budget_runtime.resolve_nonpdf_plan,
        apply_field_extract_timeout_floor=foundation_bundle.support_bundle.nonpdf_budget_runtime.apply_field_extract_timeout_floor,
        word_pdf_required=foundation_bundle.policy_bundle.word_pdf_required,
        is_word_file=is_word_file,
        office_convert_enabled=foundation_bundle.policy_bundle.office_convert_enabled,
        docx_native_recovery_enabled=foundation_bundle.policy_bundle.docx_native_recovery_enabled,
        validate_word_preconditions=foundation_bundle.support_bundle.word_conversion_policy_runtime.validate_preconditions,
        resolve_conversion_timeout=foundation_bundle.support_bundle.nonpdf_budget_runtime.resolve_conversion_timeout,
        build_word_pdf_success=foundation_bundle.support_bundle.word_conversion_policy_runtime.build_word_pdf_success,
        resolve_word_pdf_failure=foundation_bundle.support_bundle.word_conversion_policy_runtime.resolve_word_pdf_failure,
        build_doc_to_docx_success=foundation_bundle.support_bundle.word_conversion_policy_runtime.build_doc_to_docx_success,
        build_doc_to_docx_failure=foundation_bundle.support_bundle.word_conversion_policy_runtime.build_doc_to_docx_failure,
        word_pdf_semaphore=foundation_bundle.extraction_bundle.extraction_word_pdf_semaphore,
        ensure_preview_job_started=foundation_bundle.service_bundle.office_preview_runtime.ensure_job_started,
        await_or_reuse_pdf=foundation_bundle.service_bundle.office_preview_runtime.await_or_reuse_pdf,
        run_with_progress_heartbeat=foundation_bundle.progress_bundle.run_with_progress_heartbeat,
        convert_doc_to_docx_with_timeout=foundation_bundle.document_io_bundle.convert_doc_to_docx_with_timeout,
        tighten_parse_budgets_before_parse=foundation_bundle.support_bundle.nonpdf_budget_runtime.tighten_parse_budgets_before_parse,
        build_parse_session=foundation_bundle.support_bundle.document_parse_session_runtime.build_session,
        build_parse_attempt_runner=foundation_bundle.support_bundle.document_parse_attempt_runtime.build_runner,
        acquire_parse_execution_slots=foundation_bundle.extraction_bundle.acquire_parse_execution_slots,
        run_parse_in_process_pool=foundation_bundle.platform_bundle.run_parse_in_process_pool,
        resolve_parse_progress_ramp_sec=foundation_bundle.progress_bundle.resolve_parse_progress_ramp_sec,
        unpack_parse_output=foundation_bundle.support_bundle.document_parse_attempt_runtime.unpack_parse_output,
        visual_parse_policy_runtime=foundation_bundle.support_bundle.visual_parse_policy_runtime,
        parse_fallback_coordinator_runtime=foundation_bundle.support_bundle.parse_fallback_coordinator_runtime,
        docx_native_recovery_runtime=foundation_bundle.support_bundle.docx_native_recovery_runtime,
        fasttrack_fallback_runtime=foundation_bundle.support_bundle.fasttrack_fallback_runtime,
        visual_chain_required=foundation_bundle.policy_bundle.visual_chain_required,
        visual_strict_mode=foundation_bundle.policy_bundle.visual_strict_mode,
        disable_fasttrack_fallback=foundation_bundle.policy_bundle.disable_fasttrack_fallback,
        build_visual_chain_contract=foundation_bundle.quality_bundle.build_visual_chain_contract,
        extraction_llm_semaphore=foundation_bundle.extraction_bundle.extraction_llm_semaphore,
        detect_domain_template=detect_domain_template,
        extract_text_for_schema=schema_pipeline_bundle.schema_context_bundle.extract_text_for_schema,
        resolve_effective_schema=schema_pipeline_bundle.schema_resolution_bundle.resolve_effective_schema,
        resolve_dynamic_extract_timeout_sec=schema_pipeline_bundle.schema_timeout_bundle.resolve_dynamic_extract_timeout_sec,
        run_graph=foundation_bundle.graph.run,
        resolve_extract_progress_ramp_sec=foundation_bundle.progress_bundle.resolve_extract_progress_ramp_sec,
        quick_extract_from_tables=foundation_bundle.quick_extract_bundle.quick_extract_from_tables,
        disable_quick_table_fallback=foundation_bundle.policy_bundle.disable_quick_table_fallback,
        xlsx_workbook_artifact_runtime=foundation_bundle.service_bundle.xlsx_workbook_artifact_runtime,
        logger=logger,
        post_parse_quality_runtime=foundation_bundle.support_bundle.post_parse_quality_runtime,
        post_parse_artifact_runtime=foundation_bundle.support_bundle.post_parse_artifact_runtime,
        diagnostics_builder_runtime=foundation_bundle.support_bundle.diagnostics_builder_runtime,
        extraction_response_runtime=foundation_bundle.support_bundle.extraction_response_runtime,
        graph_diagnostics_factory=lambda: foundation_bundle.graph.diagnostics() if hasattr(foundation_bundle.graph, "diagnostics") else {},
        current_extraction_logic_version=foundation_bundle.extraction_bundle.current_extraction_logic_version,
        current_extraction_logic_components=foundation_bundle.extraction_bundle.current_extraction_logic_components,
        field_naming_version=FIELD_NAMING_VERSION,
        schema_rule_versions=resolved_schema_rule_versions,
        is_low_value_auto_schema_field_name=schema_pipeline_bundle.schema_fields_bundle.is_low_value_auto_schema_field_name,
        has_meaningful_value=foundation_bundle.quality_bundle.has_meaningful_value,
        is_low_value_quick_fallback_value=foundation_bundle.value_guard_bundle.is_low_value_quick_fallback_value,
        is_recoverable_timeout_error=foundation_bundle.nonpdf_bundle.is_recoverable_timeout_error,
        filter_low_value_auto_results=schema_pipeline_bundle.result_filter_bundle.filter_low_value_auto_results,
        effective_quality_schema_fields=schema_pipeline_bundle.result_filter_bundle.effective_quality_schema_fields,
        result_quality_snapshot=foundation_bundle.quality_bundle.result_quality_snapshot,
        strip_recovered_extract_warnings=foundation_bundle.nonpdf_bundle.strip_recovered_extract_warnings,
        write_artifact_bytes=foundation_bundle.service_bundle.artifact_support_runtime.write_artifact_bytes,
        crop_pdf_region_png=foundation_bundle.document_io_bundle.crop_pdf_region_png,
        build_document_trace_hits=foundation_bundle.service_bundle.document_trace_hits_runtime.build_document_trace_hits,
        trace_stats_builder=foundation_bundle.service_bundle.trace_semantics_runtime.build_trace_stats,
        build_polymorphic_links=foundation_bundle.service_bundle.polymorphic_links_runtime.build_links,
        count_table_cells=foundation_bundle.quality_bundle.count_table_cells,
        table_quality_avg=foundation_bundle.quality_bundle.table_quality_avg,
        table_source_counts=foundation_bundle.quality_bundle.table_source_counts,
        count_figure_dataframe_cells=foundation_bundle.quality_bundle.count_figure_dataframe_cells,
        figure_pages=foundation_bundle.quality_bundle.figure_pages,
        figure_source_counts=foundation_bundle.quality_bundle.figure_source_counts,
        persist_assistant1_source_markdown_artifact=foundation_bundle.service_bundle.artifact_support_runtime.persist_assistant1_source_markdown_artifact,
    )
    document_workflow_runtime = workflow_bundle.document_workflow_runtime

    resolved_python_executable = python_executable or sys.executable
    resolved_python_prefix = python_prefix or sys.prefix
    resolved_python_base_prefix = python_base_prefix or sys.base_prefix
    resolved_python_venv_active = (
        python_venv_active if python_venv_active is not None else resolved_python_prefix != resolved_python_base_prefix
    )

    entry_bundle = build_module2_main_entry_bundle(
        app_lifecycle_runtime=foundation_bundle.support_bundle.module2_app_lifecycle_runtime,
        cache_clear_runtime=foundation_bundle.http_runtime_bundle.cache_clear_runtime,
        artifact_file_runtime=foundation_bundle.service_bundle.artifact_file_runtime,
        health_runtime=foundation_bundle.support_bundle.module2_health_runtime,
        module2_bootstrap_runtime=foundation_bundle.platform_bundle.module2_bootstrap_runtime,
        startup_task_runtime=foundation_bundle.support_bundle.startup_task_runtime,
        runtime_state_repository=foundation_bundle.repository_bundle.runtime_state_repository,
        office_preview_runtime=foundation_bundle.service_bundle.office_preview_runtime,
        module4_sync_config_runtime=foundation_bundle.support_bundle.module4_sync_config_runtime,
        module4_sync_outbox_runtime=foundation_bundle.service_bundle.module4_sync_outbox_runtime,
        module4_sync_metrics_runtime=foundation_bundle.support_bundle.module4_sync_metrics_runtime,
        module4_sync_task_runtime=foundation_bundle.support_bundle.module4_sync_task_runtime,
        extraction_job_runtime=foundation_bundle.http_runtime_bundle.extraction_job_runtime,
        extraction_jobs=foundation_bundle.http_runtime_bundle.extraction_jobs,
        extraction_lock=foundation_bundle.http_runtime_bundle.extraction_lock,
        extraction_job_runtime_specs=foundation_bundle.http_runtime_bundle.extraction_job_runtime_specs,
        extraction_job_tasks=foundation_bundle.http_runtime_bundle.extraction_job_tasks,
        extraction_job_persist_markers=foundation_bundle.http_runtime_bundle.extraction_job_persist_markers,
        clear_mineru_process_runtime_cache=clear_mineru_process_runtime_cache,
        reset_process_pool=foundation_bundle.platform_bundle.reset_process_pool,
        build_preflight_provider=foundation_bundle.policy_bundle.build_preflight_provider,
        run_parse_in_process_pool=foundation_bundle.platform_bundle.run_parse_in_process_pool,
        schedule_module4_sync_outbox=foundation_bundle.service_bundle.module4_sync_callback_bundle.schedule_outbox,
        shutdown_process_pool=lambda: foundation_bundle.platform_bundle.shutdown_process_pool(
            foundation_bundle.platform_bundle.current_process_pool(),
            "app_shutdown",
        ),
        python_executable=resolved_python_executable,
        python_prefix=resolved_python_prefix,
        python_base_prefix=resolved_python_base_prefix,
        python_venv_active=resolved_python_venv_active,
        extraction_request_runtime=foundation_bundle.http_runtime_bundle.extraction_request_runtime,
        office_preview_request_runtime=foundation_bundle.http_runtime_bundle.office_preview_request_runtime,
        document_tools_runtime=foundation_bundle.http_runtime_bundle.document_tools_runtime,
        assistant1_runtime=foundation_bundle.service_bundle.assistant1_runtime,
        list_outbox_rows=foundation_bundle.service_bundle.module4_sync_callback_bundle.list_outbox_rows,
        get_outbox_row=foundation_bundle.service_bundle.module4_sync_callback_bundle.get_outbox_row,
        build_list_response=foundation_bundle.service_bundle.module4_sync_callback_bundle.build_list_response,
        serialize_outbox_row=foundation_bundle.service_bundle.module4_sync_callback_bundle.serialize_outbox_row,
        metrics_snapshot=foundation_bundle.service_bundle.module4_sync_callback_bundle.metrics_snapshot,
    )

    return Module2BootstrapComponents(
        foundation_bundle=foundation_bundle,
        schema_pipeline_bundle=schema_pipeline_bundle,
        workflow_bundle=workflow_bundle,
        entry_bundle=entry_bundle,
        schema_noise_rules=schema_noise_rules,
        field_type_rules=field_type_rules,
        schema_selection_rules=schema_selection_rules,
        schema_semantic_rules=schema_semantic_rules,
        schema_coverage_profiles=schema_coverage_profiles,
        schema_rule_versions=resolved_schema_rule_versions,
        auto_schema_logic_revision=auto_schema_logic_revision,
    )
