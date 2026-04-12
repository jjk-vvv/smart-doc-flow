from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.domain.assistant import AssistantChatRequest
from app.services.assistant_service import AssistantService, get_assistant_service


def build_router() -> APIRouter:
    router = APIRouter(tags=["assistant"])

    @router.get("/api/chat/health")
    async def chat_health(
        force_smoke: bool = False,
        service: AssistantService = Depends(get_assistant_service),
    ):
        return service.health_payload(force_smoke=force_smoke)

    @router.post("/api/chat")
    async def chat(
        payload: AssistantChatRequest,
        service: AssistantService = Depends(get_assistant_service),
        _current_user: AuthenticatedUser = Depends(require_authenticated_user),
    ):
        return service.stream_chat(payload.model_dump())

    return router


router = build_router()
