from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse, urlunparse

from .prompts import PROMPT_KEY_TO_ENV
from .runtime_selection import choose_graphrag_python_bin, resolve_graphrag_config_style


def _resolve_path(module4_root: Path, raw_value: str, default_rel: str) -> Path:
    text = str(raw_value or default_rel).strip()
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = (module4_root / candidate).resolve()
    return candidate


def _csv_list(raw_value: str, fallback: List[str]) -> List[str]:
    items = [item.strip() for item in str(raw_value or "").split(",") if item.strip()]
    return items or list(fallback)


def _csv_list_optional(raw_value: str) -> List[str]:
    return [item.strip() for item in str(raw_value or "").split(",") if item.strip()]


def _normalize_api_base(raw_value: str) -> str:
    text = str(raw_value or "").strip().rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    path = str(parsed.path or "").strip()
    if path in {"", "/"}:
        parsed = parsed._replace(path="/v1")
        return urlunparse(parsed).rstrip("/")
    return text


def _env_first(keys: List[str], default: str = "") -> str:
    for key in keys:
        value = str(os.getenv(key, "")).strip()
        if value:
            return value
    return default


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def _running_under_pytest() -> bool:
    # During test collection PYTEST_CURRENT_TEST may still be empty.
    # Checking loaded modules keeps the detection stable for test-only defaults.
    return "pytest" in sys.modules or bool(str(os.getenv("PYTEST_CURRENT_TEST", "")).strip())


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
    config_style: str = "auto"
    source_repo_root: str = ""
    use_source_checkout: bool = False
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
    extract_graph_prompt_file: str = "extract_graph.txt"
    summarize_descriptions_prompt_file: str = "summarize_descriptions.txt"
    extract_claims_prompt_file: str = "extract_claims.txt"
    community_report_graph_prompt_file: str = "community_report_graph.txt"
    community_report_text_prompt_file: str = "community_report_text.txt"
    local_search_prompt_file: str = "local_search_system_prompt.txt"
    global_search_map_prompt_file: str = "global_search_map_system_prompt.txt"
    global_search_reduce_prompt_file: str = "global_search_reduce_system_prompt.txt"
    global_search_knowledge_prompt_file: str = "global_search_knowledge_system_prompt.txt"
    drift_search_prompt_file: str = "drift_search_system_prompt.txt"
    drift_reduce_prompt_file: str = "drift_search_reduce_prompt.txt"
    basic_search_prompt_file: str = "basic_search_system_prompt.txt"
    question_gen_prompt_file: str = "question_gen_system_prompt.txt"
    max_tokens: int = 4000
    chunk_size: int = 1200
    chunk_overlap: int = 100
    cluster_max_size: int = 10
    utils_port: int = 8012
    indexing_method: str = "standard"
    workflows: List[str] = field(default_factory=list)
    skip_workflows: List[str] = field(default_factory=list)
    retry_skip_community_reports: bool = False
    execution_mode: str = "graphrag"

    @classmethod
    def from_env(cls, module4_root: Path | None = None) -> "GraphRAGRuntimeSettings":
        root = (module4_root or Path(__file__).resolve().parents[2]).resolve()
        execution_mode = str(os.getenv("MODULE4_GRAPHRAG_EXECUTION_MODE", "") or "").strip().lower()
        if not execution_mode:
            execution_mode = "deterministic_local" if _running_under_pytest() else "graphrag"
        configured_python_bin = str(os.getenv("MODULE4_GRAPHRAG_PYTHON_BIN", "") or "").strip()
        configured_query_python_bin = str(os.getenv("MODULE4_GRAPHRAG_QUERY_PYTHON_BIN", "") or "").strip()
        resolved_python_bin = choose_graphrag_python_bin(
            configured_python_bin=configured_python_bin,
            configured_query_python_bin=configured_query_python_bin,
        )
        resolved_config_style = resolve_graphrag_config_style(
            str(os.getenv("MODULE4_GRAPHRAG_CONFIG_STYLE", "auto") or "auto").strip().lower() or "auto",
            python_bin=resolved_python_bin,
            configured_python_bin=configured_python_bin,
            configured_query_python_bin=configured_query_python_bin,
        )
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
            api_base=_normalize_api_base(
                str(os.getenv("MODULE4_GRAPHRAG_API_BASE", os.getenv("GRAPHRAG_API_BASE", "")) or "").strip()
            ),
            chat_api_key=str(
                os.getenv("MODULE4_GRAPHRAG_CHAT_API_KEY", os.getenv("GRAPHRAG_CHAT_API_KEY", "")) or ""
            ).strip(),
            chat_model=str(
                os.getenv("MODULE4_GRAPHRAG_CHAT_MODEL", os.getenv("GRAPHRAG_CHAT_MODEL", "qwen-max")) or "qwen-max"
            ).strip()
            or "qwen-max",
            embedding_api_key=str(
                os.getenv("MODULE4_GRAPHRAG_EMBEDDING_API_KEY", os.getenv("GRAPHRAG_EMBEDDING_API_KEY", "")) or ""
            ).strip(),
            embedding_model=str(
                os.getenv(
                    "MODULE4_GRAPHRAG_EMBEDDING_MODEL",
                    os.getenv("GRAPHRAG_EMBEDDING_MODEL", "Embedding-V1"),
                )
                or "Embedding-V1"
            ).strip()
            or "Embedding-V1",
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
            config_style=resolved_config_style,
            source_repo_root=str(os.getenv("MODULE4_GRAPHRAG_SOURCE_REPO_ROOT", "") or "").strip(),
            use_source_checkout=_env_bool(
                "MODULE4_GRAPHRAG_USE_SOURCE_CHECKOUT",
                default=bool(str(os.getenv("MODULE4_GRAPHRAG_SOURCE_REPO_ROOT", "") or "").strip()),
            ),
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
            extract_graph_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["extract_graph"]],
                default="extract_graph.txt",
            ),
            summarize_descriptions_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["summarize_descriptions"]],
                default="summarize_descriptions.txt",
            ),
            extract_claims_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["extract_claims"]],
                default="extract_claims.txt",
            ),
            community_report_graph_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["community_report_graph"]],
                default="community_report_graph.txt",
            ),
            community_report_text_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["community_report_text"]],
                default="community_report_text.txt",
            ),
            local_search_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["local_search_system_prompt"]],
                default="local_search_system_prompt.txt",
            ),
            global_search_map_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["global_search_map_system_prompt"]],
                default="global_search_map_system_prompt.txt",
            ),
            global_search_reduce_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["global_search_reduce_system_prompt"]],
                default="global_search_reduce_system_prompt.txt",
            ),
            global_search_knowledge_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["global_search_knowledge_system_prompt"]],
                default="global_search_knowledge_system_prompt.txt",
            ),
            drift_search_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["drift_search_system_prompt"]],
                default="drift_search_system_prompt.txt",
            ),
            drift_reduce_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["drift_reduce_prompt"]],
                default="drift_search_reduce_prompt.txt",
            ),
            basic_search_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["basic_search_system_prompt"]],
                default="basic_search_system_prompt.txt",
            ),
            question_gen_prompt_file=_env_first(
                [PROMPT_KEY_TO_ENV["question_gen_system_prompt"]],
                default="question_gen_system_prompt.txt",
            ),
            max_tokens=max(256, int(os.getenv("MODULE4_GRAPHRAG_MAX_TOKENS", "4000"))),
            chunk_size=max(200, int(os.getenv("MODULE4_GRAPHRAG_CHUNK_SIZE", "1200"))),
            chunk_overlap=max(0, int(os.getenv("MODULE4_GRAPHRAG_CHUNK_OVERLAP", "100"))),
            cluster_max_size=max(2, int(os.getenv("MODULE4_GRAPHRAG_CLUSTER_MAX_SIZE", "10"))),
            utils_port=max(1, int(os.getenv("MODULE4_GRAPHRAG_UTILS_PORT", "8012"))),
            indexing_method=str(os.getenv("MODULE4_GRAPHRAG_INDEXING_METHOD", "standard") or "standard").strip()
            or "standard",
            workflows=_csv_list_optional(str(os.getenv("MODULE4_GRAPHRAG_WORKFLOWS", "") or "").strip()),
            skip_workflows=_csv_list_optional(str(os.getenv("MODULE4_GRAPHRAG_SKIP_WORKFLOWS", "") or "").strip()),
            retry_skip_community_reports=_env_bool(
                "MODULE4_GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS",
                default=False,
            ),
            execution_mode=execution_mode or "graphrag",
        )

    def prompt_overrides(self) -> Dict[str, str]:
        return {
            "extract_graph": self.extract_graph_prompt_file,
            "summarize_descriptions": self.summarize_descriptions_prompt_file,
            "extract_claims": self.extract_claims_prompt_file,
            "community_report_graph": self.community_report_graph_prompt_file,
            "community_report_text": self.community_report_text_prompt_file,
            "local_search_system_prompt": self.local_search_prompt_file,
            "global_search_map_system_prompt": self.global_search_map_prompt_file,
            "global_search_reduce_system_prompt": self.global_search_reduce_prompt_file,
            "global_search_knowledge_system_prompt": self.global_search_knowledge_prompt_file,
            "drift_search_system_prompt": self.drift_search_prompt_file,
            "drift_reduce_prompt": self.drift_reduce_prompt_file,
            "basic_search_system_prompt": self.basic_search_prompt_file,
            "question_gen_system_prompt": self.question_gen_prompt_file,
        }

    def is_configured(self) -> bool:
        return not self.missing_fields()

    def missing_fields(self) -> List[str]:
        mode = str(self.execution_mode or "").strip().lower()
        if mode in {"deterministic_local", "offline_local"}:
            return []
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
            "GRAPHRAG_API_KEY": self.chat_api_key,
            "GRAPHRAG_LLM_API_KEY": self.chat_api_key,
            "OPENAI_API_KEY": self.chat_api_key,
            "GRAPHRAG_CHAT_API_KEY": self.chat_api_key,
            "GRAPHRAG_CHAT_MODEL": self.chat_model,
            "GRAPHRAG_EMBEDDING_API_KEY": self.embedding_api_key,
            "GRAPHRAG_EMBEDDING_MODEL": self.embedding_model,
            "GRAPHRAG_EXTRACT_GRAPH_PROMPT_FILE": prompt_paths.get("extract_graph", "prompts/extract_graph.txt"),
            "GRAPHRAG_SUMMARIZE_DESCRIPTIONS_PROMPT_FILE": prompt_paths.get(
                "summarize_descriptions",
                "prompts/summarize_descriptions.txt",
            ),
            "GRAPHRAG_EXTRACT_CLAIMS_PROMPT_FILE": prompt_paths.get("extract_claims", "prompts/extract_claims.txt"),
            "GRAPHRAG_COMMUNITY_REPORT_GRAPH_PROMPT_FILE": prompt_paths.get(
                "community_report_graph",
                "prompts/community_report_graph.txt",
            ),
            "GRAPHRAG_COMMUNITY_REPORT_TEXT_PROMPT_FILE": prompt_paths.get(
                "community_report_text",
                "prompts/community_report_text.txt",
            ),
            "GRAPHRAG_LOCAL_SEARCH_PROMPT_FILE": prompt_paths.get(
                "local_search_system_prompt",
                "prompts/local_search_system_prompt.txt",
            ),
            "GRAPHRAG_GLOBAL_SEARCH_MAP_PROMPT_FILE": prompt_paths.get(
                "global_search_map_system_prompt",
                "prompts/global_search_map_system_prompt.txt",
            ),
            "GRAPHRAG_GLOBAL_SEARCH_REDUCE_PROMPT_FILE": prompt_paths.get(
                "global_search_reduce_system_prompt",
                "prompts/global_search_reduce_system_prompt.txt",
            ),
            "GRAPHRAG_GLOBAL_SEARCH_KNOWLEDGE_PROMPT_FILE": prompt_paths.get(
                "global_search_knowledge_system_prompt",
                "prompts/global_search_knowledge_system_prompt.txt",
            ),
            "GRAPHRAG_DRIFT_SEARCH_PROMPT_FILE": prompt_paths.get(
                "drift_search_system_prompt",
                "prompts/drift_search_system_prompt.txt",
            ),
            "GRAPHRAG_DRIFT_REDUCE_PROMPT_FILE": prompt_paths.get(
                "drift_reduce_prompt",
                "prompts/drift_search_reduce_prompt.txt",
            ),
            "GRAPHRAG_BASIC_SEARCH_PROMPT_FILE": prompt_paths.get(
                "basic_search_system_prompt",
                "prompts/basic_search_system_prompt.txt",
            ),
            "GRAPHRAG_QUESTION_GEN_PROMPT_FILE": prompt_paths.get(
                "question_gen_system_prompt",
                "prompts/question_gen_system_prompt.txt",
            ),
            "GRAPHRAG_INPUT_DIR": self.input_dir,
            "GRAPHRAG_CACHE_DIR": self.cache_dir,
            "GRAPHRAG_STORAGE_DIR": self.storage_dir,
            "GRAPHRAG_REPORTING_DIR": self.reporting_dir,
            "GRAPHRAG_CONFIG_STYLE": self.config_style,
            "GRAPHRAG_SOURCE_REPO_ROOT": self.source_repo_root,
            "GRAPHRAG_USE_SOURCE_CHECKOUT": "1" if self.use_source_checkout else "0",
            "GRAPHRAG_UTILS_PORT": str(self.utils_port),
            "GRAPHRAG_INDEXING_METHOD": self.indexing_method,
            "GRAPHRAG_WORKFLOWS": ",".join(self.workflows),
            "GRAPHRAG_SKIP_WORKFLOWS": ",".join(self.skip_workflows),
            "GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS": "1" if self.retry_skip_community_reports else "0",
            "GRAPHRAG_EXECUTION_MODE": str(self.execution_mode or "graphrag"),
        }

    def env_mapping(self) -> Dict[str, Dict[str, str]]:
        return {
            "runtime": {
                "MODULE4_GRAPHRAG_API_BASE": "GRAPHRAG_API_BASE",
                "MODULE4_GRAPHRAG_CHAT_API_KEY": "GRAPHRAG_CHAT_API_KEY",
                "MODULE4_GRAPHRAG_CHAT_MODEL": "GRAPHRAG_CHAT_MODEL",
                "MODULE4_GRAPHRAG_EMBEDDING_API_KEY": "GRAPHRAG_EMBEDDING_API_KEY",
                "MODULE4_GRAPHRAG_EMBEDDING_MODEL": "GRAPHRAG_EMBEDDING_MODEL",
                "MODULE4_GRAPHRAG_INPUT_DIR": "GRAPHRAG_INPUT_DIR",
                "MODULE4_GRAPHRAG_CACHE_DIR": "GRAPHRAG_CACHE_DIR",
                "MODULE4_GRAPHRAG_STORAGE_DIR": "GRAPHRAG_STORAGE_DIR",
                "MODULE4_GRAPHRAG_REPORTING_DIR": "GRAPHRAG_REPORTING_DIR",
                "MODULE4_GRAPHRAG_CONFIG_STYLE": "GRAPHRAG_CONFIG_STYLE",
                "MODULE4_GRAPHRAG_SOURCE_REPO_ROOT": "GRAPHRAG_SOURCE_REPO_ROOT",
                "MODULE4_GRAPHRAG_USE_SOURCE_CHECKOUT": "GRAPHRAG_USE_SOURCE_CHECKOUT",
                "MODULE4_GRAPHRAG_UTILS_PORT": "GRAPHRAG_UTILS_PORT",
                "MODULE4_GRAPHRAG_INDEXING_METHOD": "GRAPHRAG_INDEXING_METHOD",
                "MODULE4_GRAPHRAG_WORKFLOWS": "GRAPHRAG_WORKFLOWS",
                "MODULE4_GRAPHRAG_SKIP_WORKFLOWS": "GRAPHRAG_SKIP_WORKFLOWS",
                "MODULE4_GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS": "GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS",
                "MODULE4_GRAPHRAG_EXECUTION_MODE": "GRAPHRAG_EXECUTION_MODE",
            },
            "prompts": {
                "MODULE4_GRAPHRAG_EXTRACT_GRAPH_PROMPT_FILE": "GRAPHRAG_EXTRACT_GRAPH_PROMPT_FILE",
                "MODULE4_GRAPHRAG_SUMMARIZE_DESCRIPTIONS_PROMPT_FILE": "GRAPHRAG_SUMMARIZE_DESCRIPTIONS_PROMPT_FILE",
                "MODULE4_GRAPHRAG_EXTRACT_CLAIMS_PROMPT_FILE": "GRAPHRAG_EXTRACT_CLAIMS_PROMPT_FILE",
                "MODULE4_GRAPHRAG_COMMUNITY_REPORT_GRAPH_PROMPT_FILE": "GRAPHRAG_COMMUNITY_REPORT_GRAPH_PROMPT_FILE",
                "MODULE4_GRAPHRAG_COMMUNITY_REPORT_TEXT_PROMPT_FILE": "GRAPHRAG_COMMUNITY_REPORT_TEXT_PROMPT_FILE",
                "MODULE4_GRAPHRAG_LOCAL_SEARCH_PROMPT_FILE": "GRAPHRAG_LOCAL_SEARCH_PROMPT_FILE",
                "MODULE4_GRAPHRAG_GLOBAL_SEARCH_MAP_PROMPT_FILE": "GRAPHRAG_GLOBAL_SEARCH_MAP_PROMPT_FILE",
                "MODULE4_GRAPHRAG_GLOBAL_SEARCH_REDUCE_PROMPT_FILE": "GRAPHRAG_GLOBAL_SEARCH_REDUCE_PROMPT_FILE",
                "MODULE4_GRAPHRAG_GLOBAL_SEARCH_KNOWLEDGE_PROMPT_FILE": "GRAPHRAG_GLOBAL_SEARCH_KNOWLEDGE_PROMPT_FILE",
                "MODULE4_GRAPHRAG_DRIFT_SEARCH_PROMPT_FILE": "GRAPHRAG_DRIFT_SEARCH_PROMPT_FILE",
                "MODULE4_GRAPHRAG_DRIFT_REDUCE_PROMPT_FILE": "GRAPHRAG_DRIFT_REDUCE_PROMPT_FILE",
                "MODULE4_GRAPHRAG_BASIC_SEARCH_PROMPT_FILE": "GRAPHRAG_BASIC_SEARCH_PROMPT_FILE",
                "MODULE4_GRAPHRAG_QUESTION_GEN_PROMPT_FILE": "GRAPHRAG_QUESTION_GEN_PROMPT_FILE",
            },
            "settings": {
                "MODULE4_GRAPHRAG_ENTITY_TYPES": "entity_extraction.entity_types",
                "MODULE4_GRAPHRAG_MAX_TOKENS": "completion_models.default_chat_model.call_args.max_completion_tokens",
                "MODULE4_GRAPHRAG_CHUNK_SIZE": "chunking.size",
                "MODULE4_GRAPHRAG_CHUNK_OVERLAP": "chunking.overlap",
                "MODULE4_GRAPHRAG_CLUSTER_MAX_SIZE": "cluster_graph.max_cluster_size",
                "MODULE4_GRAPHRAG_WORKFLOWS": "workflows",
                "MODULE4_GRAPHRAG_SKIP_WORKFLOWS": "skip_workflows",
                "MODULE4_GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS": "runtime.retry_skip_community_reports",
            },
        }
