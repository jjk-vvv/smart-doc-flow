from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.core.config import Settings
from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.core.deps import get_settings
from app.domain.extraction import (
    Assistant1ChatStreamRequest,
    BatchExtractionResponse,
    CacheClearResponse,
    CancelExtractionJobFileRequest,
    CancelExtractionJobFileResponse,
    SummarizeRequest,
    TraceLocateRequest,
)
from app.services.extraction_service import ExtractionService, get_extraction_service


def build_router() -> APIRouter:
    router = APIRouter(tags=["extraction"])

    @router.get("/healthz")
    async def extraction_healthz(
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
    ):
        return await asyncio.to_thread(extraction_service.health_payload, settings)

    @router.post("/extract/jobs/create")
    async def extract_jobs_create(
        request: Request,
        files: list[UploadFile] = File(...),
        schema_form: str = Form(..., alias="schema"),
        tenant_id: str = Form(default=""),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return await extraction_service.create_job(settings, request, files, schema_form, tenant_id)

    @router.get("/extract/jobs/status/{job_id}")
    async def extract_jobs_status(
        job_id: str,
        include_documents: bool = False,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.get_job_status(settings, job_id, include_documents=include_documents)

    @router.post("/extract/jobs/{job_id}/cancel-file", response_model=CancelExtractionJobFileResponse)
    async def extract_jobs_cancel_file(
        job_id: str,
        payload: CancelExtractionJobFileRequest,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.cancel_job_file(
            settings,
            job_id,
            file_hash=payload.file_hash,
            file_name=payload.file_name,
        )

    @router.post("/extract/batch", response_model=BatchExtractionResponse)
    async def extract_batch(
        request: Request,
        files: list[UploadFile] = File(...),
        schema_form: str = Form(..., alias="schema"),
        tenant_id: str = Form(default=""),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return await extraction_service.extract_batch(settings, request, files, schema_form, tenant_id)

    @router.post("/extract/preview/office/start")
    async def extract_office_preview_start(
        file: UploadFile = File(...),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return await extraction_service.start_office_preview(settings, file)

    @router.get("/extract/preview/office/status/{job_id}")
    async def extract_office_preview_status(
        job_id: str,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return await extraction_service.get_office_preview_status(settings, job_id)

    @router.post("/extract/summarize")
    async def extract_summarize(
        payload: SummarizeRequest,
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.summarize(payload)

    @router.post("/extract/trace/locate")
    async def extract_trace_locate(
        payload: TraceLocateRequest,
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.trace_locate(payload)

    @router.post("/extract/assistant1/chat/stream")
    async def extract_assistant1_chat_stream(
        request: Request,
        payload: Assistant1ChatStreamRequest,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        extra_context = dict(payload.extra_context or {})
        extra_context.setdefault(
            "authenticated_user",
            {
                "id": current_user.user_id,
                "name": current_user.name,
                "email": current_user.email,
            },
        )
        request.state.authenticated_user = current_user
        return extraction_service.build_assistant1_stream(
            settings,
            request,
            payload.model_copy(update={"extra_context": extra_context}),
        )

    @router.get("/extract/assistant1/sessions/{session_id}")
    async def extract_assistant1_session(
        session_id: str,
        request: Request,
        limit: int = Query(default=40, ge=1, le=200),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.get_assistant1_session(
            settings,
            request,
            session_id,
            limit=limit,
        )

    @router.post("/extract/cache/clear", response_model=CacheClearResponse)
    async def extract_cache_clear(
        scope: str = Query(default="results", pattern="^(results|runtime|all)$"),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return await extraction_service.clear_cache(settings, scope)

    @router.api_route("/extract/layout-preview/{artifact_name}", methods=["GET", "HEAD"])
    async def extract_layout_preview(
        artifact_name: str,
        request: Request,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.serve_layout_preview(settings, artifact_name, request.method)

    @router.api_route("/extract/artifact/{artifact_path:path}", methods=["GET", "HEAD"])
    async def extract_artifact(
        artifact_path: str,
        request: Request,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.serve_artifact(settings, artifact_path, request.method)

    return router


router = build_router()
