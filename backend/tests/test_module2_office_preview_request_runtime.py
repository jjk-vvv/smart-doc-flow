from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib import import_module


runtime_module = import_module("app.modules.module2.services.preview.office")
OfficePreviewRequestRuntime = runtime_module.OfficePreviewRequestRuntime


@dataclass
class FakeUpload:
    filename: str
    payload: bytes

    def __post_init__(self) -> None:
        self._read = False

    async def read(self, size: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        if size < 0:
            return self.payload
        return self.payload[:size]


def test_office_preview_request_runtime_start_validates_and_serializes(monkeypatch) -> None:
    started_calls: list[dict] = []

    async def _ensure_job_started(**kwargs):
        started_calls.append(dict(kwargs))
        return {"job_id": "preview-1", "status": "queued"}

    runtime = OfficePreviewRequestRuntime(
        is_word_file=lambda name: name.endswith(".docx"),
        office_convert_enabled=lambda: True,
        ensure_job_started=_ensure_job_started,
        serialize_job=lambda job: {"job_id": job["job_id"], "status": job["status"]},
        get_status_payload=lambda job_id: (_ for _ in ()).throw(AssertionError("unexpected")),
    )

    async def _scenario():
        return await runtime.start(FakeUpload("demo.docx", b"demo-content"))

    payload = asyncio.run(_scenario())

    assert payload == {"job_id": "preview-1", "status": "queued"}
    assert started_calls and started_calls[0]["file_name"] == "demo.docx"
    assert started_calls[0]["file_bytes"] == b"demo-content"
    assert len(started_calls[0]["file_hash"]) == 64


def test_office_preview_request_runtime_get_status_maps_missing_job() -> None:
    async def _missing(_job_id: str):
        raise FileNotFoundError("missing")

    runtime = OfficePreviewRequestRuntime(
        is_word_file=lambda name: True,
        office_convert_enabled=lambda: True,
        ensure_job_started=lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected")),
        serialize_job=lambda job: job,
        get_status_payload=_missing,
    )

    async def _scenario():
        return await runtime.get_status("missing-job")

    try:
        asyncio.run(_scenario())
    except Exception as exc:  # noqa: BLE001
        assert exc.__class__.__name__ == "HTTPException"
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("expected HTTPException")
