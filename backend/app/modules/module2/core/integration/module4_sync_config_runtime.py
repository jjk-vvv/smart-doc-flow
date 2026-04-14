from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException


EnvGetter = Callable[[str, str], str]


class Module4SyncConfigRuntime:
    """Resolve module4 sync configuration, tenant selection, and retry policy."""

    def __init__(self, *, env_get: EnvGetter | None = None) -> None:
        self._env_get = env_get or os.getenv

    @staticmethod
    def _bool_value(raw: str, *, default: bool) -> bool:
        text = str(raw or "").strip().lower()
        if not text:
            return default
        return text in {"1", "true", "yes"}

    @staticmethod
    def _int_value(raw: str, *, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(str(raw or "").strip() or str(default))
        except Exception:
            value = default
        return max(minimum, min(value, maximum))

    @staticmethod
    def _float_value(raw: str, *, default: float, minimum: float) -> float:
        try:
            value = float(str(raw or "").strip() or str(default))
        except Exception:
            value = default
        return max(minimum, value)

    def sync_enabled(self) -> bool:
        return self._bool_value(self._env_get("MODULE2_MODULE4_SYNC_ENABLED", "true"), default=True)

    def document_sync_enabled(self) -> bool:
        return self._bool_value(
            self._env_get("MODULE2_MODULE4_DOCUMENT_SYNC_ENABLED", "false"),
            default=False,
        )

    def document_sync_per_file_enabled(self) -> bool:
        return self._bool_value(
            self._env_get("MODULE2_MODULE4_SYNC_PER_FILE_ENABLE", "true"),
            default=True,
        )

    def document_sync_final_batch_enabled(self) -> bool:
        return self._bool_value(
            self._env_get("MODULE2_MODULE4_SYNC_FINAL_BATCH_ENABLE", "false"),
            default=False,
        )

    def payload_mode(self) -> str:
        raw = str(self._env_get("MODULE2_MODULE4_SYNC_PAYLOAD_MODE", "hybrid") or "").strip().lower()
        if raw in {"hybrid", "text_corpus_only"}:
            return raw
        return "hybrid"

    def base_url(self) -> str:
        raw = str(self._env_get("MODULE2_MODULE4_BASE_URL", "http://localhost:8100") or "").strip().rstrip("/")
        return raw or "http://localhost:8100"

    def timeout_sec(self) -> float:
        return self._float_value(
            self._env_get("MODULE2_MODULE4_SYNC_TIMEOUT_SEC", "12"),
            default=12.0,
            minimum=2.0,
        )

    def retries(self) -> int:
        return self._int_value(
            self._env_get("MODULE2_MODULE4_SYNC_RETRIES", "2"),
            default=2,
            minimum=0,
            maximum=5,
        )

    def backoff_sec(self) -> float:
        return self._float_value(
            self._env_get("MODULE2_MODULE4_SYNC_BACKOFF_SEC", "1.5"),
            default=1.5,
            minimum=0.2,
        )

    def shutdown_drain_sec(self) -> float:
        return self._float_value(
            self._env_get("MODULE2_MODULE4_SHUTDOWN_DRAIN_SEC", "8"),
            default=8.0,
            minimum=0.0,
        )

    def tenant_guard_mode(self) -> str:
        raw_mode = str(
            self._env_get("MODULE2_MODULE4_TENANT_GUARD_MODE", "compat_default") or ""
        ).strip().lower()
        if raw_mode in {"strict", "strict_authenticated_tenant", "authenticated_required"}:
            return "authenticated_required"
        return "compat_default"

    def default_tenant(self) -> str:
        return str(self._env_get("MODULE2_MODULE4_DEFAULT_TENANT", "default") or "default").strip() or "default"

    def tenant(self, request: Optional[Any] = None, explicit: str = "") -> str:
        explicit_clean = str(explicit or "").strip()
        header_tenant = ""
        authenticated_tenant = ""
        authenticated_user = ""
        if request is not None:
            headers = getattr(request, "headers", None)
            if headers is not None:
                header_tenant = str(headers.get("x-tenant-id") or "").strip()
                authenticated_tenant = str(headers.get("x-authenticated-tenant-id") or "").strip()
                authenticated_user = str(headers.get("x-authenticated-user-id") or "").strip()
        authenticated_owner = authenticated_tenant or authenticated_user
        if authenticated_owner:
            if explicit_clean and explicit_clean != authenticated_owner:
                raise HTTPException(status_code=403, detail="tenant mismatch for authenticated request")
            if header_tenant and header_tenant != authenticated_owner:
                raise HTTPException(status_code=403, detail="tenant mismatch for authenticated request")
            return authenticated_owner

        if self.tenant_guard_mode() == "authenticated_required":
            raise HTTPException(status_code=401, detail="authenticated tenant headers required")

        if explicit_clean:
            return explicit_clean
        if header_tenant:
            return header_tenant
        return self.default_tenant()

    def headers(self, tenant_id: str, *, authenticated_tenant_id: str = "") -> Dict[str, str]:
        tenant_value = str(tenant_id or "").strip()
        authenticated_value = str(authenticated_tenant_id or "").strip() or tenant_value
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-Id": tenant_value,
        }
        if authenticated_value:
            headers["X-Authenticated-Tenant-Id"] = authenticated_value
        bearer = str(self._env_get("MODULE2_MODULE4_BEARER_TOKEN", "") or "").strip()
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        return headers

    @staticmethod
    def retryable_status(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    def delay_sec(self, attempt_index: int) -> float:
        base = self.backoff_sec()
        return min(base * (2 ** max(0, int(attempt_index or 0) - 1)), 12.0)
