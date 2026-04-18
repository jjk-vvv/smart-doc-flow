from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.module1.composition import build_app


def test_build_app_registers_prefixed_module1_routes() -> None:
    app = build_app()
    route_paths = {route.path for route in app.routes}

    assert "/module1/health" in route_paths
    assert "/health" not in route_paths
