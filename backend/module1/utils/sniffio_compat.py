from __future__ import annotations

import asyncio


class AsyncLibraryNotFoundError(RuntimeError):
    pass


def current_async_library() -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError as exc:
        raise AsyncLibraryNotFoundError("no async library detected") from exc

    return "asyncio"
