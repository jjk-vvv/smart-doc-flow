from __future__ import annotations

from ...schemas.bootstrap import PlatformAssistantCatalogPayload
from ...services.guidance_service import build_catalog_payload

from fastapi import APIRouter

router = APIRouter()


@router.get("/catalog")
async def catalog() -> PlatformAssistantCatalogPayload:
    return build_catalog_payload()


__all__ = ["router"]
