from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import Settings
from app.modules.module2.composition.embedded_runtime import (
    cancel_job_file as cancel_local_job_file,
    create_job as create_local_job,
    get_job_status as get_local_job_status,
)

from .cache_runtime import merge_module2_cache_clear_payloads
from .config import ExtractionSettings, get_extraction_settings
from .module2_upstream_runtime import Module2UpstreamRuntime
from .module2_worker_runtime import Module2WorkerError, Module2WorkerRuntime


class Module2ExecutionFacade:
    def __init__(self, extraction_settings: ExtractionSettings | None = None) -> None:
        self.extraction_settings = extraction_settings or get_extraction_settings()
        self.worker_runtime = Module2WorkerRuntime(self.extraction_settings)
        self.upstream_runtime = Module2UpstreamRuntime()

    def health_payload(self, settings: Settings) -> dict[str, Any]:
        requested_mode = self.extraction_settings.module2_execution_mode
        worker_script = self._worker_script_path(settings)
        worker_available = worker_script.exists() and worker_script.is_file()
        active_mode = requested_mode
        if requested_mode == "auto":
            active_mode = "subprocess" if worker_available else "upstream"
        return {
            "requested_mode": requested_mode,
            "active_mode": active_mode,
            "fallback_to_upstream": self.extraction_settings.module2_fallback_to_upstream,
            "worker_available": worker_available,
            "worker_script": str(worker_script),
            "worker_timeout_sec": float(self.extraction_settings.module2_worker_timeout_sec),
            "worker_python": self._worker_python_executable(),
        }

    async def create_job(
        self,
        settings: Settings,
        *,
        files_payload: list[tuple[str, tuple[str, bytes, str]]],
        schema_form: str,
        tenant_id: str = "",
        request_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del settings, request_headers
        return await create_local_job(
            files_payload=files_payload,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )

    def get_job_status(
        self,
        settings: Settings,
        *,
        job_id: str,
        include_documents: bool = False,
    ) -> dict[str, Any]:
        del settings
        return get_local_job_status(
            job_id=job_id,
            include_documents=include_documents,
        )

    def cancel_job_file(
        self,
        settings: Settings,
        *,
        job_id: str,
        file_hash: str,
        file_name: str = "",
    ) -> dict[str, Any]:
        del settings
        return cancel_local_job_file(
            job_id=job_id,
            file_hash=file_hash,
            file_name=file_name,
        )

    async def extract_batch(
        self,
        settings: Settings,
        *,
        request_headers: dict[str, str],
        files_payload: list[tuple[str, tuple[str, bytes, str]]],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        requested_mode = self.extraction_settings.module2_execution_mode
        subprocess_error: Exception | None = None

        if requested_mode in {"auto", "subprocess"}:
            try:
                return await self._extract_batch_subprocess(
                    settings,
                    request_headers=request_headers,
                    files_payload=files_payload,
                    schema_form=schema_form,
                    tenant_id=tenant_id,
                )
            except Exception as exc:
                subprocess_error = exc
                if requested_mode == "subprocess" and not self.extraction_settings.module2_fallback_to_upstream:
                    raise

        if requested_mode == "subprocess" and subprocess_error is not None:
            raise subprocess_error

        return await self._extract_batch_upstream(
            settings,
            request_headers=request_headers,
            files_payload=files_payload,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )

    async def clear_cache(
        self,
        settings: Settings,
        *,
        scope: str,
        tenant_id: str = "",
        request_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        requested_mode = self.extraction_settings.module2_execution_mode
        payloads: list[dict[str, Any]] = []
        errors: list[str] = []

        if requested_mode in {"auto", "subprocess"}:
            try:
                payloads.append(await self._clear_cache_subprocess(settings, scope=scope, tenant_id=tenant_id))
            except Exception as exc:
                errors.append(f"subprocess:{type(exc).__name__}:{exc}")
                if requested_mode == "subprocess" and not self.extraction_settings.module2_fallback_to_upstream:
                    raise

        should_call_upstream = (
            requested_mode in {"upstream", "auto"}
            or (requested_mode == "subprocess" and not payloads and self.extraction_settings.module2_fallback_to_upstream)
        )

        if should_call_upstream:
            try:
                payloads.append(
                    await self._clear_cache_upstream(
                        settings,
                        scope=scope,
                        tenant_id=tenant_id,
                        request_headers=request_headers or {},
                    )
                )
            except Exception as exc:
                errors.append(f"upstream:{type(exc).__name__}:{exc}")

        if not payloads:
            raise Module2WorkerError("; ".join(errors) if errors else "module2 cache clear failed")
        return merge_module2_cache_clear_payloads(payloads, scope=scope, errors=errors)

    def _worker_python_executable(self) -> str:
        return self.worker_runtime.worker_python_executable()

    async def _extract_batch_subprocess(
        self,
        settings: Settings,
        *,
        request_headers: dict[str, str],
        files_payload: list[tuple[str, tuple[str, bytes, str]]],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        return await self.worker_runtime.extract_batch_subprocess(
            settings,
            request_headers=request_headers,
            files_payload=files_payload,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )

    async def _extract_batch_upstream(
        self,
        settings: Settings,
        *,
        request_headers: dict[str, str],
        files_payload: list[tuple[str, tuple[str, bytes, str]]],
        schema_form: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        return await self.upstream_runtime.extract_batch(
            settings,
            request_headers=request_headers,
            files_payload=files_payload,
            schema_form=schema_form,
            tenant_id=tenant_id,
        )

    async def _clear_cache_subprocess(
        self,
        settings: Settings,
        *,
        scope: str,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        return await self.worker_runtime.clear_cache_subprocess(
            settings,
            scope=scope,
            tenant_id=tenant_id,
        )

    async def _clear_cache_upstream(
        self,
        settings: Settings,
        *,
        scope: str,
        tenant_id: str = "",
        request_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return await self.upstream_runtime.clear_cache(
            settings,
            scope=scope,
            tenant_id=tenant_id,
            request_headers=request_headers or {},
        )

    @staticmethod
    def _worker_script_path(settings: Settings):
        return Module2WorkerRuntime.worker_script_path(settings)


@lru_cache(maxsize=1)
def get_module2_execution_facade() -> Module2ExecutionFacade:
    return Module2ExecutionFacade()
