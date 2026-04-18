from __future__ import annotations

from fastapi import APIRouter

from ...schemas.bootstrap import PlatformAssistantBootstrapPayload
from ...services.guidance_service import build_bootstrap_payload

router = APIRouter()


@router.get("/bootstrap")
async def bootstrap(tab: str = "dashboard") -> PlatformAssistantBootstrapPayload:
    return build_bootstrap_payload(tab)


__all__ = ["router"]
