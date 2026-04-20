from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List

from ..services.document.tools import DocumentToolsRuntime
from ..services.extraction.executor import ExtractionJobExecutionService
from ..services.extraction.job import ExtractionJobRuntime
from ..services.extraction.request import ExtractionRequestService
from ..services.preview.office import OfficePreviewRequestRuntime
from .cache_clear import Module2CacheClearRuntime


ArtifactRootFactory = Callable[[], Path]
ResolveModule2PathFn = Callable[[str, Path], Path]
ExtractionJobStateRootFactory = Callable[[], Path]
SafeArtifactPathFn = Callable[[str], Path]
ProcessSingleDocBytesFn = Callable[..., Awaitable[Any]]
ParseSchemaFormFn = Callable[[str], Dict[str, Any]]
WriteArtifactBytesFn = Callable[..., tuple[str, str]]
SchemaHashFn = Callable[[Dict[str, Any]], str]
BuildStreamRouterFn = Callable[[], Any]
EnsureProviderReadyFn = Callable[[], Awaitable[None]]
Module4TenantFn = Callable[..., str]
JobStateFactory = Callable[..., Any]
JobFileStateFactory = Callable[..., Any]
DocumentValidateFn = Callable[[Any], Any]
ExtractionResultFactory = Callable[[Dict[str, Any]], Any]
DocumentResponseFactory = Callable[..., Any]
BatchResponseFactory = Callable[..., Any]
IsWordFileFn = Callable[[str], bool]
OfficeConvertEnabledFn = Callable[[], bool]
SummarizeDocumentPayloadFn = Callable[[Any], str]
BuildDocumentTraceHitsFn = Callable[..., List[Dict[str, Any]]]
FilterTraceHitsFn = Callable[..., List[Dict[str, Any]]]
ResponseFactory = Callable[..., Any]
BoundedEnvIntFn = Callable[..., int]


@dataclass(frozen=True)
class Module2HttpRuntimeBundle:
    cache_clear_runtime: Module2CacheClearRuntime
    extraction_job_runtime: ExtractionJobRuntime
    extraction_job_executor: ExtractionJobExecutionService
    extraction_request_runtime: ExtractionRequestService
    office_preview_request_runtime: OfficePreviewRequestRuntime
    document_tools_runtime: DocumentToolsRuntime
    extraction_jobs: Dict[str, Any]
    extraction_lock: asyncio.Lock
    extraction_job_runtime_specs: Dict[str, Dict[str, Any]]
    extraction_job_tasks: Dict[str, asyncio.Task[Any]]
    extraction_job_persist_markers: Dict[str, float]


def build_module2_http_runtime_bundle(
    *,
    module2_root: Path,
    artifact_root_factory: ArtifactRootFactory,
    resolve_module2_path: ResolveModule2PathFn,
    extraction_job_state_root_factory: ExtractionJobStateRootFactory,
    safe_artifact_path: SafeArtifactPathFn,
    process_single_doc_bytes: ProcessSingleDocBytesFn,
    parse_schema_form_json: ParseSchemaFormFn,
    write_artifact_bytes: WriteArtifactBytesFn,
    schema_hash: SchemaHashFn,
    build_stream_router: BuildStreamRouterFn,
    ensure_provider_ready_for_job_create: EnsureProviderReadyFn,
    module4_tenant: Module4TenantFn,
    job_state_factory: JobStateFactory,
    job_file_state_factory: JobFileStateFactory,
    document_validate: DocumentValidateFn,
    extraction_result_factory: ExtractionResultFactory,
    document_response_factory: DocumentResponseFactory,
    batch_response_factory: BatchResponseFactory,
    module4_sync_callback_bundle: Any,
    office_preview_runtime: Any,
    is_word_file: IsWordFileFn,
    office_convert_enabled: OfficeConvertEnabledFn,
    summarize_document_payload: SummarizeDocumentPayloadFn,
    build_document_trace_hits: BuildDocumentTraceHitsFn,
    filter_trace_hits: FilterTraceHitsFn,
    summarize_response_factory: ResponseFactory,
    trace_locate_response_factory: ResponseFactory,
    bounded_env_int: BoundedEnvIntFn,
    logger: Any,
) -> Module2HttpRuntimeBundle:
    cache_clear_runtime = Module2CacheClearRuntime(
        module2_root=module2_root,
        artifact_root_factory=artifact_root_factory,
        resolve_module2_path=resolve_module2_path,
        extraction_job_state_root_factory=extraction_job_state_root_factory,
    )
    # The executor depends on the job runtime, while the job runtime schedules the
    # executor. Keep the same late-bound assembly that main.py used before.
    extraction_job_runtime = ExtractionJobRuntime(
        state_root_factory=extraction_job_state_root_factory,
        safe_artifact_path=safe_artifact_path,
        job_state_factory=job_state_factory,
        job_file_state_factory=job_file_state_factory,
        document_validate=document_validate,
        run_extraction_job=lambda **kwargs: extraction_job_executor.run_job(**kwargs),
        logger=logger,
    )
    extraction_jobs = extraction_job_runtime.jobs
    extraction_lock = extraction_job_runtime.lock
    extraction_job_runtime_specs = extraction_job_runtime.runtime_specs
    extraction_job_tasks = extraction_job_runtime.tasks
    extraction_job_persist_markers = extraction_job_runtime.persist_markers
    extraction_job_file_semaphore = asyncio.Semaphore(
        bounded_env_int("MODULE2_JOB_FILE_CONCURRENCY", 3, maximum=8)
    )
    extraction_job_executor = ExtractionJobExecutionService(
        extraction_job_runtime=extraction_job_runtime,
        module4_sync_callback_bundle=module4_sync_callback_bundle,
        file_semaphore=extraction_job_file_semaphore,
        process_single_doc_bytes=process_single_doc_bytes,
        logger=logger,
    )
    extraction_request_runtime = ExtractionRequestService(
        process_single_doc_bytes=process_single_doc_bytes,
        parse_schema_form_json=parse_schema_form_json,
        write_artifact_bytes=write_artifact_bytes,
        schema_hash=schema_hash,
        build_stream_router=build_stream_router,
        ensure_provider_ready_for_job_create=ensure_provider_ready_for_job_create,
        module4_tenant=module4_tenant,
        extraction_job_runtime=extraction_job_runtime,
        module4_sync_callback_bundle=module4_sync_callback_bundle,
        document_validate=document_validate,
        extraction_result_factory=extraction_result_factory,
        document_response_factory=document_response_factory,
        batch_response_factory=batch_response_factory,
        logger=logger,
    )
    office_preview_request_runtime = OfficePreviewRequestRuntime(
        is_word_file=is_word_file,
        office_convert_enabled=office_convert_enabled,
        ensure_job_started=office_preview_runtime.ensure_job_started,
        serialize_job=office_preview_runtime.serialize_job,
        get_status_payload=office_preview_runtime.get_status_payload,
    )
    document_tools_runtime = DocumentToolsRuntime(
        summarize_document_payload=summarize_document_payload,
        build_document_trace_hits=build_document_trace_hits,
        filter_trace_hits=filter_trace_hits,
        summarize_response_factory=summarize_response_factory,
        trace_locate_response_factory=trace_locate_response_factory,
    )
    return Module2HttpRuntimeBundle(
        cache_clear_runtime=cache_clear_runtime,
        extraction_job_runtime=extraction_job_runtime,
        extraction_job_executor=extraction_job_executor,
        extraction_request_runtime=extraction_request_runtime,
        office_preview_request_runtime=office_preview_request_runtime,
        document_tools_runtime=document_tools_runtime,
        extraction_jobs=extraction_jobs,
        extraction_lock=extraction_lock,
        extraction_job_runtime_specs=extraction_job_runtime_specs,
        extraction_job_tasks=extraction_job_tasks,
        extraction_job_persist_markers=extraction_job_persist_markers,
    )
