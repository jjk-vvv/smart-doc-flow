from __future__ import annotations

from ..composition.app_callback_bundle import Module2AppCallbackBundle, build_module2_app_callback_bundle
from ..composition.http_runtime_bundle import Module2HttpRuntimeBundle, build_module2_http_runtime_bundle
from ..services.document.tools import (
    DocumentToolsRuntime,
    DocumentToolsSupportRuntime,
    PolymorphicLinksRuntime,
    TraceLocatorPayloadRuntime,
    TraceLocatorTextRuntime,
    TraceSemanticsRuntime,
)
from ..services.extraction.document_io_builder import Module2MainDocumentIoBundle, build_module2_main_document_io_bundle
from ..services.extraction.extraction_builder import Module2MainExtractionBundle, build_module2_main_extraction_bundle
from ..services.extraction.executor import ExtractionJobExecutionService
from ..services.extraction.geometry_builder import Module2MainGeometryBundle, build_module2_main_geometry_bundle
from ..services.extraction.job import ExtractionJobFileState, ExtractionJobRuntime, ExtractionJobState
from ..services.extraction.nonpdf_builder import Module2MainNonPdfBundle, build_module2_main_nonpdf_bundle
from ..services.extraction.platform_builder import Module2MainPlatformBundle, build_module2_main_platform_bundle
from ..services.extraction.policy_builder import Module2MainPolicyBundle, build_module2_main_policy_bundle
from ..services.extraction.progress_builder import Module2MainProgressBundle, build_module2_main_progress_bundle
from ..services.extraction.quality_builder import Module2MainQualityBundle, build_module2_main_quality_bundle
from ..services.extraction.quick_extract_builder import (
    Module2MainQuickExtractBundle,
    Module2MainValueGuardBundle,
    build_module2_main_quick_extract_bundle,
    build_module2_main_value_guard_bundle,
)
from ..services.extraction.request import ExtractionRequestService
from ..services.extraction.workflow_builder import Module2MainWorkflowBundle, build_module2_main_workflow_bundle
from ..services.preview.office import OfficePreviewJob, OfficePreviewRequestRuntime, OfficePreviewRuntime
from ..services.schema.result_filter_builder import Module2MainResultFilterBundle, build_module2_main_result_filter_bundle
from ..services.schema.schema_context_builder import Module2MainSchemaContextBundle, build_module2_main_schema_context_bundle
from ..services.schema.schema_fields_builder import Module2MainSchemaFieldsBundle, build_module2_main_schema_fields_bundle
from ..services.schema.schema_inference_builder import (
    Module2MainSchemaInferenceBundle,
    build_module2_main_schema_inference_bundle,
)
from ..services.schema.schema_llm_builder import Module2MainSchemaLlmBundle, build_module2_main_schema_llm_bundle
from ..services.schema.schema_primitives_builder import (
    Module2MainSchemaPrimitivesBundle,
    Module2MainSchemaRequestBundle,
    Module2MainSchemaTimeoutBundle,
    build_module2_main_schema_primitives_bundle,
    build_module2_main_schema_request_bundle,
    build_module2_main_schema_timeout_bundle,
)
from ..services.schema.schema_resolution_builder import (
    Module2MainSchemaResolutionBundle,
    build_module2_main_schema_resolution_bundle,
)
from ..services.schema.schema_selection_builder import (
    Module2MainSchemaSelectionBundle,
    build_module2_main_schema_selection_bundle,
)
from ..services.schema.schema_semantics_builder import (
    Module2MainSchemaSemanticsBundle,
    build_module2_main_schema_semantics_bundle,
)
from .artifact_support_runtime import ArtifactSupportRuntime
from .cache_clear import Module2CacheClearRuntime
from .document_trace_hits_runtime import DocumentTraceHitsRuntime
from .sync_callback_bundle import Module4SyncCallbackBundle, build_module4_sync_callback_bundle

# Keep package-level compatibility aliases while canonical names are promoted.
ExtractionJobExecutor = ExtractionJobExecutionService
ExtractionRequestRuntime = ExtractionRequestService

__all__ = [
    "DocumentToolsRuntime",
    "DocumentTraceHitsRuntime",
    "DocumentToolsSupportRuntime",
    "TraceLocatorPayloadRuntime",
    "TraceLocatorTextRuntime",
    "ArtifactSupportRuntime",
    "ExtractionJobExecutionService",
    "ExtractionJobExecutor",
    "ExtractionJobFileState",
    "ExtractionJobRuntime",
    "ExtractionJobState",
    "ExtractionRequestService",
    "ExtractionRequestRuntime",
    "Module2AppCallbackBundle",
    "Module2HttpRuntimeBundle",
    "Module2MainExtractionBundle",
    "Module2MainDocumentIoBundle",
    "Module2MainGeometryBundle",
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
    "Module2MainSchemaPrimitivesBundle",
    "Module2MainSchemaResolutionBundle",
    "Module2MainSchemaTimeoutBundle",
    "Module2MainSchemaRequestBundle",
    "Module2MainSchemaSemanticsBundle",
    "Module2MainSchemaSelectionBundle",
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
    "build_module2_http_runtime_bundle",
    "build_module2_main_extraction_bundle",
    "build_module2_main_document_io_bundle",
    "build_module2_main_geometry_bundle",
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
    "build_module2_main_schema_primitives_bundle",
    "build_module2_main_schema_resolution_bundle",
    "build_module2_main_schema_timeout_bundle",
    "build_module2_main_schema_request_bundle",
    "build_module2_main_schema_semantics_bundle",
    "build_module2_main_schema_selection_bundle",
    "build_module2_main_value_guard_bundle",
    "build_module2_main_workflow_bundle",
    "build_module4_sync_callback_bundle",
]
