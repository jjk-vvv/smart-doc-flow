from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree as ET

MODULE4_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MODULE4_DIR.parents[1]

import sys

if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.db.storage import Module4Storage  # noqa: E402
from app.composition.application import _get_runtime_ref, _set_runtime_ref  # noqa: E402
from app.composition.application import _run_document_ingest_job  # noqa: E402
from app.schemas import IngestRequest  # noqa: E402
from app.services.graphrag.query_adapter import load_artifact_graph_snapshot  # noqa: E402

TEXT_FILE_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml"}
OFFICE_FILE_SUFFIXES = {".docx", ".xlsx"}
SUPPORTED_SUFFIXES = TEXT_FILE_SUFFIXES | OFFICE_FILE_SUFFIXES
EXCLUDED_SUFFIXES = {".pdf"}
MAX_TEXT_CHARS = 120_000
REPLACEMENT_CHAR = "\ufffd"


@dataclass(frozen=True)
class FileEval:
    relative_path: str
    suffix: str
    status: str
    reason: Optional[str]
    text_chars: int
    node_count: int
    edge_count: int
    by_node_type: Dict[str, int]
    by_relation_type: Dict[str, int]
    has_replacement_char: bool


def _slug_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n?", "\n", text)).strip()


def _iter_nonpdf_files(dataset_root: Path) -> Iterable[Path]:
    for path in sorted(dataset_root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in EXCLUDED_SUFFIXES:
            continue
        if suffix in SUPPORTED_SUFFIXES:
            yield path


def _extract_docx_text(path: Path) -> str:
    chunks: List[str] = []
    with zipfile.ZipFile(path) as zf:
        with zf.open("word/document.xml") as fp:
            xml_bytes = fp.read()
    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for node in root.findall(".//w:t", ns):
        if node.text:
            chunks.append(node.text)
    return _normalize_whitespace("\n".join(chunks))


def _extract_xlsx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in shared_root.findall(".//x:si", ns):
                txt = "".join(t.text or "" for t in si.findall(".//x:t", ns))
                shared_strings.append(txt)

        ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        lines: List[str] = []
        sheet_names = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        for sheet_name in sorted(sheet_names):
            sheet_root = ET.fromstring(zf.read(sheet_name))
            for row in sheet_root.findall(".//x:row", ns):
                vals: List[str] = []
                for cell in row.findall("x:c", ns):
                    cell_type = str(cell.attrib.get("t") or "")
                    v_node = cell.find("x:v", ns)
                    if v_node is None or v_node.text is None:
                        continue
                    value = v_node.text
                    if cell_type == "s":
                        try:
                            idx = int(value)
                            value = shared_strings[idx] if 0 <= idx < len(shared_strings) else value
                        except Exception:
                            pass
                    vals.append(value)
                if vals:
                    lines.append(" | ".join(vals))
    return _normalize_whitespace("\n".join(lines))


def _extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_FILE_SUFFIXES:
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="gb18030", errors="ignore")
        return _normalize_whitespace(raw)
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix == ".xlsx":
        return _extract_xlsx_text(path)
    raise ValueError(f"Unsupported suffix: {suffix}")


def _has_replacement_char(graph_nodes: List[Dict[str, Any]]) -> bool:
    for node in graph_nodes:
        if REPLACEMENT_CHAR in str(node.get("display_name") or ""):
            return True
        attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
        if REPLACEMENT_CHAR in json.dumps(attrs, ensure_ascii=False):
            return True
    return False


async def _evaluate_file(storage: Module4Storage, dataset_root: Path, file_path: Path, tenant_id: str) -> FileEval:
    relative_path = str(file_path.relative_to(dataset_root))
    suffix = file_path.suffix.lower()
    try:
        text = _extract_text(file_path)
    except Exception as exc:
        return FileEval(
            relative_path=relative_path,
            suffix=suffix,
            status="skipped",
            reason=f"text_extract_failed:{type(exc).__name__}",
            text_chars=0,
            node_count=0,
            edge_count=0,
            by_node_type={},
            by_relation_type={},
            has_replacement_char=False,
        )

    if not text.strip():
        return FileEval(
            relative_path=relative_path,
            suffix=suffix,
            status="skipped",
            reason="empty_text",
            text_chars=0,
            node_count=0,
            edge_count=0,
            by_node_type={},
            by_relation_type={},
            has_replacement_char=False,
        )

    trimmed_text = text[:MAX_TEXT_CHARS]
    file_hash = _slug_hash(f"{relative_path}:{len(trimmed_text)}:{trimmed_text[:1000]}")
    payload = IngestRequest(
        tenant_id=tenant_id,
        source="module2",
        graph_mode="hybrid",
        documents=[
            {
                "file_name": file_path.name,
                "file_hash": file_hash,
                "track": "alignment-nonpdf",
                "text": trimmed_text,
            }
        ],
    )

    await _run_document_ingest_job(
        job_id=f"eval-{uuid.uuid4().hex[:10]}",
        batch_id=f"batch-{uuid.uuid4().hex[:10]}",
        payload=payload,
    )
    graph_file = await storage.get_graph_file(tenant_id=tenant_id, file_hash=file_hash)
    if not graph_file:
        return FileEval(
            relative_path=relative_path,
            suffix=suffix,
            status="skipped",
            reason="graph_file_missing",
            text_chars=len(trimmed_text),
            node_count=0,
            edge_count=0,
            by_node_type={},
            by_relation_type={},
            has_replacement_char=False,
        )

    artifact_graph = load_artifact_graph_snapshot(graph_file)
    if artifact_graph is None:
        return FileEval(
            relative_path=relative_path,
            suffix=suffix,
            status="skipped",
            reason="artifacts_unavailable",
            text_chars=len(trimmed_text),
            node_count=0,
            edge_count=0,
            by_node_type={},
            by_relation_type={},
            has_replacement_char=False,
        )

    nodes = list(artifact_graph.nodes)
    edges = list(artifact_graph.edges)
    by_node_type = dict(Counter(str(n.get("node_type") or "") for n in nodes))
    by_relation_type = dict(Counter(str(e.get("relation_type") or "") for e in edges))
    return FileEval(
        relative_path=relative_path,
        suffix=suffix,
        status="ok",
        reason=None,
        text_chars=len(trimmed_text),
        node_count=len(nodes),
        edge_count=len(edges),
        by_node_type=by_node_type,
        by_relation_type=by_relation_type,
        has_replacement_char=_has_replacement_char(nodes),
    )


def _aggregate(items: List[FileEval]) -> Dict[str, Any]:
    ok_items = [item for item in items if item.status == "ok"]
    skipped_items = [item for item in items if item.status != "ok"]
    node_type_counter: Counter[str] = Counter()
    relation_counter: Counter[str] = Counter()
    replacement_files = 0
    for item in ok_items:
        node_type_counter.update(item.by_node_type)
        relation_counter.update(item.by_relation_type)
        if item.has_replacement_char:
            replacement_files += 1
    return {
        "files_total": len(items),
        "files_ok": len(ok_items),
        "files_skipped": len(skipped_items),
        "replacement_char_files": replacement_files,
        "node_types_total": dict(node_type_counter),
        "relation_types_total": dict(relation_counter),
        "expected_node_types": ["Document", "Chunk", "Entity", "Community", "CommunityReport"],
        "expected_relations": ["has_chunk", "has_entity", "related_to", "in_community", "has_report"],
    }


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    dataset_root = Path(args.dataset_root).resolve()
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")

    storage = Module4Storage("postgresql://invalid")
    _set_runtime_ref("storage", storage)
    _get_runtime_ref("job_tasks").clear()

    tenant_id = args.tenant_id
    selected = list(_iter_nonpdf_files(dataset_root))
    if args.limit and args.limit > 0:
        selected = selected[: args.limit]

    results: List[FileEval] = []
    for file_path in selected:
        results.append(await _evaluate_file(storage=storage, dataset_root=dataset_root, file_path=file_path, tenant_id=tenant_id))

    summary = _aggregate(results)
    return {
        "dataset_root": str(dataset_root),
        "tenant_id": tenant_id,
        "limit": args.limit,
        "summary": summary,
        "files": [
            {
                "relative_path": item.relative_path,
                "suffix": item.suffix,
                "status": item.status,
                "reason": item.reason,
                "text_chars": item.text_chars,
                "node_count": item.node_count,
                "edge_count": item.edge_count,
                "by_node_type": item.by_node_type,
                "by_relation_type": item.by_relation_type,
                "has_replacement_char": item.has_replacement_char,
            }
            for item in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate non-PDF dataset alignment for module4 GraphRAG pipeline.")
    parser.add_argument(
        "--dataset-root",
        default=str(PROJECT_ROOT / "datasets"),
        help="Dataset root path. Defaults to project datasets folder.",
    )
    parser.add_argument("--tenant-id", default="alignment-nonpdf", help="Tenant id for in-memory graph scope.")
    parser.add_argument("--limit", type=int, default=0, help="Optional cap on number of files to process.")
    parser.add_argument(
        "--output",
        default=str(MODULE4_DIR / "runtime-data" / "nonpdf-alignment-report.json"),
        help="JSON report output path.",
    )
    args = parser.parse_args()

    report = asyncio.run(_run(args))
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
