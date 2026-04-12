from __future__ import annotations

import sys
from pathlib import Path


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag.prompts import PROMPT_ASSETS, PromptRegistry


def test_prompt_registry_loads_repo_assets() -> None:
    registry = PromptRegistry(asset_root=MODULE4_DIR / "assets" / "prompts")

    assert set(registry.keys()) == set(PROMPT_ASSETS.keys())

    extract_graph_text = registry.prompt_text("extract_graph")
    assert "Given a text document" in extract_graph_text
    assert "{input_text}" in extract_graph_text
    assert "{entity_types}" in extract_graph_text

    community_graph_text = registry.prompt_text("community_report_graph")
    assert "Return output as a well-formed JSON-formatted string" in community_graph_text
    assert "{input_text}" in community_graph_text

    community_text_text = registry.prompt_text("community_report_text")
    assert '"date_range"' in community_text_text
    assert "{max_report_length}" in community_text_text

    local_search_text = registry.prompt_text("local_search_system_prompt")
    assert "---Role---" in local_search_text
    assert "{context_data}" in local_search_text
    assert "{response_type}" in local_search_text

    global_map_text = registry.prompt_text("global_search_map_system_prompt")
    assert '"points"' in global_map_text
    assert "{max_length}" in global_map_text

    drift_text = registry.prompt_text("drift_search_system_prompt")
    assert "{global_query}" in drift_text
    assert "{followups}" in drift_text

    basic_text = registry.prompt_text("basic_search_system_prompt")
    assert "{context_data}" in basic_text
    assert "{response_type}" in basic_text


def test_prompt_registry_manifest_uses_absolute_paths() -> None:
    registry = PromptRegistry(asset_root=MODULE4_DIR / "assets" / "prompts")
    manifest = registry.manifest()

    assert manifest["extract_graph"].endswith("extract_graph.txt")
    assert Path(manifest["extract_claims"]).is_absolute()
    assert manifest["local_search_system_prompt"].endswith("local_search_system_prompt.txt")
    assert manifest["question_gen_system_prompt"].endswith("question_gen_system_prompt.txt")
