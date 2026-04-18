from __future__ import annotations

from importlib import import_module
from pathlib import Path


def _read_backend_file(relative_path: str) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    return (backend_root / relative_path).read_text(encoding="utf-8-sig", errors="ignore")


def test_round16_module2_runtime_no_longer_imports_service_compat_aliases_directly() -> None:
    source = _read_backend_file("app/modules/module2/runtime/__init__.py")

    assert "from ..services.extraction.executor import ExtractionJobExecutionService, ExtractionJobExecutor" not in source
    assert "from ..services.extraction.request import ExtractionRequestRuntime, ExtractionRequestService" not in source
    assert "from ..services.extraction.executor import ExtractionJobExecutionService" in source
    assert "from ..services.extraction.request import ExtractionRequestService" in source


def test_round16_module2_runtime_still_exposes_package_level_compat_aliases() -> None:
    module = import_module("app.modules.module2.runtime")

    assert module.ExtractionJobExecutor is module.ExtractionJobExecutionService
    assert module.ExtractionRequestRuntime is module.ExtractionRequestService
