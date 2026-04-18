from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .foundation import build_module2_default_bootstrap_components

MODULE2_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_MODULE2_ENV_FILE = str(os.getenv("MODULE2_ENV_FILE", "") or "").strip()

# Always load Module 2's own env file so uvicorn startup from repo root
# does not silently miss module-specific runtime settings.
load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)
if CUSTOM_MODULE2_ENV_FILE:
    load_dotenv(dotenv_path=CUSTOM_MODULE2_ENV_FILE, override=True)

logger = logging.getLogger(__name__)
_module2_bootstrap_components = build_module2_default_bootstrap_components(
    logger=logger,
    module2_root=MODULE2_ROOT,
)

# Keep subprocess worker entrypoints while preserving `app/create_app` as the
# canonical public composition surface.
_module2_main_entry_bundle = _module2_bootstrap_components.entry_bundle
_module2_http_runtime_bundle = _module2_bootstrap_components.foundation_bundle.http_runtime_bundle
_extraction_request_runtime = _module2_http_runtime_bundle.extraction_request_runtime

CORS_ORIGINS = _module2_bootstrap_components.foundation_bundle.platform_bundle.cors_origins
CORS_ALLOW_ALL = _module2_bootstrap_components.foundation_bundle.platform_bundle.cors_allow_all


async def extract_batch(
    *,
    request: Any = None,
    files: Sequence[UploadFile],
    schema_form: str,
    tenant_id: str = "",
) -> Any:
    """Subprocess worker entrypoint for module2 batch extraction."""

    return await _extraction_request_runtime.extract_batch(
        request=request,
        files=files,
        schema_form=schema_form,
        tenant_id=tenant_id,
    )


async def extract_cache_clear(scope: str = "results", tenant_id: str = "") -> Any:
    """Subprocess worker entrypoint for module2 cache clear."""

    return await _module2_main_entry_bundle.module2_app_callback_bundle.clear_cache_request(
        scope,
        tenant_id=tenant_id,
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="A23 Module 2 - Unstructured Document Extraction",
        version="1.0.0",
        lifespan=_module2_main_entry_bundle.lifespan(),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if CORS_ALLOW_ALL else CORS_ORIGINS,
        allow_credentials=not CORS_ALLOW_ALL,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _module2_main_entry_bundle.register_app(app)
    return app


app = create_app()


__all__ = [
    "CORS_ALLOW_ALL",
    "CORS_ORIGINS",
    "app",
    "create_app",
]
