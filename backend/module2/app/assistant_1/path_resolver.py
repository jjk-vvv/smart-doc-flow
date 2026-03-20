from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Assistant1Settings
from .models import DocumentSourceBundle


class Assistant1PathResolver:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.module2_root = self.settings.module2_root

    def resolve(self, file_hash: str) -> DocumentSourceBundle:
        normalized_hash = str(file_hash or "").strip()
        if not normalized_hash:
            raise ValueError("file_hash is required")

        warnings: list[str] = []
        assistant_payload_path = self._find_assistant_payload(normalized_hash)
        assistant_payload = self._read_json(Path(assistant_payload_path)) if assistant_payload_path else {}

        mineru_logical_dir = self.module2_root / "artifacts" / "pdf_parse" / "mineru" / normalized_hash
        pointer_path = mineru_logical_dir / "mineru_run_pointer.json"
        meta_path = mineru_logical_dir / "mineru_run_meta.json"

        pointer_data = self._read_json(pointer_path) if pointer_path.exists() else {}
        meta_data = self._read_json(meta_path) if meta_path.exists() else {}
        run_dir_raw = str(pointer_data.get("actual_run_dir", "") or meta_data.get("run_dir", "") or "").strip()
        if not run_dir_raw and assistant_payload:
            inferred_run_dir = self._infer_run_dir_from_assistant_payload(assistant_payload)
            if inferred_run_dir:
                run_dir_raw = inferred_run_dir
                inferred_meta_path = Path(run_dir_raw) / "mineru_run_meta.json"
                if inferred_meta_path.exists():
                    meta_data = self._read_json(inferred_meta_path)
                warnings.append("resolved MinerU run dir from assistant_payload image_path fallback")

        actual_run_dir = Path(run_dir_raw) if run_dir_raw else None

        if actual_run_dir and not actual_run_dir.exists():
            warnings.append(f"resolved MinerU run dir does not exist: {actual_run_dir}")

        markdown_path = str(meta_data.get("markdown_path", "") or "")
        content_list_path = str(meta_data.get("content_list_path", "") or "")
        images_dir = str(meta_data.get("images_dir", "") or "")

        if not markdown_path and actual_run_dir:
            fallback_markdown = actual_run_dir / "o" / "i" / "auto" / "i.md"
            if fallback_markdown.exists():
                markdown_path = str(fallback_markdown)
        if not content_list_path and actual_run_dir:
            fallback_content_list = actual_run_dir / "o" / "i" / "auto" / "i_content_list.json"
            if fallback_content_list.exists():
                content_list_path = str(fallback_content_list)
        if not images_dir and actual_run_dir:
            fallback_images_dir = actual_run_dir / "o" / "i" / "auto" / "images"
            if fallback_images_dir.exists():
                images_dir = str(fallback_images_dir)

        if not markdown_path:
            warnings.append(f"MinerU markdown path missing for file_hash={normalized_hash}")
        if not content_list_path:
            warnings.append(f"MinerU content_list path missing for file_hash={normalized_hash}")
        if not assistant_payload_path:
            warnings.append(f"assistant payload artifact not found for file_hash={normalized_hash}")

        return DocumentSourceBundle(
            file_hash=normalized_hash,
            file_name=str(meta_data.get("file_name", "") or assistant_payload.get("file_name", "") or ""),
            mineru_run_key=str(meta_data.get("run_key", "") or pointer_data.get("run_key", "") or ""),
            mineru_run_token=str(meta_data.get("run_token", "") or pointer_data.get("run_token", "") or ""),
            mineru_run_dir=str(actual_run_dir) if actual_run_dir else "",
            mineru_markdown_path=markdown_path,
            mineru_content_list_path=content_list_path,
            assistant_payload_path=assistant_payload_path,
            images_dir=images_dir,
            metadata={
                "pointer_path": str(pointer_path) if pointer_path.exists() else "",
                "meta_path": str(meta_path) if meta_path.exists() else "",
                "pointer_data": pointer_data,
                "meta_data": meta_data,
                "assistant_payload_path": assistant_payload_path,
            },
            warnings=warnings,
        )

    def _find_assistant_payload(self, file_hash: str) -> str:
        payload_dir = self.module2_root / "artifacts" / "assistant_payload" / file_hash[:12]
        if not payload_dir.exists():
            return ""
        for candidate in sorted(payload_dir.glob("*.json")):
            payload = self._read_json(candidate)
            if str(payload.get("file_hash", "") or "").strip() == file_hash:
                return str(candidate)
        return ""

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _infer_run_dir_from_assistant_payload(payload: dict[str, Any]) -> str:
        for key in ("tables", "figures"):
            for item in payload.get(key, []) or []:
                image_path = str(item.get("image_path", "") or "").strip()
                if not image_path:
                    continue
                image_file = Path(image_path)
                parts = [part.lower() for part in image_file.parts]
                if "images" in parts:
                    try:
                        images_index = parts.index("images")
                    except ValueError:
                        continue
                    if images_index >= 4:
                        return str(Path(*image_file.parts[: images_index - 3]))
        return ""
