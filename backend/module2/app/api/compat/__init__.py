"""Compatibility adapters for deprecated module2 API import paths."""

from .extraction_assistant_router import build_extraction_assistant_router
from .extraction_request_router import build_extraction_request_router
from .extraction_support_router import build_extraction_support_router
from .module4_sync_router import build_module4_sync_router
from .router_bundle import build_module2_routers
from .sync_router import build_sync_router

__all__ = [
    "build_extraction_assistant_router",
    "build_extraction_request_router",
    "build_extraction_support_router",
    "build_module4_sync_router",
    "build_module2_routers",
    "build_sync_router",
]
