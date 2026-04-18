from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from ...services.modification_service import apply_document_modifications


router = APIRouter()


@router.post("/apply-modifications")
async def apply_modifications(
    file: UploadFile = File(...),
    modifications: str = Form("[]"),
    modifications_json: Optional[str] = Form(None),
    instruction: str = Form(""),
):
    payload = modifications_json if modifications_json is not None else modifications
    return await apply_document_modifications(file, payload, instruction)


__all__ = ["router"]
