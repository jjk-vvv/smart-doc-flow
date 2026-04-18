from __future__ import annotations

from ..domain import SavedUpload
from .sandbox_service import save_upload_to_temp


async def store_runtime_upload(
    upload,
    *,
    max_file_bytes: int,
    max_file_mb: int,
) -> SavedUpload:
    return await save_upload_to_temp(
        upload,
        max_file_bytes=max_file_bytes,
        max_file_mb=max_file_mb,
    )


__all__ = ["store_runtime_upload"]
