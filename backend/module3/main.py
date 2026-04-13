from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from backend.module3.app.main import app, create_app
    from backend.module3.tools.module3_tool import main as service_main
else:
    from .app.main import app, create_app
    from .tools.module3_tool import main as service_main


def main() -> None:
    service_main()


if __name__ == "__main__":
    main()


__all__ = ["app", "create_app", "main"]
