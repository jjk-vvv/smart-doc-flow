# Module 4 GraphRAG Sync And Frontend Design

Date: 2026-03-15

## Summary

This design redefines Module 4 as the GraphRAG-first knowledge graph pipeline for the project.
The new primary path is:

`upload file in module 2 -> persist original artifact -> immediately sync file references to module 4 -> normalize every supported file into input/*.txt -> run GraphRAG index -> import artifacts into Neo4j -> render a Neo4j-style knowledge graph workbench in the frontend`

Module 2 no longer acts as the primary semantic source for Module 4 graph construction.
Module 2 becomes:

- the upload entry
- the original file storage owner
- an optional evidence enhancement layer for later phases

Module 4 becomes:

- the GraphRAG workspace manager
- the text normalization owner
- the GraphRAG indexing owner
- the Neo4j import owner
- the graph query API owner
- the graph workbench owner in the frontend

## Goals

- Make Module 4 follow the same GraphRAG input idea as `D:\ragtest`: the internal corpus must be plain text files in `input/*.txt`.
- Sync uploads from Module 2 to Module 4 immediately after original files are persisted.
- Ensure Module 4 uses uploaded files as the primary graph input, not Module 2 structured extraction JSON.
- Keep frontend graph APIs JSON-based and frontend-rendered. Do not embed Neo4j Browser or other third-party graph pages.
- Upgrade the Module 4 frontend into a stable, Neo4j-style graph workbench with stronger layout stability, visual hierarchy, and graph interaction quality.
- Preserve a future path for Module 2 evidence enrichment such as `trace_hits`, `bbox`, `artifact_url`, and document-grounded detail panels.

## Non-Goals

- Do not make Module 4 depend on Module 2 structured extraction completion before graph ingestion starts.
- Do not require GraphRAG to accept raw PDFs, Office files, or images directly as final input. All supported formats must end as `.txt`.
- Do not reproduce Neo4j Browser pixel-for-pixel. The requirement is to match its graph browsing quality and interaction model while preserving project-specific document workflows.
- Do not make image OCR the mandatory first-phase input path for Module 4.
- Do not redesign unrelated modules or global product navigation outside the Module 4 workbench context.

## Current Problems

### Backend

- Module 4 already supports `uploads`, workspace generation, text normalization, GraphRAG execution, and Neo4j import, but the ingest semantics are still mixed with Module 2 `documents`.
- Module 2 currently auto-syncs structured `documents` to Module 4. This conflicts with the new GraphRAG-first definition.
- The current upload normalization logic falls back to writing JSON metadata text when file content cannot be read. That produces placeholder graph inputs instead of real document text.
- The idempotency key logic is still aligned with `documents`, not upload file references.
- Workspace lifecycle status exists conceptually, but stage-level tracking is not yet productized through the storage schema.

### Frontend

- `frontend/components/KnowledgeNexus.tsx` currently mixes data loading, fallback logic, layout, graph rendering, detail panel rendering, and styling in one large component.
- The graph uses a pure force layout and can re-render or re-fit too aggressively, causing unstable visual behavior.
- The page looks like a demo graph panel rather than a graph workbench.
- The frontend still contains a fallback sync path that pushes `documents` after extraction, which will conflict with backend upload-first sync.
- The graph interaction model is weaker than Neo4j Browser in three areas:
  - layout stability
  - visual clarity
  - graph exploration ergonomics

## Primary Decision

The approved primary sync timing is:

`sync to module 4 immediately after uploaded file artifacts are persisted successfully`

This means Module 4 graph jobs should start from file references, not from completed Module 2 extraction results.

## Target Architecture

### Module 2 Responsibilities

- Accept user uploads.
- Persist original files to artifact storage.
- Produce per-file metadata:
  - `file_name`
  - `file_hash`
  - `artifact_path`
  - `artifact_url`
  - `mime_type`
- Immediately create one upload batch sync request to Module 4 after artifact persistence succeeds.
- Continue running its own extraction pipeline for Module 2 features.
- Later provide evidence enhancement data to Module 4 detail panels and alert explanations.

### Module 4 Responsibilities

- Accept upload reference batches through `/module4/sync/uploads`.
- Create an isolated GraphRAG workspace per sync job.
- Normalize every supported input file to `workspace/input/*.txt`.
- Generate workspace-local `settings.yaml`, `.env`, prompts, and output directories.
- Run GraphRAG indexing against the normalized text corpus.
- Import GraphRAG artifacts into Neo4j.
- Serve graph data, neighborhoods, node detail, alerts, and evidence to the frontend.
- Render the graph in a frontend workbench that matches Neo4j-style graph browsing quality.

### Frontend Responsibilities

- Use Module 4 JSON APIs only.
- Render the graph workbench using project-controlled UI components.
- Do not embed Neo4j Browser.
- Support search, filter, focus, neighborhood exploration, and inspector panels.

## Implementation Units And Interfaces

This work should be implemented as a set of focused units with clear ownership.

### Module 2 Upload Sync Client

Purpose:
Send upload-reference batches to Module 4 immediately after artifact persistence.

Consumes:

- uploaded file metadata
- tenant information
- module 4 sync configuration

Produces:

- one asynchronous sync request per uploaded batch

Does not own:

- GraphRAG workspace creation
- text normalization
- graph rendering

### Module 4 Upload Ingest Endpoint

Purpose:
Validate upload-reference batches, compute idempotency, create jobs and batch records, and schedule workspace processing.

Consumes:

- upload batch payloads

Produces:

- job record
- ingest batch record
- scheduled workspace pipeline

Does not own:

- file extraction logic in Module 2
- frontend rendering

### Module 4 Input Normalizer

Purpose:
Convert supported uploaded formats into valid `input/*.txt` files for GraphRAG.

Consumes:

- artifact or storage paths
- optional inline text content

Produces:

- normalized `.txt` files
- per-file normalization results

Does not own:

- GraphRAG execution
- Neo4j import

### Module 4 Workspace Runtime

Purpose:
Create and manage GraphRAG workspaces, settings, prompts, logs, and manifest files.

Consumes:

- normalized input results
- runtime configuration

Produces:

- complete workspace directory
- workspace manifest
- workspace execution logs

Does not own:

- upload storage
- frontend UI

### Module 4 GraphRAG Runner

Purpose:
Run GraphRAG indexing inside the prepared workspace and report stage results.

Consumes:

- workspace path
- GraphRAG runtime environment

Produces:

- GraphRAG output artifacts
- stage logs and status

Does not own:

- input normalization
- graph UI behavior

### Module 4 Neo4j Importer

Purpose:
Import GraphRAG artifacts into Neo4j and expose graph-ready data for query APIs.

Consumes:

- GraphRAG artifact directory
- tenant and workspace scope

Produces:

- Neo4j graph content
- import summary

Does not own:

- frontend-specific layout state

### Module 4 Graph Query Layer

Purpose:
Serve graph, neighborhood, node detail, and later evidence-enhanced inspector payloads.

Consumes:

- Neo4j graph data
- optional storage-backed detail data

Produces:

- frontend-ready JSON payloads

Does not own:

- graph layout calculations in the client

### Module 4 Frontend Workbench Shell

Purpose:
Compose the graph workbench regions, manage user state, and coordinate graph and inspector interactions.

Consumes:

- Module 4 JSON APIs

Produces:

- graph workbench UI

Does not own:

- backend graph generation
- original file normalization

### Frontend Graph Renderer

Purpose:
Render the graph canvas with stable layout, focus, and exploration behavior.

Consumes:

- graph JSON
- local layout state

Produces:

- graph interaction experience

Does not own:

- graph data source decisions
- backend query semantics

## Data Flow

### Upload To Graph Flow

1. The user uploads files through Module 2.
2. Module 2 writes each original file into shared artifact storage.
3. Module 2 builds a single upload batch payload for Module 4.
4. Module 2 asynchronously calls `POST /module4/sync/uploads`.
5. Module 4 creates a workspace for the batch.
6. Module 4 converts each supported source file into one `.txt` input file.
7. Module 4 runs `python -m graphrag.index --root <workspace>`.
8. Module 4 imports the latest GraphRAG artifacts into Neo4j.
9. The frontend loads graph JSON from Module 4 and renders the workbench.

### Evidence Enhancement Flow

This is not part of the first-phase primary graph path.
It is a later enhancement path:

1. Module 2 finishes extraction and trace building.
2. Module 2 evidence metadata is linked to Module 4 node detail, alerts, and evidence cards.
3. The graph remains GraphRAG-first, but the inspector becomes document-grounded.

## Canonical Input Contract

The canonical sync payload to Module 4 becomes upload-reference based.

Required per file:

- `file_name`
- `file_hash`
- `artifact_path`

Recommended per file:

- `artifact_url`
- `mime_type`
- `storage_path` when different from `artifact_path`

Optional:

- `text_content` for direct text submissions
- `metadata`

The batch payload must include:

- `tenant_id`
- `source`
- `source_batch_key`
- `uploads`
- `graph_mode`

The primary graph path should treat `documents` as optional compatibility input only.

## Workspace Design

### Workspace Identity

The storage schema can keep a generated `workspace_id`, but directory structure should evolve toward:

`backend/module4/workspaces/{tenant_id}/{batch_id}/{workspace_id}/`

This preserves:

- tenant isolation
- batch-level reproducibility
- workspace uniqueness per run

### Workspace Contents

Each workspace contains:

- `input/`
- `cache/`
- `output/`
- `prompts/`
- `settings.yaml`
- `.env`
- `workspace_manifest.json`
- `graphrag-index.log`

### Manifest Requirements

For each file, the manifest must record:

- `file_name`
- `file_hash`
- `source_kind`
- `original_path`
- `artifact_path`
- `artifact_url`
- `input_txt`
- `text_length`
- `normalization_status`
- `error`

This information is necessary for debugging and user-facing status inspection.

## File Normalization Rules

Module 4 internal GraphRAG input must be `.txt` only.

### Supported In Phase 1

- `.txt`
- `.md`
- `.pdf`
- `.docx`
- `.xlsx`
- `.xlsm`

### Explicitly Conditional In Phase 1

- `.doc`
- `.xls`

These formats must not silently degrade to metadata-only pseudo-text.
They require either:

- a real conversion step
- or an explicit per-file failure status

### Normalization Behavior

- `.txt` and `.md`
  - read content directly
- `.pdf`
  - extract page text
  - write one normalized `.txt`
- `.docx`
  - preserve reading order across title, paragraph, and table content
  - write one normalized `.txt`
- `.xlsx` and `.xlsm`
  - serialize sheet names, headers, and rows into structured text
  - write one normalized `.txt`
- `.doc` and `.xls`
  - only proceed if a real conversion path is available
  - otherwise mark the file as failed

### Failure Rules

- empty normalized text is a normalization failure
- unsupported formats are explicit failures
- unreadable files are explicit failures
- no normalized files in the batch means the whole job fails
- partial normalization success is allowed if at least one valid `.txt` input is produced

## Job Model

### Top-Level Job Status

Top-level status remains:

- `queued`
- `running`
- `success`
- `failed`
- `cancelled`

### Stage-Level Status

Stage details must be persisted in job result and workspace run records:

- `queued`
- `preparing_workspace`
- `normalizing_inputs`
- `indexing_graphrag`
- `importing_neo4j`
- `ready`
- `failed`

### Partial Success

A batch can complete with partial success if:

- at least one file becomes valid GraphRAG text input
- GraphRAG indexing and Neo4j import succeed for the surviving set

The result payload must include:

- `normalized_files`
- `failed_files`
- `skip_reasons`
- `partial`

## Idempotency

Module 4 batch deduplication must be computed from upload references, not documents.

Recommended stable key input:

- `tenant_id`
- `source`
- ordered list of:
  - `file_hash`
  - `artifact_path`
  - `file_name`

This prevents duplicate graph jobs for the same uploaded batch.

## API Semantics

### Primary APIs

- `POST /module4/sync/uploads`
  - primary upload-reference ingestion endpoint
- `GET /module4/jobs/{job_id}`
  - query job progress and stage details
- `GET /module4/graph`
  - graph JSON for the workbench
- `GET /module4/graph/neighborhood/{node_id}`
  - local graph expansion endpoint
- `GET /module4/node/{node_id}`
  - inspector data endpoint
- `POST /module4/rebuild`
  - rerun graph generation from stored batch payloads

### Compatibility APIs

- `POST /module4/ingest`
  - keep as compatibility alias temporarily
  - should delegate to the same upload-first logic
  - should no longer imply that structured documents are the primary graph source

## Module 2 Sync Changes

### New Sync Trigger

Module 2 must trigger Module 4 sync after file artifacts are persisted successfully.

This replaces the current behavior where Module 4 sync is tied to structured extraction output.

### New Sync Payload

Module 2 should send one batch payload containing:

- `tenant_id`
- `source`
- `source_batch_key`
- `uploads`

The payload should not depend on extraction completion.

### Retry Model

Module 2 keeps asynchronous retry and exponential backoff.
Upload success must not be blocked by Module 4 temporary failure.

## Frontend Workbench Design

### Product Goal

The Module 4 frontend should feel like a Neo4j-style graph workbench:

- stable layout
- strong graph readability
- easy graph exploration
- professional inspector panels

It should also be better suited than Neo4j Browser for document-centric graph use cases.

### Layout Structure

The frontend should use a five-zone workbench:

- top toolbar
- left control rail
- center graph canvas
- right inspector
- bottom status strip

### Top Toolbar

Contains:

- node search
- layout switcher
- reset view
- refresh graph
- workspace indicator
- data source indicator
- current job or indexing status

### Left Control Rail

Contains:

- node type filters
- relation type filters
- document source filters
- community filters
- graph statistics
- legend
- alert summary

### Center Graph Canvas

Contains:

- primary graph renderer
- minimap
- zoom controls
- focus and neighborhood actions
- fit-to-view action
- layout lock or unlock controls

### Right Inspector

Contains:

- selected node metadata
- related relationships
- related documents
- community summary
- evidence cards
- later Module 2 evidence enhancements

### Bottom Status Strip

Contains:

- graph source
- workspace id
- last refresh time
- indexing state
- node and edge counts

## Frontend Rendering Strategy

### Current Problem

The current graph is driven by pure force layout with repeated render and fit behaviors.
This causes instability and breaks the Neo4j-style browsing goal.

### Required Rendering Strategy

Use a mixed strategy:

1. deterministic initial placement by graph role or node type
2. constrained force refinement after initial placement
3. no full re-layout on every selection, filter, or inspector change
4. optional coordinate caching keyed by `workspace_id + node_id`

### Fit Behavior

- auto-fit only on initial load or explicit user action
- never auto-fit after every render cycle

### Exploration Behavior

- click selects and highlights neighborhood
- explicit user action expands neighborhood
- selection changes update styles, not full graph re-layout

### Node Sizing

Node size should be driven by graph semantics such as type, degree, or importance.
It should not depend mainly on field confidence.

### Renderer

The rendering choice should favor graph stability and scalability over the current demo-style setup.
The implementation may continue with G6, but the design assumes:

- stable camera behavior
- scalable rendering path
- explicit hover, select, and neighborhood styling

## Frontend Visual Direction

### Design Intent

The Module 4 workbench should not look like a generic admin dashboard.
It should look like a serious graph analysis environment.

### Visual Principles

- clear panel hierarchy
- dense but readable information
- strong type color semantics
- professional edge and label treatment
- obvious focus and selection states

### Neo4j-Style Targets

The frontend should match Neo4j-style quality in:

- layout stability
- graph interaction
- type grouping clarity
- graph focus behavior
- inspector usability

It does not need to replicate Neo4j Browser branding or exact chrome.

## Compatibility Strategy

### Module 4 Compatibility

- keep `documents` support for a transition period
- treat `documents` as compatibility input or evidence augmentation input
- do not let `documents` remain the primary graph source

### Frontend Compatibility

The existing frontend fallback that pushes `documents` after extraction must be disabled or restricted to development-only use.
If retained for debugging, it must use the same upload-first batch semantics and idempotency key rules.

## Testing Strategy

### Module 2 Tests

- upload artifact persistence triggers upload batch sync
- sync payload contains upload references, not only documents
- retry behavior does not break upload success
- idempotency key generation is stable for repeated uploads

### Module 4 Tests

- uploads-only ingestion creates workspace and `.txt` inputs
- unsupported or unreadable files fail explicitly
- empty normalized text fails explicitly
- partial success returns correct normalized and failed counts
- no valid normalized file causes job failure
- rebuild uses stored upload payloads correctly
- graph import works for GraphRAG artifacts

### Frontend Tests

- graph page renders stable workbench regions
- filter and selection do not force full graph reset
- search focuses the correct node
- neighborhood expansion updates graph predictably
- inspector shows node and related context correctly

## Rollout Plan

### Phase 1

- move Module 2 sync trigger to post-artifact-persistence
- make Module 4 upload-first
- normalize supported formats into `.txt`
- run GraphRAG and Neo4j import
- disable frontend document-based fallback sync

### Phase 2

- rebuild frontend into the graph workbench
- introduce stable layout controls and inspector improvements
- add graph source, workspace, and indexing state visibility

### Phase 3

- merge Module 2 evidence into Module 4 detail experience
- add evidence cards, source anchors, and document-grounded explanations

## Risks

- `.doc` and `.xls` may not have a reliable conversion path in the current environment. They must be handled explicitly, not silently downgraded.
- Graph layout stability depends on not triggering full re-render behavior from ordinary UI state changes.
- Duplicate sync jobs can occur if frontend fallback and backend upload sync both remain active.
- Workspace lifecycle data will remain opaque if `workspaces` and `workspace_runs` are not wired into storage operations.

## Acceptance Criteria

- Uploading a supported file in Module 2 triggers Module 4 sync immediately after artifact persistence.
- Module 4 creates real `input/*.txt` files for supported inputs before GraphRAG indexing starts.
- The primary Module 4 graph path works without waiting for Module 2 structured extraction completion.
- Unsupported or unreadable files return explicit failure details.
- A batch with zero valid normalized text inputs fails clearly.
- A partially valid batch completes with visible partial status and per-file detail.
- Repeated sync for the same batch is idempotent.
- The frontend presents a stable graph workbench with Neo4j-style browsing quality.
- Graph selection, filtering, and neighborhood exploration do not trigger uncontrolled layout resets.
- Existing frontend graph JSON contract remains usable without embedding external graph pages.
