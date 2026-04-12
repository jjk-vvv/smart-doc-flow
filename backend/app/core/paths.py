from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_dir(name: str, fallback: Path) -> Path:
    raw_value = str(os.getenv(name, "") or "").strip()
    if not raw_value:
        return fallback
    return Path(raw_value).expanduser().resolve()


def resolve_runtime_root_dir() -> Path:
    return _resolve_dir("SMART_DOC_FLOW_RUNTIME_ROOT", REPO_ROOT)


def resolve_config_root_dir(runtime_root: Path | None = None) -> Path:
    runtime = runtime_root or resolve_runtime_root_dir()
    return _resolve_dir("SMART_DOC_FLOW_CONFIG_ROOT", runtime)


def resolve_data_root_dir(runtime_root: Path | None = None) -> Path:
    runtime = runtime_root or resolve_runtime_root_dir()
    return _resolve_dir("SMART_DOC_FLOW_DATA_ROOT", runtime)


def resolve_frontend_dist_dir(runtime_root: Path | None = None) -> Path:
    runtime = runtime_root or resolve_runtime_root_dir()
    raw_value = str(os.getenv("GATEWAY_FRONTEND_DIST_DIR", "") or "").strip()
    if raw_value:
        return Path(raw_value).expanduser().resolve()
    return (runtime / "frontend" / "dist").resolve()

