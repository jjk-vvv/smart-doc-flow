from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from app.core.paths import resolve_config_root_dir, resolve_data_root_dir, resolve_runtime_root_dir


def _parse_env_file(file_path: Path, allowed_keys: tuple[str, ...] | None = None) -> dict[str, str]:
    if not file_path.exists() or not file_path.is_file():
        return {}

    allow_set = {item.strip() for item in allowed_keys or () if str(item or "").strip()} or None
    values: dict[str, str] = {}
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = str(raw_line or "").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if allow_set is not None and key not in allow_set:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key] = value
    return values


def _ensure_env_value(name: str, value: str) -> None:
    if str(os.getenv(name, "") or "").strip():
        return
    os.environ[name] = value


def _assign_env_value(name: str, value: str, *, force: bool = False) -> None:
    if force:
        os.environ[name] = value
        return
    _ensure_env_value(name, value)


def _resolve_optional_dir(raw_value: str, fallback: Path) -> Path:
    raw = str(raw_value or "").strip()
    if not raw:
        return fallback.resolve()
    return Path(raw).expanduser().resolve()


def _build_env_file_specs(
    *,
    runtime_root: Path,
    config_root: Path,
    normalized_scopes: tuple[str, ...],
    scope_specs: dict[str, tuple[Path, tuple[str, ...] | None]],
) -> list[tuple[Path, tuple[str, ...] | None]]:
    env_file_specs: list[tuple[Path, tuple[str, ...] | None]] = []
    seen_specs: set[tuple[Path, tuple[str, ...] | None]] = set()
    for base_dir in (runtime_root, config_root):
        for scope in normalized_scopes:
            spec = scope_specs.get(scope)
            if spec is None:
                continue
            rel_path, allowed_keys = spec
            full_path = (base_dir / rel_path).resolve()
            dedupe_key = (full_path, allowed_keys)
            if dedupe_key in seen_specs:
                continue
            seen_specs.add(dedupe_key)
            env_file_specs.append((full_path, allowed_keys))
    return env_file_specs


def _load_env_file_values(env_file_specs: list[tuple[Path, tuple[str, ...] | None]]) -> dict[str, str]:
    env_file_values: dict[str, str] = {}
    for env_file_path, allowed_keys in env_file_specs:
        env_file_values.update(_parse_env_file(env_file_path, allowed_keys=allowed_keys))
    return env_file_values


def _resolve_managed_roots(
    *,
    runtime_root: Path,
    config_root: Path,
    env_file_values: dict[str, str],
) -> tuple[Path, Path, Path]:
    resolved_runtime_root = _resolve_optional_dir(
        env_file_values.get("SMART_DOC_FLOW_RUNTIME_ROOT", ""),
        runtime_root,
    )
    default_config_root = resolve_config_root_dir(resolved_runtime_root)
    resolved_config_root = _resolve_optional_dir(
        env_file_values.get("SMART_DOC_FLOW_CONFIG_ROOT", ""),
        default_config_root if default_config_root else config_root,
    )
    resolved_data_root = _resolve_optional_dir(
        env_file_values.get("SMART_DOC_FLOW_DATA_ROOT", ""),
        resolve_data_root_dir(resolved_runtime_root),
    )
    return resolved_runtime_root, resolved_config_root, resolved_data_root


@lru_cache(maxsize=1)
def load_managed_env_files(scopes: tuple[str, ...] | None = None) -> None:
    runtime_root = resolve_runtime_root_dir()
    config_root = resolve_config_root_dir(runtime_root)
    scope_specs: dict[str, tuple[Path, tuple[str, ...] | None]] = {
        "backend": (Path("backend/.env"), None),
        "module1": (Path("backend/app/modules/module1/.env"), None),
        "module2": (Path("backend/app/modules/module2/.env"), None),
        "module3": (Path("backend/app/modules/module3/.env"), None),
        "module4": (Path("backend/app/modules/module4/.env"), None),
    }
    normalized_scopes = tuple(scopes or ("module1", "backend", "module2", "module3", "module4"))

    env_file_specs = _build_env_file_specs(
        runtime_root=runtime_root,
        config_root=config_root,
        normalized_scopes=normalized_scopes,
        scope_specs=scope_specs,
    )
    env_file_values = _load_env_file_values(env_file_specs)
    runtime_root, config_root, data_root = _resolve_managed_roots(
        runtime_root=runtime_root,
        config_root=config_root,
        env_file_values=env_file_values,
    )

    # If runtime/config roots are overridden inside env files, reload envs from
    # the resolved roots so module-specific .env files are discovered correctly.
    reloaded_env_file_specs = _build_env_file_specs(
        runtime_root=runtime_root,
        config_root=config_root,
        normalized_scopes=normalized_scopes,
        scope_specs=scope_specs,
    )
    if reloaded_env_file_specs != env_file_specs:
        env_file_values = _load_env_file_values(reloaded_env_file_specs)
        runtime_root, config_root, data_root = _resolve_managed_roots(
            runtime_root=runtime_root,
            config_root=config_root,
            env_file_values=env_file_values,
        )

    for key, value in env_file_values.items():
        _ensure_env_value(key, value)

    os.environ["SMART_DOC_FLOW_RUNTIME_ROOT"] = str(runtime_root)
    os.environ["SMART_DOC_FLOW_CONFIG_ROOT"] = str(config_root)
    os.environ["SMART_DOC_FLOW_DATA_ROOT"] = str(data_root)
    os.environ["SMART_DOC_FLOW_GATEWAY_ENV_FILE"] = str((config_root / "backend" / ".env").resolve())
    os.environ["MODULE2_ENV_FILE"] = str((config_root / "backend" / "app" / "modules" / "module2" / ".env").resolve())
    os.environ["MODULE3_ENV_FILE"] = str((config_root / "backend" / "app" / "modules" / "module3" / ".env").resolve())
    os.environ["SMART_DOC_FLOW_MODULE4_ENV_FILE"] = str(
        (config_root / "backend" / "app" / "modules" / "module4" / ".env").resolve()
    )

    force_managed_data_paths = data_root.resolve() != runtime_root.resolve()

    _ensure_env_value("GATEWAY_FRONTEND_DIST_DIR", str((runtime_root / "frontend" / "dist").resolve()))
    _assign_env_value(
        "AUTH_USERS_FILE",
        str((data_root / "auth" / "users.json").resolve()),
        force=force_managed_data_paths,
    )
    _assign_env_value(
        "MODULE2_ARTIFACT_ROOT_DIR",
        str((data_root / "module2" / "artifacts").resolve()),
        force=force_managed_data_paths,
    )
    _assign_env_value(
        "MODULE2_MINERU_CACHE_DIR",
        str((data_root / "module2" / "cache" / "mineru").resolve()),
        force=force_managed_data_paths,
    )
    _assign_env_value(
        "MODULE2_GEMINI_CACHE_DIR",
        str((data_root / "module2" / "cache" / "gemini").resolve()),
        force=force_managed_data_paths,
    )
    _assign_env_value(
        "MODULE2_MINERU_WORK_ROOT_DIR",
        str((data_root / "module2" / "work" / "mineru").resolve()),
        force=force_managed_data_paths,
    )
    _assign_env_value(
        "MODULE2_EXTRACT_JOB_STATE_DIR",
        str((data_root / "module2" / "runlogs" / "extraction_jobs").resolve()),
        force=force_managed_data_paths,
    )
    _assign_env_value(
        "MODULE2_LLM_DEBUG_DIR",
        str((data_root / "module2" / "runlogs" / "module2-llm-debug").resolve()),
        force=force_managed_data_paths,
    )

    bundled_mineru_runtime_models_dir = (
        runtime_root / "backend" / "app" / "modules" / "module2" / ".cache" / "mineru_runtime_models"
    ).resolve()
    _assign_env_value(
        "MODULE2_MINERU_RUNTIME_MODELS_DIR",
        str(
            bundled_mineru_runtime_models_dir
            if bundled_mineru_runtime_models_dir.exists()
            else (data_root / "module2" / "cache" / "mineru_runtime_models").resolve()
        ),
        force=force_managed_data_paths,
    )
    _assign_env_value(
        "MODULE4_GRAPHRAG_WORKSPACES_ROOT",
        str((data_root / "module4" / "workspaces").resolve()),
        force=force_managed_data_paths,
    )
    _ensure_env_value(
        "MODULE4_GRAPHRAG_PROMPTS_ROOT",
        str((runtime_root / "backend" / "app" / "modules" / "module4" / "assets" / "prompts").resolve()),
    )
