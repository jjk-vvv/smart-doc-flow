from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def clear_unified_backend_caches():
    from app.core.config import get_settings
    from app.core.env import load_managed_env_files
    from app.modules.assistant.service import get_assistant_service
    from app.modules.auth.service import get_auth_service
    from app.modules.extraction.artifact_runtime import get_extraction_artifact_runtime
    from app.modules.extraction.assistant1_runtime import get_assistant1_facade
    from app.modules.extraction.config import get_extraction_settings
    from app.modules.extraction.module2_execution_facade import get_module2_execution_facade
    from app.modules.extraction.module2_sidecar_runtime import (
        clear_module2_upstream_resolution_cache,
        get_module2_sidecar_manager,
    )
    from app.modules.extraction.service import get_extraction_service
    from app.modules.gateway.module4_sidecar_runtime import (
        clear_module4_upstream_resolution_cache,
        get_module4_sidecar_manager,
        get_module4_sidecar_settings,
    )

    load_managed_env_files.cache_clear()
    get_settings.cache_clear()
    asyncio.run(get_auth_service().shutdown())
    get_auth_service.cache_clear()
    get_assistant_service.cache_clear()
    get_assistant1_facade.cache_clear()
    get_module2_execution_facade.cache_clear()
    get_module2_sidecar_manager().shutdown_started_process(wait_timeout_sec=0.5)
    get_module2_sidecar_manager.cache_clear()
    clear_module2_upstream_resolution_cache()
    get_module4_sidecar_manager().shutdown_started_process(wait_timeout_sec=0.5)
    get_module4_sidecar_manager.cache_clear()
    get_module4_sidecar_settings.cache_clear()
    clear_module4_upstream_resolution_cache()
    get_extraction_settings.cache_clear()
    get_extraction_service.cache_clear()
    get_extraction_artifact_runtime().clear_office_preview_runtime_state()
    yield
    load_managed_env_files.cache_clear()
    get_settings.cache_clear()
    asyncio.run(get_auth_service().shutdown())
    get_auth_service.cache_clear()
    get_assistant_service.cache_clear()
    get_assistant1_facade.cache_clear()
    get_module2_execution_facade.cache_clear()
    get_module2_sidecar_manager().shutdown_started_process(wait_timeout_sec=0.5)
    get_module2_sidecar_manager.cache_clear()
    clear_module2_upstream_resolution_cache()
    get_module4_sidecar_manager().shutdown_started_process(wait_timeout_sec=0.5)
    get_module4_sidecar_manager.cache_clear()
    get_module4_sidecar_settings.cache_clear()
    clear_module4_upstream_resolution_cache()
    get_extraction_settings.cache_clear()
    get_extraction_service.cache_clear()
    get_extraction_artifact_runtime().clear_office_preview_runtime_state()
