from fastapi import FastAPI

from app.api.v1.router import build_api_v1_router
from app.core.config import get_settings
from app.core.env import load_managed_env_files
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan_context
from app.core.middleware import register_middleware


def create_app() -> FastAPI:
    load_managed_env_files(scopes=("module2", "backend"))
    settings = get_settings()
    app = FastAPI(
        title="Smart Doc Flow Unified Gateway",
        version="0.1.0",
        lifespan=lifespan_context,
    )

    register_middleware(app, settings)
    register_exception_handlers(app)

    app.include_router(build_api_v1_router())

    return app
