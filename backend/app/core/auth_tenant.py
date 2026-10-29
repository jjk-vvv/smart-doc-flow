from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs

from fastapi import HTTPException, Request, status

from app.core.config import Settings
from app.core.auth_security import normalize_str

_TENANT_MODES = {"compat_default", "user_preferred", "user_strict"}


@dataclass(frozen=True)
class TenantResolution:
    tenant_id: str
    mode: str
    source: str
    requested_tenant_id: str
    header_tenant_id: str
    user_tenant_id: str
    default_tenant_id: str

    def to_forward_headers(self) -> dict[str, str]:
        return {"X-Tenant-Id": self.tenant_id}


def normalize_tenant_mode(raw_value: str) -> str:
    normalized = normalize_str(raw_value).lower()
    if normalized not in _TENANT_MODES:
        return "user_strict"
    return normalized


def _strict_mode_allow_legacy_fallback() -> bool:
    raw_value = str(os.getenv("AUTH_TENANT_STRICT_ALLOW_LEGACY_FALLBACK", "0") or "").strip().lower()
    return raw_value not in {"0", "false", "off", "no"}


def resolve_authenticated_tenant(
    settings: Settings,
    *,
    request: Request,
    additional_headers: Mapping[str, str] | None = None,
    request_body: bytes | None = None,
    explicit_tenant_id: str = "",
) -> TenantResolution:
    mode = normalize_tenant_mode(settings.auth_tenant_mode)
    default_tenant_id = normalize_str(settings.auth_tenant_default_id) or "default"
    resolved_explicit_tenant_id = normalize_str(explicit_tenant_id) or extract_explicit_tenant_candidate(
        request,
        request_body=request_body,
    )
    header_tenant_id = extract_tenant_header(request)
    user_tenant_id = extract_authenticated_user_tenant(additional_headers, request=request)

    if mode == "compat_default":
        tenant_id = resolved_explicit_tenant_id or header_tenant_id or default_tenant_id
        source = "request" if resolved_explicit_tenant_id else "header" if header_tenant_id else "default"
        return TenantResolution(
            tenant_id=tenant_id,
            mode=mode,
            source=source,
            requested_tenant_id=resolved_explicit_tenant_id,
            header_tenant_id=header_tenant_id,
            user_tenant_id=user_tenant_id,
            default_tenant_id=default_tenant_id,
        )

    if mode == "user_preferred":
        tenant_id = resolved_explicit_tenant_id or header_tenant_id or user_tenant_id or default_tenant_id
        if resolved_explicit_tenant_id:
            source = "request"
        elif header_tenant_id:
            source = "header"
        elif user_tenant_id:
            source = "authenticated_user"
        else:
            source = "default"
        return TenantResolution(
            tenant_id=tenant_id,
            mode=mode,
            source=source,
            requested_tenant_id=resolved_explicit_tenant_id,
            header_tenant_id=header_tenant_id,
            user_tenant_id=user_tenant_id,
            default_tenant_id=default_tenant_id,
        )

    if user_tenant_id:
        if resolved_explicit_tenant_id and resolved_explicit_tenant_id != user_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch for authenticated user",
            )
        if header_tenant_id and header_tenant_id != user_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch for authenticated user",
            )
        return TenantResolution(
            tenant_id=user_tenant_id,
            mode=mode,
            source="authenticated_user",
            requested_tenant_id=resolved_explicit_tenant_id,
            header_tenant_id=header_tenant_id,
            user_tenant_id=user_tenant_id,
            default_tenant_id=default_tenant_id,
        )

    if _strict_mode_allow_legacy_fallback():
        tenant_id = resolved_explicit_tenant_id or header_tenant_id or default_tenant_id
        source = "request" if resolved_explicit_tenant_id else "header" if header_tenant_id else "default"
        return TenantResolution(
            tenant_id=tenant_id,
            mode=mode,
            source=f"{source}_legacy_fallback",
            requested_tenant_id=resolved_explicit_tenant_id,
            header_tenant_id=header_tenant_id,
            user_tenant_id=user_tenant_id,
            default_tenant_id=default_tenant_id,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authenticated tenant identity is required in user_strict mode",
    )

def extract_authenticated_user_tenant(
    additional_headers: Mapping[str, str] | None = None,
    *,
    request: Request | None = None,
) -> str:
    normalized_headers = _normalize_header_mapping(additional_headers)
    tenant_id = normalize_str(normalized_headers.get("x-authenticated-tenant-id"))
    if tenant_id:
        return tenant_id
    user_id = normalize_str(normalized_headers.get("x-authenticated-user-id"))
    if user_id:
        return user_id
    if request is None:
        return ""
    request_headers = _request_headers(request)
    tenant_id = normalize_str(request_headers.get("x-authenticated-tenant-id"))
    if tenant_id:
        return tenant_id
    user_id = normalize_str(request_headers.get("x-authenticated-user-id"))
    if user_id:
        return user_id
    state_user = getattr(getattr(request, "state", None), "authenticated_user", None)
    if state_user is not None:
        tenant_id = normalize_str(getattr(state_user, "tenant_id", ""))
        if tenant_id:
            return tenant_id
        return normalize_str(getattr(state_user, "user_id", ""))
    return ""


def extract_tenant_header(request: Request | None) -> str:
    if request is None:
        return ""
    return normalize_str(_request_headers(request).get("x-tenant-id"))


def extract_explicit_tenant_candidate(request: Request | None, *, request_body: bytes | None = None) -> str:
    if request is None:
        return ""

    query_params = getattr(request, "query_params", None)
    if query_params is not None:
        tenant_id = normalize_str(query_params.get("tenant_id"))
        if tenant_id:
            return tenant_id

    content_type = normalize_str(_request_headers(request).get("content-type")).lower()
    if not request_body:
        return ""

    if "application/json" in content_type:
        payload = _decode_json_dict(request_body)
        return normalize_str(payload.get("tenant_id"))

    if "application/x-www-form-urlencoded" in content_type:
        return _decode_form_tenant_id(request_body)

    return ""


def _decode_json_dict(request_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(request_body.decode("utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _decode_form_tenant_id(request_body: bytes) -> str:
    try:
        parsed = parse_qs(request_body.decode("utf-8"), keep_blank_values=False)
    except Exception:
        return ""
    values = parsed.get("tenant_id") or []
    if not values:
        return ""
    return normalize_str(values[0])


def _normalize_header_mapping(headers: Mapping[str, str] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (headers or {}).items():
        normalized[normalize_str(key).lower()] = normalize_str(value)
    return normalized


def _request_headers(request: Request) -> Mapping[str, str]:
    headers = getattr(request, "headers", None)
    if headers is None:
        return {}
    return headers
