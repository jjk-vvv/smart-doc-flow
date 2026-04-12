from __future__ import annotations

import warnings

__all__ = ["router"]


def __getattr__(name: str):
    if name == "router":
        warnings.warn(
            "app.modules.assistant.router is deprecated; "
            "use app.api.v1.endpoints.assistant.router instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from app.modules.assistant.router import router

        return router
    raise AttributeError(name)
