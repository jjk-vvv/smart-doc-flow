from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user

from ...schemas.chat import AssistantContextEnvelope, AssistantSessionMeta, PlatformAssistantChatRequest
from ...services.chat_service import PlatformAssistantService, get_platform_assistant_service

router = APIRouter()


@router.post("/chat")
async def chat(
    payload: PlatformAssistantChatRequest,
    service: PlatformAssistantService = Depends(get_platform_assistant_service),
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    context = payload.context.model_copy(deep=True) if payload.context is not None else AssistantContextEnvelope()
    session_meta = context.sessionMeta.model_copy(deep=True) if context.sessionMeta is not None else AssistantSessionMeta()
    session_meta.userId = current_user.user_id
    session_meta.tenantId = current_user.tenant_id
    session_meta.requestId = current_user.session_id or current_user.user_id
    context.sessionMeta = session_meta

    normalized_payload = payload.model_dump()
    normalized_payload["context"] = context.model_dump(exclude_none=True)
    return service.stream_chat(normalized_payload)


__all__ = ["router"]
