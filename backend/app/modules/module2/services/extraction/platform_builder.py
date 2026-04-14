from __future__ import annotations

"""Platform bundle builders for module2 extraction service layer."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import os
from typing import Any, Awaitable, Callable, List, Optional

from .support_builder import Module2BootstrapRuntimeBundle, build_module2_bootstrap_runtime_bundle


BuildPoolFn = Callable[[], Any]
ParseDocumentInSubprocessFn = Callable[..., Any]
GetEnvFn = Callable[[str, str | None], str | None]


@dataclass(frozen=True)
class Module2MainPlatformBundle:
    cors_origins: List[str]
    cors_allow_all: bool
    bounded_env_int: Callable[..., int]
    document_process_pool_runtime: Any
    module2_bootstrap_runtime: Any
    current_process_pool: Callable[[], Any]
    reset_process_pool: Callable[[str], int]
    shutdown_process_pool: Callable[[Any, str], None]
    run_parse_in_process_pool: Callable[..., Awaitable[Any]]


def build_module2_main_platform_bundle(
    *,
    logger: Any,
    provider_preflight_runtime: Any,
    mineru_warmup_runtime: Any,
    getenv: GetEnvFn,
    parse_document_in_subprocess: ParseDocumentInSubprocessFn,
    cpu_count_provider: Callable[[], Optional[int]] = os.cpu_count,
    process_pool_factory: Callable[[int], Any] = ProcessPoolExecutor,
) -> Module2MainPlatformBundle:
    def _cors_origins() -> tuple[List[str], bool]:
        raw = getenv(
            "MODULE2_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3002,http://127.0.0.1:3002,http://localhost:5173,http://127.0.0.1:5173,http://localhost:19006,http://127.0.0.1:19006,http://localhost:19007,http://127.0.0.1:19007,http://localhost:19008,http://127.0.0.1:19008",
        )
        origins = [item.strip() for item in str(raw or "").split(",") if item.strip()]
        if not origins:
            origins = ["http://localhost:3000"]
        allow_all = "*" in origins
        return origins, allow_all

    def _max_workers() -> int:
        cpu = cpu_count_provider() or 4
        return min(max(cpu - 1, 2), 8)

    def _bounded_env_int(
        name: str,
        default: int,
        *,
        minimum: int = 1,
        maximum: int = 8,
    ) -> int:
        raw = getenv(name, str(default))
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _build_process_pool() -> Any:
        return process_pool_factory(_max_workers())

    bootstrap_runtime_bundle: Module2BootstrapRuntimeBundle = build_module2_bootstrap_runtime_bundle(
        logger=logger,
        provider_preflight_runtime=provider_preflight_runtime,
        mineru_warmup_runtime=mineru_warmup_runtime,
        getenv=getenv,
        bounded_env_int=_bounded_env_int,
        max_workers_provider=_max_workers,
        build_pool=_build_process_pool,
        parse_document_in_subprocess=parse_document_in_subprocess,
    )
    document_process_pool_runtime = bootstrap_runtime_bundle.document_process_pool_runtime
    module2_bootstrap_runtime = bootstrap_runtime_bundle.module2_bootstrap_runtime
    cors_origins, cors_allow_all = _cors_origins()

    def _shutdown_process_pool(pool: Any, reason: str) -> None:
        document_process_pool_runtime.shutdown_pool(pool, reason=reason)

    def _current_process_pool() -> Any:
        return document_process_pool_runtime.current_pool()

    def _reset_process_pool(reason: str) -> int:
        return document_process_pool_runtime.reset_pool(reason)

    async def _run_parse_in_process_pool(
        *,
        loop,
        file_bytes: bytes,
        file_name: str,
        track: str,
        timeout_sec: float,
        context_label: str,
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Any:
        return await document_process_pool_runtime.run_parse_in_pool(
            loop=loop,
            file_bytes=file_bytes,
            file_name=file_name,
            track=track,
            timeout_sec=timeout_sec,
            context_label=context_label,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
        )

    return Module2MainPlatformBundle(
        cors_origins=cors_origins,
        cors_allow_all=cors_allow_all,
        bounded_env_int=_bounded_env_int,
        document_process_pool_runtime=document_process_pool_runtime,
        module2_bootstrap_runtime=module2_bootstrap_runtime,
        current_process_pool=_current_process_pool,
        reset_process_pool=_reset_process_pool,
        shutdown_process_pool=_shutdown_process_pool,
        run_parse_in_process_pool=_run_parse_in_process_pool,
    )
