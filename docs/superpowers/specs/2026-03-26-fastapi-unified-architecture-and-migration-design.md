# FastAPI Unified Architecture And Migration Design

Date: 2026-03-26

## Summary

This spec records the approved architecture direction for the current Smart Doc Flow project.

The recommended path is:

- keep `backend/app` as the single public FastAPI gateway and packaged backend entry
- keep `backend/module2` as the real document extraction engine
- keep `backend/module4` as the real graph and risk engine
- keep `backend/auth/server.cjs` as a temporary compatibility proxy instead of deleting it early
- keep the frontend on `React + Vite`
- adopt a layered MVC-style backend design instead of forcing a textbook single-process MVC rewrite
- migrate by boundary and responsibility, not by moving all files into one directory at once

This direction is preferred because it preserves the current full workflow:

- auth
- file upload
- DOC or DOCX preview conversion
- PDF parsing
- MinerU and Gemini-enhanced extraction
- trace rendering
- assistant1 grounded chat
- Module 2 to Module 4 sync
- graph querying, alerts, rules, explain, and simulate
- Electron packaging with a unified backend entry

The key architectural judgment is:

`The project is already on the right path toward framework unification, but it is not yet in a state where all old backend code should be physically merged into backend/app. The safest and highest-quality solution is a unified FastAPI gateway with bounded internal engines.`

## Why This Spec Exists

Recent project work established a unified FastAPI gateway and a stronger desktop entrypoint, but the real business logic is still split across several code boundaries.

That split is not automatically a problem.
What matters is whether the split is:

- explicit
- stable
- testable
- packageable
- aligned with the real product workflow

Current user requirements make the target constraints very clear:

- `auth` cannot be dropped
- the migration must not degrade functionality
- the full upload to extraction to graph workflow must remain intact
- old dead code and runtime junk must not be dragged into the new architecture
- the final structure must support later software packaging

This spec exists to convert those constraints into a practical architecture decision and a migration blueprint that can be executed safely.

## Approved Direction

The approved direction is `Approach B`:

- unify the backend framework around FastAPI
- unify the public backend entry around `backend/app`
- preserve Module 2 and Module 4 as bounded internal runtime engines
- continue reducing legacy concentration inside those engines through staged internal refactors
- treat compatibility layers as temporary bridges, not as future primary architecture

This approach is intentionally not a "hard single-process monolith now" plan.
It is a "single public entry, internally bounded engines, staged migration" plan.

## Goals

- Make FastAPI the authoritative backend framework.
- Preserve the current full business workflow without regression.
- Keep a single public backend entry and a single packaged desktop backend entry.
- Retain auth compatibility until old callers are no longer needed.
- Keep Module 2 extraction behavior complete, including DOCX to PDF and PDF parsing chains.
- Keep Module 4 graph behavior complete, including file graph, alerts, rules, explain, and simulate.
- Reduce architecture ambiguity by defining exact responsibility boundaries.
- Prepare the codebase for continued development after packaging.
- Exclude runtime artifacts, historical outputs, and test assets from packaged deliverables.

## Non-Goals

- Do not force all backend code into `backend/app` immediately.
- Do not rewrite the frontend into MVVM.
- Do not rebuild Module 2 parsing from scratch.
- Do not rebuild Module 4 around GraphRAG-only execution before the current graph ingest path is stabilized.
- Do not delete `auth` compatibility before migration risk is truly gone.
- Do not package runtime artifacts such as `artifacts`, `workspaces`, `runlogs`, or test outputs.

## Current State Snapshot

### 1. Real Public Backend Entry

The real public backend entry is:

- `backend/app/create_app.py`
- `backend/app/main.py`

This gateway already registers:

- auth
- assistant
- extraction
- gateway
- module1 placeholder
- frontend static

This means the project already has a meaningful unified backend shell.

### 2. Auth Is Already Split Into Core And Compatibility

Auth is not a single thing anymore.
It has two layers:

- FastAPI auth core in `backend/app/modules/auth`
- Node compatibility proxy in `backend/auth/server.cjs`

The FastAPI auth core is the real business authority.
The Node auth process is a compatibility adapter that forwards historical routes.

This is why `backend/auth/server.cjs` still contains `/api/chat`.
That file is not an auth-domain service.
It is a historical route proxy.

### 3. Module 2 Is Still The Real Extraction Engine

The current real extraction execution path is still centered in:

- `backend/module2/app/main.py`
- `backend/module2/app/runtime/*`
- `backend/module2/app/core/*`
- `backend/module2/app/agent/graph.py`
- `backend/module2/app/db/storage.py`
- `backend/module2/app/assistant_1/*`

The unified gateway extraction layer does not replace this engine yet.
It wraps and orchestrates it.

### 4. Module 4 Is Still The Real Graph Engine

The current real graph execution path is still centered in:

- `backend/module4/app/main.py`
- `backend/module4/app/db/storage.py`
- `backend/module4/app/services/*`

The unified gateway does not embed Module 4 directly.
It proxies `/module4/*` requests to the Module 4 backend.

### 5. Frontend Already Fits Single-Origin Deployment

The frontend is already aligned with a single-origin deployment model because:

- API calls are mostly relative-path fetches
- `frontend/shared/api/client.ts` sends `credentials: 'include'`
- `frontend/lib/module4Api.ts` targets `/module4/*` relative endpoints

This is a strong positive sign for unified packaging.

## Why The Recommended Approach Is Best

Three realistic architecture approaches were considered.

### Approach A: Merge Everything Into backend/app Immediately

Benefits:

- appears maximally unified
- reduces the number of backend folders on paper

Costs:

- highest migration risk
- likely to destabilize the working extraction and graph paths
- mixes framework unification with deep business-logic relocation
- likely to break artifact paths, job semantics, and packaging assumptions

Decision:

- rejected for the current project phase

### Approach B: Unified Gateway With Bounded Internal Engines

Benefits:

- preserves the current full workflow
- matches the real codebase state
- keeps packaging and single-entry goals achievable
- allows steady internal cleanup without forced rewrites
- gives the project a clean public architecture while respecting real engine boundaries

Costs:

- multiple backend directories remain for a while
- migration progress is less visually dramatic than a hard merge

Decision:

- approved

### Approach C: Keep The Mixed Legacy Structure With Minimal Cleanup

Benefits:

- lowest short-term disruption

Costs:

- architecture ambiguity remains
- packaging risk stays higher
- future maintenance and onboarding stay harder
- dead or unclear boundaries continue to accumulate

Decision:

- rejected as the long-term design

## Backend Architecture Model

The best fit for this project is not a literal textbook MVC split.
The best fit is a layered MVC-style backend architecture.

### MVC Mapping In This Project

- Controller: FastAPI routers
- Application Service: service and runtime orchestration
- Model: schemas, domain logic, parser logic, repositories, and storage
- View: frontend React pages and components

This is the right interpretation because the system is not a CRUD application.
It is a workflow-heavy system with:

- upload flows
- async jobs
- parsing pipelines
- multimodal enhancement
- evidence traces
- graph ingest
- rule execution
- explain and simulate behavior

That kind of system needs layered application services, not only three flat MVC buckets.

## Frontend Architecture Model

The frontend should remain `React + Vite`.

The preferred frontend structure is feature-based, not MVVM.

Why MVVM is not the best fit here:

- React already maps naturally to page containers and reusable components
- the app already has stable API, store, and session layers
- adding a ViewModel layer would likely duplicate state responsibilities
- the main challenge is workflow decomposition, not data-binding abstraction

The preferred frontend style is:

- page containers
- feature components
- shared components
- API clients
- local stores and session helpers

## Target Architecture Blueprint

```text
backend/
  app/                           # single public FastAPI gateway
    main.py
    create_app.py
    core/
      config.py
      deps.py
      env.py
      paths.py
      lifespan.py
      middleware.py
      exceptions.py
      health.py
    modules/
      auth/
      assistant/
      extraction/
        bridges/
        assistant1/
      gateway/
      frontend_static/
      module1_placeholder/

  auth/                          # compatibility proxy only
    server.cjs

  module2/                       # extraction engine
    app/
      main.py
      schemas.py
      runtime/
      core/
      assistant_1/
      agent/
      db/
      prompts/

  module4/                       # graph engine
    app/
      main.py
      schemas.py
      db/
      services/
    sql/

frontend/
  App.tsx
  pages/
  components/
  shared/api/
  lib/

scripts/
electron/
docs/
```

## Responsibility Boundaries

### backend/app

`backend/app` owns:

- the only public backend entry
- auth core
- platform assistant entry
- extraction API contracts
- Module 2 sidecar and upstream coordination
- Module 4 proxying
- gateway readiness and health
- packaged frontend static serving
- Electron-facing backend startup semantics

`backend/app` should not become the place where all parser and graph internals are dumped.

### backend/auth

`backend/auth` owns:

- compatibility only
- forwarding of historical auth routes
- forwarding of historical chat routes

It should not receive new primary business logic.

### backend/module2

`backend/module2` owns:

- file upload materialization
- extraction jobs
- DOC and DOCX preview conversion
- PDF parsing
- MinerU and visual extraction chain
- OCR and image flows
- structured field extraction
- trace hits
- assistant1 grounding and retrieval
- Module 4 sync outbox behavior
- extraction persistence and cache

It should not own:

- platform login
- frontend static serving
- Module 4 graph querying

### backend/module4

`backend/module4` owns:

- graph ingest from Module 2 documents
- graph file and graph version state
- alerts, rules, evidence
- explain and simulate operations
- graph query surfaces
- GraphRAG capability services
- Neo4j projection capability services

It should not own:

- raw file upload parsing
- Office preview
- platform auth

## Real Workflow Preservation Requirements

The migration is only acceptable if these workflow guarantees remain true.

### Auth

- login, register, logout, and current-user flows remain stable
- cookie semantics remain stable
- auth data remains migratable between legacy and managed storage

### Module 2 Upload And Parsing

- frontend still uploads through the unified FastAPI entry
- extraction jobs still support create and poll behavior
- document outputs still return stable document payloads

### DOCX Preview And PDF Path

- DOC or DOCX preview still converts to PDF asynchronously
- the PDF preview artifact remains reachable through stable artifact URLs
- DOCX parsing still feeds the intended PDF-centered quality path where required

### Parsing And Trace

- trace hits remain available
- trace artifact URLs remain resolvable
- summarize and trace-locate contracts remain stable

### Assistant1

- assistant1 remains grounded on extraction artifacts and document context
- streaming behavior remains available through the unified API

### Module 2 To Module 4 Sync

- Module 2 can still sync parsed document payloads to Module 4
- Module 4 still treats `documents` as the primary ingest contract

### Module 4 Querying

- file graph view remains available
- node detail remains available
- neighborhood remains available
- alerts and rules remain available
- explain and simulate remain available

## Packaging And Runtime Boundaries

The packaged application should include runtime code, not runtime junk.

### Must Be Packaged

- `backend/app/**`
- `backend/app/modules/extraction/module2_compat_worker.py`
- `backend/module2/app/**`
- `backend/module4/app/**`
- `backend/auth/server.cjs`
- `frontend/dist/**`
- required `scripts/**/*.cjs`
- Electron runtime files

### Must Not Be Packaged

- `backend/module2/artifacts/**`
- `module2/artifacts/**`
- `backend/module4/workspaces/**`
- `module2/runlogs/**`
- `.pytest_cache/**`
- `.runlogs/**`
- `.codex-temp/**`
- `backend/tests/**`
- `backend/module2/tests/**`
- `backend/module4/tests/**`
- `frontend/e2e/**`
- `backend/module2/tools/**`
- historical package outputs such as `dist-electron/**` and `dist-electron-final/**`

### Important Packaging Principle

Runtime-generated data must be written to a writable runtime-data directory, not baked into packaged app resources.

## Source Categories

To avoid future confusion, source and non-source content should be discussed using these categories.

### Category A: Real Production Mainline Source

- `backend/app/**`
- `backend/app/modules/extraction/module2_compat_worker.py`
- `backend/module2/app/**`
- `backend/module4/app/**`
- `frontend/App.tsx`
- `frontend/components/DeepReadWorkbench.tsx`
- `frontend/components/knowledge-nexus/KnowledgeNexusNeo4j.tsx`
- `frontend/components/AuthModal.tsx`
- `frontend/components/AIAssistant.tsx`
- `frontend/shared/api/**`
- `frontend/lib/**`
- `scripts/start-*.cjs`
- `electron/main.cjs`

### Category B: Compatibility Layer Still In Use

- `backend/auth/server.cjs`
- `backend/app/modules/extraction/module2_execution_facade.py`
- `backend/app/modules/extraction/module2_compat_worker.py`

### Category C: Capability Layer Not Yet The Current Business Mainline

- `backend/module4/app/services/graphrag_workspace.py`
- `backend/module4/app/services/graphrag_indexer.py`
- `backend/module4/app/services/graphrag_artifact_importer.py`
- `backend/module4/app/services/graphrag_artifact_validator.py`
- `backend/module4/app/services/neo4j_graph.py`
- `backend/module4/app/services/oneapi_runtime.py`
- `backend/module4/app/services/prompt_registry.py`

### Category D: Present But Not On The Current Frontend Mainline

- `frontend/components/DocInteractionWorkbench.tsx`
- `frontend/components/Module2InlineAssistant.tsx`

### Category E: Retired Or Non-Mainline Development Assets

- `backend/ai-assistant/**`
- test directories
- E2E scripts
- benchmark and eval tools
- historical outputs

## Migration Principles

Every future refactor should follow these rules.

### 1. Preserve External Contracts First

Do not break:

- `/api/*`
- `/extract/*`
- `/module4/*`

unless there is a carefully managed compatibility plan.

### 2. Preserve Artifact Semantics

Do not silently break:

- `artifact_path`
- `artifact_url`
- office preview artifacts
- trace artifact references

### 3. Preserve Job Semantics

The create and poll extraction model must remain stable.

### 4. Move Logic By Layer, Not By Emotion

Only move code when its responsibility boundary becomes clearer after the move.

### 5. Bridges May Stay Until Risk Is Gone

Compatibility and bridge files should not be deleted just because a newer path exists.
They should be removed only when:

- callers are gone
- packaging is proven
- regressions are covered

### 6. Runtime Junk Must Never Be Treated As Source

Artifacts, workspaces, logs, and packaged outputs are not migration targets.

## Preferred Frontend Refactor Shape

The frontend should evolve toward a feature-oriented structure.

Example target shape:

```text
frontend/
  pages/
    deepread/
      DeepReadPage.tsx
      hooks/
      components/
    nexus/
      KnowledgeNexusPage.tsx
      hooks/
      components/
  components/
    shared/
  shared/
    api/
  lib/
```

This is intended as a gradual direction, not a forced one-shot rewrite.

## Preferred Module 2 Refactor Shape

Module 2 should keep shrinking `app/main.py` by moving stable logic into:

- `runtime/` for request and job orchestration
- `core/` for parser and domain capability logic
- `assistant_1/` for grounded assistant behavior
- `db/` for persistence

The goal is to make `main.py` eventually mostly:

- runtime construction
- dependency wiring
- route registration

without changing the working parser mainline prematurely.

## Preferred Module 4 Refactor Shape

Module 4 should move toward:

- thinner `app/main.py`
- clearer separation between API entrypoints and ingest application logic
- continued storage stability
- capability services that are explicitly marked as current-mainline or not-yet-mainline

The current `documents -> graph ingest` mainline should remain authoritative until a richer GraphRAG execution path is proven in production.

## Phased Execution Plan

### Phase A: Lock The Unified Entry

- keep `backend/app` as the only public backend entry
- keep Electron startup centered on the FastAPI-first path
- keep single-origin frontend behavior stable

### Phase B: Continue Internal Module 2 Decomposition

- keep splitting `backend/module2/app/main.py`
- continue extracting pure rule blocks from `parser.py`
- keep function behavior identical while improving locality and testability

### Phase C: Continue Internal Module 4 Decomposition

- split `backend/module4/app/main.py` into thinner API and application boundaries
- keep current graph ingest contract stable
- avoid forcing GraphRAG service files into the main ingest loop before that path is proven

### Phase D: Frontend Feature Decomposition

- split `DeepReadWorkbench.tsx`
- split `KnowledgeNexusNeo4j.tsx`
- keep API and store contracts stable while reducing giant-component complexity

### Phase E: Compatibility Retirement

- retire `backend/auth/server.cjs` only after all historical callers are gone
- retire bridge layers only after packaging and regression confidence are strong

## Acceptance Criteria

This architecture direction should be considered successful when all of the following are true:

- the packaged app starts from a single backend entry
- auth remains complete and reliable
- Module 2 upload, preview, parse, trace, and assistant1 flows remain complete
- Module 4 graph and risk flows remain complete
- no runtime artifact directories are packaged as source content
- the codebase has a clear boundary between gateway, engine, compatibility, and runtime-output layers

## Final Recommendation

For the current project state, the best architecture choice is:

`FastAPI unified gateway + bounded Module 2 and Module 4 engines + React frontend preserved + compatibility bridges retained until migration risk is genuinely removed.`

This is the most complete, lowest-risk, and most packaging-ready path available without sacrificing the current full workflow.
