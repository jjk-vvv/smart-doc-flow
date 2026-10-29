from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.core.config import Settings
from app.core.deps import get_settings
from app.modules.module2.schemas.extraction import Assistant1ChatStreamRequest
from app.modules.module2.services.api.extraction_service import (
    ExtractionService,
    get_extraction_service,
)


def build_router() -> APIRouter:
    router = APIRouter(tags=["extraction"])
    extract_router = APIRouter(prefix="/extract")

    @extract_router.post("/assistant1/chat/stream")
    async def extract_assistant1_chat_stream(
        request: Request,
        payload: Assistant1ChatStreamRequest,
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        extra_context = dict(payload.extra_context or {})
        extra_context.setdefault(
            "authenticated_user",
            {
                "id": current_user.user_id,
                "name": current_user.name,
                "email": current_user.email,
                "tenant_id": current_user.tenant_id,
            },
        )
        request.state.authenticated_user = current_user
        return extraction_service.build_assistant1_stream(
            settings,
            request,
            payload.model_copy(update={"extra_context": extra_context}),
        )

    @extract_router.get("/assistant1/sessions/{session_id}")
    async def extract_assistant1_session(
        session_id: str,
        request: Request,
        limit: int = Query(default=40, ge=1, le=200),
        settings: Settings = Depends(get_settings),
        extraction_service: ExtractionService = Depends(get_extraction_service),
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        request.state.authenticated_user = current_user
        return await extraction_service.get_assistant1_session_async(
            settings,
            request,
            session_id,
            limit=limit,
        )

    router.include_router(extract_router)
    return router


router = build_router()

__all__ = ["build_router", "router"]
