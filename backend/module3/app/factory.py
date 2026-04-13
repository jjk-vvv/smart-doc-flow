from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.router import build_api_v1_router
from .core.lifespan import build_module3_lifespan


def create_app() -> FastAPI:
    application = FastAPI(
        title="Module3 Fusion API",
        version="1.0.0",
        lifespan=build_module3_lifespan(),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(build_api_v1_router())
    return application


__all__ = ["create_app"]
