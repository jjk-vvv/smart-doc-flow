# Single-File Graph Isolation Design

Date: 2026-03-16

## Summary

This design defines the next stable architecture for the knowledge graph system:

`upload file -> persist file as a first-class record -> extract document facts -> enqueue file-level graph sync -> create one GraphRAG workspace per file -> import one graph per file -> render a file-scoped graph workbench`

The highest-priority requirement is now explicit:

- each uploaded file must produce one isolated graph
- graphs from different files must not be merged by default
- Module 4 should follow the current Module 2 document by default, but still allow manual switching to another file graph

This design also introduces two structural constraints that must be respected in the implementation:

- database table names must be business-oriented and must not include `module` prefixes
- the rule system must be split into extraction rules, graph-building rules, and alerting rules rather than forcing all logic into one generic rule table

## Why This Spec Exists

Earlier design work aligned Module 4 with a GraphRAG-first direction, but the current system still has three blocking problems:

- the graph view is still effectively tenant-scoped rather than file-scoped
- graph generation and querying are not modeled around a first-class file graph record
- the existing rule model is centered on alerting and is too narrow to manage prompt assets and graph construction policy cleanly

As long as those conditions remain true, frontend fixes such as drag polish, layout tuning, and performance work will continue to sit on top of the wrong data boundary.

This spec re-centers the system around a strict file graph model and makes the database, API, worker, and frontend design consistent with that decision.

## Goals

- Make each uploaded file produce one isolated graph with no default cross-file mixing.
- Make Module 2 the file fact source of truth for the whole pipeline.
- Make Module 4 a file-graph production system, not a tenant-global graph slicer.
- Ensure graph queries are file-scoped before they are node-type or relation-type scoped.
- Support two frontend graph entry modes:
  - follow the current Module 2 active document
  - manually switch to another file graph inside the Module 4 page
- Keep upload-to-graph sync immediate after file persistence.
- Replace implementation-oriented table naming with business-oriented naming.
- Split the rule system into distinct families for extraction, graph building, and alerting.

## Non-Goals

- Do not make multi-file merged graphs the default user experience.
- Do not keep using tenant-global `/graph` queries as the primary frontend path.
- Do not use one generic rules table as the only long-term configuration system.
- Do not make frontend filtering the main way to enforce graph isolation.
- Do not prioritize drag polish ahead of file-graph correctness.

## Approved Product Decisions

The following product decisions are already approved and are treated as fixed inputs for implementation:

- strict single-file graph isolation has higher priority than drag feel or performance polish
- Module 4 should follow the current Module 2 active document by default
- Module 4 should also let the user manually switch to another file graph
- when multiple files are uploaded, each file should immediately create its own graph task
- file graph creation can run in parallel or in queue, but each file remains independent
- database tables should use business names and should not include `module` prefixes

## Current State Findings

### 1. The graph query boundary is wrong

The current Module 4 graph endpoints still operate like tenant-level graph queries with optional display filters.
That means the frontend can only receive a slice of a larger mixed graph rather than a truly isolated file graph.

### 2. The GraphRAG workspace boundary is still batch-oriented

The current upload ingestion flow prepares one workspace from a list of uploads.
That is acceptable for workspace preparation, but it is not compatible with strict single-file graph isolation because semantic extraction and relationship construction can cross file boundaries before the frontend ever queries the graph.

### 3. Module 2 storage is still too cache-oriented

Module 2 currently stores extraction results and staging data well enough for extraction and assistant use, but it does not yet expose a fully modeled file fact layer and sync outbox that can reliably drive a downstream graph system per file.

### 4. The existing rule system is alert-centric

The existing Module 4 rules capability is useful for deterministic alert generation, but it is not the right structure for:

- prompt asset management
- graph naming policy
- entity and relationship normalization policy
- chunking policy
- domain routing for graph construction

## Architecture Overview

The target architecture consists of six business domains:

- file domain
- extraction domain
- graph domain
- evidence domain
- job domain
- rule domain

Each domain has explicit storage responsibilities and clear ownership boundaries.

### File Domain

The file domain owns the canonical identity of every uploaded file.

All downstream systems should anchor to:

- `file_id`
- `file_hash`

instead of relying on transient frontend state or mixed batch payloads.

### Extraction Domain

The extraction domain owns file-level extraction tasks and structured extraction results.
It is not responsible for graph generation, but it provides the stable source records and later evidence enrichments needed by the graph system.

### Graph Domain

The graph domain owns one graph per file, graph versioning, graph nodes, graph edges, and graph import lineage.

### Evidence Domain

The evidence domain owns snippets, bounding boxes, page references, and traceable links between graph objects and document artifacts.

### Job Domain

The job domain owns durable async execution records and sync delivery records across extraction and graph workflows.

### Rule Domain

The rule domain owns extraction policy, graph-building policy, prompt asset profiles, and alerting policy as separate rule families.

## Database Design

Table names below are intentionally business-oriented and avoid `module` prefixes.

### File Domain Tables

#### `upload_file`

Purpose:
Store the canonical file record for each uploaded document.

Key fields:

- `id`
- `tenant_id`
- `file_hash`
- `file_name`
- `mime_type`
- `file_size`
- `storage_path`
- `artifact_path`
- `artifact_url`
- `source`
- `status`
- `created_at`
- `updated_at`

Constraints:

- unique `(tenant_id, file_hash)`

#### `file_version`

Purpose:
Optional future table for file re-upload or version evolution.

This can be deferred if versioning is not needed immediately, but the storage model should leave room for it.

### Extraction Domain Tables

#### `extract_job`

Purpose:
Track extraction task runs.

Key fields:

- `id`
- `tenant_id`
- `job_type`
- `status`
- `progress`
- `schema_profile_id`
- `schema_hash`
- `schema_payload`
- `started_at`
- `finished_at`
- `error_message`
- `created_at`
- `updated_at`

#### `extract_job_file`

Purpose:
Bind extraction jobs to one or more files.

Key fields:

- `id`
- `job_id`
- `file_id`
- `file_hash`
- `file_order`
- `track`
- `status`
- `cache_key`
- `result_version`
- `created_at`
- `updated_at`

This table is required because one upload action can include many files, but graph work must later split into independent file graph tasks.

#### `extraction_result`

Purpose:
Store the durable extraction result record for one file and one schema context.

Key fields:

- `id`
- `tenant_id`
- `file_id`
- `file_hash`
- `schema_hash`
- `result_version`
- `summary_text`
- `quality_snapshot_json`
- `diagnostics_json`
- `extraction_json`
- `is_active`
- `created_at`
- `updated_at`

#### `extracted_field`

Purpose:
Persist important extracted field facts outside the raw JSON payload.

Key fields:

- `id`
- `result_id`
- `file_hash`
- `field_name`
- `field_type`
- `field_value_text`
- `field_value_json`
- `confidence`
- `source_ref_id`
- `page_no`
- `bbox_json`
- `created_at`

#### `extracted_table_cell`

Purpose:
Persist structured table cell output for downstream use and audit.

Key fields:

- `id`
- `result_id`
- `file_hash`
- `table_id`
- `page_no`
- `row_idx`
- `col_idx`
- `cell_text`
- `cell_ref_id`
- `bbox_json`
- `created_at`

### Graph Domain Tables

#### `graph_file`

Purpose:
Store the canonical graph record for one uploaded file.

This is the core isolation table for the entire design.

Key fields:

- `id`
- `tenant_id`
- `file_id`
- `file_hash`
- `file_name`
- `workspace_id`
- `graph_mode`
- `status`
- `current_job_id`
- `active_version_id`
- `last_error`
- `node_count`
- `edge_count`
- `created_at`
- `updated_at`
- `last_indexed_at`

Constraints:

- unique `(tenant_id, file_hash)`

#### `graph_version`

Purpose:
Track versioned graph builds for one file.

Key fields:

- `id`
- `graph_file_id`
- `workspace_id`
- `job_id`
- `version_no`
- `status`
- `normalized_txt_path`
- `settings_path`
- `prompt_profile_id`
- `artifact_dir`
- `report_dir`
- `manifest_path`
- `index_status`
- `index_error`
- `import_summary_json`
- `created_at`
- `updated_at`

#### `graph_node`

Purpose:
Store nodes belonging to one file graph version.

Key fields:

- `id`
- `tenant_id`
- `graph_file_id`
- `graph_version_id`
- `file_hash`
- `node_type`
- `canonical_key`
- `display_name`
- `attrs_json`
- `confidence`
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

Important requirement:

- node queries must always be able to bind back to `graph_file_id` or `file_hash`

#### `graph_edge`

Purpose:
Store edges belonging to one file graph version.

Key fields:

- `id`
- `tenant_id`
- `graph_file_id`
- `graph_version_id`
- `file_hash`
- `source_node_id`
- `target_node_id`
- `relation_type`
- `direction`
- `attrs_json`
- `confidence`
- `risk_score`
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

### Evidence Domain Tables

#### `evidence_item`

Purpose:
Store document-grounded evidence records.

Key fields:

- `id`
- `tenant_id`
- `file_id`
- `file_hash`
- `doc_ref_id`
- `object_type`
- `object_id`
- `page_no`
- `snippet`
- `locator_json`
- `bbox_json`
- `artifact_path`
- `artifact_url`
- `confidence`
- `created_at`

#### `edge_evidence`

Purpose:
Link graph edges to evidence items.

Key fields:

- `id`
- `edge_id`
- `evidence_id`
- `created_at`

#### `node_evidence`

Purpose:
Optional node-level evidence linking for later phases.

### Job Domain Tables

#### `job_run`

Purpose:
Track durable async jobs across extraction and graph workflows.

Key fields:

- `id`
- `tenant_id`
- `job_type`
- `status`
- `progress`
- `payload_json`
- `result_json`
- `error_message`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

#### `sync_outbox`

Purpose:
Durably store pending sync events from file persistence to downstream graph processing.

Key fields:

- `id`
- `tenant_id`
- `file_id`
- `file_hash`
- `target_system`
- `event_type`
- `payload_json`
- `status`
- `attempt_count`
- `last_error`
- `next_retry_at`
- `created_at`
- `updated_at`

This table is strongly recommended because immediate sync should be reliable, not fire-and-forget.

### Rule Domain Tables

#### `rule_profile`

Purpose:
Store rule definitions across multiple rule families.

Key fields:

- `id`
- `rule_family`
- `name`
- `description`
- `version`
- `enabled`
- `scope`
- `config_json`
- `created_at`
- `updated_at`

Required rule families:

- `extraction`
- `graph_build`
- `alerting`

#### `prompt_profile`

Purpose:
Store prompt bundle configuration for graph construction.

Key fields:

- `id`
- `name`
- `domain`
- `entity_types_json`
- `chunk_config_json`
- `prompt_bundle_json`
- `enabled`
- `version`
- `created_at`
- `updated_at`

#### `prompt_asset`

Purpose:
Store versioned prompt assets or prompt references.

Key fields:

- `id`
- `asset_key`
- `name`
- `asset_type`
- `file_path`
- `content_hash`
- `content_text`
- `language`
- `version`
- `created_at`
- `updated_at`

#### `rule_binding`

Purpose:
Bind rule profiles to tenants, file types, graph builds, or other targets.

Key fields:

- `id`
- `rule_profile_id`
- `target_type`
- `target_id`
- `priority`
- `enabled`
- `created_at`

## Rule System Design

The rule system should no longer be treated as one generic `expr` evaluation layer.
It should be modeled as three independent but related families.

### 1. Extraction Rules

Purpose:
Control how Module 2 plans and validates extraction.

Representative rule types:

- schema profile selection
- field normalization policy
- table hint policy
- OCR or vision hint policy
- extraction quality gates
- domain inference policy

### 2. Graph-Building Rules

Purpose:
Control how the graph is constructed from normalized text.

Representative rule types:

- prompt profile routing
- chunk policy
- entity naming policy
- relationship pruning policy
- community summarization policy
- graph label normalization policy

This family is the correct home for prompt asset management and GraphRAG behavior control.

### 3. Alerting Rules

Purpose:
Control post-graph risk detection and alert generation.

Representative rule types:

- threshold rules
- coverage rules
- consistency rules
- anomaly rules

The existing deterministic alert rule flow can remain as the seed of this family, but it should no longer be expected to carry graph construction policy.

## End-To-End File Graph Flow

The target data flow is:

1. User uploads one or more files in Module 2.
2. Each file is persisted as an `upload_file` record.
3. Module 2 creates extraction task records and extraction result records as usual.
4. For each persisted file, Module 2 writes one `sync_outbox` event for graph sync.
5. A worker or background runner submits one file-level graph job.
6. Module 4 creates one GraphRAG workspace per file.
7. The file is normalized into one or more GraphRAG-compatible text inputs for that file workspace.
8. GraphRAG indexing runs for that file only.
9. Artifacts are imported into `graph_file`, `graph_version`, `graph_node`, and `graph_edge`.
10. The frontend loads the graph by `file_hash` or `graph_file_id`, never by tenant-wide default.

## API Design

The graph API should shift from tenant-global graph queries to file-scoped graph queries.

### Required File Graph APIs

- `POST /graph/sync/uploads`
  - accepts one file sync request at a time
  - returns the file graph job record

- `GET /graph/files`
  - returns the file graph registry list for the current tenant

- `GET /graph/files/{file_hash}`
  - returns status and summary for one file graph

- `GET /graph/files/{file_hash}/view`
  - returns the main graph for one file

- `GET /graph/files/{file_hash}/neighborhood/{node_id}`
  - expands graph context for one node, still bound to the same file graph

- `POST /graph/files/{file_hash}/rebuild`
  - rebuilds one file graph only

### Transitional Compatibility

The old tenant-global graph endpoints can remain during migration, but they should be downgraded to compatibility paths.
The frontend should stop using them as the primary source once the file graph APIs exist.

## Query Model

The query precedence must become:

1. resolve `graph_file_id` or `file_hash`
2. locate the graph version boundary
3. select nodes and edges within that file graph only
4. apply node type and relation type filters
5. apply result limits

The query precedence must not remain:

1. load tenant-global nodes
2. load tenant-global edges
3. hope frontend filtering makes the graph feel file-scoped

## Frontend Interaction Design

The Module 4 page should become a file graph workbench, not a global graph demo.

### Core Context Model

The frontend should maintain a `CurrentGraphContext` with:

- `tenant_id`
- `file_hash`
- `graph_file_id`
- `workspace_id`
- `job_status`
- `source_mode`

Where `source_mode` is one of:

- `follow-active-doc`
- `manual-select`

### Required Behavior

- when the active document changes in Module 2, the graph follows automatically if the current source mode is `follow-active-doc`
- when the user manually picks another file graph inside Module 4, the source mode becomes `manual-select`
- the user can always click back into `follow-active-doc`
- if the chosen file graph is not ready yet, the page shows file-level graph job status instead of falling back to a tenant-global graph

### Workbench Regions

Recommended page structure:

- top context bar
- left file graph navigator
- center graph canvas
- floating node detail inspector
- bottom status line

### Top Context Bar

Should show:

- current file name
- file hash short code
- graph status
- workspace status
- current mode
- rebuild action
- return-to-follow action

### Left File Graph Navigator

Should show:

- all file graphs available for the current tenant
- status per file
- last indexed time
- node count
- edge count
- active state

This is the manual file graph switching surface.

## Performance And Interaction Priorities

Performance and drag polish are not first-order milestones until file graph isolation is correct.
After file graph isolation is in place, the next priorities become:

- remove drag-end auto pinning
- keep drag and click as separate interactions
- reduce initial graph load size per file
- use lazy neighborhood expansion
- avoid full simulation rebuilds for simple UI state changes

These improvements are intentionally sequenced after the data boundary is fixed.

## Error Handling And Recovery

The file graph workflow should be treated as a durable pipeline with explicit recovery points.

### Recovery points

- file persisted but sync event not delivered
- sync event delivered but no file graph job created
- file graph job created but workspace preparation failed
- workspace prepared but GraphRAG indexing failed
- indexing succeeded but graph import failed
- graph import succeeded but `graph_file.active_version_id` was not advanced

### Required recovery behavior

- `sync_outbox` retries with bounded backoff and idempotent delivery
- `job_run` stores stage-level progress and terminal failure reasons
- `graph_file.last_error` and `graph_version.index_error` retain actionable failure detail
- file graph rebuild retries only the selected file, never unrelated files
- the frontend never silently falls back to another file graph when the requested graph fails

### User-visible status expectations

The frontend should expose file-level graph states such as:

- `queued`
- `preparing`
- `indexing`
- `importing`
- `ready`
- `failed`

This prevents the UI from hiding failure behind empty canvases or unrelated data.

## Testing Strategy

This design requires tests at the schema, workflow, query, and frontend context levels.

### Data model tests

- `upload_file` uniqueness by tenant and `file_hash`
- `graph_file` uniqueness by tenant and `file_hash`
- `graph_node` and `graph_edge` always bind to one `graph_file_id`
- `rule_profile.rule_family` validation for `extraction`, `graph_build`, and `alerting`

### Workflow tests

- file persistence creates one `sync_outbox` record per file
- repeated sync delivery remains idempotent
- one upload with three files creates three independent file graph jobs
- one failed file graph does not block another file graph in the same upload batch
- rebuilding one file graph does not rebuild unrelated files

### Query tests

- file graph queries return only nodes and edges for the requested file
- neighborhood expansion cannot escape the current file graph boundary
- compatibility endpoints do not become the primary frontend path again

### Frontend context tests

- follow-current-document mode updates the graph when Module 2 `activeDoc` changes
- manual selection mode pins the chosen file graph until the user returns to follow mode
- non-ready file graphs show stage-aware status instead of loading a tenant-global graph

## Migration Notes

The move to file-scoped graphs should be staged rather than implemented as one destructive cutover.

### Recommended migration path

1. Add the new business-oriented tables in parallel with current storage tables.
2. Continue writing current cache and staging data during transition.
3. Start writing `upload_file`, `graph_file`, `graph_version`, and `sync_outbox` without changing the frontend entry path yet.
4. Cut graph job creation over to per-file sync.
5. Switch the frontend to file-scoped graph APIs.
6. Deprioritize tenant-global graph endpoints to compatibility mode only.

### Expected backfill work

- synthesize `upload_file` records for existing persisted files when possible
- map existing graph artifacts or imports into `graph_file` and `graph_version`
- migrate existing alert rules into `rule_profile` with `rule_family = alerting`

## Milestones

### Milestone 1: Business Data Model Foundation

Deliver:

- `upload_file`
- `extract_job`
- `extract_job_file`
- `extraction_result`
- `graph_file`
- `graph_version`
- `graph_node`
- `graph_edge`
- `evidence_item`
- `job_run`
- `sync_outbox`
- `rule_profile`
- `prompt_profile`
- `prompt_asset`

Exit criteria:

- the database can model one file graph per file without tenant-global ambiguity
- rule families are represented explicitly

### Milestone 2: Module 2 File Fact Source

Deliver:

- file persistence records
- extraction records tied to files
- sync outbox emission after file persistence

Exit criteria:

- every uploaded file has a durable file record
- graph sync no longer depends on transient frontend-only state

### Milestone 3: File-Level Graph Production

Deliver:

- one graph workspace per file
- one graph job per file
- one imported graph per file

Exit criteria:

- multi-file uploads produce multiple independent graph tasks
- different files no longer share default graph context

### Milestone 4: File-Scoped Graph APIs

Deliver:

- file graph registry endpoint
- file graph summary endpoint
- file graph main view endpoint
- file graph neighborhood endpoint
- file graph rebuild endpoint

Exit criteria:

- frontend graph access always includes file context

### Milestone 5: Frontend File Graph Workbench

Deliver:

- follow-current-document mode
- manual file switch mode
- file graph navigator
- file graph state cards

Exit criteria:

- the page can follow Module 2 active document automatically
- the page can switch manually to another file graph
- the page never needs a tenant-global graph fallback for normal behavior

### Milestone 6: Interaction And Performance Refinement

Deliver:

- drag fix
- reduced first paint graph load
- lazy neighborhood fetch
- label density controls
- simulation stability improvements

Exit criteria:

- drag behavior feels consistent
- graph load is smoother
- node exploration is stable within a file graph

## Acceptance Criteria

The design should be considered implemented correctly only when all of the following are true:

- each uploaded file gets one independent graph task
- each uploaded file gets one independent graph record
- graph data can always be queried by `file_hash` or `graph_file_id`
- the default graph page follows the current Module 2 document
- the user can manually switch to another file graph
- a file graph never includes nodes or edges from another file unless the user explicitly enters a future cross-file mode
- table names are business-oriented and do not contain `module`
- rule families are split into extraction, graph building, and alerting rather than collapsed into one generic configuration surface

## Risks

### Risk 1: Migration complexity

Moving from cache-oriented storage and tenant-wide graph assumptions to file-graph storage introduces migration work.

Mitigation:

- keep transitional compatibility endpoints briefly
- migrate the frontend to file-scoped APIs only after the new graph registry is present

### Risk 2: Rule sprawl

Splitting the rule system into multiple families can create operational overhead if profiles are not governed well.

Mitigation:

- use `rule_profile` as a shared parent shape
- keep only three top-level families at first

### Risk 3: Duplicate sync events

Immediate file-level graph sync can produce duplicate jobs if file persistence and retry logic are not idempotent.

Mitigation:

- make `sync_outbox` durable
- dedupe on `tenant_id + file_hash + target_system + event_type`

## Final Recommendation

The correct next move is not another round of frontend-only graph tuning.
The correct next move is to turn the system into a real file graph platform:

- file records first
- one graph per file
- file-scoped graph APIs
- business-oriented table names
- layered rule families
- frontend follow mode plus manual file graph switching

Once that boundary is correct, drag polish, Neo4j-style feel, and performance work will become much easier and much more durable.
