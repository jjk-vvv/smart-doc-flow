from __future__ import annotations

from importlib import import_module
from pathlib import Path


def _read_backend_file(relative_path: str) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    return (backend_root / relative_path).read_text(encoding="utf-8-sig", errors="ignore")


def test_round15_http_runtime_bundle_uses_canonical_module2_service_names() -> None:
    source = _read_backend_file("app/modules/module2/composition/http_runtime_bundle.py")

    assert "from ..services.extraction.executor import ExtractionJobExecutionService" in source
    assert "from ..services.extraction.request import ExtractionRequestService" in source
    assert "from ..services.extraction.executor import ExtractionJobExecutor" not in source
    assert "from ..services.extraction.request import ExtractionRequestRuntime" not in source


def test_round15_module2_runtime_package_exports_canonical_and_compat_service_names() -> None:
    module = import_module("app.modules.module2.runtime")
    exports = tuple(getattr(module, "__all__", ()) or ())

    assert "ExtractionJobExecutionService" in exports
    assert "ExtractionRequestService" in exports
    # Keep temporary compat exports to avoid runtime breakage during migration.
    assert "ExtractionJobExecutor" in exports
    assert "ExtractionRequestRuntime" in exports
