"""Artifact-only query fallback for legacy GraphRAG runtimes.

GraphRAG 0.3 predates ``graphrag.api`` / ``graphrag_storage``: its ``graphrag.index``
import chain pulls optional heavyweight dependencies and its search engines need a
LanceDB description store. When the installed runtime is legacy we still want
``/module4/query/search`` to work, so this module answers from the artifact parquet
files with a retrieval + chat-completion flow and labels the result as a fallback.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

ARTIFACT_FILES: Dict[str, str] = {
    "text_units": "create_final_text_units.parquet",
    "community_reports": "create_final_community_reports.parquet",
    "entities": "create_final_entities.parquet",
    "relationships": "create_final_relationships.parquet",
    "communities": "create_final_communities.parquet",
}

_CJK = re.compile(r"[\u4e00-\u9fff]")
_WORD = re.compile(r"[a-zA-Z0-9_]+")
_CONTEXT_CHAR_LIMIT = 6000
_MAX_TEXT_UNITS = 6
_MAX_REPORTS = 2


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return default


def _artifact_path(artifacts_dir: Path, name: str) -> Path | None:
    filename = ARTIFACT_FILES.get(name)
    if not filename:
        return None
    candidate = artifacts_dir / filename
    return candidate if candidate.exists() else None


def load_artifacts(artifacts_dir: Path, names: List[str]) -> Dict[str, Any]:
    import pandas as pd

    frames: Dict[str, Any] = {}
    for name in names:
        path = _artifact_path(artifacts_dir, name)
        frames[name] = pd.read_parquet(path) if path is not None else None
    return frames


def _tokenize(text: str) -> set[str]:
    lowered = str(text or "").lower()
    tokens = {match.group(0) for match in _WORD.finditer(lowered) if len(match.group(0)) > 1}
    cjk = "".join(_CJK.findall(lowered))
    for index in range(len(cjk) - 1):
        tokens.add(cjk[index : index + 2])
    return tokens


def _score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    overlap = query_tokens & tokens
    return float(len(overlap)) / (len(query_tokens) ** 0.5)


def _rank(
    frame: Any,
    *,
    text_columns: Tuple[str, ...],
    query_tokens: set[str],
    limit: int,
) -> List[Tuple[float, str]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    ranked: List[Tuple[float, str]] = []
    for _, row in frame.iterrows():
        parts = []
        for column in text_columns:
            value = row.get(column)
            if value is None:
                continue
            parts.append(str(value))
        text = " ".join(part for part in parts if part).strip()
        if not text:
            continue
        ranked.append((_score(query_tokens, text), text))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:limit]


def _build_context(frames: Dict[str, Any], query: str) -> Tuple[str, Dict[str, Any]]:
    query_tokens = _tokenize(query)
    text_units = _rank(
        frames.get("text_units"),
        text_columns=("text",),
        query_tokens=query_tokens,
        limit=_MAX_TEXT_UNITS,
    )
    reports = _rank(
        frames.get("community_reports"),
        text_columns=("title", "summary", "full_content"),
        query_tokens=query_tokens,
        limit=_MAX_REPORTS,
    )

    lines: List[str] = []
    payload_units: List[Dict[str, Any]] = []
    for _, text in text_units:
        lines.append(f"[原文片段] {text}")
        payload_units.append({"type": "text_unit", "text": text})
    for _, text in reports:
        lines.append(f"[社区报告] {text}")
        payload_units.append({"type": "community_report", "text": text})

    context = "\n\n".join(lines)[:_CONTEXT_CHAR_LIMIT]
    return context, {"text_units": payload_units}


def _chat_answer(*, query: str, context: str, response_type: str) -> str:
    from openai import OpenAI

    api_key = _env("GRAPHRAG_CHAT_API_KEY", "MODULE4_GRAPHRAG_CHAT_API_KEY", default="")
    base_url = _env("GRAPHRAG_API_BASE", "MODULE4_GRAPHRAG_API_BASE", default="")
    model = _env("GRAPHRAG_CHAT_MODEL", "MODULE4_GRAPHRAG_CHAT_MODEL", default="")
    if not api_key or not base_url or not model:
        raise RuntimeError("GraphRAG chat model is not configured for artifact fallback")

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
    completion = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_tokens=1200,
        messages=[
            {
                "role": "system",
                "content": (
                    "You answer questions about a document knowledge graph. "
                    "Use only the provided context and say so when it is insufficient. "
                    f"Reply in {response_type or 'multiple paragraphs'}."
                ),
            },
            {"role": "user", "content": f"问题：{query}\n\n上下文：\n{context or '(no matching context)'}"},
        ],
    )
    content = completion.choices[0].message.content if completion.choices else ""
    return str(content or "").strip()


async def run_artifact_query(
    *,
    workspace_dir: Path,
    artifacts_dir: Path,
    mode: str,
    query: str,
    response_type: str,
) -> Dict[str, Any]:
    import asyncio

    frames = load_artifacts(artifacts_dir, ["text_units", "community_reports"])
    context, context_data = _build_context(frames, query)
    answer = await asyncio.to_thread(
        _chat_answer,
        query=query,
        context=context,
        response_type=response_type,
    )
    return {
        "answer": answer,
        "mode": mode,
        "context_data": context_data,
        "source": f"graphrag:query:{mode}:artifact_fallback",
        "workspace_dir": str(workspace_dir),
    }


__all__ = ["run_artifact_query", "load_artifacts"]
