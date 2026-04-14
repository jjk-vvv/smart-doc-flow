from __future__ import annotations

"""Service composition bundle builders for module2 extraction service layer."""

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Tuple

from ...assistant_1.persistence import Assistant1PersistenceAdapter
from ...assistant_1.stream_runtime import Assistant1StreamingRuntime
from ...core.integration.artifact_file_runtime import Module2ArtifactFileRuntime
from ...core.integration.module4_sync_outbox_runtime import Module4SyncOutboxRuntime
from ...runtime.artifact_support_runtime import ArtifactSupportRuntime
from ...runtime.document_trace_hits_runtime import DocumentTraceHitsRuntime
from ...runtime.sync_callback_bundle import Module4SyncCallbackBundle, build_module4_sync_callback_bundle
from ...runtime.xlsx_workbook_artifact_runtime import XlsxWorkbookArtifactRuntime
from ..document.tools import (
    DocumentToolsSupportRuntime,
    PolymorphicLinksRuntime,
    TraceLocatorPayloadRuntime,
    TraceLocatorTextRuntime,
    TraceSemanticsRuntime,
)
from ..preview.office import OfficePreviewRuntime


ArtifactRootFactory = Callable[[], Path]
ConvertWordToPdfFn = Callable[..., Awaitable[Tuple[bytes, Dict[str, Any]]]]
TimeoutSecFactory = Callable[[], float]
NormalizeBboxFn = Callable[..., Any]
PageFromBboxFn = Callable[[Any], Any]
IsMeaningfulBboxFn = Callable[[Any], bool]
UtcNowFactory = Callable[[], Any]


@dataclass(frozen=True)
class Module2MainServiceBundle:
    assistant1_runtime: Assistant1StreamingRuntime
    artifact_file_runtime: Module2ArtifactFileRuntime
    artifact_support_runtime: ArtifactSupportRuntime
    xlsx_workbook_artifact_runtime: XlsxWorkbookArtifactRuntime
    office_preview_runtime: OfficePreviewRuntime
    module4_sync_outbox_runtime: Module4SyncOutboxRuntime
    module4_sync_callback_bundle: Module4SyncCallbackBundle
    trace_semantics_runtime: TraceSemanticsRuntime
    trace_locator_text_runtime: TraceLocatorTextRuntime
    trace_locator_payload_runtime: TraceLocatorPayloadRuntime
    document_trace_hits_runtime: DocumentTraceHitsRuntime
    polymorphic_links_runtime: PolymorphicLinksRuntime
    document_tools_support_runtime: DocumentToolsSupportRuntime


def build_module2_main_service_bundle(
    *,
    logger: Any,
    outbox_repository: Any | None = None,
    assistant_repository: Any | None = None,
    legacy_storage: Any | None = None,
    artifact_root_factory: ArtifactRootFactory,
    convert_word_to_pdf: ConvertWordToPdfFn,
    office_preview_timeout_sec_factory: TimeoutSecFactory,
    module4_sync_config_runtime: Any,
    module4_sync_metrics_runtime: Any,
    module4_sync_task_runtime: Any,
    normalize_bbox: NormalizeBboxFn,
    page_from_bbox: PageFromBboxFn,
    is_meaningful_bbox: IsMeaningfulBboxFn,
    utcnow_factory: UtcNowFactory,
    **legacy_kwargs: Any,
) -> Module2MainServiceBundle:
    if "storage" in legacy_kwargs:
        if legacy_storage is not None:
            raise TypeError("Pass only one of legacy_storage=... or storage=...")
        legacy_storage = legacy_kwargs.pop("storage")
    if legacy_kwargs:
        unexpected = ", ".join(sorted(legacy_kwargs))
        raise TypeError(f"Unexpected keyword argument(s): {unexpected}")
    if outbox_repository is None and legacy_storage is not None:
        warnings.warn(
            "build_module2_main_service_bundle(storage=...) is deprecated; "
            "pass outbox_repository=... instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    if assistant_repository is None and legacy_storage is not None:
        warnings.warn(
            "build_module2_main_service_bundle(legacy_storage=...) for assistant persistence is deprecated; "
            "pass assistant_repository=... instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    resolved_outbox_repository = outbox_repository or legacy_storage
    if resolved_outbox_repository is None:
        raise ValueError("outbox_repository or legacy_storage is required")
    resolved_assistant_repository = assistant_repository or legacy_storage

    assistant1_runtime = Assistant1StreamingRuntime(
        persistence=Assistant1PersistenceAdapter(
            repository=resolved_assistant_repository,
            logger=logger,
        ),
        logger=logger,
    )
    artifact_file_runtime = Module2ArtifactFileRuntime(
        artifact_root_factory=artifact_root_factory,
    )
    artifact_support_runtime = ArtifactSupportRuntime(
        artifact_root_factory=artifact_root_factory,
        logger=logger,
    )
    xlsx_workbook_artifact_runtime = XlsxWorkbookArtifactRuntime(
        artifact_support_runtime=artifact_support_runtime,
        logger=logger,
    )
    office_preview_runtime = OfficePreviewRuntime(
        convert_word_to_pdf=convert_word_to_pdf,
        safe_artifact_path=artifact_file_runtime.safe_artifact_path,
        artifact_fragment_from_path=artifact_support_runtime.artifact_fragment_from_path,
        artifact_url_from_fragment=artifact_support_runtime.artifact_url_from_fragment,
        timeout_sec_factory=office_preview_timeout_sec_factory,
    )
    module4_sync_outbox_runtime = Module4SyncOutboxRuntime(
        logger=logger,
        outbox_repository=resolved_outbox_repository,
        metrics_runtime=module4_sync_metrics_runtime,
        base_url_factory=module4_sync_config_runtime.base_url,
        headers_factory=module4_sync_config_runtime.headers,
        timeout_factory=module4_sync_config_runtime.timeout_sec,
        retries_factory=module4_sync_config_runtime.retries,
        retryable_status=module4_sync_config_runtime.retryable_status,
        delay_factory=module4_sync_config_runtime.delay_sec,
        utcnow_factory=utcnow_factory,
        default_tenant_factory=module4_sync_config_runtime.default_tenant,
        tenant_guard_mode_factory=(
            module4_sync_config_runtime.tenant_guard_mode
            if hasattr(module4_sync_config_runtime, "tenant_guard_mode")
            else (lambda: "compat_default")
        ),
    )
    module4_sync_callback_bundle = build_module4_sync_callback_bundle(
        outbox_repository=resolved_outbox_repository,
        module4_sync_config_runtime=module4_sync_config_runtime,
        module4_sync_outbox_runtime=module4_sync_outbox_runtime,
        module4_sync_task_runtime=module4_sync_task_runtime,
        module4_sync_metrics_runtime=module4_sync_metrics_runtime,
    )
    trace_semantics_runtime = TraceSemanticsRuntime()
    trace_locator_text_runtime = TraceLocatorTextRuntime()
    trace_locator_payload_runtime = TraceLocatorPayloadRuntime()
    document_trace_hits_runtime = DocumentTraceHitsRuntime(
        normalize_bbox=normalize_bbox,
        page_from_bbox=page_from_bbox,
        is_meaningful_bbox=is_meaningful_bbox,
        resolve_trace_artifact_ref=artifact_support_runtime.resolve_trace_artifact_ref,
        locator_text_runtime=trace_locator_text_runtime,
        locator_payload_runtime=trace_locator_payload_runtime,
    )
    polymorphic_links_runtime = PolymorphicLinksRuntime(
        normalize_bbox=normalize_bbox,
        page_from_bbox=page_from_bbox,
    )
    document_tools_support_runtime = DocumentToolsSupportRuntime(
        trace_display_kind_from_hit=trace_semantics_runtime.display_kind_from_hit,
    )
    return Module2MainServiceBundle(
        assistant1_runtime=assistant1_runtime,
        artifact_file_runtime=artifact_file_runtime,
        artifact_support_runtime=artifact_support_runtime,
        xlsx_workbook_artifact_runtime=xlsx_workbook_artifact_runtime,
        office_preview_runtime=office_preview_runtime,
        module4_sync_outbox_runtime=module4_sync_outbox_runtime,
        module4_sync_callback_bundle=module4_sync_callback_bundle,
        trace_semantics_runtime=trace_semantics_runtime,
        trace_locator_text_runtime=trace_locator_text_runtime,
        trace_locator_payload_runtime=trace_locator_payload_runtime,
        document_trace_hits_runtime=document_trace_hits_runtime,
        polymorphic_links_runtime=polymorphic_links_runtime,
        document_tools_support_runtime=document_tools_support_runtime,
    )
