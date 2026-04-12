from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from backend.module3.core.bootstrap import ensure_module3_storage
    from backend.module3.routes import router
    from backend.module3.tools.module3_tool import main as service_main
else:
    from .core.bootstrap import ensure_module3_storage
    from .routes import router
    from .tools.module3_tool import main as service_main


def create_app() -> FastAPI:
    application = FastAPI(title="Module3 Fusion API", version="1.0.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_event_handler("startup", ensure_module3_storage)
    application.include_router(router)
    return application


app = create_app()


def main() -> None:
    service_main()


if __name__ == "__main__":
    main()
