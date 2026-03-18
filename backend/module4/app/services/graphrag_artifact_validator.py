from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


FINAL_ARTIFACT_REQUIREMENTS: Dict[str, Sequence[str]] = {
    "create_final_documents.parquet": ("id", "title", "raw_content"),
    "create_final_text_units.parquet": ("id", "text", "n_tokens", "document_ids", "entity_ids", "relationship_ids"),
    "create_final_entities.parquet": ("id", "name", "type", "description", "human_readable_id", "text_unit_ids"),
    "create_final_relationships.parquet": (
        "id",
        "source",
        "target",
        "rank",
        "weight",
        "human_readable_id",
        "description",
        "text_unit_ids",
    ),
    "create_final_communities.parquet": ("id", "level", "title", "text_unit_ids", "relationship_ids"),
}

PARTIAL_ARTIFACT_REQUIREMENTS: Dict[str, Sequence[str]] = {
    "create_base_text_units.parquet": ("id", "chunk", "document_ids", "n_tokens"),
}

OPTIONAL_PARTIAL_ENTITY_ARTIFACTS: tuple[str, ...] = (
    "create_summarized_entities.parquet",
    "create_base_extracted_entities.parquet",
)


def _read_schema_names(path: Path) -> set[str]:
    import pyarrow.parquet as pq

    return set(pq.read_schema(path).names)


def _read_row_count(path: Path) -> int:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    metadata = parquet.metadata
    return int(metadata.num_rows if metadata is not None else 0)


def _missing_columns(path: Path, required_columns: Iterable[str]) -> List[str]:
    schema_names = _read_schema_names(path)
    return [name for name in required_columns if name not in schema_names]


@dataclass(frozen=True)
class GraphRAGArtifactValidationResult:
    ok: bool
    import_mode: str
    partial: bool
    stats: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "import_mode": self.import_mode,
            "partial": self.partial,
            "stats": dict(self.stats),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

    def summary(self) -> str:
        parts: List[str] = []
        if self.errors:
            parts.append("; ".join(self.errors))
        if self.warnings:
            parts.append(f"warnings: {'; '.join(self.warnings)}")
        if not parts:
            parts.append("artifact quality gate passed")
        return " | ".join(parts)


class GraphRAGArtifactValidator:
    def validate(self, artifacts_dir: Path) -> GraphRAGArtifactValidationResult:
        artifacts_dir = artifacts_dir.resolve()
        final_documents = artifacts_dir / "create_final_documents.parquet"

        if final_documents.exists():
            final_result = self._validate_final(artifacts_dir)
            if final_result.ok:
                return final_result

            partial_result = self._validate_partial(artifacts_dir)
            if partial_result.ok:
                return GraphRAGArtifactValidationResult(
                    ok=True,
                    import_mode="partial",
                    partial=True,
                    stats=dict(partial_result.stats),
                    errors=[],
                    warnings=list(final_result.errors) + list(partial_result.warnings),
                )
            return final_result

        return self._validate_partial(artifacts_dir)

    def _validate_final(self, artifacts_dir: Path) -> GraphRAGArtifactValidationResult:
        errors: List[str] = []
        warnings: List[str] = []
        stats: Dict[str, int] = {}

        for file_name, required_columns in FINAL_ARTIFACT_REQUIREMENTS.items():
            path = artifacts_dir / file_name
            if not path.exists():
                errors.append(f"missing required final artifact: {file_name}")
                continue
            try:
                missing = _missing_columns(path, required_columns)
                if missing:
                    errors.append(f"{file_name} missing required columns: {', '.join(missing)}")
                    continue
                row_count = _read_row_count(path)
                stats[file_name] = row_count
            except Exception as exc:
                errors.append(f"unable to inspect {file_name}: {type(exc).__name__}: {exc}")

        documents_count = int(stats.get("create_final_documents.parquet", 0))
        text_units_count = int(stats.get("create_final_text_units.parquet", 0))
        entities_count = int(stats.get("create_final_entities.parquet", 0))
        relationships_count = int(stats.get("create_final_relationships.parquet", 0))
        communities_count = int(stats.get("create_final_communities.parquet", 0))

        if documents_count <= 0:
            errors.append("final artifact set has no documents")
        if text_units_count <= 0:
            errors.append("final artifact set has no text units")
        if entities_count <= 0:
            warnings.append("final artifact set has no entities")
        if relationships_count <= 0:
            warnings.append("final artifact set has no relationships")
        if communities_count <= 0:
            warnings.append("final artifact set has no communities")

        return GraphRAGArtifactValidationResult(
            ok=not errors,
            import_mode="final",
            partial=False,
            stats=stats,
            errors=errors,
            warnings=warnings,
        )

    def _validate_partial(self, artifacts_dir: Path) -> GraphRAGArtifactValidationResult:
        errors: List[str] = []
        warnings: List[str] = []
        stats: Dict[str, int] = {}

        for file_name, required_columns in PARTIAL_ARTIFACT_REQUIREMENTS.items():
            path = artifacts_dir / file_name
            if not path.exists():
                errors.append(f"missing required partial artifact: {file_name}")
                continue
            try:
                missing = _missing_columns(path, required_columns)
                if missing:
                    errors.append(f"{file_name} missing required columns: {', '.join(missing)}")
                    continue
                row_count = _read_row_count(path)
                stats[file_name] = row_count
            except Exception as exc:
                errors.append(f"unable to inspect {file_name}: {type(exc).__name__}: {exc}")

        if int(stats.get("create_base_text_units.parquet", 0)) <= 0:
            errors.append("partial artifact set has no text units")

        found_optional_graph = False
        for file_name in OPTIONAL_PARTIAL_ENTITY_ARTIFACTS:
            path = artifacts_dir / file_name
            if not path.exists():
                continue
            found_optional_graph = True
            try:
                missing = _missing_columns(path, ("entity_graph",))
                if missing:
                    errors.append(f"{file_name} missing required columns: {', '.join(missing)}")
                    continue
                stats[file_name] = _read_row_count(path)
            except Exception as exc:
                errors.append(f"unable to inspect {file_name}: {type(exc).__name__}: {exc}")
        if not found_optional_graph:
            warnings.append("partial artifact set does not include entity graph output")

        return GraphRAGArtifactValidationResult(
            ok=not errors,
            import_mode="partial",
            partial=True,
            stats=stats,
            errors=errors,
            warnings=warnings,
        )
