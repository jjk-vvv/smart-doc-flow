from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...services.chat_service import PlatformAssistantService, get_platform_assistant_service

router = APIRouter()


@router.get("/health")
async def health(
    force_smoke: bool = False,
    service: PlatformAssistantService = Depends(get_platform_assistant_service),
) -> dict[str, Any]:
    payload = service.health_payload(force_smoke=force_smoke)
    payload["route"] = "/api/platform-assistant/health"
    return payload


__all__ = ["router"]
