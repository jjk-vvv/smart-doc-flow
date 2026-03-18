from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.db.storage import Module4Storage, _dsn_connection_candidates


def test_dsn_candidates_add_ipv4_fallback_for_localhost() -> None:
    dsn = "postgresql://postgres:postgres@localhost:5433/Knowledge_Graph"
    assert _dsn_connection_candidates(dsn) == [
        "postgresql://postgres:postgres@localhost:5433/Knowledge_Graph",
        "postgresql://postgres:postgres@127.0.0.1:5433/Knowledge_Graph",
    ]


def test_dsn_candidates_keep_remote_hosts_unchanged() -> None:
    dsn = "postgresql://postgres:postgres@db.internal:5433/Knowledge_Graph"
    assert _dsn_connection_candidates(dsn) == [dsn]


def test_connect_retries_ipv4_when_localhost_candidate_fails(monkeypatch) -> None:
    monkeypatch.setenv("MODULE4_FORCE_MEMORY_MODE", "0")
    attempts: list[str] = []

    async def fake_create_pool(dsn: str, **_: object) -> object:
        attempts.append(dsn)
        if "localhost" in dsn:
            raise ConnectionError("connection was closed in the middle of operation")
        return object()

    fake_asyncpg = SimpleNamespace(create_pool=fake_create_pool)
    monkeypatch.setitem(sys.modules, "asyncpg", fake_asyncpg)

    async def _noop(self: Module4Storage) -> None:
        return None

    monkeypatch.setattr(Module4Storage, "_init_schema", _noop)
    monkeypatch.setattr(Module4Storage, "ensure_default_rules", _noop)

    async def _exercise() -> Module4Storage:
        storage = Module4Storage("postgresql://postgres:postgres@localhost:5433/Knowledge_Graph")
        await storage.connect()
        return storage

    storage = asyncio.run(_exercise())

    assert attempts == [
        "postgresql://postgres:postgres@localhost:5433/Knowledge_Graph",
        "postgresql://postgres:postgres@127.0.0.1:5433/Knowledge_Graph",
    ]
    assert storage.diagnostics()["db_connected"] is True


def test_connect_raises_when_all_candidates_fail(monkeypatch) -> None:
    monkeypatch.setenv("MODULE4_FORCE_MEMORY_MODE", "0")

    async def fake_create_pool(dsn: str, **_: object) -> object:
        raise ConnectionError(f"failed for {dsn}")

    fake_asyncpg = SimpleNamespace(create_pool=fake_create_pool)
    monkeypatch.setitem(sys.modules, "asyncpg", fake_asyncpg)

    async def _noop(self: Module4Storage) -> None:
        return None

    monkeypatch.setattr(Module4Storage, "_init_schema", _noop)
    monkeypatch.setattr(Module4Storage, "ensure_default_rules", _noop)

    async def _exercise() -> None:
        storage = Module4Storage("postgresql://postgres:postgres@localhost:5433/Knowledge_Graph")
        await storage.connect()

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(_exercise())

    assert "127.0.0.1" in str(exc_info.value)


def test_connect_rejects_force_memory_mode(monkeypatch) -> None:
    monkeypatch.setenv("MODULE4_FORCE_MEMORY_MODE", "1")

    async def _exercise() -> None:
        storage = Module4Storage("postgresql://postgres:postgres@localhost:5433/Knowledge_Graph")
        await storage.connect()

    with pytest.raises(RuntimeError, match="no longer supported"):
        asyncio.run(_exercise())
