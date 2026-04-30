from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter

from app.core.config import Settings
from app.modules.auth.composition import router as auth_router
from app.modules.diagnostics.composition import router as diagnostics_router
from app.modules.file_assets.api.router import router as file_assets_router
from app.modules.frontend_static.api.router import router as frontend_static_router
from app.modules.module1.composition import router as module1_router
from app.modules.module2.composition import router as module2_router
from app.modules.module4.composition import router as module4_router
from app.modules.platform_assistant.composition import router as platform_assistant_router

logger = logging.getLogger(__name__)


RouterLoader = Callable[[Settings], APIRouter | None]


@dataclass(frozen=True)
class ModuleRouteRegistration:
    name: str
    loader: RouterLoader


def _constant_router_loader(router: APIRouter) -> RouterLoader:
    def _load(_: Settings) -> APIRouter:
        return router

    return _load


def _load_module3_router(settings: Settings) -> APIRouter | None:
    mode = str(settings.module3_router_mode or "auto").strip().lower()
    if mode == "disabled":
        return None

    try:
        from app.modules.module3 import router as module3_router
    except Exception as exc:  # pragma: no cover - import safety for optional module wiring
        if mode == "required":
            raise RuntimeError("Module3 router registration failed in required mode.") from exc
        logger.warning("Skip module3 router registration (auto mode): %s", exc)
        return None

    return module3_router


_MODULE_ROUTE_REGISTRATIONS: tuple[ModuleRouteRegistration, ...] = (
    ModuleRouteRegistration("auth", _constant_router_loader(auth_router)),
    ModuleRouteRegistration("diagnostics", _constant_router_loader(diagnostics_router)),
    ModuleRouteRegistration("file_assets", _constant_router_loader(file_assets_router)),
    ModuleRouteRegistration("module1", _constant_router_loader(module1_router)),
    ModuleRouteRegistration("module2", _constant_router_loader(module2_router)),
    ModuleRouteRegistration("module3", _load_module3_router),
    ModuleRouteRegistration("module4", _constant_router_loader(module4_router)),
    ModuleRouteRegistration("platform_assistant", _constant_router_loader(platform_assistant_router)),
    ModuleRouteRegistration("frontend_static", _constant_router_loader(frontend_static_router)),
)


def resolve_module_routers(settings: Settings) -> tuple[tuple[str, APIRouter], ...]:
    resolved: list[tuple[str, APIRouter]] = []
    for registration in _MODULE_ROUTE_REGISTRATIONS:
        router = registration.loader(settings)
        if router is None:
            continue
        resolved.append((registration.name, router))
    return tuple(resolved)


__all__ = ["ModuleRouteRegistration", "resolve_module_routers"]
