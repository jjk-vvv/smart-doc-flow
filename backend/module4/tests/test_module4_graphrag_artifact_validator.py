from __future__ import annotations

import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag_artifact_validator import GraphRAGArtifactValidator


def _write_pylist(path: Path, rows: list[dict], schema: pa.Schema | None = None) -> None:
    if schema is not None:
        table = pa.Table.from_pylist(rows, schema=schema)
    else:
        table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def test_validator_accepts_complete_final_artifacts(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True)

    _write_pylist(
        artifacts_dir / "create_final_documents.parquet",
        [{"id": "doc-1", "title": "Doc 1", "raw_content": "hello"}],
    )
    _write_pylist(
        artifacts_dir / "create_final_text_units.parquet",
        [
            {
                "id": "chunk-1",
                "text": "hello",
                "n_tokens": 3,
                "document_ids": ["doc-1"],
                "entity_ids": ["entity-1"],
                "relationship_ids": ["rel-1"],
            }
        ],
    )
    _write_pylist(
        artifacts_dir / "create_final_entities.parquet",
        [
            {
                "id": "entity-1",
                "name": "Alpha",
                "type": "ORG",
                "description": "desc",
                "human_readable_id": "E1",
                "text_unit_ids": ["chunk-1"],
            }
        ],
    )
    _write_pylist(
        artifacts_dir / "create_final_relationships.parquet",
        [
            {
                "id": "rel-1",
                "source": "Alpha",
                "target": "Beta",
                "rank": 1,
                "weight": 1.0,
                "human_readable_id": "R1",
                "description": "related",
                "text_unit_ids": ["chunk-1"],
            }
        ],
    )
    _write_pylist(
        artifacts_dir / "create_final_communities.parquet",
        [{"id": "community-1", "level": 1, "title": "Group", "text_unit_ids": ["chunk-1"], "relationship_ids": ["rel-1"]}],
    )

    validator = GraphRAGArtifactValidator()
    result = validator.validate(artifacts_dir)

    assert result.ok is True
    assert result.import_mode == "final"
    assert result.partial is False


def test_validator_falls_back_to_partial_when_final_artifacts_are_incomplete(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True)

    _write_pylist(
        artifacts_dir / "create_final_documents.parquet",
        [{"id": "doc-1", "title": "Doc 1", "raw_content": "hello"}],
    )
    _write_pylist(
        artifacts_dir / "create_base_text_units.parquet",
        [{"id": "chunk-1", "chunk": "hello", "document_ids": ["doc-1"], "n_tokens": 3}],
    )

    validator = GraphRAGArtifactValidator()
    result = validator.validate(artifacts_dir)

    assert result.ok is True
    assert result.import_mode == "partial"
    assert result.partial is True
    assert result.warnings
