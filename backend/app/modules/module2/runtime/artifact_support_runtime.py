from __future__ import annotations

import hashlib
import json
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_HEX_BUCKET_RE = re.compile(r"^[0-9a-f]{32,64}$", flags=re.IGNORECASE)


class ArtifactSupportRuntime:
    def __init__(self, *, artifact_root_factory, logger: Any) -> None:
        self._artifact_root_factory = artifact_root_factory
        self._logger = logger

    @staticmethod
    def _safe_link_name(name: str, suffix: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip())
        safe_name = safe_name.strip("._")
        if not safe_name:
            return f"artifact{suffix.lower()}"
        if len(safe_name) > 120:
            stem = Path(safe_name).stem[:96].rstrip("._-") or "artifact"
            ext = Path(safe_name).suffix[:16]
            safe_name = f"{stem}{ext}" if ext else stem
        return safe_name

    @staticmethod
    def _normalize_link_bucket(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if _HEX_BUCKET_RE.fullmatch(raw):
            return raw.lower()[:12]
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
        if not safe:
            return ""
        return safe[:48]

    def _derive_link_bucket(self, candidate: Path, source_bucket: Any = None) -> str:
        normalized = self._normalize_link_bucket(source_bucket)
        if normalized:
            return normalized
        for part in reversed(candidate.parent.parts):
            if _HEX_BUCKET_RE.fullmatch(part or ""):
                return str(part).lower()[:12]
        return hashlib.sha1(str(candidate.parent).encode("utf-8", "ignore")).hexdigest()[:12]

    def artifact_fragment_from_path(self, path_value: Any, *, source_bucket: Any = None) -> str:
        raw = str(path_value or "").strip()
        if not raw:
            return ""
        normalized = raw.replace("\\", "/").strip().lstrip("/")
        root = self._artifact_root_factory()

        try:
            candidate = Path(raw).resolve()
        except Exception:
            candidate = None
        if candidate is not None:
            try:
                rel = candidate.relative_to(root)
                return str(rel).replace("\\", "/")
            except Exception:
                pass
            try:
                if candidate.exists() and candidate.is_file():
                    digest = hashlib.sha1(str(candidate).encode("utf-8", "ignore")).hexdigest()[:16]
                    bucket = self._derive_link_bucket(candidate, source_bucket=source_bucket)
                    safe_name = self._safe_link_name(candidate.name, candidate.suffix)
                    mirror_rel = Path("linked") / bucket / f"{digest}_{safe_name}"
                    mirror_path = (root / mirror_rel).resolve()
                    mirror_path.relative_to(root)
                    source_stat = candidate.stat()
                    should_copy = True
                    if mirror_path.exists():
                        try:
                            mirror_stat = mirror_path.stat()
                            should_copy = (
                                mirror_stat.st_size != source_stat.st_size
                                or int(mirror_stat.st_mtime) != int(source_stat.st_mtime)
                            )
                        except Exception:
                            should_copy = True
                    if should_copy:
                        mirror_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(candidate, mirror_path)
                    return str(mirror_rel).replace("\\", "/")
            except Exception:
                pass

        try:
            joined = (root / normalized).resolve()
            rel = joined.relative_to(root)
            return str(rel).replace("\\", "/")
        except Exception:
            return ""

    @staticmethod
    def artifact_url_from_fragment(fragment: str) -> str:
        cleaned = str(fragment or "").strip().strip("/")
        if not cleaned:
            return ""
        encoded = "/".join(urllib.parse.quote(seg, safe="") for seg in cleaned.split("/") if seg)
        return f"/extract/artifact/{encoded}" if encoded else ""

    @staticmethod
    def _sanitize_file_stem(name: str, fallback: str = "artifact") -> str:
        stem = Path(name or "").stem or fallback
        safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", stem).strip("_")
        return safe or fallback

    @staticmethod
    def _coerce_json_safe_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, tuple):
            value = list(value)
        if isinstance(value, list):
            return [ArtifactSupportRuntime._coerce_json_safe_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): ArtifactSupportRuntime._coerce_json_safe_value(item)
                for key, item in value.items()
            }
        return str(value)

    @staticmethod
    def _coerce_artifact_bbox(raw_value: Any) -> List[float]:
        if not isinstance(raw_value, list) or len(raw_value) < 5:
            return []
        bbox: List[float] = []
        for item in raw_value[:5]:
            try:
                bbox.append(float(item))
            except (TypeError, ValueError):
                return []
        return bbox if len(bbox) == 5 else []

    def write_artifact_bytes(self, *, data: bytes, file_name: str, sub_dir: str, ext: str) -> Tuple[str, str]:
        root = self._artifact_root_factory()
        target_dir = (root / sub_dir).resolve()
        try:
            target_dir.relative_to(root)
        except Exception:
            target_dir = root / "preview"
        target_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()[:16]
        suffix = ext if ext.startswith(".") else f".{ext}"
        fname = f"{self._sanitize_file_stem(file_name)}_{digest}{suffix}"
        target = (target_dir / fname).resolve()
        target.write_bytes(data)
        fragment = str(target.relative_to(root)).replace("\\", "/")
        return fragment, self.artifact_url_from_fragment(fragment)

    def write_json_artifact(self, *, payload: Dict[str, Any], file_name: str, sub_dir: str) -> Tuple[str, str]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self.write_artifact_bytes(data=data, file_name=file_name, sub_dir=sub_dir, ext=".json")

    def persist_assistant_payload_artifact(
        self,
        *,
        file_name: str,
        file_hash: str,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
    ) -> Tuple[str, str]:
        payload = {
            "version": "module2-assistant-payload-v1",
            "file_name": file_name,
            "file_hash": file_hash,
            "tables": table_blocks,
            "figures": figure_blocks,
        }
        try:
            return self.write_json_artifact(
                payload=payload,
                file_name=f"{Path(file_name).stem}_assistant_payload",
                sub_dir=f"assistant_payload/{file_hash[:12]}",
            )
        except Exception as exc:
            self._logger.warning("failed to persist assistant payload artifact for %s: %s", file_name, exc)
            return "", ""

    def persist_field_results_artifact(
        self,
        *,
        file_name: str,
        file_hash: str,
        track: str,
        final_results: Dict[str, Any],
    ) -> Tuple[str, str]:
        if not isinstance(final_results, dict) or not final_results:
            return "", ""

        field_items: List[Dict[str, Any]] = []
        for field_name in sorted(final_results.keys(), key=lambda item: str(item or "").lower()):
            entity = final_results.get(field_name)
            if not isinstance(entity, dict):
                continue
            bbox = self._coerce_artifact_bbox(entity.get("bbox"))
            ref_id = str(entity.get("source_ref_id") or "").strip()
            try:
                confidence = float(entity.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            field_payload: Dict[str, Any] = {
                "field_name": str(field_name),
                "value": self._coerce_json_safe_value(entity.get("value")),
                "confidence": max(0.0, min(1.0, confidence)),
                "source_ref_id": ref_id or None,
                "bbox": bbox,
            }
            if bbox:
                try:
                    field_payload["page"] = max(1, int(round(float(bbox[0]))))
                except (TypeError, ValueError):
                    pass
            field_items.append(field_payload)

        if not field_items:
            return "", ""

        payload = {
            "version": "module2-field-results-v1",
            "file_name": file_name,
            "file_hash": file_hash,
            "track": str(track or "").strip(),
            "field_count": len(field_items),
            "fields": field_items,
        }
        try:
            return self.write_json_artifact(
                payload=payload,
                file_name=f"{Path(file_name).stem}_field_results",
                sub_dir=f"field_results/{file_hash[:12]}",
            )
        except Exception as exc:
            self._logger.warning("failed to persist field results artifact for %s: %s", file_name, exc)
            return "", ""

    def persist_assistant1_source_markdown_artifact(
        self,
        *,
        file_name: str,
        file_hash: str,
        markdown_text: str,
        track: str,
    ) -> Tuple[str, str, str, str]:
        clean_markdown = str(markdown_text or "").strip()
        if not clean_markdown:
            return "", "", "", ""
        try:
            markdown_fragment, markdown_url = self.write_artifact_bytes(
                data=clean_markdown.encode("utf-8"),
                file_name=f"{Path(file_name).stem}_assistant1_source",
                sub_dir=f"assistant_1_source/{file_hash[:12]}",
                ext=".md",
            )
            manifest_fragment, manifest_url = self.write_json_artifact(
                payload={
                    "version": "module2-assistant1-source-v1",
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "track": track,
                    "markdown_artifact_path": markdown_fragment,
                    "markdown_artifact_url": markdown_url,
                },
                file_name=f"{Path(file_name).stem}_assistant1_source_meta",
                sub_dir=f"assistant_1_source/{file_hash[:12]}",
            )
            return markdown_fragment, markdown_url, manifest_fragment, manifest_url
        except Exception as exc:
            self._logger.warning("failed to persist assistant_1 source markdown for %s: %s", file_name, exc)
            return "", "", "", ""

    def resolve_trace_artifact_ref(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        source_bucket = (
            payload.get("file_hash")
            or payload.get("source_file_hash")
            or payload.get("document_id")
            or payload.get("file_name")
        )
        image_fragment = self.artifact_fragment_from_path(
            payload.get("image_path"),
            source_bucket=source_bucket,
        )
        if image_fragment:
            return image_fragment, self.artifact_url_from_fragment(image_fragment)

        direct_url = str(payload.get("artifact_url") or "").strip()
        if direct_url:
            return None, direct_url

        for key in ("artifact_path",):
            fragment = self.artifact_fragment_from_path(
                payload.get(key),
                source_bucket=source_bucket,
            )
            if fragment:
                return fragment, self.artifact_url_from_fragment(fragment)
        return None, None
