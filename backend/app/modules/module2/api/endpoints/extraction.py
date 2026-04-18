from __future__ import annotations

import asyncio
import inspect

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.core.config import Settings
from app.core.deps import get_settings
from app.modules.module2.schemas.extraction import (
    Assistant1ChatStreamRequest,
    BatchExtractionResponse,
    CacheClearResponse,
    CancelExtractionJobFileRequest,
    CancelExtractionJobFileResponse,
    SummarizeRequest,
    TraceLocateRequest,
)
from app.modules.module2.services.api.extraction_service import (
    ExtractionService,
    get_extraction_service,
)


def build_router() -> APIRouter:
    router = APIRouter(tags=["extraction"])
    extract_router = APIRouter(prefix="/extract")

    def _legacy_route_mode() -> str:
        return "off"

    def _attach_route_debug_headers(response: Response, *, resolved_via: str) -> Response:
        if "X-Extract-Resolved-Via" not in response.headers:
            response.headers["X-Extract-Resolved-Via"] = resolved_via
        if "X-Extract-Legacy-Route-Mode" not in response.headers:
            response.headers["X-Extract-Legacy-Route-Mode"] = _legacy_route_mode()
        return response

    def _ensure_legacy_route_available(successor_path: str) -> None:
        del successor_path
        raise HTTPException(
            status_code=410,
            detail=(
                "legacy artifact path route is disabled; "
                "use /extract/artifact/by-file/{file_id} instead"
            ),
        )

    @router.get("/healthz")
    async def extraction_healthz(
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
    ):
        return await asyncio.to_thread(extraction_service.health_payload, settings)

    @extract_router.post("/jobs/create")
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

    @extract_router.get("/jobs/status/{job_id}")
    async def extract_jobs_status(
        request: Request,
        job_id: str,
        include_documents: bool = False,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return await asyncio.to_thread(
            extraction_service.get_job_status,
            settings,
            request,
            job_id,
            include_documents=include_documents,
        )

    @extract_router.post("/jobs/{job_id}/cancel-file", response_model=CancelExtractionJobFileResponse)
    async def extract_jobs_cancel_file(
        request: Request,
        job_id: str,
        payload: CancelExtractionJobFileRequest,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return await asyncio.to_thread(
            extraction_service.cancel_job_file,
            settings,
            request,
            job_id,
            file_hash=payload.file_hash,
            file_name=payload.file_name,
        )

    @extract_router.post("/batch", response_model=BatchExtractionResponse)
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

    @extract_router.post("/preview/office/start")
    async def extract_office_preview_start(
        request: Request,
        file: UploadFile = File(...),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return await extraction_service.start_office_preview(settings, request, file)

    @extract_router.get("/preview/office/status/{job_id}")
    async def extract_office_preview_status(
        request: Request,
        job_id: str,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return await extraction_service.get_office_preview_status(settings, request, job_id)

    @extract_router.post("/summarize")
    async def extract_summarize(
        payload: SummarizeRequest,
        extraction_service: ExtractionService = Depends(get_extraction_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return extraction_service.summarize(payload)

    @extract_router.post("/trace/locate")
    async def extract_trace_locate(
        request: Request,
        payload: TraceLocateRequest,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return extraction_service.trace_locate(payload, settings=settings, request=request)

    @extract_router.post("/assistant1/chat/stream")
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
                "tenant_id": current_user.tenant_id,
            },
        )
        request.state.authenticated_user = current_user
        return extraction_service.build_assistant1_stream(
            settings,
            request,
            payload.model_copy(update={"extra_context": extra_context}),
        )

    @extract_router.get("/assistant1/sessions/{session_id}")
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

    @extract_router.post("/cache/clear", response_model=CacheClearResponse)
    async def extract_cache_clear(
        request: Request,
        scope: str = Query(default="results", pattern="^(results|runtime|all)$"),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        clear_cache_params = inspect.signature(extraction_service.clear_cache).parameters
        if "request" in clear_cache_params:
            return await extraction_service.clear_cache(settings, scope=scope, request=request)
        return await extraction_service.clear_cache(settings, scope=scope)

    @extract_router.api_route("/layout-preview/{artifact_name}", methods=["GET", "HEAD"])
    async def extract_layout_preview(
        artifact_name: str,
        request: Request,
        file_id: str = Query(default=""),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            _ensure_legacy_route_available("/extract/layout-preview/by-file/{file_id}")
        response = extraction_service.serve_layout_preview(
            settings,
            request,
            artifact_name,
            request.method,
            file_id=normalized_file_id,
        )
        return _attach_route_debug_headers(response, resolved_via="by-file")

    @extract_router.api_route("/layout-preview/by-file/{file_id}", methods=["GET", "HEAD"])
    async def extract_layout_preview_by_file(
        file_id: str,
        request: Request,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        response = extraction_service.serve_layout_preview(
            settings,
            request,
            artifact_name="",
            method=request.method,
            file_id=file_id,
        )
        return _attach_route_debug_headers(response, resolved_via="by-file")

    @extract_router.api_route("/artifact/by-file/{file_id}", methods=["GET", "HEAD"])
    async def extract_artifact_by_file(
        file_id: str,
        request: Request,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        response = extraction_service.serve_artifact(
            settings,
            request,
            artifact_path="",
            method=request.method,
            file_id=file_id,
        )
        return _attach_route_debug_headers(response, resolved_via="by-file")

    @extract_router.api_route("/artifact/{artifact_path:path}", methods=["GET", "HEAD"])
    async def extract_artifact(
        artifact_path: str,
        request: Request,
        file_id: str = Query(default=""),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            _ensure_legacy_route_available("/extract/artifact/by-file/{file_id}")
        response = extraction_service.serve_artifact(
            settings,
            request,
            artifact_path,
            request.method,
            file_id=normalized_file_id,
        )
        return _attach_route_debug_headers(response, resolved_via="by-file")

    router.include_router(extract_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
