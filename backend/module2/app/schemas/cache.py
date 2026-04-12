from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field


class CacheClearResponse(BaseModel):
    ok: bool = True
    message: str
    scope: str = "results"
    cache_counts: Dict[str, int] = Field(default_factory=dict)
    removed_artifacts: int = 0
    removed_runtime_models: int = 0
    removed_materialized: Dict[str, int] = Field(default_factory=dict)
    process_pool_reset_generation: int = 0

