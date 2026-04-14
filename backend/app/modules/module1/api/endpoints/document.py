from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from app.modules.module1.services.document_service import (
    handle_apply_modifications,
    handle_convert_docx_to_pdf,
    handle_operate_stream,
    handle_save_edited_document,
)

router = APIRouter()

@router.post("/apply_modifications")
async def apply_modifications(
    file: UploadFile = File(...),
    modifications: str = Form("[]"),
    modifications_json: Optional[str] = Form(None),
):
    payload = modifications_json if modifications_json is not None else modifications
    return await handle_apply_modifications(file, payload)

@router.post("/convert/docx-to-pdf")
async def convert_docx_to_pdf(file: UploadFile = File(...)):
    return await handle_convert_docx_to_pdf(file)

@router.post("/save_edited_document")
async def save_edited_document(
    file: UploadFile = File(...),
    content: str = Form(""),
):
    return await handle_save_edited_document(file, content)

@router.post("/operate_stream")
async def operate_stream(
    instruction: str = Form(""),
    file: UploadFile = File(None),
    files: Optional[list[UploadFile]] = File(None),
    conversation_context: str = Form("[]"),
    selected_file_name: str = Form(""),
):
    normalized_files = list(files or [])
    if file is not None:
        normalized_files.insert(0, file)
    return await handle_operate_stream(
        normalized_files,
        instruction,
        conversation_context=conversation_context,
        selected_file_name=selected_file_name,
    )
