from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.paths import (
    resolve_config_root_dir,
    resolve_data_root_dir,
    resolve_frontend_dist_dir,
    resolve_runtime_root_dir,
)


def _env_str(name: str, default: str) -> str:
    value = str(os.getenv(name, default) or default).strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw_value = str(os.getenv(name, default)).strip()
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.getenv(name, default)).strip()
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _env_choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = _env_str(name, default).lower()
    return value if value in set(allowed) else default


def _split_csv(raw_value: str) -> tuple[str, ...]:
    items = [item.strip() for item in str(raw_value or "").split(",") if item.strip()]
    if not items:
        return ("http://localhost:3000", "http://127.0.0.1:3000")
    return tuple(items)


@dataclass(frozen=True)
class Settings:
    gateway_host: str
    gateway_port: int
    cors_origins: tuple[str, ...]
    request_timeout_sec: float
    stream_chunk_size: int
    runtime_root_dir: Path
    config_root_dir: Path
    data_root_dir: Path
    frontend_dist_dir: Path
    module2_upstream_url: str
    module4_upstream_url: str
    module3_router_mode: str = "auto"
    auth_tenant_mode: str = "user_strict"
    auth_tenant_default_id: str = "default"
    gateway_health_probe_timeout_sec: float = 2.0
    gateway_startup_sidecar_grace_sec: float = 5.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    runtime_root_dir = resolve_runtime_root_dir()
    config_root_dir = resolve_config_root_dir(runtime_root_dir)
    data_root_dir = resolve_data_root_dir(runtime_root_dir)
    frontend_dist_dir = resolve_frontend_dist_dir(runtime_root_dir)
    gateway_host = _env_str("GATEWAY_HOST", "0.0.0.0")
    gateway_port = _env_int("GATEWAY_PORT", 3001)
    gateway_loopback_host = gateway_host if gateway_host not in {"", "0.0.0.0", "::"} else "127.0.0.1"
    gateway_base_url = _env_str("GATEWAY_BASE_URL", f"http://{gateway_loopback_host}:{gateway_port}")

    return Settings(
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        cors_origins=_split_csv(
            _env_str(
                "GATEWAY_CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3002,http://127.0.0.1:3002,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3010,http://127.0.0.1:3010,http://localhost:5173,http://127.0.0.1:5173,http://localhost:19006,http://127.0.0.1:19006,http://localhost:19007,http://127.0.0.1:19007,http://localhost:19008,http://127.0.0.1:19008",
            )
        ),
        request_timeout_sec=max(1.0, _env_float("GATEWAY_REQUEST_TIMEOUT_SEC", 60.0)),
        stream_chunk_size=max(1024, _env_int("GATEWAY_STREAM_CHUNK_SIZE", 4096)),
        runtime_root_dir=runtime_root_dir,
        config_root_dir=config_root_dir,
        data_root_dir=data_root_dir,
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url=_env_str("MODULE2_UPSTREAM_URL", gateway_base_url),
        module4_upstream_url=_env_str("MODULE4_UPSTREAM_URL", gateway_base_url),
        module3_router_mode=_env_choice(
            "UNIFIED_GATEWAY_MODULE3_ROUTER_MODE",
            "auto",
            ("auto", "disabled", "required"),
        ),
        auth_tenant_mode=_env_str("AUTH_TENANT_MODE", "user_strict"),
        auth_tenant_default_id=_env_str("AUTH_TENANT_DEFAULT_ID", "default"),
        gateway_health_probe_timeout_sec=max(1.0, _env_float("GATEWAY_HEALTH_PROBE_TIMEOUT_SEC", 2.0)),
        gateway_startup_sidecar_grace_sec=max(
            0.0,
            _env_float("GATEWAY_STARTUP_SIDECAR_GRACE_SEC", 5.0),
        ),
    )
