from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings

from .module2_sidecar_runtime import parse_upstream_json_response, request_module2
from .schemas import CacheClearResponse


class Module2UpstreamRuntime:
    async def create_job(
        self,
        settings: Settings,
        *,
        files_payload: list[tuple[str, tuple[str, bytes, str]]],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        response = await asyncio.to_thread(
            request_module2,
            settings,
            method="POST",
            path="/extract/jobs/create",
            data={
                "schema": str(schema_form or "").strip(),
                "tenant_id": str(tenant_id or "").strip(),
            },
            files=files_payload,
            timeout_sec=max(settings.request_timeout_sec, 180.0),
            ensure_sidecar=True,
        )
        return parse_upstream_json_response(response, default_action="create extraction job")

    def get_job_status(
        self,
        settings: Settings,
        *,
        job_id: str,
        include_documents: bool = False,
    ) -> dict[str, Any]:
        response = request_module2(
            settings,
            method="GET",
            path=f"/extract/jobs/status/{str(job_id or '').strip()}",
            params={"include_documents": "true"} if include_documents else None,
            timeout_sec=max(settings.request_timeout_sec, 30.0),
            ensure_sidecar=True,
        )
        return parse_upstream_json_response(response, default_action="fetch extraction job status")

    def cancel_job_file(
        self,
        settings: Settings,
        *,
        job_id: str,
        file_hash: str,
        file_name: str = "",
    ) -> dict[str, Any]:
        response = request_module2(
            settings,
            method="POST",
            path=f"/extract/jobs/{str(job_id or '').strip()}/cancel-file",
            json_payload={
                "file_hash": str(file_hash or "").strip(),
                "file_name": str(file_name or "").strip(),
            },
            timeout_sec=max(settings.request_timeout_sec, 30.0),
            ensure_sidecar=True,
        )
        return parse_upstream_json_response(response, default_action="cancel extraction job file")

    async def extract_batch(
        self,
        settings: Settings,
        *,
        request_headers: dict[str, str],
        files_payload: list[tuple[str, tuple[str, bytes, str]]],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        response = await asyncio.to_thread(
            request_module2,
            settings,
            method="POST",
            path="/extract/batch",
            data={
                "schema": str(schema_form or "").strip(),
                "tenant_id": str(tenant_id or "").strip(),
            },
            files=files_payload,
            headers=request_headers or None,
            timeout_sec=max(settings.request_timeout_sec, 300.0),
        )
        return parse_upstream_json_response(response, default_action="run batch extraction")

    async def clear_cache(
        self,
        settings: Settings,
        *,
        scope: str,
    ) -> dict[str, Any]:
        response = await asyncio.to_thread(
            request_module2,
            settings,
            method="POST",
            path="/extract/cache/clear",
            params={"scope": str(scope or "").strip()},
            timeout_sec=max(settings.request_timeout_sec, 120.0),
        )
        payload = parse_upstream_json_response(response, default_action="clear extraction cache")
        return CacheClearResponse.model_validate(payload).model_dump(mode="json")
