from .app_callback_bundle import Module2AppCallbackBundle, build_module2_app_callback_bundle
from .artifact_support_runtime import ArtifactSupportRuntime
from .cache_clear import Module2CacheClearRuntime
from ..services.document.tools import (
    DocumentToolsRuntime,
    DocumentToolsSupportRuntime,
    TraceLocatorPayloadRuntime,
    PolymorphicLinksRuntime,
    TraceLocatorTextRuntime,
    TraceSemanticsRuntime,
)
from .document_trace_hits_runtime import DocumentTraceHitsRuntime
from ..services.extraction.executor import ExtractionJobExecutor
from ..services.extraction.job import ExtractionJobFileState, ExtractionJobRuntime, ExtractionJobState
from ..services.extraction.request import ExtractionRequestRuntime
from .http_runtime_bundle import Module2HttpRuntimeBundle, build_module2_http_runtime_bundle
from .main_extraction_bundle import Module2MainExtractionBundle, build_module2_main_extraction_bundle
from .main_document_io_bundle import Module2MainDocumentIoBundle, build_module2_main_document_io_bundle
from .main_geometry_bundle import Module2MainGeometryBundle, build_module2_main_geometry_bundle
from .main_nonpdf_bundle import Module2MainNonPdfBundle, build_module2_main_nonpdf_bundle
from .main_policy_bundle import Module2MainPolicyBundle, build_module2_main_policy_bundle
from .main_platform_bundle import Module2MainPlatformBundle, build_module2_main_platform_bundle
from .main_progress_bundle import Module2MainProgressBundle, build_module2_main_progress_bundle
from .main_quick_extract_bundle import (
    Module2MainQuickExtractBundle,
    Module2MainValueGuardBundle,
    build_module2_main_quick_extract_bundle,
    build_module2_main_value_guard_bundle,
)
from .main_quality_bundle import Module2MainQualityBundle, build_module2_main_quality_bundle
from .main_result_filter_bundle import Module2MainResultFilterBundle, build_module2_main_result_filter_bundle
from .main_schema_context_bundle import Module2MainSchemaContextBundle, build_module2_main_schema_context_bundle
from .main_schema_fields_bundle import Module2MainSchemaFieldsBundle, build_module2_main_schema_fields_bundle
from .main_schema_inference_bundle import Module2MainSchemaInferenceBundle, build_module2_main_schema_inference_bundle
from .main_schema_llm_bundle import Module2MainSchemaLlmBundle, build_module2_main_schema_llm_bundle
from .main_schema_primitives_bundle import (
    Module2MainSchemaPrimitivesBundle,
    Module2MainSchemaRequestBundle,
    Module2MainSchemaTimeoutBundle,
    build_module2_main_schema_primitives_bundle,
    build_module2_main_schema_request_bundle,
    build_module2_main_schema_timeout_bundle,
)
from .main_schema_resolution_bundle import (
    Module2MainSchemaResolutionBundle,
    build_module2_main_schema_resolution_bundle,
)
from .main_schema_semantics_bundle import Module2MainSchemaSemanticsBundle, build_module2_main_schema_semantics_bundle
from .main_schema_selection_bundle import Module2MainSchemaSelectionBundle, build_module2_main_schema_selection_bundle
from .main_workflow_bundle import Module2MainWorkflowBundle, build_module2_main_workflow_bundle
from .sync_callback_bundle import Module4SyncCallbackBundle, build_module4_sync_callback_bundle
from ..services.preview.office import OfficePreviewJob, OfficePreviewRequestRuntime, OfficePreviewRuntime

__all__ = [
    "DocumentToolsRuntime",
    "DocumentTraceHitsRuntime",
    "DocumentToolsSupportRuntime",
    "TraceLocatorPayloadRuntime",
    "TraceLocatorTextRuntime",
    "ArtifactSupportRuntime",
    "ExtractionJobExecutor",
    "ExtractionJobFileState",
    "ExtractionJobRuntime",
    "ExtractionJobState",
    "ExtractionRequestRuntime",
    "Module2AppCallbackBundle",
    "Module2HttpRuntimeBundle",
    "Module2BootstrapRuntimeBundle",
    "Module2MainExtractionBundle",
    "Module2MainFoundationBundle",
    "Module2BootstrapComponents",
    "Module2MainDocumentIoBundle",
    "Module2MainGeometryBundle",
    "Module2MainEntryBundle",
    "Module2MainNonPdfBundle",
    "Module2MainPolicyBundle",
    "Module2MainPlatformBundle",
    "Module2MainProgressBundle",
    "Module2MainQuickExtractBundle",
    "Module2MainQualityBundle",
    "Module2MainResultFilterBundle",
    "Module2MainSchemaContextBundle",
    "Module2MainSchemaFieldsBundle",
    "Module2MainSchemaInferenceBundle",
    "Module2MainSchemaLlmBundle",
    "Module2MainSchemaPipelineBundle",
    "Module2MainSchemaPrimitivesBundle",
    "Module2MainSchemaResolutionBundle",
    "Module2MainSchemaTimeoutBundle",
    "Module2MainSchemaRequestBundle",
    "Module2MainSchemaSemanticsBundle",
    "Module2MainSchemaSelectionBundle",
    "Module2MainServiceBundle",
    "Module2MainSupportBundle",
    "Module2MainValueGuardBundle",
    "Module2MainWorkflowBundle",
    "Module4SyncCallbackBundle",
    "Module2CacheClearRuntime",
    "OfficePreviewJob",
    "OfficePreviewRuntime",
    "OfficePreviewRequestRuntime",
    "PolymorphicLinksRuntime",
    "TraceSemanticsRuntime",
    "build_module2_app_callback_bundle",
    "build_module2_bootstrap_runtime_bundle",
    "build_module2_http_runtime_bundle",
    "build_module2_main_extraction_bundle",
    "build_module2_main_foundation_bundle",
    "build_module2_default_bootstrap_components",
    "build_module2_main_document_io_bundle",
    "build_module2_main_geometry_bundle",
    "build_module2_main_entry_bundle",
    "build_module2_main_nonpdf_bundle",
    "build_module2_main_policy_bundle",
    "build_module2_main_platform_bundle",
    "build_module2_main_progress_bundle",
    "build_module2_main_quick_extract_bundle",
    "build_module2_main_quality_bundle",
    "build_module2_main_result_filter_bundle",
    "build_module2_main_schema_context_bundle",
    "build_module2_main_schema_fields_bundle",
    "build_module2_main_schema_inference_bundle",
    "build_module2_main_schema_llm_bundle",
    "build_module2_main_schema_pipeline_bundle",
    "build_module2_main_schema_pipeline_bundle_from_rules",
    "build_module2_main_schema_primitives_bundle",
    "build_module2_main_schema_resolution_bundle",
    "build_module2_main_schema_timeout_bundle",
    "build_module2_main_schema_request_bundle",
    "build_module2_main_schema_semantics_bundle",
    "build_module2_main_schema_selection_bundle",
    "build_module2_main_service_bundle",
    "build_module2_main_support_bundle",
    "build_module2_main_value_guard_bundle",
    "build_module2_main_workflow_bundle",
    "build_module4_sync_callback_bundle",
]


def __getattr__(name: str):
    if name in {
        "Module2MainFoundationBundle",
        "build_module2_main_foundation_bundle",
        "Module2BootstrapComponents",
        "build_module2_default_bootstrap_components",
        "Module2MainEntryBundle",
        "build_module2_main_entry_bundle",
    }:
        from ..composition.foundation import (
            Module2BootstrapComponents,
            Module2MainFoundationBundle,
            build_module2_default_bootstrap_components,
            build_module2_main_foundation_bundle,
        )
        from ..services.extraction.entry_builder import (
            Module2MainEntryBundle,
            build_module2_main_entry_bundle,
        )

        mapping = {
            "Module2MainFoundationBundle": Module2MainFoundationBundle,
            "build_module2_main_foundation_bundle": build_module2_main_foundation_bundle,
            "Module2BootstrapComponents": Module2BootstrapComponents,
            "build_module2_default_bootstrap_components": build_module2_default_bootstrap_components,
            "Module2MainEntryBundle": Module2MainEntryBundle,
            "build_module2_main_entry_bundle": build_module2_main_entry_bundle,
        }
        return mapping[name]
    if name in {
        "Module2MainServiceBundle",
        "build_module2_main_service_bundle",
    }:
        from ..services.extraction.service_builder import (
            Module2MainServiceBundle,
            build_module2_main_service_bundle,
        )

        mapping = {
            "Module2MainServiceBundle": Module2MainServiceBundle,
            "build_module2_main_service_bundle": build_module2_main_service_bundle,
        }
        return mapping[name]
    if name in {
        "Module2MainSupportBundle",
        "Module2BootstrapRuntimeBundle",
        "build_module2_main_support_bundle",
        "build_module2_bootstrap_runtime_bundle",
    }:
        from ..services.extraction.support_builder import (
            Module2BootstrapRuntimeBundle,
            Module2MainSupportBundle,
            build_module2_bootstrap_runtime_bundle,
            build_module2_main_support_bundle,
        )

        mapping = {
            "Module2MainSupportBundle": Module2MainSupportBundle,
            "Module2BootstrapRuntimeBundle": Module2BootstrapRuntimeBundle,
            "build_module2_main_support_bundle": build_module2_main_support_bundle,
            "build_module2_bootstrap_runtime_bundle": build_module2_bootstrap_runtime_bundle,
        }
        return mapping[name]
    if name in {
        "Module2MainSchemaPipelineBundle",
        "build_module2_main_schema_pipeline_bundle",
        "build_module2_main_schema_pipeline_bundle_from_rules",
    }:
        from ..services.schema.schema_pipeline_builder import (
            Module2MainSchemaPipelineBundle,
            build_module2_main_schema_pipeline_bundle,
            build_module2_main_schema_pipeline_bundle_from_rules,
        )

        mapping = {
            "Module2MainSchemaPipelineBundle": Module2MainSchemaPipelineBundle,
            "build_module2_main_schema_pipeline_bundle": build_module2_main_schema_pipeline_bundle,
            "build_module2_main_schema_pipeline_bundle_from_rules": build_module2_main_schema_pipeline_bundle_from_rules,
        }
        return mapping[name]
    raise AttributeError(name)
