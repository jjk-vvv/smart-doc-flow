from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Tuple

from app.core.env import load_managed_env_files

load_managed_env_files(scopes=("module1", "backend"))


def _cors_origins() -> Tuple[List[str], bool]:
    raw = os.getenv(
        "MODULE1_CORS_ORIGINS",
        (
            "http://localhost:3000,"
            "http://127.0.0.1:3000,"
            "http://localhost:3002,"
            "http://127.0.0.1:3002,"
            "http://localhost:5173,"
            "http://127.0.0.1:5173"
        ),
    )
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if not origins:
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    allow_all = "*" in origins
    return origins, allow_all


@dataclass(frozen=True)
class Settings:
    cors_origins: List[str]
    cors_allow_all: bool
    max_file_mb: int
    max_file_bytes: int
    port: int
    zhipu_api_key: str
    
    @classmethod
    def load(cls) -> "Settings":
        cors_origins, cors_allow_all = _cors_origins()
        max_file_mb = max(1, int(os.getenv("MODULE1_MAX_FILE_MB", "20")))
        return cls(
            cors_origins=cors_origins,
            cors_allow_all=cors_allow_all,
            max_file_mb=max_file_mb,
            max_file_bytes=max_file_mb * 1024 * 1024,
            port=int(os.getenv("MODULE1_PORT", os.getenv("PORT", "5000"))),
            zhipu_api_key=os.getenv("ZHIPU_API_KEY", "").strip(),
        )


_settings = Settings.load()


def get_settings() -> Settings:
    return _settings


def get_cors_config() -> Tuple[List[str], bool]:
    return _settings.cors_origins, _settings.cors_allow_all
