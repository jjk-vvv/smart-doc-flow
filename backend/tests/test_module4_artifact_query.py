from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.module4.services.graphrag import artifact_query


def _write_artifacts(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "id": ["t1", "t2"],
            "text": [
                "地区生产总值达到 12345 亿元，同比增长 5.2%。",
                "常住人口为 987.6 万人。",
            ],
        }
    ).to_parquet(target / "create_final_text_units.parquet")
    pd.DataFrame(
        {
            "community": [0],
            "title": ["经济指标"],
            "summary": ["该社区汇总地区生产总值等核心经济指标。"],
            "full_content": ["地区生产总值 12345 亿元。"],
        }
    ).to_parquet(target / "create_final_community_reports.parquet")
    return target


def test_artifact_query_builds_ranked_context(monkeypatch, tmp_path: Path) -> None:
    artifacts = _write_artifacts(tmp_path / "artifacts")
    monkeypatch.setattr(artifact_query, "_chat_answer", lambda **_kwargs: "ANSWER")

    payload = asyncio.run(
        artifact_query.run_artifact_query(
            workspace_dir=tmp_path,
            artifacts_dir=artifacts,
            mode="basic",
            query="地区生产总值是多少？",
            response_type="multiple paragraphs",
        )
    )

    assert payload["answer"] == "ANSWER"
    assert payload["source"] == "graphrag:query:basic:artifact_fallback"
    units = payload["context_data"]["text_units"]
    assert units
    assert "地区生产总值" in units[0]["text"]


def test_artifact_query_handles_missing_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        artifact_query,
        "_chat_answer",
        lambda **kwargs: f"context-present:{bool(kwargs['context'])}",
    )

    payload = asyncio.run(
        artifact_query.run_artifact_query(
            workspace_dir=tmp_path,
            artifacts_dir=tmp_path / "missing",
            mode="local",
            query="任意问题",
            response_type="multiple paragraphs",
        )
    )

    assert payload["answer"] == "context-present:False"
    assert payload["context_data"]["text_units"] == []
