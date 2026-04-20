from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from fastapi import HTTPException


EnvGetter = Callable[[str, str], str]


class Module4SyncConfigRuntime:
    """Resolve module4 sync configuration, tenant selection, and retry policy."""

    _LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}

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

    @classmethod
    def _normalized_host(cls, raw: str) -> str:
        return str(raw or "").strip().lower()

    @classmethod
    def _is_local_host(cls, raw: str) -> bool:
        return cls._normalized_host(raw) in cls._LOCAL_HOSTS

    @staticmethod
    def _parsed_port(parsed) -> int | None:
        try:
            return int(parsed.port) if parsed.port is not None else None
        except Exception:
            return None

    @staticmethod
    def _default_port_for_scheme(scheme: str) -> int | None:
        normalized = str(scheme or "").strip().lower()
        if normalized == "https":
            return 443
        if normalized == "http":
            return 80
        return None

    def _gateway_port(self) -> int | None:
        raw = str(self._env_get("GATEWAY_PORT", "") or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except Exception:
            return None

    def _same_process_module4_target(self) -> bool:
        parsed = urlparse(self.base_url())
        base_host = self._normalized_host(parsed.hostname or "")
        if not base_host:
            return False
        base_port = self._parsed_port(parsed) or self._default_port_for_scheme(parsed.scheme)
        gateway_port = self._gateway_port()
        if base_port is None or gateway_port is None or base_port != gateway_port:
            return False

        gateway_host = self._normalized_host(self._env_get("GATEWAY_HOST", "") or "")
        if not gateway_host:
            return False
        if base_host == gateway_host:
            return True
        return self._is_local_host(base_host) and self._is_local_host(gateway_host)

    def initial_dispatch_delay_sec(self) -> float:
        explicit_raw = str(self._env_get("MODULE2_MODULE4_SYNC_INITIAL_DISPATCH_DELAY_SEC", "") or "").strip()
        if explicit_raw:
            return self._float_value(
                explicit_raw,
                default=0.25,
                minimum=0.0,
            )
        default_delay = 1.5 if self._same_process_module4_target() else 0.25
        return self._float_value(
            "",
            default=default_delay,
            minimum=0.0,
        )

    def tenant_guard_mode(self) -> str:
        raw_mode = str(
            self._env_get("MODULE2_MODULE4_TENANT_GUARD_MODE", "authenticated_required") or ""
        ).strip().lower()
        if raw_mode in {"strict", "strict_authenticated_tenant", "authenticated_required"}:
            return "authenticated_required"
        if raw_mode in {"compat", "compat_default"}:
            return "compat_default"
        return "authenticated_required"

    def default_tenant(self) -> str:
        return str(self._env_get("MODULE2_MODULE4_DEFAULT_TENANT", "default") or "default").strip() or "default"

    @staticmethod
    def _resolve_authenticated_owner_from_request_state(request: Optional[Any]) -> str:
        if request is None:
            return ""
        state = getattr(request, "state", None)
        authenticated_user = getattr(state, "authenticated_user", None)
        if authenticated_user is None:
            return ""

        if isinstance(authenticated_user, dict):
            return str(
                authenticated_user.get("tenant_id")
                or authenticated_user.get("tenantId")
                or authenticated_user.get("user_id")
                or authenticated_user.get("id")
                or ""
            ).strip()

        return str(
            getattr(authenticated_user, "tenant_id", "")
            or getattr(authenticated_user, "tenantId", "")
            or getattr(authenticated_user, "user_id", "")
            or getattr(authenticated_user, "id", "")
            or ""
        ).strip()

    def tenant(self, request: Optional[Any] = None, explicit: str = "") -> str:
        explicit_clean = str(explicit or "").strip()
        header_tenant = ""
        authenticated_tenant = ""
        authenticated_user = ""
        state_authenticated_owner = ""
        if request is None and explicit_clean:
            # Embedded internal invocations can pass a pre-resolved tenant_id
            # derived from authenticated context at the API layer.
            return explicit_clean
        if request is not None:
            headers = getattr(request, "headers", None)
            if headers is not None:
                header_tenant = str(headers.get("x-tenant-id") or "").strip()
                authenticated_tenant = str(headers.get("x-authenticated-tenant-id") or "").strip()
                authenticated_user = str(headers.get("x-authenticated-user-id") or "").strip()
            state_authenticated_owner = self._resolve_authenticated_owner_from_request_state(request)

        if (
            state_authenticated_owner
            and authenticated_tenant
            and authenticated_tenant != state_authenticated_owner
        ):
            raise HTTPException(status_code=403, detail="tenant mismatch for authenticated request")
        if (
            state_authenticated_owner
            and authenticated_user
            and authenticated_user != state_authenticated_owner
        ):
            raise HTTPException(status_code=403, detail="tenant mismatch for authenticated request")

        authenticated_owner = authenticated_tenant or authenticated_user or state_authenticated_owner
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
        internal_token = str(self._env_get("MODULE2_MODULE4_INTERNAL_TOKEN", "") or "").strip()
        if internal_token:
            headers["X-Module4-Internal-Token"] = internal_token
        return headers

    @staticmethod
    def retryable_status(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    def delay_sec(self, attempt_index: int) -> float:
        base = self.backoff_sec()
        return min(base * (2 ** max(0, int(attempt_index or 0) - 1)), 12.0)
