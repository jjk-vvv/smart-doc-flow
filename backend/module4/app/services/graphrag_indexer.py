from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .neo4j_graph import Neo4jSettings
from .oneapi_runtime import GraphRAGRuntimeSettings
from .prompt_registry import PromptRegistry


def _module4_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _local_venv_python() -> Path:
    root = _module4_root()
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _resolve_python_bin() -> str:
    configured = str(os.getenv("MODULE4_GRAPHRAG_PYTHON_BIN", "") or "").strip()
    generic_commands = {"python", "python3", "py"}
    if configured and configured.lower() not in generic_commands:
        return configured

    local_venv = _local_venv_python()
    if local_venv.exists():
        return str(local_venv)

    if configured:
        return configured
    return sys.executable


def _workspace_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _find_latest_timestamp_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = [path for path in root.iterdir() if path.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


def _resolve_output_layout(output_root: Path) -> tuple[Path | None, Path | None, Path | None]:
    if not output_root.exists():
        return None, None, None

    candidates = [path for path in output_root.iterdir() if path.is_dir()]
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        artifacts_dir = candidate / "artifacts"
        reports_dir = candidate / "reports"
        if artifacts_dir.exists():
            return candidate, artifacts_dir, reports_dir if reports_dir.exists() else None

    root_artifacts_dir = output_root / "artifacts"
    root_reports_dir = output_root / "reports"
    if root_artifacts_dir.exists():
        return output_root, root_artifacts_dir, root_reports_dir if root_reports_dir.exists() else None

    latest_dir = candidates[0] if candidates else None
    if latest_dir is None:
        return None, None, None
    reports_dir = latest_dir / "reports"
    return latest_dir, None, reports_dir if reports_dir.exists() else None


def _rewrite_skip_workflows(settings_text: str, workflows: List[str]) -> str:
    rendered = ", ".join(json.dumps(str(item), ensure_ascii=False) for item in workflows)
    replacement = f"skip_workflows: [{rendered}]"
    lines = settings_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("skip_workflows:"):
            lines[index] = replacement
            return "\n".join(lines) + ("\n" if settings_text.endswith("\n") else "")
    return f"{replacement}\n{settings_text}"


def _should_retry_without_community_reports(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return (
        "create_final_community_reports" in text
        and (
            "Failed to generate valid JSON output" in text
            or "error generating community report" in text
            or "error running workflow create_final_community_reports" in text
        )
    )


@dataclass(frozen=True)
class GraphRAGIndexResult:
    command: List[str]
    log_path: Path
    output_dir: Path | None
    artifacts_dir: Path | None
    reports_dir: Path | None
    skipped_workflows: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphRAGIndexError(RuntimeError):
    category: str
    message: str
    log_path: Path
    exit_code: int | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class GraphRAGDependencyProbe:
    configured: bool
    reachable: Optional[bool] = None
    missing_fields: List[str] = field(default_factory=list)
    error_message: str | None = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "configured": self.configured,
            "reachable": self.reachable,
            "missing_fields": list(self.missing_fields),
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class GraphRAGRuntimeProbe:
    ready: bool
    check_mode: str
    python_bin: str
    python_bin_exists: bool
    graphrag_module_available: bool
    module_error_message: str | None
    prompt_assets_root: str
    prompt_assets_ok: bool
    missing_prompt_assets: List[str] = field(default_factory=list)
    config_missing_fields: List[str] = field(default_factory=list)
    runtime_versions: Dict[str, str] = field(default_factory=dict)
    tiktoken_encoding_ready: Optional[bool] = None
    tiktoken_encoding_error_message: str | None = None
    oneapi: GraphRAGDependencyProbe = field(default_factory=lambda: GraphRAGDependencyProbe(configured=False))
    neo4j: GraphRAGDependencyProbe = field(default_factory=lambda: GraphRAGDependencyProbe(configured=False))

    def as_dict(self) -> Dict[str, object]:
        return {
            "ready": self.ready,
            "check_mode": self.check_mode,
            "python_bin": self.python_bin,
            "python_bin_exists": self.python_bin_exists,
            "graphrag_module_available": self.graphrag_module_available,
            "module_error_message": self.module_error_message,
            "prompt_assets_root": self.prompt_assets_root,
            "prompt_assets_ok": self.prompt_assets_ok,
            "missing_prompt_assets": list(self.missing_prompt_assets),
            "config_missing_fields": list(self.config_missing_fields),
            "runtime_versions": dict(self.runtime_versions),
            "tiktoken_encoding_ready": self.tiktoken_encoding_ready,
            "tiktoken_encoding_error_message": self.tiktoken_encoding_error_message,
            "oneapi": self.oneapi.as_dict(),
            "neo4j": self.neo4j.as_dict(),
        }

    def summary(self) -> str:
        parts: List[str] = []
        if self.config_missing_fields:
            parts.append(f"missing config: {', '.join(self.config_missing_fields)}")
        if not self.python_bin_exists:
            parts.append(f"python executable not found: {self.python_bin}")
        if not self.graphrag_module_available:
            parts.append(self.module_error_message or "graphrag package is not available")
        if self.missing_prompt_assets:
            parts.append(f"missing prompt assets: {', '.join(self.missing_prompt_assets)}")
        if self.tiktoken_encoding_ready is False:
            parts.append(self.tiktoken_encoding_error_message or "tiktoken encoding is not available")
        if self.oneapi.configured and self.oneapi.reachable is False:
            parts.append(self.oneapi.error_message or "OneAPI endpoint is not reachable")
        if not parts:
            parts.append("runtime ready")
        return "; ".join(parts)


def _python_bin_exists(python_bin: str) -> bool:
    if not python_bin:
        return False
    candidate = Path(python_bin)
    if candidate.is_absolute():
        return candidate.exists()
    return shutil.which(python_bin) is not None


def _python_supports_module(python_bin: str, module_name: str) -> tuple[bool, str | None]:
    if not _python_bin_exists(python_bin):
        return False, f"Configured python executable not found: {python_bin}"
    try:
        completed = subprocess.run(
            [
                python_bin,
                "-c",
                (
                    "import importlib.util, sys; "
                    f"sys.stdout.write('1' if importlib.util.find_spec({module_name!r}) else '0')"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out while checking module availability: {module_name}"
    except FileNotFoundError:
        return False, f"Configured python executable not found: {python_bin}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"Unable to inspect python runtime: {type(exc).__name__}: {exc}"

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return False, detail or f"Module check failed for {module_name}"
    if (completed.stdout or "").strip() == "1":
        return True, None
    return False, f"Python runtime does not have module installed: {module_name}"


def _python_runtime_details(python_bin: str) -> tuple[Dict[str, str], Optional[bool], str | None]:
    if not _python_bin_exists(python_bin):
        return {}, None, f"Configured python executable not found: {python_bin}"

    try:
        completed = subprocess.run(
            [
                python_bin,
                "-c",
                (
                    "import json, importlib.metadata as md\n"
                    "payload = {'versions': {}, 'tiktoken_encoding_ready': None, 'tiktoken_encoding_error': None}\n"
                    "for name in ('python', 'graphrag', 'tiktoken', 'pandas', 'datashaper'):\n"
                    "    try:\n"
                    "        if name == 'python':\n"
                    "            import sys\n"
                    "            payload['versions'][name] = sys.version.split()[0]\n"
                    "        else:\n"
                    "            payload['versions'][name] = md.version(name)\n"
                    "    except Exception:\n"
                    "        continue\n"
                    "try:\n"
                    "    import tiktoken\n"
                    "    tiktoken.get_encoding('cl100k_base')\n"
                    "    payload['tiktoken_encoding_ready'] = True\n"
                    "except Exception as exc:\n"
                    "    payload['tiktoken_encoding_ready'] = False\n"
                    "    payload['tiktoken_encoding_error'] = f'{type(exc).__name__}: {exc}'\n"
                    "print(json.dumps(payload, ensure_ascii=False))\n"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, None, "Timed out while inspecting python runtime details"
    except FileNotFoundError:
        return {}, None, f"Configured python executable not found: {python_bin}"
    except Exception as exc:  # pragma: no cover - defensive
        return {}, None, f"Unable to inspect python runtime details: {type(exc).__name__}: {exc}"

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return {}, None, detail or "Python runtime detail inspection failed"

    try:
        payload = json.loads((completed.stdout or "").strip() or "{}")
    except Exception as exc:
        return {}, None, f"Unable to parse python runtime details: {type(exc).__name__}: {exc}"

    raw_versions = payload.get("versions") if isinstance(payload.get("versions"), dict) else {}
    versions = {str(key): str(value) for key, value in raw_versions.items() if str(value).strip()}
    encoding_ready = payload.get("tiktoken_encoding_ready")
    if encoding_ready is not None:
        encoding_ready = bool(encoding_ready)
    encoding_error = str(payload.get("tiktoken_encoding_error") or "").strip() or None
    return versions, encoding_ready, encoding_error


def _missing_prompt_assets(runtime: GraphRAGRuntimeSettings) -> List[str]:
    registry = PromptRegistry(asset_root=runtime.prompt_assets_root, overrides=runtime.prompt_overrides())
    missing: List[str] = []
    for key in registry.keys():
        path = registry.prompt_path(key)
        if not path.exists():
            missing.append(str(path))
    return missing


def _oneapi_status_url(api_base: str) -> str:
    base = str(api_base or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/api/status"


def _probe_oneapi(runtime: GraphRAGRuntimeSettings, *, check_remote: bool) -> GraphRAGDependencyProbe:
    missing_fields = ["MODULE4_GRAPHRAG_API_BASE"] if not runtime.api_base else []
    configured = not missing_fields
    if not configured:
        return GraphRAGDependencyProbe(configured=False, reachable=None, missing_fields=missing_fields)
    if not check_remote:
        return GraphRAGDependencyProbe(configured=True, reachable=None, missing_fields=[])

    url = _oneapi_status_url(runtime.api_base)
    request = urllib.request.Request(url, headers={"User-Agent": "module4-healthz/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            body = response.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}
        ok = bool(payload.get("success", True))
        error_message = None if ok else f"OneAPI status probe returned success={payload.get('success')}"
        return GraphRAGDependencyProbe(configured=True, reachable=ok, missing_fields=[], error_message=error_message)
    except urllib.error.HTTPError as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"OneAPI status probe failed with HTTP {exc.code}",
        )
    except Exception as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"OneAPI status probe failed: {type(exc).__name__}: {exc}",
        )


def _probe_neo4j(neo4j: Neo4jSettings, *, check_remote: bool) -> GraphRAGDependencyProbe:
    missing_fields = neo4j.missing_fields()
    configured = not missing_fields
    if not configured:
        return GraphRAGDependencyProbe(configured=False, reachable=None, missing_fields=missing_fields)
    if not check_remote:
        return GraphRAGDependencyProbe(configured=True, reachable=None, missing_fields=[])

    try:
        from neo4j import GraphDatabase
    except Exception as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"Neo4j driver import failed: {type(exc).__name__}: {exc}",
        )

    driver = None
    try:
        driver = GraphDatabase.driver(
            neo4j.uri,
            auth=(neo4j.username, neo4j.password),
            connection_timeout=3.0,
            max_connection_pool_size=1,
        )
        driver.verify_connectivity()
        return GraphRAGDependencyProbe(configured=True, reachable=True, missing_fields=[])
    except Exception as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"Neo4j connectivity probe failed: {type(exc).__name__}: {exc}",
        )
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception:  # pragma: no cover - defensive
                pass


class GraphRAGIndexer:
    def __init__(self) -> None:
        self.python_bin = _resolve_python_bin()
        self.timeout_sec = max(60, int(os.getenv("MODULE4_GRAPHRAG_INDEX_TIMEOUT_SEC", "7200")))

    def probe(
        self,
        runtime: GraphRAGRuntimeSettings | None = None,
        neo4j: Neo4jSettings | None = None,
        *,
        check_remote: bool = False,
    ) -> GraphRAGRuntimeProbe:
        runtime = runtime or GraphRAGRuntimeSettings.from_env()
        neo4j = neo4j or Neo4jSettings.from_env()
        config_missing_fields = runtime.missing_fields()
        missing_prompt_assets = _missing_prompt_assets(runtime)
        python_exists = _python_bin_exists(self.python_bin)
        module_available, module_error = _python_supports_module(self.python_bin, "graphrag")
        runtime_versions, tiktoken_encoding_ready, tiktoken_encoding_error = _python_runtime_details(self.python_bin)
        oneapi_probe = _probe_oneapi(runtime, check_remote=check_remote)
        neo4j_probe = _probe_neo4j(neo4j, check_remote=check_remote)

        oneapi_ok = oneapi_probe.configured
        if check_remote:
            oneapi_ok = oneapi_probe.reachable is True

        ready = (
            not config_missing_fields
            and python_exists
            and module_available
            and not missing_prompt_assets
            and tiktoken_encoding_ready is not False
            and oneapi_ok
        )

        return GraphRAGRuntimeProbe(
            ready=ready,
            check_mode="deep" if check_remote else "basic",
            python_bin=self.python_bin,
            python_bin_exists=python_exists,
            graphrag_module_available=module_available,
            module_error_message=module_error,
            prompt_assets_root=str(runtime.prompt_assets_root),
            prompt_assets_ok=not missing_prompt_assets,
            missing_prompt_assets=missing_prompt_assets,
            config_missing_fields=config_missing_fields,
            runtime_versions=runtime_versions,
            tiktoken_encoding_ready=tiktoken_encoding_ready,
            tiktoken_encoding_error_message=tiktoken_encoding_error,
            oneapi=oneapi_probe,
            neo4j=neo4j_probe,
        )

    def run(self, workspace_dir: Path) -> GraphRAGIndexResult:
        workspace_dir = workspace_dir.resolve()
        env = os.environ.copy()
        env.update(_workspace_env_file(workspace_dir / ".env"))

        log_path = workspace_dir / "graphrag-index.log"
        command = [self.python_bin, "-m", "graphrag.index", "--root", str(workspace_dir)]

        def _execute() -> subprocess.CompletedProcess[str]:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"$ {' '.join(command)}\n")
                log_file.flush()
                try:
                    return subprocess.run(
                        command,
                        cwd=str(workspace_dir),
                        env=env,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=self.timeout_sec,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise GraphRAGIndexError(
                        category="index_timeout",
                        message=f"GraphRAG index timed out after {self.timeout_sec}s. See {log_path}",
                        log_path=log_path,
                    ) from exc

        skipped_workflows: List[str] = []
        completed = _execute()
        try:
            log_path.touch(exist_ok=True)
        except Exception:  # pragma: no cover - defensive
            pass

        if completed.returncode != 0:
            settings_path = workspace_dir / "settings.yaml"
            if settings_path.exists() and _should_retry_without_community_reports(log_path):
                skipped_workflows = ["create_final_community_reports"]
                original = settings_path.read_text(encoding="utf-8")
                updated = _rewrite_skip_workflows(original, skipped_workflows)
                if updated != original:
                    settings_path.write_text(updated, encoding="utf-8")
                with log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(
                        "\n# module4 retry: skip_workflows=[\"create_final_community_reports\"] due to unstable community report JSON\n"
                    )
                completed = _execute()
            if completed.returncode != 0:
                raise GraphRAGIndexError(
                    category="index_process_failed",
                    message=f"GraphRAG index failed with exit code {completed.returncode}. See {log_path}",
                    log_path=log_path,
                    exit_code=completed.returncode,
                )

        output_root = workspace_dir / "output"
        output_dir, artifacts_dir, reports_dir = _resolve_output_layout(output_root)
        if not output_dir or not artifacts_dir or not artifacts_dir.exists():
            raise GraphRAGIndexError(
                category="artifacts_missing",
                message=f"GraphRAG index finished but no artifacts directory was produced under {output_root}",
                log_path=log_path,
            )

        return GraphRAGIndexResult(
            command=command,
            log_path=log_path,
            output_dir=output_dir,
            artifacts_dir=artifacts_dir,
            reports_dir=reports_dir if reports_dir and reports_dir.exists() else None,
            skipped_workflows=skipped_workflows,
        )

    def inspect_output(self, workspace_dir: Path) -> GraphRAGIndexResult:
        workspace_dir = workspace_dir.resolve()
        log_path = workspace_dir / "graphrag-index.log"
        command = [self.python_bin, "-m", "graphrag.index", "--root", str(workspace_dir)]
        output_root = workspace_dir / "output"
        output_dir, artifacts_dir, reports_dir = _resolve_output_layout(output_root)
        return GraphRAGIndexResult(
            command=command,
            log_path=log_path,
            output_dir=output_dir,
            artifacts_dir=artifacts_dir,
            reports_dir=reports_dir if reports_dir and reports_dir.exists() else None,
            skipped_workflows=[],
        )
