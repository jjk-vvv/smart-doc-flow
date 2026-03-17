# Module 4 Stability And Repair Design

Date: 2026-03-17

## Summary

This spec defines the approved repair direction for Module 4.
The goal is not to redesign Module 4 from scratch.
The goal is to turn the current implementation into a stable, reproducible, evidence-aware, build-versioned graph service that can support production-style upload sync from Module 2.

The current codebase already contains a meaningful foundation:

- upload sync and document ingest APIs exist
- GraphRAG workspace preparation exists
- GraphRAG runtime probing exists
- artifact import exists for both final and partial outputs
- graph file and graph version metadata exist
- alert, evidence, explain, simulate, and health APIs exist

However, the system is still in an in-between state.
It behaves like a partially completed graph platform:

- the main storage and versioning model are usable but not yet fully durable
- runtime fallback paths are stronger than runtime correctness guarantees
- evidence lineage is much stronger for direct document ingest than for GraphRAG import
- API contracts expose more capability than the implementation actually performs
- Neo4j is configured and probed, but is not yet a true serving plane

This spec converts those observations into a concrete repair strategy.

## Relationship To Existing Specs

This spec builds on the existing Module 4 design work and narrows the focus to stabilization and implementation correctness.

It is intentionally downstream of:

- `docs/superpowers/specs/2026-03-15-module4-graphrag-sync-frontend-design.md`
- `docs/superpowers/specs/2026-03-16-module4-graphrag-production-alignment-design.md`
- `docs/superpowers/specs/2026-03-16-module4-production-closure-execution-plan-design.md`
- `docs/superpowers/specs/2026-03-17-module4-neo4j-overview-graph-design.md`

Those documents established the direction.
This document focuses on one narrower question:

How do we repair the current Module 4 implementation so that it becomes stable, versioned, evidence-complete, and implementation-honest?

## Why This Spec Exists

Recent analysis of the current Module 4 code and tests shows a clear pattern:

### 1. Module 4 is closer to "operational skeleton" than "production-complete graph service"

The backend is not empty.
It already has:

- build workspace generation
- GraphRAG runtime checks
- upload normalization
- final and partial artifact import
- graph file metadata
- graph version metadata
- tenant graph and file graph APIs
- default deterministic rules

That means the next step is not invention.
It is closure and hardening.

### 2. Stability gaps are now implementation gaps, not only configuration gaps

The current test suite mostly passes, but not fully.
On 2026-03-17, `pytest backend/module4/tests -q` produced:

- 29 passing tests
- 2 failing tests

The failures are not random.
They point at startup and database retry behavior around localhost versus IPv4 candidate ordering.
That is exactly the kind of issue that distinguishes "mostly working" from "operationally stable."

### 3. The system currently over-relies on fallback behavior

Module 4 does several useful things when dependencies are imperfect:

- memory fallback when database connection fails
- partial artifact import when full GraphRAG indexing fails but usable artifacts exist
- rule engine seeding even in degraded states

These are useful recovery behaviors.
They are not substitutes for a stable mainline.
The repaired design should preserve controlled fallback, but only after the mainline is clearly defined and validated.

### 4. The graph plane is still transitional

Today, Module 4 mainly serves graph results from Module 4 storage.
Neo4j is only:

- configured
- exposed to workspaces
- probed during deep health checks

This means the system can claim Neo4j compatibility, but not yet true Neo4j-backed graph serving.

### 5. Evidence quality is not consistent across ingest modes

Direct document ingest writes evidence and edge-evidence links.
GraphRAG import writes graph objects, but does not yet materialize a similarly rich evidence layer from text units, community reports, and relationship provenance.

As a result, Module 4 is stronger at "store graph objects" than at "prove why they exist."

### 6. API shape is ahead of real capability in several places

Examples:

- schema allows `semantic` and `anomaly` rules, but runtime only executes deterministic rules
- explain and simulate APIs exist, but currently provide lightweight placeholder behavior rather than graph-native reasoning

This gap should be closed either by implementing the capability or narrowing the contract until the capability exists.

## Goals

- Make Module 4 startup, storage connection, and recovery behavior deterministic and test-clean.
- Preserve Postgres-backed control plane semantics as the primary source of truth for jobs, files, builds, alerts, and evidence metadata.
- Make upload sync reproducible through internal Module 4 snapshots rather than depending on external file paths remaining valid forever.
- Treat GraphRAG output quality as a gated build artifact, not just a directory that happens to exist.
- Make graph build lineage explicit and queryable through graph file and graph version records.
- Materialize usable evidence for GraphRAG-derived graph objects so the graph can be explained and audited.
- Align API contracts with actual behavior, especially around rule types, explain, and simulate.
- Prepare Module 4 for Neo4j promotion without making Neo4j cutover a prerequisite for storage correctness.
- Preserve file-scoped graph correctness while enabling later tenant-level global entity aggregation.

## Non-Goals

- Do not replace the current system with a Neo4j-only implementation in one step.
- Do not remove partial recovery behavior before the mainline is stronger.
- Do not treat direct document ingest and GraphRAG upload ingest as fully equivalent; their semantics differ and should remain explicit.
- Do not expand product scope into frontend redesign in this spec.
- Do not promise semantic or anomaly rule execution in the same milestone as storage hardening unless explicitly planned.
- Do not optimize build latency ahead of correctness, lineage, and evidence quality.

## Current State Findings

### Finding 1: Storage retry behavior is not yet fully stable

The current connection candidate logic in `Module4Storage` is close, but not consistent with its own test expectations.
The localhost and IPv4 fallback order is currently reversed relative to the intended behavior.

Impact:

- startup behavior is less predictable than desired
- operational recovery semantics are harder to reason about
- the test suite is not fully green

### Finding 2: Memory fallback is useful but currently too easy to lean on

Memory fallback helps local development and failure tolerance.
But it can also hide a real database readiness problem if it is treated as "good enough."

Impact:

- degraded mode can mask production-critical issues
- restart recovery and durable rebuild semantics become weaker in memory mode
- correctness depends too heavily on runtime environment luck

### Finding 3: Upload rebuild durability is incomplete

Rebuild currently replays ingest batches from saved raw payloads.
For uploads, that means the replay still depends on the referenced file paths and artifacts remaining valid outside Module 4.

Impact:

- rebuild is not fully self-contained
- old uploads may become non-replayable if external storage paths change
- build reproducibility is weaker than the API suggests

### Finding 4: Input normalization is text-centric rather than structure-centric

`UploadInputNormalizer` converts PDF, DOCX, and XLSX inputs into text.
This is useful for GraphRAG input.
But it does not preserve richer structural objects such as:

- table lineage
- figure lineage
- page-level evidence blocks
- layout-aware anchors

Impact:

- Module 4 can build graphs from text, but it cannot yet fully preserve structure-origin evidence from upload-side artifacts
- evidence richness lags behind graph object richness

### Finding 5: GraphRAG artifact import is stronger on graph objects than on evidence objects

The importer successfully creates:

- Document nodes
- Chunk nodes
- Entity nodes
- Community nodes
- Covariate nodes
- graph edges between them

But it does not yet generate a first-class evidence layer from:

- text units
- relationship source chunk references
- community report content
- report-to-document anchors

Impact:

- graph exploration works better than graph justification
- explainability is weaker than the storage model could support

### Finding 6: Partial artifact fallback is operationally useful but not quality-governed enough

When GraphRAG full indexing fails but recoverable artifacts exist, Module 4 imports partial results.
This behavior is valuable.
But it currently does not enforce a formal artifact quality gate before marking results as importable partial output.

Impact:

- partial mode can vary in quality
- downstream consumers may not know how incomplete the imported graph really is
- "ready" versus "usable enough to inspect" is not sharply defined

### Finding 7: Rule engine contract is broader than the actual execution engine

Schemas and persistence allow:

- deterministic
- semantic
- anomaly

But runtime evaluation currently executes only deterministic rules.

Impact:

- API truthfulness is weaker than it should be
- callers may infer capabilities that do not exist
- implementation planning gets muddier because contract and execution differ

### Finding 8: Explain and simulate are not yet graph-native features

The current endpoints are valid scaffolding, but they do not yet deliver full graph reasoning behavior.

Explain currently focuses on:

- alert summary
- rule metadata
- generic guidance

Simulate currently focuses on:

- risk multiplier effects over existing alerts

Impact:

- these endpoints are better described as placeholders than mature graph intelligence features

### Finding 9: Neo4j is present in readiness flow but absent from the serving path

Neo4j configuration and deep health probing are implemented.
Neo4j environment values are passed into GraphRAG workspaces.
But Module 4 does not yet write, version, query, and validate graph data through a real Neo4j service layer.

Impact:

- the current serving path is still storage-centric rather than graph-plane-centric
- long-term graph-native querying is not yet realized
- Neo4j remains preparatory rather than decisive

### Finding 10: Tenant graph exists, but true global entity aggregation does not yet

Module 4 can list tenant-level graph views.
But it does not yet implement a robust cross-file canonical entity layer that safely merges same-real-world entities across files.

Impact:

- the service is currently stronger at file graph isolation than at tenant-wide knowledge consolidation
- future "global graph" behavior needs an explicit aggregation layer rather than implicit name-based merging

## Approaches Considered

### Approach A: Stabilize Postgres-first, postpone Neo4j

Description:
Treat Postgres storage as both the control plane and the practical graph-serving plane for now.
Repair stability, lineage, evidence, and contract honesty first.
Leave Neo4j as a later enhancement.

Advantages:

- lowest short-term risk
- fastest path to a stable backend
- fits current implementation patterns

Disadvantages:

- delays true graph-native serving
- keeps Module 4 more transitional for longer

### Approach B: Postgres fact source plus Neo4j projection

Description:
Keep Postgres as the source of truth for jobs, graph files, graph versions, alerts, evidence metadata, and build lineage.
Add a Neo4j projection layer that only activates for validated ready builds.
Serve graph traversal from the projection layer once it is reliable.

Advantages:

- best balance between safety and long-term direction
- preserves current investment in storage versioning
- makes Neo4j promotion incremental instead of disruptive

Disadvantages:

- requires dual-system consistency handling
- introduces a projection pipeline that must be monitored

### Approach C: Neo4j-first rewrite of the graph plane

Description:
Move the graph plane to Neo4j as the main execution and query store immediately.
Retain Postgres only for non-graph control-plane data.

Advantages:

- cleanest long-term graph-native model
- avoids keeping a transitional graph path too long

Disadvantages:

- highest migration risk
- most likely to disrupt currently working behavior
- too much change for the current stabilization stage

## Recommendation

The recommended path is Approach B:

`Postgres as fact source and control plane, Neo4j as promoted projection layer`

This approach matches the current codebase best because:

- graph file and graph version lineage already exist
- storage-driven APIs already exist
- Neo4j readiness and workspace integration already exist
- the user priority is first to make the path stable and complete, not to maximize architectural novelty immediately

## Architecture Principles

### 1. Mainline before fallback

Fallback is allowed only after the system has a clearly defined successful mainline.
Partial import and memory mode should be explicit degraded states, not the assumed operating norm.

### 2. Build lineage is first-class

Every graph result must belong to:

- a tenant
- a file
- a build version
- a workspace snapshot

No graph output should exist without traceable build ownership.

### 3. Evidence is a product feature, not an implementation detail

A graph object that cannot be traced back to textual or structural evidence is incomplete.
Graph import should therefore produce graph objects and evidence objects together.

### 4. Contracts must tell the truth

If Module 4 only executes deterministic rules today, the public contract should either say so or expose semantic and anomaly support as explicitly inactive.

### 5. File graph isolation and global aggregation are different layers

Single-file graph correctness remains the base layer.
Tenant-wide aggregation should be built as a second layer, not as accidental merging in the base layer.

## Target System Model

The repaired Module 4 is organized into six cooperating domains:

- runtime and startup domain
- file and build lineage domain
- GraphRAG execution domain
- graph import and evidence domain
- rule and explanation domain
- graph projection domain

### Runtime And Startup Domain

Purpose:
Guarantee deterministic startup, dependency readiness classification, and explicit degraded behavior.

Responsibilities:

- storage connection candidate ordering
- startup timeout behavior
- memory fallback policy
- recoverable job replay
- readiness classification

### File And Build Lineage Domain

Purpose:
Own durable identity for graph files, graph versions, ingest batches, and replayable upload state.

Responsibilities:

- graph file state machine
- graph version history
- upload normalization snapshots
- replay-safe build inputs

### GraphRAG Execution Domain

Purpose:
Produce workspace inputs, run GraphRAG, classify failures, and validate output quality.

Responsibilities:

- workspace creation
- prompt materialization
- runtime probing
- GraphRAG invocation
- artifact quality gating

### Graph Import And Evidence Domain

Purpose:
Import valid graph artifacts into storage and materialize evidence that can explain the graph.

Responsibilities:

- final artifact import
- partial artifact import
- evidence generation from text units and reports
- edge-to-evidence linkage

### Rule And Explanation Domain

Purpose:
Execute supported rules honestly and provide explanation APIs that reflect real provenance.

Responsibilities:

- deterministic rule evaluation
- capability declaration for unsupported rule kinds
- evidence-backed explain responses
- scenario evaluation that is meaningfully tied to rule execution

### Graph Projection Domain

Purpose:
Project validated ready graph builds into Neo4j and eventually serve graph-native query endpoints from that projection.

Responsibilities:

- projection job
- projection version tracking
- consistency checks between Postgres metadata and Neo4j graph plane

## Data Flow

The repaired preferred data flow is:

`Module 2 persisted upload -> Module 4 ingest batch record -> normalization snapshot -> workspace creation -> GraphRAG run -> artifact quality gate -> graph import + evidence materialization -> graph version ready -> optional Neo4j projection -> queryable file graph`

### Important Clarification

The repair plan does not require Neo4j to be in the critical path before a graph build can be marked ready.
Instead:

- a build is ready when Postgres-side lineage, import, and evidence are valid
- Neo4j projection can follow as a downstream promotion step

This avoids turning Neo4j reachability into a blocker before the core build pipeline is stable.

## Detailed Repair Plan

### Workstream A: Runtime Stability And Test Closure

Objective:
Make startup, connection retry, and degraded behavior deterministic.

Tasks:

- fix localhost versus IPv4 candidate ordering in storage connection logic
- make the storage retry path fully align with test expectations
- keep memory fallback, but make it explicit and configurable for development versus production-style deployment
- extend health reporting to distinguish:
  - hard failure
  - degraded but running
  - fully ready
- ensure recovery logic does not silently continue from invalid replay payloads

Acceptance criteria:

- `pytest backend/module4/tests -q` passes cleanly
- storage retry behavior is deterministic
- degraded mode is visible and intentional

### Workstream B: Replayable Upload Snapshots

Objective:
Make rebuild and retry independent from fragile external file paths.

Tasks:

- persist normalized text snapshot metadata at ingest time
- store enough file lineage to replay upload builds without depending only on original storage paths
- record normalization failures as first-class graph file failures with replay diagnostics
- ensure rebuild prefers internal snapshots over outside-of-Module-4 references

Acceptance criteria:

- a rebuild can succeed even if the original external upload path is no longer the primary replay source
- every upload-derived graph version can identify its normalization snapshot

### Workstream C: GraphRAG Artifact Quality Gate

Objective:
Promote artifacts to import only when they satisfy explicit quality rules.

Tasks:

- define separate validation rules for final artifact sets and partial artifact sets
- require core artifact presence and minimal structural consistency
- classify output as:
  - success
  - partial
  - failed
- include quality gate results in graph version import summaries and manifests

Acceptance criteria:

- partial import is explicit and quality-scored
- ready builds satisfy a documented minimum artifact contract
- failed builds explain which artifact requirement was violated

### Workstream D: Evidence Materialization For GraphRAG Imports

Objective:
Close the gap between imported graph objects and their provenance.

Tasks:

- convert text units into evidence objects
- attach community report summaries and report content as evidence where appropriate
- link relationships and graph edges back to source chunk references
- preserve artifact URLs, file identity, and any available page or structural locator metadata
- expose evidence counts and evidence completeness in import summaries

Acceptance criteria:

- GraphRAG-derived nodes and edges can be traced back to evidence entries
- explain responses can cite concrete evidence rather than generic summaries alone

### Workstream E: Honest Rule Capability Model

Objective:
Align rule contracts with real execution behavior.

Tasks:

- keep deterministic evaluation as the only active execution path initially
- mark semantic and anomaly kinds as unsupported or inactive until implemented
- expose capability metadata through API or documentation
- separate future rule extension design from current deterministic execution hardening

Acceptance criteria:

- public behavior no longer implies unsupported rule execution
- deterministic rules remain stable through ingest and rebuild

### Workstream F: Explain And Simulate Hardening

Objective:
Move explain and simulate from placeholders toward evidence-aware utility.

Tasks:

- make explain return alert context, graph neighborhood hints, and evidence references
- make explain responses reference real evidence IDs, node IDs, and graph file or graph version identifiers where available
- make simulate operate on rule inputs or scenario state rather than only multiplying existing scores
- keep the initial implementation narrow and explicit rather than pretending to offer general reasoning

Acceptance criteria:

- explain is evidence-backed
- simulate is scenario-aware rather than a purely cosmetic score transform

### Workstream G: Neo4j Projection Layer

Objective:
Promote Neo4j into a real downstream graph plane without destabilizing the control plane.

Tasks:

- add a projection service that writes ready graph versions into Neo4j
- version projection results and store sync status per graph version
- validate projection completeness before serving graph data from Neo4j
- keep Postgres file and build metadata as the authoritative control plane

Acceptance criteria:

- ready graph versions can be projected and validated
- projection failure does not corrupt Postgres-side build state
- a clean path exists to move selected graph endpoints to Neo4j later

### Workstream H: Tenant-Wide Global Aggregation Layer

Objective:
Prepare for true global graph behavior without weakening file isolation.

Tasks:

- retain file-scoped graph correctness as the base graph layer
- add explicit canonical entity aggregation logic for future cross-file consolidation
- avoid implicit same-name merging as the default behavior
- define merge confidence and provenance rules before any automatic cross-file union is enabled

Acceptance criteria:

- file graphs remain isolated
- global aggregation can be added as a controlled second layer

## State Machines

### Graph File Statuses

Recommended stable statuses:

- `queued`
- `preparing_input`
- `normalizing_inputs`
- `validating_runtime`
- `indexing`
- `importing_graph`
- `ready`
- `failed`

### Graph Version Statuses

Recommended stable statuses:

- `preparing_input`
- `indexing`
- `importing_graph`
- `ready`
- `partial`
- `failed`

Important rule:

- a graph file may remain `ready` while a new graph version is being built
- active version switching should occur only after the new version passes import and quality gates

## Error Handling

The repaired Module 4 should classify failures into explicit buckets.

Minimum required failure categories:

- `storage_connect_failed`
- `memory_mode_forced`
- `recover_payload_invalid`
- `normalization_failed`
- `runtime_not_ready`
- `index_timeout`
- `index_process_failed`
- `artifacts_missing`
- `artifact_quality_failed`
- `graph_import_failed`
- `evidence_materialization_failed`
- `projection_failed`

Every failure should produce:

- job-visible status
- file-visible status
- version-visible status when a version exists
- concise failure message
- classification code

## Testing Strategy

### Unit Tests

- storage candidate ordering and startup behavior
- normalization snapshot creation
- artifact quality gate behavior
- GraphRAG import evidence generation
- rule capability declaration
- explain and simulate contract behavior

### Integration Tests

- upload sync produces replayable build lineage
- rebuild reuses internal snapshots correctly
- final artifact import yields graph and evidence outputs
- partial artifact import yields explicit partial classification
- projection service records sync results correctly

### Regression Tests

- repeated rebuild on the same tenant produces stable graph counts and version lineage
- two files with overlapping names remain isolated unless canonical aggregation is explicitly invoked
- evidence counts are non-zero for GraphRAG-derived graphs where text units exist
- health responses distinguish ready versus degraded states accurately

## Sequencing

Implementation should proceed in this order:

### Phase P0: Stabilize The Current Mainline

- Workstream A
- Workstream B
- Workstream C

Reason:
The system must first become deterministic, replayable, and quality-gated.

### Phase P1: Complete Provenance And Contract Honesty

- Workstream D
- Workstream E
- Workstream F

Reason:
Once the build path is stable, the next priority is to make results trustworthy and explainable.

### Phase P2: Promote The Graph Plane

- Workstream G
- Workstream H

Reason:
Neo4j promotion and tenant-wide aggregation should happen after file-scoped lineage and evidence are solid.

## Success Criteria

Module 4 should be considered materially repaired for this plan when all of the following are true:

- the Module 4 backend test suite is green
- startup and storage retry behavior are deterministic
- upload rebuild no longer depends only on fragile external file references
- graph versions are classified by explicit artifact quality gates
- GraphRAG-derived graph objects have usable evidence links
- explain and simulate no longer overstate their real capability
- rule contracts match rule execution behavior
- Neo4j has a defined and testable promotion path as a projection layer
- file-scoped graph correctness remains intact throughout the repair work

## Open Decisions For Implementation Planning

These do not block the design, but they must be resolved before or during implementation planning:

- exact format and retention policy for normalization snapshots
- whether projection to Neo4j is synchronous after ready import or asynchronous through a dedicated queue
- whether semantic and anomaly rules remain hidden, rejected, or marked inactive at the API level in the first repair milestone
- how much evidence metadata can be recovered directly from GraphRAG outputs versus requiring upstream enrichment from Module 2

## Recommendation

The recommended execution path is:

1. close startup and storage stability gaps first
2. make upload replay and build lineage durable
3. introduce explicit artifact quality gates
4. materialize evidence for GraphRAG imports
5. narrow contracts to match real behavior
6. only then promote Neo4j into a real projection layer

This order best matches the current system state and the approved priority:

first make Module 4 reliable and honest, then make it graph-native and globally aggregating.
