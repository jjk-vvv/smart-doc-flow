from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from app.core.config import get_settings
from app.modules.module2.composition.embedded_runtime import embedded_lifespan as module2_embedded_lifespan
from app.modules.module4.composition import embedded_lifespan as module4_embedded_lifespan
from app.services.auth_service import get_auth_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan_context(app: FastAPI):
    app.state.started_at = datetime.now(timezone.utc)
    get_settings()
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(module4_embedded_lifespan(app))
        await stack.enter_async_context(module2_embedded_lifespan(app))
        try:
            yield
        finally:
            await get_auth_service().shutdown()
