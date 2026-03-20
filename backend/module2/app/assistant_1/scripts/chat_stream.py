from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[3]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.stream_runtime import Assistant1StreamingRuntime


async def _run(args: argparse.Namespace) -> None:
    runtime = Assistant1StreamingRuntime()
    async for chunk in runtime.stream_chat(
        user_message=args.message,
        file_hash=args.file_hash,
        max_steps=args.max_steps,
        top_k=args.top_k,
        session_id=args.session_id,
        debug=args.debug,
    ):
        sys.stdout.write(chunk.decode("utf-8", errors="ignore"))
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run assistant_1 SSE chat stream in the terminal")
    parser.add_argument("--message", required=True, help="User message")
    parser.add_argument("--file-hash", default="", help="Optional default file hash")
    parser.add_argument("--session-id", default="", help="Optional session id")
    parser.add_argument("--max-steps", type=int, default=6, help="Maximum tool rounds")
    parser.add_argument("--top-k", type=int, default=5, help="Default retrieval top-k")
    parser.add_argument("--debug", action="store_true", help="Emit debug-visible events")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
