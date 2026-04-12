from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from app.core.config import get_settings
from app.services.auth_service import get_auth_service
from app.modules.extraction.config import get_extraction_settings
from app.modules.extraction.module2_sidecar_runtime import get_module2_sidecar_manager
from app.modules.gateway.module4_sidecar_runtime import (
    get_module4_sidecar_manager,
    get_module4_sidecar_settings,
)

logger = logging.getLogger(__name__)


async def _prewarm_sidecar_with_grace(
    *,
    name: str,
    settings,
    grace_timeout_sec: float,
    ensure_ready,
) -> None:
    task = asyncio.create_task(asyncio.to_thread(ensure_ready, settings))

    def _log_task_failure(completed: asyncio.Task[object]) -> None:
        try:
            completed.result()
        except Exception as exc:  # pragma: no cover - defensive runtime logging
            logger.warning("%s sidecar prewarm failed after startup: %s", name, exc)

    task.add_done_callback(_log_task_failure)

    if grace_timeout_sec <= 0:
        return

    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=grace_timeout_sec)
    except asyncio.TimeoutError:
        logger.warning(
            "%s sidecar prewarm exceeded %.1fs startup grace window; continuing gateway startup",
            name,
            grace_timeout_sec,
        )
    except Exception as exc:
        logger.warning("%s sidecar prewarm failed during startup; continuing gateway startup: %s", name, exc)


@asynccontextmanager
async def lifespan_context(app: FastAPI):
    app.state.started_at = datetime.now(timezone.utc)
    settings = get_settings()
    extraction_settings = get_extraction_settings()
    module2_sidecar_manager = get_module2_sidecar_manager()
    module4_sidecar_manager = get_module4_sidecar_manager()
    grace_timeout_sec = float(settings.gateway_startup_sidecar_grace_sec)
    if extraction_settings.module2_sidecar_mode == "managed":
        await _prewarm_sidecar_with_grace(
            name="module2",
            settings=settings,
            grace_timeout_sec=grace_timeout_sec,
            ensure_ready=module2_sidecar_manager.ensure_ready,
        )
    if get_module4_sidecar_settings().module4_sidecar_mode == "managed":
        await _prewarm_sidecar_with_grace(
            name="module4",
            settings=settings,
            grace_timeout_sec=grace_timeout_sec,
            ensure_ready=module4_sidecar_manager.ensure_ready,
        )
    try:
        yield
    finally:
        await get_auth_service().shutdown()
        await asyncio.to_thread(module2_sidecar_manager.shutdown_started_process)
        await asyncio.to_thread(module4_sidecar_manager.shutdown_started_process)
