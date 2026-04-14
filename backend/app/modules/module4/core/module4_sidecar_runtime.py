from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.health import probe_json

_RESOLVE_CACHE_TTL_SEC = 20.0
_module4_upstream_lock = threading.RLock()
_module4_upstream_cached_url = ""
_module4_upstream_checked_at = 0.0
_MODULE4_HEALTH_PROBE_TIMEOUT_CAP_SEC = 2.0


def _env_str(name: str, default: str = "") -> str:
    value = str(os.getenv(name, default) or "").strip()
    return value or default


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _bounded_probe_timeout(timeout_sec: float, *, cap_sec: float = _MODULE4_HEALTH_PROBE_TIMEOUT_CAP_SEC) -> float:
    return max(1.0, min(float(timeout_sec or cap_sec), float(cap_sec)))


@dataclass(frozen=True)
class Module4SidecarSettings:
    module4_port_hint: str
    module4_sidecar_mode: str
    module4_sidecar_python: str
    module4_sidecar_startup_timeout_sec: float

    @classmethod
    def from_env(cls) -> "Module4SidecarSettings":
        module4_sidecar_mode = _env_str("UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE", "auto").lower()
        if module4_sidecar_mode not in {"disabled", "auto", "managed"}:
            module4_sidecar_mode = "auto"
        return cls(
            module4_port_hint=_env_str("MODULE4_PORT", ""),
            module4_sidecar_mode=module4_sidecar_mode,
            module4_sidecar_python=_env_str("UNIFIED_GATEWAY_MODULE4_SIDECAR_PYTHON", ""),
            module4_sidecar_startup_timeout_sec=max(
                10.0,
                _env_float("UNIFIED_GATEWAY_MODULE4_SIDECAR_STARTUP_TIMEOUT_SEC", 90.0),
            ),
        )


@dataclass
class Module4ManagedProcessState:
    base_url: str = ""
    pid: int | None = None
    started_at: float = 0.0
    last_checked_at: float = 0.0
    last_error: str = ""
    log_file: str = ""
    started_by_manager: bool = False


class Module4SidecarError(RuntimeError):
    pass


def clear_module4_upstream_resolution_cache() -> None:
    global _module4_upstream_cached_url, _module4_upstream_checked_at
    with _module4_upstream_lock:
        _module4_upstream_cached_url = ""
        _module4_upstream_checked_at = 0.0


def _set_cached_module4_upstream_url(base_url: str) -> None:
    global _module4_upstream_cached_url, _module4_upstream_checked_at
    with _module4_upstream_lock:
        _module4_upstream_cached_url = str(base_url or "").strip().rstrip("/")
        _module4_upstream_checked_at = time.time()


def module4_upstream_candidates(settings: Settings) -> list[str]:
    configured = str(settings.module4_upstream_url or "").strip() or "http://127.0.0.1:8100"
    candidates: list[str] = [configured]
    env_port = get_module4_sidecar_settings().module4_port_hint
    if env_port:
        candidates.append(f"http://127.0.0.1:{env_port}")

    local_fallbacks = ("http://127.0.0.1:8100", "http://127.0.0.1:8110")
    if configured.startswith("http://127.0.0.1:") or configured.startswith("http://localhost:"):
        candidates.extend(local_fallbacks)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = str(item or "").strip().rstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def probe_module4_upstream(base_url: str, timeout_sec: float) -> dict[str, Any]:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    health_url = f"{normalized_base_url}/module4/healthz"
    result = probe_json(health_url, _bounded_probe_timeout(timeout_sec))
    result["base_url"] = normalized_base_url
    result["health_url"] = health_url
    result["checked_at"] = time.time()
    return result


def resolve_live_module4_upstream_url(
    settings: Settings,
    *,
    force_refresh: bool = False,
    ensure_sidecar: bool = False,
) -> str:
    global _module4_upstream_cached_url, _module4_upstream_checked_at

    if ensure_sidecar:
        try:
            base_url = get_module4_sidecar_manager().ensure_ready(settings)
        except Module4SidecarError:
            base_url = ""
        if base_url:
            _set_cached_module4_upstream_url(base_url)
            return base_url

    now_ts = time.time()
    with _module4_upstream_lock:
        if (
            not force_refresh
            and _module4_upstream_cached_url
            and (now_ts - float(_module4_upstream_checked_at or 0.0)) < _RESOLVE_CACHE_TTL_SEC
        ):
            return _module4_upstream_cached_url

    chosen = str(settings.module4_upstream_url or "").strip().rstrip("/")
    for candidate in module4_upstream_candidates(settings):
        result = probe_module4_upstream(candidate, settings.request_timeout_sec)
        if bool(result.get("ok")):
            chosen = str(result.get("base_url") or candidate).rstrip("/")
            break

    with _module4_upstream_lock:
        _module4_upstream_cached_url = chosen
        _module4_upstream_checked_at = now_ts
    return chosen


class Module4SidecarManager:
    def __init__(self, sidecar_settings: Module4SidecarSettings | None = None) -> None:
        self.sidecar_settings = sidecar_settings or get_module4_sidecar_settings()
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._log_handle: TextIO | None = None
        self._state = Module4ManagedProcessState()

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        preferred_base_url = self._preferred_base_url(settings)
        manageable_target = self._manageable_target(preferred_base_url)
        probe_timeout_sec = _bounded_probe_timeout(
            getattr(settings, "gateway_health_probe_timeout_sec", settings.request_timeout_sec)
        )
        probe_payload = (
            self._probe_base_url(preferred_base_url, probe_timeout_sec)
            if preferred_base_url and manageable_target
            else {}
        )
        with self._lock:
            self._reap_dead_process_locked()
            state = Module4ManagedProcessState(**self._state.__dict__)
            running = self._process is not None and self._process.poll() is None

        requested_mode = self.sidecar_settings.module4_sidecar_mode
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
            "startup_timeout_sec": float(self.sidecar_settings.module4_sidecar_startup_timeout_sec),
            "python": self._resolve_python_executable(settings),
            "module4_root": str(self._module4_root(settings)),
            "log_file": state.log_file,
            "last_start_at": float(state.started_at or 0.0),
            "last_checked_at": float(max(state.last_checked_at or 0.0, probe_payload.get("checked_at", 0.0) or 0.0)),
            "last_error": state.last_error or str(probe_payload.get("error") or ""),
            "probe": probe_payload,
        }

    def ensure_ready(self, settings: Settings) -> str:
        requested_mode = self.sidecar_settings.module4_sidecar_mode
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
            timeout_sec=self.sidecar_settings.module4_sidecar_startup_timeout_sec,
        )
        if bool(ready_payload.get("ok")):
            return preferred_base_url

        error_message = str(ready_payload.get("error") or "module4 sidecar failed to become healthy").strip()
        with self._lock:
            self._state.last_error = error_message
            self._terminate_process_locked(wait_timeout_sec=2.0)
        if requested_mode == "managed":
            raise Module4SidecarError(error_message)
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
                        "error": f"module4 sidecar exited before healthy, rc={process.returncode}",
                    }
            time.sleep(0.5)
        return {
            "ok": False,
            "base_url": preferred_base_url,
            "checked_at": time.time(),
            "error": f"module4 sidecar health timeout after {float(timeout_sec):.1f}s",
        }

    def _start_process_locked(self, settings: Settings, host: str, port: int, base_url: str) -> None:
        module4_root = self._module4_root(settings)
        module4_entry = module4_root / "main.py"
        if not module4_root.exists() or not module4_entry.exists():
            raise Module4SidecarError(f"module4 source not found under {module4_root}")

        python_executable = self._resolve_python_executable(settings)
        log_path = self._sidecar_log_path(settings, port=port)
        backend_root = (settings.runtime_root_dir / "backend").resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "a", encoding="utf-8")
        env = os.environ.copy()
        env["MODULE4_PORT"] = str(port)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process = subprocess.Popen(
            [python_executable, "-m", "uvicorn", "app.modules.module4.main:app", "--host", host, "--port", str(port)],
            cwd=str(backend_root),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        self._close_log_handle_locked()
        self._log_handle = log_handle
        self._process = process
        self._state = Module4ManagedProcessState(
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
            self._state.last_error = f"module4 sidecar exited, rc={return_code}"
        self._state.started_by_manager = False

    @staticmethod
    def _preferred_base_url(settings: Settings) -> str:
        return str(settings.module4_upstream_url or "").strip().rstrip("/")

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
        return probe_module4_upstream(base_url, timeout_sec)

    def _resolve_python_executable(self, settings: Settings) -> str:
        configured = str(self.sidecar_settings.module4_sidecar_python or "").strip()
        if configured:
            return configured

        candidates = [
            settings.runtime_root_dir / ".venv-module4-py311" / "Scripts" / "python.exe",
            settings.runtime_root_dir / ".venv-module4-py311" / "bin" / "python",
            settings.runtime_root_dir / ".venv" / "Scripts" / "python.exe",
            settings.runtime_root_dir / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return sys.executable

    @staticmethod
    def _module4_root(settings: Settings) -> Path:
        return (settings.runtime_root_dir / "backend" / "app" / "modules" / "module4").resolve()

    @staticmethod
    def _sidecar_log_path(settings: Settings, *, port: int) -> Path:
        return (
            settings.data_root_dir
            / "module4"
            / "runlogs"
            / "sidecar"
            / f"module4-sidecar-{int(port)}.log"
        ).resolve()


@lru_cache(maxsize=1)
def get_module4_sidecar_settings() -> Module4SidecarSettings:
    return Module4SidecarSettings.from_env()


@lru_cache(maxsize=1)
def get_module4_sidecar_manager() -> Module4SidecarManager:
    return Module4SidecarManager()
