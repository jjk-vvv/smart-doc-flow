from __future__ import annotations

import asyncio
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from app.core.config import Settings
from app.core.health import probe_json, probe_path
from app.services.auth_service import get_auth_service
from app.core.auth_tenant import resolve_authenticated_tenant
from app.modules.module4.core.module4_sidecar_runtime import (
    get_module4_sidecar_settings,
    get_module4_sidecar_manager,
    resolve_live_module4_upstream_url,
)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


@dataclass(frozen=True)
class UpstreamTarget:
    name: str
    base_url: str
    health_path: str
    mode: str = "upstream"


def list_upstream_targets(settings: Settings) -> tuple[UpstreamTarget, ...]:
    return (
        UpstreamTarget("auth", "", "/api/auth/health", mode="local"),
        UpstreamTarget("module2", "", "/healthz", mode="local"),
        UpstreamTarget("module4", settings.module4_upstream_url, "/module4/healthz"),
    )


def build_gateway_info(settings: Settings) -> dict[str, Any]:
    module4_sidecar_settings = get_module4_sidecar_settings()
    return {
        "ok": True,
        "gateway": {
            "host": settings.gateway_host,
            "port": settings.gateway_port,
        },
        "auth": {
            "tenant_mode": settings.auth_tenant_mode,
            "tenant_default_id": settings.auth_tenant_default_id,
        },
        "runtime": {
            "runtime_root_dir": str(settings.runtime_root_dir),
            "config_root_dir": str(settings.config_root_dir),
            "data_root_dir": str(settings.data_root_dir),
            "frontend_dist_dir": str(settings.frontend_dist_dir),
        },
        "upstreams": {
            target.name: {
                "mode": target.mode,
                "base_url": target.base_url,
                "health_path": target.health_path,
                "sidecar": (
                    {
                        "requested_mode": module4_sidecar_settings.module4_sidecar_mode,
                        "startup_timeout_sec": float(module4_sidecar_settings.module4_sidecar_startup_timeout_sec),
                    }
                    if target.name == "module4"
                    else None
                ),
            }
            for target in list_upstream_targets(settings)
        },
    }


async def build_gateway_health(settings: Settings) -> dict[str, Any]:
    health_probe_timeout_sec = float(settings.gateway_health_probe_timeout_sec)

    async def probe_local_target(target: UpstreamTarget) -> dict[str, Any]:
        if target.name == "auth":
            payload = await get_auth_service().health_payload()
        elif target.name == "module2":
            from app.services.extraction_service import get_extraction_service

            payload = await asyncio.to_thread(get_extraction_service().health_payload, settings)
        else:
            payload = {
                "ok": False,
                "service": target.name,
                "error": "Unknown local target",
            }
        return {
            "ok": bool(payload.get("ok", False)),
            "mode": "local",
            "health_path": target.health_path,
            "payload": payload,
        }

    async def probe_target(target: UpstreamTarget) -> tuple[str, dict[str, Any]]:
        if target.mode == "local":
            return target.name, await probe_local_target(target)
        if target.name == "module4":
            module4_sidecar = await asyncio.to_thread(get_module4_sidecar_manager().health_payload, settings)
            probe_payload = (
                module4_sidecar.get("probe")
                if isinstance(module4_sidecar.get("probe"), dict)
                else {}
            )
            resolved_url = str(module4_sidecar.get("preferred_base_url") or target.base_url or "").rstrip("/")
            return target.name, {
                "ok": bool(probe_payload.get("ok")) or bool(module4_sidecar.get("healthy")),
                "mode": str(module4_sidecar.get("active_mode") or target.mode),
                "health_path": target.health_path,
                "configured_url": target.base_url,
                "resolved_url": resolved_url,
                "payload": probe_payload.get("payload", {}),
                "status_code": int(probe_payload.get("status_code", 0) or 0),
                "url": str(probe_payload.get("url") or ""),
                "error": str(probe_payload.get("error") or ""),
                "sidecar": module4_sidecar,
            }
        url = f"{target.base_url.rstrip('/')}{target.health_path}"
        result = await asyncio.to_thread(probe_json, url, health_probe_timeout_sec)
        result["mode"] = target.mode
        return target.name, result

    upstream_results = dict(await asyncio.gather(*(probe_target(target) for target in list_upstream_targets(settings))))
    frontend_result = probe_path(settings.frontend_dist_dir)
    overall_ok = all(result.get("ok", False) for result in upstream_results.values())

    return {
        "ok": overall_ok,
        "upstreams": upstream_results,
        "frontend_static": frontend_result,
    }


def _resolve_scope(scope: str) -> tuple[str, ...]:
    normalized = str(scope or "all").strip().lower() or "all"
    if normalized in {"all", "*"}:
        return ("auth", "module2", "module4", "frontend_static")
    if normalized == "backend":
        return ("auth", "module2", "module4")
    if normalized == "frontend":
        return ("frontend_static",)
    values = [item.strip() for item in normalized.split(",") if item.strip()]
    return tuple(values or ("auth", "module2", "module4", "frontend_static"))


async def build_gateway_readiness(settings: Settings, scope: str) -> tuple[dict[str, Any], bool]:
    health = await build_gateway_health(settings)
    requested_targets = _resolve_scope(scope)
    target_map: dict[str, Any] = {
        "frontend_static": health.get("frontend_static", {}),
        **health.get("upstreams", {}),
    }
    selected = {name: target_map.get(name, {"ok": False, "error": "Unknown readiness target"}) for name in requested_targets}
    ready = all(bool(item.get("ok")) for item in selected.values())
    payload = {
        "ok": ready,
        "scope": list(requested_targets),
        "targets": selected,
    }
    return payload, ready


def _compose_target_url(base_url: str, upstream_path: str, query_string: str) -> str:
    normalized_path = upstream_path if upstream_path.startswith("/") else f"/{upstream_path}"
    url = f"{base_url.rstrip('/')}{normalized_path}"
    if query_string:
        return f"{url}?{query_string}"
    return url


def _forward_request_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        normalized_key = key.lower().strip()
        if normalized_key in HOP_BY_HOP_HEADERS:
            continue
        out[key] = value
    return out


def _copy_response_headers(response: Response, upstream_headers) -> None:
    set_cookie_values = []
    if hasattr(upstream_headers, "get_all"):
        set_cookie_values = list(upstream_headers.get_all("Set-Cookie") or [])

    for key, value in upstream_headers.items():
        normalized_key = key.lower().strip()
        if normalized_key in HOP_BY_HOP_HEADERS or normalized_key == "set-cookie":
            continue
        response.headers[key] = value

    for cookie in set_cookie_values:
        response.headers.append("set-cookie", cookie)


def _open_upstream(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout_sec: float,
):
    request = urllib.request.Request(
        url=url,
        data=body if body else None,
        headers=headers,
        method=method.upper(),
    )
    return urllib.request.urlopen(request, timeout=timeout_sec)


def _stream_upstream_body(upstream_response, chunk_size: int) -> Iterable[bytes]:
    try:
        while True:
            chunk = upstream_response.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        upstream_response.close()


def _should_stream_response(upstream_headers) -> bool:
    content_type = str(upstream_headers.get("Content-Type", "") or "").lower()
    if "text/event-stream" in content_type:
        return True
    return bool(upstream_headers.get("X-Vercel-AI-Data-Stream"))


async def proxy_request(
    request: Request,
    settings: Settings,
    upstream_base_url: str,
    upstream_path: str,
    *,
    additional_headers: dict[str, str] | None = None,
) -> Response:
    target_url = _compose_target_url(upstream_base_url, upstream_path, request.url.query)
    request_body = await request.body()
    request_headers = _forward_request_headers(request)
    for key, value in (additional_headers or {}).items():
        normalized_key = str(key or "").lower().strip()
        if not normalized_key or normalized_key in HOP_BY_HOP_HEADERS:
            continue
        request_headers[key] = value

    try:
        upstream_response = await asyncio.to_thread(
            _open_upstream,
            request.method,
            target_url,
            request_headers,
            request_body,
            settings.request_timeout_sec,
        )
    except urllib.error.HTTPError as exc:
        error_body = await asyncio.to_thread(exc.read)
        response = Response(content=error_body, status_code=exc.code)
        _copy_response_headers(response, exc.headers)
        return response
    except urllib.error.URLError as exc:
        return Response(
            content=f'{{"error": "Gateway timeout or upstream service unavailable", "detail": "{str(exc.reason)}"}}'.encode("utf-8"),
            status_code=502,
            media_type="application/json"
        )
    except Exception as exc:
        return Response(
            content=f'{{"error": "Internal gateway error", "detail": "{str(exc)}"}}'.encode("utf-8"),
            status_code=500,
            media_type="application/json"
        )

    if request.method.upper() == "HEAD":
        response = Response(status_code=int(getattr(upstream_response, "status", 200) or 200))
        _copy_response_headers(response, upstream_response.headers)
        upstream_response.close()
        return response

    if _should_stream_response(upstream_response.headers):
        response = StreamingResponse(
            _stream_upstream_body(upstream_response, settings.stream_chunk_size),
            status_code=int(getattr(upstream_response, "status", 200) or 200),
        )
        _copy_response_headers(response, upstream_response.headers)
        return response

    response_body = await asyncio.to_thread(upstream_response.read)
    response = Response(
        content=response_body,
        status_code=int(getattr(upstream_response, "status", 200) or 200),
    )
    _copy_response_headers(response, upstream_response.headers)
    upstream_response.close()
    return response


async def proxy_module4_request(
    request: Request,
    settings: Settings,
    upstream_path: str,
    *,
    additional_headers: dict[str, str] | None = None,
) -> Response:
    request_body = await request.body()
    tenant_resolution = resolve_authenticated_tenant(
        settings,
        request=request,
        additional_headers=additional_headers,
        request_body=request_body,
    )
    merged_headers = dict(additional_headers or {})
    merged_headers.update(tenant_resolution.to_forward_headers())
    upstream_base_url = resolve_live_module4_upstream_url(settings, ensure_sidecar=True)
    return await proxy_request(
        request,
        settings,
        upstream_base_url,
        upstream_path,
        additional_headers=merged_headers,
    )
