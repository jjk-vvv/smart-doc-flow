from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
import ipaddress
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urljoin, urlparse

from fastapi import HTTPException
import requests
from requests import RequestException, Response

from app.core.config import Settings

from .config import ExtractionSettings, get_extraction_settings


_RESOLVE_CACHE_TTL_SEC = 20.0
_module2_upstream_lock = threading.RLock()
_module2_upstream_cached_url = ""
_module2_upstream_checked_at = 0.0


class Module2SidecarError(RuntimeError):
    pass


def clear_module2_upstream_resolution_cache() -> None:
    global _module2_upstream_cached_url, _module2_upstream_checked_at
    with _module2_upstream_lock:
        _module2_upstream_cached_url = ""
        _module2_upstream_checked_at = 0.0


def _set_cached_module2_upstream_url(base_url: str) -> None:
    global _module2_upstream_cached_url, _module2_upstream_checked_at
    with _module2_upstream_lock:
        _module2_upstream_cached_url = str(base_url or "").strip().rstrip("/")
        _module2_upstream_checked_at = time.time()


def _is_loopback_upstream(base_url: str) -> bool:
    parsed = urlparse(str(base_url or "").strip())
    host = str(parsed.hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost"}


def _candidate_port_from_base_url(base_url: str, default_port: str = "8010") -> str:
    parsed = urlparse(str(base_url or "").strip())
    if parsed.port:
        return str(parsed.port)
    if parsed.scheme == "https":
        return "443"
    if parsed.scheme == "http":
        return "80"
    return str(default_port or "8010").strip() or "8010"


def _preferred_local_host_aliases() -> list[str]:
    aliases: list[str] = []
    hostname = str(socket.gethostname() or "").strip()
    if hostname and hostname.lower() not in {"localhost"}:
        aliases.append(hostname)

    ip_candidates: list[str] = []
    try:
        _, _, host_ips = socket.gethostbyname_ex(hostname or "localhost")
        ip_candidates.extend(host_ips)
    except Exception:
        pass

    try:
        for info in socket.getaddrinfo(hostname or "localhost", None, family=socket.AF_INET, type=socket.SOCK_STREAM):
            sockaddr = info[4] if len(info) >= 5 else None
            if isinstance(sockaddr, tuple) and sockaddr:
                ip_candidates.append(str(sockaddr[0] or "").strip())
    except Exception:
        pass

    deduped_ips: list[str] = []
    seen_ips: set[str] = set()
    for raw_ip in ip_candidates:
        ip = str(raw_ip or "").strip()
        if not ip or ip in seen_ips:
            continue
        try:
            parsed_ip = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if parsed_ip in ipaddress.ip_network("198.18.0.0/15"):
            continue
        if (
            parsed_ip.is_loopback
            or parsed_ip.is_link_local
            or parsed_ip.is_multicast
            or parsed_ip.is_unspecified
            or parsed_ip.is_reserved
        ):
            continue
        seen_ips.add(ip)
        deduped_ips.append(ip)

    return aliases + deduped_ips


def _local_alias_base_urls(*, scheme: str, port: str) -> list[str]:
    normalized_scheme = str(scheme or "http").strip() or "http"
    normalized_port = str(port or "").strip()
    if not normalized_port:
        return []
    ip_hosts: list[str] = []
    named_hosts: list[str] = []
    for host in _preferred_local_host_aliases():
        normalized_host = str(host or "").strip()
        if not normalized_host:
            continue
        try:
            ipaddress.ip_address(normalized_host)
        except ValueError:
            named_hosts.append(normalized_host)
        else:
            ip_hosts.append(normalized_host)
    ordered_hosts = ip_hosts + named_hosts
    return [f"{normalized_scheme}://{host}:{normalized_port}" for host in ordered_hosts]


def module2_upstream_candidates(settings: Settings) -> list[str]:
    configured = str(settings.module2_upstream_url or "").strip() or "http://127.0.0.1:8010"
    candidates: list[str] = [configured]
    env_port = get_extraction_settings().module2_port_hint
    if env_port:
        candidates.append(f"http://127.0.0.1:{env_port}")

    # Keep 8010 as canonical module2 local port while preserving 8000 fallback
    # compatibility for old local dev environments.
    local_fallbacks = ("http://127.0.0.1:8010", "http://127.0.0.1:8000")
    if _is_loopback_upstream(configured):
        parsed = urlparse(configured)
        scheme = str(parsed.scheme or "http").strip() or "http"
        configured_port = _candidate_port_from_base_url(configured, env_port or "8010")
        alias_ports = [configured_port]
        if env_port and env_port not in alias_ports:
            alias_ports.append(env_port)
        for fallback in local_fallbacks:
            fallback_port = _candidate_port_from_base_url(fallback, "8010")
            if fallback_port not in alias_ports:
                alias_ports.append(fallback_port)
        alias_candidates: list[str] = []
        for port in alias_ports:
            alias_candidates.extend(_local_alias_base_urls(scheme=scheme, port=port))
        # Keep configured/explicit loopback endpoints first to avoid paying alias probe
        # timeouts on every request when local upstream is already reachable.
        candidates = candidates + alias_candidates + list(local_fallbacks)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = str(item or "").strip().rstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _probe_upstream_base_url(base_url: str, timeout_sec: float) -> dict[str, Any]:
    checked_at = time.time()
    health_url = f"{str(base_url or '').rstrip('/')}/healthz"
    try:
        response = requests.get(health_url, timeout=max(1.0, min(5.0, float(timeout_sec))))
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "base_url": str(base_url or "").rstrip("/"),
            "health_url": health_url,
            "checked_at": checked_at,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "ok": True,
        "base_url": str(base_url or "").rstrip("/"),
        "health_url": health_url,
        "checked_at": checked_at,
        "payload": payload if isinstance(payload, dict) else {},
    }


def probe_module2_upstream(base_url: str, timeout_sec: float) -> dict[str, object]:
    return _probe_upstream_base_url(base_url, timeout_sec)


def resolve_live_module2_upstream_url(settings: Settings, *, force_refresh: bool = False) -> str:
    global _module2_upstream_cached_url, _module2_upstream_checked_at

    configured_url = str(settings.module2_upstream_url or "").strip().rstrip("/")
    with _module2_upstream_lock:
        cached_url = str(_module2_upstream_cached_url or "").strip().rstrip("/")
    if not force_refresh and cached_url:
        # Fast path: if we already discovered a reachable upstream, reuse it directly.
        # Runtime callers can trigger force_refresh=True when a connection attempt fails.
        #
        # Special case: when configured upstream is local loopback and cached URL is a
        # non-loopback alias, prefer loopback again once it becomes healthy. This keeps
        # request latency stable under environments where alias routing is slower.
        if configured_url and _is_loopback_upstream(configured_url) and not _is_loopback_upstream(cached_url):
            configured_probe = probe_module2_upstream(configured_url, min(float(settings.request_timeout_sec), 1.0))
            if bool(configured_probe.get("ok")):
                preferred_url = str(configured_probe.get("base_url") or configured_url).strip().rstrip("/")
                with _module2_upstream_lock:
                    _module2_upstream_cached_url = preferred_url
                    _module2_upstream_checked_at = time.time()
                return preferred_url
        return cached_url

    chosen = configured_url
    for candidate in module2_upstream_candidates(settings):
        result = probe_module2_upstream(candidate, settings.request_timeout_sec)
        if bool(result.get("ok")):
            chosen = str(result.get("base_url") or candidate).rstrip("/")
            break

    with _module2_upstream_lock:
        _module2_upstream_cached_url = chosen
        _module2_upstream_checked_at = time.time()
    return chosen


def request_module2(
    settings: Settings,
    *,
    method: str,
    path: str,
    params: dict[str, object] | None = None,
    data: dict[str, object] | None = None,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    json_payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    timeout_sec: float | None = None,
    ensure_sidecar: bool = False,
) -> Response:
    base_url = ""
    if ensure_sidecar:
        try:
            base_url = get_module2_sidecar_manager().ensure_ready(settings)
        except Module2SidecarError as exc:
            raise RequestException(str(exc)) from exc
        if base_url:
            _set_cached_module2_upstream_url(base_url)
    if not base_url:
        base_url = resolve_live_module2_upstream_url(settings, force_refresh=ensure_sidecar)

    request_url = urljoin(f"{base_url.rstrip('/')}/", str(path or "").lstrip("/"))
    return requests.request(
        method=str(method or "GET").upper(),
        url=request_url,
        params=params or None,
        data=data or None,
        files=files or None,
        json=json_payload,
        headers=headers or None,
        timeout=max(1.0, float(timeout_sec or settings.request_timeout_sec)),
    )


def parse_upstream_json_response(response: Response, *, default_action: str) -> dict[str, Any]:
    if response.status_code >= 400:
        detail = _parse_upstream_error_detail(response, default_action)
        raise HTTPException(status_code=int(response.status_code), detail=detail)
    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Module2 upstream returned invalid JSON for {default_action}: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail=f"Module2 upstream returned an unexpected payload for {default_action}",
        )
    return payload


def _parse_upstream_error_detail(response: Response, default_action: str) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if detail is not None:
            return json.dumps(detail, ensure_ascii=False)
    text = str(response.text or "").strip()
    return text or f"Module2 upstream failed to {default_action}"


@dataclass
class Module2ManagedProcessState:
    base_url: str = ""
    pid: int | None = None
    started_at: float = 0.0
    last_checked_at: float = 0.0
    last_error: str = ""
    log_file: str = ""
    started_by_manager: bool = False


class Module2SidecarManager:
    def __init__(self, extraction_settings: ExtractionSettings | None = None) -> None:
        self.extraction_settings = extraction_settings or get_extraction_settings()
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._log_handle: TextIO | None = None
        self._state = Module2ManagedProcessState()

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        preferred_base_url = self._preferred_base_url(settings)
        manageable_target = self._manageable_target(preferred_base_url)
        probe_payload = (
            self._probe_base_url(preferred_base_url, settings.request_timeout_sec)
            if preferred_base_url and manageable_target
            else {}
        )
        with self._lock:
            self._reap_dead_process_locked()
            state = Module2ManagedProcessState(**self._state.__dict__)
            running = self._process is not None and self._process.poll() is None

        requested_mode = self.extraction_settings.module2_sidecar_mode
        if requested_mode == "disabled":
            active_mode = "disabled"
        elif not manageable_target:
            active_mode = "remote_upstream"
        elif bool(probe_payload.get("ok")) and state.started_by_manager:
            active_mode = "managed"
        elif bool(probe_payload.get("ok")):
            active_mode = "external"
        elif running:
            active_mode = "starting"
        elif state.last_error:
            active_mode = "error"
        else:
            active_mode = "idle"

        return {
            "requested_mode": requested_mode,
            "active_mode": active_mode,
            "manageable": bool(manageable_target),
            "preferred_base_url": preferred_base_url,
            "healthy": bool(probe_payload.get("ok")),
            "running": running,
            "pid": state.pid,
            "started_by_manager": state.started_by_manager,
            "startup_timeout_sec": float(self.extraction_settings.module2_sidecar_startup_timeout_sec),
            "python": self._resolve_python_executable(settings),
            "module2_root": str(self._module2_root(settings)),
            "log_file": state.log_file,
            "last_start_at": float(state.started_at or 0.0),
            "last_checked_at": float(max(state.last_checked_at or 0.0, probe_payload.get("checked_at", 0.0) or 0.0)),
            "last_error": state.last_error or str(probe_payload.get("error") or ""),
            "probe": probe_payload,
        }

    def ensure_ready(self, settings: Settings) -> str:
        requested_mode = self.extraction_settings.module2_sidecar_mode
        if requested_mode == "disabled":
            return ""

        preferred_base_url = self._preferred_base_url(settings)
        manageable_target = self._manageable_target(preferred_base_url)
        if manageable_target is None:
            return ""

        probe_payload = self._probe_base_url(preferred_base_url, settings.request_timeout_sec)
        if bool(probe_payload.get("ok")):
            with self._lock:
                self._state.base_url = preferred_base_url
                self._state.last_checked_at = float(probe_payload.get("checked_at", time.time()) or time.time())
                self._state.last_error = ""
            return preferred_base_url

        with self._lock:
            self._reap_dead_process_locked()
            second_probe = self._probe_base_url(preferred_base_url, settings.request_timeout_sec)
            if bool(second_probe.get("ok")):
                self._state.base_url = preferred_base_url
                self._state.last_checked_at = float(second_probe.get("checked_at", time.time()) or time.time())
                self._state.last_error = ""
                return preferred_base_url
            if self._process is None or self._process.poll() is not None:
                self._start_process_locked(settings, manageable_target["host"], manageable_target["port"], preferred_base_url)

        ready_payload = self._wait_for_healthy(
            settings,
            preferred_base_url=preferred_base_url,
            timeout_sec=self.extraction_settings.module2_sidecar_startup_timeout_sec,
        )
        if bool(ready_payload.get("ok")):
            return preferred_base_url

        error_message = str(ready_payload.get("error") or "module2 sidecar failed to become healthy").strip()
        with self._lock:
            self._state.last_error = error_message
            self._terminate_process_locked(wait_timeout_sec=2.0)
        if requested_mode == "managed":
            raise Module2SidecarError(error_message)
        return ""

    def shutdown_started_process(self, wait_timeout_sec: float = 8.0) -> None:
        with self._lock:
            self._terminate_process_locked(wait_timeout_sec=wait_timeout_sec)

    def _wait_for_healthy(
        self,
        settings: Settings,
        *,
        preferred_base_url: str,
        timeout_sec: float,
    ) -> dict[str, Any]:
        deadline = time.time() + max(1.0, float(timeout_sec))
        while time.time() < deadline:
            probe_payload = self._probe_base_url(preferred_base_url, settings.request_timeout_sec)
            if bool(probe_payload.get("ok")):
                with self._lock:
                    self._state.base_url = preferred_base_url
                    self._state.last_checked_at = float(probe_payload.get("checked_at", time.time()) or time.time())
                    self._state.last_error = ""
                return probe_payload
            with self._lock:
                process = self._process
                if process is not None and process.poll() is not None:
                    return {
                        "ok": False,
                        "base_url": preferred_base_url,
                        "checked_at": time.time(),
                        "error": f"module2 sidecar exited before healthy, rc={process.returncode}",
                    }
            time.sleep(0.5)
        return {
            "ok": False,
            "base_url": preferred_base_url,
            "checked_at": time.time(),
            "error": f"module2 sidecar health timeout after {float(timeout_sec):.1f}s",
        }

    def _start_process_locked(self, settings: Settings, host: str, port: int, base_url: str) -> None:
        module2_root = self._module2_root(settings)
        module2_entry = module2_root / "app" / "main.py"
        if not module2_root.exists() or not module2_entry.exists():
            raise Module2SidecarError(f"module2 source not found under {module2_root}")

        python_executable = self._resolve_python_executable(settings)
        log_path = self._sidecar_log_path(settings, port=port)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "a", encoding="utf-8")
        env = os.environ.copy()
        env["MODULE2_PORT"] = str(port)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            [python_executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(port)],
            cwd=str(module2_root),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        self._close_log_handle_locked()
        self._log_handle = log_handle
        self._process = process
        self._state = Module2ManagedProcessState(
            base_url=base_url,
            pid=int(process.pid),
            started_at=time.time(),
            last_checked_at=0.0,
            last_error="",
            log_file=str(log_path),
            started_by_manager=True,
        )

    def _terminate_process_locked(self, *, wait_timeout_sec: float) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=max(0.5, float(wait_timeout_sec)))
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass
        self._process = None
        self._close_log_handle_locked()
        self._state.pid = None
        self._state.started_by_manager = False

    def _close_log_handle_locked(self) -> None:
        if self._log_handle is None:
            return
        try:
            self._log_handle.flush()
        except Exception:
            pass
        try:
            self._log_handle.close()
        except Exception:
            pass
        self._log_handle = None

    def _reap_dead_process_locked(self) -> None:
        process = self._process
        if process is None:
            return
        return_code = process.poll()
        if return_code is None:
            return
        self._process = None
        self._close_log_handle_locked()
        self._state.pid = None
        if self._state.started_by_manager and not self._state.last_error:
            self._state.last_error = f"module2 sidecar exited, rc={return_code}"
        self._state.started_by_manager = False

    @staticmethod
    def _preferred_base_url(settings: Settings) -> str:
        return str(settings.module2_upstream_url or "").strip().rstrip("/")

    @staticmethod
    def _manageable_target(base_url: str) -> dict[str, Any] | None:
        parsed = urlparse(str(base_url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.path not in {"", "/"}:
            return None
        host = str(parsed.hostname or "").strip()
        if host not in {"127.0.0.1", "localhost"}:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        normalized = f"{parsed.scheme}://{host}:{port}"
        return {"host": host, "port": int(port), "base_url": normalized}

    @staticmethod
    def _probe_base_url(base_url: str, timeout_sec: float) -> dict[str, Any]:
        return _probe_upstream_base_url(base_url, timeout_sec)

    def _resolve_python_executable(self, settings: Settings) -> str:
        configured = str(self.extraction_settings.module2_sidecar_python or "").strip()
        if configured:
            return configured
        worker_python = str(self.extraction_settings.module2_worker_python or "").strip()
        if worker_python:
            return worker_python

        candidates = [
            settings.runtime_root_dir / ".venv-module2-py311" / "Scripts" / "python.exe",
            settings.runtime_root_dir / ".venv-module2-py311" / "bin" / "python",
            self._module2_root(settings) / ".venv-module2-py311" / "Scripts" / "python.exe",
            self._module2_root(settings) / ".venv-module2-py311" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return sys.executable

    @staticmethod
    def _module2_root(settings: Settings) -> Path:
        return (settings.runtime_root_dir / "backend" / "module2").resolve()

    @staticmethod
    def _sidecar_log_path(settings: Settings, *, port: int) -> Path:
        return (
            settings.data_root_dir
            / "module2"
            / "runlogs"
            / "sidecar"
            / f"module2-sidecar-{int(port)}.log"
        ).resolve()


@lru_cache(maxsize=1)
def get_module2_sidecar_manager() -> Module2SidecarManager:
    return Module2SidecarManager()
