from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_GENERIC_COMMANDS = {"python", "python3", "py"}


def _repo_root() -> Path:
    runtime_root = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
    if runtime_root:
        return Path(runtime_root).resolve()
    return Path(__file__).resolve().parents[6]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _candidate_python_bins(
    *,
    configured_python_bin: str | None = None,
    configured_query_python_bin: str | None = None,
) -> list[str]:
    repo_root = _repo_root()
    candidates = [
        str(configured_query_python_bin or "").strip(),
        str(configured_python_bin or "").strip(),
        str(repo_root / ".venv-module4-py311" / "Scripts" / "python.exe"),
        str(repo_root / ".venv-module4-py311" / "bin" / "python"),
        str(repo_root / ".venv" / "Scripts" / "python.exe"),
        str(repo_root / ".venv" / "bin" / "python"),
        sys.executable,
    ]
    return _unique(candidates)


@dataclass(frozen=True)
class GraphRAGPythonRuntime:
    python_bin: str
    exists: bool
    has_cli_main: bool
    has_legacy_index_module: bool
    has_api: bool

    @property
    def ready(self) -> bool:
        return self.has_cli_main or self.has_legacy_index_module

    @property
    def preferred_config_style(self) -> str:
        if self.has_cli_main:
            return "v3"
        if self.has_legacy_index_module:
            return "legacy"
        return "v3"

    @property
    def score(self) -> int:
        score = 0
        if self.has_cli_main:
            score += 100
        if self.has_api:
            score += 10
        if self.has_legacy_index_module:
            score += 1
        return score


@lru_cache(maxsize=16)
def probe_graphrag_python_runtime(python_bin: str) -> GraphRAGPythonRuntime:
    candidate = str(python_bin or "").strip()
    if not candidate:
        return GraphRAGPythonRuntime(
            python_bin="",
            exists=False,
            has_cli_main=False,
            has_legacy_index_module=False,
            has_api=False,
        )

    exists = True
    if os.path.isabs(candidate):
        exists = Path(candidate).exists()
    else:
        exists = shutil.which(candidate) is not None
    if not exists:
        return GraphRAGPythonRuntime(
            python_bin=candidate,
            exists=False,
            has_cli_main=False,
            has_legacy_index_module=False,
            has_api=False,
        )

    probe_script = (
        "import importlib.util, json\n"
        "def has(name):\n"
        "    try:\n"
        "        return importlib.util.find_spec(name) is not None\n"
        "    except Exception:\n"
        "        return False\n"
        "print(json.dumps({"
        "'has_cli_main': has('graphrag.cli.main'), "
        "'has_legacy_index_module': has('graphrag.index.__main__'), "
        "'has_api': has('graphrag.api')"
        "}))\n"
    )
    try:
        completed = subprocess.run(
            [candidate, "-c", probe_script],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except Exception:
        return GraphRAGPythonRuntime(
            python_bin=candidate,
            exists=True,
            has_cli_main=False,
            has_legacy_index_module=False,
            has_api=False,
        )

    try:
        payload = json.loads(str(completed.stdout or "").strip() or "{}")
    except Exception:
        payload = {}

    return GraphRAGPythonRuntime(
        python_bin=candidate,
        exists=True,
        has_cli_main=bool(payload.get("has_cli_main")),
        has_legacy_index_module=bool(payload.get("has_legacy_index_module")),
        has_api=bool(payload.get("has_api")),
    )


def choose_graphrag_python_bin(
    *,
    configured_python_bin: str | None = None,
    configured_query_python_bin: str | None = None,
) -> str:
    configured = str(configured_python_bin or "").strip()
    query_configured = str(configured_query_python_bin or "").strip()

    if configured and configured.lower() not in _GENERIC_COMMANDS:
        runtime = probe_graphrag_python_runtime(configured)
        if runtime.ready:
            return configured

    if query_configured and query_configured.lower() not in _GENERIC_COMMANDS:
        runtime = probe_graphrag_python_runtime(query_configured)
        if runtime.ready:
            return query_configured

    best_runtime: GraphRAGPythonRuntime | None = None
    for candidate in _candidate_python_bins(
        configured_python_bin=configured,
        configured_query_python_bin=query_configured,
    ):
        runtime = probe_graphrag_python_runtime(candidate)
        if not runtime.ready:
            continue
        if best_runtime is None or runtime.score > best_runtime.score:
            best_runtime = runtime

    if best_runtime is not None:
        return best_runtime.python_bin
    if configured:
        return configured
    if query_configured:
        return query_configured
    return sys.executable


def resolve_graphrag_config_style(
    requested_style: str | None,
    *,
    python_bin: str | None = None,
    configured_python_bin: str | None = None,
    configured_query_python_bin: str | None = None,
) -> str:
    normalized = str(requested_style or "").strip().lower()
    if normalized in {"v3", "legacy"}:
        return normalized

    effective_python_bin = str(python_bin or "").strip() or choose_graphrag_python_bin(
        configured_python_bin=configured_python_bin,
        configured_query_python_bin=configured_query_python_bin,
    )
    runtime = probe_graphrag_python_runtime(effective_python_bin)
    return runtime.preferred_config_style
