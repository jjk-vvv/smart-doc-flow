from __future__ import annotations

from importlib import import_module
from pathlib import Path


def _read_backend_file(relative_path: str) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    return (backend_root / relative_path).read_text(encoding="utf-8-sig", errors="ignore")


def test_round13_module3_main_is_compat_shim_to_core_application() -> None:
    source = _read_backend_file("app/modules/module3/main.py")

    assert "from .core.application import app, create_app" in source
    assert "def create_app() -> FastAPI:" not in source
    assert "from .api.router import router as module3_router" not in source
    assert "ensure_module3_storage()" not in source
    assert "def main() -> None:" in source


def test_round13_module3_core_application_is_canonical_assembly_point() -> None:
    source = _read_backend_file("app/modules/module3/core/application.py")

    assert "from ..api.router import router as module3_router" in source
    assert "ensure_module3_storage()" in source
    assert "def create_app() -> FastAPI:" in source
    assert "app = create_app()" in source


def test_round13_module4_main_exposes_explicit_standalone_entrypoint() -> None:
    source = _read_backend_file("app/modules/module4/main.py")

    assert "from .core.application import app, create_app" in source
    assert "def main() -> None:" in source
    assert "uvicorn.run(\"app.modules.module4.main:app\"" in source
    assert "\"main\"," in source


def test_round13_module2_composition_application_surface_is_tightened() -> None:
    source = _read_backend_file("app/modules/module2/composition/application.py")

    assert "_module2_bootstrap_components = build_module2_default_bootstrap_components" in source
    assert "_module2_main_entry_bundle = " in source
    assert "storage = module2_main_repository_bundle.legacy_storage" not in source
    assert "module2_main_foundation_bundle = " not in source
    assert "module2_main_repository_bundle = " not in source
    assert "async def extract_batch(" in source
    assert "async def extract_cache_clear(" in source


def test_round13_module2_composition_application_no_longer_exports_legacy_aliases() -> None:
    module = import_module("app.modules.module2.composition.application")

    assert hasattr(module, "extract_batch")
    assert hasattr(module, "extract_cache_clear")
    assert not hasattr(module, "module2_bootstrap_components")
    assert not hasattr(module, "module2_http_runtime_bundle")
    assert not hasattr(module, "module2_main_entry_bundle")
    assert not hasattr(module, "module2_main_foundation_bundle")
    assert not hasattr(module, "module2_main_repository_bundle")
    assert not hasattr(module, "runtime_state_repository")
    assert not hasattr(module, "extraction_cache_repository")
