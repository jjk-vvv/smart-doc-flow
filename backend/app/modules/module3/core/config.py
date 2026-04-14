from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = next(
    (parent.resolve() for parent in BASE_DIR.parents if (parent / "backend").exists()),
    BASE_DIR.parents[3].resolve(),
)
BACKEND_DIR = (REPO_ROOT / "backend").resolve()
MODULE3_DIR = BASE_DIR.resolve()
ENV_PATH = (MODULE3_DIR / ".env").resolve()
LEGACY_STORAGE_DIR = (MODULE3_DIR / "storage").resolve()


def _load_module3_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig", override=False)
    custom_env_file = str(os.getenv("MODULE3_ENV_FILE", "") or "").strip()
    if custom_env_file:
        load_dotenv(dotenv_path=Path(custom_env_file), encoding="utf-8-sig", override=True)


def _resolve_runtime_root() -> Path:
    runtime_root = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
    if runtime_root:
        return Path(runtime_root).resolve()
    return REPO_ROOT.resolve()


def _resolve_data_root(runtime_root: Path) -> Path:
    data_root = str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
    if data_root:
        return Path(data_root).resolve()
    return (runtime_root / "runtime-data").resolve()


def _resolve_storage_dir() -> Path:
    explicit_storage_dir = str(os.getenv("MODULE3_STORAGE_DIR", "") or "").strip()
    if explicit_storage_dir:
        return Path(explicit_storage_dir).resolve()

    runtime_root = _resolve_runtime_root()
    managed_storage_dir = (_resolve_data_root(runtime_root) / "module3" / "storage").resolve()

    # In managed runtime mode, always keep artifacts out of the source tree.
    if str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip():
        return managed_storage_dir

    # Backward-compatible local fallback for direct standalone runs.
    if LEGACY_STORAGE_DIR.exists() and not managed_storage_dir.exists():
        return LEGACY_STORAGE_DIR.resolve()
    return managed_storage_dir


STORAGE_DIR = _resolve_storage_dir()
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
    _load_module3_env()
    raw = (
        os.getenv("MODULE3_DATABASE_URL", "").strip()
        or os.getenv("MODULE3_DATABASE_DSN", "").strip()
    )
    if not raw:
        return ""
    return normalize_database_url(raw)


def read_runtime_settings(api_mode_override: str | None = None) -> dict[str, Any]:
    _load_module3_env()

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
    "BACKEND_DIR",
    "DEFAULT_HEADER_ROW",
    "DEFAULT_PROMPT",
    "DEFAULT_WRITE_ROW",
    "DOCSETS_DIR",
    "ENV_PATH",
    "LEGACY_STORAGE_DIR",
    "PREVIEW_CHAR_LIMIT",
    "PREVIEW_LINE_LIMIT",
    "REPO_ROOT",
    "RUNS_DIR",
    "STORAGE_DIR",
    "TEMPLATES_DIR",
    "normalize_database_url",
    "normalize_base_url",
    "read_database_url",
    "read_runtime_settings",
]
