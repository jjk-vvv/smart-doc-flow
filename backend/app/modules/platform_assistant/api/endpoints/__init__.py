from .bootstrap import router as bootstrap_router
from .catalog import router as catalog_router
from .chat import router as chat_router
from .diagnostics import router as diagnostics_router
from .health import router as health_router

__all__ = ["bootstrap_router", "catalog_router", "chat_router", "diagnostics_router", "health_router"]
