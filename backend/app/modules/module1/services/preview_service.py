from __future__ import annotations

import logging
from pathlib import Path
import urllib.parse

from fastapi import UploadFile
from fastapi.responses import JSONResponse, Response

from ..core.config import get_settings
from .conversion_service import (
    convert_word_bytes_to_pdf,
    download_office_preview_artifact,
    get_office_preview_status,
    is_word_file,
    start_office_preview,
)
from . import document_io_support as io_support


logger = logging.getLogger(__name__)


async def convert_docx_to_pdf(file: UploadFile) -> Response:
    settings = get_settings()
    filename = (file.filename or "").strip()
    if not filename:
        return JSONResponse(status_code=400, content={"error": "空文件名"})

    file_bytes = await file.read()
    if not file_bytes:
        return JSONResponse(status_code=400, content={"error": "空文件"})
    if len(file_bytes) > settings.max_file_bytes:
        return JSONResponse(
            status_code=400,
            content={"error": f"文件大小超过 {settings.max_file_mb}MB 限制"},
        )
    if not is_word_file(filename):
        return JSONResponse(status_code=400, content={"error": f"不支持的文件类型: {filename}"})
    if not io_support._matches_file_signature(Path(filename).suffix.lower(), file_bytes):
        return JSONResponse(
            status_code=400,
            content={"error": "文件内容与扩展名不匹配，请重新上传正确的 Word 文件"},
        )

    try:
        pdf_bytes, _ = convert_word_bytes_to_pdf(
            file_name=filename,
            file_bytes=file_bytes,
            timeout_sec=90.0,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Word 转 PDF 失败")
        return JSONResponse(status_code=500, content={"error": f"转换失败: {exc}"})

    output_name = f"{Path(filename).stem}.pdf"
    encoded_filename = urllib.parse.quote(output_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename={encoded_filename}; "
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )


async def start_office_preview_job(file: UploadFile) -> Response:
    settings = get_settings()
    filename = (file.filename or "").strip()
    if not filename:
        return JSONResponse(status_code=400, content={"error": "空文件名"})
    if not is_word_file(filename):
        return JSONResponse(status_code=400, content={"error": f"不支持的文件类型: {filename}"})

    file_bytes = await file.read()
    if not file_bytes:
        return JSONResponse(status_code=400, content={"error": "空文件"})
    if len(file_bytes) > settings.max_file_bytes:
        return JSONResponse(
            status_code=400,
            content={"error": f"文件大小超过 {settings.max_file_mb}MB 限制"},
        )

    try:
        payload = start_office_preview(file_name=filename, file_bytes=file_bytes)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Office 预览启动失败")
        return JSONResponse(status_code=500, content={"error": f"Office 预览启动失败: {exc}"})

    proxied_payload = dict(payload)
    job_id = str(proxied_payload.get("job_id") or "").strip()
    if job_id:
        proxied_payload["artifact_url"] = (
            f"/module1/convert/office/artifact/{urllib.parse.quote(job_id, safe='')}"
        )
        proxied_payload["status_url"] = (
            f"/module1/convert/office/status/{urllib.parse.quote(job_id, safe='')}"
        )
    return JSONResponse(content=proxied_payload)


async def get_office_preview_job_status(job_id: str) -> Response:
    try:
        payload = get_office_preview_status(job_id=job_id)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("查询 Office 预览状态失败")
        return JSONResponse(status_code=500, content={"error": f"Office 状态查询失败: {exc}"})

    proxied_payload = dict(payload)
    normalized_job_id = str(proxied_payload.get("job_id") or job_id).strip()
    if normalized_job_id and str(proxied_payload.get("status") or "").strip().lower() == "completed":
        proxied_payload["artifact_url"] = (
            f"/module1/convert/office/artifact/{urllib.parse.quote(normalized_job_id, safe='')}"
        )
    proxied_payload["status_url"] = (
        f"/module1/convert/office/status/"
        f"{urllib.parse.quote(normalized_job_id or job_id, safe='')}"
    )
    return JSONResponse(content=proxied_payload)


async def download_office_preview_job_artifact(job_id: str) -> Response:
    try:
        content, content_type, output_name = download_office_preview_artifact(job_id=job_id)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except RuntimeError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("下载 Office 预览产物失败")
        return JSONResponse(status_code=500, content={"error": f"Office 预览产物下载失败: {exc}"})

    output_name = str(output_name or f"{Path(str(job_id).strip() or 'office_preview').stem}.pdf")
    encoded_filename = urllib.parse.quote(output_name)
    return Response(
        content=content,
        media_type=content_type or "application/pdf",
        headers={
            "Content-Disposition": (
                f"inline; filename={encoded_filename}; "
                f"filename*=UTF-8''{encoded_filename}"
            )
        },
    )


__all__ = [
    "convert_docx_to_pdf",
    "download_office_preview_job_artifact",
    "get_office_preview_job_status",
    "start_office_preview_job",
]
