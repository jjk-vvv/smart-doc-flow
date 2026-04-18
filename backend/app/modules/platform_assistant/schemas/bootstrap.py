from __future__ import annotations

from pydantic import Field

from .chat import PlatformAssistantModel


class AssistantBootstrapPaths(PlatformAssistantModel):
    chatPath: str = "/api/platform-assistant/chat"
    healthPath: str = "/api/platform-assistant/health"
    diagnosticsPath: str = "/api/platform-assistant/diagnostics"
    catalogPath: str = "/api/platform-assistant/catalog"
    bootstrapPath: str = "/api/platform-assistant/bootstrap"


class AssistantBootstrapAction(PlatformAssistantModel):
    label: str
    targetTab: str
    variant: str = "primary"


class AssistantBootstrapCard(PlatformAssistantModel):
    title: str
    summary: str
    steps: list[str]
    primaryAction: AssistantBootstrapAction
    secondaryAction: AssistantBootstrapAction | None = None


class AssistantBootstrapPrompt(PlatformAssistantModel):
    id: str
    question: str
    keywords: list[str] = Field(default_factory=list)
    answer: AssistantBootstrapCard


class AssistantBootstrapPage(PlatformAssistantModel):
    tab: str
    label: str
    cue: str
    starter: AssistantBootstrapCard
    prompts: list[AssistantBootstrapPrompt] = Field(default_factory=list)
    primaryPromptCount: int = 0


class PlatformAssistantBootstrapPayload(PlatformAssistantModel):
    ok: bool = True
    assistant: AssistantBootstrapPaths
    page: AssistantBootstrapPage
    updatedAt: str


class PlatformAssistantCatalogPayload(PlatformAssistantModel):
    ok: bool = True
    assistant: AssistantBootstrapPaths
    pages: list[AssistantBootstrapPage] = Field(default_factory=list)
    updatedAt: str


__all__ = [
    "AssistantBootstrapAction",
    "AssistantBootstrapCard",
    "AssistantBootstrapPage",
    "AssistantBootstrapPaths",
    "AssistantBootstrapPrompt",
    "PlatformAssistantBootstrapPayload",
    "PlatformAssistantCatalogPayload",
]
