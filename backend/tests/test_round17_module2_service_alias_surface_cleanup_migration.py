from __future__ import annotations

from importlib import import_module
from pathlib import Path


def _read_backend_file(relative_path: str) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    return (backend_root / relative_path).read_text(encoding="utf-8-sig", errors="ignore")


def test_round17_module2_service_modules_drop_legacy_alias_exports() -> None:
    request_source = _read_backend_file("app/modules/module2/services/extraction/request.py")
    executor_source = _read_backend_file("app/modules/module2/services/extraction/executor.py")

    assert "ExtractionRequestRuntime = ExtractionRequestService" not in request_source
    assert "ExtractionJobExecutor = ExtractionJobExecutionService" not in executor_source
    assert "__all__ = [\"ExtractionRequestService\"]" in request_source
    assert "__all__ = [\"ExtractionJobExecutionService\"]" in executor_source


def test_round17_module2_runtime_package_keeps_compat_aliases_for_callers() -> None:
    request_module = import_module("app.modules.module2.services.extraction.request")
    executor_module = import_module("app.modules.module2.services.extraction.executor")
    runtime_module = import_module("app.modules.module2.runtime")

    assert not hasattr(request_module, "ExtractionRequestRuntime")
    assert not hasattr(executor_module, "ExtractionJobExecutor")
    assert runtime_module.ExtractionRequestRuntime is runtime_module.ExtractionRequestService
    assert runtime_module.ExtractionJobExecutor is runtime_module.ExtractionJobExecutionService
