from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


BuildProvider = Callable[[float], Any]
BuildWarmupPdfBytes = Callable[[], bytes]
RunParseInProcessPool = Callable[..., Awaitable[Any]]
GetEnv = Callable[[str, str], str]
BoundedEnvInt = Callable[..., int]
RaiseUnavailable = Callable[[Exception], Exception]


class Module2BootstrapRuntime:
    """Coordinate provider preflight, MinerU warmup, and related health snapshots."""

    def __init__(
        self,
        *,
        provider_preflight_runtime: Any,
        mineru_warmup_runtime: Any,
        logger: Any,
        getenv: GetEnv,
        bounded_env_int: BoundedEnvInt,
        max_workers_provider: Callable[[], int],
    ) -> None:
        self._provider_preflight_runtime = provider_preflight_runtime
        self._mineru_warmup_runtime = mineru_warmup_runtime
        self._logger = logger
        self._getenv = getenv
        self._bounded_env_int = bounded_env_int
        self._max_workers_provider = max_workers_provider

    def provider_healthcheck_on_job_create(self) -> bool:
        return self._bool_env("MODULE2_PROVIDER_HEALTHCHECK_ON_JOB_CREATE", "true")

    def fail_on_provider_unavailable(self) -> bool:
        return self._bool_env("MODULE2_FAIL_ON_PROVIDER_UNAVAILABLE", "true")

    def provider_healthcheck_ttl_sec(self) -> float:
        return max(5.0, float(self._getenv("MODULE2_PROVIDER_HEALTHCHECK_TTL_SEC", "120")))

    def provider_healthcheck_timeout_sec(self) -> float:
        return max(5.0, float(self._getenv("MODULE2_PROVIDER_HEALTHCHECK_TIMEOUT_SEC", "20")))

    def provider_preflight_on_startup(self) -> bool:
        return self._bool_env("MODULE2_PROVIDER_PREFLIGHT_ON_STARTUP", "true")

    def mineru_warmup_enabled(self) -> bool:
        return self._bool_env("MODULE2_MINERU_WARMUP_ENABLE", "false")

    def mineru_warmup_delay_sec(self) -> float:
        return max(0.0, float(self._getenv("MODULE2_MINERU_WARMUP_DELAY_SEC", "1.5")))

    def mineru_warmup_timeout_sec(self) -> float:
        return max(30.0, float(self._getenv("MODULE2_MINERU_WARMUP_TIMEOUT_SEC", "240")))

    def mineru_warmup_worker_count(self) -> int:
        return self._bounded_env_int(
            "MODULE2_MINERU_WARMUP_WORKERS",
            1,
            minimum=1,
            maximum=max(1, min(4, self._max_workers_provider())),
        )

    def provider_preflight_snapshot(self) -> Dict[str, Any]:
        return self._provider_preflight_runtime.snapshot()

    def provider_config_snapshot(self, *, build_provider: BuildProvider) -> Dict[str, Any]:
        return self._provider_preflight_runtime.build_config_snapshot(
            timeout_sec=self.provider_healthcheck_timeout_sec(),
            build_provider=build_provider,
        )

    def run_provider_preflight(
        self,
        *,
        force: bool,
        build_provider: BuildProvider,
    ) -> Dict[str, Any]:
        return self._provider_preflight_runtime.run_preflight(
            force=force,
            ttl_sec=self.provider_healthcheck_ttl_sec(),
            timeout_sec=self.provider_healthcheck_timeout_sec(),
            build_provider=build_provider,
        )

    async def ensure_provider_ready_for_job_create(
        self,
        *,
        build_provider: BuildProvider,
        raise_unavailable: RaiseUnavailable,
    ) -> None:
        if not self.provider_healthcheck_on_job_create():
            return
        try:
            await asyncio.to_thread(
                self.run_provider_preflight,
                force=False,
                build_provider=build_provider,
            )
        except Exception as exc:
            self._logger.warning("module2 provider preflight failed: %s: %s", type(exc).__name__, exc)
            if self.fail_on_provider_unavailable():
                raise raise_unavailable(exc) from exc

    def mineru_warmup_snapshot(self) -> Dict[str, Any]:
        return self._mineru_warmup_runtime.snapshot()

    @staticmethod
    def build_mineru_warmup_pdf_bytes() -> bytes:
        import fitz  # pymupdf

        doc = fitz.open()
        try:
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 96), "Module2 MinerU warmup")
            page.insert_text((72, 124), "This document preloads MinerU runtime for the first PDF job.")
            page.insert_text((72, 152), "0123456789 alpha beta gamma")
            return bytes(doc.tobytes(garbage=4, deflate=True))
        finally:
            doc.close()

    async def startup_provider_preflight_task(self, *, build_provider: BuildProvider) -> None:
        try:
            await asyncio.to_thread(
                self.run_provider_preflight,
                force=True,
                build_provider=build_provider,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.warning(
                "module2 startup provider preflight failed: %s: %s",
                type(exc).__name__,
                exc,
            )

    async def startup_mineru_warmup_task(
        self,
        *,
        run_parse_in_process_pool: RunParseInProcessPool,
        build_warmup_pdf_bytes: BuildWarmupPdfBytes | None = None,
    ) -> None:
        enabled = self.mineru_warmup_enabled()
        worker_count = self.mineru_warmup_worker_count() if enabled else 0
        await self._mineru_warmup_runtime.startup_warmup_task(
            enabled=enabled,
            worker_count=worker_count,
            delay_sec=self.mineru_warmup_delay_sec(),
            timeout_sec=self.mineru_warmup_timeout_sec(),
            build_warmup_pdf_bytes=build_warmup_pdf_bytes or self.build_mineru_warmup_pdf_bytes,
            run_parse_in_process_pool=run_parse_in_process_pool,
        )

    def _bool_env(self, name: str, default: str) -> bool:
        return (self._getenv(name, default) or default).lower() in {"1", "true", "yes"}
