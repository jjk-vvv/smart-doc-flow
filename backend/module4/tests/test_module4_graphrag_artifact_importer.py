from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.db.storage import Module4Storage  # noqa: E402
from app.services.graphrag.importer import GraphRAGArtifactImporter  # noqa: E402


def _write_pylist(path: Path, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def test_partial_artifacts_are_imported_as_base_graph(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True)

    _write_pylist(
        artifacts_dir / "create_base_text_units.parquet",
        [
            {
                "id": "chunk-1",
                "chunk": "Qingniu Town is located in Linhai New District.",
                "chunk_id": "chunk-1",
                "document_ids": ["doc-1"],
                "n_tokens": 16,
            }
        ],
    )

    graphml = """
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="node" attr.name="type" attr.type="string" />
  <key id="d1" for="node" attr.name="description" attr.type="string" />
  <key id="d2" for="node" attr.name="source_id" attr.type="string" />
  <key id="d3" for="edge" attr.name="description" attr.type="string" />
  <key id="d4" for="edge" attr.name="weight" attr.type="double" />
  <key id="d5" for="edge" attr.name="source_id" attr.type="string" />
  <graph edgedefault="undirected">
    <node id="QINGNIU TOWN">
      <data key="d0">GEO</data>
      <data key="d1">A town in Linhai New District</data>
      <data key="d2">chunk-1</data>
    </node>
    <node id="LINHAI NEW DISTRICT">
      <data key="d0">GEO</data>
      <data key="d1">A district that contains Qingniu Town</data>
      <data key="d2">chunk-1</data>
    </node>
    <edge source="QINGNIU TOWN" target="LINHAI NEW DISTRICT">
      <data key="d3">Qingniu Town is located in Linhai New District</data>
      <data key="d4">2</data>
      <data key="d5">chunk-1</data>
    </edge>
  </graph>
</graphml>
""".strip()
    _write_pylist(
        artifacts_dir / "create_summarized_entities.parquet",
        [{"entity_graph": graphml}],
    )

    async def scenario() -> None:
        tenant_id = f"test-{uuid.uuid4().hex[:8]}"
        storage = Module4Storage("postgresql://invalid")

        importer = GraphRAGArtifactImporter()
        summary = await importer.import_into_storage(
            storage=storage,
            tenant_id=tenant_id,
            batch_id="batch-1",
            workspace_id="workspace-1",
            artifacts_dir=artifacts_dir,
            source_files=[
                {
                    "file_name": "sample.txt",
                    "file_hash": "hash-sample",
                    "artifact_path": "preview/sample.txt",
                }
            ],
        )

        assert summary.partial is True
        assert summary.mode == "partial"
        assert summary.documents == 1
        assert summary.chunks == 1
        assert summary.entities == 2
        assert summary.nodes >= 4
        assert summary.edges >= 4
        assert summary.evidence >= 4
        assert summary.edge_evidence_links >= 4

        nodes = [
            dict(row)
            for row in storage._nodes_by_id.values()
            if str(row.get("tenant_id") or "") == tenant_id
        ]
        edges = [
            dict(row)
            for row in storage._edges_by_id.values()
            if str(row.get("tenant_id") or "") == tenant_id
        ]
        node_types = {str(item.get("node_type")) for item in nodes}
        relation_types = {str(item.get("relation_type")) for item in edges}
        assert {"Document", "Chunk", "Entity"}.issubset(node_types)
        assert {"PART_OF", "HAS_ENTITY", "RELATED"}.issubset(relation_types)

        evidence_total, evidence_rows = await storage.list_evidence(
            tenant_id=tenant_id,
            doc_id=None,
            object_type="chunk",
            object_id="chunk-1",
            page=1,
            page_size=20,
        )
        assert evidence_total >= 1
        assert evidence_rows

        related_edge = next((edge for edge in edges if str(edge.get("relation_type")) == "RELATED"), None)
        assert related_edge is not None
        edge_evidence_total, edge_evidence_rows = await storage.list_edge_evidence(
            tenant_id=tenant_id,
            edge_id=str(related_edge["edge_id"]),
            page=1,
            page_size=20,
        )
        assert edge_evidence_total >= 1
        assert edge_evidence_rows

        await storage.close()

    asyncio.run(scenario())


def test_v3_final_artifacts_are_imported_with_field_compatibility(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True)

    _write_pylist(
        artifacts_dir / "documents.parquet",
        [
            {
                "id": "doc-1",
                "human_readable_id": 1,
                "title": "示例合同",
                "text": "Acme signed with Contoso.",
                "text_unit_ids": ["chunk-1"],
                "raw_data": '{"source":"demo"}',
            }
        ],
    )
    _write_pylist(
        artifacts_dir / "text_units.parquet",
        [
            {
                "id": "chunk-1",
                "human_readable_id": 1,
                "text": "Acme signed with Contoso in 2025.",
                "n_tokens": 32,
                "document_id": "doc-1",
                "entity_ids": ["ent-1", "ent-2"],
                "relationship_ids": ["rel-1"],
            }
        ],
    )
    _write_pylist(
        artifacts_dir / "entities.parquet",
        [
            {
                "id": "ent-1",
                "human_readable_id": 1,
                "title": "Acme",
                "type": "organization",
                "description": "Party A",
                "text_unit_ids": ["chunk-1"],
            },
            {
                "id": "ent-2",
                "human_readable_id": 2,
                "title": "Contoso",
                "type": "organization",
                "description": "Party B",
                "text_unit_ids": ["chunk-1"],
            },
        ],
    )
    _write_pylist(
        artifacts_dir / "relationships.parquet",
        [
            {
                "id": "rel-1",
                "human_readable_id": 1,
                "source": "Acme",
                "target": "Contoso",
                "description": "signed_with",
                "weight": 0.87,
                "combined_degree": 4,
                "text_unit_ids": ["chunk-1"],
            }
        ],
    )
    _write_pylist(
        artifacts_dir / "communities.parquet",
        [
            {
                "id": "comm-row-1",
                "community": "comm-1",
                "level": 0,
                "title": "Contract Parties",
                "text_unit_ids": ["chunk-1"],
                "relationship_ids": ["rel-1"],
            }
        ],
    )
    _write_pylist(
        artifacts_dir / "community_reports.parquet",
        [
            {
                "id": "report-1",
                "community": "comm-1",
                "title": "Community Report 1",
                "summary": "Acme and Contoso contract summary.",
                "full_content": "Detailed findings",
                "level": 0,
                "rank": 1,
                "rating_explanation": "highest rank",
                "text_unit_ids": ["chunk-1"],
            }
        ],
    )

    async def scenario() -> None:
        tenant_id = f"test-{uuid.uuid4().hex[:8]}"
        storage = Module4Storage("postgresql://invalid")

        importer = GraphRAGArtifactImporter()
        summary = await importer.import_into_storage(
            storage=storage,
            tenant_id=tenant_id,
            batch_id="batch-v3",
            workspace_id="workspace-v3",
            artifacts_dir=artifacts_dir,
            source_files=[
                {
                    "file_name": "sample-v3.txt",
                    "file_hash": "hash-v3",
                    "artifact_path": "preview/sample-v3.txt",
                }
            ],
        )

        assert summary.partial is False
        assert summary.mode == "final"
        assert summary.documents == 1
        assert summary.chunks == 1
        assert summary.entities == 2
        assert summary.communities >= 1
        assert summary.nodes >= 5
        assert summary.edges >= 6
        assert summary.evidence >= 5

        nodes = [
            dict(row)
            for row in storage._nodes_by_id.values()
            if str(row.get("tenant_id") or "") == tenant_id
        ]
        edges = [
            dict(row)
            for row in storage._edges_by_id.values()
            if str(row.get("tenant_id") or "") == tenant_id
        ]
        node_types = {str(item.get("node_type")) for item in nodes}
        relation_types = {str(item.get("relation_type")) for item in edges}
        assert {"Document", "Chunk", "Entity", "Community", "CommunityReport"}.issubset(node_types)
        assert {"PART_OF", "HAS_ENTITY", "RELATED", "IN_COMMUNITY", "HAS_REPORT"}.issubset(relation_types)

        report_rows = [row for row in nodes if str(row.get("node_type")) == "CommunityReport"]
        assert report_rows
        assert str((report_rows[0].get("attrs") or {}).get("graph_source") or "").startswith("graphrag_artifacts")

        rel_total, rel_rows = await storage.list_evidence(
            tenant_id=tenant_id,
            doc_id=None,
            object_type="relationship",
            object_id="rel-1",
            page=1,
            page_size=20,
        )
        assert rel_total >= 1
        assert rel_rows

        report_total, report_rows = await storage.list_evidence(
            tenant_id=tenant_id,
            doc_id=None,
            object_type="community_report",
            object_id="report-1",
            page=1,
            page_size=20,
        )
        assert report_total >= 1
        assert report_rows

        await storage.close()

    asyncio.run(scenario())
