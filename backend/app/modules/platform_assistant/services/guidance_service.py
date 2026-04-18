from __future__ import annotations

from datetime import UTC, datetime

from ..data.page_configs import get_all_page_configs, get_page_config
from ..schemas.bootstrap import (
    AssistantBootstrapPage,
    AssistantBootstrapPaths,
    PlatformAssistantBootstrapPayload,
    PlatformAssistantCatalogPayload,
)


def build_bootstrap_payload(tab: str | None) -> PlatformAssistantBootstrapPayload:
    return PlatformAssistantBootstrapPayload(
        assistant=AssistantBootstrapPaths(),
        page=AssistantBootstrapPage.model_validate(get_page_config(tab)),
        updatedAt=datetime.now(UTC).isoformat(),
    )


def build_catalog_payload() -> PlatformAssistantCatalogPayload:
    return PlatformAssistantCatalogPayload(
        assistant=AssistantBootstrapPaths(),
        pages=[AssistantBootstrapPage.model_validate(page) for page in get_all_page_configs()],
        updatedAt=datetime.now(UTC).isoformat(),
    )


__all__ = ["build_bootstrap_payload", "build_catalog_payload"]
