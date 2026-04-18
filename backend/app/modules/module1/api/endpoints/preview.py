from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from ...services.preview_service import (
    convert_docx_to_pdf,
    download_office_preview_job_artifact,
    get_office_preview_job_status,
    start_office_preview_job,
)


router = APIRouter()


@router.post("/convert/docx-to-pdf")
async def convert_docx_preview(file: UploadFile = File(...)):
    return await convert_docx_to_pdf(file)


@router.post("/convert/office/start")
async def start_office_preview(file: UploadFile = File(...)):
    return await start_office_preview_job(file)


@router.get("/convert/office/status/{job_id}")
async def get_office_preview_status(job_id: str):
    return await get_office_preview_job_status(job_id)


@router.get("/convert/office/artifact/{job_id}")
async def get_office_preview_artifact(job_id: str):
    return await download_office_preview_job_artifact(job_id)


__all__ = ["router"]
