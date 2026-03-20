# Module 2 Assistant 1 Vector Rebuild Design

Date: 2026-03-19

## Summary

This design introduces a new parallel assistant foundation under `backend/module2/app/assistant_1/`.

It does not modify the current Module 2 assistant implementation.
It does not depend on the current Module 2 assistant prompt stack.
It does not require changing the current backend routing before the new pipeline is ready.

The approved direction is:

- create a new `assistant_1` directory and keep all new implementation isolated there
- treat existing MinerU and Gemini Vision artifacts as upstream inputs, not something to redesign in this pass
- rebuild document understanding around a new intermediate representation instead of around the current assistant payload shape
- merge MinerU markdown, MinerU reading-order objects, and Gemini Vision table/figure outputs into one complete document view
- clean that merged document into a retrieval-grade markdown artifact
- split the cleaned document into multiple knowledge-unit types instead of relying on naive whole-document chunking
- generate Gemini embeddings for both document units and user queries
- store embeddings in PostgreSQL with `pgvector`
- retrieve by vector similarity first, with the option to add hybrid ranking later

The key architectural conclusion is:

`the merged markdown file is an important product artifact, but it is not the primary retrieval unit`

The primary retrieval unit should be a typed knowledge record such as:

- narrative chunk
- table overview
- table row
- figure overview
- figure dataframe row

That is the only way to support later file-grounded Q&A with stable row-level and figure-level recall quality.

## Why This Rebuild Exists

The current Module 2 assistant has accumulated too many responsibilities in one interaction path:

- chat interaction
- file-grounded extraction
- table/image follow-up
- prompt steering
- partial memory behavior
- tool orchestration

The user's new requirement is different.
The rebuild should first establish a stronger knowledge substrate:

1. take the parsed document outputs that already exist
2. reconstruct a complete, readable, retrieval-grade document
3. normalize the content
4. split it into high-value knowledge units
5. embed and store those units in a vector database
6. retrieve relevant units for later answering and action planning

This is a foundational rebuild rather than a prompt-tuning patch.

## Scope

This spec covers:

- new `assistant_1` architecture
- artifact discovery and path resolution
- merged markdown generation
- markdown cleaning rules
- knowledge-unit extraction rules
- Gemini embedding integration
- PostgreSQL `pgvector` schema and ingestion flow
- vector retrieval flow
- phased implementation plan

This spec does not cover:

- replacing MinerU
- replacing Gemini Vision extraction prompts
- replacing the current Module 2 assistant entrypoint right away
- frontend wiring to the new assistant before the pipeline is stable
- final chat-answer style tuning

## Non-Goals

- Do not modify current `backend/module2/app/assistant/` files in this pass.
- Do not rewrite current parser behavior in this pass.
- Do not force the new pipeline to own CRUD or NL2SQL execution yet.
- Do not assume current assistant session storage is reusable as the new vector store contract.
- Do not reduce the design to one monolithic merged markdown file and call that retrieval-ready.

## Current State Snapshot

### Upstream Inputs Already Exist

The current Module 2 parse chain already emits the main ingredients needed by the rebuild:

- MinerU run pointer metadata
- MinerU run meta metadata
- MinerU markdown output
- MinerU `content_list.json`
- Gemini Vision outputs normalized into assistant payload artifacts

Confirmed artifact patterns include:

- `backend/module2/artifacts/pdf_parse/mineru/<file_hash>/mineru_run_pointer.json`
- `backend/module2/artifacts/pdf_parse/mineru/<file_hash>/mineru_run_meta.json`
- `backend/module2/.mcache/.../o/i/auto/i.md`
- `backend/module2/.mcache/.../o/i/auto/i_content_list.json`
- `backend/module2/artifacts/assistant_payload/<file_hash_prefix>/...json`

### Important Observations

1. MinerU markdown alone is not enough.
   It contains narrative text and object placeholders, but table and image semantics are incomplete.

2. Gemini Vision outputs alone are not enough.
   They contain rich table and figure understanding, but not the document reading order.

3. `content_list.json` is the real structural spine.
   It preserves page order, object type, local object location, captions, footnotes, and image references.

4. The current database storage does not yet provide a dedicated knowledge-unit vector schema.
   `pgvector` is available in dependencies, but a purpose-built vector layer is still missing.

These observations drive the design choice below.

## Approaches Considered

### Approach A: Markdown-First Merge

Build the new assistant around raw MinerU markdown and append table/figure summaries after the document body.

Pros:

- simplest to implement
- fastest to get a first artifact on disk

Cons:

- breaks original reading order
- separates figures and tables from the paragraphs that reference them
- harms later retrieval quality
- makes page-local follow-up much harder

This is not recommended.

### Approach B: Object-Only Knowledge Store

Ignore merged markdown as a primary deliverable and only store structured objects such as tables, rows, figures, and small text blocks.

Pros:

- retrieval precision can be high for structured objects
- works well for highly tabular documents

Cons:

- weak for prose-heavy documents
- poor for section-level understanding
- produces fragmented context for downstream answering
- loses the user's desire for a complete clean markdown output

This is also not recommended.

### Approach C: IR-First Reconstruction

Create a new intermediate representation that unifies:

- document metadata
- ordered content blocks from `content_list.json`
- MinerU markdown-derived narrative text
- Gemini Vision table/figure enrichments

Then derive multiple downstream artifacts from that shared representation:

- merged raw markdown
- merged clean markdown
- knowledge units
- vector rows
- sidecar source index

Pros:

- preserves document order
- keeps visual objects grounded in local context
- supports both human-readable output and retrieval-grade structured storage
- makes later assistant answering, source tracing, and schema planning much easier

Cons:

- more upfront design work
- requires clear matching logic between content list objects and vision outputs

This is the recommended and approved approach.

## Core Design

## Architectural Principle

`assistant_1` should be built as an ingest-and-retrieve substrate, not as a chat-first assistant package.

The internal flow should be:

1. resolve artifact paths for a document
2. load upstream artifacts
3. match content-list objects with visual outputs
4. build a unified document bundle
5. render merged raw markdown
6. clean and normalize markdown
7. derive typed knowledge units
8. embed knowledge units with Gemini embedding model
9. store them in PostgreSQL with `pgvector`
10. retrieve by vector similarity for future assistant use

## Directory Layout

All new code lives under:

- `backend/module2/app/assistant_1/`

Recommended first-stage structure:

- `backend/module2/app/assistant_1/__init__.py`
- `backend/module2/app/assistant_1/models.py`
- `backend/module2/app/assistant_1/path_resolver.py`
- `backend/module2/app/assistant_1/source_loader.py`
- `backend/module2/app/assistant_1/matcher.py`
- `backend/module2/app/assistant_1/bundle_builder.py`
- `backend/module2/app/assistant_1/markdown_renderer.py`
- `backend/module2/app/assistant_1/markdown_cleaner.py`
- `backend/module2/app/assistant_1/knowledge_units.py`
- `backend/module2/app/assistant_1/embedder_gemini.py`
- `backend/module2/app/assistant_1/pgvector_store.py`
- `backend/module2/app/assistant_1/ingest_pipeline.py`
- `backend/module2/app/assistant_1/retrieval_pipeline.py`
- `backend/module2/app/assistant_1/sql/001_assistant1_pgvector.sql`
- `backend/module2/app/assistant_1/scripts/build_bundle.py`
- `backend/module2/app/assistant_1/scripts/ingest_document.py`
- `backend/module2/app/assistant_1/scripts/query_vector.py`

## Module Responsibilities

Each file should keep one clear boundary and one clear purpose.

- `models.py`
  Defines typed data classes, enums, and shared payload contracts used across assistant_1.

- `path_resolver.py`
  Resolves artifact locations for a document from `file_hash` and related metadata.

- `source_loader.py`
  Loads markdown, JSON, and metadata from upstream artifact files and normalizes them into runtime structures.

- `matcher.py`
  Matches MinerU content-list visual placeholders with assistant payload tables and figures.

- `bundle_builder.py`
  Builds the canonical ordered `DocumentBundle` from loaded sources and match results.

- `markdown_renderer.py`
  Renders the unified bundle into raw markdown, clean-markdown candidates, and sidecar index data.

- `markdown_cleaner.py`
  Cleans rendered markdown into a retrieval-grade artifact without paraphrasing or inventing content.

- `knowledge_units.py`
  Splits bundle content into typed knowledge units such as `narrative_chunk`, `table_row`, and `figure_dataframe_row`.

- `embedder_gemini.py`
  Encapsulates Gemini embedding API calls, batching, retry handling, and vector validation.

- `pgvector_store.py`
  Owns assistant_1-only schema setup, document upsert, unit upsert, and similarity search queries.

- `ingest_pipeline.py`
  Orchestrates the full offline ingest path from artifact resolution to vector persistence.

- `retrieval_pipeline.py`
  Embeds user queries, searches stored vectors, and returns a retrieval context pack for later assistant use.

- `scripts/*.py`
  Provide thin operator entrypoints for bundle build, document ingest, and manual vector query workflows.

## Data Model

### 1. `DocumentSourceBundle`

Represents resolved upstream inputs for one document.

Suggested fields:

- `file_hash`
- `file_name`
- `mineru_run_key`
- `mineru_run_token`
- `mineru_run_dir`
- `mineru_markdown_path`
- `mineru_content_list_path`
- `assistant_payload_path`
- `images_dir`
- `metadata`

Purpose:

- a thin resolved-input layer
- no merge logic
- easy to inspect and test

### 2. `DocumentBundle`

Represents the unified assistant_1 document IR.

Suggested fields:

- `document_id`
- `file_hash`
- `file_name`
- `source_bundle`
- `pages`
- `blocks`
- `tables`
- `figures`
- `stats`
- `build_warnings`

The `blocks` list should be the canonical ordered sequence.
Each block should be one of:

- narrative text block
- heading block
- table block
- figure block
- formula-like image block
- list block
- caption block

### 3. `KnowledgeUnit`

Represents a retrieval item.

Suggested fields:

- `unit_id`
- `document_id`
- `file_hash`
- `unit_type`
- `title`
- `content`
- `page_start`
- `page_end`
- `source_block_ids`
- `metadata`
- `embedding`

### 4. `MergedIndexEntry`

Represents sidecar trace metadata for rendered markdown blocks.

Suggested fields:

- `render_block_id`
- `unit_candidates`
- `page`
- `source_type`
- `source_object_id`
- `image_path`
- `bbox_norm`
- `caption`

This should not be exposed in final user-facing prose.
It exists to support later traceability and debugging.

## Artifact Resolution Design

`path_resolver.py` should resolve a document's upstream inputs without depending on the current assistant runtime.

Resolution strategy:

1. locate MinerU pointer file by `file_hash`
2. read actual run directory from `mineru_run_pointer.json`
3. read `mineru_run_meta.json`
4. resolve:
   - `markdown_path`
   - `content_list_path`
   - `images_dir`
5. resolve assistant payload artifact by `file_hash`

The resolver should be permissive about file-system layout drift:

- use pointer data first
- use meta data second
- use controlled directory scanning only as a fallback

The resolver should return warnings instead of throwing immediately when one optional artifact is missing.
Only truly required inputs for the chosen pipeline stage should hard-fail.

## Merge Strategy

This is the most important design section.

## Why A Simple Concatenation Fails

If we simply append Gemini Vision outputs after MinerU markdown:

- tables lose their local section context
- figures become detached from nearby explanatory text
- duplicate captions and duplicate descriptions appear
- retrieval chunks become noisy

That would create a readable artifact, but not a reliable one.

## The Correct Merge Spine

The merge must be driven by `content_list.json`.

It should be treated as:

- the ordered list of page-local document objects
- the canonical sequence for reconstructing the document
- the anchor for matching image/table placeholders with Gemini Vision outputs

## Matching Logic

`matcher.py` should align content-list objects to assistant payload objects with a weighted strategy:

### Primary match

- normalized `img_path` basename equals visual object's `image_path` basename

### Secondary match

- same page
- same or highly similar normalized bounding box

### Tertiary match

- caption similarity
- object type compatibility

Type compatibility should prefer:

- `content_list.type == image` to figure-like payloads
- table-like image regions to table payloads when captions and bbox agree

The matcher should produce:

- exact match
- probable match
- unmatched content object
- unmatched payload object

Unmatched objects should remain visible in warnings so we can improve coverage later.

## Unified Block Construction

`bundle_builder.py` should convert the ordered content-list sequence into unified blocks:

- text blocks become narrative or heading blocks
- image placeholders become figure/table/formula blocks if a visual payload match exists
- otherwise image placeholders become lightweight unresolved visual blocks
- captions and footnotes should attach to the nearest compatible visual block

For matched table objects, the constructed block should include:

- title or caption
- header rows
- normalized headers
- rows
- notes
- confidence
- image reference
- page and bbox metadata

For matched figure objects, the constructed block should include:

- caption
- figure type
- insights
- dataframe if present
- text blocks if present
- content modes
- confidence
- image reference
- page and bbox metadata

## Markdown Rendering Design

`markdown_renderer.py` should generate at least two outputs.

### `merged.raw.md`

Purpose:

- preserve as much structure and source richness as possible
- useful for inspection and debugging

Rendering behavior:

- keep headings
- keep paragraph order
- render tables as markdown tables when rectangular, or fallback bullet rows when not
- render figures with a short caption block plus extracted insights and dataframe summary
- keep light provenance comments only if explicitly enabled for debug mode

### `merged.clean.md`

Purpose:

- human-readable
- retrieval-friendly
- no noisy internal tracing fields

Rendering behavior:

- remove raw ids, ref ids, bbox, internal object ids
- deduplicate repeated captions and notes
- collapse redundant blank lines
- normalize heading spacing
- preserve table row order and figure takeaways
- keep only user-meaningful text

## Markdown Cleaning Design

`markdown_cleaner.py` should operate on the rendered markdown, not on raw upstream artifacts.

Cleaning rules should include:

- normalize line endings to `\n`
- collapse runs of blank lines
- trim trailing spaces
- remove empty headings
- deduplicate adjacent duplicate paragraphs
- remove obvious OCR separator noise
- preserve meaningful list and table formatting
- standardize markdown table separators
- normalize repeated spaces around Chinese and English punctuation carefully

The cleaner should not aggressively rewrite content.
Its job is to reduce noise, not paraphrase meaning.

## Knowledge-Unit Design

The retrieval layer should not embed only the full clean markdown or naive fixed windows.

`knowledge_units.py` should emit multiple unit types.

### Unit Type: `narrative_chunk`

Use for:

- section text
- prose paragraphs
- explanatory content

Recommended chunking rule:

- chunk by heading boundaries first
- then split oversized sections by paragraph groups

### Unit Type: `table_overview`

Use for:

- what the table is about
- its headers
- row count
- caption and notes

This improves coarse recall when the user asks broad questions like:

- "这份表主要讲什么"
- "这个表里有哪些字段"

### Unit Type: `table_row`

Use for:

- row-level precise recall
- row-specific values
- later structured follow-up

Each row unit should include:

- caption or table title context
- headers
- one row rendered as labeled fields
- page and row index metadata

This is critical for questions like:

- "某个站点某个时间的 PM10 是多少"

### Unit Type: `figure_overview`

Use for:

- chart or figure summary
- caption
- key insights
- available data modes

### Unit Type: `figure_dataframe_row`

Use for:

- figure-derived dataframe rows
- chart data points
- image-derived table-like rows

This is critical when the answer comes from a chart rather than a true table.

### Optional Later Unit Types

- `formula_block`
- `glossary_fact`
- `cross_page_table_continuation`

These are not required in phase 1.

## Embedding Model Design

The recommended embedding model is:

- `gemini-embedding-001`

Reasons:

- aligns with the user's Gemini-first model strategy
- supports retrieval-oriented embedding workflows
- avoids introducing a second provider at the foundation layer

Configuration guidance:

- use retrieval-document mode for stored units
- use retrieval-query mode for user queries if supported by the chosen endpoint
- default output dimensionality to `1536`
- keep output dimensionality configurable for later expansion

`embedder_gemini.py` should expose a narrow interface:

- embed document units in batch
- embed one query
- return vector length and model metadata

It should also include:

- retry policy
- response-shape validation
- basic batching controls

## PostgreSQL Vector Store Design

`pgvector_store.py` should own all new persistence logic for the assistant_1 knowledge base.

It should not be mixed into the current `storage.py` in phase 1.

## Schema Recommendation

Table names should avoid `module2` prefixes, matching the user's preference.

Recommended tables:

### `doc_knowledge_document`

Suggested columns:

- `id uuid primary key`
- `file_hash text not null unique`
- `file_name text not null`
- `source_bundle_json jsonb not null`
- `merged_raw_markdown text`
- `merged_clean_markdown text`
- `build_stats_json jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

### `doc_knowledge_unit`

Suggested columns:

- `id uuid primary key`
- `document_id uuid not null references doc_knowledge_document(id) on delete cascade`
- `file_hash text not null`
- `unit_type text not null`
- `title text`
- `content text not null`
- `page_start int`
- `page_end int`
- `source_block_ids jsonb not null default '[]'::jsonb`
- `unit_meta_json jsonb not null default '{}'::jsonb`
- `embedding vector(1536) not null`
- `created_at timestamptz not null default now()`

### `doc_ingest_run`

Suggested columns:

- `id uuid primary key`
- `file_hash text not null`
- `status text not null`
- `stage text not null`
- `warning_count int not null default 0`
- `error_text text`
- `stats_json jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `finished_at timestamptz`

Optional later index additions:

- `hnsw` or `ivfflat` on `doc_knowledge_unit.embedding`

Phase 1 recommendation:

- start with exact similarity search or simple vector search without aggressive ANN tuning
- add ANN indexing after data volume and latency patterns are known

## Ingestion Pipeline Design

`ingest_pipeline.py` should orchestrate the full offline ingest.

Stages:

1. resolve paths
2. load sources
3. match visual objects
4. build document bundle
5. render raw markdown
6. clean markdown
7. derive knowledge units
8. embed units
9. upsert document and units
10. record ingest run

The pipeline should produce local artifacts for inspection:

- `merged.raw.md`
- `merged.clean.md`
- `merged.index.json`
- `knowledge_units.jsonl`
- `ingest_summary.json`

These should live under a dedicated assistant_1 artifact area rather than mixed into existing assistant artifacts.

## Retrieval Pipeline Design

`retrieval_pipeline.py` should be simple in phase 1.

Flow:

1. embed user query
2. run vector similarity search against `doc_knowledge_unit`
3. return top-k units with metadata
4. optionally group by document or unit type
5. optionally assemble a retrieval context pack for downstream answering

Recommended defaults:

- `top_k = 8` for broad queries
- `top_k = 12` for row-heavy queries
- allow unit-type filters such as:
  - `table_row`
  - `figure_dataframe_row`
  - `narrative_chunk`

Later hybrid extensions can add:

- lexical reranking
- metadata filtering by page range or object type
- per-document search scope

## Error Handling Strategy

The new pipeline should distinguish clearly between:

### Hard failures

- required artifact missing
- unreadable JSON artifact
- embedding request failure after retries
- database write failure

### Soft degradations

- unmatched visual objects
- missing assistant payload but available MinerU markdown
- malformed table rows in one object
- figure with no dataframe but usable caption and insights

Soft degradations should not abort the whole document ingest unless they leave the bundle empty.

## Testing Strategy

Phase 1 testing should focus on determinism and inspectability.

### Unit tests

- path resolution tests
- object matching tests
- markdown cleaning tests
- knowledge-unit splitting tests

### Fixture tests

Use real saved artifacts from current Module 2 runs:

- one prose-heavy PDF
- one table-heavy workbook-derived document
- one figure-heavy document

### Acceptance checks

- merged raw markdown preserves document order
- clean markdown removes internal noise without losing business meaning
- table rows become row-level knowledge units
- figure dataframe rows become retrievable knowledge units
- query embedding returns relevant row-level matches for specific value queries

## Implementation Phases

## Phase 1: Local Reconstruction Core

Build:

- `models.py`
- `path_resolver.py`
- `source_loader.py`
- `matcher.py`
- `bundle_builder.py`
- `markdown_renderer.py`
- `markdown_cleaner.py`
- `knowledge_units.py`

Goal:

- generate complete merged artifacts and knowledge-unit JSON without embeddings or database writes

## Phase 2: Vectorization And Persistence

Build:

- `embedder_gemini.py`
- `pgvector_store.py`
- `sql/001_assistant1_pgvector.sql`
- `ingest_pipeline.py`

Goal:

- ingest one document end to end into PostgreSQL with vector rows

## Phase 3: Retrieval Entry

Build:

- `retrieval_pipeline.py`
- `scripts/query_vector.py`

Goal:

- query by natural language and return useful matched units

## Phase 4: Assistant Integration

Not part of the first coding pass.

Goal:

- let future assistant logic consume retrieved context from assistant_1

## Execution Plan

The first implementation pass should proceed in this order:

1. define the core data classes in `models.py`
2. implement path resolution for MinerU and assistant payload artifacts
3. implement source loading and JSON parsing helpers
4. implement content-object to visual-payload matching
5. build the unified bundle
6. render `merged.raw.md`
7. clean to `merged.clean.md`
8. emit `knowledge_units.jsonl`
9. add Gemini embedding client
10. add PostgreSQL vector storage and ingest scripts

This sequencing keeps the system inspectable at every stage.

## Final Recommendation

The rebuild should start with the knowledge substrate, not with chat behavior.

The most important design commitments are:

- keep all new work isolated in `assistant_1`
- use `content_list.json` as the merge spine
- build an intermediate representation first
- output both merged markdown artifacts and typed knowledge units
- store embeddings in PostgreSQL with `pgvector`
- optimize for row-level and figure-level recall, not only whole-document similarity

If this design is followed, the next generation of the information extraction assistant will have a much stronger base for:

- file-grounded Q&A
- specified-content extraction
- schema planning
- NL2SQL grounding
- later audited action flows
