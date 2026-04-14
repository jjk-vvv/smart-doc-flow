from __future__ import annotations

from importlib import import_module

import pytest
from fastapi import APIRouter


@pytest.mark.parametrize(
    "module_path",
    [
        "app.modules.auth.api.router",
        "app.modules.module1.api.router",
        "app.modules.module2.api.router",
        "app.modules.module4.api.router",
        "app.modules.frontend_static.api.router",
    ],
)
def test_unified_backend_module_router_paths_are_importable(module_path: str) -> None:
    module = import_module(module_path)
    assert isinstance(module.router, APIRouter)


@pytest.mark.parametrize(
    "legacy_package_path",
    [
        "app.modules.assistant",
        "app.modules.extraction",
        "app.modules.gateway",
        "app.modules.module1_placeholder",
    ],
)
def test_legacy_compat_packages_are_removed(legacy_package_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(legacy_package_path)
