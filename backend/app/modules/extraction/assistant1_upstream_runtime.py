from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from fastapi import Request
from fastapi.responses import Response, StreamingResponse
from requests import RequestException, Response as RequestsResponse

from app.core.config import Settings

from .module2_request_runtime import forward_module2_context_headers
from .module2_sidecar_runtime import (
    get_module2_sidecar_manager,
    probe_module2_upstream,
    resolve_live_module2_upstream_url,
)

_HOP_BY_HOP_HEADERS = {
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
_SSE_PROXY_CHUNK_SIZE = 1


def _compose_target_url(base_url: str, upstream_path: str) -> str:
    return urljoin(f"{str(base_url or '').rstrip('/')}/", str(upstream_path or "").lstrip("/"))


def _copy_response_headers(response: Response, upstream_headers: Any) -> None:
    set_cookie_values: list[str] = []
    if hasattr(upstream_headers, "get_all"):
        set_cookie_values = list(upstream_headers.get_all("Set-Cookie") or [])

    for key, value in upstream_headers.items():
        normalized_key = str(key or "").lower().strip()
        if normalized_key in _HOP_BY_HOP_HEADERS or normalized_key == "set-cookie":
            continue
        response.headers[key] = value

    for cookie in set_cookie_values:
        response.headers.append("set-cookie", cookie)


def _stream_upstream_body(upstream_response: RequestsResponse, chunk_size: int) -> Any:
    try:
        for chunk in upstream_response.iter_content(chunk_size=max(1, int(chunk_size or 1))):
            if chunk:
                yield chunk
    finally:
        upstream_response.close()


def _error_response(*, status_code: int, detail: str) -> Response:
    return Response(
        content=json.dumps({"detail": str(detail or "").strip() or "assistant upstream request failed"}, ensure_ascii=False),
        status_code=int(status_code),
        media_type="application/json",
    )


class Assistant1UpstreamRuntime:
    assistant_path = "/extract/assistant1/chat/stream"
    session_path_template = "/extract/assistant1/sessions/{session_id}"

    @staticmethod
    def _stream_timeout_tuple(timeout_sec: float) -> tuple[float, float]:
        normalized_timeout = max(1.0, float(timeout_sec or 0.0))
        connect_timeout = min(3.0, max(0.8, normalized_timeout / 6.0))
        read_timeout = max(normalized_timeout, 300.0)
        return (connect_timeout, read_timeout)

    @staticmethod
    def _json_timeout_tuple(timeout_sec: float) -> tuple[float, float]:
        normalized_timeout = max(1.0, float(timeout_sec or 0.0))
        connect_timeout = min(3.0, max(0.8, normalized_timeout / 6.0))
        read_timeout = max(normalized_timeout, 30.0)
        return (connect_timeout, read_timeout)

    @staticmethod
    def _stream_request(
        *,
        base_url: str,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_sec: float,
    ) -> RequestsResponse:
        return requests.post(
            _compose_target_url(base_url, path),
            json=payload,
            headers=headers,
            timeout=Assistant1UpstreamRuntime._stream_timeout_tuple(timeout_sec),
            stream=True,
        )

    @staticmethod
    def _json_request(
        *,
        base_url: str,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        timeout_sec: float,
    ) -> RequestsResponse:
        return requests.get(
            _compose_target_url(base_url, path),
            params=params,
            headers=headers,
            timeout=Assistant1UpstreamRuntime._json_timeout_tuple(timeout_sec),
        )

    @staticmethod
    def _preferred_assistant_base_urls(base_url: str) -> list[str]:
        normalized = str(base_url or "").strip().rstrip("/")
        if not normalized:
            return []
        parsed = urlparse(normalized)
        host = str(parsed.hostname or "").strip().lower()
        if host not in {"127.0.0.1", "localhost"}:
            return [normalized]
        scheme = str(parsed.scheme or "http").strip() or "http"
        if parsed.port is not None:
            port = int(parsed.port)
        elif scheme == "https":
            port = 443
        else:
            port = 80
        if int(port) != 8000:
            return [normalized]
        preferred = f"{scheme}://{host}:8010"
        return [preferred, normalized]

    def _resolve_target_base_url(
        self,
        settings: Settings,
        *,
        ensure_managed_start: bool,
        force_refresh: bool = False,
    ) -> str:
        resolved_url = str(
            resolve_live_module2_upstream_url(
                settings,
                force_refresh=bool(force_refresh),
            )
            or ""
        ).strip().rstrip("/")

        # Fast path: trust recently resolved cached URL to avoid expensive upstream probing
        # on every request. If connection fails later, caller can retry with force_refresh=True.
        if resolved_url and not force_refresh:
            return resolved_url

        if not resolved_url and not force_refresh:
            resolved_url = str(resolve_live_module2_upstream_url(settings, force_refresh=True) or "").strip().rstrip("/")

        if resolved_url:
            probe_payload = probe_module2_upstream(resolved_url, min(float(settings.request_timeout_sec), 2.0))
            if bool(probe_payload.get("ok")):
                return resolved_url

        if ensure_managed_start:
            sidecar_base_url = str(get_module2_sidecar_manager().ensure_ready(settings) or "").strip().rstrip("/")
            if sidecar_base_url:
                return sidecar_base_url

        return resolved_url

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        sidecar_payload = get_module2_sidecar_manager().health_payload(settings)
        resolved_url = str(resolve_live_module2_upstream_url(settings, force_refresh=False) or "").strip().rstrip("/")
        probe_payload = probe_module2_upstream(resolved_url, min(float(settings.request_timeout_sec), 2.0)) if resolved_url else {}
        runtime_ready = bool(probe_payload.get("ok")) or bool(sidecar_payload.get("healthy"))
        return {
            "ok": runtime_ready,
            "configured": bool(resolved_url),
            "runtime_ready": runtime_ready,
            "model": "",
            "base_url": resolved_url,
            "endpoint_path": self.assistant_path,
            "tavily_configured": False,
            "transport": "module2_upstream",
            "sidecar": sidecar_payload,
            "probe": probe_payload,
        }

    def build_stream_response(
        self,
        settings: Settings,
        *,
        request: Request,
        payload: Any,
        additional_headers: dict[str, str] | None = None,
    ) -> Response:
        try:
            base_url = self._resolve_target_base_url(
                settings,
                ensure_managed_start=True,
                force_refresh=False,
            )
        except Exception as exc:
            return _error_response(status_code=502, detail=f"Module2 assistant upstream unavailable: {type(exc).__name__}: {exc}")

        if not str(base_url or "").strip():
            return _error_response(status_code=502, detail="Module2 assistant upstream is not configured")

        request_headers = forward_module2_context_headers(request, additional_headers=additional_headers)
        request_headers["Accept"] = "text/event-stream"
        request_payload = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else dict(payload or {})

        upstream_response = None
        first_error = None
        for candidate_base_url in self._preferred_assistant_base_urls(base_url):
            try:
                upstream_response = self._stream_request(
                    base_url=candidate_base_url,
                    path=self.assistant_path,
                    payload=request_payload,
                    headers=request_headers,
                    timeout_sec=float(settings.request_timeout_sec),
                )
                break
            except RequestException as exc:
                if first_error is None:
                    first_error = exc
                continue

        if upstream_response is None:
            exc = first_error if isinstance(first_error, RequestException) else RequestException("assistant upstream request failed")
            retry_base_url = ""
            try:
                retry_base_url = self._resolve_target_base_url(
                    settings,
                    ensure_managed_start=True,
                    force_refresh=True,
                )
            except Exception:
                retry_base_url = ""
            if retry_base_url and retry_base_url != base_url:
                retry_error = None
                for candidate_base_url in self._preferred_assistant_base_urls(retry_base_url):
                    try:
                        upstream_response = self._stream_request(
                            base_url=candidate_base_url,
                            path=self.assistant_path,
                            payload=request_payload,
                            headers=request_headers,
                            timeout_sec=float(settings.request_timeout_sec),
                        )
                        break
                    except RequestException as retry_exc:
                        retry_error = retry_exc
                        continue
                if upstream_response is None:
                    return _error_response(
                        status_code=502,
                        detail=f"Module2 assistant upstream connection error: {exc}; retry: {retry_error}",
                    )
            else:
                return _error_response(status_code=502, detail=f"Module2 assistant upstream connection error: {exc}")

        if int(upstream_response.status_code or 0) >= 400:
            try:
                response_body = upstream_response.content
            finally:
                upstream_response.close()
            response = Response(
                content=response_body,
                status_code=int(upstream_response.status_code),
                media_type=str(upstream_response.headers.get("Content-Type") or "").strip() or None,
            )
            _copy_response_headers(response, upstream_response.headers)
            return response

        content_type = str(upstream_response.headers.get("Content-Type") or "").lower()
        if "text/event-stream" not in content_type:
            try:
                response_body = upstream_response.content
            finally:
                upstream_response.close()
            response = Response(
                content=response_body,
                status_code=int(upstream_response.status_code or 200),
                media_type=str(upstream_response.headers.get("Content-Type") or "").strip() or None,
            )
            _copy_response_headers(response, upstream_response.headers)
            return response

        response = StreamingResponse(
            _stream_upstream_body(upstream_response, _SSE_PROXY_CHUNK_SIZE),
            status_code=int(upstream_response.status_code or 200),
            media_type="text/event-stream",
        )
        _copy_response_headers(response, upstream_response.headers)
        return response

    def fetch_session_response(
        self,
        settings: Settings,
        *,
        request: Request,
        session_id: str,
        limit: int = 40,
        additional_headers: dict[str, str] | None = None,
    ) -> Response:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return _error_response(status_code=400, detail="session_id is required")

        try:
            base_url = self._resolve_target_base_url(
                settings,
                ensure_managed_start=False,
                force_refresh=False,
            )
        except Exception as exc:
            return _error_response(status_code=502, detail=f"Module2 assistant upstream unavailable: {type(exc).__name__}: {exc}")

        if not str(base_url or "").strip():
            return _error_response(status_code=502, detail="Module2 assistant upstream is not configured")

        request_headers = forward_module2_context_headers(request, additional_headers=additional_headers)
        request_headers["Accept"] = "application/json"
        request_path = self.session_path_template.format(session_id=quote(normalized_session_id, safe=""))

        upstream_response = None
        first_error = None
        for candidate_base_url in self._preferred_assistant_base_urls(base_url):
            try:
                upstream_response = self._json_request(
                    base_url=candidate_base_url,
                    path=request_path,
                    params={"limit": max(1, min(200, int(limit or 40)))},
                    headers=request_headers,
                    timeout_sec=float(settings.request_timeout_sec),
                )
                break
            except RequestException as exc:
                if first_error is None:
                    first_error = exc
                continue

        if upstream_response is None:
            exc = first_error if isinstance(first_error, RequestException) else RequestException("assistant session upstream request failed")
            retry_base_url = ""
            try:
                retry_base_url = self._resolve_target_base_url(
                    settings,
                    ensure_managed_start=False,
                    force_refresh=True,
                )
            except Exception:
                retry_base_url = ""
            if retry_base_url and retry_base_url != base_url:
                retry_error = None
                for candidate_base_url in self._preferred_assistant_base_urls(retry_base_url):
                    try:
                        upstream_response = self._json_request(
                            base_url=candidate_base_url,
                            path=request_path,
                            params={"limit": max(1, min(200, int(limit or 40)))},
                            headers=request_headers,
                            timeout_sec=float(settings.request_timeout_sec),
                        )
                        break
                    except RequestException as retry_exc:
                        retry_error = retry_exc
                        continue
                if upstream_response is None:
                    return _error_response(
                        status_code=502,
                        detail=f"Module2 assistant session upstream connection error: {exc}; retry: {retry_error}",
                    )
            else:
                return _error_response(status_code=502, detail=f"Module2 assistant session upstream connection error: {exc}")

        try:
            response_body = upstream_response.content
        finally:
            upstream_response.close()

        response = Response(
            content=response_body,
            status_code=int(upstream_response.status_code or 200),
            media_type=str(upstream_response.headers.get("Content-Type") or "").strip() or "application/json",
        )
        _copy_response_headers(response, upstream_response.headers)
        return response
