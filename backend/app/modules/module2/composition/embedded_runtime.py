from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Sequence

from .application import (
    _module2_bootstrap_components,
    _module2_http_runtime_bundle,
    _module2_main_entry_bundle,
)


_PRIMARY_LOOP_LOCK = threading.Lock()
_PRIMARY_EVENT_LOOP: asyncio.AbstractEventLoop | None = None


@dataclass
class InMemoryUploadFile:
    filename: str
    content_type: str
    _content: bytes
    _cursor: int = 0

    async def read(self, size: int = -1) -> bytes:
        if int(size or -1) < 0:
            size = len(self._content) - self._cursor
        start = self._cursor
        end = min(len(self._content), start + int(size))
        self._cursor = end
        return self._content[start:end]


def embedded_lifespan(app: Any):
    return _module2_main_entry_bundle.lifespan()(app)


def _remember_primary_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    if loop is None or loop.is_closed():
        return
    with _PRIMARY_LOOP_LOCK:
        global _PRIMARY_EVENT_LOOP
        _PRIMARY_EVENT_LOOP = loop


def _get_primary_loop() -> asyncio.AbstractEventLoop | None:
    with _PRIMARY_LOOP_LOCK:
        loop = _PRIMARY_EVENT_LOOP
    if loop is None or loop.is_closed():
        return None
    return loop


def _uploads_from_files_payload(
    files_payload: Sequence[tuple[str, tuple[str, bytes, str]]],
) -> list[InMemoryUploadFile]:
    uploads: list[InMemoryUploadFile] = []
    for item in files_payload:
        _, (file_name, file_bytes, content_type) = item
        uploads.append(
            InMemoryUploadFile(
                filename=str(file_name or "file.bin"),
                content_type=str(content_type or "application/octet-stream"),
                _content=bytes(file_bytes or b""),
            )
        )
    return uploads


def _run_sync(coro: Any) -> Any:
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is not None:
        _remember_primary_loop(running_loop)
        result_holder: dict[str, Any] = {}
        error_holder: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                # Keep the event-loop-active path self-contained in a worker thread.
                # This avoids blocking the current loop thread while preserving
                # the historical behavior expected by existing call sites/tests.
                result_holder["result"] = asyncio.run(coro)
            except BaseException as exc:  # noqa: BLE001
                error_holder["error"] = exc

        worker = threading.Thread(target=_runner, name="module2-embedded-sync-bridge", daemon=True)
        worker.start()
        worker.join()
        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder.get("result")

    primary_loop = _get_primary_loop()
    if primary_loop is not None and primary_loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, primary_loop).result()

    return asyncio.run(coro)


async def create_job(
    *,
    files_payload: Sequence[tuple[str, tuple[str, bytes, str]]],
    schema_form: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    _remember_primary_loop(asyncio.get_running_loop())
    return await _module2_http_runtime_bundle.extraction_request_runtime.create_job(
        request=None,
        files=_uploads_from_files_payload(files_payload),
        schema_form=str(schema_form or ""),
        tenant_id=str(tenant_id or ""),
    )


def get_job_status(job_id: str, *, include_documents: bool = False) -> dict[str, Any]:
    return _run_sync(
        _module2_http_runtime_bundle.extraction_request_runtime.get_job_status(
            str(job_id or ""),
            include_documents=bool(include_documents),
        )
    )


def cancel_job_file(*, job_id: str, file_hash: str, file_name: str = "") -> dict[str, Any]:
    return _run_sync(
        _module2_http_runtime_bundle.extraction_request_runtime.cancel_job_file(
            job_id=str(job_id or ""),
            payload={
                "file_hash": str(file_hash or ""),
                "file_name": str(file_name or ""),
            },
        )
    )


async def clear_cache(*, scope: str, tenant_id: str = "") -> dict[str, Any]:
    _remember_primary_loop(asyncio.get_running_loop())
    return await _module2_main_entry_bundle.module2_app_callback_bundle.clear_cache_request(
        str(scope or ""),
        tenant_id=str(tenant_id or ""),
    )


async def trigger_graph_sync(
    *,
    request: Any = None,
    payload: dict[str, Any] | None = None,
    background_tasks: Any | None = None,
) -> dict[str, Any]:
    _remember_primary_loop(asyncio.get_running_loop())
    return await _module2_http_runtime_bundle.extraction_request_runtime.trigger_graph_sync(
        request=request,
        payload=dict(payload or {}),
        background_tasks=background_tasks,
    )


def build_health_payload() -> dict[str, Any]:
    payload = _module2_main_entry_bundle.module2_app_callback_bundle.build_health_payload()
    return dict(payload) if isinstance(payload, dict) else {}


def get_assistant1_runtime() -> Any:
    return _module2_bootstrap_components.foundation_bundle.service_bundle.assistant1_runtime


__all__ = [
    "build_health_payload",
    "cancel_job_file",
    "clear_cache",
    "create_job",
    "embedded_lifespan",
    "get_assistant1_runtime",
    "get_job_status",
    "trigger_graph_sync",
]
