from __future__ import annotations

from functools import lru_cache
import inspect
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.core.config import Settings
from app.core.auth_tenant import TenantResolution, resolve_authenticated_tenant
from app.modules.file_assets.service import (
    build_file_asset_urls,
    register_file,
    resolve_file_for_owner,
)
from app.modules.module2.core.artifact_runtime import get_extraction_artifact_runtime
from app.modules.module2.core.assistant1_runtime import get_assistant1_facade
from app.modules.module2.core.cache_runtime import merge_unified_cache_clear_payload
from app.modules.module2.core.config import get_extraction_settings
from app.modules.module2.core.module2_execution_facade import get_module2_execution_facade
from app.modules.module2.core.module2_request_runtime import (
    forward_module2_context_headers,
    normalize_cache_clear_scope,
    parse_schema_form_json,
    read_uploads_for_upstream,
)
from app.modules.module2.core.module2_shadow_runtime import (
    cancel_shadow_extraction_job_file,
    clear_shadow_extraction_runtime_state,
    get_shadow_extraction_job_status,
    start_shadow_extraction_job,
)
from app.modules.module2.core.module2_sidecar_runtime import (
    get_module2_sidecar_manager,
    probe_module2_upstream,
    resolve_live_module2_upstream_url,
)
from app.modules.module2.schemas.extraction import (
    Assistant1ChatStreamRequest,
    BatchExtractionResponse,
    CacheClearResponse,
    SummarizeRequest,
    SummarizeResponse,
    TraceLocateRequest,
    TraceLocateResponse,
)
from app.modules.module2.core.summary_runtime import (
    summarize_document as summarize_document_runtime,
    trace_locate as trace_locate_runtime,
)


class ExtractionService:
    @staticmethod
    def _artifact_path_key_to_output_keys(path_key: str) -> tuple[str, str, str] | None:
        key_name = str(path_key or "").strip()
        if not key_name.endswith("_path"):
            return None
        base_name = key_name[: -len("_path")].strip()
        if not base_name:
            return None
        return (
            f"{base_name}_file_id",
            f"{base_name}_download_url",
            f"{base_name}_by_file_url",
        )

    @staticmethod
    def _artifact_url_key_to_output_keys(url_key: str) -> tuple[str, str, str] | None:
        key_name = str(url_key or "").strip()
        if not key_name.endswith("_url"):
            return None
        base_name = key_name[: -len("_url")].strip()
        if not base_name:
            return None
        return (
            f"{base_name}_file_id",
            f"{base_name}_download_url",
            f"{base_name}_by_file_url",
        )

    @staticmethod
    def _build_module2_by_file_url(source_key: str, file_id: str) -> str:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            return ""
        normalized_key = str(source_key or "").strip().lower()
        preview_like = (
            normalized_key == "layout_preview_path"
            or normalized_key == "layout_preview_url"
            or normalized_key.endswith("_preview_path")
            or normalized_key.endswith("_preview_url")
        )
        if preview_like:
            return f"/extract/layout-preview/by-file/{normalized_file_id}"
        return f"/extract/artifact/by-file/{normalized_file_id}"

    @staticmethod
    def _artifact_fragment_from_url(url: str) -> str:
        raw_value = str(url or "").strip()
        if not raw_value:
            return ""
        normalized_url = raw_value.split("#", 1)[0].split("?", 1)[0].strip()
        if not normalized_url:
            return ""
        lowered = normalized_url.lower()
        if lowered.startswith(("http://", "https://", "data:", "/download/", "/file-assets/")):
            return ""
        prefix = "/extract/artifact/"
        if lowered.startswith(prefix):
            return unquote(normalized_url[len(prefix) :].lstrip("/"))
        relative_prefix = "extract/artifact/"
        if lowered.startswith(relative_prefix):
            return unquote(normalized_url[len(relative_prefix) :].lstrip("/"))
        return ""

    def _resolve_module2_artifact_candidate(
        self,
        settings: Settings,
        artifact_path: str,
    ) -> Path | None:
        raw_value = str(artifact_path or "").strip()
        if not raw_value:
            return None

        candidate = Path(raw_value).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if resolved.exists() and resolved.is_file():
                return resolved

        runtime = get_extraction_artifact_runtime()
        try:
            resolved = runtime.resolve_existing_artifact_path(settings, raw_value)
        except Exception:
            return None
        if not resolved.exists() or not resolved.is_file():
            return None
        return resolved

    def _augment_module2_payload_with_file_assets(
        self,
        settings: Settings,
        payload: Any,
        *,
        owner_id: str,
    ) -> Any:
        normalized_owner = str(owner_id or "").strip() or "default"
        file_id_cache: dict[str, str] = {}

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in list(node.items()):
                    _walk(value)
                    if not isinstance(value, str):
                        continue

                    output_keys: tuple[str, str, str] | None = None
                    artifact_reference = ""
                    if key == "artifact_path" or key.endswith("_artifact_path") or key.endswith("_preview_path"):
                        output_keys = self._artifact_path_key_to_output_keys(key)
                        artifact_reference = value
                    elif key == "artifact_url" or key.endswith("_artifact_url") or key.endswith("_preview_url"):
                        output_keys = self._artifact_url_key_to_output_keys(key)
                        artifact_reference = self._artifact_fragment_from_url(value)

                    if output_keys is None:
                        continue
                    file_id_key, download_url_key, by_file_url_key = output_keys

                    existing_file_id = str(node.get(file_id_key) or "").strip()
                    if existing_file_id:
                        file_asset_urls = build_file_asset_urls(existing_file_id)
                        if not str(node.get(download_url_key) or "").strip():
                            node[download_url_key] = str(file_asset_urls.get("download_url") or "")
                        if not str(node.get(by_file_url_key) or "").strip():
                            by_file_url = self._build_module2_by_file_url(key, existing_file_id)
                            if by_file_url:
                                node[by_file_url_key] = by_file_url
                        continue

                    if not artifact_reference:
                        continue

                    resolved = self._resolve_module2_artifact_candidate(settings, artifact_reference)
                    if resolved is None:
                        continue

                    cache_key = str(resolved)
                    cached_file_id = file_id_cache.get(cache_key)
                    if cached_file_id is None:
                        try:
                            asset = register_file(
                                path=resolved,
                                owner_id=normalized_owner,
                                source_module="module2",
                                purpose="extraction_artifact",
                                filename=resolved.name,
                            )
                        except Exception:
                            continue
                        cached_file_id = str(asset.get("file_id") or "").strip()
                        if not cached_file_id:
                            continue
                        file_id_cache[cache_key] = cached_file_id

                    if not str(node.get(file_id_key) or "").strip():
                        node[file_id_key] = cached_file_id
                    file_asset_urls = build_file_asset_urls(cached_file_id)
                    if not str(node.get(download_url_key) or "").strip():
                        node[download_url_key] = str(file_asset_urls.get("download_url") or "")
                    if not str(node.get(by_file_url_key) or "").strip():
                        by_file_url = self._build_module2_by_file_url(key, cached_file_id)
                        if by_file_url:
                            node[by_file_url_key] = by_file_url
                return

            if isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(payload)
        return payload

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
        extraction_settings = get_extraction_settings()
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
            "tenant_guard_mode": extraction_settings.job_tenant_guard_mode,
            "artifact_tenant_guard_mode": str(
                os.getenv("UNIFIED_EXTRACT_ARTIFACT_TENANT_GUARD_MODE", "warn") or "warn"
            ).strip().lower(),
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
        tenant_resolution, additional_headers = self._resolve_module2_tenant_context(settings, request, tenant_id)
        create_job_kwargs: dict[str, Any] = {
            "parse_schema_form_json": parse_schema_form_json,
            "read_uploads_for_upstream": read_uploads_for_upstream,
            "execution_facade_factory": get_module2_execution_facade,
            "tenant_id": (tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        }
        start_job_params = inspect.signature(start_shadow_extraction_job).parameters
        if "request_headers" in start_job_params:
            create_job_kwargs["request_headers"] = (
                forward_module2_context_headers(request, additional_headers=additional_headers)
                if request is not None
                else (additional_headers or {})
            )
        payload = await start_shadow_extraction_job(
            settings,
            uploads,
            schema_form,
            **create_job_kwargs,
        )
        resolved_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=resolved_tenant_id,
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
        tenant_resolution, additional_headers = self._resolve_module2_tenant_context(settings, request, tenant_id)
        payload = await facade.extract_batch(
            settings,
            request_headers=forward_module2_context_headers(request, additional_headers=additional_headers),
            files_payload=files_payload,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )
        validated = BatchExtractionResponse.model_validate(payload).model_dump(mode="json")
        resolved_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        return self._augment_module2_payload_with_file_assets(
            settings,
            validated,
            owner_id=resolved_tenant_id,
        )

    def get_job_status(
        self,
        settings: Settings,
        request: Request | None,
        job_id: str,
        *,
        include_documents: bool = False,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        payload = get_shadow_extraction_job_status(
            settings,
            job_id,
            execution_facade_factory=get_module2_execution_facade,
            include_documents=include_documents,
            expected_tenant_id=(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        )
        resolved_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=resolved_tenant_id,
        )

    def cancel_job_file(
        self,
        settings: Settings,
        request: Request | None,
        job_id: str,
        *,
        file_hash: str,
        file_name: str = "",
        tenant_id: str = "",
    ) -> dict[str, Any]:
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        return cancel_shadow_extraction_job_file(
            settings,
            job_id,
            file_hash=file_hash,
            file_name=file_name,
            execution_facade_factory=get_module2_execution_facade,
            expected_tenant_id=(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        )

    async def clear_cache(
        self,
        settings: Settings,
        scope: str = "results",
        request: Request | None = None,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        normalized_scope = normalize_cache_clear_scope(scope)
        tenant_resolution, additional_headers = self._resolve_module2_tenant_context(settings, request, tenant_id)
        resolved_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        facade = get_module2_execution_facade()

        clear_cache_kwargs: dict[str, Any] = {"scope": normalized_scope}
        clear_cache_params = inspect.signature(facade.clear_cache).parameters
        if "tenant_id" in clear_cache_params:
            clear_cache_kwargs["tenant_id"] = resolved_tenant_id
        if "request_headers" in clear_cache_params:
            clear_cache_kwargs["request_headers"] = additional_headers
        base_payload = CacheClearResponse.model_validate(
            await facade.clear_cache(settings, **clear_cache_kwargs)
        ).model_dump(mode="json")

        shadow_clear_kwargs: dict[str, Any] = {"remove_snapshots": normalized_scope in {"results", "all"}}
        shadow_clear_params = inspect.signature(clear_shadow_extraction_runtime_state).parameters
        if "tenant_id" in shadow_clear_params:
            shadow_clear_kwargs["tenant_id"] = resolved_tenant_id
        shadow_counts = clear_shadow_extraction_runtime_state(settings, **shadow_clear_kwargs)

        office_runtime = get_extraction_artifact_runtime()
        office_clear = office_runtime.clear_office_preview_runtime_state
        office_clear_params = inspect.signature(office_clear).parameters
        if "tenant_id" in office_clear_params:
            office_preview_counts = office_clear(tenant_id=resolved_tenant_id)
        else:
            office_preview_counts = office_clear()
        return merge_unified_cache_clear_payload(
            base_payload,
            shadow_counts=shadow_counts,
            office_preview_counts=office_preview_counts,
        )

    async def start_office_preview(
        self,
        settings: Settings,
        request: Request | None,
        upload: UploadFile,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        payload = await get_extraction_artifact_runtime().start_office_preview(
            settings,
            upload,
            tenant_id=(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        )
        resolved_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=resolved_tenant_id,
        )

    async def get_office_preview_status(
        self,
        settings: Settings,
        request: Request | None,
        job_id: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        payload = await get_extraction_artifact_runtime().get_office_preview_status(
            settings,
            job_id,
            expected_tenant_id=(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        )
        resolved_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=resolved_tenant_id,
        )

    def serve_layout_preview(
        self,
        settings: Settings,
        request: Request | None,
        artifact_name: str,
        method: str,
        file_id: str = "",
        tenant_id: str = "",
    ) -> Response:
        if str(file_id or "").strip():
            return self.serve_file_asset(
                settings,
                request,
                file_id,
                method,
                tenant_id=tenant_id,
            )
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        return get_extraction_artifact_runtime().serve_layout_preview(
            settings,
            artifact_name,
            method,
            expected_tenant_id=(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        )

    def serve_artifact(
        self,
        settings: Settings,
        request: Request | None,
        artifact_path: str,
        method: str,
        file_id: str = "",
        tenant_id: str = "",
    ) -> Response:
        if str(file_id or "").strip():
            return self.serve_file_asset(
                settings,
                request,
                file_id,
                method,
                tenant_id=tenant_id,
            )
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        return get_extraction_artifact_runtime().serve_artifact(
            settings,
            artifact_path,
            method,
            expected_tenant_id=(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id),
        )

    @staticmethod
    def _file_asset_head_response(file_path: Path, *, media_type: str) -> Response:
        return Response(
            status_code=200,
            headers={
                "Content-Length": str(file_path.stat().st_size),
                "Content-Type": media_type or "application/octet-stream",
            },
        )

    def serve_file_asset(
        self,
        settings: Settings,
        request: Request | None,
        file_id: str,
        method: str,
        *,
        tenant_id: str = "",
    ) -> Response:
        normalized_file_id = str(file_id or "").strip()
        if not normalized_file_id:
            raise HTTPException(status_code=400, detail="file_id is required")

        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        owner_id = str(tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id).strip()
        if not owner_id and request is not None:
            authenticated_user = getattr(getattr(request, "state", None), "authenticated_user", None)
            owner_id = (
                str(getattr(authenticated_user, "tenant_id", "") or "").strip()
                or str(getattr(authenticated_user, "user_id", "") or "").strip()
                or str(request.headers.get("X-Authenticated-User-Id") or "").strip()
            )
        if not owner_id:
            owner_id = "default"

        try:
            record, file_path = resolve_file_for_owner(normalized_file_id, owner_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        media_type = str(record.get("mime_type") or "application/octet-stream")
        if str(method or "").upper() == "HEAD":
            return self._file_asset_head_response(file_path, media_type=media_type)
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=str(record.get("filename") or file_path.name),
            content_disposition_type="inline",
        )

    def summarize(self, payload: SummarizeRequest) -> SummarizeResponse:
        return summarize_document_runtime(payload)

    def trace_locate(
        self,
        payload: TraceLocateRequest,
        settings: Settings | None = None,
        request: Request | None = None,
        tenant_id: str = "",
    ) -> TraceLocateResponse:
        response = trace_locate_runtime(payload)
        if settings is None:
            return response

        normalized_payload = (
            response.model_dump(mode="json")
            if hasattr(response, "model_dump")
            else dict(response or {})
        )
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        resolved_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        augmented = self._augment_module2_payload_with_file_assets(
            settings,
            normalized_payload,
            owner_id=resolved_tenant_id,
        )
        return TraceLocateResponse.model_validate(augmented)


@lru_cache(maxsize=1)
def get_extraction_service() -> ExtractionService:
    return ExtractionService()
