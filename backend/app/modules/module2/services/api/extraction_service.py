from __future__ import annotations

import asyncio
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
from app.modules.module2.composition.embedded_runtime import (
    build_health_payload as build_embedded_module2_health_payload,
    get_assistant1_runtime as get_embedded_assistant1_runtime,
    trigger_graph_sync as trigger_embedded_graph_sync,
)
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
    get_shadow_extraction_job_status_snapshot,
    start_shadow_extraction_job,
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
    def _select_graph_sync_document_payload(
        payload: dict[str, Any] | None,
        *,
        file_name: str = "",
        file_hash: str = "",
    ) -> dict[str, Any] | None:
        documents = payload.get("documents") if isinstance(payload, dict) and isinstance(payload.get("documents"), list) else []
        normalized_name = str(file_name or "").strip().lower()
        normalized_hash = str(file_hash or "").strip()
        fallback_document: dict[str, Any] | None = None

        for item in documents:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("file_name") or "").strip()
            item_hash = str(item.get("file_hash") or "").strip()
            item_name_lower = item_name.lower()

            if normalized_hash and item_hash == normalized_hash:
                if not normalized_name or not item_name or item_name_lower == normalized_name:
                    return dict(item)
                if fallback_document is None:
                    fallback_document = dict(item)
                continue

            if not normalized_hash and normalized_name and item_name_lower == normalized_name:
                return dict(item)

        return fallback_document

    @staticmethod
    def _compact_job_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
        def _to_int(value: Any, *, minimum: int = 0) -> int:
            try:
                return max(minimum, int(value))
            except (TypeError, ValueError):
                return minimum

        def _to_ratio(value: Any) -> float:
            try:
                return max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                return 0.0

        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        errors_raw = payload.get("errors")
        errors = [str(item or "").strip() for item in (errors_raw or []) if str(item or "").strip()]
        active_stages_raw = progress.get("active_stages")
        active_stages: dict[str, int] = {}
        if isinstance(active_stages_raw, dict):
            for stage, raw_count in active_stages_raw.items():
                normalized_count = _to_int(raw_count, minimum=0)
                if normalized_count <= 0:
                    continue
                active_stages[str(stage or "").strip() or "unknown"] = normalized_count

        return {
            "ok": bool(payload.get("ok", True)),
            "job_id": str(payload.get("job_id") or "").strip(),
            "status": str(payload.get("status") or "").strip() or "queued",
            "terminal": bool(payload.get("terminal")),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "progress": {
                "total_files": _to_int(progress.get("total_files"), minimum=0),
                "completed_files": _to_int(progress.get("completed_files"), minimum=0),
                "failed_files": _to_int(progress.get("failed_files"), minimum=0),
                "current_file_index": _to_int(progress.get("current_file_index"), minimum=0),
                "current_file_name": str(progress.get("current_file_name") or "").strip(),
                "current_stage": str(progress.get("current_stage") or "").strip() or "queued",
                "progress_ratio": _to_ratio(progress.get("progress_ratio")),
                "queued_files": _to_int(progress.get("queued_files"), minimum=0),
                "active_stages": active_stages,
            },
            "errors": errors,
        }

    @staticmethod
    def _repo_root_dir() -> Path:
        try:
            return Path(__file__).resolve().parents[3]
        except Exception:
            return Path.cwd().resolve()

    @staticmethod
    def _resolve_file_asset_owner_id(
        request: Request | None,
        tenant_resolution: TenantResolution | None,
        explicit_tenant_id: str = "",
    ) -> str:
        owner_candidates: list[str] = []
        if tenant_resolution is not None:
            owner_candidates.append(str(getattr(tenant_resolution, "tenant_id", "") or "").strip())
        owner_candidates.append(str(explicit_tenant_id or "").strip())

        authenticated_user = getattr(getattr(request, "state", None), "authenticated_user", None)
        owner_candidates.append(str(getattr(authenticated_user, "tenant_id", "") or "").strip())
        owner_candidates.append(str(getattr(authenticated_user, "user_id", "") or "").strip())

        if request is not None:
            owner_candidates.append(str(request.headers.get("X-Authenticated-Tenant-Id") or "").strip())
            owner_candidates.append(str(request.headers.get("X-Authenticated-User-Id") or "").strip())

        for candidate in owner_candidates:
            if candidate:
                return candidate
        return "default"

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
    def _artifact_path_key_to_companion_url_key(path_key: str) -> str:
        key_name = str(path_key or "").strip()
        if not key_name.endswith("_path"):
            return ""
        base_name = key_name[: -len("_path")].strip()
        if not base_name:
            return ""
        return f"{base_name}_url"

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
        layout_prefix = "/extract/layout-preview/"
        if lowered.startswith(layout_prefix):
            return unquote(normalized_url[len(layout_prefix) :].lstrip("/"))
        relative_prefix = "extract/artifact/"
        if lowered.startswith(relative_prefix):
            return unquote(normalized_url[len(relative_prefix) :].lstrip("/"))
        relative_layout_prefix = "extract/layout-preview/"
        if lowered.startswith(relative_layout_prefix):
            return unquote(normalized_url[len(relative_layout_prefix) :].lstrip("/"))
        return ""

    @staticmethod
    def _fallback_module2_artifact_roots(settings: Settings) -> list[Path]:
        repo_root = ExtractionService._repo_root_dir()
        runtime_root = Path(getattr(settings, "runtime_root_dir", Path.cwd())).resolve()
        data_root = Path(getattr(settings, "data_root_dir", runtime_root / "runtime-data")).resolve()
        candidates = [
            (data_root / "module2" / "artifacts").resolve(),
            (runtime_root / "runtime-data" / "module2" / "artifacts").resolve(),
            (
                runtime_root
                / "backend"
                / "app"
                / "modules"
                / "module2"
                / "runtime-data"
                / "module2"
                / "artifacts"
            ).resolve(),
            (repo_root / "runtime-data" / "module2" / "artifacts").resolve(),
            (
                repo_root
                / "backend"
                / "app"
                / "modules"
                / "module2"
                / "runtime-data"
                / "module2"
                / "artifacts"
            ).resolve(),
            (
                repo_root
                / "backend"
                / "module2"
                / "runtime-data"
                / "module2"
                / "artifacts"
            ).resolve(),
        ]
        uniq: list[Path] = []
        for root in candidates:
            if root not in uniq:
                uniq.append(root)
        return uniq

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
            resolved = None
        if resolved is not None and resolved.exists() and resolved.is_file():
            return resolved

        normalized_rel = raw_value.replace("\\", "/").lstrip("/")
        if not normalized_rel:
            return None

        for root in self._fallback_module2_artifact_roots(settings):
            try:
                candidate = (root / normalized_rel).resolve()
            except Exception:
                continue
            try:
                candidate.relative_to(root)
            except Exception:
                continue
            if candidate.exists() and candidate.is_file():
                return candidate

        return None

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
                    canonical_url_key = ""
                    if key == "artifact_path" or key.endswith("_artifact_path") or key.endswith("_preview_path"):
                        output_keys = self._artifact_path_key_to_output_keys(key)
                        artifact_reference = value
                        canonical_url_key = self._artifact_path_key_to_companion_url_key(key)
                    elif key == "artifact_url" or key.endswith("_artifact_url") or key.endswith("_preview_url"):
                        output_keys = self._artifact_url_key_to_output_keys(key)
                        artifact_reference = self._artifact_fragment_from_url(value)
                        canonical_url_key = key

                    if output_keys is None:
                        continue
                    file_id_key, download_url_key, by_file_url_key = output_keys

                    existing_file_id = str(node.get(file_id_key) or "").strip()
                    if existing_file_id:
                        file_asset_urls = build_file_asset_urls(existing_file_id)
                        if not str(node.get(download_url_key) or "").strip():
                            node[download_url_key] = str(file_asset_urls.get("download_url") or "")
                        by_file_url = self._build_module2_by_file_url(key, existing_file_id)
                        if not str(node.get(by_file_url_key) or "").strip():
                            if by_file_url:
                                node[by_file_url_key] = by_file_url
                        # Canonicalize payload URL fields to by-file routes so deep links
                        # don't depend on legacy /extract/artifact/<path> endpoints.
                        if by_file_url and canonical_url_key:
                            node[canonical_url_key] = by_file_url
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
                    by_file_url = self._build_module2_by_file_url(key, cached_file_id)
                    if not str(node.get(by_file_url_key) or "").strip():
                        if by_file_url:
                            node[by_file_url_key] = by_file_url
                    if by_file_url and canonical_url_key:
                        node[canonical_url_key] = by_file_url
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

    async def get_assistant1_session_async(
        self,
        settings: Settings,
        request: Request,
        session_id: str,
        *,
        limit: int = 40,
    ) -> Response:
        facade = get_assistant1_facade()
        extraction_settings = get_extraction_settings()
        _, additional_headers = self._resolve_module2_tenant_context(settings, request)
        if extraction_settings.assistant1_mode != "upstream":
            runtime = get_embedded_assistant1_runtime()
            persistence = getattr(runtime, "persistence", None)
            if persistence is None:
                raise HTTPException(status_code=503, detail="assistant session persistence unavailable")

            expected_tenant_id = (
                str(additional_headers.get("X-Authenticated-Tenant-Id") or "").strip()
                or str(additional_headers.get("X-Authenticated-User-Id") or "").strip()
                or str(additional_headers.get("X-Tenant-Id") or "").strip()
            )
            session = inspect.iscoroutinefunction(getattr(persistence, "fetch_session", None))
            if not session:
                raise HTTPException(status_code=503, detail="assistant session persistence unavailable")
            session_payload = await persistence.fetch_session(
                session_id, expected_tenant_id=expected_tenant_id
            )
            messages = await persistence.list_messages(
                session_id,
                limit=limit,
                expected_tenant_id=expected_tenant_id,
            )
            if not isinstance(session_payload, dict) and not messages:
                raise HTTPException(status_code=404, detail="assistant session not found")
            return {
                "session_id": str(session_id or "").strip(),
                "summary_used": str((session_payload or {}).get("summary_text") or ""),
                "current_object_lock": (
                    (session_payload or {}).get("current_object_lock_json")
                    if isinstance((session_payload or {}).get("current_object_lock_json"), dict)
                    else None
                ),
                "messages": messages,
                "file_hash": str((session_payload or {}).get("file_hash") or ""),
                "file_name": str((session_payload or {}).get("file_name") or ""),
                "metadata": (
                    (session_payload or {}).get("metadata_json")
                    if isinstance((session_payload or {}).get("metadata_json"), dict)
                    else {}
                ),
            }
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

    def get_assistant1_session(
        self,
        settings: Settings,
        request: Request,
        session_id: str,
        *,
        limit: int = 40,
    ) -> Response:
        return asyncio.run(
            self.get_assistant1_session_async(settings, request, session_id, limit=limit)
        )

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        extraction_settings = get_extraction_settings()
        facade = get_assistant1_facade()
        assistant1_payload = facade.health_payload(settings)
        module2_execution_payload = get_module2_execution_facade().health_payload(settings)
        module2_embedded_payload = build_embedded_module2_health_payload()
        module2_ready = str(module2_embedded_payload.get("status") or "").strip().lower() == "ok"
        module2_upstream_payload = {
            "configured_url": "",
            "resolved_url": "embedded://module2",
            "ok": module2_ready,
            "mode": "embedded",
            "health_url": "embedded://module2/healthz",
            "payload": module2_embedded_payload,
        }
        module2_sidecar_payload = {
            "requested_mode": "disabled",
            "active_mode": "embedded",
            "healthy": module2_ready,
            "running": False,
            "preferred_base_url": "",
            "last_error": "",
        }
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
        owner_id = self._resolve_file_asset_owner_id(
            request,
            tenant_resolution,
            tenant_id,
        )
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=owner_id,
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
        owner_id = self._resolve_file_asset_owner_id(
            request,
            tenant_resolution,
            tenant_id,
        )
        return self._augment_module2_payload_with_file_assets(
            settings,
            validated,
            owner_id=owner_id,
        )

    def get_job_status(
        self,
        settings: Settings,
        request: Request | None,
        job_id: str,
        *,
        include_documents: bool = False,
        status_only: bool = False,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, tenant_id)
        expected_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else tenant_id
        if status_only:
            try:
                payload = get_shadow_extraction_job_status_snapshot(
                    settings,
                    job_id,
                    include_documents=False,
                    expected_tenant_id=expected_tenant_id,
                )
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                payload = get_shadow_extraction_job_status(
                    settings,
                    job_id,
                    execution_facade_factory=get_module2_execution_facade,
                    include_documents=False,
                    expected_tenant_id=expected_tenant_id,
                )
        else:
            payload = get_shadow_extraction_job_status(
                settings,
                job_id,
                execution_facade_factory=get_module2_execution_facade,
                include_documents=include_documents,
                expected_tenant_id=expected_tenant_id,
            )
        if status_only:
            return self._compact_job_status_payload(payload)
        owner_id = self._resolve_file_asset_owner_id(
            request,
            tenant_resolution,
            tenant_id,
        )
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=owner_id,
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
        owner_id = self._resolve_file_asset_owner_id(
            request,
            tenant_resolution,
            tenant_id,
        )
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=owner_id,
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
        owner_id = self._resolve_file_asset_owner_id(
            request,
            tenant_resolution,
            tenant_id,
        )
        return self._augment_module2_payload_with_file_assets(
            settings,
            payload,
            owner_id=owner_id,
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
        owner_id = self._resolve_file_asset_owner_id(request, tenant_resolution, tenant_id)

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

    async def trigger_graph_sync(
        self,
        settings: Settings,
        request: Request,
        payload: dict[str, Any] | None = None,
        background_tasks: Any | None = None,
    ) -> dict[str, Any]:
        normalized_payload = dict(payload or {})
        job_id = str(normalized_payload.get("job_id") or "").strip()
        file_name = str(normalized_payload.get("file_name") or "").strip()
        file_hash = str(normalized_payload.get("file_hash") or "").strip()
        document_payload = normalized_payload.get("document")

        if document_payload is None and job_id:
            tenant_resolution, _ = self._resolve_module2_tenant_context(settings, request, "")
            expected_tenant_id = tenant_resolution.tenant_id if tenant_resolution is not None else ""
            try:
                status_payload = await asyncio.to_thread(
                    get_shadow_extraction_job_status_snapshot,
                    settings,
                    job_id,
                    include_documents=True,
                    expected_tenant_id=expected_tenant_id,
                )
            except HTTPException:
                status_payload = None
            except Exception:
                status_payload = None

            recovered_document = self._select_graph_sync_document_payload(
                status_payload,
                file_name=file_name,
                file_hash=file_hash,
            )
            if recovered_document is None:
                try:
                    live_status_payload = await asyncio.to_thread(
                        self.get_job_status,
                        settings,
                        request,
                        job_id,
                        include_documents=True,
                        status_only=False,
                    )
                except HTTPException:
                    live_status_payload = None
                except Exception:
                    live_status_payload = None
                recovered_document = self._select_graph_sync_document_payload(
                    live_status_payload,
                    file_name=file_name,
                    file_hash=file_hash,
                )
            if recovered_document is not None:
                normalized_payload["document"] = recovered_document
                if not file_name:
                    normalized_payload["file_name"] = str(recovered_document.get("file_name") or "").strip()
                if not file_hash:
                    normalized_payload["file_hash"] = str(recovered_document.get("file_hash") or "").strip()

        return await trigger_embedded_graph_sync(
            request=request,
            payload=normalized_payload,
            background_tasks=background_tasks,
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
        owner_id = self._resolve_file_asset_owner_id(
            request,
            tenant_resolution,
            tenant_id,
        )
        augmented = self._augment_module2_payload_with_file_assets(
            settings,
            normalized_payload,
            owner_id=owner_id,
        )
        return TraceLocateResponse.model_validate(augmented)


@lru_cache(maxsize=1)
def get_extraction_service() -> ExtractionService:
    return ExtractionService()
