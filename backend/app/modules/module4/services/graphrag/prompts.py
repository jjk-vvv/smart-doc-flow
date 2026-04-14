from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping


PROMPT_KEY_TO_ENV = {
    "extract_graph": "MODULE4_GRAPHRAG_EXTRACT_GRAPH_PROMPT_FILE",
    "summarize_descriptions": "MODULE4_GRAPHRAG_SUMMARIZE_DESCRIPTIONS_PROMPT_FILE",
    "extract_claims": "MODULE4_GRAPHRAG_EXTRACT_CLAIMS_PROMPT_FILE",
    "community_report_graph": "MODULE4_GRAPHRAG_COMMUNITY_REPORT_GRAPH_PROMPT_FILE",
    "community_report_text": "MODULE4_GRAPHRAG_COMMUNITY_REPORT_TEXT_PROMPT_FILE",
    "local_search_system_prompt": "MODULE4_GRAPHRAG_LOCAL_SEARCH_PROMPT_FILE",
    "global_search_map_system_prompt": "MODULE4_GRAPHRAG_GLOBAL_SEARCH_MAP_PROMPT_FILE",
    "global_search_reduce_system_prompt": "MODULE4_GRAPHRAG_GLOBAL_SEARCH_REDUCE_PROMPT_FILE",
    "global_search_knowledge_system_prompt": "MODULE4_GRAPHRAG_GLOBAL_SEARCH_KNOWLEDGE_PROMPT_FILE",
    "drift_search_system_prompt": "MODULE4_GRAPHRAG_DRIFT_SEARCH_PROMPT_FILE",
    "drift_reduce_prompt": "MODULE4_GRAPHRAG_DRIFT_REDUCE_PROMPT_FILE",
    "basic_search_system_prompt": "MODULE4_GRAPHRAG_BASIC_SEARCH_PROMPT_FILE",
    "question_gen_system_prompt": "MODULE4_GRAPHRAG_QUESTION_GEN_PROMPT_FILE",
}


@dataclass(frozen=True)
class PromptAsset:
    key: str
    filename: str
    description: str


PROMPT_ASSETS: Dict[str, PromptAsset] = {
    "extract_graph": PromptAsset(
        key="extract_graph",
        filename="extract_graph.txt",
        description="GraphRAG native extract_graph prompt.",
    ),
    "summarize_descriptions": PromptAsset(
        key="summarize_descriptions",
        filename="summarize_descriptions.txt",
        description="GraphRAG native summarize_descriptions prompt.",
    ),
    "extract_claims": PromptAsset(
        key="extract_claims",
        filename="extract_claims.txt",
        description="GraphRAG native extract_claims prompt.",
    ),
    "community_report_graph": PromptAsset(
        key="community_report_graph",
        filename="community_report_graph.txt",
        description="GraphRAG native community_report graph prompt.",
    ),
    "community_report_text": PromptAsset(
        key="community_report_text",
        filename="community_report_text.txt",
        description="GraphRAG native community_report text prompt.",
    ),
    "local_search_system_prompt": PromptAsset(
        key="local_search_system_prompt",
        filename="local_search_system_prompt.txt",
        description="GraphRAG native local_search system prompt.",
    ),
    "global_search_map_system_prompt": PromptAsset(
        key="global_search_map_system_prompt",
        filename="global_search_map_system_prompt.txt",
        description="GraphRAG native global_search map prompt.",
    ),
    "global_search_reduce_system_prompt": PromptAsset(
        key="global_search_reduce_system_prompt",
        filename="global_search_reduce_system_prompt.txt",
        description="GraphRAG native global_search reduce prompt.",
    ),
    "global_search_knowledge_system_prompt": PromptAsset(
        key="global_search_knowledge_system_prompt",
        filename="global_search_knowledge_system_prompt.txt",
        description="GraphRAG native global_search knowledge prompt.",
    ),
    "drift_search_system_prompt": PromptAsset(
        key="drift_search_system_prompt",
        filename="drift_search_system_prompt.txt",
        description="GraphRAG native drift_search system prompt.",
    ),
    "drift_reduce_prompt": PromptAsset(
        key="drift_reduce_prompt",
        filename="drift_search_reduce_prompt.txt",
        description="GraphRAG native drift_search reduce prompt.",
    ),
    "basic_search_system_prompt": PromptAsset(
        key="basic_search_system_prompt",
        filename="basic_search_system_prompt.txt",
        description="GraphRAG native basic_search system prompt.",
    ),
    "question_gen_system_prompt": PromptAsset(
        key="question_gen_system_prompt",
        filename="question_gen_system_prompt.txt",
        description="GraphRAG native question generation system prompt.",
    ),
}


def _module4_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_prompt_root() -> Path:
    raw = str(os.getenv("MODULE4_GRAPHRAG_PROMPTS_ROOT", "assets/prompts") or "").strip()
    prompt_root = Path(raw)
    if not prompt_root.is_absolute():
        prompt_root = (_module4_root() / prompt_root).resolve()
    return prompt_root


class PromptRegistry:
    def __init__(self, asset_root: Path | None = None, overrides: Mapping[str, str] | None = None) -> None:
        self.asset_root = (asset_root or _default_prompt_root()).resolve()
        self._overrides = dict(overrides or {})

    def keys(self) -> Iterable[str]:
        return PROMPT_ASSETS.keys()

    def prompt_path(self, key: str) -> Path:
        asset = PROMPT_ASSETS.get(key)
        if asset is None:
            raise KeyError(f"Unknown prompt asset: {key}")

        raw_override = str(self._overrides.get(key) or "").strip()
        if not raw_override:
            raw_override = str(os.getenv(PROMPT_KEY_TO_ENV[key], "")).strip()
        candidate = Path(raw_override or asset.filename)
        if not candidate.is_absolute():
            candidate = (self.asset_root / candidate).resolve()
        return candidate

    def prompt_text(self, key: str) -> str:
        path = self.prompt_path(key)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise FileNotFoundError(f"Prompt asset not found for {key}: {path}")

    def manifest(self) -> Dict[str, str]:
        return {key: str(self.prompt_path(key)) for key in self.keys()}

    def materialize(self, destination_dir: Path) -> Dict[str, Path]:
        destination_dir = destination_dir.resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)

        copied: Dict[str, Path] = {}
        for key in self.keys():
            source = self.prompt_path(key)
            target = destination_dir / source.name
            try:
                shutil.copyfile(source, target)
            except FileNotFoundError:
                raise FileNotFoundError(f"Prompt asset not found for {key}: {source}")
            copied[key] = target
        return copied
