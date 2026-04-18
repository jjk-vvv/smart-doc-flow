from __future__ import annotations

import os

import uvicorn

from .core.application import app, create_app


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
