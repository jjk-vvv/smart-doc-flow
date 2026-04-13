from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from ...core.bootstrap import ensure_module3_storage


def build_module3_lifespan():
    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        ensure_module3_storage()
        yield

    return _lifespan


__all__ = ["build_module3_lifespan"]
