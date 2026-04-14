from __future__ import annotations

import ast
from pathlib import Path


LEGACY_IMPORT_PREFIXES = (
    "module2.app",
    "app.modules.module2.api.compat",
    "app.modules.module2.routes",
    "app.modules.assistant",
    "app.modules.extraction",
    "app.modules.gateway",
    "app.modules.module2.native_backend",
)


def _iter_backend_app_python_files() -> list[Path]:
    app_root = (Path(__file__).resolve().parents[1] / "app").resolve()
    files: list[Path] = []
    for path in app_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def _match_legacy_import(name: str) -> bool:
    normalized = str(name or "").strip()
    if not normalized:
        return False
    return any(normalized.startswith(prefix) for prefix in LEGACY_IMPORT_PREFIXES)


def test_backend_app_has_no_legacy_import_paths() -> None:
    violations: list[str] = []

    for path in _iter_backend_app_python_files():
        source = path.read_text(encoding="utf-8-sig", errors="ignore")
        tree = ast.parse(source, filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _match_legacy_import(alias.name):
                        violations.append(f"{path}:{node.lineno} import {alias.name}")
                continue
            if isinstance(node, ast.ImportFrom):
                if _match_legacy_import(node.module or ""):
                    violations.append(f"{path}:{node.lineno} from {node.module}")

    assert not violations, "Found legacy import paths in backend/app:\n" + "\n".join(sorted(violations))
