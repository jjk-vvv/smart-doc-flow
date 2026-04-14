from __future__ import annotations

"""Module2 standardized package using compatibility adapters."""

from fastapi import APIRouter

__all__ = ["build_router", "router"]


def build_router() -> APIRouter:
    from .composition import build_router as _build_router

    return _build_router()


def __getattr__(name: str):
    if name == "router":
        from .composition import router

        return router
    if name == "build_router":
        return build_router
    raise AttributeError(name)
