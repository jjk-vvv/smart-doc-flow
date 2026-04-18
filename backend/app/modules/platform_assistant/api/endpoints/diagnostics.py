from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user

from ...services.chat_service import PlatformAssistantService, get_platform_assistant_service

router = APIRouter()


@router.get("/diagnostics")
async def diagnostics(
    force_smoke: bool = False,
    service: PlatformAssistantService = Depends(get_platform_assistant_service),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, Any]:
    del current_user
    payload = service.diagnostics_payload(force_smoke=force_smoke)
    payload["route"] = "/api/platform-assistant/diagnostics"
    return payload


__all__ = ["router"]
