from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
STORAGE_DIR = BASE_DIR / "storage"
TEMPLATES_DIR = STORAGE_DIR / "templates"
DOCSETS_DIR = STORAGE_DIR / "docsets"
RUNS_DIR = STORAGE_DIR / "runs"

ALLOWED_TEMPLATE_SUFFIXES = {".xlsx", ".docx"}
ALLOWED_SOURCE_SUFFIXES = {".docx", ".xlsx", ".txt", ".md"}
DEFAULT_HEADER_ROW = 1
DEFAULT_WRITE_ROW = 2
DEFAULT_PROMPT = (
    "Extract structured data according to the template fields and the user requirements. "
    "If a value cannot be determined, use an empty string. "
    "Keep field keys exactly as provided. Preserve factual values from the source when possible. "
    "If you need to normalize or generate explanatory free-text content, write it in Simplified Chinese."
)
PREVIEW_LINE_LIMIT = 0
PREVIEW_CHAR_LIMIT = 0


def normalize_base_url(raw: str) -> str:
    url = raw.strip().rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


def normalize_database_url(raw: str) -> str:
    url = raw.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def read_database_url() -> str:
    load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")
    raw = (
        os.getenv("MODULE3_DATABASE_URL", "").strip()
        or os.getenv("MODULE3_DATABASE_DSN", "").strip()
    )
    if not raw:
        return ""
    return normalize_database_url(raw)


def read_runtime_settings(api_mode_override: str | None = None) -> dict[str, Any]:
    load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("请在 .env 中配置 OPENAI_API_KEY")

    base_url = normalize_base_url(os.getenv("OPENAI_BASE_URL", "https://jeniya.cn/v1"))
    model = os.getenv("OPENAI_MODEL", "gpt-5.1").strip() or "gpt-5.1"
    api_mode = (api_mode_override or os.getenv("OPENAI_API_MODE", "responses")).strip().lower()
    if api_mode not in {"responses", "chat"}:
        raise ValueError("OPENAI_API_MODE 只支持 responses 或 chat")

    try:
        max_images = int(os.getenv("OPENAI_MAX_IMAGES", "12"))
        max_image_bytes = int(os.getenv("OPENAI_MAX_IMAGE_BYTES", "4194304"))
    except ValueError as exc:
        raise ValueError("OPENAI_MAX_IMAGES / OPENAI_MAX_IMAGE_BYTES 必须是整数") from exc

    if max_images <= 0:
        raise ValueError("OPENAI_MAX_IMAGES 必须大于 0")
    if max_image_bytes <= 0:
        raise ValueError("OPENAI_MAX_IMAGE_BYTES 必须大于 0")

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "api_mode": api_mode,
        "max_images": max_images,
        "max_image_bytes": max_image_bytes,
    }


__all__ = [
    "ALLOWED_SOURCE_SUFFIXES",
    "ALLOWED_TEMPLATE_SUFFIXES",
    "BASE_DIR",
    "DEFAULT_HEADER_ROW",
    "DEFAULT_PROMPT",
    "DEFAULT_WRITE_ROW",
    "DOCSETS_DIR",
    "ENV_PATH",
    "PREVIEW_CHAR_LIMIT",
    "PREVIEW_LINE_LIMIT",
    "RUNS_DIR",
    "STORAGE_DIR",
    "TEMPLATES_DIR",
    "normalize_database_url",
    "normalize_base_url",
    "read_database_url",
    "read_runtime_settings",
]
