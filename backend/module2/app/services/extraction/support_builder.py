from __future__ import annotations

"""Support/runtime bundle builders for module2 extraction service layer."""

from dataclasses import dataclass
from typing import Any, Callable

from ...core.format.docx_native_recovery_runtime import DocxNativeRecoveryRuntime
from ...core.format.nonpdf_budget_runtime import NonPdfBudgetRuntime
from ...core.format.word_input_preparation_runtime import WordConversionPolicyRuntime, WordInputPreparationRuntime
from ...core.integration.app_support_runtime import (
    Module2AppLifecycleRuntime,
    Module2HealthRuntime,
    ProviderPreflightRuntime,
    StartupTaskRuntime,
)
from ...core.integration.cached_extraction_restore_runtime import CachedExtractionRestoreRuntime
from ...core.integration.mineru_warmup_runtime import MineruWarmupRuntime
from ...core.integration.module2_bootstrap_runtime import Module2BootstrapRuntime
from ...core.integration.module4_sync_config_runtime import Module4SyncConfigRuntime
from ...core.integration.module4_sync_metrics_runtime import Module4SyncMetricsRuntime
from ...core.integration.module4_sync_task_runtime import Module4SyncTaskRuntime
from ...core.pipeline.document_parse_recovery_runtime import (
    DocumentParseRecoveryRuntime,
    FastTrackFallbackRuntime,
    ParseFallbackCoordinatorRuntime,
    VisualParsePolicyRuntime,
)
from ...core.pipeline.document_pipeline_runtime import (
    DocumentInputPlanRuntime,
    DocumentParseAttemptRuntime,
    DocumentParseSessionRuntime,
    ParsePreparationRuntime,
)
from ...core.pipeline.document_postprocess_runtime import (
    DiagnosticsBuilderRuntime,
    ExtractionResponseRuntime,
    PostParseArtifactRuntime,
    PostParseQualityRuntime,
)
from ...core.pipeline.document_process_pool_runtime import DocumentProcessPoolRuntime
from ...core.pipeline.extraction_graph_runtime import ExtractionGraphRuntime
from ...core.schema.schema_session_runtime import SchemaSessionRuntime


@dataclass(frozen=True)
class Module2MainSupportBundle:
    module4_sync_task_runtime: Module4SyncTaskRuntime
    module4_sync_metrics_runtime: Module4SyncMetricsRuntime
    module4_sync_config_runtime: Module4SyncConfigRuntime
    module2_health_runtime: Module2HealthRuntime
    module2_app_lifecycle_runtime: Module2AppLifecycleRuntime
    startup_task_runtime: StartupTaskRuntime
    mineru_warmup_runtime: MineruWarmupRuntime
    provider_preflight_runtime: ProviderPreflightRuntime
    cached_extraction_restore_runtime: CachedExtractionRestoreRuntime
    nonpdf_budget_runtime: NonPdfBudgetRuntime
    visual_parse_policy_runtime: VisualParsePolicyRuntime
    word_conversion_policy_runtime: WordConversionPolicyRuntime
    word_input_preparation_runtime: WordInputPreparationRuntime
    document_parse_attempt_runtime: DocumentParseAttemptRuntime
    document_input_plan_runtime: DocumentInputPlanRuntime
    document_parse_recovery_runtime: DocumentParseRecoveryRuntime
    document_parse_session_runtime: DocumentParseSessionRuntime
    diagnostics_builder_runtime: DiagnosticsBuilderRuntime
    docx_native_recovery_runtime: DocxNativeRecoveryRuntime
    extraction_response_runtime: ExtractionResponseRuntime
    extraction_graph_runtime: ExtractionGraphRuntime
    fasttrack_fallback_runtime: FastTrackFallbackRuntime
    post_parse_artifact_runtime: PostParseArtifactRuntime
    post_parse_quality_runtime: PostParseQualityRuntime
    parse_fallback_coordinator_runtime: ParseFallbackCoordinatorRuntime
    parse_preparation_runtime: ParsePreparationRuntime
    schema_session_runtime: SchemaSessionRuntime


@dataclass(frozen=True)
class Module2BootstrapRuntimeBundle:
    document_process_pool_runtime: DocumentProcessPoolRuntime
    module2_bootstrap_runtime: Module2BootstrapRuntime


def build_module2_main_support_bundle(*, logger: Any) -> Module2MainSupportBundle:
    return Module2MainSupportBundle(
        module4_sync_task_runtime=Module4SyncTaskRuntime(logger=logger),
        module4_sync_metrics_runtime=Module4SyncMetricsRuntime(),
        module4_sync_config_runtime=Module4SyncConfigRuntime(),
        module2_health_runtime=Module2HealthRuntime(),
        module2_app_lifecycle_runtime=Module2AppLifecycleRuntime(),
        startup_task_runtime=StartupTaskRuntime(),
        mineru_warmup_runtime=MineruWarmupRuntime(logger=logger),
        provider_preflight_runtime=ProviderPreflightRuntime(),
        cached_extraction_restore_runtime=CachedExtractionRestoreRuntime(),
        nonpdf_budget_runtime=NonPdfBudgetRuntime(),
        visual_parse_policy_runtime=VisualParsePolicyRuntime(),
        word_conversion_policy_runtime=WordConversionPolicyRuntime(),
        word_input_preparation_runtime=WordInputPreparationRuntime(),
        document_parse_attempt_runtime=DocumentParseAttemptRuntime(),
        document_input_plan_runtime=DocumentInputPlanRuntime(),
        document_parse_recovery_runtime=DocumentParseRecoveryRuntime(),
        document_parse_session_runtime=DocumentParseSessionRuntime(),
        diagnostics_builder_runtime=DiagnosticsBuilderRuntime(),
        docx_native_recovery_runtime=DocxNativeRecoveryRuntime(),
        extraction_response_runtime=ExtractionResponseRuntime(),
        extraction_graph_runtime=ExtractionGraphRuntime(),
        fasttrack_fallback_runtime=FastTrackFallbackRuntime(),
        post_parse_artifact_runtime=PostParseArtifactRuntime(),
        post_parse_quality_runtime=PostParseQualityRuntime(),
        parse_fallback_coordinator_runtime=ParseFallbackCoordinatorRuntime(),
        parse_preparation_runtime=ParsePreparationRuntime(),
        schema_session_runtime=SchemaSessionRuntime(),
    )


def build_module2_bootstrap_runtime_bundle(
    *,
    logger: Any,
    provider_preflight_runtime: ProviderPreflightRuntime,
    mineru_warmup_runtime: MineruWarmupRuntime,
    getenv: Callable[[str, str | None], str | None],
    bounded_env_int: Callable[..., int],
    max_workers_provider: Callable[[], int],
    build_pool: Callable[[], Any],
    parse_document_in_subprocess: Callable[..., Any],
) -> Module2BootstrapRuntimeBundle:
    document_process_pool_runtime = DocumentProcessPoolRuntime(
        build_pool=build_pool,
        parse_document_in_subprocess=parse_document_in_subprocess,
        logger=logger,
    )
    module2_bootstrap_runtime = Module2BootstrapRuntime(
        provider_preflight_runtime=provider_preflight_runtime,
        mineru_warmup_runtime=mineru_warmup_runtime,
        logger=logger,
        getenv=getenv,
        bounded_env_int=bounded_env_int,
        max_workers_provider=max_workers_provider,
    )
    return Module2BootstrapRuntimeBundle(
        document_process_pool_runtime=document_process_pool_runtime,
        module2_bootstrap_runtime=module2_bootstrap_runtime,
    )
