from __future__ import annotations

import ast
from importlib import import_module
from pathlib import Path


def _read_backend_file(relative_path: str) -> str:
    backend_root = Path(__file__).resolve().parents[1]
    return (backend_root / relative_path).read_text(encoding="utf-8-sig", errors="ignore")


def _collect_import_modules(source: str) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names if alias.name)
            continue
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_round12_module2_endpoints_no_longer_import_global_app_services() -> None:
    platform_assistant_source = _read_backend_file("app/modules/platform_assistant/api/endpoints/chat.py")
    module2_assistant_source = _read_backend_file("app/modules/module2/api/endpoints/assistant.py")
    module2_extraction_source = _read_backend_file("app/modules/module2/api/endpoints/extraction.py")

    platform_assistant_imports = _collect_import_modules(platform_assistant_source)
    module2_assistant_imports = _collect_import_modules(module2_assistant_source)
    module2_extraction_imports = _collect_import_modules(module2_extraction_source)

    assert "app.services.assistant_service" not in platform_assistant_imports
    assert "app.services.assistant_service" not in module2_assistant_imports
    assert "app.services.extraction_service" not in module2_extraction_imports
    assert any(module.endswith("services.chat_service") for module in platform_assistant_imports)
    assert any(module.endswith("module2.services.api.extraction_service") for module in module2_assistant_imports)
    assert any(module.endswith("module2.services.api.extraction_service") for module in module2_extraction_imports)


def test_round12_global_service_paths_removed_after_boundary_migration() -> None:
    module2_assistant = import_module("app.modules.module2.services.api.assistant_service")
    module2_extraction = import_module("app.modules.module2.services.api.extraction_service")

    assert callable(module2_assistant.AssistantService)
    assert callable(module2_assistant.get_assistant_service)
    assert callable(module2_extraction.ExtractionService)
    assert callable(module2_extraction.get_extraction_service)
