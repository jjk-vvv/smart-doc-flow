from __future__ import annotations

from fastapi import APIRouter

from app.modules.module2.api.router import router as module2_router

from .foundation import (
    GetEnvFn,
    Module2BootstrapComponents,
    Module2MainFoundationBundle,
    build_module2_default_bootstrap_components,
    build_module2_main_foundation_bundle,
)


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(module2_router)
    return router


router = build_router()

__all__ = [
    "build_router",
    "router",
    "GetEnvFn",
    "Module2BootstrapComponents",
    "Module2MainFoundationBundle",
    "build_module2_default_bootstrap_components",
    "build_module2_main_foundation_bundle",
]
