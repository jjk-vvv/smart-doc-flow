from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, File, Form, Request, UploadFile

try:
    from app.schemas import BatchExtractionResponse
except ModuleNotFoundError:  # pragma: no cover - direct file-loading tests can fall back to plain dict
    BatchExtractionResponse = dict


def build_router(*, extraction_request_runtime) -> APIRouter:
    router = APIRouter(prefix="/extract", tags=["extraction"])

    @router.post("/jobs/create")
    async def extract_jobs_create(
        request: Request,
        files: List[UploadFile] = File(...),
        schema_form: str = Form(..., alias="schema"),
        tenant_id: str = Form(default=""),
    ) -> Dict[str, Any]:
        return await extraction_request_runtime.create_job(
            request=request,
            files=files,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )

    @router.get("/jobs/status/{job_id}")
    async def extract_jobs_status(job_id: str, include_documents: bool = False) -> Dict[str, Any]:
        return await extraction_request_runtime.get_job_status(job_id, include_documents=include_documents)

    @router.post("/jobs/{job_id}/cancel-file")
    async def extract_jobs_cancel_file(job_id: str, payload: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
        return await extraction_request_runtime.cancel_job_file(job_id=job_id, payload=payload)

    @router.post("/batch", response_model=BatchExtractionResponse)
    async def extract_batch(
        request: Request,
        files: List[UploadFile] = File(...),
        schema_form: str = Form(..., alias="schema"),
        tenant_id: str = Form(default=""),
    ) -> BatchExtractionResponse:
        return await extraction_request_runtime.extract_batch(
            request=request,
            files=files,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )

    return router
