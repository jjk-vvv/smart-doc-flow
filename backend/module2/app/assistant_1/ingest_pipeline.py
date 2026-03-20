from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .bundle_builder import Assistant1BundleBuilder
from .config import Assistant1Settings
from .embedder_gemini import GeminiEmbeddingClient
from .knowledge_units import Assistant1KnowledgeUnitExtractor
from .markdown_cleaner import Assistant1MarkdownCleaner
from .markdown_renderer import Assistant1MarkdownRenderer
from .models import DocumentBundle, KnowledgeUnit
from .path_resolver import Assistant1PathResolver
from .pgvector_store import Assistant1PgVectorStore
from .source_loader import Assistant1SourceLoader


class Assistant1IngestPipeline:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.path_resolver = Assistant1PathResolver(self.settings)
        self.source_loader = Assistant1SourceLoader()
        self.bundle_builder = Assistant1BundleBuilder()
        self.renderer = Assistant1MarkdownRenderer()
        self.cleaner = Assistant1MarkdownCleaner()
        self.unit_extractor = Assistant1KnowledgeUnitExtractor()
        self.embedder = GeminiEmbeddingClient(self.settings)

    def build_bundle(self, file_hash: str) -> dict[str, Any]:
        source_bundle = self.path_resolver.resolve(file_hash)
        loaded = self.source_loader.load(source_bundle)
        bundle = self.bundle_builder.build(loaded)
        raw_markdown, clean_candidate, merged_index = self.renderer.render(bundle)
        clean_markdown = self.cleaner.clean(clean_candidate)
        units = self.unit_extractor.extract(bundle)
        artifact_dir = self._artifact_dir(file_hash)
        self._write_artifacts(
            artifact_dir=artifact_dir,
            bundle=bundle,
            raw_markdown=raw_markdown,
            clean_markdown=clean_markdown,
            merged_index=merged_index,
            knowledge_units=units,
        )
        return {
            "file_hash": file_hash,
            "artifact_dir": str(artifact_dir),
            "bundle_stats": bundle.stats,
            "warning_count": len(bundle.build_warnings),
            "warnings": bundle.build_warnings,
            "knowledge_unit_count": len(units),
        }

    def ingest(self, file_hash: str, *, persist: bool = True) -> dict[str, Any]:
        source_bundle = self.path_resolver.resolve(file_hash)
        loaded = self.source_loader.load(source_bundle)
        bundle = self.bundle_builder.build(loaded)
        raw_markdown, clean_candidate, merged_index = self.renderer.render(bundle)
        clean_markdown = self.cleaner.clean(clean_candidate)
        units = self.unit_extractor.extract(bundle)
        artifact_dir = self._artifact_dir(file_hash)
        self._write_artifacts(
            artifact_dir=artifact_dir,
            bundle=bundle,
            raw_markdown=raw_markdown,
            clean_markdown=clean_markdown,
            merged_index=merged_index,
            knowledge_units=units,
        )

        persisted = False
        if persist:
            if not self.embedder.ready:
                raise RuntimeError("Gemini embedding config is missing; cannot persist vectors")
            vectors = self.embedder.embed_documents([unit.content for unit in units])
            for unit, vector in zip(units, vectors):
                unit.embedding = vector
            asyncio.run(self._persist(bundle, raw_markdown, clean_markdown, units))
            persisted = True

        summary = {
            "file_hash": file_hash,
            "document_id": bundle.document_id,
            "artifact_dir": str(artifact_dir),
            "bundle_stats": bundle.stats,
            "warning_count": len(bundle.build_warnings),
            "warnings": bundle.build_warnings,
            "knowledge_unit_count": len(units),
            "persisted": persisted,
        }
        (artifact_dir / "ingest_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    async def _persist(
        self,
        bundle: DocumentBundle,
        raw_markdown: str,
        clean_markdown: str,
        units: list[KnowledgeUnit],
    ) -> None:
        store = Assistant1PgVectorStore(self.settings)
        try:
            await store.init_schema()
            document_id = await store.upsert_document(bundle, raw_markdown, clean_markdown)
            await store.replace_units(document_id, bundle.file_hash, units)
            await store.record_ingest_run(
                file_hash=bundle.file_hash,
                status="success",
                stage="persist",
                warning_count=len(bundle.build_warnings),
                stats={
                    "document_id": document_id,
                    "unit_count": len(units),
                    "bundle_stats": bundle.stats,
                },
            )
        finally:
            await store.close()

    def _artifact_dir(self, file_hash: str) -> Path:
        target = self.settings.artifact_root_dir / file_hash[:12]
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _write_artifacts(
        self,
        *,
        artifact_dir: Path,
        bundle: DocumentBundle,
        raw_markdown: str,
        clean_markdown: str,
        merged_index: list[dict[str, Any]],
        knowledge_units: list[KnowledgeUnit],
    ) -> None:
        (artifact_dir / "merged.raw.md").write_text(raw_markdown, encoding="utf-8")
        (artifact_dir / "merged.clean.md").write_text(clean_markdown, encoding="utf-8")
        (artifact_dir / "merged.index.json").write_text(
            json.dumps(merged_index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (artifact_dir / "bundle.json").write_text(
            json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with (artifact_dir / "knowledge_units.jsonl").open("w", encoding="utf-8") as handle:
            for unit in knowledge_units:
                handle.write(json.dumps(unit.to_dict(), ensure_ascii=False) + "\n")
