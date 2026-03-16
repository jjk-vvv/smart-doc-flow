# Module 4 Production Closure Execution Plan Design

Date: 2026-03-16

## Summary

This spec converts the approved Module 4 direction into a concrete closure plan.
It builds on earlier Module 4 specs and narrows the focus to one question:

How do we move the current Module 4 state from "directionally correct but half-migrated"
to a stable, file-scoped, GraphRAG-first, Neo4j-aligned production path?

The approved target path remains:

`user uploads file once in Module 2 -> file persistence succeeds -> Module 4 sync starts immediately per file -> Module 4 normalizes the file into internal txt corpus -> GraphRAG indexing runs in a per-file workspace -> graph artifacts are imported into a real file-scoped graph plane -> frontend renders only that file graph by default`

This spec exists because the current blockers are no longer mainly environment setup problems.
As of 2026-03-16, the live Module 4 deep health check reports:

- Postgres reachable
- GraphRAG runtime ready
- prompt assets present
- OneAPI reachable
- Neo4j reachable

The remaining problems are structural:

- strict single-file graph isolation is not yet guaranteed at the storage level
- the running Module 4 instance is drifting from repo code
- Neo4j is configured but not yet the real graph query plane
- prompt and rule systems are still transitional
- the frontend still contains tenant-wide and local fallback paths

This design turns those problems into an execution plan with delivery gates.

## Relationship To Existing Specs

This spec is intentionally downstream of:

- `docs/superpowers/specs/2026-03-15-module4-graphrag-sync-frontend-design.md`
- `docs/superpowers/specs/2026-03-16-module4-graphrag-production-alignment-design.md`
- `docs/superpowers/specs/2026-03-16-single-file-graph-isolation-design.md`

Those documents established the main architecture direction.
This document does not replace them.
It serves as the closure-oriented execution plan that sequences the remaining work and defines what "done" means.

## Why This Spec Exists

Recent analysis across the current repo and running services found a consistent pattern:

### 1. Runtime is healthier than architecture

The live Module 4 service can pass a deep health probe, which means configuration work is no longer the primary bottleneck.
This changes the next-best action from "fill missing env vars" to "close architectural gaps."

### 2. The system is currently in a split-brain state

The repo contains file-scoped APIs such as:

- `/module4/graph/files`
- `/module4/graph/files/{file_hash}`
- `/module4/graph/files/{file_hash}/view`
- `/module4/graph/files/{file_hash}/neighborhood/{node_id}`

But the running `openapi.json` does not expose these routes yet.
That means the active runtime and the repo code are out of sync.

### 3. File isolation is still mostly logical, not physical

The system now has `graph_files` and `graph_versions`, but the actual graph payload tables are still global per tenant.
Nodes and edges are currently scoped mainly by `attrs.file_hash`, `attrs.workspace_id`, and `canonical_key` conventions.
That is a compatibility bridge, not a stable production boundary.

### 4. Frontend improvements are ahead of backend guarantees

The graph workbench now supports:

- following the current Module 2 document
- manual file switching
- Neo4j-inspired interaction patterns

But it still contains fallback paths for tenant graph and local extraction graph.
This means the UX can still silently show the wrong graph boundary.

### 5. Prompt and rule systems are operationally useful but not yet assets

Prompt files are now copied into workspaces successfully, and a basic prompt registry exists.
However, there is still no first-class model for:

- prompt profiles
- prompt versioning
- prompt snapshots per graph build
- domain routing
- rule family separation

As long as those pieces remain transitional, Module 4 cannot be treated as a durable production graph platform.

## Goals

- Enforce one file to one graph as a hard data boundary rather than a query-time convention.
- Make Module 2 upload persistence the only upstream source needed to trigger Module 4 graph production.
- Keep GraphRAG txt corpus input as the canonical internal input mode.
- Move Module 4 from a compatibility storage graph to a true file-scoped graph platform.
- Promote Neo4j into a formal graph query plane instead of keeping it as a configured side dependency.
- Convert prompt handling into managed prompt assets with profiles and reproducible snapshots.
- Split the current generic rule model into business-oriented rule families.
- Make the frontend default to the current document graph and never silently mix unrelated file graphs.
- Preserve a path for later Module 2 evidence enrichment without making Module 2 structured JSON the primary graph input.

## Non-Goals

- Do not revert Module 4 back to a Module 2 structured-JSON-first graph path.
- Do not make multi-file merged graphs the default user experience.
- Do not embed Neo4j Browser directly into the frontend.
- Do not make OCR the mandatory first-phase input path for all files.
- Do not optimize visual polish ahead of graph-boundary correctness.
- Do not treat tenant-global graph endpoints as the long-term primary contract.

## Approved Product Decisions

The following decisions are already approved and should be treated as fixed:

- Module 4 primary input model follows the `D:\ragtest` pattern internally: GraphRAG consumes text corpus files.
- Module 2 remains the upload owner; users should not upload the same file twice.
- Upload persistence success should trigger Module 4 sync immediately.
- Each file must create its own graph task after persistence.
- Module 4 should default to following the current Module 2 document.
- Module 4 should also allow manual switching to a different file graph.
- Database table naming should be business-oriented and should not keep expanding `module`-prefixed names as the long-term domain model.
- Prompt asset management and rule library design are first-class concerns, not cleanup work for later.

## Current State Findings

### Finding 1: Strict single-file isolation is not complete

Current state:

- `graph_files` and `graph_versions` exist
- `nodes` and `edges` remain tenant-global tables
- uniqueness rules still operate on tenant-wide keys
- file scoping is largely implemented through JSON attributes and conventions

Impact:

- cross-file collisions remain possible
- file isolation depends on careful querying instead of guaranteed data ownership
- later versioning and rebuild semantics are harder than they should be

### Finding 2: Runtime and repo drift is a P0 problem

Current state:

- file-scoped routes exist in code
- running OpenAPI does not expose them
- `GET /module4/graph/files` currently returns `404`

Impact:

- frontend cannot reliably enter strict file-graph mode
- debugging becomes misleading because repo state and runtime state are different
- backend and frontend work can appear broken even when one side is correct

### Finding 3: Neo4j is reachable but not yet decisive

Current state:

- Neo4j config is present
- connectivity probing is implemented
- workspace env rendering passes Neo4j settings through
- artifact import still primarily writes graph data into Module 4 storage tables

Impact:

- the platform is not yet operating on a true graph-native query plane
- frontend interaction cannot fully inherit Neo4j-style traversal semantics
- long-term graph querying remains tied to transitional storage logic

### Finding 4: Prompt management is still file-level, not asset-level

Current state:

- prompt assets exist on disk
- prompt registry resolves them
- workspaces materialize copies of those files

Missing:

- prompt asset versions
- prompt profiles
- domain routing
- prompt snapshots per graph build
- tenant/profile binding

Impact:

- prompt changes are harder to audit
- domain-specific optimization is harder to control
- graph build reproducibility is weaker than it should be

### Finding 5: Rule architecture is still too generic

Current state:

- a generic `rules` model exists
- `rule_kind` is still generic rather than domain-specific

Missing:

- extraction rules
- graph-building rules
- alerting rules
- runtime policy rules

Impact:

- unrelated concerns are forced into one abstraction
- operational governance is weak
- graph construction policy is harder to inspect and evolve

### Finding 6: Module 2 sync is immediate but not durable

Current state:

- per-file sync to Module 4 already exists
- sync currently uses in-process async tasks
- Module 2 storage health still shows degraded memory mode in live checks

Impact:

- process restarts can lose delivery intent
- upstream persistence is not yet strong enough to be treated as fully durable
- file graph production still lacks production-grade task recovery

### Finding 7: Graph quality can still degrade below `ragtest` output quality

Current state:

- importer supports a final artifact path and a partial fallback path
- indexer can retry without community reports if output JSON becomes unstable

Impact:

- the system can produce useful graphs, but not yet reliably `ragtest`-level final graphs every time
- graph output quality is still dependent on workflow fallback behavior

### Finding 8: Frontend still contains compatibility paths

Current state:

- file-graph flows exist
- tenant-storage and local fallback flows still remain
- node detail is still synthesized from neighborhood queries on the client

Impact:

- users may still see a graph that is not the current file graph
- frontend correctness depends on fallback order
- node detail interaction is less stable than a dedicated backend contract

### Finding 9: Operational discipline is insufficient for this migration stage

Current state:

- Module 4 is still optional in `dev-all`
- workspace retention and cleanup policy are not formalized

Impact:

- stale runtimes are easier to leave running
- workspace sprawl will grow over time
- build reproducibility and cleanup will get harder

## Architecture Principles

### 1. File graph correctness comes before graph beauty

No amount of frontend rendering polish can compensate for the wrong graph boundary.
The graph must be correct at the file level before it is optimized visually.

### 2. Control plane and graph plane should be separated

Postgres should own jobs, file metadata, build metadata, prompt bindings, rule bindings, and evidence references.
Neo4j should become the graph query plane for nodes and relationships.

### 3. Every file graph build must be reproducible

Each build should preserve:

- normalized txt input
- settings snapshot
- prompt snapshot
- index log
- artifact location
- import summary

### 4. Compatibility bridges should be temporary and explicit

Tenant-wide graph queries and local extraction fallback may remain during migration, but they must be treated as transitional diagnostics rather than the default user path.

### 5. Prompt and rule systems are platform assets

Prompt files and graph rules are not mere implementation details.
They are part of the product operating model and should be versioned, bound, and auditable.

## Target System Model

The target production model is split into six domains:

- file domain
- graph build domain
- graph query domain
- evidence domain
- prompt domain
- rule domain

### File Domain

Purpose:
Own the persisted identity of uploaded files and the normalized text asset lineage.

Core responsibilities:

- canonical file identity
- file storage reference
- file metadata
- normalized text asset reference
- sync outbox intent

### Graph Build Domain

Purpose:
Own per-file workspaces, GraphRAG execution, artifact lineage, and build status.

Core responsibilities:

- one graph build per file run
- build workspace lifecycle
- GraphRAG settings and prompt snapshotting
- import status
- build logs and summaries

### Graph Query Domain

Purpose:
Own graph nodes, edges, file graph views, and neighborhood traversal on the active file graph plane.

Core responsibilities:

- file-scoped graph querying
- node detail serving
- graph filtering within a file graph
- graph statistics and summaries

### Evidence Domain

Purpose:
Own links from graph objects back to document evidence and later Module 2 enhancements.

Core responsibilities:

- snippet storage
- page and bbox references
- artifact links
- graph-object-to-evidence joins

### Prompt Domain

Purpose:
Own prompt assets, profiles, routing, and reproducible prompt snapshots.

Core responsibilities:

- prompt asset storage
- profile management
- domain routing
- graph-build prompt snapshotting

### Rule Domain

Purpose:
Own graph production and alert policy without collapsing unrelated logic into one generic table.

Core responsibilities:

- extraction rules
- graph-building rules
- alert rules
- optional runtime policy rules

## Database Direction

The long-term database design should be business-oriented and avoid carrying `module` in business table names.
Migration can be staged, but the destination model should be explicit from the beginning.

### Recommended Core Tables

#### File and Sync

- `upload_file`
- `text_asset`
- `graph_sync_outbox`

#### Graph Build

- `graph_file`
- `graph_build`
- `graph_build_input`
- `graph_build_prompt_snapshot`
- `graph_build_log`

#### Graph Query Metadata

- `graph_node_ref`
- `graph_edge_ref`
- `graph_node_evidence`
- `graph_edge_evidence`

#### Prompt

- `prompt_asset`
- `prompt_profile`
- `prompt_binding`

#### Rules

- `extraction_rule`
- `graph_rule`
- `alert_rule`
- `runtime_rule` if needed

### Important Boundary Rule

The long-term model must not rely on:

- tenant-global node uniqueness alone
- file scoping hidden only in JSON attrs
- workspace scoping inferred at query time

Every node and edge that belongs to a file graph must be traceable to a specific graph build.

## Target Service Contracts

The following contracts define the stable service boundaries that implementation should converge toward.
Exact payload shapes can evolve during planning, but these responsibilities should not.

### Upload And Build Contracts

- `POST /module4/sync/uploads`
  - accepts file references created by Module 2 after persistence
  - creates or reuses a file graph record
  - creates a new graph build intent for the file

- `GET /module4/jobs/{job_id}`
  - returns job and build status across normalization, indexing, and import stages

### File Graph Contracts

- `GET /module4/graph/files`
  - lists available file graphs for the tenant
  - includes readiness state, file identity, active build identity, and counts

- `GET /module4/graph/files/{file_hash}`
  - returns metadata for one file graph

- `GET /module4/graph/files/{file_hash}/view`
  - returns the active graph view for that file only

- `GET /module4/graph/files/{file_hash}/neighborhood/{node_id}`
  - returns neighborhood expansion for the active file graph only

- `GET /module4/graph/files/{file_hash}/node/{node_id}`
  - returns stable node detail for the active file graph only
  - should replace client-only node detail synthesis

### Build Control Contracts

- `POST /module4/rebuild`
  - triggers rebuild for one or more file graphs under explicit scope

- `POST /module4/workspaces/{workspace_id}/refresh`
  - optional follow-up contract if incremental refresh is later supported

## Migration Strategy

The migration should be staged rather than destructive.

### Stage 1: Compatibility Coexistence

- keep current transitional `module4` schema operating
- introduce business-oriented tables or compatibility views alongside it
- backfill file/build lineage without breaking current endpoints

### Stage 2: Dual Read Or Switched Read

- route new file-scoped queries to the new build-aware storage path
- keep transitional tenant-global queries only for diagnostics and rollback

### Stage 3: Default Cutover

- make file-scoped contracts the default frontend path
- demote tenant-global and local fallback paths to explicit debug behavior

### Stage 4: Cleanup

- remove obsolete attr-only graph scoping where safe
- formalize retention and cleanup for old workspaces and old build records

## Workstream Plan

### Workstream A: Runtime Alignment And Deployment Discipline

Objective:
Make repo code and running Module 4 instance behave identically and fail loudly when they do not.

Tasks:

- Make Module 4 a required service in the local dev stack for this migration stage.
- Add runtime validation for file-scoped graph endpoints during startup or smoke checks.
- Add a release gate that checks:
  - `/module4/healthz?probe=deep`
  - `/openapi.json`
  - `/module4/graph/files`
- Document the authoritative Module 4 startup method and remove ambiguity around stale processes.

Deliverables:

- consistent local startup
- no silent route drift
- easier backend/frontend联调

Acceptance criteria:

- running OpenAPI includes file-scoped routes
- `GET /module4/graph/files` is available in the active runtime
- frontend no longer needs to guess whether file-graph APIs exist

### Workstream B: Hard Single-File Graph Isolation

Objective:
Convert file graph isolation from a soft query convention into a hard data boundary.

Tasks:

- Introduce a business-oriented graph build schema where every file graph has a first-class build record.
- Bind graph nodes and edges to a graph build identity rather than only tenant scope.
- Migrate existing file graph metadata out of transitional attr-based scoping into explicit ownership fields.
- Ensure rebuilds produce a new build version without overwriting unrelated file graph records.

Deliverables:

- real one-file-one-graph ownership model
- build-aware graph versioning
- no accidental cross-file merge by storage key

Acceptance criteria:

- two files with the same entity names do not merge by default
- one file rebuild produces a new build lineage without corrupting another file graph
- file graph queries can operate without JSON attr scoping tricks

### Workstream C: Durable Upload-To-Graph Delivery

Objective:
Keep immediate post-persistence sync while making the delivery model recoverable and durable.

Tasks:

- Add a durable outbox record when Module 2 file persistence succeeds.
- Move per-file graph sync intent from process memory into database-backed delivery state.
- Preserve immediate behavior while allowing retries, replay, and restart recovery.
- Track per-file graph job state through a formal status machine.

Recommended statuses:

- `queued`
- `preparing_input`
- `normalizing`
- `indexing`
- `importing_graph`
- `ready`
- `failed`

Deliverables:

- durable file graph sync intent
- restart-safe delivery
- per-file status reporting

Acceptance criteria:

- process restart does not lose already accepted graph sync work
- every persisted file can be traced to exactly one current graph build status
- failed files can be retried without reupload

### Workstream D: GraphRAG Workspace Hardening

Objective:
Make per-file GraphRAG workspaces reproducible, inspectable, and equivalent in structure to the proven `ragtest` path.

Tasks:

- Keep txt as the only canonical internal GraphRAG input format.
- Preserve per-file workspace structure:
  - `input`
  - `cache`
  - `output`
  - `prompts`
  - `settings.yaml`
- Save normalization metadata, file lineage, prompt lineage, and build lineage per workspace.
- Improve rejection and degradation handling for unsupported formats and low-quality extracted text.
- Extend format normalization roadmap for:
  - legacy Office conversion
  - OCR for scanned images and image-heavy PDFs

Deliverables:

- reproducible file workspaces
- better failure visibility
- clearer parity with `ragtest`

Acceptance criteria:

- each successful build has real txt corpus files
- each failed build records an explicit reason
- workspace contents are sufficient for replay and debugging

### Workstream E: Prompt Asset Management

Objective:
Turn prompt handling into a governed platform capability.

Tasks:

- Introduce prompt assets with version and hash identity.
- Introduce prompt profiles for broad document families.
- Bind files or tenants to prompt profiles through explicit rules.
- Snapshot actual prompt content used by each graph build.
- Evolve prompt strategy into:
  - universal extraction skeleton
  - domain-specific profile layer
  - optional example layer

Target initial profile families:

- general business documents
- policy and regulatory documents
- contracts and agreements
- research and reports
- finance and statements
- medical or domain-specialized documents

Deliverables:

- prompt asset versioning
- prompt profile routing
- reproducible prompt snapshots per build

Acceptance criteria:

- prompt changes are traceable
- graph builds can be replayed against a known prompt snapshot
- different document families can route to different prompt profiles without code edits

### Workstream F: Rule Library Redesign

Objective:
Replace the current generic rule model with domain-oriented rule families.

Tasks:

- Separate extraction rules from graph-building rules and alert rules.
- Define clear ownership boundaries for each rule family.
- Add versioning, enablement, and evaluation metadata per rule.
- Reserve runtime policy rules for workflow-specific operational behavior if needed.

Rule families:

- `extraction_rule`
- `graph_rule`
- `alert_rule`
- optional `runtime_rule`

Deliverables:

- clearer governance of graph production policy
- easier debugging of graph quality
- cleaner alignment with business terminology

Acceptance criteria:

- graph naming and dedup policy no longer have to hide inside a generic rule model
- alert logic can evolve without disturbing extraction logic
- rule tables and APIs are understandable by domain responsibility

### Workstream G: Neo4j Promotion To Primary Graph Plane

Objective:
Make Neo4j the real graph query layer rather than only a probed dependency.

Tasks:

- Build a formal Neo4j import service for file graph builds.
- Import graph data with file and build identity preserved.
- Build dedicated query services for:
  - file graph view
  - node neighborhood
  - node detail
  - graph statistics
- Keep Postgres as control plane, not the long-term primary graph query source.

Deliverables:

- Neo4j-backed file graph queries
- clear separation of graph plane and control plane
- lower dependency on transitional attr-based queries

Acceptance criteria:

- file graph query endpoints can be served from Neo4j-backed services
- graph build identity remains queryable
- frontend contracts can remain stable while storage shifts under the hood

### Workstream H: Frontend Strict File-Graph Mode And Neo4j-Style UX

Objective:
Make the frontend correct first, then polished.

Tasks:

- Remove tenant-wide graph as the default display path once file graph APIs are live.
- Keep local fallback only as an explicit diagnostic mode, not silent default behavior.
- Add a dedicated backend-driven node detail contract.
- Preserve two entry modes:
  - follow current Module 2 document
  - manual graph file selection
- Continue Neo4j-style UX work:
  - force-directed layout stability
  - draggable nodes
  - click-to-open node details
  - double-click neighborhood expansion
  - lighter initial payload and incremental graph growth

Deliverables:

- strict file graph correctness
- clearer node interaction
- cleaner graph detail behavior

Acceptance criteria:

- default frontend path shows only the current file graph
- manual switching can open another single-file graph
- node detail comes from a dedicated contract, not only client-side neighborhood synthesis
- no unrelated file graph is shown by default

### Workstream I: Quality, Regression, And Operations

Objective:
Make the whole path observable and stable enough for repeated validation.

Tasks:

- Create regression fixtures for:
  - plain text file
  - layout-heavy PDF
  - table-heavy spreadsheet
- Compare Module 4 output against `ragtest` on:
  - entity quality
  - relationship quality
  - community quality
  - build duration
  - failure modes
- Add workspace retention and cleanup policy.
- Add observability for:
  - current queued builds
  - latest final vs partial artifact mode
  - retry counts
  - outbox backlog

Deliverables:

- repeatable quality checks
- cleaner operations
- measurable production confidence

Acceptance criteria:

- one canonical sample set can be replayed repeatedly
- build quality regressions are visible
- workspace sprawl is controlled

## Sequencing

The implementation should proceed in this order:

### Phase P0: Correctness And Runtime Consistency

- Workstream A
- Workstream B
- Workstream C

Reason:
Without runtime consistency and hard file isolation, the rest of the work sits on the wrong boundary.

### Phase P1: Production Graph Backbone

- Workstream D
- Workstream E
- Workstream F
- Workstream G

Reason:
These workstreams make graph production reproducible, configurable, and graph-native.

### Phase P2: Product Experience And Long-Term Stability

- Workstream H
- Workstream I

Reason:
Frontend polish and operations are most effective once the graph backbone is stable.

## Planning Decomposition

This spec is intentionally a program-level closure plan rather than a single coding task.
Implementation planning should decompose it into three subplans:

- `P0 correctness and runtime consistency`
- `P1 graph backbone and governance`
- `P2 frontend strict mode and operational hardening`

Each subplan should be independently actionable, testable, and reviewable.
No single implementation batch is expected to complete the whole spec at once.

## Dependencies

### Critical Path Dependencies

- Workstream B depends on a chosen business-oriented table model.
- Workstream C depends on a durable upstream persistence event model in Module 2.
- Workstream G depends on file/build identity being stable first.
- Workstream H depends on runtime file APIs and stable file graph querying.

### Parallelizable Work

- Prompt asset management and rule redesign can begin while graph storage migration is underway.
- workspace hardening and regression fixture design can proceed in parallel once core file identity is stable.

## Error Handling And Failure Semantics

The target system must make failures explicit and classifiable.

At minimum, builds should be able to distinguish:

- input normalization failed
- GraphRAG runtime missing
- GraphRAG indexing failed
- artifact set incomplete
- graph import failed
- Neo4j query plane unavailable
- prompt snapshot missing
- runtime drift detected

Each failure should be reflected in:

- job state
- build state
- user-visible status where relevant
- logs sufficient for replay

## Testing Strategy

### Backend

- unit tests for input normalization and workspace manifest generation
- storage tests for file graph isolation
- import tests for final and partial artifact paths
- API tests for file graph routes and node detail contracts

### Integration

- Module 2 persisted upload triggers per-file graph sync
- successful graph build creates build lineage and queryable file graph
- rebuild creates a new build without corrupting existing file graphs

### Frontend

- default follows active file
- manual switching changes graph file correctly
- no tenant-wide fallback shown in normal mode
- node click opens correct detail for the current file graph

### Regression

- compare current output against known `ragtest` baseline samples
- compare final artifact mode vs partial fallback mode

## Risks

### Risk 1: Table migration complexity

Moving from transitional `module4` storage patterns to business-oriented graph build ownership will require careful migration and coexistence planning.

Mitigation:

- use staged dual-read or compatibility views where necessary
- preserve file/build lineage during migration

### Risk 2: Neo4j promotion before boundaries are stable

If Neo4j import is promoted before file/build identity is stable, the graph plane may just inherit the current ambiguity.

Mitigation:

- finish file/build ownership work before fully switching query services

### Risk 3: Prompt expansion lowers precision

Broader prompt coverage can reduce graph precision if done through one oversized prompt.

Mitigation:

- use profile routing and prompt snapshots rather than one universal mega-prompt

### Risk 4: Frontend polish masks backend correctness issues

Improving force layout and styling too early can create confidence without fixing wrong data boundaries.

Mitigation:

- require strict file-graph correctness before enabling polished UX as the default

## Success Criteria

Module 4 should be considered materially complete for this plan when the following are all true:

- file-scoped graph APIs are live in the running runtime
- each uploaded file produces one isolated graph build
- graph nodes and edges are owned by build identity, not only tenant scope
- Module 2 upload sync intent survives restarts
- GraphRAG workspaces are reproducible and txt-based
- prompt usage is snapshot-based and profile-aware
- rules are split into domain-specific families
- Neo4j serves as a real graph query plane
- frontend defaults to the current file graph and does not silently mix graphs
- output quality is consistently close to the validated `ragtest` path on baseline samples

## Open Decisions For Implementation Planning

These do not block this design, but they must be resolved in the implementation plan:

- exact migration strategy from `module4.*` transitional tables to business-oriented tables
- whether Neo4j query services replace all existing graph APIs at once or behind a compatibility layer
- whether OCR is introduced in the same milestone as legacy Office conversion or in a later milestone
- whether prompt profile routing is manual-first or heuristic-first in the first release

## Recommendation

The recommended path is a staged closure strategy:

1. fix runtime drift and enforce file graph correctness first
2. harden durable sync and workspace reproducibility
3. promote prompt, rule, and Neo4j subsystems into first-class platform capabilities
4. only then make the frontend fully strict and polished by default

This ordering minimizes rework and aligns with the user-approved priority:

correct single-file graph behavior first, Neo4j-grade product experience second, long-term platform governance third.
