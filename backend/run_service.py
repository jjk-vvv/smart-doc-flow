from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
GATEWAY_ROOT = BACKEND_ROOT / "gateway"
MODULE2_ROOT = BACKEND_ROOT / "module2"
MODULE4_ROOT = BACKEND_ROOT / "module4"
REEXEC_MARKER = "SMART_DOC_FLOW_BACKEND_RUN_SERVICE_REEXEC"
DEFAULT_DATA_ROOT = REPO_ROOT / "runtime-data"


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _resolve_python(service: str) -> Path:
    candidates: list[Path] = []
    if service == "module4":
        candidates.extend(
            [
                _venv_python(REPO_ROOT / ".venv-module4-py311"),
                _venv_python(REPO_ROOT / ".venv"),
            ]
        )
    else:
        candidates.extend(
            [
                _venv_python(REPO_ROOT / ".venv-module2-py311"),
                _venv_python(MODULE2_ROOT / ".venv"),
                _venv_python(REPO_ROOT / ".venv"),
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return Path(sys.executable).resolve()


def _maybe_reexec(service: str) -> int | None:
    if os.environ.get(REEXEC_MARKER) == "1":
        return None

    target_python = _resolve_python(service)
    current_python = Path(sys.executable).resolve()
    if target_python == current_python:
        return None

    env = os.environ.copy()
    env[REEXEC_MARKER] = "1"
    completed = subprocess.run(
        [str(target_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
    )
    return int(completed.returncode)


def _reload_args(enabled: bool) -> list[str]:
    if not enabled:
        return []
    return ["--reload", "--reload-dir", "app"]


def _service_runtime(service: str) -> tuple[Path, str, str]:
    env = os.environ
    if service in {"backend", "gateway"}:
        gateway_runtime_root = GATEWAY_ROOT if (GATEWAY_ROOT / "app" / "main.py").exists() else BACKEND_ROOT
        return (
            gateway_runtime_root,
            str(env.get("GATEWAY_HOST") or "0.0.0.0").strip() or "0.0.0.0",
            str(env.get("GATEWAY_PORT") or "3001").strip() or "3001",
        )
    if service == "module2":
        return (
            MODULE2_ROOT,
            str(env.get("MODULE2_HOST") or "0.0.0.0").strip() or "0.0.0.0",
            str(env.get("MODULE2_PORT") or "8000").strip() or "8000",
        )
    return (
        MODULE4_ROOT,
        str(env.get("MODULE4_HOST") or "0.0.0.0").strip() or "0.0.0.0",
        str(env.get("MODULE4_PORT") or "8100").strip() or "8100",
    )


def _build_env(service: str) -> dict[str, str]:
    env = os.environ.copy()
    runtime_root = Path(str(env.get("SMART_DOC_FLOW_RUNTIME_ROOT") or REPO_ROOT)).resolve()
    config_root = Path(str(env.get("SMART_DOC_FLOW_CONFIG_ROOT") or runtime_root)).resolve()
    data_root = Path(str(env.get("SMART_DOC_FLOW_DATA_ROOT") or DEFAULT_DATA_ROOT)).resolve()

    env.setdefault("SMART_DOC_FLOW_RUNTIME_ROOT", str(runtime_root))
    env.setdefault("SMART_DOC_FLOW_CONFIG_ROOT", str(config_root))
    env.setdefault("SMART_DOC_FLOW_DATA_ROOT", str(data_root))
    env.setdefault("SMART_DOC_FLOW_GATEWAY_ENV_FILE", str((config_root / "backend" / ".env").resolve()))
    env.setdefault("MODULE2_ENV_FILE", str((config_root / "backend" / "module2" / ".env").resolve()))
    env.setdefault(
        "SMART_DOC_FLOW_MODULE4_ENV_FILE",
        str((config_root / "backend" / "module4" / ".env").resolve()),
    )
    env.setdefault("GATEWAY_FRONTEND_DIST_DIR", str((runtime_root / "frontend" / "dist").resolve()))
    env.setdefault("AUTH_USERS_FILE", str((data_root / "auth" / "users.json").resolve()))
    env.setdefault("MODULE2_ARTIFACT_ROOT_DIR", str((data_root / "module2" / "artifacts").resolve()))
    env.setdefault("MODULE2_MINERU_CACHE_DIR", str((data_root / "module2" / "cache" / "mineru").resolve()))
    env.setdefault("MODULE2_GEMINI_CACHE_DIR", str((data_root / "module2" / "cache" / "gemini").resolve()))
    env.setdefault("MODULE2_MINERU_WORK_ROOT_DIR", str((data_root / "module2" / "work" / "mineru").resolve()))
    env.setdefault(
        "MODULE2_EXTRACT_JOB_STATE_DIR",
        str((data_root / "module2" / "runlogs" / "extraction_jobs").resolve()),
    )
    env.setdefault(
        "MODULE2_LLM_DEBUG_DIR",
        str((data_root / "module2" / "runlogs" / "module2-llm-debug").resolve()),
    )
    bundled_runtime_models = (runtime_root / "backend" / "module2" / ".cache" / "mineru_runtime_models").resolve()
    env.setdefault(
        "MODULE2_MINERU_RUNTIME_MODELS_DIR",
        str(
            bundled_runtime_models
            if bundled_runtime_models.exists()
            else (data_root / "module2" / "cache" / "mineru_runtime_models").resolve()
        ),
    )
    env.setdefault(
        "MODULE4_GRAPHRAG_WORKSPACES_ROOT",
        str((data_root / "module4" / "workspaces").resolve()),
    )
    env.setdefault(
        "MODULE4_GRAPHRAG_PROMPTS_ROOT",
        str((runtime_root / "backend" / "module4" / "assets" / "prompts").resolve()),
    )

    if service in {"backend", "gateway"}:
        module2_port = str(env.get("MODULE2_PORT") or "8000").strip() or "8000"
        module4_port = str(env.get("MODULE4_PORT") or "8100").strip() or "8100"
        # Default to auto mode to avoid blocking gateway startup when sidecars are
        # already running externally (or temporarily unavailable during boot).
        env.setdefault("UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE", "auto")
        env.setdefault("UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE", "auto")
        env.setdefault("MODULE2_UPSTREAM_URL", f"http://127.0.0.1:{module2_port}")
        env.setdefault("MODULE4_UPSTREAM_URL", f"http://127.0.0.1:{module4_port}")
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Smart Doc Flow FastAPI services without Node.js backend wrappers.")
    parser.add_argument("service", choices=("backend", "gateway", "module2", "module4"))
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload mode.")
    args = parser.parse_args()

    reexec_code = _maybe_reexec(args.service)
    if reexec_code is not None:
        return reexec_code

    service_root, host, port = _service_runtime(args.service)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        port,
        *_reload_args(args.reload),
    ]

    print(f"[run_service] service={args.service}")
    print(f"[run_service] python={sys.executable}")
    print(f"[run_service] cwd={service_root}")
    print(f"[run_service] command={' '.join(command)}")

    completed = subprocess.run(
        command,
        cwd=str(service_root),
        env=_build_env(args.service),
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
