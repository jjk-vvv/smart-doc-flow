from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from starlette.datastructures import Headers, UploadFile


MODULE2_ROOT = Path(__file__).resolve().parents[3] / "module2"
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.composition.application import extract_batch, extract_cache_clear  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _close_upload(upload: UploadFile) -> None:
    close = getattr(upload, "close", None)
    if callable(close):
        result = close()
        if asyncio.iscoroutine(result):
            await result


async def _handle_extract_batch(request_payload: dict[str, Any]) -> dict[str, Any]:
    uploads: list[UploadFile] = []
    for item in request_payload.get("files", []) if isinstance(request_payload.get("files"), list) else []:
        if not isinstance(item, dict):
            continue
        file_path = Path(str(item.get("path") or "").strip())
        file_handle = file_path.open("rb")
        upload = UploadFile(
            file=file_handle,
            filename=str(item.get("file_name") or file_path.name or "unknown"),
            headers=Headers({"content-type": str(item.get("content_type") or "application/octet-stream")}),
        )
        uploads.append(upload)

    try:
        request_stub = SimpleNamespace(headers=dict(request_payload.get("headers") or {}))
        response = await extract_batch(
            request=request_stub,
            files=uploads,
            schema_form=str(request_payload.get("schema_form") or "").strip(),
            tenant_id=str(request_payload.get("tenant_id") or "").strip(),
        )
        if hasattr(response, "model_dump"):
            return response.model_dump(mode="json")
        if isinstance(response, dict):
            return response
        raise RuntimeError("module2 extract_batch returned an unexpected payload")
    finally:
        for upload in uploads:
            await _close_upload(upload)


async def _handle_clear_cache(request_payload: dict[str, Any]) -> dict[str, Any]:
    response = await extract_cache_clear(scope=str(request_payload.get("scope") or "results").strip() or "results")
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    raise RuntimeError("module2 extract_cache_clear returned an unexpected payload")


async def _run(command: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    normalized_command = str(command or "").strip().lower()
    if normalized_command == "extract-batch":
        return await _handle_extract_batch(request_payload)
    if normalized_command == "clear-cache":
        return await _handle_clear_cache(request_payload)
    raise RuntimeError(f"unknown compat worker command: {command}")


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: module2_compat_worker.py <command> <request_json> <response_json>", file=sys.stderr)
        return 2

    command = argv[1]
    request_path = Path(argv[2]).resolve()
    response_path = Path(argv[3]).resolve()

    try:
        request_payload = _read_json(request_path)
        result = asyncio.run(_run(command, request_payload))
    except Exception as exc:
        _write_json(
            response_path,
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return 1

    _write_json(response_path, {"ok": True, "result": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
