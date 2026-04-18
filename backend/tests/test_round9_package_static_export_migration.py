from __future__ import annotations

from importlib import import_module


def test_round9_module2_package_exports_are_static_without_dynamic_getattr() -> None:
    module2_pkg = import_module("app.modules.module2")
    bootstrap_pkg = import_module("app.modules.module2.bootstrap")

    assert "__getattr__" not in module2_pkg.__dict__
    assert "__getattr__" not in bootstrap_pkg.__dict__
