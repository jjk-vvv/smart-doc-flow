from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env_str(name: str, default: str = "") -> str:
    value = str(os.getenv(name, default) or "").strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw_value = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class ExtractionSettings:
    module2_port_hint: str
    artifact_root_dir: str
    module2_execution_mode: str
    module2_fallback_to_upstream: bool
    module2_worker_timeout_sec: float
    module2_worker_python: str
    module2_sidecar_mode: str
    module2_sidecar_python: str
    module2_sidecar_startup_timeout_sec: float
    max_file_mb: int
    doc_to_pdf_enable: bool
    office_preview_timeout_sec: float
    office_preview_job_ttl_sec: float
    office_preview_job_cap: int
    extract_job_ttl_sec: float
    extract_job_cap: int
    shadow_poll_timeout_sec: float
    shadow_poll_interval_sec: float
    job_tenant_guard_mode: str = "warn"
    assistant1_mode: str = "upstream"
    assistant1_fallback_to_legacy: bool = True
    assistant1_context_max_source_chars: int = 12000
    assistant1_context_max_refs: int = 6
    assistant1_history_window: int = 12
    module2_legacy_import_fallback: bool = False

    @classmethod
    def from_env(cls) -> "ExtractionSettings":
        assistant1_mode = _env_str("UNIFIED_EXTRACT_ASSISTANT1_MODE", "upstream").lower()
        if assistant1_mode not in {"legacy", "native", "upstream"}:
            assistant1_mode = "upstream"
        module2_execution_mode = _env_str("UNIFIED_EXTRACT_MODULE2_EXECUTION_MODE", "upstream").lower()
        if module2_execution_mode not in {"auto", "upstream", "subprocess"}:
            module2_execution_mode = "upstream"
        module2_sidecar_mode = _env_str("UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE", "auto").lower()
        if module2_sidecar_mode not in {"disabled", "auto", "managed"}:
            module2_sidecar_mode = "auto"
        job_tenant_guard_mode = _env_str("UNIFIED_EXTRACT_JOB_TENANT_GUARD_MODE", "warn").lower()
        if job_tenant_guard_mode not in {"compat", "warn", "strict"}:
            job_tenant_guard_mode = "warn"
        return cls(
            module2_port_hint=_env_str("MODULE2_PORT", ""),
            artifact_root_dir=_env_str("MODULE2_ARTIFACT_ROOT_DIR", ""),
            module2_execution_mode=module2_execution_mode,
            module2_fallback_to_upstream=_env_bool("UNIFIED_EXTRACT_MODULE2_FALLBACK_TO_UPSTREAM", True),
            module2_worker_timeout_sec=max(30.0, _env_float("UNIFIED_EXTRACT_MODULE2_WORKER_TIMEOUT_SEC", 900.0)),
            module2_worker_python=_env_str("UNIFIED_EXTRACT_MODULE2_WORKER_PYTHON", ""),
            module2_sidecar_mode=module2_sidecar_mode,
            module2_sidecar_python=_env_str("UNIFIED_EXTRACT_MODULE2_SIDECAR_PYTHON", ""),
            module2_sidecar_startup_timeout_sec=max(
                10.0,
                _env_float("UNIFIED_EXTRACT_MODULE2_SIDECAR_STARTUP_TIMEOUT_SEC", 120.0),
            ),
            max_file_mb=max(1, _env_int("MODULE2_MAX_FILE_MB", 25)),
            doc_to_pdf_enable=_env_bool("MODULE2_DOC_TO_PDF_ENABLE", True),
            office_preview_timeout_sec=max(20.0, _env_float("MODULE2_OFFICE_PREVIEW_TIMEOUT_SEC", 120.0)),
            office_preview_job_ttl_sec=max(120.0, _env_float("MODULE2_OFFICE_PREVIEW_JOB_TTL_SEC", 1800.0)),
            office_preview_job_cap=max(20, _env_int("MODULE2_OFFICE_PREVIEW_JOB_CAP", 240)),
            extract_job_ttl_sec=max(300.0, _env_float("MODULE2_EXTRACT_JOB_TTL_SEC", 7200.0)),
            extract_job_cap=max(16, _env_int("MODULE2_EXTRACT_JOB_CAP", 240)),
            shadow_poll_timeout_sec=max(120.0, _env_float("UNIFIED_EXTRACT_SHADOW_POLL_TIMEOUT_SEC", 2700.0)),
            shadow_poll_interval_sec=max(0.5, _env_float("UNIFIED_EXTRACT_SHADOW_POLL_INTERVAL_SEC", 1.2)),
            job_tenant_guard_mode=job_tenant_guard_mode,
            assistant1_mode=assistant1_mode,
            assistant1_fallback_to_legacy=_env_bool("UNIFIED_EXTRACT_ASSISTANT1_FALLBACK_TO_LEGACY", True),
            assistant1_context_max_source_chars=max(
                1500,
                _env_int("UNIFIED_EXTRACT_ASSISTANT1_CONTEXT_MAX_SOURCE_CHARS", 12000),
            ),
            assistant1_context_max_refs=max(
                1,
                min(16, _env_int("UNIFIED_EXTRACT_ASSISTANT1_CONTEXT_MAX_REFS", 6)),
            ),
            assistant1_history_window=max(
                1,
                min(24, _env_int("UNIFIED_EXTRACT_ASSISTANT1_HISTORY_WINDOW", 12)),
            ),
            module2_legacy_import_fallback=_env_bool("UNIFIED_EXTRACT_MODULE2_LEGACY_IMPORT_FALLBACK", False),
        )


@lru_cache(maxsize=1)
def get_extraction_settings() -> ExtractionSettings:
    return ExtractionSettings.from_env()
