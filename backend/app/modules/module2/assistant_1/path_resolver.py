from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config import Assistant1Settings
from .models import DocumentSourceBundle


class Assistant1PathResolver:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.module2_root = self.settings.module2_root
        self.artifact_root = self.settings.module2_artifact_root_dir

    def resolve(self, file_hash: str) -> DocumentSourceBundle:
        normalized_hash = str(file_hash or "").strip()
        if not normalized_hash:
            raise ValueError("file_hash is required")

        warnings: list[str] = []
        assistant_payload_path = self._find_assistant_payload(normalized_hash)
        assistant_payload = self._read_json(Path(assistant_payload_path)) if assistant_payload_path else {}
        assistant_source_manifest_path = self._find_assistant_source_manifest(normalized_hash)
        assistant_source_meta = (
            self._read_json(Path(assistant_source_manifest_path))
            if assistant_source_manifest_path
            else {}
        )
        uploaded_text_artifact_path = self._find_uploaded_text_artifact(normalized_hash)

        mineru_logical_dir = self.artifact_root / "pdf_parse" / "mineru" / normalized_hash
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

        run_dir_raw = self._remap_legacy_data_path(run_dir_raw)
        actual_run_dir = Path(run_dir_raw) if run_dir_raw else None

        if actual_run_dir and not actual_run_dir.exists():
            remapped_run_dir = self._remap_missing_runtime_path(actual_run_dir)
            if remapped_run_dir is not None:
                actual_run_dir = remapped_run_dir
                run_dir_raw = str(remapped_run_dir)
                warnings.append(f"resolved MinerU run dir via managed data root remap: {actual_run_dir}")
            else:
                warnings.append(f"resolved MinerU run dir does not exist: {actual_run_dir}")

        markdown_path = self._remap_legacy_data_path(str(meta_data.get("markdown_path", "") or ""))
        content_list_path = self._remap_legacy_data_path(str(meta_data.get("content_list_path", "") or ""))
        images_dir = self._remap_legacy_data_path(str(meta_data.get("images_dir", "") or ""))

        if not markdown_path and actual_run_dir:
            fallback_markdown = actual_run_dir / "o" / "i" / "auto" / "i.md"
            if fallback_markdown.exists():
                markdown_path = str(fallback_markdown)
        if not markdown_path:
            assistant_source_markdown = self._resolve_artifact_path(
                assistant_source_meta.get("markdown_artifact_path", "")
            )
            if assistant_source_markdown and Path(assistant_source_markdown).exists():
                markdown_path = assistant_source_markdown
        if not markdown_path and uploaded_text_artifact_path:
            markdown_path = uploaded_text_artifact_path
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
            file_name=str(
                meta_data.get("file_name", "")
                or assistant_payload.get("file_name", "")
                or assistant_source_meta.get("file_name", "")
                or (Path(uploaded_text_artifact_path).name if uploaded_text_artifact_path else "")
                or ""
            ),
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
                "assistant_source_manifest_path": assistant_source_manifest_path,
                "assistant_source_meta": assistant_source_meta,
            },
            warnings=warnings,
        )

    def _find_assistant_payload(self, file_hash: str) -> str:
        payload_dir = self.artifact_root / "assistant_payload" / file_hash[:12]
        if not payload_dir.exists():
            return ""
        for candidate in sorted(payload_dir.glob("*.json")):
            payload = self._read_json(candidate)
            if str(payload.get("file_hash", "") or "").strip() == file_hash:
                return str(candidate)
        return ""

    def _find_assistant_source_manifest(self, file_hash: str) -> str:
        manifest_dir = self.artifact_root / "assistant_1_source" / file_hash[:12]
        if not manifest_dir.exists():
            return ""
        for candidate in sorted(manifest_dir.glob("*.json")):
            payload = self._read_json(candidate)
            if str(payload.get("file_hash", "") or "").strip() == file_hash:
                return str(candidate)
        return ""

    def _find_uploaded_text_artifact(self, file_hash: str) -> str:
        upload_dir = self.artifact_root / "preview" / "uploaded"
        if not upload_dir.exists():
            return ""
        allowed_suffixes = {".md", ".txt", ".csv", ".json"}
        for candidate in sorted(upload_dir.glob(f"*_{file_hash[:16]}.*")):
            if candidate.suffix.lower() not in allowed_suffixes:
                continue
            return str(candidate)
        return ""

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _resolve_artifact_path(self, path_value: Any) -> str:
        raw = str(path_value or "").strip()
        if not raw:
            return ""
        candidate = Path(raw)
        if candidate.is_absolute():
            return self._remap_legacy_data_path(str(candidate))
        return str((self.artifact_root / Path(*raw.replace("\\", "/").split("/"))).resolve())

    def _remap_legacy_data_path(self, raw_path: str) -> str:
        raw = str(raw_path or "").strip()
        if not raw:
            return ""
        candidate = Path(raw)
        if not candidate.is_absolute():
            return raw

        runtime_root = self._runtime_root_dir()
        data_root = self._data_root_dir()
        replacements = (
            ((runtime_root / "backend" / "module2" / "artifacts").resolve(), (data_root / "module2" / "artifacts").resolve()),
            ((runtime_root / "module2").resolve(), (data_root / "module2").resolve()),
            ((runtime_root / "backend" / "module4" / "workspaces").resolve(), (data_root / "module4" / "workspaces").resolve()),
            ((runtime_root / "auth").resolve(), (data_root / "auth").resolve()),
        )
        remapped = self._remap_prefix(candidate, replacements)
        return str(remapped if remapped is not None else candidate)

    def _remap_missing_runtime_path(self, candidate: Path) -> Path | None:
        if candidate.exists():
            return candidate
        runtime_root = self._runtime_root_dir()
        data_root = self._data_root_dir()
        replacements = (
            ((runtime_root / "backend" / "module2" / "artifacts").resolve(), (data_root / "module2" / "artifacts").resolve()),
            ((runtime_root / "module2").resolve(), (data_root / "module2").resolve()),
            ((runtime_root / "backend" / "module4" / "workspaces").resolve(), (data_root / "module4" / "workspaces").resolve()),
            ((runtime_root / "auth").resolve(), (data_root / "auth").resolve()),
        )
        remapped = self._remap_prefix(candidate, replacements)
        if remapped is not None and remapped.exists():
            return remapped
        return None

    def _runtime_root_dir(self) -> Path:
        configured = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return self.module2_root.parents[3].resolve()

    def _data_root_dir(self) -> Path:
        configured = str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return self._runtime_root_dir()

    @staticmethod
    def _remap_prefix(candidate: Path, replacements: tuple[tuple[Path, Path], ...]) -> Path | None:
        candidate_resolved = candidate.resolve(strict=False)
        candidate_text = str(candidate_resolved).lower()
        ordered = sorted(replacements, key=lambda item: len(str(item[0])), reverse=True)
        for old_root, new_root in ordered:
            old_root_resolved = old_root.resolve(strict=False)
            old_text = str(old_root_resolved).lower()
            if candidate_text == old_text:
                return new_root.resolve(strict=False)
            prefix = old_text + "\\"
            if candidate_text.startswith(prefix):
                suffix = candidate_resolved.relative_to(old_root_resolved)
                return (new_root / suffix).resolve(strict=False)
        return None

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
