from __future__ import annotations

import sys
from pathlib import Path


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.prompt_registry import PROMPT_ASSETS, PromptRegistry


def test_prompt_registry_loads_repo_assets() -> None:
    registry = PromptRegistry(asset_root=MODULE4_DIR / "assets" / "prompts")

    assert set(registry.keys()) == set(PROMPT_ASSETS.keys())

    entity_text = registry.prompt_text("entity_extraction")
    assert "统计公报" in entity_text
    assert "{input_text}" in entity_text
    assert "{completion_delimiter}" in entity_text

    community_text = registry.prompt_text("community_report")
    assert "json.loads" in community_text
    assert "{input_text}" in community_text


def test_prompt_registry_manifest_uses_absolute_paths() -> None:
    registry = PromptRegistry(asset_root=MODULE4_DIR / "assets" / "prompts")
    manifest = registry.manifest()

    assert manifest["entity_extraction"].endswith("entity_extraction.txt")
    assert Path(manifest["claim_extraction"]).is_absolute()
