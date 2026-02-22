from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader

MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from dotenv import load_dotenv  # noqa: E402
from app.core.parser import NativeDocumentParser  # noqa: E402

load_dotenv(dotenv_path=MODULE2_ROOT / ".env")


BENCHMARKS = [
    {
        "name": "cts15",
        "file_name": "cts15-selected_ancillary_compounds-r-final-rev.pdf",
        "size_bytes": 23863928,
        "start_page": 85,
        "end_page": 120,
        "gt_tables": 5,
        "gt_figures": 0,
    },
    {
        "name": "nuclear",
        "file_name": "核燃料后处理工学.pdf",
        "size_bytes": 16022495,
        "start_page": 40,
        "end_page": 72,
        "gt_tables": 20,
        "gt_figures": 19,
    },
    {
        "name": "national_bulletin",
        "file_name": "中华人民共和国2024年国民经济和社会发展统计公报.pdf",
        "size_bytes": 3558869,
        "start_page": 1,
        "end_page": 38,
        "gt_tables": 17,
        "gt_figures": 24,
    },
]


def _resolve_file(benchmark: Dict[str, Any]) -> Optional[Path]:
    expected = benchmark["file_name"]
    p = Path(expected)
    if p.exists():
        return p
    expected_size = int(benchmark["size_bytes"])
    for cand in Path.cwd().glob("*.pdf"):
        try:
            if cand.stat().st_size == expected_size:
                return cand
        except OSError:
            continue
    return None


def _safe_ratio(pred: int, gt: int) -> float:
    if gt <= 0:
        return 1.0 if pred <= 0 else 0.0
    return round(min(pred, gt) / float(gt), 4)


def _safe_precision(pred: int, gt: int) -> float:
    if pred <= 0:
        return 1.0 if gt <= 0 else 0.0
    return round(min(pred, gt) / float(pred), 4)


def _safe_f1(precision: float, recall: float) -> float:
    p = float(precision)
    r = float(recall)
    if p <= 0.0 or r <= 0.0:
        return 0.0
    return round((2.0 * p * r) / (p + r), 4)


def _in_range(page: int, start: int, end: int) -> bool:
    return start <= page <= end


def _evaluate_one(
    parser: NativeDocumentParser,
    benchmark: Dict[str, Any],
    file_path: Path,
    track: str,
) -> Dict[str, Any]:
    start_page = int(benchmark["start_page"])
    end_page = int(benchmark["end_page"])
    gt_tables = int(benchmark["gt_tables"])
    gt_figures = int(benchmark["gt_figures"])

    t0 = time.perf_counter()
    file_bytes = file_path.read_bytes()
    markdown, bbox_map, table_blocks = parser.parse_document(
        file_name=file_path.name,
        file_bytes=file_bytes,
        track=track,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    figure_blocks = parser.get_last_figure_blocks()

    tables_in_range = [
        t
        for t in table_blocks
        if _in_range(int(t.get("page", 0) or 0), start_page, end_page)
    ]
    valid_tables_in_range = [
        t
        for t in tables_in_range
        if int(t.get("row_count", 0) or 0) >= 2 and int(t.get("col_count", 0) or 0) >= 2
    ]
    figures_in_range = [
        f
        for f in figure_blocks
        if _in_range(int(f.get("page", 0) or 0), start_page, end_page)
    ]

    table_pages = sorted({int(t.get("page", 0) or 0) for t in tables_in_range if int(t.get("page", 0) or 0) > 0})
    figure_pages = sorted({int(f.get("page", 0) or 0) for f in figures_in_range if int(f.get("page", 0) or 0) > 0})

    table_sources: Dict[str, int] = {}
    for t in tables_in_range:
        source = str(t.get("source", "unknown") or "unknown")
        table_sources[source] = table_sources.get(source, 0) + 1
    figure_sources: Dict[str, int] = {}
    for f in figures_in_range:
        source = str(f.get("source", "unknown") or "unknown")
        figure_sources[source] = figure_sources.get(source, 0) + 1

    return {
        "benchmark": benchmark["name"],
        "file_name": file_path.name,
        "file_size_bytes": len(file_bytes),
        "total_pdf_pages": len(PdfReader(str(file_path)).pages),
        "track": track,
        "range": [start_page, end_page],
        "elapsed_ms": elapsed_ms,
        "markdown_chars": len(markdown),
        "ref_count": len(bbox_map),
        "ground_truth": {
            "tables": gt_tables,
            "figures": gt_figures,
        },
        "predicted": {
            "tables": len(tables_in_range),
            "valid_tables": len(valid_tables_in_range),
            "figures": len(figures_in_range),
        },
        "recall_like": {
            "tables": _safe_ratio(len(valid_tables_in_range), gt_tables),
            "figures": _safe_ratio(len(figures_in_range), gt_figures),
        },
        "precision_like": {
            "tables": _safe_precision(len(valid_tables_in_range), gt_tables),
            "figures": _safe_precision(len(figures_in_range), gt_figures),
        },
        "f1_like": {
            "tables": _safe_f1(
                _safe_precision(len(valid_tables_in_range), gt_tables),
                _safe_ratio(len(valid_tables_in_range), gt_tables),
            ),
            "figures": _safe_f1(
                _safe_precision(len(figures_in_range), gt_figures),
                _safe_ratio(len(figures_in_range), gt_figures),
            ),
        },
        "pages": {
            "table_pages": table_pages,
            "figure_pages": figure_pages,
        },
        "sources": {
            "table_sources": table_sources,
            "figure_sources": figure_sources,
        },
    }


def main() -> int:
    cli = argparse.ArgumentParser(description="Evaluate parser on 3 benchmark samples with page ranges.")
    cli.add_argument(
        "--track",
        choices=["FastTrack", "VisualTrack"],
        default="VisualTrack",
        help="Parser track to run.",
    )
    cli.add_argument(
        "--output",
        default="",
        help="Optional output JSON path.",
    )
    args = cli.parse_args()

    parser = NativeDocumentParser()
    out: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "track": args.track,
        "results": [],
    }

    for benchmark in BENCHMARKS:
        file_path = _resolve_file(benchmark)
        if file_path is None:
            out["results"].append(
                {
                    "benchmark": benchmark["name"],
                    "file_name": benchmark["file_name"],
                    "error": "file_not_found",
                }
            )
            continue
        try:
            out["results"].append(_evaluate_one(parser, benchmark, file_path, args.track))
        except Exception as exc:
            out["results"].append(
                {
                    "benchmark": benchmark["name"],
                    "file_name": file_path.name,
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
