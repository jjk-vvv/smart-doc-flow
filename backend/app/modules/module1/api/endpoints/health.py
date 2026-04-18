from __future__ import annotations

from fastapi import APIRouter

from ...services.health_service import build_health_response

router = APIRouter()


@router.get("/health")
async def health():
    return build_health_response()
