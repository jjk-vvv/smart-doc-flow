from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = MODULE2_ROOT.parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.module2.assistant_1.retrieval_pipeline import Assistant1RetrievalPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Query assistant_1 pgvector knowledge store")
    parser.add_argument("--query", required=True, help="Natural language query")
    parser.add_argument("--file-hash", default="", help="Optional file hash filter")
    parser.add_argument("--unit-type", action="append", default=[], help="Optional unit type filter; repeatable")
    parser.add_argument("--top-k", type=int, default=8, help="Top K matches")
    args = parser.parse_args()

    pipeline = Assistant1RetrievalPipeline()
    result = pipeline.query(
        args.query,
        file_hash=args.file_hash,
        unit_types=args.unit_type,
        top_k=args.top_k,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
