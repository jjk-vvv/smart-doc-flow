from __future__ import annotations

"""Policy bundle builders for module2 extraction service layer."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException


GetEnvFn = Callable[[str, str | None], str | None]


@dataclass(frozen=True)
class Module2MainPolicyBundle:
    resolve_module2_path: Callable[[str, Path], Path]
    artifact_root_dir: Callable[[], Path]
    extraction_job_state_root_dir: Callable[[], Path]
    office_preview_timeout_sec: Callable[[], float]
    office_convert_enabled: Callable[[], bool]
    word_pdf_required: Callable[[], bool]
    visual_strict_mode: Callable[[], bool]
    visual_chain_required: Callable[[], bool]
    disable_fasttrack_fallback: Callable[[], bool]
    disable_quick_table_fallback: Callable[[], bool]
    build_preflight_provider: Callable[[float], Any]
    provider_unavailable_http_exception: Callable[[Exception], HTTPException]
    docx_native_recovery_enabled: Callable[[], bool]
    utcnow_factory: Callable[[], datetime]


def build_module2_main_policy_bundle(
    *,
    module2_root: Path,
    getenv: GetEnvFn,
    build_module2_llm_provider_fn: Callable[..., Any],
) -> Module2MainPolicyBundle:
    module2_root = Path(module2_root).resolve()

    def _runtime_root_dir() -> Path:
        configured = str(getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return module2_root.parents[1].resolve()

    def _data_root_dir() -> Path:
        configured = str(getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        runtime_root = _runtime_root_dir()
        runtime_data_dir = (runtime_root / "runtime-data").resolve()
        if runtime_data_dir.exists():
            return runtime_data_dir
        return runtime_root

    def _env_truthy(name: str, default: str) -> bool:
        return (getenv(name, default) or default).lower() in {"1", "true", "yes"}

    def _resolve_module2_path(raw_value: str, default_path: Path) -> Path:
        raw = str(raw_value or "").strip()
        if not raw:
            return default_path.resolve()
        path = Path(raw)
        if path.is_absolute():
            return path.resolve()

        candidate_module2 = (module2_root / path).resolve()
        candidate_repo = (module2_root.parents[1] / path).resolve()
        normalized = raw.replace("\\", "/").lower()
        if normalized.startswith("backend/module2/"):
            return candidate_repo
        if candidate_repo.exists() and not candidate_module2.exists():
            return candidate_repo
        return candidate_module2

    def _artifact_root_dir() -> Path:
        configured = getenv("MODULE2_ARTIFACT_ROOT_DIR", "") or ""
        root = _resolve_module2_path(configured, _data_root_dir() / "module2" / "artifacts")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _extraction_job_state_root_dir() -> Path:
        configured = getenv("MODULE2_EXTRACT_JOB_STATE_DIR", "") or ""
        root = _resolve_module2_path(
            configured,
            _data_root_dir() / "module2" / "runlogs" / "extraction_jobs",
        )
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _office_preview_timeout_sec() -> float:
        return max(20.0, float(getenv("MODULE2_OFFICE_PREVIEW_TIMEOUT_SEC", "120") or "120"))

    def _office_convert_enabled() -> bool:
        return _env_truthy("MODULE2_DOC_TO_PDF_ENABLE", "true")

    def _word_pdf_required() -> bool:
        raw = (
            getenv(
                "MODULE2_WORD_PARSE_VIA_PDF",
                getenv("MODULE2_WORD_REQUIRE_PDF_PARSE", "true"),
            )
            or "true"
        ).lower()
        return raw in {"1", "true", "yes"}

    def _visual_strict_mode() -> bool:
        return _env_truthy("MODULE2_VISUAL_STRICT", "true")

    def _visual_chain_required() -> bool:
        return _env_truthy("MODULE2_REQUIRE_VISUAL_CHAIN", "true")

    def _disable_fasttrack_fallback() -> bool:
        return _env_truthy("MODULE2_DISABLE_FASTTRACK_FALLBACK", "true")

    def _disable_quick_table_fallback() -> bool:
        return _env_truthy("MODULE2_DISABLE_QUICK_TABLE_FALLBACK", "true")

    def _build_preflight_provider(timeout_sec: float) -> Any:
        return build_module2_llm_provider_fn(
            temperature=0.0,
            max_tokens=8,
            timeout_sec=timeout_sec,
        )

    def _provider_unavailable_http_exception(exc: Exception) -> HTTPException:
        return HTTPException(
            status_code=503,
            detail=(
                "Extraction provider preflight failed before job creation: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    def _docx_native_recovery_enabled() -> bool:
        return _env_truthy("MODULE2_DOCX_NATIVE_RECOVERY_ENABLE", "false")

    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    return Module2MainPolicyBundle(
        resolve_module2_path=_resolve_module2_path,
        artifact_root_dir=_artifact_root_dir,
        extraction_job_state_root_dir=_extraction_job_state_root_dir,
        office_preview_timeout_sec=_office_preview_timeout_sec,
        office_convert_enabled=_office_convert_enabled,
        word_pdf_required=_word_pdf_required,
        visual_strict_mode=_visual_strict_mode,
        visual_chain_required=_visual_chain_required,
        disable_fasttrack_fallback=_disable_fasttrack_fallback,
        disable_quick_table_fallback=_disable_quick_table_fallback,
        build_preflight_provider=_build_preflight_provider,
        provider_unavailable_http_exception=_provider_unavailable_http_exception,
        docx_native_recovery_enabled=_docx_native_recovery_enabled,
        utcnow_factory=_utcnow,
    )
