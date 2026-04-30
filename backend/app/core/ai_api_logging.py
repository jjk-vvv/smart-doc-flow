from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import deque
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DEFAULT_MAX_CHARS = 12_000
_DEFAULT_STRING_MAX_CHARS = 3_000
_DEFAULT_LIST_MAX_ITEMS = 80
_DEFAULT_BROWSER_BUFFER_SIZE = 500
_BACKEND_ENV_CACHE: dict[str, str] | None = None
_BROWSER_LOG_LOCK = threading.Lock()
_BROWSER_LOG_SEQUENCE = 0
_BROWSER_LOG_ENTRIES: deque[dict[str, Any]] = deque(maxlen=_DEFAULT_BROWSER_BUFFER_SIZE)


def _backend_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    except OSError:
        return {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = raw_value.strip()
        if (
            len(value) >= 2
            and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'"))
        ):
            value = value[1:-1]
        values[key] = value
    return values


def _read_backend_env() -> dict[str, str]:
    global _BACKEND_ENV_CACHE
    if _BACKEND_ENV_CACHE is None:
        _BACKEND_ENV_CACHE = _parse_env_file(_backend_env_path())
    return _BACKEND_ENV_CACHE


def _env_raw(name: str) -> str | None:
    value = os.getenv(name)
    if value is not None:
        return value
    return _read_backend_env().get(name)


def _config_names(config_prefix: str, suffix: str) -> list[str]:
    prefix = str(config_prefix or "").strip().upper()
    key_suffix = "LOGGING_ENABLED" if suffix == "ENABLED" else f"LOG_{suffix}"
    names: list[str] = []
    if prefix:
        names.append(f"{prefix}_AI_API_{key_suffix}")
    names.append(f"AI_API_{key_suffix}")
    return names


def _env_bool(config_prefix: str, suffix: str, default: bool = False) -> bool:
    for name in _config_names(config_prefix, suffix):
        raw_value = _env_raw(name)
        if raw_value is None:
            continue
        normalized = str(raw_value or "").strip().lower()
        if not normalized:
            continue
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    return default


def _env_int(config_prefix: str, suffix: str, default: int, minimum: int) -> int:
    for name in _config_names(config_prefix, suffix):
        raw_value = _env_raw(name)
        if raw_value is None:
            continue
        text = str(raw_value or "").strip()
        if not text:
            continue
        try:
            return max(minimum, int(text))
        except ValueError:
            continue
    return default


def ai_api_logging_enabled(config_prefix: str = "") -> bool:
    return _env_bool(config_prefix, "ENABLED", False)


def _max_chars(config_prefix: str = "") -> int:
    return _env_int(config_prefix, "MAX_CHARS", _DEFAULT_MAX_CHARS, 1_000)


def _string_max_chars(config_prefix: str = "") -> int:
    return _env_int(config_prefix, "STRING_MAX_CHARS", _DEFAULT_STRING_MAX_CHARS, 200)


def _list_max_items(config_prefix: str = "") -> int:
    return _env_int(config_prefix, "LIST_MAX_ITEMS", _DEFAULT_LIST_MAX_ITEMS, 10)


def _include_base64(config_prefix: str = "") -> bool:
    return _env_bool(config_prefix, "INCLUDE_BASE64", False)


def ai_api_browser_console_enabled() -> bool:
    return _env_bool("", "BROWSER_CONSOLE_ENABLED", False)


def _browser_buffer_size() -> int:
    return _env_int("", "BROWSER_CONSOLE_BUFFER_SIZE", _DEFAULT_BROWSER_BUFFER_SIZE, 50)


def _sync_browser_log_capacity() -> None:
    global _BROWSER_LOG_ENTRIES
    configured_size = _browser_buffer_size()
    if _BROWSER_LOG_ENTRIES.maxlen == configured_size:
        return
    with _BROWSER_LOG_LOCK:
        if _BROWSER_LOG_ENTRIES.maxlen == configured_size:
            return
        _BROWSER_LOG_ENTRIES = deque(list(_BROWSER_LOG_ENTRIES)[-configured_size:], maxlen=configured_size)


def _append_browser_log_entry(*, logger_name: str, message: str) -> None:
    global _BROWSER_LOG_SEQUENCE
    if not ai_api_browser_console_enabled():
        return
    _sync_browser_log_capacity()
    with _BROWSER_LOG_LOCK:
        _BROWSER_LOG_SEQUENCE += 1
        _BROWSER_LOG_ENTRIES.append(
            {
                "id": _BROWSER_LOG_SEQUENCE,
                "logger": logger_name,
                "message": message,
            }
        )


def read_ai_api_browser_log_entries(*, since_id: int = 0, limit: int = 100) -> dict[str, Any]:
    enabled = ai_api_browser_console_enabled()
    if not enabled:
        return {
            "enabled": False,
            "entries": [],
            "next_since": max(0, int(since_id or 0)),
            "latest_id": _BROWSER_LOG_SEQUENCE,
        }
    _sync_browser_log_capacity()
    normalized_since = max(0, int(since_id or 0))
    normalized_limit = max(1, min(300, int(limit or 100)))
    with _BROWSER_LOG_LOCK:
        entries = [entry for entry in _BROWSER_LOG_ENTRIES if int(entry.get("id", 0)) > normalized_since]
        selected = entries[:normalized_limit]
        latest_id = _BROWSER_LOG_SEQUENCE
    next_since = int(selected[-1]["id"]) if selected else normalized_since
    return {
        "enabled": enabled,
        "entries": selected,
        "next_since": next_since,
        "latest_id": latest_id,
    }


def _format_log_line(message: str, *args: Any) -> str:
    if not args:
        return str(message)
    try:
        return str(message) % args
    except Exception:
        joined_args = " ".join(str(arg) for arg in args)
        return f"{message} {joined_args}".strip()


def _log_ai_api_line(
    *,
    logger: logging.Logger,
    logger_name: str,
    message: str,
    args: tuple[Any, ...] = (),
) -> None:
    logger.info(message, *args)
    _append_browser_log_entry(
        logger_name=logger_name,
        message=_format_log_line(message, *args),
    )


def truncate_for_ai_api_log(value: Any, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}...<truncated {omitted} chars>"


def _is_data_payload(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("data:") and ";base64," in normalized


def _looks_like_base64(value: str) -> bool:
    text = value.strip()
    if len(text) < 512:
        return False
    if len(text) % 4 not in {0, 2, 3}:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/=\s]+", text))


def _redact_data_payload(value: str) -> str:
    prefix = value.split(",", 1)[0]
    return f"<redacted {prefix}, length={len(value)} chars>"


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").strip().lower().replace("_", "-")
    return normalized in {
        "authorization",
        "api-key",
        "apikey",
        "x-api-key",
        "x-goog-api-key",
        "token",
        "access-token",
        "refresh-token",
        "secret",
        "client-secret",
    }


def sanitize_ai_api_url(value: str, *, config_prefix: str = "") -> str:
    url = truncate_for_ai_api_log(value, _max_chars(config_prefix))
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    if not parts.query:
        return url
    redacted_query: list[tuple[str, str]] = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.strip().lower().replace("_", "-")
        if _is_sensitive_key(key) or normalized_key in {"key", "access-key"}:
            redacted_query.append((key, "redacted"))
        else:
            redacted_query.append((key, item))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted_query), parts.fragment))


def _is_vector_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return normalized in {"embedding", "embeddings", "vector", "vectors", "values"}


def _is_number_list(value: list[Any]) -> bool:
    if not value:
        return False
    sample = value[: min(len(value), 12)]
    return all(isinstance(item, (int, float)) for item in sample)


def sanitize_ai_api_log_value(value: Any, *, config_prefix: str = "", parent_key: str = "") -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized_key = key_text.strip().lower()
            if _is_sensitive_key(key_text):
                sanitized[key_text] = "<redacted>"
                continue
            if (
                normalized_key in {"data", "file_data", "image_url", "url"}
                and isinstance(item, str)
                and (_is_data_payload(item) or _looks_like_base64(item))
                and not _include_base64(config_prefix)
            ):
                sanitized[key_text] = _redact_data_payload(item) if _is_data_payload(item) else (
                    f"<redacted base64-like payload, length={len(item)} chars>"
                )
                continue
            sanitized[key_text] = sanitize_ai_api_log_value(
                item,
                config_prefix=config_prefix,
                parent_key=key_text,
            )
        return sanitized

    if isinstance(value, list):
        if _is_vector_key(parent_key) and _is_number_list(value):
            return f"<redacted numeric vector, length={len(value)}>"
        max_items = _list_max_items(config_prefix)
        items = [
            sanitize_ai_api_log_value(item, config_prefix=config_prefix, parent_key=parent_key)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            items.append(f"<truncated {len(value) - max_items} items>")
        return items

    if isinstance(value, str):
        if _is_data_payload(value) and not _include_base64(config_prefix):
            return _redact_data_payload(value)
        if parent_key.strip().lower() in {"data", "file_data"} and _looks_like_base64(value) and not _include_base64(config_prefix):
            return f"<redacted base64-like payload, length={len(value)} chars>"
        return truncate_for_ai_api_log(value, _string_max_chars(config_prefix))

    return value


def format_ai_api_log_json(value: Any, *, config_prefix: str = "") -> str:
    sanitized = sanitize_ai_api_log_value(value, config_prefix=config_prefix)
    try:
        text = json.dumps(sanitized, ensure_ascii=False, default=str)
    except TypeError:
        text = str(sanitized)
    return truncate_for_ai_api_log(text, _max_chars(config_prefix))


def extract_model_name(request_body: Any, fallback: str = "") -> str:
    fallback_text = str(fallback or "").strip()
    if isinstance(request_body, dict):
        for key in ("model", "model_name", "modelName", "modelVersion"):
            value = request_body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for key in ("metadata", "generationConfig"):
            nested = request_body.get(key)
            if isinstance(nested, dict):
                found = extract_model_name(nested)
                if found:
                    return found
    return fallback_text


def _response_to_text(response: Any, *, config_prefix: str = "") -> str:
    if response is None:
        return ""
    if isinstance(response, (dict, list)):
        return format_ai_api_log_json(response, config_prefix=config_prefix)
    if isinstance(response, bytes):
        return truncate_for_ai_api_log(response.decode("utf-8", errors="ignore"), _max_chars(config_prefix))
    if isinstance(response, str):
        text = response
    elif hasattr(response, "text"):
        text = str(getattr(response, "text") or "")
    elif hasattr(response, "model_dump"):
        try:
            return format_ai_api_log_json(response.model_dump(), config_prefix=config_prefix)
        except Exception:
            text = str(response)
    elif hasattr(response, "to_dict"):
        try:
            return format_ai_api_log_json(response.to_dict(), config_prefix=config_prefix)
        except Exception:
            text = str(response)
    else:
        text = str(response)

    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return format_ai_api_log_json(json.loads(stripped), config_prefix=config_prefix)
        except Exception:
            pass
    sanitized = sanitize_ai_api_log_value(text, config_prefix=config_prefix)
    return truncate_for_ai_api_log(str(sanitized), _max_chars(config_prefix))


def log_ai_api_request(
    *,
    api_url: str,
    request_body: Any,
    model: str = "",
    attempt: int = 1,
    max_attempts: int = 1,
    logger_name: str = "app.ai_api",
    config_prefix: str = "",
) -> None:
    if not ai_api_logging_enabled(config_prefix):
        return
    logger = logging.getLogger(logger_name)
    _log_ai_api_line(logger=logger, logger_name=logger_name, message="===== 开始调用AI大模型API =====")
    if max_attempts > 1:
        _log_ai_api_line(
            logger=logger,
            logger_name=logger_name,
            message="AI调用尝试：%s/%s",
            args=(attempt, max_attempts),
        )
    _log_ai_api_line(
        logger=logger,
        logger_name=logger_name,
        message="AI接口地址：%s",
        args=(sanitize_ai_api_url(api_url, config_prefix=config_prefix),),
    )
    _log_ai_api_line(
        logger=logger,
        logger_name=logger_name,
        message="模型名称：%s",
        args=(extract_model_name(request_body, fallback=model) or "unknown",),
    )
    _log_ai_api_line(
        logger=logger,
        logger_name=logger_name,
        message="请求参数：%s",
        args=(format_ai_api_log_json(request_body, config_prefix=config_prefix),),
    )


def log_ai_api_response(
    *,
    response: Any = None,
    response_text: str = "",
    logger_name: str = "app.ai_api",
    config_prefix: str = "",
    close_call: bool = True,
) -> None:
    if not ai_api_logging_enabled(config_prefix):
        return
    logger = logging.getLogger(logger_name)
    raw_text = _response_to_text(response_text if response_text else response, config_prefix=config_prefix)
    _log_ai_api_line(
        logger=logger,
        logger_name=logger_name,
        message="AI原始返回结果：%s",
        args=(truncate_for_ai_api_log(raw_text, _max_chars(config_prefix)),),
    )
    if close_call:
        _log_ai_api_line(logger=logger, logger_name=logger_name, message="===== AI API调用结束 =====")


def log_ai_api_exception(
    *,
    exc: BaseException,
    logger_name: str = "app.ai_api",
    config_prefix: str = "",
    close_call: bool = True,
) -> None:
    if not ai_api_logging_enabled(config_prefix):
        return
    logger = logging.getLogger(logger_name)
    _log_ai_api_line(logger=logger, logger_name=logger_name, message="AI API调用异常：%s", args=(exc,))
    if close_call:
        _log_ai_api_line(logger=logger, logger_name=logger_name, message="===== AI API调用结束 =====")


class AIAPIStreamRecorder:
    def __init__(self, *, logger_name: str = "app.ai_api", config_prefix: str = "") -> None:
        self.logger_name = logger_name
        self.config_prefix = config_prefix
        self.enabled = ai_api_logging_enabled(config_prefix)
        self.max_chars = _max_chars(config_prefix)
        self._parts: list[str] = []
        self._size = 0
        self._truncated = False

    def append(self, value: Any) -> None:
        if not self.enabled or self._truncated:
            return
        text = _response_to_text(value, config_prefix=self.config_prefix)
        if not text:
            return
        remaining = self.max_chars - self._size
        if remaining <= 0:
            self._truncated = True
            return
        if len(text) > remaining:
            self._parts.append(text[:remaining])
            self._truncated = True
        else:
            self._parts.append(text)
            self._size += len(text)

    def close(self) -> None:
        if not self.enabled:
            return
        text = "\n".join(self._parts)
        if self._truncated:
            text += "\n<truncated stream response>"
        if not text.strip():
            text = "<empty stream response>"
        log_ai_api_response(
            response_text=text,
            logger_name=self.logger_name,
            config_prefix=self.config_prefix,
        )


__all__ = [
    "AIAPIStreamRecorder",
    "ai_api_browser_console_enabled",
    "ai_api_logging_enabled",
    "extract_model_name",
    "format_ai_api_log_json",
    "log_ai_api_exception",
    "log_ai_api_request",
    "log_ai_api_response",
    "read_ai_api_browser_log_entries",
    "sanitize_ai_api_log_value",
    "sanitize_ai_api_url",
    "truncate_for_ai_api_log",
]
