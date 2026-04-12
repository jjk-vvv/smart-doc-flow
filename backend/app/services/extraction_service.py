from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import HTTPException, Request, Response, UploadFile

from app.core.config import Settings
from app.core.auth_tenant import TenantResolution, resolve_authenticated_tenant
from app.modules.extraction.artifact_runtime import get_extraction_artifact_runtime
from app.modules.extraction.assistant1_runtime import get_assistant1_facade
from app.modules.extraction.cache_runtime import merge_unified_cache_clear_payload
from app.modules.extraction.module2_execution_facade import get_module2_execution_facade
from app.modules.extraction.module2_request_runtime import (
    forward_module2_context_headers,
    normalize_cache_clear_scope,
    parse_schema_form_json,
    read_uploads_for_upstream,
)
from app.modules.extraction.module2_shadow_runtime import (
    cancel_shadow_extraction_job_file,
    clear_shadow_extraction_runtime_state,
    get_shadow_extraction_job_status,
    start_shadow_extraction_job,
)
from app.modules.extraction.module2_sidecar_runtime import (
    get_module2_sidecar_manager,
    probe_module2_upstream,
    resolve_live_module2_upstream_url,
)
from app.domain.extraction import (
    Assistant1ChatStreamRequest,
    BatchExtractionResponse,
    CacheClearResponse,
    SummarizeRequest,
    SummarizeResponse,
    TraceLocateRequest,
    TraceLocateResponse,
)
from app.modules.extraction.summary_runtime import (
    summarize_document as summarize_document_runtime,
    trace_locate as trace_locate_runtime,
)


class ExtractionService:
    @staticmethod
    def _resolve_module2_tenant_context(
        settings: Settings,
        request: Request | None,
        tenant_id: str = "",
    ) -> tuple[TenantResolution | None, dict[str, str]]:
        authenticated_user = getattr(getattr(request, "state", None), "authenticated_user", None)
        additional_headers = (
            authenticated_user.to_forward_headers()
            if authenticated_user is not None and hasattr(authenticated_user, "to_forward_headers")
            else {}
        )
        if request is None:
            return None, additional_headers
        tenant_resolution = resolve_authenticated_tenant(
            settings,
            request=request,
            additional_headers=additional_headers,
            explicit_tenant_id=tenant_id,
        )
        merged_headers = dict(additional_headers)
        merged_headers.update(tenant_resolution.to_forward_headers())
        return tenant_resolution, merged_headers

    def build_assistant1_stream(
        self,
        settings: Settings,
        request: Request,
        payload: Assistant1ChatStreamRequest,
    ) -> Response:
        facade = get_assistant1_facade()
        _, additional_headers = self._resolve_module2_tenant_context(settings, request)
        return facade.build_stream_response(
            settings,
            request=request,
            payload=payload,
            additional_headers=additional_headers,
        )

    def get_assistant1_session(
        self,
        settings: Settings,
        request: Request,
        session_id: str,
        *,
        limit: int = 40,
    ) -> Response:
        facade = get_assistant1_facade()
        _, additional_headers = self._resolve_module2_tenant_context(settings, request)
        fetch_session_response = getattr(getattr(facade, "upstream_runtime", None), "fetch_session_response", None)
        if not callable(fetch_session_response):
            raise HTTPException(status_code=503, detail="assistant session runtime unavailable")
        return fetch_session_response(
            settings,
            request=request,
            session_id=session_id,
            limit=limit,
            additional_headers=additional_headers,
        )

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        facade = get_assistant1_facade()
        assistant1_payload = facade.health_payload(settings)
        module2_execution_payload = get_module2_execution_facade().health_payload(settings)
        module2_sidecar_payload = get_module2_sidecar_manager().health_payload(settings)
        resolved_module2_upstream_url = resolve_live_module2_upstream_url(settings)
        module2_probe_payload = probe_module2_upstream(
            resolved_module2_upstream_url,
            settings.request_timeout_sec,
        )
        module2_upstream_payload = {
            "configured_url": settings.module2_upstream_url,
            "resolved_url": resolved_module2_upstream_url,
            **module2_probe_payload,
        }
        module2_ready = bool(module2_probe_payload.get("ok")) or bool(module2_sidecar_payload.get("healthy"))
        overall_ok = bool(assistant1_payload.get("ok")) and module2_ready

        return {
            "ok": overall_ok,
            "status": "ok" if overall_ok else "degraded",
            "service": "unified-extraction",
            "module2_upstream": module2_upstream_payload,
            "module2_execution": module2_execution_payload,
            "module2_sidecar": module2_sidecar_payload,
            "assistant1": assistant1_payload,
            "routes": {
                "local": {
                    "extract_jobs_create": "local",
                    "extract_jobs_status": "local",
                    "extract_jobs_cancel_file": "local",
                    "extract_batch": "local",
                    "extract_summarize": "local",
                    "extract_trace_locate": "local",
                    "extract_assistant1_chat_stream": "local",
                    "extract_assistant1_session": "local",
                    "extract_cache_clear": "local",
                    "extract_preview_office_start": "local",
                    "extract_preview_office_status": "local",
                    "extract_layout_preview": "local",
                    "extract_artifact": "local",
                },
                "proxy": {},
            },
        }

    async def create_job(
        self,
        settings: Settings,
        request: Request | None,
        uploads: list[UploadFile],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        return await start_shadow_extraction_job(
            settings,
            uploads,
            schema_form,
            parse_schema_form_json=parse_schema_form_json,
            read_uploads_for_upstream=read_uploads_for_upstream,
            execution_facade_factory=get_module2_execution_facade,
            tenant_id=(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        )

    async def extract_batch(
        self,
        settings: Settings,
        request: Request,
        uploads: list[UploadFile],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        parse_schema_form_json(schema_form)
        files_payload = await read_uploads_for_upstream(uploads)
        facade = get_module2_execution_facade()
        _, additional_headers = self._resolve_module2_tenant_context(settings, request, tenant_id)
        payload = await facade.extract_batch(
            settings,
            request_headers=forward_module2_context_headers(request, additional_headers=additional_headers),
            files_payload=files_payload,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )
        return BatchExtractionResponse.model_validate(payload).model_dump(mode="json")

    def get_job_status(
        self,
        settings: Settings,
        job_id: str,
        *,
        include_documents: bool = False,
    ) -> dict[str, Any]:
        return get_shadow_extraction_job_status(
            settings,
            job_id,
            execution_facade_factory=get_module2_execution_facade,
            include_documents=include_documents,
        )

    def cancel_job_file(
        self,
        settings: Settings,
        job_id: str,
        *,
        file_hash: str,
        file_name: str = "",
    ) -> dict[str, Any]:
        return cancel_shadow_extraction_job_file(
            settings,
            job_id,
            file_hash=file_hash,
            file_name=file_name,
            execution_facade_factory=get_module2_execution_facade,
        )

    async def clear_cache(self, settings: Settings, scope: str = "results") -> dict[str, Any]:
        normalized_scope = normalize_cache_clear_scope(scope)
        facade = get_module2_execution_facade()
        base_payload = CacheClearResponse.model_validate(
            await facade.clear_cache(settings, scope=normalized_scope)
        ).model_dump(mode="json")

        shadow_counts = clear_shadow_extraction_runtime_state(
            settings,
            remove_snapshots=normalized_scope in {"results", "all"},
        )
        office_preview_counts = get_extraction_artifact_runtime().clear_office_preview_runtime_state()
        return merge_unified_cache_clear_payload(
            base_payload,
            shadow_counts=shadow_counts,
            office_preview_counts=office_preview_counts,
        )

    async def start_office_preview(self, settings: Settings, upload: UploadFile) -> dict[str, Any]:
        return await get_extraction_artifact_runtime().start_office_preview(settings, upload)

    async def get_office_preview_status(self, settings: Settings, job_id: str) -> dict[str, Any]:
        return await get_extraction_artifact_runtime().get_office_preview_status(settings, job_id)

    def serve_layout_preview(self, settings: Settings, artifact_name: str, method: str) -> Response:
        return get_extraction_artifact_runtime().serve_layout_preview(settings, artifact_name, method)

    def serve_artifact(self, settings: Settings, artifact_path: str, method: str) -> Response:
        return get_extraction_artifact_runtime().serve_artifact(settings, artifact_path, method)

    def summarize(self, payload: SummarizeRequest) -> SummarizeResponse:
        return summarize_document_runtime(payload)

    def trace_locate(self, payload: TraceLocateRequest) -> TraceLocateResponse:
        return trace_locate_runtime(payload)


@lru_cache(maxsize=1)
def get_extraction_service() -> ExtractionService:
    return ExtractionService()
