from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException, Request, UploadFile


LoadedFileEntry = Tuple[str, bytes, str, str, str, str]
ProcessSingleDocBytesFn = Callable[..., Awaitable[Any]]
ParseSchemaFormFn = Callable[[str], Dict[str, Any]]
WriteArtifactBytesFn = Callable[..., Tuple[str, str]]
SchemaHashFn = Callable[[Dict[str, Any]], str]
BuildStreamRouterFn = Callable[[], Any]
EnsureProviderReadyFn = Callable[[], Awaitable[None]]
Module4TenantFn = Callable[..., str]
ExtractionResultFactory = Callable[[Dict[str, Any]], Any]
DocumentResponseFactory = Callable[..., Any]
BatchResponseFactory = Callable[..., Any]


class ExtractionRequestService:
    """Application service for extraction HTTP request orchestration."""

    def __init__(
        self,
        *,
        process_single_doc_bytes: ProcessSingleDocBytesFn,
        parse_schema_form_json: ParseSchemaFormFn,
        write_artifact_bytes: WriteArtifactBytesFn,
        schema_hash: SchemaHashFn,
        build_stream_router: BuildStreamRouterFn,
        ensure_provider_ready_for_job_create: EnsureProviderReadyFn,
        module4_tenant: Module4TenantFn,
        extraction_job_runtime: Any,
        module4_sync_callback_bundle: Any,
        extraction_result_factory: ExtractionResultFactory,
        document_response_factory: DocumentResponseFactory,
        batch_response_factory: BatchResponseFactory,
        logger: Any,
    ) -> None:
        self._process_single_doc_bytes = process_single_doc_bytes
        self._parse_schema_form_json = parse_schema_form_json
        self._write_artifact_bytes = write_artifact_bytes
        self._schema_hash = schema_hash
        self._build_stream_router = build_stream_router
        self._ensure_provider_ready_for_job_create = ensure_provider_ready_for_job_create
        self._module4_tenant = module4_tenant
        self._extraction_job_runtime = extraction_job_runtime
        self._module4_sync_callback_bundle = module4_sync_callback_bundle
        self._extraction_result_factory = extraction_result_factory
        self._document_response_factory = document_response_factory
        self._batch_response_factory = batch_response_factory
        self._logger = logger

    async def read_upload_file_bytes(self, file: Any) -> Tuple[str, bytes]:
        file_name = getattr(file, "filename", None) or "unknown"
        max_file_mb = max(1, int(os.getenv("MODULE2_MAX_FILE_MB", "25")))
        max_file_bytes = max_file_mb * 1024 * 1024
        file_bytes = await file.read(max_file_bytes + 1)
        if len(file_bytes) > max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_name}. Max size is {max_file_mb}MB.",
            )
        if not file_bytes:
            raise HTTPException(status_code=400, detail=f"Empty file: {file_name}")
        return file_name, file_bytes

    async def process_single_doc(
        self,
        file: Any,
        schema: Dict[str, Any],
        schema_hash: str,
        max_retries: int,
        tenant_id: str = "",
    ) -> Any:
        file_name, file_bytes = await self.read_upload_file_bytes(file)
        return await self._process_single_doc_bytes(
            file_name=file_name,
            file_bytes=file_bytes,
            schema=schema,
            schema_hash=schema_hash,
            max_retries=max_retries,
            tenant_id=str(tenant_id or "").strip(),
        )

    def error_doc_response(self, file_name: str, exc: Exception) -> Any:
        if isinstance(exc, HTTPException):
            detail = exc.detail
            if isinstance(detail, str):
                message = detail
            else:
                message = json.dumps(detail, ensure_ascii=False)
        else:
            message = str(exc) or "Unexpected extraction failure"
        return self._document_response_factory(
            file_name=file_name,
            file_hash="",
            track="Error",
            cached=False,
            result=self._extraction_result_factory({}),
            errors=[message],
            diagnostics={},
        )

    async def create_job(
        self,
        *,
        request: Optional[Request],
        files: Sequence[UploadFile],
        schema_form: str,
        tenant_id: str = "",
    ) -> Dict[str, Any]:
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")
        if len(files) > 5:
            raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

        resolved_tenant = self._module4_tenant(request, tenant_id)
        schema_obj = self._parse_schema_form_json(schema_form)
        loaded_files: List[LoadedFileEntry] = []
        for file in files:
            file_name, file_bytes = await self.read_upload_file_bytes(file)
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            ext = Path(file_name).suffix or ".bin"
            artifact_path, artifact_url = self._write_artifact_bytes(
                data=file_bytes,
                file_name=file_name,
                sub_dir="preview/uploaded",
                ext=ext,
            )
            mime_type = (
                getattr(file, "content_type", None)
                or mimetypes.guess_type(file_name)[0]
                or "application/octet-stream"
            ).strip()
            loaded_files.append((file_name, file_bytes, file_hash, artifact_path, artifact_url, mime_type))

        schema_digest = self._schema_hash(schema_obj)
        router = self._build_stream_router()

        async def _triage_with_compat(file_name: str, file_bytes: bytes) -> Any:
            try:
                return await router.triage(
                    file_name,
                    file_bytes,
                    schema_digest,
                    schema=schema_obj,
                    tenant_id=resolved_tenant,
                )
            except TypeError as exc:
                error_text = str(exc)
                if "tenant_id" in error_text:
                    try:
                        return await router.triage(file_name, file_bytes, schema_digest, schema=schema_obj)
                    except TypeError:
                        return await router.triage(file_name, file_bytes, schema_digest)
                if "schema" not in error_text:
                    raise
                # Backward compatibility: some legacy routers only accept
                # (file_name, file_bytes, schema_digest).
                try:
                    return await router.triage(file_name, file_bytes, schema_digest, tenant_id=resolved_tenant)
                except TypeError:
                    return await router.triage(file_name, file_bytes, schema_digest)

        route_decisions = [
            await _triage_with_compat(file_name, file_bytes)
            for file_name, file_bytes, _file_hash, _artifact_path, _artifact_url, _mime_type in loaded_files
        ]
        if any(getattr(decision, "cached_payload", None) is None for decision in route_decisions):
            await self._ensure_provider_ready_for_job_create()

        max_retries = max(0, min(int(os.getenv("MODULE2_MAX_RETRIES", "2")), 6))
        job_state = await self._extraction_job_runtime.register_job(
            loaded_files=loaded_files,
            schema_obj=schema_obj,
            schema_digest=schema_digest,
            max_retries=max_retries,
            tenant_id=resolved_tenant,
        )
        return self._extraction_job_runtime.serialize_job(job_state, include_documents=False)

    async def get_job_status(self, job_id: str, *, include_documents: bool = False) -> Dict[str, Any]:
        normalized_job_id = str(job_id).strip()
        if normalized_job_id and not re.fullmatch(r"extract_job_[A-Za-z0-9]+", normalized_job_id):
            self._logger.warning("module2 unexpected extraction job status lookup job_id=%r", normalized_job_id)
        job = await self._extraction_job_runtime.find_job(normalized_job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Extraction job not found")
        return self._extraction_job_runtime.serialize_job(job, include_documents=include_documents)

    async def cancel_job_file(self, *, job_id: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        normalized_job_id = str(job_id or "").strip()
        if normalized_job_id and not re.fullmatch(r"extract_job_[A-Za-z0-9]+", normalized_job_id):
            self._logger.warning("module2 unexpected extraction job cancel lookup job_id=%r", normalized_job_id)
        file_hash = str((payload or {}).get("file_hash") or "").strip()
        file_name = str((payload or {}).get("file_name") or "").strip()
        if not normalized_job_id:
            raise HTTPException(status_code=400, detail="Invalid extraction job id")
        if not file_hash and not file_name:
            raise HTTPException(status_code=400, detail="file_hash or file_name is required")
        cancel_result = await self._extraction_job_runtime.cancel_file(
            job_id=normalized_job_id,
            file_hash=file_hash,
            file_name=file_name,
        )
        if not cancel_result:
            raise HTTPException(status_code=404, detail="Extraction job file not found")
        await self._extraction_job_runtime.persist_snapshot(normalized_job_id, True)
        return cancel_result

    async def extract_batch(
        self,
        *,
        request: Optional[Request],
        files: Sequence[UploadFile],
        schema_form: str,
        tenant_id: str = "",
    ) -> Any:
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")
        if len(files) > 5:
            raise HTTPException(status_code=400, detail="At most 5 files are allowed per batch")

        schema_obj = self._parse_schema_form_json(schema_form)
        await self._ensure_provider_ready_for_job_create()

        schema_digest = self._schema_hash(schema_obj)
        max_retries = max(0, min(int(os.getenv("MODULE2_MAX_RETRIES", "2")), 6))
        resolved_tenant = self._module4_tenant(request, tenant_id)
        concurrency = max(1, min(int(os.getenv("MODULE2_BATCH_CONCURRENCY", "2")), len(files)))
        semaphore = asyncio.Semaphore(concurrency)

        async def _run(file: UploadFile) -> Any:
            async with semaphore:
                return await self.process_single_doc(
                    file,
                    schema_obj,
                    schema_digest,
                    max_retries,
                    tenant_id=resolved_tenant,
                )

        gathered = await asyncio.gather(*[_run(file) for file in files], return_exceptions=True)
        results: List[Any] = []
        for file, item in zip(files, gathered):
            if isinstance(item, Exception):
                results.append(self.error_doc_response(getattr(file, "filename", None) or "unknown", item))
            else:
                results.append(item)

        await self._module4_sync_callback_bundle.enqueue_document_sync_for_seed(
            source="module2",
            tenant_id=resolved_tenant,
            documents=results,
            seed=f"extract_batch:{schema_digest}",
            mode="default",
        )

        return self._batch_response_factory(documents=results)


# Backward-compatible alias during migration.
ExtractionRequestRuntime = ExtractionRequestService
