from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from dotenv import load_dotenv  # noqa: E402
from app.core.parser import NativeDocumentParser  # noqa: E402

load_dotenv()
load_dotenv(MODULE2_ROOT / ".env")


def _table_stats(table_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_cells = 0
    valid_tables = 0
    one_row_tables = 0
    one_col_tables = 0
    row_counts: List[int] = []
    col_counts: List[int] = []
    source_counter: Dict[str, int] = {}

    for table in table_blocks:
        rows = int(table.get("row_count", 0) or 0)
        cols = int(table.get("col_count", 0) or 0)
        if rows <= 1:
            one_row_tables += 1
        if cols <= 1:
            one_col_tables += 1
        if rows >= 2 and cols >= 2:
            valid_tables += 1
        row_counts.append(rows)
        col_counts.append(cols)
        source = str(table.get("source", "unknown") or "unknown")
        source_counter[source] = source_counter.get(source, 0) + 1
        for row in table.get("rows", []):
            total_cells += len(row.get("cells", []))

    table_count = len(table_blocks)
    return {
        "table_count": table_count,
        "valid_table_count": valid_tables,
        "valid_table_ratio": round((valid_tables / float(table_count)), 4) if table_count else 0.0,
        "table_cells": total_cells,
        "avg_rows": round((sum(row_counts) / float(len(row_counts))), 2) if row_counts else 0.0,
        "avg_cols": round((sum(col_counts) / float(len(col_counts))), 2) if col_counts else 0.0,
        "one_row_tables": one_row_tables,
        "one_col_tables": one_col_tables,
        "sources": source_counter,
    }


def _eval_one(parser: NativeDocumentParser, file_path: Path, track: str) -> Dict[str, Any]:
    start = time.perf_counter()
    with file_path.open("rb") as fp:
        file_bytes = fp.read()
    markdown, bbox_map, table_blocks = parser.parse_document(
        file_name=file_path.name,
        file_bytes=file_bytes,
        track=track,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    stats = _table_stats(table_blocks)
    return {
        "file_name": file_path.name,
        "track": track,
        "size_bytes": len(file_bytes),
        "markdown_chars": len(markdown),
        "ref_count": len(bbox_map),
        "elapsed_ms": elapsed_ms,
        **stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate module2 parser on sample files.")
    parser.add_argument(
        "--files",
        nargs="+",
        required=False,
        default=[
            "中华人民共和国2024年国民经济和社会发展统计公报.pdf",
            "cts15-selected_ancillary_compounds-r-final-rev.pdf",
            "核燃料后处理工学.pdf",
        ],
        help="Input files to evaluate.",
    )
    parser.add_argument(
        "--tracks",
        nargs="+",
        default=["FastTrack"],
        choices=["FastTrack", "VisualTrack"],
        help="Tracks to evaluate.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON file path.",
    )
    args = parser.parse_args()

    out: Dict[str, Any] = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "results": []}
    native_parser = NativeDocumentParser()

    for file_raw in args.files:
        file_path = Path(file_raw)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists():
            out["results"].append(
                {
                    "file_name": file_raw,
                    "error": "file_not_found",
                }
            )
            continue

        for track in args.tracks:
            try:
                result = _eval_one(native_parser, file_path, track)
                out["results"].append(result)
            except Exception as exc:
                out["results"].append(
                    {
                        "file_name": file_path.name,
                        "track": track,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
