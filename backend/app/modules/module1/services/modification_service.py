from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from ..core.config import get_settings
from ..domain import SavedUpload
from . import document_io_support as io_support
from . import document_mutation_support as mutation_support
from . import modification_support as modification_support
from .sandbox_service import cleanup_temp_paths, save_upload_to_temp


logger = logging.getLogger(__name__)


async def apply_document_modifications(
    file: UploadFile,
    modifications_json: str,
    instruction: str = "",
) -> Response:
    settings = get_settings()
    saved_upload: SavedUpload | None = None
    extra_paths: list[str] = []
    output_path = ""

    try:
        modifications = modification_support._normalize_modifications_payload(modifications_json)
        if str(instruction or "").strip():
            modifications = modification_support._sanitize_modifications_for_instruction(modifications, instruction)
        saved_upload = await save_upload_to_temp(
            file,
            max_file_bytes=settings.max_file_bytes,
            max_file_mb=settings.max_file_mb,
        )
        extra_paths.append(saved_upload.path)

        source_ext = io_support._validate_saved_upload(saved_upload)
        output_name = f"modified_{saved_upload.filename}"
        media_type = io_support._media_type_for_name(saved_upload.filename)

        if source_ext in {".docx", ".doc"}:
            working_path, converted_path = io_support._prepare_docx_source(saved_upload)
            if converted_path:
                extra_paths.append(converted_path)
                output_name = f"modified_{Path(saved_upload.filename).stem}.docx"
                media_type = io_support._media_type_for_name(output_name)
            output_path = mutation_support._apply_modifications_to_docx(working_path, modifications)
        elif source_ext in io_support.TEXT_EXTENSIONS:
            output_path = mutation_support._apply_modifications_to_text(saved_upload.path, modifications)
        elif source_ext == ".pdf":
            extracted_text = io_support._extract_text_from_pdf(saved_upload.path)
            if not extracted_text.strip():
                return JSONResponse(
                    status_code=400,
                    content={"error": "PDF 未提取到可修改文本，暂时无法生成修改版"},
                )

            if mutation_support.docx is not None:
                working_path = str(
                    Path(saved_upload.path).with_name(
                        f"{Path(saved_upload.filename).stem}_extracted.docx"
                    )
                )
                mutation_support._write_content_to_docx(working_path, extracted_text)
                extra_paths.append(working_path)
                output_name = f"modified_{Path(saved_upload.filename).stem}.docx"
                media_type = io_support._media_type_for_name(output_name)
                output_path = mutation_support._apply_modifications_to_docx(working_path, modifications)
            else:
                working_path = str(
                    Path(saved_upload.path).with_name(
                        f"{Path(saved_upload.filename).stem}_extracted.txt"
                    )
                )
                with open(working_path, "w", encoding="utf-8") as temp_text_file:
                    temp_text_file.write(extracted_text)
                extra_paths.append(working_path)
                output_name = f"modified_{Path(saved_upload.filename).stem}.txt"
                media_type = io_support._media_type_for_name(output_name)
                output_path = mutation_support._apply_modifications_to_text(working_path, modifications)
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"不支持的文件类型: {source_ext or 'unknown'}"},
            )

        with open(output_path, "rb") as output_file:
            output_bytes = output_file.read()

        return Response(
            content=output_bytes,
            media_type=media_type,
            headers=io_support._build_download_headers(output_name, len(modifications), applied=True),
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("应用修改失败")
        return JSONResponse(status_code=500, content={"error": str(exc)})
    finally:
        cleanup_temp_paths(output_path, *extra_paths)


__all__ = ["apply_document_modifications"]
