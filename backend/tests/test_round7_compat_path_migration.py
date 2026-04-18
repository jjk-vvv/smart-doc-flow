from __future__ import annotations

from importlib import import_module

import pytest


@pytest.mark.parametrize(
    "removed_module_path",
    [
        "app.domain.assistant",
        "app.domain.extraction",
        "app.shared.contracts",
        "app.shared.utils",
        "app.shared.integrations",
        "app.modules.module3.repositories",
        "app.modules.module3.repositories.storage_repository",
    ],
)
def test_round7_removed_compat_modules_raise_not_found(removed_module_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(removed_module_path)
