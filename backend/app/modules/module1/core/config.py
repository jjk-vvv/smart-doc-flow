from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Tuple

from app.core.env import load_managed_env_files

load_managed_env_files(scopes=("module1", "backend"))


def _env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default


def _normalize_base_url(raw_url: str) -> str:
    cleaned = str(raw_url or "").strip().rstrip("/")
    if not cleaned:
        return "https://quanzil.com/v1"

    for suffix in ("/v1/responses", "/v1/chat/completions", "/chat/completions", "/responses"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break

    if not cleaned.endswith("/v1"):
        cleaned = f"{cleaned}/v1"
    return cleaned


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
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_vision_model: str
    llm_timeout_sec: float
    analysis_first_token_timeout_sec: float
    analysis_hard_timeout_sec: float

    @classmethod
    def load(cls) -> "Settings":
        cors_origins, cors_allow_all = _cors_origins()
        max_file_mb = max(1, int(os.getenv("MODULE1_MAX_FILE_MB", "20")))
        llm_model = _env_first(
            "MODULE1_LLM_MODEL",
            "MODULE1_MODEL",
            "OPENAI_MODEL",
            default="qwen-plus",
        )
        llm_vision_model = _env_first(
            "MODULE1_LLM_VISION_MODEL",
            "MODULE1_VISION_MODEL",
            default=llm_model,
        )
        return cls(
            cors_origins=cors_origins,
            cors_allow_all=cors_allow_all,
            max_file_mb=max_file_mb,
            max_file_bytes=max_file_mb * 1024 * 1024,
            port=int(os.getenv("MODULE1_PORT", os.getenv("PORT", "5000"))),
            llm_api_key=_env_first(
                "MODULE1_LLM_API_KEY",
                "OPENAI_API_KEY",
            ),
            llm_base_url=_normalize_base_url(
                _env_first(
                    "MODULE1_LLM_BASE_URL",
                    "MODULE1_BASE_URL",
                    "OPENAI_BASE_URL",
                    "BASE_URL",
                    default="https://quanzil.com/v1",
                )
            ),
            llm_model=llm_model,
            llm_vision_model=llm_vision_model,
            llm_timeout_sec=float(os.getenv("MODULE1_LLM_TIMEOUT_SEC", "180")),
            analysis_first_token_timeout_sec=max(
                0.0,
                float(os.getenv("MODULE1_ANALYSIS_FIRST_TOKEN_TIMEOUT_SEC", "18")),
            ),
            analysis_hard_timeout_sec=max(
                30.0,
                float(
                    os.getenv(
                        "MODULE1_ANALYSIS_HARD_TIMEOUT_SEC",
                        os.getenv("MODULE1_LLM_TIMEOUT_SEC", "180"),
                    )
                ),
            ),
        )



_settings = Settings.load()


def get_settings() -> Settings:
    return _settings


def get_cors_config() -> Tuple[List[str], bool]:
    return _settings.cors_origins, _settings.cors_allow_all
