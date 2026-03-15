from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


class MineruLayoutExtractor:
    """Run MinerU and normalize layout objects into a stable shape."""

    def __init__(
        self,
        *,
        backend: str = "pipeline",
        method: str = "txt",
        timeout_sec: int = 900,
        cache_dir: str | None = None,
        enable_cache: bool = True,
        enable_formula: bool = False,
        enable_table: bool = True,
        device: str = "cpu",
        method_fallbacks: str | None = None,
        cache_version: str | None = None,
    ) -> None:
        self.backend = (backend or "pipeline").strip() or "pipeline"
        self.method = (method or "txt").strip() or "txt"
        self.timeout_sec = max(60, int(timeout_sec))
        self.enable_cache = bool(enable_cache)
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else None
        self.enable_formula = bool(enable_formula)
        self.enable_table = bool(enable_table)
        self.device = (device or "cpu").strip() or "cpu"
        raw_fallbacks = str(method_fallbacks or "auto,ocr,txt").strip()
        self.method_fallbacks = [x.strip() for x in raw_fallbacks.split(",") if x.strip()]
        self.cache_version = (
            str(cache_version or os.getenv("MODULE2_MINERU_CACHE_VERSION", "20260309-pdf-chain-v1")).strip()
            or "20260309-pdf-chain-v1"
        )
        self._last_run_meta: Dict[str, Any] = {}

    def get_last_run_meta(self) -> Dict[str, Any]:
        return copy.deepcopy(self._last_run_meta)

    def extract_layout(
        self,
        *,
        pdf_bytes: bytes,
        file_name: str,
        start_page: int = 1,
        end_page: int | None = None,
        method: str | None = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[int, List[str]]]:
        self._last_run_meta = {}
        if not pdf_bytes:
            self._last_run_meta = {"status": "empty_input"}
            return [], {}
        start_page = max(1, int(start_page))
        if end_page is None:
            end_page = start_page
        end_page = max(start_page, int(end_page))
        start_idx = start_page - 1
        end_idx = end_page - 1

        run_method = (method or self.method or "txt").strip() or "txt"
        methods_to_try = self._candidate_methods(run_method)
        run_key = self._build_run_key(
            pdf_bytes=pdf_bytes,
            file_name=file_name,
            start_idx=start_idx,
            end_idx=end_idx,
            backend=self.backend,
            method=run_method,
            enable_formula=self.enable_formula,
            enable_table=self.enable_table,
            cache_version=self.cache_version,
        )
        run_meta: Dict[str, Any] = {
            "status": "init",
            "run_key": run_key,
            "file_name": str(file_name or ""),
            "backend": self.backend,
            "method_requested": run_method,
            "start_page": start_page,
            "end_page": end_page,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "enable_cache": bool(self.enable_cache),
            "cache_dir": str(self.cache_dir) if self.cache_dir else "",
            "device": self.device,
            "cache_version": self.cache_version,
            "method_candidates": list(methods_to_try),
        }
        temp_ctx: tempfile.TemporaryDirectory[str] | None = None
        if self.enable_cache and self.cache_dir is not None:
            run_dir = self.cache_dir / run_key
            run_dir.mkdir(parents=True, exist_ok=True)
        else:
            temp_ctx = tempfile.TemporaryDirectory(prefix="module2_mineru_")
            run_dir = Path(temp_ctx.name)
        run_meta["run_dir"] = str(run_dir.resolve())

        try:
            input_pdf = run_dir / "input.pdf"
            if not input_pdf.exists() or input_pdf.stat().st_size != len(pdf_bytes):
                input_pdf.write_bytes(pdf_bytes)
            run_meta["input_pdf"] = str(input_pdf.resolve())
            run_meta["input_pdf_size"] = int(input_pdf.stat().st_size)

            output_root = run_dir / "mineru_out"
            run_meta["output_root"] = str(output_root.resolve())
            content_json = self._find_content_list_json(output_root, method=run_method)
            markdown_file = self._find_markdown_file(output_root, method=run_method)
            if content_json is None:
                content_json = self._find_content_list_json(output_root)
            if markdown_file is None:
                markdown_file = self._find_markdown_file(output_root)

            attempts: List[Dict[str, Any]] = []
            cached_method = str(content_json.parent.name).strip().lower() if content_json is not None else ""
            parsed_content: Dict[str, Any] | None = None
            best_candidate: Dict[str, Any] | None = None
            best_content_json = content_json
            best_markdown_file = markdown_file

            if content_json is not None and content_json.exists():
                try:
                    parsed_content = self._parse_content_json(content_json)
                    best_candidate = parsed_content
                    run_meta["method_used"] = cached_method or run_method
                    run_meta["cached_content_reused"] = True
                except Exception as exc:
                    run_meta["cached_content_reused"] = False
                    run_meta["cached_content_error"] = f"{type(exc).__name__}: {exc}"
                    parsed_content = None
            else:
                run_meta["cached_content_reused"] = False

            if parsed_content is None or not parsed_content.get("objects"):
                for method_try in methods_to_try:
                    if method_try == cached_method and parsed_content is not None:
                        if best_candidate is None:
                            best_candidate = parsed_content
                        if parsed_content.get("objects"):
                            run_meta["method_used"] = method_try
                            break
                        continue

                    started_at = time.perf_counter()
                    attempt: Dict[str, Any] = {
                        "method": method_try,
                        "started_at": time.time(),
                    }
                    try:
                        exec_meta = self._run_mineru(
                            input_pdf=input_pdf,
                            output_root=output_root,
                            start_idx=start_idx,
                            end_idx=end_idx,
                            method=method_try,
                        )
                        attempt.update(exec_meta)
                    except Exception as exc:
                        attempt["ok"] = False
                        attempt["error"] = f"{type(exc).__name__}: {exc}"
                        attempt["duration_sec"] = round(time.perf_counter() - started_at, 3)
                        attempts.append(attempt)
                        continue

                    content_json_try = self._find_content_list_json(output_root, method=method_try)
                    markdown_file_try = self._find_markdown_file(output_root, method=method_try)
                    if content_json_try is None:
                        content_json_try = self._find_content_list_json(output_root)
                    if markdown_file_try is None:
                        markdown_file_try = self._find_markdown_file(output_root)
                    attempt["duration_sec"] = round(time.perf_counter() - started_at, 3)
                    attempt["content_list_found"] = bool(content_json_try and content_json_try.exists())
                    attempt["markdown_found"] = bool(markdown_file_try and markdown_file_try.exists())

                    parsed_try: Dict[str, Any] | None = None
                    if content_json_try is not None and content_json_try.exists():
                        try:
                            parsed_try = self._parse_content_json(content_json_try)
                            attempt["content_list_item_count"] = len(parsed_try.get("items", []))
                            attempt["object_count"] = len(parsed_try.get("objects", []))
                            attempt["table_count"] = sum(
                                1
                                for item in parsed_try.get("objects", [])
                                if str(item.get("object_type", "")).strip().lower() == "table"
                            )
                            attempt["image_count"] = sum(
                                1
                                for item in parsed_try.get("objects", [])
                                if str(item.get("object_type", "")).strip().lower() == "image"
                            )
                        except Exception as exc:
                            attempt["content_parse_error"] = f"{type(exc).__name__}: {exc}"
                    attempt["ok"] = bool(content_json_try and content_json_try.exists() and parsed_try is not None)
                    attempts.append(attempt)

                    if parsed_try is not None:
                        if (
                            best_candidate is None
                            or len(parsed_try.get("objects", [])) > len(best_candidate.get("objects", []))
                            or (
                                len(parsed_try.get("objects", [])) == len(best_candidate.get("objects", []))
                                and len(parsed_try.get("items", [])) > len(best_candidate.get("items", []))
                            )
                        ):
                            best_candidate = parsed_try
                            best_content_json = content_json_try
                            best_markdown_file = markdown_file_try
                            run_meta["method_used"] = method_try

                    if parsed_try is not None and parsed_try.get("objects"):
                        parsed_content = parsed_try
                        content_json = content_json_try
                        markdown_file = markdown_file_try
                        run_meta["method_used"] = method_try
                        break

                if parsed_content is None and best_candidate is not None:
                    parsed_content = best_candidate
                    content_json = best_content_json
                    markdown_file = best_markdown_file

            if content_json is None or not content_json.exists():
                run_meta["status"] = "no_content_list"
                run_meta["attempts"] = attempts
                run_meta["markdown_path"] = str(markdown_file.resolve()) if markdown_file else ""
                self._finalize_run_meta(run_meta, run_dir=run_dir)
                return [], {}

            run_meta["attempts"] = attempts
            if parsed_content is None:
                parsed_content = self._parse_content_json(content_json)
            items = parsed_content.get("items", [])
            if not items:
                run_meta["status"] = "content_list_empty"
                run_meta["content_list_path"] = str(content_json.resolve())
                run_meta["markdown_path"] = str(markdown_file.resolve()) if markdown_file else ""
                self._finalize_run_meta(run_meta, run_dir=run_dir)
                return [], {}

            objects = parsed_content.get("objects", [])
            page_text_lines = parsed_content.get("page_text_lines", {})
            images_dir = parsed_content.get("images_dir")
            image_count = int(parsed_content.get("image_count", 0) or 0)
            run_meta["status"] = "ok"
            run_meta["content_list_path"] = str(content_json.resolve())
            run_meta["content_list_size"] = int(content_json.stat().st_size)
            run_meta["content_list_item_count"] = len(items)
            run_meta["markdown_path"] = str(markdown_file.resolve()) if markdown_file else ""
            run_meta["images_dir"] = str(images_dir.resolve()) if images_dir else ""
            run_meta["images_count"] = image_count
            run_meta["object_count"] = len(objects)
            run_meta["table_count"] = sum(
                1 for x in objects if str(x.get("object_type", "")).strip().lower() == "table"
            )
            run_meta["image_count"] = sum(
                1 for x in objects if str(x.get("object_type", "")).strip().lower() == "image"
            )
            self._finalize_run_meta(run_meta, run_dir=run_dir)
            return objects, page_text_lines
        except Exception as exc:
            run_meta["status"] = "error"
            run_meta["error"] = f"{type(exc).__name__}: {exc}"
            self._finalize_run_meta(run_meta, run_dir=run_dir)
            raise
        finally:
            if temp_ctx is not None:
                temp_ctx.cleanup()

    def _run_mineru(
        self,
        *,
        input_pdf: Path,
        output_root: Path,
        start_idx: int,
        end_idx: int,
        method: str,
    ) -> Dict[str, Any]:
        output_root.mkdir(parents=True, exist_ok=True)
        cmd = [
            "mineru",
            "-p",
            str(input_pdf),
            "-o",
            str(output_root),
            "-s",
            str(max(0, int(start_idx))),
            "-e",
            str(max(0, int(end_idx))),
            "-b",
            self.backend,
            "-m",
            method,
            "-f",
            "true" if self.enable_formula else "false",
            "-t",
            "true" if self.enable_table else "false",
        ]
        if self.backend in {"pipeline", "hybrid-http-client", "hybrid-auto-engine"}:
            cmd.extend(["-d", self.device])
        env = os.environ.copy()
        # Torch>=2.6 defaults to weights_only=True, which breaks doclayout_yolo checkpoints.
        env.setdefault("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "1")
        # Avoid update-check noise from albumentations during MinerU subprocess runs.
        env.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
        started = time.perf_counter()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            check=False,
            env=env,
        )
        duration_sec = round(time.perf_counter() - started, 3)
        exec_meta: Dict[str, Any] = {
            "cmd": " ".join(cmd),
            "returncode": int(proc.returncode),
            "stdout_tail": (proc.stdout or "").strip()[-600:],
            "stderr_tail": (proc.stderr or "").strip()[-600:],
            "duration_sec": duration_sec,
        }
        if proc.returncode != 0 or self._stderr_indicates_failure(proc.stderr):
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            msg = stderr or stdout or f"exit_code={proc.returncode}"
            raise RuntimeError(f"MinerU command failed: {msg[:800]}")
        return exec_meta

    @staticmethod
    def _build_run_key(
        *,
        pdf_bytes: bytes,
        file_name: str,
        start_idx: int,
        end_idx: int,
        backend: str,
        method: str,
        enable_formula: bool,
        enable_table: bool,
        cache_version: str,
    ) -> str:
        digest = hashlib.sha256()
        digest.update(pdf_bytes)
        digest.update(str(file_name or "").encode("utf-8", errors="ignore"))
        digest.update(f":{start_idx}:{end_idx}".encode("ascii"))
        digest.update(str(backend or "").encode("utf-8"))
        digest.update(str(method or "").encode("utf-8"))
        digest.update(str(bool(enable_formula)).encode("ascii"))
        digest.update(str(bool(enable_table)).encode("ascii"))
        digest.update(str(cache_version or "").encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _find_content_list_json(output_root: Path, method: str | None = None) -> Path | None:
        if not output_root.exists():
            return None
        method_norm = str(method or "").strip().lower()
        if method_norm:
            candidates = sorted(
                p for p in output_root.rglob("*_content_list.json") if p.parent.name.strip().lower() == method_norm
            )
        else:
            candidates = sorted(output_root.rglob("*_content_list.json"))
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def _find_markdown_file(output_root: Path, method: str | None = None) -> Path | None:
        if not output_root.exists():
            return None
        method_norm = str(method or "").strip().lower()
        if method_norm:
            candidates = sorted(p for p in output_root.rglob("*.md") if p.parent.name.strip().lower() == method_norm)
        else:
            candidates = sorted(output_root.rglob("*.md"))
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _parse_content_json(self, content_json: Path) -> Dict[str, Any]:
        payload = json.loads(content_json.read_text(encoding="utf-8", errors="ignore"))
        items = self._normalize_content_items(payload)
        objects: List[Dict[str, Any]] = []
        page_text_lines: Dict[int, List[str]] = {}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            obj_type = str(raw.get("type", "") or "").strip().lower()
            page_idx = self._to_int(raw.get("page_idx"))
            page_no = max(1, page_idx + 1)
            bbox = self._safe_bbox(raw.get("bbox"))

            if obj_type == "text":
                text = self._normalize_text(str(raw.get("text", "") or ""))
                if text:
                    page_text_lines.setdefault(page_no, []).append(text)
                continue
            if obj_type not in {"table", "image"}:
                continue

            caption = self._safe_str_list(
                raw.get("table_caption") if obj_type == "table" else raw.get("image_caption")
            )
            footnote = self._safe_str_list(
                raw.get("table_footnote") if obj_type == "table" else raw.get("image_footnote")
            )
            for cap in caption:
                page_text_lines.setdefault(page_no, []).append(cap)
            for note in footnote:
                page_text_lines.setdefault(page_no, []).append(note)

            img_path = self._resolve_image_path(
                content_json_path=content_json,
                raw_img_path=str(raw.get("img_path", "") or ""),
            )
            x1, y1, x2, y2 = bbox
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            objects.append(
                {
                    "object_type": obj_type,
                    "page": page_no,
                    "bbox": bbox,
                    "area": area,
                    "img_path": str(img_path) if img_path else "",
                    "caption": caption,
                    "footnote": footnote,
                    "table_body_html": str(raw.get("table_body", "") or "") if obj_type == "table" else "",
                }
            )

        objects.sort(
            key=lambda x: (
                int(x.get("page", 0) or 0),
                0 if str(x.get("object_type", "")) == "table" else 1,
                -float(x.get("area", 0.0) or 0.0),
            )
        )
        images_dir, image_count = self._detect_images_dir(content_json)
        return {
            "items": items,
            "objects": objects,
            "page_text_lines": page_text_lines,
            "images_dir": images_dir,
            "image_count": image_count,
        }

    @staticmethod
    def _normalize_content_items(payload: Any) -> List[Dict[str, Any]]:
        raw_items: Any = payload
        if isinstance(raw_items, dict):
            for key in ("content_list", "items", "data"):
                maybe = raw_items.get(key)
                if isinstance(maybe, list):
                    raw_items = maybe
                    break
        if not isinstance(raw_items, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                out.append(item)
                continue
            if isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict):
                        out.append(sub)
        return out

    @staticmethod
    def _detect_images_dir(content_json: Path) -> Tuple[Path | None, int]:
        parent = content_json.parent
        candidates = [parent / "images", parent.parent / "images"]
        seen: set[str] = set()
        for cand in candidates:
            key = str(cand.resolve())
            if key in seen:
                continue
            seen.add(key)
            if not cand.exists() or not cand.is_dir():
                continue
            count = 0
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.tif", "*.tiff"):
                count += len(list(cand.glob(ext)))
            return cand, count
        return None, 0

    def _candidate_methods(self, requested_method: str) -> List[str]:
        candidates = [str(requested_method or "").strip()]
        candidates.extend(self.method_fallbacks)
        out: List[str] = []
        seen = set()
        for item in candidates:
            method = item.strip().lower()
            if not method:
                continue
            if method in seen:
                continue
            seen.add(method)
            out.append(method)
        return out or ["auto"]

    def _finalize_run_meta(self, run_meta: Dict[str, Any], *, run_dir: Path) -> None:
        run_meta["finished_at"] = time.time()
        self._last_run_meta = copy.deepcopy(run_meta)
        try:
            debug_path = run_dir / "mineru_run_meta.json"
            debug_path.write_text(
                json.dumps(run_meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            return

    @staticmethod
    def _resolve_image_path(*, content_json_path: Path, raw_img_path: str) -> Path | None:
        rel = str(raw_img_path or "").strip()
        if not rel:
            return None
        p = Path(rel)
        if p.is_absolute() and p.exists():
            return p
        parent = content_json_path.parent
        pp = content_json_path.parent.parent

        normalized = rel.replace("\\", "/")
        stripped = normalized[7:] if normalized.lower().startswith("images/") else normalized
        stripped_path = Path(stripped)

        candidates = [
            (parent / p).resolve(),
            (parent / stripped_path).resolve(),
            (parent / "images" / stripped_path).resolve(),
            (parent / "images" / p.name).resolve(),
            (pp / p).resolve(),
            (pp / stripped_path).resolve(),
            (pp / "images" / stripped_path).resolve(),
            (pp / "images" / p.name).resolve(),
        ]
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _safe_bbox(raw_bbox: Any) -> List[float]:
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return [0.0, 0.0, 1.0, 1.0]
        out: List[float] = []
        for idx in range(4):
            try:
                out.append(float(raw_bbox[idx]))
            except (TypeError, ValueError):
                out.append(0.0 if idx < 2 else 1.0)
        x1, y1, x2, y2 = out
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        return [x1, y1, x2, y2]

    @staticmethod
    def _safe_str_list(raw: Any, *, max_items: int = 6, max_len: int = 300) -> List[str]:
        if not isinstance(raw, list):
            return []
        out: List[str] = []
        for item in raw[:max_items]:
            text = MineruLayoutExtractor._normalize_text(str(item or ""))
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            out.append(text)
        return out

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _stderr_indicates_failure(stderr_text: str) -> bool:
        probe = str(stderr_text or "").strip().lower()
        if not probe:
            return False
        if "traceback (most recent call last)" in probe:
            return True
        if "modulenotfounderror:" in probe or "importerror:" in probe:
            return True
        return False

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(str(text or "").replace("\x00", " ").split())
