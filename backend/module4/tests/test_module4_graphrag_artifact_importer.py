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
from app.services.graphrag_artifact_importer import GraphRAGArtifactImporter  # noqa: E402


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

        nodes, edges = await storage.list_graph(
            tenant_id=tenant_id,
            node_types=[],
            relation_types=[],
            limit_nodes=100,
            limit_edges=100,
        )
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
