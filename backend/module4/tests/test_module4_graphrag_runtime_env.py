from __future__ import annotations

import sys
from pathlib import Path


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag.indexer import _resolve_python_bin  # noqa: E402


def test_graphrag_runtime_prefers_repo_root_module4_venv(monkeypatch, tmp_path: Path) -> None:
    repo_python = tmp_path / ".venv-module4-py311" / "Scripts" / "python.exe"
    local_python = tmp_path / "backend" / "module4" / ".venv" / "Scripts" / "python.exe"
    repo_python.parent.mkdir(parents=True)
    local_python.parent.mkdir(parents=True)
    repo_python.write_text("", encoding="utf-8")
    local_python.write_text("", encoding="utf-8")

    monkeypatch.setenv("SMART_DOC_FLOW_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", "python")
    monkeypatch.setattr("app.services.graphrag.indexer._module4_root", lambda: (tmp_path / "backend" / "module4"))

    assert Path(_resolve_python_bin()) == repo_python
