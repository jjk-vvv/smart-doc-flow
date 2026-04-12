from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE2_ROOT = REPO_ROOT / "backend" / "module2"
E2E_SCRIPT = REPO_ROOT / "frontend" / "e2e" / "module2_assistant_streaming_playwright.mjs"
HOST = os.getenv("MODULE2_FRONTEND_CHECK_HOST", "127.0.0.1")
PORT = int(os.getenv("MODULE2_FRONTEND_CHECK_PORT", "8001"))


def wait_healthz(url: str, timeout_sec: float = 60.0) -> None:
    started_at = time.time()
    last_error = ""
    while time.time() - started_at < timeout_sec:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - best effort bootstrap
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"temp server health check failed: {last_error or 'timeout'}")


def main() -> int:
    os.chdir(MODULE2_ROOT)
    sys.path.insert(0, str(MODULE2_ROOT))

    from app.composition.application import app

    config = uvicorn.Config(app=app, host=HOST, port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        wait_healthz(f"http://{HOST}:{PORT}/healthz")
        env = os.environ.copy()
        env.setdefault("MODULE2_API_BASE_OVERRIDE", f"http://{HOST}:{PORT}")
        completed = subprocess.run(
            ["node", str(E2E_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=1800,
        )
        if completed.stdout:
            print(completed.stdout)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        return int(completed.returncode)
    finally:
        server.should_exit = True
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
