from __future__ import annotations

from pathlib import Path


def test_module4_main_is_standard_entrypoint_without_runtime_compat_exports() -> None:
    module4_main = Path(__file__).resolve().parents[1] / "app" / "main.py"
    source = module4_main.read_text(encoding="utf-8")

    assert "from .composition.application import app, create_app" in source
    assert "__all__ = [" in source
    assert "\"app\"" in source
    assert "\"create_app\"" in source
    assert "def __getattr__(name: str):" not in source
    assert "_get_runtime_ref = " not in source
    assert "_set_runtime_ref = " not in source
    assert "module4_app_runtime = " not in source
    assert "from .services.app_runtime import (" not in source


def test_module4_composition_application_owns_runtime_assembly() -> None:
    module4_application = Path(__file__).resolve().parents[1] / "app" / "composition" / "application.py"
    source = module4_application.read_text(encoding="utf-8")

    assert "from .runtime import (" in source
    assert "_composition_components = build_default_composition_components(" in source


def test_module4_composition_runtime_prefers_composition_named_builder_alias() -> None:
    composition_runtime = Path(__file__).resolve().parents[1] / "app" / "composition" / "runtime.py"
    source = composition_runtime.read_text(encoding="utf-8")

    assert (
        "build_default_composition_components = _service_module.build_default_composition_components"
        in source
    )
