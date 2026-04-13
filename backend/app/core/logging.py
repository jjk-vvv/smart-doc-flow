from __future__ import annotations

import logging
import os


def configure_app_logging() -> None:
    level_name = str(os.getenv("GATEWAY_LOG_LEVEL", "INFO")).strip().upper() or "INFO"
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


__all__ = ["configure_app_logging"]
