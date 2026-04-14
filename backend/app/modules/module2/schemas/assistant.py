from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AssistantModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class AssistantChatMessage(AssistantModel):
    role: Literal["user", "assistant"]
    content: str


class AssistantChatRequest(AssistantModel):
    messages: list[AssistantChatMessage]
    platformContext: str | None = None

