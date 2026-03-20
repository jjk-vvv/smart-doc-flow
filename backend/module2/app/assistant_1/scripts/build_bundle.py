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
    parser = argparse.ArgumentParser(description="Build assistant_1 merged markdown and knowledge units")
    parser.add_argument("--file-hash", required=True, help="Document file hash")
    args = parser.parse_args()

    pipeline = Assistant1IngestPipeline()
    result = pipeline.build_bundle(args.file_hash)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
