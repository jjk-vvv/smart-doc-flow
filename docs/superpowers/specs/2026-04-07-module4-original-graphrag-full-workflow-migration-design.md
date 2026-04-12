# Module 4 Original GraphRAG Full Workflow Migration Design

## 1. Purpose

This design defines how to migrate the original `D:\GraphRAG` GraphRAG knowledge graph workflow into Module 4 so that Module 4 becomes a host container for the original GraphRAG runtime instead of an independent graph-building implementation.

The target end state is:

- Module 4 keeps the FastAPI shell.
- Module 4 keeps PostgreSQL persistence, job orchestration, and frontend response shaping.
- Module 4 keeps the project-specific text corpus input adapter.
- GraphRAG becomes the authoritative indexing and query core.
- GraphRAG artifacts become the primary truth source for graph semantics.
- Module 4 graph APIs and frontend rendering become adapters over GraphRAG-native outputs.

This is not a "make Module 4 look more like GraphRAG" effort.
This is a "make Module 4 run the original GraphRAG workflow inside the project architecture" effort.

## 2. Scope

### In scope

- Align Module 4 indexing to original GraphRAG workflow order and artifact semantics.
- Align Module 4 query behavior to original GraphRAG query data loading and context-building concepts.
- Align Module 4 settings, prompt organization, workspace structure, and output layout to GraphRAG conventions as closely as practical.
- Preserve Module 4 project-specific input semantics:
  - direct text corpus input
  - Module 2 derived high-quality text corpus input
  - FastAPI job orchestration
  - PostgreSQL graph projection
  - frontend graph rendering adapter

### Out of scope

- Replacing the broader project backend architecture outside Module 4.
- Replacing Module 2 file parsing and assistant systems.
- Requiring users to interact with raw GraphRAG CLI directories directly.
- Removing PostgreSQL storage from the product architecture.
- Requiring the frontend to consume raw GraphRAG artifacts directly without Module 4 APIs.

## 3. Decision Summary

### Decision 1: GraphRAG is the graph core

Graph construction logic, workflow order, artifact definitions, query context semantics, and prompt contracts should be owned by GraphRAG, not by Module 4 custom logic.

### Decision 2: Module 4 is the host layer

Module 4 remains responsible for:

- accepting normalized text corpus
- preparing workspaces
- running GraphRAG
- importing artifacts into PostgreSQL
- exposing stable APIs for the frontend
- preserving tenant, file, job, and graph version isolation

### Decision 3: Artifact-first truth model

GraphRAG artifact outputs are the semantic source of truth.
PostgreSQL is a service projection and retrieval layer, not the primary graph-definition layer.

### Decision 4: Query must be migrated, not only indexing

If only indexing is aligned but query remains database-first and Module 4-defined, the user-visible graph will still diverge from original GraphRAG behavior.

### Decision 5: Input adaptation remains project-specific

Original GraphRAG input discovery can be replaced by the project's own text corpus ingestion path, but the resulting normalized corpus must satisfy GraphRAG expectations for clean, semantically meaningful text.

## 4. Original GraphRAG Workflow Baseline

The original GraphRAG standard indexing pipeline is defined by the original GraphRAG workflow factory:

- `load_input_documents`
- `create_base_text_units`
- `create_final_documents`
- `extract_graph`
- `finalize_graph`
- `extract_covariates`
- `create_communities`
- `create_final_text_units`
- `create_community_reports`
- `generate_text_embeddings`

These workflows form a dependency chain rather than a single extraction step. The practical meaning of the pipeline is:

1. load documents
2. split documents into text units
3. link documents and text units
4. extract entity and relationship candidates
5. merge and summarize graph structure
6. optionally extract claims or covariates
7. detect graph communities
8. materialize final text unit outputs
9. generate community reports
10. generate embeddings for downstream query

GraphRAG therefore owns:

- the structure of text-unit composition
- graph extraction workflow order
- summarization behavior
- community construction
- community report generation
- embedding timing and artifact family

Module 4 should not independently redefine these semantics.

## 5. Current Module 4 State

Module 4 already contains important GraphRAG-oriented infrastructure:

- GraphRAG-style workspace builder
- GraphRAG CLI runner and runtime probe
- GraphRAG prompt registry
- GraphRAG final and partial artifact importer
- PostgreSQL graph persistence with file scope
- FastAPI graph, evidence, alert, and job APIs

Current strengths:

- Module 4 can already prepare a GraphRAG-style workspace and run `python -m graphrag.index`.
- Module 4 already imports final artifact families such as:
  - `create_final_documents.parquet`
  - `create_final_text_units.parquet`
  - `create_final_entities.parquet`
  - `create_final_relationships.parquet`
  - `create_final_communities.parquet`
  - `create_final_community_reports.parquet`
- Module 4 already persists file-scoped graph state and graph versions.

Current gaps:

- settings and configuration are still Module 4-shaped first and GraphRAG-shaped second
- input corpus normalization still contains project-specific assembly logic that can inject noise
- query behavior is still not fully GraphRAG-native
- frontend graph views are still largely database-driven rather than GraphRAG query-context-driven
- prompts are aligned in intent but not yet fully aligned in workflow contract and variable semantics
- Module 4 still contains custom compatibility behavior that can obscure what GraphRAG itself produced

## 6. Gap Matrix

| Dimension | Current Module 4 State | Target State | Migration Direction |
| --- | --- | --- | --- |
| Input ingestion | Module 4 accepts project-specific normalized payloads | GraphRAG consumes a clean GraphRAG-ready text corpus generated by Module 4 | Keep Module 4 adapter, tighten corpus quality rules |
| Workspace structure | GraphRAG-like | As close as possible to original GraphRAG workspace contract | Continue converging toward original GraphRAG structure |
| Settings model | Module 4 env mapped into generated YAML | Internal runtime centered on GraphRAG-native config semantics | Refactor settings generation around GraphRAG concepts |
| Workflow ownership | GraphRAG CLI invoked, but Module 4 still carries some defining behavior | GraphRAG workflows define graph outputs | Shift ownership to GraphRAG pipeline |
| Prompt organization | Similar files exist in Module 4 | Prompt contract follows original GraphRAG workflow semantics | Realign prompt content, variables, and binding |
| Artifact semantics | Imported into PostgreSQL with compatibility shaping | Artifact family is authoritative truth source | Make importer artifact-first and thinner |
| Query semantics | Largely graph-database-driven APIs | GraphRAG query context drives graph views | Introduce GraphRAG query adapter layer |
| Graph API output | Stable for frontend, but not fully GraphRAG-native | Stable APIs backed by GraphRAG query semantics | Preserve API shell, replace internal source |
| Frontend render source | Mostly database graph view | GraphRAG semantic view adapted to G6 | Make frontend adapter query-result-first |
| Diagnostics | Workspace manifest and logs already exist | Workspace, config, logs, artifacts, and graph versions fully traceable | Strengthen artifact-first diagnostics |

## 7. Target Architecture

The target architecture is a six-layer design.

### 7.1 Input Corpus Adapter

Purpose:

- accept Module 4 text input
- accept Module 2-derived high-quality text corpus
- produce GraphRAG-ready normalized document text

Responsibilities:

- merge high-quality textual sources
- strip display-shell noise
- preserve semantic prose and fact-bearing chart or table text
- emit deterministic document metadata

Non-responsibilities:

- graph extraction
- relationship construction
- community generation

### 7.2 GraphRAG Runtime Host

Purpose:

- host original GraphRAG runtime inside Module 4

Responsibilities:

- workspace creation
- settings generation
- prompt materialization
- GraphRAG indexing execution
- GraphRAG query runtime wiring
- run logs and manifest tracking

Non-responsibilities:

- product API response shaping
- frontend graph layout
- business storage semantics beyond runtime bookkeeping

### 7.3 Artifact Truth Layer

Purpose:

- define graph semantics from GraphRAG outputs

Responsibilities:

- preserve exact GraphRAG artifact family
- preserve artifact lineage
- make artifacts inspectable and reproducible

Non-responsibilities:

- frontend-specific graph projection
- database-specific graph invention

### 7.4 PostgreSQL Projection Layer

Purpose:

- persist GraphRAG outputs in the product's data model

Responsibilities:

- file-scoped graph storage
- graph version storage
- evidence rows
- alert and rule storage
- tenant isolation
- API-friendly retrieval

Non-responsibilities:

- redefining graph semantics
- replacing GraphRAG artifact contracts

### 7.5 Query Adaptation Layer

Purpose:

- expose GraphRAG-native query behavior through Module 4 APIs

Responsibilities:

- load GraphRAG artifacts or data readers
- build local/global/drift query-compatible context
- generate stable overview, community, and drilldown graph models
- adapt GraphRAG query outputs to frontend contracts

Non-responsibilities:

- direct graph layout styling
- replacing GraphRAG query semantics with ad hoc database joins

### 7.6 Frontend Render Adapter

Purpose:

- turn GraphRAG semantic graph outputs into stable AntV G6 view models

Responsibilities:

- node categorization
- cluster assignment
- stable relation labeling
- overview and drilldown graph presentation

Non-responsibilities:

- inferring graph meaning from raw database edges

## 8. Input Corpus Strategy

Module 4 does not need to adopt original GraphRAG's raw file discovery path.
It should adopt original GraphRAG's expectations about clean textual input.

### 8.1 Supported input modes

- direct text corpus for plain text uploads
- Module 2 generated text corpus for complex uploads such as `docx` or `pdf`

### 8.2 Preferred text sources

- source document plain text
- MinerU markdown body text
- Gemini chart or table analysis converted into fact-bearing prose
- semantically useful summaries grounded in the source document

### 8.3 Text that should be suppressed or downgraded

- display shell labels
- placeholder table or figure identifiers
- assistant payload wrapper keys when they are not semantically meaningful
- page artifact identifiers
- pure UI metadata text

### 8.4 Input acceptance rule

Module 4 should only send text to GraphRAG when it meets this standard:

- understandable to a human without the original UI shell
- preserves entity-bearing context
- preserves relationship-bearing context
- does not over-index page labels and artifact wrappers

## 9. Prompt Contract Alignment

Prompt migration must not stop at filename parity.

Module 4 prompt alignment must cover:

- prompt purpose parity
- variable contract parity
- output-shape parity
- workflow binding parity
- settings binding parity

The following prompt families must be treated as GraphRAG workflow contracts:

- `entity_extraction`
- `summarize_descriptions`
- `claim_extraction`
- `community_report`

Module 4-specific language localization is allowed, but only when:

- the workflow contract remains intact
- the expected output structure remains intact
- the prompt still behaves as the original GraphRAG workflow expects

## 10. Query Alignment Requirements

Full migration requires query alignment, not only indexing alignment.

Module 4 must eventually support a GraphRAG-native query adaptation layer with these properties:

- graph view generation should be query-context-informed
- community reports should participate in graph exploration
- entity drilldown should preserve GraphRAG semantic neighborhood structure
- overview graphs should not be raw full-database graph dumps

The frontend should ultimately consume three stable semantic graph modes:

- overview graph
- community-focused graph
- entity drilldown graph

These should be derived from GraphRAG semantics and then adapted into G6 payloads.

## 11. Migration Phases

### Phase 1: Configuration and Workspace Native Alignment

Goal:

- make Module 4 internal runtime configuration GraphRAG-native in structure and semantics

Primary modules:

- `backend/module4/app/services/graphrag/settings.py`
- `backend/module4/app/services/graphrag/workspace.py`
- `backend/module4/app/services/graphrag/prompts.py`
- `backend/module4/assets/prompts/*`

Deliverables:

- GraphRAG-shaped settings generation
- stable prompt binding contract
- explicit env-to-GraphRAG-config mapping
- reduced Module 4-specific runtime divergence

Acceptance:

- workspace layout is reproducible
- settings structure is understandable in GraphRAG terms
- prompt materialization is deterministic

### Phase 2: Indexing Workflow Native Alignment

Goal:

- shift graph construction ownership to original GraphRAG workflows

Primary modules:

- `backend/module4/app/services/graphrag/indexer.py`
- `backend/module4/app/services/ingestion/runtime.py`
- `backend/module4/app/services/ingestion/text_corpus.py`

Deliverables:

- GraphRAG pipeline is the authoritative indexing path
- Module 4 no longer defines graph semantics outside host concerns
- workflow skips and retries are explicit and observable

Acceptance:

- node and edge meaning trace back to GraphRAG artifacts
- indexing output no longer depends on Module 4 custom extraction semantics

### Phase 3: Artifact Import and Projection Alignment

Goal:

- make PostgreSQL a GraphRAG projection layer instead of a graph-definition layer

Primary modules:

- `backend/module4/app/services/graphrag/importer.py`
- `backend/module4/app/db/storage.py`

Deliverables:

- artifact-first importer semantics
- document, text unit, entity, relationship, community, report, and covariate mapping aligned to GraphRAG outputs
- stronger graph version traceability

Acceptance:

- every major stored graph object can be traced back to its artifact source
- importer behavior is thinner and less interpretive

### Phase 4: Query Workflow Native Alignment

Goal:

- replace database-first graph views with GraphRAG-query-informed graph views

Primary modules:

- `backend/module4/app/services/query/*`
- `backend/module4/app/router.py`
- new GraphRAG query adapter modules under `backend/module4/app/services/graphrag/`

Deliverables:

- GraphRAG query data loading
- GraphRAG semantic graph view builder
- stable overview, community, and drilldown response models

Acceptance:

- graph responses are no longer thin wrappers over raw graph tables
- community reports and GraphRAG context materially affect returned graph views

### Phase 5: Frontend Semantic Rendering Alignment

Goal:

- make the frontend render GraphRAG semantic graph views rather than loosely arranged database graphs

Primary modules:

- frontend knowledge graph adapters
- frontend graph workbench state and render model

Deliverables:

- stable graph modes
- consistent node categories and relation semantics
- GraphRAG-compatible overview and drilldown interaction

Acceptance:

- users do not lose graph worldview when clicking nodes
- graph naming is centered on entities, communities, and reports rather than arbitrary text fragments

## 12. Module Mapping

The following Module 4 files are central to the migration:

- `backend/module4/app/services/graphrag/workspace.py`
- `backend/module4/app/services/graphrag/indexer.py`
- `backend/module4/app/services/graphrag/importer.py`
- `backend/module4/app/services/graphrag/settings.py`
- `backend/module4/app/services/graphrag/prompts.py`
- `backend/module4/app/services/ingestion/runtime.py`
- `backend/module4/app/services/ingestion/text_corpus.py`
- `backend/module4/app/services/query/runtime.py`
- `backend/module4/app/router.py`
- `backend/module4/assets/prompts/entity_extraction.txt`
- `backend/module4/assets/prompts/summarize_descriptions.txt`
- `backend/module4/assets/prompts/claim_extraction.txt`
- `backend/module4/assets/prompts/community_report.txt`

Expected future responsibility changes:

- `workspace.py` becomes a GraphRAG runtime host component rather than a custom workspace utility
- `indexer.py` becomes a GraphRAG pipeline execution adapter rather than a simple CLI wrapper
- `importer.py` becomes a standardized GraphRAG artifact projector
- `ingestion/runtime.py` becomes an orchestration-only layer
- query runtime shifts from database-centered graph assembly to GraphRAG query adaptation

## 13. Risks

### Risk 1: Partial alignment creates a false sense of parity

If indexing is aligned but query remains database-first, the frontend will still diverge from original GraphRAG behavior.

### Risk 2: Input corpus quality undermines GraphRAG quality

If Module 4 continues passing low-value payload wrappers, placeholder table labels, or display-shell text into GraphRAG, graph quality will remain unstable even with workflow parity.

### Risk 3: PostgreSQL projection becomes semantically overpowered again

If the importer or query layer starts inventing graph semantics for convenience, the migration will drift away from GraphRAG after initial success.

### Risk 4: Prompt localization changes behavior

Prompt language updates that preserve meaning for a human may still break GraphRAG workflow expectations if they change output contract or extraction framing.

### Risk 5: Frontend pressure may cause premature graph reshaping

Trying to solve rendering concerns before query alignment can force the backend to return visually convenient but semantically unstable graph payloads.

## 14. Non-Negotiable Principles

- GraphRAG owns graph semantics.
- Artifacts are the semantic source of truth.
- PostgreSQL is a projection and service layer.
- Module 4 input remains project-specific, but GraphRAG output remains GraphRAG-defined.
- Query alignment is required for true parity.
- Frontend rendering must adapt GraphRAG semantics, not replace them.

## 15. Acceptance Criteria

The migration should only be considered successful when all of the following are true:

- Module 4 generates the same essential artifact family as original GraphRAG for the same input class.
- Module 4 graph construction semantics are traceable to GraphRAG workflows rather than Module 4 custom graph logic.
- Module 4 query responses are driven by GraphRAG artifact and context semantics rather than raw database expansion.
- Frontend graph views are stable across overview and drilldown interactions.
- Node naming is primarily semantic and graph-native, not raw text-fragment-driven.
- Workspace, settings, logs, artifacts, graph versions, and import summaries are inspectable and traceable.
- Module 4 remains a host shell and integration layer rather than a competing graph engine.

## 16. Immediate Next Step

The next implementation stage should be Phase 1 only:

- converge runtime settings
- converge workspace generation
- converge prompt contract
- define the internal env-to-GraphRAG-config mapping

No further large-scale graph behavior change should be attempted before that Phase 1 baseline is written, reviewed, and accepted.

## 17. Relationship To Earlier Design Work

Earlier Module 4 GraphRAG designs in this repository focused on:

- GraphRAG-first indexing enablement
- frontend sync and workspace execution
- production runtime readiness
- file-scoped graph storage and rendering

This document supersedes those earlier designs as the top-level migration blueprint wherever they conflict on the question of ownership.

The new ownership model is:

- GraphRAG owns graph logic
- Module 4 owns product integration

