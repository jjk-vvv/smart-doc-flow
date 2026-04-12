from __future__ import annotations

from typing import Any


def build_placeholder_info() -> dict[str, Any]:
    return {
        "ok": True,
        "module": "module1",
        "status": "placeholder",
        "title": "Module 1 Placeholder",
        "message": "Module 1 UI is intentionally kept as a placeholder during the FastAPI unification stage.",
    }

