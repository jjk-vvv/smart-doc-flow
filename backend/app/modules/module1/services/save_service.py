from __future__ import annotations

import logging
from pathlib import Path
import urllib.parse

from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from ..core.config import get_settings
from ..domain import SavedUpload
from . import document_io_support as io_support
from . import document_mutation_support as mutation_support
from .sandbox_service import cleanup_temp_paths, save_upload_to_temp


logger = logging.getLogger(__name__)


async def save_edited_document_content(file: UploadFile, content: str) -> Response:
    settings = get_settings()
    saved_upload: SavedUpload | None = None
    extra_paths: list[str] = []
    output_path = ""

    try:
        saved_upload = await save_upload_to_temp(
            file,
            max_file_bytes=settings.max_file_bytes,
            max_file_mb=settings.max_file_mb,
        )
        extra_paths.append(saved_upload.path)

        source_ext = io_support._validate_saved_upload(saved_upload)
        normalized_content = str(content or "").replace("\r", "")

        if source_ext in {".doc", ".docx"}:
            output_name = f"edited_{Path(saved_upload.filename).stem}.docx"
            output_path = str(Path(saved_upload.path).with_name(output_name))
            mutation_support._write_content_to_docx(output_path, normalized_content)
            media_type = io_support._media_type_for_name(output_name)
        elif source_ext in io_support.TEXT_EXTENSIONS:
            output_name = f"edited_{saved_upload.filename}"
            output_path = str(Path(saved_upload.path).with_name(output_name))
            with open(output_path, "w", encoding="utf-8") as output_file:
                output_file.write(normalized_content)
            media_type = io_support._media_type_for_name(output_name)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"当前文件类型暂不支持直接保存编辑稿: {source_ext or 'unknown'}"},
            )

        with open(output_path, "rb") as output_file:
            output_bytes = output_file.read()

        encoded_name = urllib.parse.quote(output_name)
        return Response(
            content=output_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": (
                    f"attachment; filename={encoded_name}; "
                    f"filename*=UTF-8''{encoded_name}"
                )
            },
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("保存编辑稿失败")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        cleanup_temp_paths(output_path, *extra_paths)


__all__ = ["save_edited_document_content"]
