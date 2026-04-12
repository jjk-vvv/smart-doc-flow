from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_extraction_bundle_module = import_module("module2.app.bootstrap.extraction")


class _GraphStub:
    def diagnostics(self):
        return {
            "prompt_version": "prompt-v1",
            "prompt_versions": {"extract": "prompt-v1"},
        }


async def _unused_check_cache(cache_key: str):
    return None


async def _unused_find_recent_document_caches(file_hash: str):
    return []


def _unused_schema_target_fields(schema: dict):
    return schema.get("fields", {}) if isinstance(schema, dict) else {}


async def _enter_slots(bundle) -> None:
    async with bundle.acquire_parse_execution_slots("VisualTrack"):
        return None


def test_build_module2_main_extraction_bundle_exposes_expected_runtime_fields() -> None:
    bundle = main_extraction_bundle_module.build_module2_main_extraction_bundle(
        module2_root=Path("backend/module2"),
        check_cache=_unused_check_cache,
        find_recent_document_caches=_unused_find_recent_document_caches,
        graph=_GraphStub(),
        getenv=lambda name, default=None: default,
        bounded_env_int=lambda *args, **kwargs: 2,
        schema_target_fields=_unused_schema_target_fields,
        field_naming_version="field-v1",
        schema_rule_versions={"schema": "v1"},
        auto_schema_logic_revision="auto-v1",
        fingerprint_files=("app/main.py",),
    )

    assert bundle.extraction_cache_version == "20260318-strict-visual-chain-v1"
    assert len(bundle.runtime_code_fingerprint) == 20
    assert bundle.current_extraction_logic_components()["field_naming_version"] == "field-v1"
    assert bundle.current_extraction_logic_version()
    assert bundle.current_extraction_cache_version().startswith("20260318-strict-visual-chain-v1:")
    assert bundle.build_stream_router() is not None
    asyncio.run(_enter_slots(bundle))
