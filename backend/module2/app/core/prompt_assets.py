from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


APP_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = APP_ROOT / "prompts"
PROMPT_FILE_MAP = {
    "extract_fields": "extract_fields.prompty",
    "extract_table_fields": "extract_table_fields.prompty",
    "json_repair": "json_repair.prompty",
}


@lru_cache(maxsize=1)
def load_prompt_assets() -> Dict[str, Any]:
    prompts: Dict[str, Dict[str, str]] = {}
    version_digest = hashlib.sha256()
    for prompt_name, file_name in PROMPT_FILE_MAP.items():
        path = PROMPTS_DIR / file_name
        content = path.read_text(encoding="utf-8").strip() + "\n"
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        prompts[prompt_name] = {
            "name": prompt_name,
            "path": str(path),
            "content": content,
            "sha256": sha256,
        }
        version_digest.update(prompt_name.encode("utf-8"))
        version_digest.update(b"\0")
        version_digest.update(content.encode("utf-8"))
        version_digest.update(b"\0")
    return {
        "version": f"prompt-assets-{version_digest.hexdigest()[:16]}",
        "prompts": prompts,
    }


def load_prompt_text(prompt_name: str) -> str:
    prompt = load_prompt_assets().get("prompts", {}).get(str(prompt_name).strip())
    if not isinstance(prompt, dict):
        raise KeyError(f"Unknown prompt asset: {prompt_name}")
    return str(prompt.get("content") or "")


def prompt_asset_versions() -> Dict[str, str]:
    prompts = load_prompt_assets().get("prompts", {})
    return {
        str(name): str(meta.get("sha256") or "")
        for name, meta in prompts.items()
        if isinstance(meta, dict)
    }


def prompt_asset_names() -> list[str]:
    return list(load_prompt_assets().get("prompts", {}).keys())
