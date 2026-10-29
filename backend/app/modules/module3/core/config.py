from __future__ import annotations

import json
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
BACKEND_ENV_PATH = (BACKEND_DIR / ".env").resolve()
ENV_PATH = (MODULE3_DIR / ".env").resolve()
LEGACY_STORAGE_DIR = (MODULE3_DIR / "storage").resolve()


def _load_module3_env() -> None:
    # Load unified backend runtime env first so auth/session config remains
    # consistent when module3 is started as an independent service.
    load_dotenv(dotenv_path=BACKEND_ENV_PATH, encoding="utf-8-sig", override=False)
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
DEFAULT_STRUCTURED_METRIC_PROFILE: dict[str, Any] = {
    "header_aliases": {
        "region": ["国家/地区", "国家地区", "country/region", "country", "region"],
        "gdp_per_capita": ["人均GDP", "人均 gdp", "gdp per capita"],
        "population": ["人口", "总人口", "population"],
        "daily_tests": ["每日检测数", "检测数", "每日检测", "daily tests", "tests"],
        "cases": ["病例数", "病例", "确诊数", "cases", "case count"],
    },
    "root_regions": ["中国", "China", "PRC"],
    "region_suffixes": ["省", "市", "自治区", "特别行政区"],
    "cn_numeric_multipliers": [
        ["万亿", 1_000_000_000_000.0],
        ["亿", 100_000_000.0],
        ["万", 10_000.0],
        ["千", 1_000.0],
    ],
    "case_exclude_keywords": ["解除隔离", "解除医学观察", "治愈", "出院", "康复"],
    "case_strong_keywords": ["确诊", "无症状"],
    "case_weak_keywords": ["疑似"],
}


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    output: list[str] = []
    for item in value:
        token = str(item or "").strip()
        if token:
            output.append(token)
    return output


def _normalize_multiplier_list(value: Any) -> list[tuple[str, float]]:
    if not isinstance(value, (list, tuple)):
        return []
    output: list[tuple[str, float]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        unit = str(item[0] or "").strip()
        if not unit:
            continue
        try:
            multiplier = float(item[1])
        except (TypeError, ValueError):
            continue
        output.append((unit, multiplier))
    return output


def read_structured_metric_profile() -> dict[str, Any]:
    _load_module3_env()
    raw = str(os.getenv("MODULE3_STRUCTURED_METRIC_PROFILE_JSON", "") or "").strip()

    profile: dict[str, Any] = {
        "header_aliases": {
            key: list(value)
            for key, value in DEFAULT_STRUCTURED_METRIC_PROFILE["header_aliases"].items()
        },
        "root_regions": list(DEFAULT_STRUCTURED_METRIC_PROFILE["root_regions"]),
        "region_suffixes": list(DEFAULT_STRUCTURED_METRIC_PROFILE["region_suffixes"]),
        "cn_numeric_multipliers": [
            (str(unit), float(multiplier))
            for unit, multiplier in DEFAULT_STRUCTURED_METRIC_PROFILE["cn_numeric_multipliers"]
        ],
        "case_exclude_keywords": list(DEFAULT_STRUCTURED_METRIC_PROFILE["case_exclude_keywords"]),
        "case_strong_keywords": list(DEFAULT_STRUCTURED_METRIC_PROFILE["case_strong_keywords"]),
        "case_weak_keywords": list(DEFAULT_STRUCTURED_METRIC_PROFILE["case_weak_keywords"]),
    }

    if not raw:
        return profile

    try:
        override = json.loads(raw)
    except json.JSONDecodeError:
        return profile
    if not isinstance(override, dict):
        return profile

    header_aliases = override.get("header_aliases")
    if isinstance(header_aliases, dict):
        for key, aliases in header_aliases.items():
            key_text = str(key or "").strip()
            if not key_text:
                continue
            normalized_aliases = _normalize_string_list(aliases)
            if normalized_aliases:
                profile["header_aliases"][key_text] = normalized_aliases

    for list_key in ("root_regions", "region_suffixes", "case_exclude_keywords", "case_strong_keywords", "case_weak_keywords"):
        normalized = _normalize_string_list(override.get(list_key))
        if normalized:
            profile[list_key] = normalized

    multiplier_items = _normalize_multiplier_list(override.get("cn_numeric_multipliers"))
    if multiplier_items:
        profile["cn_numeric_multipliers"] = multiplier_items

    return profile


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

    base_url = normalize_base_url(os.getenv("OPENAI_BASE_URL", "https://quanzil.com/v1"))
    model = os.getenv("OPENAI_MODEL", "qwen-max").strip() or "qwen-max"
    vision_model = (
        os.getenv("OPENAI_VISION_MODEL", "").strip()
        or os.getenv("MODULE3_VISION_MODEL", "").strip()
        or model
    )
    api_mode = (api_mode_override or os.getenv("OPENAI_API_MODE", "chat")).strip().lower()
    if api_mode != "chat":
        raise ValueError("OPENAI_API_MODE now only supports chat for qwen-compatible deployments")

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
        "vision_model": vision_model,
        "api_mode": api_mode,
        "max_images": max_images,
        "max_image_bytes": max_image_bytes,
    }


__all__ = [
    "ALLOWED_SOURCE_SUFFIXES",
    "ALLOWED_TEMPLATE_SUFFIXES",
    "BASE_DIR",
    "BACKEND_DIR",
    "DEFAULT_STRUCTURED_METRIC_PROFILE",
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
    "read_structured_metric_profile",
]
