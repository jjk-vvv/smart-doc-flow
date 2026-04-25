from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_cors_config

LOCALHOST_CORS_ORIGIN_REGEX = (
    r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|capacitor://localhost|ionic://localhost)$"
)


def build_router() -> APIRouter:
    from .api.router import router as module1_router

    router = APIRouter()
    router.include_router(module1_router, prefix="/module1", tags=["module1"])
    return router


def build_app() -> FastAPI:
    app = FastAPI(title="Module 1 - Document Interaction Workbench", version="1.0.0")
    cors_origins, cors_allow_all = get_cors_config()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if cors_allow_all else cors_origins,
        allow_origin_regex=None if cors_allow_all else LOCALHOST_CORS_ORIGIN_REGEX,
        allow_credentials=not cors_allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


router = build_router()

__all__ = ["build_app", "build_router", "router"]
