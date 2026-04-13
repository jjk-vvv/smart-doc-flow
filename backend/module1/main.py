from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保项目路径可导入
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from core.config import get_cors_config, get_settings
from routes import document_router, health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Module 1 - Document Interaction Workbench", version="1.0.0")
    cors_origins, cors_allow_all = get_cors_config()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if cors_allow_all else cors_origins,
        allow_credentials=not cors_allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(document_router, prefix="", tags=["document"])
    app.include_router(health_router, prefix="", tags=["health"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=get_settings().port, reload=False)
