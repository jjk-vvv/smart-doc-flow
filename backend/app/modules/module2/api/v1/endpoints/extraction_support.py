from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Dict

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile

try:
    from app.schemas import (
        CacheClearResponse,
        SummarizeRequest,
        SummarizeResponse,
        TraceLocateRequest,
        TraceLocateResponse,
    )
except ModuleNotFoundError:  # pragma: no cover - direct file-loading tests can fall back to plain dict
    CacheClearResponse = dict
    SummarizeRequest = dict
    SummarizeResponse = dict
    TraceLocateRequest = dict
    TraceLocateResponse = dict


CacheClearRequestFn = Callable[[str], Awaitable[Dict[str, Any]]]
ServeArtifactFn = Callable[..., Response]
ServeFileAssetFn = Callable[[str, str], Response]
HealthPayloadFn = Callable[[], Dict[str, str]]
def build_router(
    *,
    office_preview_request_runtime,
    document_tools_runtime,
    clear_cache_request: CacheClearRequestFn,
    serve_layout_preview: ServeArtifactFn,
    serve_artifact: ServeArtifactFn,
    build_health_payload: HealthPayloadFn,
    serve_file_asset: ServeFileAssetFn | None = None,
) -> APIRouter:
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

    def _call_serve_artifact(
        handler: ServeArtifactFn,
        *,
        artifact_ref: str,
        request_method: str,
        file_id: str = "",
    ) -> Response:
        handler_params = inspect.signature(handler).parameters
        normalized_file_id = str(file_id or "").strip()
        if normalized_file_id and "file_id" in handler_params:
            return handler(artifact_ref, request_method, file_id=normalized_file_id)
        return handler(artifact_ref, request_method)

    def _serve_by_file_id(file_id: str, request_method: str, *, request: Request | None = None) -> Response:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise HTTPException(status_code=400, detail="file_id is required")
        if serve_file_asset is not None:
            serve_file_asset_params = inspect.signature(serve_file_asset).parameters
            if "request" in serve_file_asset_params:
                return serve_file_asset(normalized_file_id, request_method, request=request)
            return serve_file_asset(normalized_file_id, request_method)
        for handler in (serve_artifact, serve_layout_preview):
            handler_params = inspect.signature(handler).parameters
            if "file_id" in handler_params:
                return handler("", request_method, file_id=normalized_file_id)
        raise HTTPException(
            status_code=501,
            detail="file_id artifact route is unavailable in current module2 runtime",
        )

    @extract_router.post("/preview/office/start")
    async def extract_preview_office_start(file: UploadFile = File(...)) -> Dict[str, Any]:
        return await office_preview_request_runtime.start(file)

    @extract_router.get("/preview/office/status/{job_id}")
    async def extract_preview_office_status(job_id: str) -> Dict[str, Any]:
        return await office_preview_request_runtime.get_status(job_id)

    @extract_router.post("/summarize", response_model=SummarizeResponse)
    async def extract_summarize(payload: SummarizeRequest) -> SummarizeResponse:
        return document_tools_runtime.summarize(payload)

    @extract_router.post("/trace/locate", response_model=TraceLocateResponse)
    async def extract_trace_locate(payload: TraceLocateRequest) -> TraceLocateResponse:
        return document_tools_runtime.trace_locate(payload)

    @extract_router.post("/cache/clear", response_model=CacheClearResponse)
    async def extract_cache_clear(
        scope: str = Query(default="results", pattern="^(results|runtime|all)$"),
        tenant_id: str = Query(default=""),
    ) -> CacheClearResponse:
        clear_cache_params = inspect.signature(clear_cache_request).parameters
        if "tenant_id" in clear_cache_params:
            payload = await clear_cache_request(scope, tenant_id=tenant_id)
        else:
            payload = await clear_cache_request(scope)
        return payload if CacheClearResponse is dict else CacheClearResponse(**payload)

    @extract_router.api_route("/layout-preview/by-file/{file_id}", methods=["GET", "HEAD"])
    async def extract_layout_preview_by_file(file_id: str, request: Request) -> Response:
        response = _serve_by_file_id(file_id, request.method, request=request)
        return _attach_route_debug_headers(response, resolved_via="by-file")

    @extract_router.api_route("/layout-preview/{artifact_name}", methods=["GET", "HEAD"])
    async def extract_layout_preview(
        artifact_name: str,
        request: Request,
        file_id: str = Query(default=""),
    ) -> Response:
        normalized_file_id = str(file_id or "").strip()
        if normalized_file_id:
            response = _serve_by_file_id(normalized_file_id, request.method, request=request)
            return _attach_route_debug_headers(response, resolved_via="by-file")
        _ensure_legacy_route_available("/extract/layout-preview/by-file/{file_id}")
        response = _call_serve_artifact(
            serve_layout_preview,
            artifact_ref=artifact_name,
            request_method=request.method,
            file_id=normalized_file_id,
        )
        return _attach_route_debug_headers(response, resolved_via="by-file")

    @extract_router.api_route("/artifact/by-file/{file_id}", methods=["GET", "HEAD"])
    async def extract_artifact_by_file(file_id: str, request: Request) -> Response:
        response = _serve_by_file_id(file_id, request.method, request=request)
        return _attach_route_debug_headers(response, resolved_via="by-file")

    @extract_router.api_route("/artifact/{artifact_path:path}", methods=["GET", "HEAD"])
    async def extract_artifact_route(
        artifact_path: str,
        request: Request,
        file_id: str = Query(default=""),
    ) -> Response:
        normalized_file_id = str(file_id or "").strip()
        if normalized_file_id:
            response = _serve_by_file_id(normalized_file_id, request.method, request=request)
            return _attach_route_debug_headers(response, resolved_via="by-file")
        _ensure_legacy_route_available("/extract/artifact/by-file/{file_id}")
        response = _call_serve_artifact(
            serve_artifact,
            artifact_ref=artifact_path,
            request_method=request.method,
            file_id=normalized_file_id,
        )
        return _attach_route_debug_headers(response, resolved_via="by-file")

    @router.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return build_health_payload()

    router.include_router(extract_router)
    return router
