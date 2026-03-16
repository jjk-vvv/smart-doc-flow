from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .prompt_registry import PROMPT_KEY_TO_ENV


def _resolve_path(module4_root: Path, raw_value: str, default_rel: str) -> Path:
    text = str(raw_value or default_rel).strip()
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = (module4_root / candidate).resolve()
    return candidate


def _csv_list(raw_value: str, fallback: List[str]) -> List[str]:
    items = [item.strip() for item in str(raw_value or "").split(",") if item.strip()]
    return items or list(fallback)


@dataclass(frozen=True)
class GraphRAGRuntimeSettings:
    module4_root: Path
    workspaces_root: Path
    prompt_assets_root: Path
    api_base: str
    chat_api_key: str
    chat_model: str
    embedding_api_key: str
    embedding_model: str
    input_dir: str = "input"
    cache_dir: str = "cache"
    storage_dir: str = "output/${timestamp}/artifacts"
    reporting_dir: str = "output/${timestamp}/reports"
    entity_types: List[str] = field(
        default_factory=lambda: [
            "organization",
            "person",
            "geo",
            "event",
            "policy",
            "indicator",
            "facility",
            "material",
            "project",
            "agreement",
        ]
    )
    entity_extraction_prompt_file: str = "entity_extraction.txt"
    summarize_descriptions_prompt_file: str = "summarize_descriptions.txt"
    claim_extraction_prompt_file: str = "claim_extraction.txt"
    community_report_prompt_file: str = "community_report.txt"
    max_tokens: int = 4000
    chunk_size: int = 1200
    chunk_overlap: int = 100
    cluster_max_size: int = 10
    utils_port: int = 8012

    @classmethod
    def from_env(cls, module4_root: Path | None = None) -> "GraphRAGRuntimeSettings":
        root = (module4_root or Path(__file__).resolve().parents[2]).resolve()
        return cls(
            module4_root=root,
            workspaces_root=_resolve_path(
                root,
                os.getenv("MODULE4_GRAPHRAG_WORKSPACES_ROOT", ""),
                "workspaces",
            ),
            prompt_assets_root=_resolve_path(
                root,
                os.getenv("MODULE4_GRAPHRAG_PROMPTS_ROOT", ""),
                "assets/prompts",
            ),
            api_base=str(os.getenv("MODULE4_GRAPHRAG_API_BASE", os.getenv("GRAPHRAG_API_BASE", "")) or "").strip(),
            chat_api_key=str(
                os.getenv("MODULE4_GRAPHRAG_CHAT_API_KEY", os.getenv("GRAPHRAG_CHAT_API_KEY", "")) or ""
            ).strip(),
            chat_model=str(
                os.getenv("MODULE4_GRAPHRAG_CHAT_MODEL", os.getenv("GRAPHRAG_CHAT_MODEL", "qwen-turbo")) or "qwen-turbo"
            ).strip()
            or "qwen-turbo",
            embedding_api_key=str(
                os.getenv("MODULE4_GRAPHRAG_EMBEDDING_API_KEY", os.getenv("GRAPHRAG_EMBEDDING_API_KEY", "")) or ""
            ).strip(),
            embedding_model=str(
                os.getenv(
                    "MODULE4_GRAPHRAG_EMBEDDING_MODEL",
                    os.getenv("GRAPHRAG_EMBEDDING_MODEL", "text-embedding-v1"),
                )
                or "text-embedding-v1"
            ).strip()
            or "text-embedding-v1",
            input_dir=str(os.getenv("MODULE4_GRAPHRAG_INPUT_DIR", "input") or "input").strip() or "input",
            cache_dir=str(os.getenv("MODULE4_GRAPHRAG_CACHE_DIR", "cache") or "cache").strip() or "cache",
            storage_dir=str(
                os.getenv("MODULE4_GRAPHRAG_STORAGE_DIR", "output/${timestamp}/artifacts")
                or "output/${timestamp}/artifacts"
            ).strip()
            or "output/${timestamp}/artifacts",
            reporting_dir=str(
                os.getenv("MODULE4_GRAPHRAG_REPORTING_DIR", "output/${timestamp}/reports")
                or "output/${timestamp}/reports"
            ).strip()
            or "output/${timestamp}/reports",
            entity_types=_csv_list(
                os.getenv("MODULE4_GRAPHRAG_ENTITY_TYPES", ""),
                [
                    "organization",
                    "person",
                    "geo",
                    "event",
                    "policy",
                    "indicator",
                    "facility",
                    "material",
                    "project",
                    "agreement",
                ],
            ),
            entity_extraction_prompt_file=str(
                os.getenv(PROMPT_KEY_TO_ENV["entity_extraction"], "entity_extraction.txt") or "entity_extraction.txt"
            ).strip()
            or "entity_extraction.txt",
            summarize_descriptions_prompt_file=str(
                os.getenv(
                    PROMPT_KEY_TO_ENV["summarize_descriptions"],
                    "summarize_descriptions.txt",
                )
                or "summarize_descriptions.txt"
            ).strip()
            or "summarize_descriptions.txt",
            claim_extraction_prompt_file=str(
                os.getenv(PROMPT_KEY_TO_ENV["claim_extraction"], "claim_extraction.txt") or "claim_extraction.txt"
            ).strip()
            or "claim_extraction.txt",
            community_report_prompt_file=str(
                os.getenv(PROMPT_KEY_TO_ENV["community_report"], "community_report.txt") or "community_report.txt"
            ).strip()
            or "community_report.txt",
            max_tokens=max(256, int(os.getenv("MODULE4_GRAPHRAG_MAX_TOKENS", "4000"))),
            chunk_size=max(200, int(os.getenv("MODULE4_GRAPHRAG_CHUNK_SIZE", "1200"))),
            chunk_overlap=max(0, int(os.getenv("MODULE4_GRAPHRAG_CHUNK_OVERLAP", "100"))),
            cluster_max_size=max(2, int(os.getenv("MODULE4_GRAPHRAG_CLUSTER_MAX_SIZE", "10"))),
            utils_port=max(1, int(os.getenv("MODULE4_GRAPHRAG_UTILS_PORT", "8012"))),
        )

    def prompt_overrides(self) -> Dict[str, str]:
        return {
            "entity_extraction": self.entity_extraction_prompt_file,
            "summarize_descriptions": self.summarize_descriptions_prompt_file,
            "claim_extraction": self.claim_extraction_prompt_file,
            "community_report": self.community_report_prompt_file,
        }

    def is_configured(self) -> bool:
        return not self.missing_fields()

    def missing_fields(self) -> List[str]:
        missing: List[str] = []
        if not self.api_base:
            missing.append("MODULE4_GRAPHRAG_API_BASE")
        if not self.chat_api_key:
            missing.append("MODULE4_GRAPHRAG_CHAT_API_KEY")
        if not self.chat_model:
            missing.append("MODULE4_GRAPHRAG_CHAT_MODEL")
        if not self.embedding_api_key:
            missing.append("MODULE4_GRAPHRAG_EMBEDDING_API_KEY")
        if not self.embedding_model:
            missing.append("MODULE4_GRAPHRAG_EMBEDDING_MODEL")
        return missing

    def workspace_env(self, prompt_paths: Dict[str, str] | None = None) -> Dict[str, str]:
        prompt_paths = dict(prompt_paths or {})
        return {
            "GRAPHRAG_API_BASE": self.api_base,
            "GRAPHRAG_CHAT_API_KEY": self.chat_api_key,
            "GRAPHRAG_CHAT_MODEL": self.chat_model,
            "GRAPHRAG_EMBEDDING_API_KEY": self.embedding_api_key,
            "GRAPHRAG_EMBEDDING_MODEL": self.embedding_model,
            "GRAPHRAG_ENTITY_EXTRACTION_PROMPT_FILE": prompt_paths.get("entity_extraction", "prompts/entity_extraction.txt"),
            "GRAPHRAG_SUMMARIZE_DESCRIPTIONS_PROMPT_FILE": prompt_paths.get(
                "summarize_descriptions",
                "prompts/summarize_descriptions.txt",
            ),
            "GRAPHRAG_CLAIM_EXTRACTION_PROMPT_FILE": prompt_paths.get("claim_extraction", "prompts/claim_extraction.txt"),
            "GRAPHRAG_COMMUNITY_REPORT_PROMPT_FILE": prompt_paths.get("community_report", "prompts/community_report.txt"),
            "GRAPHRAG_INPUT_DIR": self.input_dir,
            "GRAPHRAG_CACHE_DIR": self.cache_dir,
            "GRAPHRAG_STORAGE_DIR": self.storage_dir,
            "GRAPHRAG_REPORTING_DIR": self.reporting_dir,
            "GRAPHRAG_UTILS_PORT": str(self.utils_port),
        }
