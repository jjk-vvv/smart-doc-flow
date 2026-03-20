from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[3]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.agent_runtime import Assistant1AgentRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="Run assistant_1 chat agent with tool calling")
    parser.add_argument("--message", required=True, help="User message")
    parser.add_argument("--file-hash", default="", help="Optional default file hash for this turn")
    parser.add_argument("--max-steps", type=int, default=6, help="Maximum function-calling rounds")
    parser.add_argument("--top-k", type=int, default=5, help="Default retrieval top-k")
    args = parser.parse_args()

    runtime = Assistant1AgentRuntime()
    result = runtime.chat(
        args.message,
        file_hash=args.file_hash,
        max_steps=args.max_steps,
        top_k=args.top_k,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
