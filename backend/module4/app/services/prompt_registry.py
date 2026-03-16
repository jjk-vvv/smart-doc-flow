from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping


PROMPT_KEY_TO_ENV = {
    "entity_extraction": "MODULE4_GRAPHRAG_ENTITY_EXTRACTION_PROMPT_FILE",
    "summarize_descriptions": "MODULE4_GRAPHRAG_SUMMARIZE_DESCRIPTIONS_PROMPT_FILE",
    "claim_extraction": "MODULE4_GRAPHRAG_CLAIM_EXTRACTION_PROMPT_FILE",
    "community_report": "MODULE4_GRAPHRAG_COMMUNITY_REPORT_PROMPT_FILE",
}


@dataclass(frozen=True)
class PromptAsset:
    key: str
    filename: str
    description: str


PROMPT_ASSETS: Dict[str, PromptAsset] = {
    "entity_extraction": PromptAsset(
        key="entity_extraction",
        filename="entity_extraction.txt",
        description="Extract graph entities and relationships from Chinese long-form documents.",
    ),
    "summarize_descriptions": PromptAsset(
        key="summarize_descriptions",
        filename="summarize_descriptions.txt",
        description="Merge multiple entity descriptions into a concise Chinese summary.",
    ),
    "claim_extraction": PromptAsset(
        key="claim_extraction",
        filename="claim_extraction.txt",
        description="Extract verifiable claims and facts from Chinese reports and policy text.",
    ),
    "community_report": PromptAsset(
        key="community_report",
        filename="community_report.txt",
        description="Produce grounded JSON community reports for graph neighborhoods.",
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

        raw_override = str(self._overrides.get(key) or os.getenv(PROMPT_KEY_TO_ENV[key], "")).strip()
        candidate = Path(raw_override or asset.filename)
        if not candidate.is_absolute():
            candidate = (self.asset_root / candidate).resolve()
        return candidate

    def prompt_text(self, key: str) -> str:
        path = self.prompt_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Prompt asset not found for {key}: {path}")
        return path.read_text(encoding="utf-8")

    def manifest(self) -> Dict[str, str]:
        return {key: str(self.prompt_path(key)) for key in self.keys()}

    def materialize(self, destination_dir: Path) -> Dict[str, Path]:
        destination_dir = destination_dir.resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)

        copied: Dict[str, Path] = {}
        for key in self.keys():
            source = self.prompt_path(key)
            if not source.exists():
                raise FileNotFoundError(f"Prompt asset not found for {key}: {source}")
            target = destination_dir / source.name
            shutil.copyfile(source, target)
            copied[key] = target
        return copied
