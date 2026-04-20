from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_python_service_utils_points_to_unified_module_env_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    node_script = "\n".join(
        [
            "const utils = require('./scripts/python-service-utils.cjs');",
            "const env = utils.buildManagedRuntimeEnv({",
            "  baseEnv: {",
            f"    SMART_DOC_FLOW_RUNTIME_ROOT: {str(repo_root)!r},",
            f"    SMART_DOC_FLOW_CONFIG_ROOT: {str(repo_root)!r},",
            "  },",
            "  scopes: ['backend', 'module2', 'module4'],",
            "});",
            "const specs = utils.resolveScopedEnvFileSpecs({",
            f"  runtimeRoot: {str(repo_root)!r},",
            f"  configRoot: {str(repo_root)!r},",
            "  scopes: ['backend', 'module2', 'module4'],",
            "});",
            "console.log(JSON.stringify({",
            "  dataRoot: env.SMART_DOC_FLOW_DATA_ROOT,",
            "  module2EnvFile: env.MODULE2_ENV_FILE,",
            "  module4EnvFile: env.SMART_DOC_FLOW_MODULE4_ENV_FILE,",
            "  module2RuntimeModelsDir: env.MODULE2_MINERU_RUNTIME_MODELS_DIR,",
            "  promptsRoot: env.MODULE4_GRAPHRAG_PROMPTS_ROOT,",
            "  module4WorkspacesRoot: env.MODULE4_GRAPHRAG_WORKSPACES_ROOT,",
            "  specs: specs.map((item) => ({ scope: item.scope, path: item.path })),",
            "}));",
        ]
    )

    result = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)

    module2_env = (repo_root / "backend" / "app" / "modules" / "module2" / ".env").resolve()
    module4_env = (repo_root / "backend" / "app" / "modules" / "module4" / ".env").resolve()
    data_root = (repo_root / "runtime-data").resolve()
    prompts_root = (repo_root / "backend" / "app" / "modules" / "module4" / "assets" / "prompts").resolve()

    assert Path(payload["dataRoot"]).resolve() == data_root
    assert Path(payload["module2EnvFile"]).resolve() == module2_env
    assert Path(payload["module4EnvFile"]).resolve() == module4_env
    assert Path(payload["module2RuntimeModelsDir"]).resolve() == (data_root / "module2" / "cache" / "mineru_runtime_models")
    assert Path(payload["promptsRoot"]).resolve() == prompts_root
    assert Path(payload["module4WorkspacesRoot"]).resolve() == (data_root / "module4" / "workspaces")
    assert module2_env.exists()
    assert module4_env.exists()
    assert prompts_root.exists()

    specs_by_scope = {item["scope"]: Path(item["path"]).resolve() for item in payload["specs"]}
    assert specs_by_scope["module2"] == module2_env
    assert specs_by_scope["module4"] == module4_env
