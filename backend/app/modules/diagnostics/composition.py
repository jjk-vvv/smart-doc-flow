from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.ai_api_logging import read_ai_api_browser_log_entries
from app.core.auth_deps import AuthenticatedUser, require_authenticated_user


router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("/ai-api-logs")
async def read_ai_api_logs_for_browser_console(
    since_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=300),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, Any]:
    del current_user
    return read_ai_api_browser_log_entries(since_id=since_id, limit=limit)


__all__ = ["router"]
