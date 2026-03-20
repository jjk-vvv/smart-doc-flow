from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[3]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.ingest_pipeline import Assistant1IngestPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest document into assistant_1 vector store")
    parser.add_argument("--file-hash", required=True, help="Document file hash")
    parser.add_argument("--no-persist", action="store_true", help="Skip vector embedding and database persistence")
    args = parser.parse_args()

    pipeline = Assistant1IngestPipeline()
    result = pipeline.ingest(args.file_hash, persist=not args.no_persist)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
