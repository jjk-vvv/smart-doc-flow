from __future__ import annotations

import warnings

__all__ = ["router"]


def __getattr__(name: str):
    if name == "router":
        warnings.warn(
            "app.modules.extraction.router is deprecated; "
            "use app.api.v1.endpoints.extraction.router instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from app.modules.extraction.router import router

        return router
    raise AttributeError(name)
