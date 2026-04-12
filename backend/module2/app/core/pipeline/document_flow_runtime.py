from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional


ProgressHook = Optional[Callable[[str, float, str, Dict[str, Any]], Awaitable[None]]]
EmitProgress = Callable[[str, float, str, Optional[Dict[str, Any]]], Awaitable[None]]
BuildStreamRouter = Callable[[], Any]
SaveExtractionResult = Callable[[str, Dict[str, Any]], Awaitable[None]]


@dataclass
class DocumentExecutionStart:
    decision: Any
    emit_progress: EmitProgress
    cached_response: Any = None


@dataclass(frozen=True)
class DocumentExecutionDependencyBundle:
    build_stream_router: BuildStreamRouter
    cached_extraction_restore_runtime: Any
    normalize_soft_warnings: Any
    promote_visual_diagnostics: Any
    persist_assistant_payload_artifact: Any
    extraction_result_factory: Any
    document_response_factory: Any
    save_extraction_result: SaveExtractionResult
    persist_field_results_artifact: Any = None


class DocumentExecutionRuntime:
    """Coordinate ingress and completion concerns for a single document extraction run."""

    @staticmethod
    def _require_dependency(name: str, value: Any) -> Any:
        if value is None:
            raise ValueError(f"DocumentExecutionRuntime requires dependency '{name}'.")
        return value

    @staticmethod
    def _noop_persist_field_results_artifact(**_kwargs) -> tuple[str, str]:
        return "", ""

    def __init__(
        self,
        *,
        build_stream_router: BuildStreamRouter | None = None,
        cached_extraction_restore_runtime: Any = None,
        normalize_soft_warnings: Any = None,
        promote_visual_diagnostics: Any = None,
        persist_assistant_payload_artifact: Any = None,
        persist_field_results_artifact: Any = None,
        extraction_result_factory: Any = None,
        document_response_factory: Any = None,
        save_extraction_result: SaveExtractionResult | None = None,
        dependency_bundle: DocumentExecutionDependencyBundle | None = None,
    ) -> None:
        bundle = dependency_bundle or DocumentExecutionDependencyBundle(
            build_stream_router=self._require_dependency("build_stream_router", build_stream_router),
            cached_extraction_restore_runtime=self._require_dependency(
                "cached_extraction_restore_runtime",
                cached_extraction_restore_runtime,
            ),
            normalize_soft_warnings=self._require_dependency("normalize_soft_warnings", normalize_soft_warnings),
            promote_visual_diagnostics=self._require_dependency(
                "promote_visual_diagnostics",
                promote_visual_diagnostics,
            ),
            persist_assistant_payload_artifact=self._require_dependency(
                "persist_assistant_payload_artifact",
                persist_assistant_payload_artifact,
            ),
            extraction_result_factory=self._require_dependency(
                "extraction_result_factory",
                extraction_result_factory,
            ),
            document_response_factory=self._require_dependency(
                "document_response_factory",
                document_response_factory,
            ),
            save_extraction_result=self._require_dependency("save_extraction_result", save_extraction_result),
            persist_field_results_artifact=(
                persist_field_results_artifact
                if callable(persist_field_results_artifact)
                else self._noop_persist_field_results_artifact
            ),
        )
        self._build_stream_router = bundle.build_stream_router
        self._cached_extraction_restore_runtime = bundle.cached_extraction_restore_runtime
        self._normalize_soft_warnings = bundle.normalize_soft_warnings
        self._promote_visual_diagnostics = bundle.promote_visual_diagnostics
        self._persist_assistant_payload_artifact = bundle.persist_assistant_payload_artifact
        self._persist_field_results_artifact = (
            bundle.persist_field_results_artifact
            if callable(bundle.persist_field_results_artifact)
            else self._noop_persist_field_results_artifact
        )
        self._extraction_result_factory = bundle.extraction_result_factory
        self._document_response_factory = bundle.document_response_factory
        self._save_extraction_result = bundle.save_extraction_result

    @staticmethod
    def build_progress_emitter(progress_hook: ProgressHook) -> EmitProgress:
        async def _emit_progress(
            stage: str,
            ratio: float,
            message: str = "",
            extra: Optional[Dict[str, Any]] = None,
        ) -> None:
            if progress_hook is None:
                return
            try:
                await progress_hook(
                    str(stage or "").strip() or "running",
                    max(0.0, min(1.0, float(ratio))),
                    str(message or "").strip(),
                    dict(extra or {}),
                )
            except Exception:
                return

        return _emit_progress

    def _should_bypass_cache_restore(self, cached_payload: Dict[str, Any]) -> bool:
        allow_degraded_restore = str(
            os.getenv("MODULE2_ALLOW_DEGRADED_CACHE_RESTORE", "false") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        if allow_degraded_restore:
            return False

        diagnostics_raw = cached_payload.get("diagnostics", cached_payload.get("metrics", {}))
        diagnostics = (
            self._promote_visual_diagnostics(dict(diagnostics_raw))
            if isinstance(diagnostics_raw, dict)
            else {}
        )
        quality_status = str(diagnostics.get("quality_status") or "").strip().lower()
        if quality_status == "degraded":
            return True

        quality_reasons = diagnostics.get("quality_reasons")
        if isinstance(quality_reasons, list):
            for item in quality_reasons:
                reason = str(item or "").strip().lower()
                if reason.startswith("low_coverage") or reason.startswith("low_confidence"):
                    return True

        normalized_warnings = self._normalize_soft_warnings(cached_payload.get("soft_warnings", []))
        warning_texts = [str(item or "").strip().lower() for item in normalized_warnings if str(item or "").strip()]
        retryable_markers = (
            "quality_gate_degraded",
            "table_extract_timeout",
            "field_extract_timeout",
            "table_extract_error:rate_limited_retryable",
            "field_extract_error:rate_limited_retryable",
            "table_extract_error:upstream_retryable",
            "field_extract_error:upstream_retryable",
        )
        if any(any(text.startswith(marker) for marker in retryable_markers) for text in warning_texts):
            return True

        return False

    async def start(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        schema: Dict[str, Any] | None = None,
        schema_hash: str,
        progress_hook: ProgressHook = None,
    ) -> DocumentExecutionStart:
        emit_progress = self.build_progress_emitter(progress_hook)
        router = self._build_stream_router()
        resolved_schema = schema if isinstance(schema, dict) else {}
        triage = getattr(router, "triage")
        try:
            decision = await triage(
                file_name,
                file_bytes,
                schema_hash,
                schema=resolved_schema,
            )
        except TypeError as exc:
            if "schema" not in str(exc):
                raise
            decision = await triage(file_name, file_bytes, schema_hash)

        if decision.cached_payload is not None:
            cached_payload = dict(decision.cached_payload)
            if getattr(decision, "cache_lookup_mode", "") == "compatible_auto":
                cached_payload = self._build_compatible_cache_alias_payload(
                    cached_payload=cached_payload,
                    file_name=file_name,
                    file_hash=decision.file_hash,
                    schema_hash=schema_hash,
                    cache_key=decision.cache_key,
                )
                try:
                    await self._save_extraction_result(decision.cache_key, cached_payload)
                except Exception:
                    pass

            if self._should_bypass_cache_restore(cached_payload):
                await emit_progress(
                    "cached",
                    0.08,
                    "Cache hit is degraded/retryable, bypassing restore and re-running extraction",
                )
            else:
                await emit_progress("cached", 1.0, "Cache hit, restoring extraction result")
                cached_response = self._cached_extraction_restore_runtime.restore_response(
                    file_name=file_name,
                    file_hash=decision.file_hash,
                    default_track=decision.track,
                    cached_payload=cached_payload,
                    normalize_soft_warnings=self._normalize_soft_warnings,
                    promote_visual_diagnostics=self._promote_visual_diagnostics,
                    persist_assistant_payload_artifact=self._persist_assistant_payload_artifact,
                    persist_field_results_artifact=self._persist_field_results_artifact,
                    extraction_result_factory=self._extraction_result_factory,
                    document_response_factory=self._document_response_factory,
                )
                return DocumentExecutionStart(
                    decision=decision,
                    emit_progress=emit_progress,
                    cached_response=cached_response,
                )

        await emit_progress("preflight", 0.05, "File received, running preflight checks")
        return DocumentExecutionStart(
            decision=decision,
            emit_progress=emit_progress,
            cached_response=None,
        )

    @staticmethod
    def _build_compatible_cache_alias_payload(
        *,
        cached_payload: Dict[str, Any],
        file_name: str,
        file_hash: str,
        schema_hash: str,
        cache_key: str,
    ) -> Dict[str, Any]:
        aliased_payload = dict(cached_payload)
        aliased_payload["file_name"] = file_name
        aliased_payload["file_hash"] = file_hash
        aliased_payload["schema_hash"] = schema_hash
        aliased_payload["cache_key"] = cache_key
        aliased_payload["cached"] = True

        diagnostics = aliased_payload.get("diagnostics")
        if isinstance(diagnostics, dict):
            next_diagnostics = dict(diagnostics)
            next_diagnostics["cache_restore_mode"] = "compatible_auto_schema"
            next_diagnostics["cache_restored_from_schema_hash"] = str(cached_payload.get("schema_hash", "") or "")
            next_diagnostics["cache_restored_from_cache_key"] = str(cached_payload.get("cache_key", "") or "")
            aliased_payload["diagnostics"] = next_diagnostics
            aliased_payload["metrics"] = next_diagnostics
        return aliased_payload

    async def finalize_success(
        self,
        *,
        cache_key: str,
        response_bundle: Any,
        emit_progress: EmitProgress,
    ) -> Any:
        await self._save_extraction_result(
            cache_key,
            getattr(response_bundle, "cache_payload", {}),
        )
        await emit_progress("completed", 1.0, "Extraction completed")
        return getattr(response_bundle, "response", None)


class DocumentWorkflowRuntime:
    """Coordinate the top-level single-document workflow across existing runtimes."""

    def __init__(
        self,
        *,
        document_execution_runtime,
        document_pipeline_runtime,
        document_postprocess_runtime,
        perf_counter: Callable[[], float] = time.perf_counter,
        finalizing_progress_message: str = "Extraction completed, finalizing result and cache",
    ) -> None:
        self._document_execution_runtime = document_execution_runtime
        self._document_pipeline_runtime = document_pipeline_runtime
        self._document_postprocess_runtime = document_postprocess_runtime
        self._perf_counter = perf_counter
        self._finalizing_progress_message = finalizing_progress_message

    async def execute(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        schema: Dict[str, Any],
        schema_hash: str,
        max_retries: int,
        progress_hook: Optional[Any] = None,
    ) -> Any:
        started_at_sec = self._perf_counter()
        execution_start = await self._document_execution_runtime.start(
            file_name=file_name,
            file_bytes=file_bytes,
            schema=schema,
            schema_hash=schema_hash,
            progress_hook=progress_hook,
        )
        if execution_start.cached_response is not None:
            return execution_start.cached_response

        decision = execution_start.decision
        emit_progress = execution_start.emit_progress
        pipeline_outcome = await self._document_pipeline_runtime.execute(
            file_name=file_name,
            file_bytes=file_bytes,
            file_hash=decision.file_hash,
            requested_schema=schema,
            max_retries=max_retries,
            initial_track=decision.track,
            started_at_sec=started_at_sec,
            emit_progress=emit_progress,
        )
        await emit_progress("finalizing", 0.96, self._finalizing_progress_message)
        total_ms = int((self._perf_counter() - started_at_sec) * 1000)
        response_bundle = self._document_postprocess_runtime.build_pipeline_response_bundle(
            file_name=file_name,
            file_hash=decision.file_hash,
            schema_hash=schema_hash,
            cache_key=decision.cache_key,
            total_ms=total_ms,
            pipeline_outcome=pipeline_outcome,
        )
        return await self._document_execution_runtime.finalize_success(
            cache_key=decision.cache_key,
            response_bundle=response_bundle,
            emit_progress=emit_progress,
        )
