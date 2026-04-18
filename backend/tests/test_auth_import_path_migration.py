from __future__ import annotations

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "removed_module_path",
    [
        "app.modules.auth.config",
        "app.modules.auth.deps",
        "app.modules.auth.notifier",
        "app.modules.auth.repository",
        "app.modules.auth.schemas",
        "app.modules.auth.security",
        "app.modules.auth.storage",
        "app.modules.auth.tenant",
        "app.modules.auth.domain",
        "app.modules.auth.domain.security",
        "app.modules.auth.domain.tenant",
        "app.modules.auth.repositories",
        "app.modules.auth.repositories.auth_repository",
        "app.modules.auth.repositories.auth_storage",
        "app.modules.auth.services",
        "app.modules.auth.services.auth_service",
    ],
)
def test_removed_auth_compat_modules_raise_not_found(removed_module_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(removed_module_path)
