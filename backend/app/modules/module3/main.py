from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import router as module3_router
from .core.bootstrap import ensure_module3_storage


def create_app() -> FastAPI:
    application = FastAPI(
        title="Module3 Fusion API",
        version="1.0.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    ensure_module3_storage()
    application.include_router(module3_router)
    return application


app = create_app()


def main() -> None:
    host = str(os.getenv("MODULE3_HOST", "0.0.0.0") or "0.0.0.0").strip() or "0.0.0.0"
    port_raw = str(os.getenv("MODULE3_PORT", "8001") or "8001").strip() or "8001"
    try:
        port = int(port_raw)
    except ValueError:
        port = 8001
    uvicorn.run("app.modules.module3.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()


__all__ = ["app", "create_app", "main"]
