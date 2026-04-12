from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from fastapi import APIRouter, File, Query, Request, Response, UploadFile

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
ServeArtifactFn = Callable[[str, str], Response]
HealthPayloadFn = Callable[[], Dict[str, str]]


def build_router(
    *,
    office_preview_request_runtime,
    document_tools_runtime,
    clear_cache_request: CacheClearRequestFn,
    serve_layout_preview: ServeArtifactFn,
    serve_artifact: ServeArtifactFn,
    build_health_payload: HealthPayloadFn,
) -> APIRouter:
    router = APIRouter(tags=["extraction"])

    @router.post("/extract/preview/office/start")
    async def extract_preview_office_start(file: UploadFile = File(...)) -> Dict[str, Any]:
        return await office_preview_request_runtime.start(file)

    @router.get("/extract/preview/office/status/{job_id}")
    async def extract_preview_office_status(job_id: str) -> Dict[str, Any]:
        return await office_preview_request_runtime.get_status(job_id)

    @router.post("/extract/summarize", response_model=SummarizeResponse)
    async def extract_summarize(payload: SummarizeRequest) -> SummarizeResponse:
        return document_tools_runtime.summarize(payload)

    @router.post("/extract/trace/locate", response_model=TraceLocateResponse)
    async def extract_trace_locate(payload: TraceLocateRequest) -> TraceLocateResponse:
        return document_tools_runtime.trace_locate(payload)

    @router.post("/extract/cache/clear", response_model=CacheClearResponse)
    async def extract_cache_clear(
        scope: str = Query(default="results", pattern="^(results|runtime|all)$")
    ) -> CacheClearResponse:
        payload = await clear_cache_request(scope)
        return payload if CacheClearResponse is dict else CacheClearResponse(**payload)

    @router.api_route("/extract/layout-preview/{artifact_name}", methods=["GET", "HEAD"])
    async def extract_layout_preview(artifact_name: str, request: Request) -> Response:
        return serve_layout_preview(artifact_name, request.method)

    @router.api_route("/extract/artifact/{artifact_path:path}", methods=["GET", "HEAD"])
    async def extract_artifact_route(artifact_path: str, request: Request) -> Response:
        return serve_artifact(artifact_path, request.method)

    @router.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return build_health_payload()

    return router
