from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from ...services.stream_service import stream_workbench_operation


router = APIRouter()


@router.post("/operate-stream")
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
    return await stream_workbench_operation(
        normalized_files,
        instruction,
        conversation_context=conversation_context,
        selected_file_name=selected_file_name,
    )


__all__ = ["router"]
