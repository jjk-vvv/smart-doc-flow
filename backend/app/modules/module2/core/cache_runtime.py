from __future__ import annotations

from typing import Any

from app.modules.module2.schemas.extraction import CacheClearResponse

from .module2_request_runtime import normalize_cache_clear_scope


def merge_module2_cache_clear_payloads(
    payloads: list[dict[str, Any]],
    *,
    scope: str,
    errors: list[str],
) -> dict[str, Any]:
    merged = CacheClearResponse(
        ok=True,
        message=f"module2 cache cleared, scope={scope}",
        scope=str(scope or "results").strip() or "results",
    ).model_dump(mode="json")

    cache_counts: dict[str, int] = {}
    removed_materialized: dict[str, int] = {}
    removed_artifacts = 0
    removed_runtime_models = 0
    process_pool_reset_generation = 0
    messages: list[str] = []

    for payload in payloads:
        model_payload = CacheClearResponse.model_validate(payload).model_dump(mode="json")
        message = str(model_payload.get("message") or "").strip()
        if message:
            messages.append(message)
        for key, value in dict(model_payload.get("cache_counts") or {}).items():
            cache_counts[str(key)] = int(cache_counts.get(str(key), 0) or 0) + int(value or 0)
        for key, value in dict(model_payload.get("removed_materialized") or {}).items():
            removed_materialized[str(key)] = int(removed_materialized.get(str(key), 0) or 0) + int(value or 0)
        removed_artifacts += int(model_payload.get("removed_artifacts", 0) or 0)
        removed_runtime_models += int(model_payload.get("removed_runtime_models", 0) or 0)
        process_pool_reset_generation = max(
            process_pool_reset_generation,
            int(model_payload.get("process_pool_reset_generation", 0) or 0),
        )

    if messages:
        merged["message"] = " | ".join(messages[:3])
    if errors:
        merged["message"] = f"{merged['message']} | partial_errors={';'.join(errors[:2])}".strip()
    merged["cache_counts"] = cache_counts
    merged["removed_materialized"] = removed_materialized
    merged["removed_artifacts"] = removed_artifacts
    merged["removed_runtime_models"] = removed_runtime_models
    merged["process_pool_reset_generation"] = process_pool_reset_generation
    return merged


def merge_unified_cache_clear_payload(
    payload: dict[str, Any],
    *,
    shadow_counts: dict[str, int],
    office_preview_counts: dict[str, int],
) -> dict[str, Any]:
    merged = CacheClearResponse.model_validate(payload).model_dump(mode="json")
    cache_counts = dict(merged.get("cache_counts") or {})
    removed_materialized = dict(merged.get("removed_materialized") or {})

    cache_counts.update(
        {
            "unified_shadow_jobs_memory": int(shadow_counts.get("cleared_shadow_jobs_memory", 0) or 0),
            "unified_shadow_pollers_memory": int(shadow_counts.get("cleared_shadow_pollers_memory", 0) or 0),
            "unified_office_preview_jobs_memory": int(
                office_preview_counts.get("cleared_office_preview_jobs_memory", 0) or 0
            ),
        }
    )
    removed_materialized.update(
        {
            "removed_shadow_snapshots": int(shadow_counts.get("removed_shadow_snapshots", 0) or 0),
        }
    )

    merged["cache_counts"] = cache_counts
    merged["removed_materialized"] = removed_materialized
    merged["scope"] = normalize_cache_clear_scope(str(merged.get("scope") or "results"))
    return CacheClearResponse.model_validate(merged).model_dump(mode="json")
