from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


MODULE2_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = MODULE2_ROOT.parents[1]
CUSTOM_MODULE2_ENV_FILE = str(os.getenv("MODULE2_ENV_FILE", "") or "").strip()
load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)
if CUSTOM_MODULE2_ENV_FILE:
    load_dotenv(dotenv_path=CUSTOM_MODULE2_ENV_FILE, override=True)


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def _runtime_root_dir() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return REPO_ROOT


def _data_root_dir() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    runtime_root = _runtime_root_dir()
    runtime_data_dir = (runtime_root / "runtime-data").resolve()
    if runtime_data_dir.exists():
        return runtime_data_dir
    return runtime_root


def _resolve_module2_path(raw_value: str, default_path: Path) -> Path:
    raw = str(raw_value or "").strip()
    if not raw:
        return default_path.resolve()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    candidate_module2 = (MODULE2_ROOT / path).resolve()
    candidate_repo = (REPO_ROOT / path).resolve()
    normalized = raw.replace("\\", "/").lower()
    if normalized.startswith("backend/module2/"):
        return candidate_repo
    if candidate_repo.exists() and not candidate_module2.exists():
        return candidate_repo
    return candidate_module2


@dataclass(frozen=True)
class Assistant1Settings:
    module2_root: Path
    module2_artifact_root_dir: Path
    artifact_root_dir: Path
    database_dsn: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    embedding_endpoint_style: str
    embedding_dimensions: int
    embedding_timeout_sec: float
    embedding_batch_size: int
    embedding_document_task_type: str
    embedding_query_task_type: str
    similarity_metric: str
    chat_api_key: str
    chat_base_url: str
    chat_endpoint_path: str
    chat_endpoint_style: str
    chat_model: str
    chat_temperature: float
    chat_timeout_sec: float
    chat_max_output_tokens: int
    chat_reasoning_effort: str
    tavily_api_key: str
    tavily_search_url: str
    tavily_timeout_sec: float
    tavily_max_results: int
    sql_timeout_sec: float
    sql_max_preview_rows: int

    @classmethod
    def from_env(cls) -> "Assistant1Settings":
        module2_artifact_root = _resolve_module2_path(
            _env("MODULE2_ARTIFACT_ROOT_DIR", default=""),
            _data_root_dir() / "module2" / "artifacts",
        )
        module2_artifact_root.mkdir(parents=True, exist_ok=True)

        artifact_root = _resolve_module2_path(
            _env("ASSISTANT1_ARTIFACT_ROOT_DIR", default=""),
            module2_artifact_root / "assistant_1",
        )
        artifact_root.mkdir(parents=True, exist_ok=True)

        endpoint_style = _env(
            "ASSISTANT1_EMBEDDING_ENDPOINT_STYLE",
            default="auto",
        ).lower()
        if endpoint_style not in {"auto", "native", "openai"}:
            endpoint_style = "auto"

        similarity_metric = _env(
            "ASSISTANT1_VECTOR_SIMILARITY_METRIC",
            default="cosine",
        ).lower()
        if similarity_metric not in {"cosine", "l2", "inner_product"}:
            similarity_metric = "cosine"

        chat_endpoint_style = _env(
            "ASSISTANT1_CHAT_ENDPOINT_STYLE",
            default="openai_responses",
        ).lower()
        if chat_endpoint_style not in {"openai_responses", "openai_chat_completions"}:
            chat_endpoint_style = "openai_responses"

        chat_endpoint_path = _env(
            "ASSISTANT1_CHAT_ENDPOINT_PATH",
            default="/v1/responses",
        ).strip() or "/v1/responses"
        if not chat_endpoint_path.startswith("/"):
            chat_endpoint_path = f"/{chat_endpoint_path}"

        chat_reasoning_effort = _env(
            "ASSISTANT1_CHAT_REASONING_EFFORT",
            default="minimal",
        ).strip().lower()
        if chat_reasoning_effort not in {"", "minimal", "low", "medium", "high"}:
            chat_reasoning_effort = "minimal"

        tavily_search_url = _env(
            "ASSISTANT1_TAVILY_SEARCH_URL",
            default="https://api.tavily.com/search",
        ).strip() or "https://api.tavily.com/search"

        return cls(
            module2_root=MODULE2_ROOT,
            module2_artifact_root_dir=module2_artifact_root,
            artifact_root_dir=artifact_root,
            database_dsn=_env(
                "ASSISTANT1_DATABASE_DSN",
                "MODULE2_DATABASE_DSN",
                default="",
            ),
            embedding_api_key=_env(
                "ASSISTANT1_EMBEDDING_API_KEY",
                "MODULE2_LLM_API_KEY",
                "GOOGLE_API_KEY",
                default="",
            ),
            embedding_base_url=_env(
                "ASSISTANT1_EMBEDDING_BASE_URL",
                "MODULE2_LLM_BASE_URL",
                default="https://generativelanguage.googleapis.com",
            ),
            embedding_model=_env(
                "ASSISTANT1_EMBEDDING_MODEL",
                default="gemini-embedding-001",
            ),
            embedding_endpoint_style=endpoint_style,
            embedding_dimensions=max(128, int(_env("ASSISTANT1_EMBEDDING_DIMENSIONS", default="1536"))),
            embedding_timeout_sec=max(
                5.0,
                float(_env("ASSISTANT1_EMBEDDING_TIMEOUT_SEC", default="45")),
            ),
            embedding_batch_size=max(
                1,
                int(_env("ASSISTANT1_EMBEDDING_BATCH_SIZE", default="16")),
            ),
            embedding_document_task_type=_env(
                "ASSISTANT1_EMBEDDING_DOCUMENT_TASK_TYPE",
                default="RETRIEVAL_DOCUMENT",
            ),
            embedding_query_task_type=_env(
                "ASSISTANT1_EMBEDDING_QUERY_TASK_TYPE",
                default="RETRIEVAL_QUERY",
            ),
            similarity_metric=similarity_metric,
            chat_api_key=_env(
                "ASSISTANT1_CHAT_API_KEY",
                "OPENAI_API_KEY",
                default="",
            ),
            chat_base_url=_env(
                "ASSISTANT1_CHAT_BASE_URL",
                "OPENAI_BASE_URL",
                default="https://api.openai.com",
            ),
            chat_endpoint_path=chat_endpoint_path,
            chat_endpoint_style=chat_endpoint_style,
            chat_model=_env(
                "ASSISTANT1_CHAT_MODEL",
                default="gpt-5-mini",
            ),
            chat_temperature=max(
                0.0,
                min(2.0, float(_env("ASSISTANT1_CHAT_TEMPERATURE", default="0.2"))),
            ),
            chat_timeout_sec=max(
                10.0,
                float(_env("ASSISTANT1_CHAT_TIMEOUT_SEC", default="120")),
            ),
            chat_max_output_tokens=max(
                256,
                int(_env("ASSISTANT1_CHAT_MAX_OUTPUT_TOKENS", default="2400")),
            ),
            chat_reasoning_effort=chat_reasoning_effort,
            tavily_api_key=_env(
                "ASSISTANT1_TAVILY_API_KEY",
                default="",
            ),
            tavily_search_url=tavily_search_url,
            tavily_timeout_sec=max(
                5.0,
                float(_env("ASSISTANT1_TAVILY_TIMEOUT_SEC", default="20")),
            ),
            tavily_max_results=max(
                1,
                min(10, int(_env("ASSISTANT1_TAVILY_MAX_RESULTS", default="6"))),
            ),
            sql_timeout_sec=max(
                5.0,
                float(_env("ASSISTANT1_SQL_TIMEOUT_SEC", default="20")),
            ),
            sql_max_preview_rows=max(
                1,
                min(200, int(_env("ASSISTANT1_SQL_MAX_PREVIEW_ROWS", default="50"))),
            ),
        )
