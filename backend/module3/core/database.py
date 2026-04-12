from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import read_database_url


class Base(DeclarativeBase):
    pass


_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None
_INIT_LOCK = threading.Lock()
_SCHEMA_READY = False


def database_enabled() -> bool:
    return bool(read_database_url())


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        database_url = read_database_url()
        if not database_url:
            raise RuntimeError("MODULE3_DATABASE_URL is not configured")
        try:
            _ENGINE = create_engine(database_url, pool_pre_ping=True, future=True)
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Module3 PostgreSQL driver is missing. Install psycopg[binary] before enabling MODULE3_DATABASE_URL."
            ) from exc
    return _ENGINE


def get_session_factory() -> sessionmaker[Session]:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)
    return _SESSION_FACTORY


def init_database() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY or not database_enabled():
        return
    with _INIT_LOCK:
        if _SCHEMA_READY:
            return
        from ..models import db_tables  # noqa: F401

        Base.metadata.create_all(bind=get_engine())
        _SCHEMA_READY = True


@contextmanager
def session_scope() -> Iterator[Session]:
    if not database_enabled():
        raise RuntimeError("Module3 database is not enabled")
    init_database()
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "Base",
    "database_enabled",
    "get_engine",
    "get_session_factory",
    "init_database",
    "session_scope",
]
