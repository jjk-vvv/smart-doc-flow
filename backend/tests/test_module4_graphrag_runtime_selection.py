from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


runtime_selection = import_module("app.modules.module4.services.graphrag.runtime_selection")
indexer_module = import_module("app.modules.module4.services.graphrag.indexer")


def test_choose_graphrag_python_bin_prefers_complete_v3_runtime(monkeypatch) -> None:
    def _probe(candidate: str):
        mapping = {
            "python": runtime_selection.GraphRAGPythonRuntime(
                python_bin="python",
                exists=True,
                has_cli_main=False,
                has_legacy_index_module=True,
                has_api=False,
            ),
            "D:/py311/python.exe": runtime_selection.GraphRAGPythonRuntime(
                python_bin="D:/py311/python.exe",
                exists=True,
                has_cli_main=True,
                has_legacy_index_module=False,
                has_api=True,
            ),
        }
        return mapping.get(
            candidate,
            runtime_selection.GraphRAGPythonRuntime(
                python_bin=candidate,
                exists=False,
                has_cli_main=False,
                has_legacy_index_module=False,
                has_api=False,
            ),
        )

    monkeypatch.setattr(runtime_selection, "probe_graphrag_python_runtime", _probe)
    monkeypatch.setattr(
        runtime_selection,
        "_candidate_python_bins",
        lambda **_kwargs: ["D:/py311/python.exe", "python"],
    )

    chosen = runtime_selection.choose_graphrag_python_bin(
        configured_python_bin="python",
        configured_query_python_bin="D:/py311/python.exe",
    )

    assert chosen == "D:/py311/python.exe"


def test_resolve_graphrag_config_style_follows_runtime_capability(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_selection,
        "probe_graphrag_python_runtime",
        lambda candidate: runtime_selection.GraphRAGPythonRuntime(
            python_bin=candidate,
            exists=True,
            has_cli_main=False,
            has_legacy_index_module=True,
            has_api=False,
        ),
    )

    assert runtime_selection.resolve_graphrag_config_style("auto", python_bin="python") == "legacy"
    assert runtime_selection.resolve_graphrag_config_style("v3", python_bin="python") == "v3"


def test_build_index_command_uses_v3_cli_when_runtime_supports_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        indexer_module,
        "probe_graphrag_python_runtime",
        lambda _candidate: runtime_selection.GraphRAGPythonRuntime(
            python_bin="D:/py311/python.exe",
            exists=True,
            has_cli_main=True,
            has_legacy_index_module=False,
            has_api=True,
        ),
    )

    command = indexer_module._build_index_command(
        python_bin="D:/py311/python.exe",
        workspace_dir=tmp_path,
        workspace_env={
            "GRAPHRAG_CONFIG_STYLE": "v3",
            "GRAPHRAG_INDEXING_METHOD": "fast",
        },
    )

    assert command[:3] == ["D:/py311/python.exe", "-c", "from graphrag.cli.main import app; app()"]
    assert command[3:6] == ["index", "--root", str(tmp_path)]
    assert command[-2:] == ["--method", "fast"]
    assert indexer_module._append_no_cache_flag(command)[-1] == "--no-cache"


def test_build_index_command_uses_legacy_module_when_only_legacy_runtime_exists(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        indexer_module,
        "probe_graphrag_python_runtime",
        lambda _candidate: runtime_selection.GraphRAGPythonRuntime(
            python_bin="python",
            exists=True,
            has_cli_main=False,
            has_legacy_index_module=True,
            has_api=False,
        ),
    )

    command = indexer_module._build_index_command(
        python_bin="python",
        workspace_dir=tmp_path,
        workspace_env={"GRAPHRAG_CONFIG_STYLE": "legacy"},
    )

    assert command == ["python", "-m", "graphrag.index", "--root", str(tmp_path)]
    assert indexer_module._append_no_cache_flag(command)[-1] == "--nocache"
