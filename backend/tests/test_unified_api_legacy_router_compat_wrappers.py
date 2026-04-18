from __future__ import annotations

from importlib import import_module

import pytest
from fastapi import APIRouter


def test_unified_backend_auth_package_exports_canonical_router() -> None:
    package = import_module("app.modules.auth")
    assert isinstance(package.router, APIRouter)


@pytest.mark.parametrize(
    "removed_path",
    [
        "app.modules.auth.router",
        "app.modules.frontend_static.router",
        "app.modules.assistant.router",
        "app.modules.extraction.router",
        "app.modules.gateway.router",
        "app.modules.module1_placeholder.router",
    ],
)
def test_unified_backend_removed_legacy_router_modules_raise_not_found(removed_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(removed_path)
