from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


CheckCache = Callable[[str], Awaitable[Optional[Dict[str, Any]]]]
FindRecentDocumentCaches = Callable[[str], Awaitable[List[Dict[str, Any]]]]
CurrentExtractionCacheVersion = Callable[[], str]
CurrentExtractionLogicComponents = Callable[[], Dict[str, Any]]
CurrentExtractionLogicVersion = Callable[[], str]
GetEnv = Callable[[str, str], str]
SchemaTargetFields = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class RouteDecision:
    file_hash: str
    cache_key: str
    track: str
    cached_payload: Optional[Dict[str, Any]]
    cache_lookup_mode: str = "miss"


class StreamRouterRuntime:
    """Layer 1: ingestion triage for cache hit detection and track selection."""

    def __init__(
        self,
        *,
        check_cache: CheckCache,
        find_recent_document_caches: FindRecentDocumentCaches | None = None,
        current_extraction_cache_version: CurrentExtractionCacheVersion,
        current_extraction_logic_components: CurrentExtractionLogicComponents | None = None,
        current_extraction_logic_version: CurrentExtractionLogicVersion | None = None,
        schema_target_fields: SchemaTargetFields | None = None,
        getenv: GetEnv = os.getenv,
    ) -> None:
        self._check_cache = check_cache
        self._find_recent_document_caches = find_recent_document_caches
        self._current_extraction_cache_version = current_extraction_cache_version
        self._current_extraction_logic_components = current_extraction_logic_components
        self._current_extraction_logic_version = current_extraction_logic_version
        self._schema_target_fields = schema_target_fields
        self._getenv = getenv

    async def triage(
        self,
        file_name: str,
        file_bytes: bytes,
        schema_hash: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> RouteDecision:
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        cache_key = hashlib.sha256(
            f"{self._current_extraction_cache_version()}:{file_hash}:{schema_hash}".encode("utf-8")
        ).hexdigest()
        cached = await self._check_cache(cache_key)
        if cached and not self._should_skip_cached_payload(cached):
            return RouteDecision(
                file_hash=file_hash,
                cache_key=cache_key,
                track="CacheHit",
                cached_payload=cached,
                cache_lookup_mode="exact",
            )

        compatible_cached = await self._find_compatible_auto_cache(
            file_hash=file_hash,
            schema_hash=schema_hash,
            schema=schema,
        )
        if compatible_cached is not None:
            return RouteDecision(
                file_hash=file_hash,
                cache_key=cache_key,
                track="CacheHit",
                cached_payload=compatible_cached,
                cache_lookup_mode="compatible_auto",
            )

        if not file_name.lower().endswith(".pdf"):
            return RouteDecision(file_hash=file_hash, cache_key=cache_key, track="FastTrack", cached_payload=None)

        force_visual = (self._getenv("MODULE2_PDF_FORCE_VISUAL", "true") or "true").lower() in {"1", "true", "yes"}
        if force_visual:
            track = "VisualTrack"
        else:
            track = "FastTrack" if self.is_native_pdf(file_name, file_bytes) else "VisualTrack"
        return RouteDecision(file_hash=file_hash, cache_key=cache_key, track=track, cached_payload=None)

    def _allow_degraded_cache_restore(self) -> bool:
        raw = str(self._getenv("MODULE2_ALLOW_DEGRADED_CACHE_RESTORE", "false") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _should_skip_cached_payload(self, payload: Dict[str, Any]) -> bool:
        if self._allow_degraded_cache_restore():
            return False
        if not isinstance(payload, dict):
            return False

        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = payload.get("metrics")
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}

        quality_status = str(diagnostics.get("quality_status") or "").strip().lower()
        if quality_status == "degraded":
            return True

        quality_reasons = diagnostics.get("quality_reasons")
        if isinstance(quality_reasons, list):
            for item in quality_reasons:
                reason = str(item or "").strip().lower()
                if reason.startswith("low_coverage") or reason.startswith("low_confidence"):
                    return True

        result_payload = payload.get("result")
        field_count = len(result_payload) if isinstance(result_payload, dict) else 0
        target_candidates = [
            diagnostics.get("quality_target_field_count"),
            diagnostics.get("schema_field_count"),
            diagnostics.get("target_field_count"),
        ]
        target_field_count = 0
        for candidate in target_candidates:
            try:
                value = int(float(candidate or 0))
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                target_field_count = value
                break
        if target_field_count > 0 and field_count < target_field_count:
            return True

        warnings = payload.get("soft_warnings")
        if not isinstance(warnings, list):
            return False
        warning_texts = [str(item or "").strip().lower() for item in warnings if str(item or "").strip()]
        retryable_prefixes = (
            "quality_gate_degraded",
            "table_extract_timeout",
            "field_extract_timeout",
            "table_extract_error:",
            "field_extract_error:",
            "upstream_rate_limited_retryable",
            "upstream_connection_retryable",
            "downgraded:",
        )
        for text in warning_texts:
            if any(text.startswith(prefix) for prefix in retryable_prefixes):
                return True
            if "http error 429" in text or "too many requests" in text or "rate limit" in text:
                return True
        return False

    async def _find_compatible_auto_cache(
        self,
        *,
        file_hash: str,
        schema_hash: str,
        schema: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self._supports_compatible_auto_cache():
            return None
        if not self._is_fieldless_auto_schema(schema):
            return None

        candidates = await self._find_recent_document_caches(str(file_hash or "").strip())
        for payload in candidates:
            if not isinstance(payload, dict):
                continue
            if str(payload.get("file_hash", "") or "").strip() != str(file_hash or "").strip():
                continue
            if self._should_skip_cached_payload(payload):
                continue
            if not self._is_auto_schema_payload(payload):
                continue
            if not self._is_logic_compatible(payload):
                continue
            payload_schema_hash = str(payload.get("schema_hash", "") or "").strip()
            if payload_schema_hash and payload_schema_hash == str(schema_hash or "").strip():
                continue
            return dict(payload)
        return None

    def _supports_compatible_auto_cache(self) -> bool:
        return (
            callable(self._find_recent_document_caches)
            and (
                callable(self._current_extraction_logic_version)
                or callable(self._current_extraction_logic_components)
            )
        )

    def _is_logic_compatible(self, payload: Dict[str, Any]) -> bool:
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = payload.get("metrics")
        if not isinstance(diagnostics, dict):
            return False

        if callable(self._current_extraction_logic_version):
            cached_logic_version = str(diagnostics.get("extraction_logic_version", "") or "").strip()
            current_logic_version = str(self._current_extraction_logic_version() or "").strip()
            if bool(cached_logic_version) and cached_logic_version == current_logic_version:
                return True

        cached_logic_components = diagnostics.get("extraction_logic_components")
        if not isinstance(cached_logic_components, dict):
            return False
        if not callable(self._current_extraction_logic_components):
            return False

        try:
            current_logic_components = dict(self._current_extraction_logic_components() or {})
        except Exception:
            current_logic_components = {}
        if not current_logic_components:
            return False

        return self._normalized_logic_compatibility_signature(
            cached_logic_components
        ) == self._normalized_logic_compatibility_signature(current_logic_components)

    @classmethod
    def _normalized_logic_compatibility_signature(cls, value: Any) -> Any:
        if isinstance(value, dict):
            normalized: Dict[str, Any] = {}
            for key in sorted(str(item) for item in value.keys()):
                if key == "runtime_code_fingerprint":
                    continue
                normalized[key] = cls._normalized_logic_compatibility_signature(value.get(key))
            return normalized
        if isinstance(value, list):
            return [cls._normalized_logic_compatibility_signature(item) for item in value]
        return value

    def _is_auto_schema_payload(self, payload: Dict[str, Any]) -> bool:
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = payload.get("metrics")
        if not isinstance(diagnostics, dict):
            return False
        return str(diagnostics.get("schema_mode", "") or "").strip().lower() == "auto"

    def _is_fieldless_auto_schema(self, schema: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(schema, dict):
            return False
        if not bool(schema.get("auto_infer")):
            return False
        if callable(self._schema_target_fields):
            try:
                target_fields = self._schema_target_fields(schema)
            except Exception:
                target_fields = {}
            return not bool(target_fields)

        fields = schema.get("fields")
        if isinstance(fields, dict) and any(str(key or "").strip() for key in fields):
            return False
        excluded = {"dependencies", "validations", "required", "auto_infer", "max_auto_fields", "prefer_llm"}
        explicit = [key for key in schema.keys() if str(key) not in excluded]
        return len(explicit) == 0

    @staticmethod
    def is_native_pdf(file_name: str, file_bytes: bytes) -> bool:
        if not file_name.lower().endswith(".pdf"):
            return False

        sample = file_bytes[:200000]
        has_text_ops = b"BT" in sample and b"ET" in sample
        has_font = b"/Font" in sample
        image_heavy = sample.count(b"/Image") > 20
        return has_text_ops and has_font and not image_heavy
