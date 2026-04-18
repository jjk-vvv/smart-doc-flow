from __future__ import annotations

import os

import uvicorn

from .core.application import app, create_app


def main() -> None:
    host = str(os.getenv("MODULE4_HOST", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    port_raw = str(os.getenv("MODULE4_PORT", "8100") or "8100").strip() or "8100"
    try:
        port = int(port_raw)
    except ValueError:
        port = 8100
    uvicorn.run("app.modules.module4.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()


__all__ = [
    "app",
    "create_app",
    "main",
]
