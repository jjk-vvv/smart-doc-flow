from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping


def probe_json(url: str, timeout_sec: float, *, headers: Mapping[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url=url, method="GET", headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read()
            status_code = int(getattr(response, "status", 0))
            payload: dict[str, Any] | None = None
            if body:
                try:
                    decoded = json.loads(body.decode("utf-8"))
                    if isinstance(decoded, dict):
                        payload = decoded
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = None
            return {
                "ok": 200 <= status_code < 300,
                "url": url,
                "status_code": status_code,
                "payload": payload or {},
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "url": url,
            "status_code": int(getattr(exc, "code", 0) or 0),
            "payload": {},
            "error": str(exc.reason or exc),
        }
    except Exception as exc:  # pragma: no cover - defensive runtime probe
        return {
            "ok": False,
            "url": url,
            "status_code": 0,
            "payload": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def probe_path(path: Path) -> dict[str, Any]:
    index_file = path / "index.html"
    exists = path.exists()
    is_dir = exists and path.is_dir()
    index_exists = index_file.exists()
    return {
        "ok": is_dir and index_exists,
        "path": str(path),
        "exists": exists,
        "is_dir": is_dir,
        "index_exists": index_exists,
    }
