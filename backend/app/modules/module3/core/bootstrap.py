from __future__ import annotations

from .database import database_enabled, init_database
from ..services.storage_service import ensure_storage_dirs


def ensure_module3_storage() -> None:
    ensure_storage_dirs()
    if database_enabled():
        init_database()


__all__ = ["ensure_module3_storage"]
