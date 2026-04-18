from __future__ import annotations

import json
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_auth_compat_runtime_has_been_removed() -> None:
    backend_root = _backend_root()

    assert not (backend_root / "auth" / "server.cjs").exists()
    assert not (backend_root / "auth" / "package.json").exists()
    assert not (backend_root / "auth" / "package-lock.json").exists()


def test_root_package_scripts_no_longer_expose_compat_backend_entrypoints() -> None:
    workspace_root = _backend_root().parents[0]
    package_json = json.loads((workspace_root / "package.json").read_text(encoding="utf-8"))
    scripts = package_json.get("scripts", {})

    assert "dev:compat" not in scripts
    assert "start:compat" not in scripts
    assert "dev:backend:compat" not in scripts
    assert "start:backend:compat" not in scripts
