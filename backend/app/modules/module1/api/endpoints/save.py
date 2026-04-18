from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from ...services.save_service import save_edited_document_content


router = APIRouter()


@router.post("/save-edited-document")
async def save_edited_document(
    file: UploadFile = File(...),
    content: str = Form(""),
):
    return await save_edited_document_content(file, content)


__all__ = ["router"]
