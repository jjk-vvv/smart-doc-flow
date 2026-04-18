from __future__ import annotations

from importlib import import_module
from pathlib import Path


def _read_backend_file(relative_path: str) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    return (backend_root / relative_path).read_text(encoding="utf-8-sig", errors="ignore")


def test_round18_module2_composition_application_exports_only_canonical_entrypoints() -> None:
    module = import_module("app.modules.module2.composition.application")
    exports = tuple(getattr(module, "__all__", ()) or ())

    assert "app" in exports
    assert "create_app" in exports
    assert "extract_batch" not in exports
    assert "extract_cache_clear" not in exports
    # Worker entrypoints remain available for explicit compat-worker imports.
    assert hasattr(module, "extract_batch")
    assert hasattr(module, "extract_cache_clear")


def test_round18_module2_compat_worker_uses_explicit_worker_entrypoint_imports() -> None:
    source = _read_backend_file("app/modules/module2/core/module2_compat_worker.py")

    assert "from app.modules.module2.composition.application import (" in source
    assert "extract_batch," in source
    assert "extract_cache_clear," in source
