from __future__ import annotations

from importlib import import_module

import pytest
from fastapi import APIRouter


@pytest.mark.parametrize(
    "module_path",
    [
        "app.modules.auth.router",
        "app.modules.frontend_static.router",
    ],
)
def test_unified_backend_legacy_router_modules_delegate_to_api_endpoints_with_warning(module_path: str) -> None:
    module = import_module(module_path)
    with pytest.warns(DeprecationWarning):
        router = module.build_legacy_router()
    assert isinstance(router, APIRouter)


@pytest.mark.parametrize(
    "package_path",
    [
        "app.modules.auth",
    ],
)
def test_unified_backend_legacy_package_router_exports_emit_deprecation_warning(package_path: str) -> None:
    package = import_module(package_path)
    package.__dict__.pop("router", None)
    with pytest.warns(DeprecationWarning):
        router = package.router
    assert isinstance(router, APIRouter)


@pytest.mark.parametrize(
    "removed_path",
    [
        "app.modules.assistant.router",
        "app.modules.extraction.router",
        "app.modules.gateway.router",
        "app.modules.module1_placeholder.router",
    ],
)
def test_unified_backend_removed_legacy_router_modules_raise_not_found(removed_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(removed_path)
