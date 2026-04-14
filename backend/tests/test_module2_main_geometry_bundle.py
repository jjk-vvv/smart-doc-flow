from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_geometry_bundle_module = import_module("app.modules.module2.bootstrap.geometry")


def test_build_module2_main_geometry_bundle_exposes_expected_geometry_helpers() -> None:
    bundle = main_geometry_bundle_module.build_module2_main_geometry_bundle()

    assert bundle.page_from_bbox([1, 0.1, 0.1, 0.2, 0.2]) == 1
    assert bundle.normalize_bbox([0.1, 0.2, 0.3, 0.4], page_hint=2) == [2.0, 0.1, 0.2, 0.3, 0.4]
    assert bundle.is_meaningful_bbox([1, 0.1, 0.1, 0.2, 0.2]) is True
    assert bundle.is_meaningful_bbox([1, 0.0, 0.0, 1.0, 1.0]) is False
