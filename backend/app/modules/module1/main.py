from __future__ import annotations

from app.modules.module1.composition import build_app
from app.modules.module1.core.config import get_settings


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.modules.module1.main:app", host="0.0.0.0", port=get_settings().port, reload=False)
