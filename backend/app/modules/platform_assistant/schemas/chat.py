from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class PlatformAssistantModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class AssistantChatMessage(PlatformAssistantModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantSessionMeta(PlatformAssistantModel):
    tenantId: str | None = None
    userId: str | None = None
    requestId: str | None = None


class AssistantContextEnvelope(PlatformAssistantModel):
    activeTab: str = "dashboard"
    pageCue: str = ""
    documents: list[dict[str, Any]] | None = None
    selection: dict[str, Any] | None = None
    moduleStatus: dict[str, Any] | None = None
    sessionMeta: AssistantSessionMeta | None = None


class PlatformAssistantChatRequest(PlatformAssistantModel):
    messages: list[AssistantChatMessage]
    context: AssistantContextEnvelope | None = None


__all__ = [
    "AssistantChatMessage",
    "AssistantContextEnvelope",
    "AssistantSessionMeta",
    "PlatformAssistantChatRequest",
]
