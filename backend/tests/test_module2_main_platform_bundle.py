from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_platform_bundle_module = import_module("module2.app.bootstrap.platform")


async def _run_parse(bundle) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    return await bundle.run_parse_in_process_pool(
        loop=loop,
        file_bytes=b"pdf",
        file_name="demo.pdf",
        track="FastTrack",
        timeout_sec=1.0,
        context_label="test",
    )


def test_build_module2_main_platform_bundle_exposes_expected_platform_helpers() -> None:
    bundle = main_platform_bundle_module.build_module2_main_platform_bundle(
        logger=object(),
        provider_preflight_runtime=object(),
        mineru_warmup_runtime=object(),
        getenv=lambda name, default=None: default,
        parse_document_in_subprocess=lambda *args: {"ok": True},
        cpu_count_provider=lambda: 4,
        process_pool_factory=lambda max_workers: __import__("concurrent.futures").futures.ThreadPoolExecutor(
            max_workers=max_workers
        ),
    )

    assert bundle.cors_origins
    assert bundle.cors_allow_all is False
    assert bundle.bounded_env_int("X", 3) == 3
    assert bundle.current_process_pool() is not None
    assert asyncio.run(_run_parse(bundle)) == {"ok": True}
