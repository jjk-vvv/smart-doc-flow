# Module 4 GraphRAG Production Alignment Design

Date: 2026-03-16

## Summary

This spec turns the approved Module 4 direction into a production-alignment execution plan.
It is narrower and more implementation-focused than the earlier design in:

- `docs/superpowers/specs/2026-03-15-module4-graphrag-sync-frontend-design.md`

The approved primary path remains:

`module 2 upload persists original file -> module 4 sync starts immediately -> module 4 normalizes supported files into input/*.txt -> GraphRAG indexing runs -> artifacts are imported into graph storage -> frontend renders a Neo4j-style graph workbench`

This spec exists because the architecture direction is now approved, but the current Module 4 state is still below `D:\ragtest` in three critical ways:

- the runtime does not yet guarantee real GraphRAG execution
- the prompt system is domain-shifted in the right direction but not yet broad or stable enough
- the frontend graph experience is improving, but it is still backed by an incomplete graph-production chain

The goal of this design is to convert that gap into a clear, staged execution plan with hard acceptance criteria.

## Why This Spec Exists

Recent investigation surfaced a mismatch between the intended Module 4 design and the actual shipped behavior.

Observed facts:

- Module 4 now has workspace preparation, prompt asset management, input normalization, and upload-sync plumbing.
- Most Module 4 workspaces still stop at `prepared` with `last_index_status = skipped`.
- The current Python environment for Module 4 does not guarantee that `python -m graphrag.index` can run successfully.
- The graph APIs currently query Module 4 storage tables and in-memory fallbacks, not a finalized Neo4j-backed query layer.
- The prompt assets were successfully shifted away from the old `ragtest` xuanhuan-novel domain, but extraction quality is still inconsistent on real business documents.

The result is a system that is architecturally pointed in the right direction, but operationally still in the `GraphRAG-ready` stage rather than the `GraphRAG-producing` stage.

This spec defines how to close that gap.

## Goals

- Make Module 4 a real GraphRAG-first production path, not only a workspace-preparation layer.
- Align Module 4 runtime capability with the working GraphRAG chain proven in `D:\ragtest`.
- Expand the prompt system from a narrow business-document bias into a controlled multi-domain extraction framework.
- Ensure Module 2 uploads sync into Module 4 immediately after original artifact persistence succeeds.
- Preserve `.txt` as the canonical internal GraphRAG corpus format for Module 4.
- Make Module 4 graph outputs stable enough to support a Neo4j-style frontend workbench.
- Keep a clean path for later Module 2 evidence enhancement without making it the primary graph input source.

## Non-Goals

- Do not revert Module 4 back to using Module 2 structured extraction JSON as the main graph input.
- Do not force the frontend to embed Neo4j Browser.
- Do not make OCR or image understanding the mandatory first-phase graph input path.
- Do not redesign unrelated product surfaces outside Module 4 and its upload-sync dependency on Module 2.
- Do not collapse the final design into one monolithic prompt or one monolithic service class.

## Current State Findings

### 1. Runtime Gap

- `backend/module4/requirements.txt` does not yet reflect the full GraphRAG runtime used by `D:\ragtest`.
- The current environment cannot be assumed to run `python -m graphrag.index` successfully.
- Because of that, Module 4 can prepare workspaces without reliably producing GraphRAG artifacts.

### 2. Workspace And Job Gap

- Workspace manifests already exist and contain useful normalization metadata.
- Many manifests still show `status = prepared`, `last_index_status = skipped`, and `latest_output_dir = null`.
- This means the system currently proves ingestion preparation more often than true graph production.

### 3. Prompt Maturity Gap

- Prompt assets are now managed and materialized correctly per workspace.
- The prompt domain is closer to the real project than the original `ragtest` prompts.
- The current prompt system is still too narrow and too brittle:
  - `entity_extraction` can over-promote dates and numbers into graph nodes
  - `claim_extraction` is not yet stable enough for evidence-oriented graph enrichment
  - `community_report` is the strongest prompt, but it still trends toward generic summaries

### 4. Graph Query Path Gap

- Module 4 already has graph APIs such as `/module4/graph` and `/module4/graph/neighborhood/{node_id}`.
- These APIs currently query `Module4Storage`, not a final Neo4j query service.
- This is a valid transitional state, but it is not yet equivalent to the `ragtest -> artifacts -> Neo4j -> graph browsing` path.

### 5. Frontend Gap

- The graph workbench has moved toward a Neo4j-style experience, but the rendering layer still depends on graph data that is not yet fully stable.
- Layout, labeling, interaction, and detail behavior cannot be considered final until upstream graph quality is stabilized.

## Primary Decisions

### Decision 1: Keep GraphRAG-First As The Mainline

Module 4 should continue using:

`uploaded file -> normalized text -> GraphRAG -> graph`

Module 2 remains:

- the upload and persistence owner
- the document parsing owner for Module 2 features
- the later evidence enhancement provider

### Decision 2: Treat `.txt` As Canonical Internal Input

External uploads may be:

- `.txt`
- `.pdf`
- `.docx`
- `.xlsx`
- image-derived OCR text

Internal GraphRAG input must still become:

- `workspace/input/*.txt`

This preserves compatibility with the `D:\ragtest` GraphRAG pattern and keeps the indexing chain understandable and reproducible.

### Decision 3: Use A Layered Prompt Architecture

Module 4 should not use one giant cross-domain prompt.
It should use:

- a universal extraction skeleton
- a domain profile layer
- a few-shot example layer

### Decision 4: Accept A Transitional Graph Storage Layer

Short term:

- GraphRAG artifacts may continue importing into Module 4 storage so existing APIs stay stable.

Long term:

- the node and edge model must align with the Neo4j semantic graph structure used by `ragtest`
- the query path should be able to move closer to a Neo4j-native graph service without frontend contract churn

## Execution Principles

### 1. Production Path Must Equal Verified Path

Module 4 should only be considered "working" when the normal upload-sync path produces real GraphRAG artifacts through the formal API flow.

### 2. Data Quality Must Be Gated Before UI Beauty

The frontend should not be treated as the primary place to solve graph-production issues.
Graph rendering quality depends on graph data quality first.

### 3. Multi-Domain Coverage Must Be Controlled

Broader prompt coverage should come from explicit domain routing, not from a single prompt that tries to memorize every possible document genre.

### 4. Workspace Isolation Is Mandatory

Every tenant and batch should keep an isolated workspace so jobs remain reproducible, debuggable, and rebuildable.

### 5. Evidence Enhancement Is Phase Two

The first stable release of Module 4 should prioritize:

- upload sync
- normalized text corpus
- GraphRAG indexing
- graph artifact import
- graph browsing

Module 2 evidence enrichment should be added after the graph mainline is stable.

## Workstream A: Runtime And Dependency Alignment

### Objective

Make Module 4 capable of running the same GraphRAG indexing class that is already proven in `D:\ragtest`.

### Tasks

- Expand `backend/module4/requirements.txt` to include the minimum runtime needed for GraphRAG indexing and artifact handling.
- Confirm the exact supported GraphRAG package version and align it deliberately with the `ragtest` working baseline.
- Add startup or health-check validation for:
  - `graphrag` import availability
  - OneAPI reachability
  - Neo4j reachability
  - prompt asset availability
  - workspace root writability
- Improve GraphRAG indexer logging so import failures, missing packages, timeout failures, and artifact-missing failures are distinguishable.

### Deliverables

- Module 4 runtime can execute `python -m graphrag.index`
- health endpoint exposes GraphRAG readiness
- failure states are actionable instead of silent

### Acceptance Criteria

- A local Module 4 workspace can run indexing without `ModuleNotFoundError`
- index failures produce explicit manifest and job-state diagnostics
- one known-good sample document produces a timestamped `output/<timestamp>/artifacts`

## Workstream B: Upload Sync And Input Normalization Hardening

### Objective

Make "upload persisted -> immediate Module 4 sync" reliable and ensure every supported input becomes high-quality `txt` for GraphRAG.

### Tasks

- Keep the immediate sync trigger in Module 2 after original artifact persistence.
- Harden Module 4 normalization for:
  - plain text files
  - PDF
  - DOCX
  - XLSX
  - OCR-generated image text
- Ensure normalization metadata is saved in the workspace manifest, including:
  - file identity
  - original path
  - artifact path
  - quality status
  - parse statistics
  - normalization status
- Formalize quality levels:
  - `ok`
  - `degraded`
  - `failed`
- Prevent placeholder or metadata-only text from silently entering GraphRAG as if it were real document text.

### Deliverables

- deterministic upload-sync contract
- stable normalized `input/*.txt` files
- input quality metadata visible per batch

### Acceptance Criteria

- a single upload only needs to happen once in Module 2
- Module 4 receives file references automatically
- every indexed workspace contains real `input/*.txt` corpus files or explicit normalization failure records

## Workstream C: Multi-Domain Prompt Platform

### Objective

Turn the current prompt set into a broader, more stable prompt framework that can cover multiple document domains without collapsing quality.

### Prompt Architecture

#### Layer 1: Universal Skeleton

Shared rules for:

- output structure
- delimiter handling
- anti-hallucination constraints
- alias deduplication
- numeric and temporal attribute handling
- relationship-strength conventions

#### Layer 2: Domain Profiles

At minimum, support:

- government policy and notices
- statistical bulletins and reports
- contracts and agreements
- enterprise rules and announcements
- project proposals and implementation plans
- academic and research reports
- technical or educational documents
- unknown or mixed documents

#### Layer 3: Few-Shot Packs

Each domain should have:

- 2 to 4 strong positive examples
- at least 1 negative or exclusion-oriented example
- explicit demonstrations of what should remain an attribute instead of becoming a primary node

### Prompt Work Priorities

- rewrite `entity_extraction` first
- rebuild `claim_extraction` into a stricter evidence-oriented extractor
- keep `community_report` grounded and less generic
- keep `summarize_descriptions` concise but improve contradiction handling

### Deliverables

- new prompt asset structure
- domain routing rules
- sample corpus for prompt evaluation
- prompt regression tests

### Acceptance Criteria

- at least 5 document categories produce reasonable core entities and relationships
- dates and numbers are no longer frequently promoted into primary nodes without justification
- `claim_extraction` no longer collapses valid business entities into `NONE`

## Workstream D: GraphRAG Indexing Parity With `ragtest`

### Objective

Make Module 4 produce the same essential artifact family as the proven GraphRAG run in `D:\ragtest`.

### Required Artifact Family

- `create_final_documents.parquet`
- `create_final_text_units.parquet`
- `create_final_entities.parquet`
- `create_final_relationships.parquet`
- `create_final_communities.parquet`
- `create_final_community_reports.parquet`

### Tasks

- run GraphRAG indexing inside Module 4 workspaces, not only in an external reference project
- capture command, log path, output directory, artifact directory, and report directory
- treat missing artifact families as job failure, not soft success
- add a small regression dataset specifically for end-to-end indexing validation

### Deliverables

- first successful Module 4 GraphRAG artifact run
- repeatable regression workspace
- artifact completeness checks

### Acceptance Criteria

- Module 4 can produce a full final artifact family for a known-good sample
- workspace manifest transitions from `prepared` to `ready`
- `latest_output_dir` is populated for successful jobs

## Workstream E: Artifact Import And Graph Query Alignment

### Objective

Make Module 4 graph nodes and edges reflect GraphRAG artifact semantics closely enough that frontend behavior can converge toward Neo4j-style exploration.

### Tasks

- keep importing GraphRAG artifacts into Module 4 storage as the short-term compatibility layer
- ensure semantic coverage for:
  - Document
  - Chunk
  - Entity
  - Community
  - Covariate
  - PART_OF
  - HAS_ENTITY
  - RELATED
  - IN_COMMUNITY
  - HAS_COVARIATE
- align naming, identifiers, and relationship metadata with the `ragtest` import model where practical
- create a clear seam for a later Neo4j-native query layer

### Deliverables

- stable graph import semantics
- cleaner node labels and display names
- consistent edge semantics for frontend rendering

### Acceptance Criteria

- graph queries return artifact-backed entity and relationship structures
- community and chunk relationships are queryable
- node labels no longer skew toward meaningless numeric fragments on known-good input

## Workstream F: Neo4j-Style Frontend Graph Workbench

### Objective

Make the Module 4 frontend feel closer to Neo4j Browser in graph exploration quality while staying fully project-controlled.

### Tasks

- stabilize force-directed layout behavior
- improve drag and simulation responsiveness
- shift from fixed right-side detail occupancy to click-triggered node detail
- improve node naming and type-based color mapping
- strengthen graph label readability and interaction hierarchy
- maintain a project-specific visual language rather than a plain demo graph panel

### Core Interaction Model

- click node -> open contextual detail overlay or inspector
- drag node -> graph smoothly rebalances
- focus node -> neighborhood exploration is easy and visually clear
- search and filter -> reduce graph noise without losing context

### Deliverables

- stable force-directed workbench
- click-to-inspect node detail behavior
- cleaner node styles and label strategy

### Acceptance Criteria

- graph drag interaction feels smooth and continuous
- node details are shown on demand instead of occupying the page by default
- graph layout no longer appears truncated or aggressively re-fit during normal interaction

## Workstream G: Module 2 Evidence Enhancement Layer

### Objective

Add document-grounded evidence details after the GraphRAG mainline is stable.

### Tasks

- map Module 2 evidence artifacts to graph nodes and edges
- expose:
  - `trace_hits`
  - `bbox`
  - `artifact_url`
  - `table_preview`
  - page-level evidence references
- surface these in node detail panels and edge explanation flows

### Deliverables

- graph node evidence cards
- traceable document references
- richer detail views for enterprise and policy documents

### Acceptance Criteria

- selected nodes can display grounded evidence from Module 2
- evidence enrichment does not block the primary graph-production chain

## Workstream H: Observability, Testing, And Release Gates

### Objective

Make the new Module 4 pipeline shippable rather than fragile.

### Tasks

- add regression tests for prompt loading, workspace generation, and runtime configuration
- add end-to-end smoke tests for:
  - sync request
  - workspace preparation
  - GraphRAG indexing
  - artifact import
  - graph query response
- record job states for:
  - `queued`
  - `preparing_input`
  - `normalizing`
  - `indexing`
  - `importing_graph`
  - `ready`
  - `failed`
- define operational dashboards or at least structured logs for job progress

### Deliverables

- end-to-end smoke coverage
- failure visibility
- bounded release gate criteria

### Acceptance Criteria

- known-good upload batches can be validated from upload persistence through graph query
- failures expose stage and reason without manual code inspection

## Milestone Plan

### Milestone A: Runtime Ready

Target outcome:

- Module 4 can run real GraphRAG indexing in its own environment

Exit criteria:

- GraphRAG dependency alignment complete
- readiness checks pass
- one known-good workspace produces final artifacts

### Milestone B: Prompt Breadth And Extraction Stability

Target outcome:

- prompts cover multiple document classes with controlled routing and improved entity quality

Exit criteria:

- prompt regression corpus exists
- entity extraction no longer overproduces date and number nodes on validation samples
- claim extraction produces usable outputs on at least several business-style samples

### Milestone C: Graph Output And Query Alignment

Target outcome:

- Module 4 graph APIs serve artifact-backed graph data with stable semantics

Exit criteria:

- import path produces reliable nodes and edges
- graph APIs return coherent document, entity, chunk, and community structures

### Milestone D: Frontend Neo4j-Style Experience

Target outcome:

- graph browsing feels stable, intentional, and closer to Neo4j-style exploration

Exit criteria:

- node drag is smooth
- details are click-driven
- labels and colors communicate graph structure clearly

### Milestone E: Evidence Enhancement

Target outcome:

- Module 2 evidence becomes a secondary detail layer on top of the semantic graph

Exit criteria:

- node detail can display traceable source evidence
- graph mainline remains independent from evidence augmentation

## Dependencies And Configuration Readiness

The execution plan assumes the following are available and verified:

- Module 4 database DSN
- OneAPI-compatible GraphRAG chat and embedding endpoints
- valid Module 4 GraphRAG API token
- Neo4j connection settings
- writable Module 4 workspace root
- Python environment capable of installing and running the chosen GraphRAG version

Configuration should be treated as ready only when:

- the API base is reachable
- models can be listed
- chat completions work
- embeddings work
- Neo4j credentials can authenticate

## Risks And Mitigations

### Risk 1: Prompt Breadth Reduces Precision

Mitigation:

- use domain routing instead of one giant universal prompt
- maintain regression corpora per domain

### Risk 2: Runtime Parity With `ragtest` Drifts

Mitigation:

- pin GraphRAG runtime intentionally
- compare artifact family completeness against `ragtest`

### Risk 3: Frontend Polishing Starts Before Graph Quality Stabilizes

Mitigation:

- gate major frontend iteration behind artifact-backed graph validation

### Risk 4: Low-Quality OCR Or Fallback Text Pollutes The Graph

Mitigation:

- preserve `quality_status`
- degrade or block indexing for known-bad inputs when needed

## Implementation Order

Recommended order:

1. Runtime and dependency alignment
2. Upload-sync and normalization hardening
3. Multi-domain prompt platform
4. GraphRAG indexing parity
5. Artifact import and graph query alignment
6. Frontend Neo4j-style workbench refinement
7. Module 2 evidence enhancement
8. Final hardening and release gates

## Final Acceptance Standard

Module 4 should be considered aligned with the approved direction only when all of the following are true:

- a normal Module 2 upload automatically starts Module 4 sync
- Module 4 produces real GraphRAG artifacts from normalized `txt` input
- the graph output is close in structural quality to the `ragtest` artifact model
- the prompt system covers multiple document domains with acceptable stability
- the frontend graph workbench is backed by stable graph data and supports Neo4j-style exploration

At that point, Module 4 will no longer be merely a design-correct prototype.
It will become the formal GraphRAG-based knowledge graph production path for the project.
