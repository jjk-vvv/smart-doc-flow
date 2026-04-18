from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "removed_module_path",
    [
        "app.modules.module2.core.parser",
        "app.modules.module2.core.llm_provider",
        "app.modules.module2.core.layout_mineru",
        "app.modules.module2.runtime.http_runtime_bundle",
        "app.modules.module2.runtime.app_callback_bundle",
    ],
)
def test_module2_round5_removed_compat_modules_raise_not_found(removed_module_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(removed_module_path)


def test_module2_round5_domain_compat_surface_removed() -> None:
    domain_init_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "domain"
        / "__init__.py"
    )
    assert not domain_init_path.exists()
