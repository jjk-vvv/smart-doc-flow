from __future__ import annotations

import hashlib
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.runtime.artifact_support_runtime import ArtifactSupportRuntime


class _Logger:
    def warning(self, *args, **kwargs) -> None:
        return None


def test_resolve_trace_artifact_ref_groups_external_files_by_file_hash(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    source_dir = tmp_path / "scratch" / "doc_a"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / "figure one.png"
    source_file.write_bytes(b"fake-image")

    runtime = ArtifactSupportRuntime(
        artifact_root_factory=lambda: artifact_root,
        logger=_Logger(),
    )

    file_hash = "43c0b0b8310c17a8fe3117fa08b4570cb5b010130f3edf979ada62f80493dff9"
    fragment, url = runtime.resolve_trace_artifact_ref(
        {
            "image_path": str(source_file),
            "file_hash": file_hash,
        }
    )

    expected_digest = hashlib.sha1(str(source_file.resolve()).encode("utf-8", "ignore")).hexdigest()[:16]

    assert fragment is not None
    assert fragment.startswith("linked/43c0b0b8310c/")
    assert Path(fragment).name == f"{expected_digest}_figure_one.png"
    assert (artifact_root / fragment).read_bytes() == b"fake-image"
    assert url == runtime.artifact_url_from_fragment(fragment)


def test_artifact_fragment_from_path_keeps_existing_artifact_relative_path(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    target = artifact_root / "pdf_parse" / "mineru" / "filehash" / "layout.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"layout")

    runtime = ArtifactSupportRuntime(
        artifact_root_factory=lambda: artifact_root,
        logger=_Logger(),
    )

    fragment = runtime.artifact_fragment_from_path(str(target), source_bucket="ignored")

    assert fragment == "pdf_parse/mineru/filehash/layout.png"
