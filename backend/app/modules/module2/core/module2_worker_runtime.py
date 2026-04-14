from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.modules.module2.schemas.extraction import CacheClearResponse

from .config import ExtractionSettings, get_extraction_settings


class Module2WorkerError(RuntimeError):
    pass


class Module2WorkerRuntime:
    def __init__(self, extraction_settings: ExtractionSettings | None = None) -> None:
        self.extraction_settings = extraction_settings or get_extraction_settings()

    async def extract_batch_subprocess(
        self,
        settings: Settings,
        *,
        request_headers: dict[str, str],
        files_payload: list[tuple[str, tuple[str, bytes, str]]],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        with self.temp_dir(settings, prefix="module2-batch-") as temp_dir:
            temp_root = Path(temp_dir)
            request_path = temp_root / "request.json"
            response_path = temp_root / "response.json"
            serialized_files: list[dict[str, str]] = []
            for index, item in enumerate(files_payload):
                _, (file_name, file_bytes, content_type) = item
                file_path = temp_root / f"input_{index}_{Path(file_name).name or 'file.bin'}"
                file_path.write_bytes(file_bytes)
                serialized_files.append(
                    {
                        "file_name": str(file_name or f"file_{index}"),
                        "content_type": str(content_type or "application/octet-stream"),
                        "path": str(file_path),
                    }
                )
            request_payload = {
                "headers": dict(request_headers or {}),
                "schema_form": str(schema_form or "").strip(),
                "tenant_id": str(tenant_id or "").strip(),
                "files": serialized_files,
            }
            request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            worker_payload = await self.run_worker_command(
                settings,
                command="extract-batch",
                request_path=request_path,
                response_path=response_path,
            )
            result = worker_payload.get("result")
            if not isinstance(result, dict):
                raise Module2WorkerError("module2 worker returned an invalid batch payload")
            return result

    async def clear_cache_subprocess(
        self,
        settings: Settings,
        *,
        scope: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        with self.temp_dir(settings, prefix="module2-cache-clear-") as temp_dir:
            temp_root = Path(temp_dir)
            request_path = temp_root / "request.json"
            response_path = temp_root / "response.json"
            request_path.write_text(
                json.dumps(
                    {
                        "scope": str(scope or "").strip(),
                        "tenant_id": str(tenant_id or "").strip(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            worker_payload = await self.run_worker_command(
                settings,
                command="clear-cache",
                request_path=request_path,
                response_path=response_path,
            )
            result = worker_payload.get("result")
            if not isinstance(result, dict):
                raise Module2WorkerError("module2 worker returned an invalid cache clear payload")
            return CacheClearResponse.model_validate(result).model_dump(mode="json")

    async def run_worker_command(
        self,
        settings: Settings,
        *,
        command: str,
        request_path: Path,
        response_path: Path,
    ) -> dict[str, Any]:
        worker_script = self.worker_script_path(settings)
        if not worker_script.exists() or not worker_script.is_file():
            raise Module2WorkerError(f"module2 worker script not found: {worker_script}")

        python_executable = self.worker_python_executable()
        timeout_sec = max(5.0, float(self.extraction_settings.module2_worker_timeout_sec))

        def _run() -> subprocess.CompletedProcess[str]:
            env = os.environ.copy()
            return subprocess.run(
                [python_executable, str(worker_script), command, str(request_path), str(response_path)],
                cwd=str(worker_script.parent),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_sec,
                check=False,
            )

        completed = await asyncio.to_thread(_run)
        response_payload = self.read_worker_response(response_path)
        if completed.returncode != 0:
            error_detail = str(response_payload.get("error") or completed.stderr or completed.stdout).strip()
            raise Module2WorkerError(
                f"module2 worker command failed ({command}) rc={completed.returncode}: {error_detail}"
            )
        if not bool(response_payload.get("ok")):
            raise Module2WorkerError(
                f"module2 worker command failed ({command}): {response_payload.get('error') or 'unknown error'}"
            )
        return response_payload

    def worker_python_executable(self) -> str:
        configured = str(self.extraction_settings.module2_worker_python or "").strip()
        return configured or sys.executable

    @staticmethod
    def worker_script_path(settings: Settings) -> Path:
        return (
            settings.runtime_root_dir / "backend" / "app" / "modules" / "module2" / "core" / "module2_compat_worker.py"
        ).resolve()

    @staticmethod
    def temp_dir(settings: Settings, *, prefix: str):
        temp_root = (settings.data_root_dir / "tmp" / "module2_compat").resolve()
        temp_root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix=prefix, dir=str(temp_root))

    @staticmethod
    def read_worker_response(response_path: Path) -> dict[str, Any]:
        if not response_path.exists() or not response_path.is_file():
            return {}
        try:
            payload = json.loads(response_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}
