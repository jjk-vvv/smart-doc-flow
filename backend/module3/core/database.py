from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import read_database_url


class Base(DeclarativeBase):
    pass


_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None
_INIT_LOCK = threading.Lock()
_SCHEMA_READY = False
_DATABASE_DISABLED_REASON: str | None = None


def database_enabled() -> bool:
    return bool(read_database_url()) and _DATABASE_DISABLED_REASON is None


def get_engine() -> Engine:
    global _ENGINE
    if _DATABASE_DISABLED_REASON is not None:
        raise RuntimeError(_DATABASE_DISABLED_REASON)
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


def _ensure_owner_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    owner_tables = (
        "module3_templates",
        "module3_docsets",
        "module3_runs",
    )

    with engine.begin() as connection:
        for table_name in owner_tables:
            if table_name not in table_names:
                continue

            existing_columns = {str(item.get("name") or "").strip() for item in inspector.get_columns(table_name)}
            if "owner_id" not in existing_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        "ADD COLUMN owner_id VARCHAR(128) NOT NULL DEFAULT 'default'"
                    )
                )

            connection.execute(
                text(
                    f"UPDATE {table_name} "
                    "SET owner_id = 'default' "
                    "WHERE owner_id IS NULL OR TRIM(owner_id) = ''"
                )
            )

            try:
                connection.execute(
                    text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_owner_id ON {table_name} (owner_id)")
                )
            except Exception:
                # Index creation differences between engines are non-fatal for runtime correctness.
                continue


def init_database() -> None:
    global _SCHEMA_READY, _DATABASE_DISABLED_REASON
    if _SCHEMA_READY or not database_enabled():
        return
    with _INIT_LOCK:
        if _SCHEMA_READY:
            return
        try:
            from ..models import db_tables  # noqa: F401

            engine = get_engine()
            Base.metadata.create_all(bind=engine)
            _ensure_owner_columns(engine)
            _SCHEMA_READY = True
        except Exception as exc:
            _DATABASE_DISABLED_REASON = f"Module3 database disabled: {exc}"


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
