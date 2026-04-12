from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse


ArtifactRootFactory = Callable[[], Path]


class Module2ArtifactFileRuntime:
    """Resolve artifact paths safely and serve stored artifact files."""

    def __init__(self, *, artifact_root_factory: ArtifactRootFactory) -> None:
        self._artifact_root_factory = artifact_root_factory

    def safe_artifact_path(self, path_fragment: str) -> Path:
        root = self._artifact_root_factory()
        fragment = str(path_fragment or "").strip().lstrip("/\\")
        target = (root / fragment).resolve()
        try:
            target.relative_to(root)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid artifact path") from exc
        return target

    def absolute_storage_path(self, path_fragment: str) -> str:
        fragment = str(path_fragment or "").strip()
        if not fragment:
            return ""
        try:
            return str(self.safe_artifact_path(fragment))
        except HTTPException:
            return ""

    @staticmethod
    def head_response_for_file(file_path: Path) -> Response:
        media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        return Response(
            status_code=200,
            headers={
                "Content-Length": str(file_path.stat().st_size),
                "Content-Type": media_type,
            },
        )

    def serve_artifact(
        self,
        *,
        path_fragment: str,
        request_method: str,
        not_found_detail: str,
        default_media_type: str,
    ) -> Response:
        target = self.safe_artifact_path(path_fragment)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail=not_found_detail)
        if str(request_method or "").upper() == "HEAD":
            return self.head_response_for_file(target)
        media_type = mimetypes.guess_type(str(target))[0] or default_media_type
        return FileResponse(
            path=target,
            media_type=media_type,
            filename=target.name,
            content_disposition_type="inline",
        )
