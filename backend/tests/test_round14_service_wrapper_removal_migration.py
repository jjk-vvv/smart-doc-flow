from __future__ import annotations

from importlib import import_module

import pytest


def test_round14_removed_global_module2_service_wrappers_cannot_be_imported() -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module("app.services.assistant_service")

    with pytest.raises(ModuleNotFoundError):
        import_module("app.services.extraction_service")


def test_round14_app_services_package_no_longer_exports_removed_wrappers() -> None:
    services_pkg = import_module("app.services")
    exports = tuple(getattr(services_pkg, "__all__", ()) or ())

    assert "assistant_service" not in exports
    assert "extraction_service" not in exports
