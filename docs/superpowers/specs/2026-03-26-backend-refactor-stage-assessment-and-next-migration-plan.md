# Backend Refactor Stage Assessment And Next Migration Plan

Date: 2026-03-26

## Summary

This spec records the current backend refactor stage for Smart Doc Flow and defines the recommended next migration operations.

It builds on:

- `docs/superpowers/specs/2026-03-26-fastapi-unified-architecture-and-migration-design.md`

The key conclusion is:

`The project has already completed unified public backend entry establishment and is now in the middle stage of internal engine decomposition. The correct next step is not a hard physical merge into backend/app, but a staged, workflow-preserving decomposition of Module 2 and Module 4 internals.`

This document answers four questions:

1. what stage the backend refactor has actually reached
2. whether the current migrated files have damaged the full workflow
3. what remains unmigrated or only partially migrated
4. what the next safe migration operations should be

## Why This Spec Exists

The current repository already reflects substantial restructuring:

- a unified FastAPI gateway exists
- auth core has moved into FastAPI
- frontend and Electron now prefer the unified gateway path
- Module 2 has started a meaningful runtime and core decomposition
- Module 4 already has a clearer capability-layer split

However, the existence of many moved files does not automatically mean that the project has reached full migration closure.

The real issue is not:

- "have files moved?"

The real issue is:

- "has architecture responsibility become clearer without breaking the workflow?"

This spec therefore focuses on stage truth, not cosmetic progress.

## Current Refactor Stage

The backend refactor is best understood as a six-stage program.

### Stage 1: Single Public Backend Entry

Status:

- completed

Evidence:

- `backend/app/create_app.py`
- `backend/app/main.py`
- `backend/app/modules/gateway/router.py`
- `scripts/start-backend-fastapi.cjs`
- `electron/main.cjs`

Meaning:

- the project now has a real unified FastAPI shell
- Electron and gateway readiness already align to a single public backend entry
- the frontend can treat the backend as a same-origin platform surface

### Stage 2: Auth Framework Unification

Status:

- substantially completed

Evidence:

- FastAPI auth core in `backend/app/modules/auth/*`
- compatibility proxy in `backend/auth/server.cjs`
- auth repository storage migration behavior in `backend/app/modules/auth/repository.py`
- auth storage preference in `backend/app/modules/auth/config.py`

Meaning:

- the authoritative auth business logic is already in FastAPI
- the Node auth process is now a compatibility bridge, not the domain authority
- auth should no longer be redesigned as a separate framework line

### Stage 3: Unified Extraction API Surface

Status:

- substantially completed

Evidence:

- `backend/app/modules/extraction/router.py`
- `backend/app/modules/extraction/service.py`
- `backend/app/modules/extraction/module2_execution_facade.py`
- `backend/app/modules/extraction/module2_compat_worker.py`

Meaning:

- public extraction entrypoints are now unified
- the gateway can coordinate Module 2 through sidecar, upstream, or subprocess bridge modes
- frontend callers no longer need to know internal backend topology

### Stage 4: Module 2 Internal Decomposition

Status:

- in progress
- currently in the middle stage

Evidence:

- `backend/module2/app/runtime/extraction_requests.py`
- `backend/module2/app/runtime/extraction_jobs.py`
- `backend/module2/app/runtime/extraction_executor.py`
- `backend/module2/app/runtime/office_preview.py`
- `backend/module2/app/runtime/document_tools.py`
- `backend/module2/app/core/*_runtime.py`
- `backend/module2/app/main.py` now importing and wiring those split units

Meaning:

- Module 2 is no longer a pure giant-main-file architecture
- request entry logic, job state logic, executor logic, office preview logic, and document tools logic are already being extracted into focused units
- the refactor is real and meaningful
- but the main parsing and orchestration heart is still concentrated in `backend/module2/app/main.py` and `backend/module2/app/core/parser.py`

### Stage 5: Module 4 Internal Decomposition

Status:

- early stage

Evidence:

- `backend/module4/app/services/*` exists as a clear capability layer
- `backend/module4/app/main.py` still contains current ingest and orchestration mainline
- `backend/module4/app/db/storage.py` remains the main graph persistence center

Meaning:

- Module 4 has started boundary formation
- but the current graph ingest path is still heavily centered in `app/main.py`
- this area needs the next major wave of cleanup after Module 2 decomposition continues

### Stage 6: Compatibility Retirements And Packaging Closure

Status:

- partial

Evidence:

- Electron already prefers FastAPI-first startup
- `electron-builder.json` already excludes major runtime artifact classes
- compatibility layers still exist and are still needed

Meaning:

- packaging direction is correct
- runtime junk boundaries are clearer than before
- but compatibility bridges should not be retired yet

## Stage Assessment In Plain Language

The project is no longer in an "architecture idea" phase.
It is also not yet in a "fully migrated clean final architecture" phase.

It is in this state:

- the public architecture is unified
- the internal engines are still real and active
- Module 2 is being decomposed internally
- Module 4 has only begun that decomposition
- compatibility and packaging boundaries still need operational cleanup

The most accurate label is:

`Unified gateway established, internal engine decomposition in progress.`

## Workflow Integrity Assessment

This section evaluates whether the already migrated files appear to have damaged the full workflow.

## Conclusion

Current evidence does **not** show that the refactor has broken the main workflow contracts.

The project still preserves the following critical lines:

- auth
- unified chat
- extraction entrypoints
- Module 2 execution
- assistant1 streaming
- Module 2 to Module 4 sync
- Module 4 graph APIs
- Electron startup through unified readiness

This conclusion is based on three kinds of evidence:

- routing continuity
- code wiring continuity
- targeted test continuity

### 1. Routing Continuity

The expected routes still exist in their proper places:

- auth in `backend/app/modules/auth/router.py`
- assistant in `backend/app/modules/assistant/router.py`
- extraction in `backend/app/modules/extraction/router.py`
- legacy auth and legacy chat compatibility in `backend/auth/server.cjs`
- Module 2 extraction endpoints in `backend/module2/app/main.py`
- Module 4 graph endpoints in `backend/module4/app/main.py`

This means external contracts have not been silently severed.

### 2. Code Wiring Continuity

The current migrated Module 2 structure still wires the business engine together from the main entry:

- `ExtractionRequestRuntime`
- `ExtractionJobRuntime`
- `ExtractionJobExecutor`
- `OfficePreviewRuntime`
- `DocumentToolsRuntime`
- `Module2ArtifactFileRuntime`
- `Module2HealthRuntime`
- `ExtractionGraph`

This is a strong sign that refactoring has mostly been a transfer of responsibilities rather than a removal of responsibilities.

### 3. Targeted Test Continuity

The following test groups were executed successfully during assessment:

- `backend/tests/test_create_app_routes.py`
- `backend/tests/test_extraction_router.py`
- `backend/tests/test_extraction_service.py`
- `backend/tests/test_assistant_router.py`
- `backend/tests/test_assistant_service.py`
- `backend/tests/test_auth_repository.py`
- `backend/module4/tests/test_module4_api.py` when executed from the `backend/module4` working directory

This confirms:

- unified FastAPI route registration is functioning
- extraction gateway behavior still matches expectation
- assistant routes and services are still intact
- auth repository and storage resolution are still intact
- Module 4 API logic still passes its existing test suite in its expected execution context

## Important Qualification

This is **not** the same as saying that the full real-user workflow has reached final acceptance closure.

The following still require continued operational validation:

- real frontend upload runs
- DOCX asynchronous preview conversion to PDF
- PDF parse chain continuity
- MinerU artifact production
- Gemini enhancement continuity
- assistant1 grounded chat on live artifacts
- Module 2 to Module 4 downstream sync through real runs
- frontend graph linkage using current file hash and workbench state

Therefore the correct statement is:

`No current evidence shows that the refactor has broken the workflow, but full workflow closure still depends on continued staged regression verification.`

## What Has Been Successfully Migrated Already

The following backend architecture shifts can now be treated as real migration progress rather than proposals.

### A. Public Framework Unification

- FastAPI is now the real backend authority
- `backend/app` is the real public entry
- Electron startup aligns to the FastAPI-first path

### B. Auth Core Migration

- auth business logic has moved into FastAPI
- auth compatibility has been reduced to a transitional proxy role

### C. Unified Extraction Surface

- extraction routes now present a single public contract
- Module 2 execution is behind gateway coordination

### D. Module 2 Internal Runtime Split

- request logic has a runtime unit
- job logic has a runtime unit
- executor logic has a runtime unit
- office preview logic has a runtime unit
- document tool logic has a runtime unit

### E. Packaging Direction

- packaging already excludes major runtime output directories
- packaged startup already leans toward unified backend entry

## What Has Not Been Fully Migrated Yet

This section is critical because "already refactored" and "fully migrated" are not the same thing.

### 1. Module 2 Main Parsing Core

Still not fully migrated:

- `backend/module2/app/core/parser.py`

Why:

- it still contains major parsing orchestration and rule-heavy logic
- many helper blocks are still concentrated there
- it is still the true parsing dispatch center

### 2. Module 2 Main Entry Concentration

Still not fully migrated:

- `backend/module2/app/main.py`

Why:

- it still owns too much orchestration and glue logic
- it still carries top-level helper concentration that should continue moving into `runtime/` or `core/`

### 3. Module 4 Application Orchestration

Still not fully migrated:

- `backend/module4/app/main.py`

Why:

- ingest and rebuild orchestration are still concentrated there
- application-level graph processing is still strongly embedded in the API entry file

### 4. Testing Execution Normalization

Still not fully migrated:

- project-wide pytest execution semantics

Why:

- Module 4 test execution still depends on working-directory assumptions
- the backend is not yet fully normalized for root-level test invocation symmetry across all backend slices

### 5. Compatibility Retirement

Still not migrated:

- removal of `backend/auth/server.cjs`
- removal of the remaining legacy Module 2 sidecar/runtime hard dependencies

Why:

- those still carry real operational stability responsibilities

## Migration Risk Assessment

### Low-Risk Ongoing Migration Areas

These are appropriate next refactor targets because they are mostly internal and can be validated incrementally:

- pure parsing helper extraction from `parser.py`
- helper and glue extraction from `backend/module2/app/main.py`
- Module 4 orchestration extraction from `backend/module4/app/main.py`
- frontend giant-component decomposition without API contract changes

### Medium-Risk Areas

- assistant1 internal provider and context behavior
- office preview storage and artifact path handling
- Module 2 to Module 4 sync behavior

These should be changed only with regression coverage close at hand.

### High-Risk Areas

- changing public route contracts
- changing artifact path or artifact URL semantics
- changing job state semantics
- deleting compatibility bridges too early
- forcing all engine logic into `backend/app`

These are currently the wrong targets for aggressive migration.

## Recommended Next Migration Strategy

The correct next strategy is:

`freeze the public contracts, continue engine-internal decomposition, strengthen regression confidence, and delay compatibility retirements until the workflow is operationally boring.`

This strategy breaks into five concrete workstreams.

## Workstream 1: Freeze Public Contracts

### Objective

Protect the current full workflow while internal migration continues.

### Freeze Boundaries

Do not change unless correctness absolutely requires it:

- `/api/*`
- `/extract/*`
- `/module4/*`
- auth cookie and session semantics
- extraction job create and poll semantics
- artifact path and artifact URL semantics
- Module 2 to Module 4 documents payload contract

### Acceptance Criteria

- frontend callers do not need to adapt during current backend decomposition
- Electron startup remains unchanged

## Workstream 2: Continue Module 2 Decomposition

### Objective

Turn Module 2 into a clearer layered engine without changing its workflow.

### Primary Target

- `backend/module2/app/core/parser.py`

### Best Next Extraction Candidates

- table merge rules
- figure matching rules
- figure title and caption recovery
- figure dataframe coercion and normalization
- trace text cleanup and low-signal filtering
- other small pure-rule helper blocks

### Preferred Landing Zones

- `backend/module2/app/core/table_merge_runtime.py`
- `backend/module2/app/core/figure_matching_runtime.py`
- `backend/module2/app/core/figure_text_runtime.py`
- `backend/module2/app/core/figure_semantics.py`

### Secondary Target

- `backend/module2/app/main.py`

### Best Next Main.py Extractions

- artifact helper logic
- trace artifact helper logic
- summarize and trace bridge glue
- office preview glue logic
- health aggregation glue
- Module 4 sync API-side helper glue

### Acceptance Criteria

- `parser.py` becomes more like a coordinator and less like a giant mixed rule container
- `main.py` becomes more like a composition root and less like a business logic file
- existing backend tests continue to pass

## Workstream 3: Start Real Module 4 Mainline Decomposition

### Objective

Reduce concentration in `backend/module4/app/main.py` without destabilizing the current graph path.

### Primary Target

- `backend/module4/app/main.py`

### Best First Extractions

- ingest job orchestration
- rebuild job orchestration
- graph file and graph version assignment orchestration
- explain and simulate orchestration
- per-document processing coordinator wrappers around `_process_document`

### Important Constraint

Do not prioritize deep GraphRAG service rewrites before current ingest orchestration has cleaner boundaries.

### Acceptance Criteria

- `app/main.py` becomes thinner
- graph ingest behavior remains unchanged
- Module 4 API tests remain green

## Workstream 4: Normalize Test Execution Semantics

### Objective

Make backend verification less dependent on manual path assumptions.

### Tasks

- normalize root-level pytest execution for Module 4
- make import resolution explicit across backend slices
- preserve independent backend-slice testability
- define smoke suites for:
  - unified gateway
  - Module 2 engine
  - Module 4 graph engine

### Acceptance Criteria

- root-level and module-local test execution rules are explicit and repeatable
- migration work no longer depends on accidental working-directory context

## Workstream 5: Delay Compatibility Retirement

### Objective

Keep the system boring and stable while the main engines are still being decomposed.

### Files To Preserve For Now

- `backend/auth/server.cjs`
- `backend/app/modules/extraction/module2_compat_worker.py`

### Rule

These may only be retired after:

- callers are gone
- packaging is stable
- regression evidence is strong
- no mainline workflows still depend on them

## Files That Should Not Be The Focus Of The Next Migration Wave

These may remain in place for now.

### Frontend Non-Mainline Files

- `frontend/components/DocInteractionWorkbench.tsx`
- `frontend/components/Module2InlineAssistant.tsx`

### Module 4 Capability Layer

- `backend/module4/app/services/graphrag_workspace.py`
- `backend/module4/app/services/graphrag_indexer.py`
- `backend/module4/app/services/graphrag_artifact_importer.py`
- `backend/module4/app/services/graphrag_artifact_validator.py`
- `backend/module4/app/services/neo4j_graph.py`
- `backend/module4/app/services/oneapi_runtime.py`
- `backend/module4/app/services/prompt_registry.py`

These are important, but they are not the highest-value next migration targets for workflow safety.

## Packaging And Repository Hygiene Actions

The following classes of content should continue to be treated as non-source runtime material:

- `backend/module2/artifacts/**`
- `module2/artifacts/**`
- `backend/module4/workspaces/**`
- `module2/runlogs/**`
- `.pytest_cache/**`
- `.runlogs/**`
- `.codex-temp/**`
- `backend/tests/**` for packaging purposes
- `backend/module2/tests/**` for packaging purposes
- `backend/module4/tests/**` for packaging purposes
- `frontend/e2e/**`
- `backend/module2/tools/**`
- `dist-electron/**`
- `dist-electron-final/**`

These should remain in the repository only when useful for development, not as package payload.

## Recommended Next Operations

The next migration operations should be executed in this order:

1. freeze and protect current public contracts
2. continue extracting pure rule and helper logic from `backend/module2/app/core/parser.py`
3. continue reducing glue concentration in `backend/module2/app/main.py`
4. begin extracting orchestration from `backend/module4/app/main.py`
5. normalize backend test execution semantics
6. postpone compatibility retirement until after those steps are stable

## Immediate Next Slice Recommendation

If a single next slice must be chosen now, the best choice is:

`Continue the small-step extraction of remaining pure rule blocks from backend/module2/app/core/parser.py, then immediately follow with another pass to reduce non-entry glue in backend/module2/app/main.py.`

This is the safest next move because:

- it preserves the public workflow
- it continues the existing decomposition direction
- it reduces complexity in the highest-risk oversized files
- it keeps the engine boundary stable while improving maintainability

## Final Judgment

The backend refactor has already moved beyond architecture setup and is now in real internal migration territory.

The current state should be understood as:

`public architecture unified, Module 2 decomposition underway, Module 4 decomposition beginning, workflow still preserved, compatibility still required, packaging direction correct but not fully closed.`

That means the project is in a good state to continue migration, but only if the next steps remain:

- incremental
- boundary-aware
- regression-protected
- workflow-first

The right target now is not architectural purity.
The right target is controlled convergence without losing the working product path.

## 2026-03-27 Module 2 Parser Progress Update

This section records the additional migration progress completed after the original 2026-03-26 assessment.

### What Has Changed

`backend/module2/app/core/parser.py` has continued to move from a mixed "rules + wiring + orchestration" file toward a thinner composition root.
`backend/module2/app/main.py` has also started its next glue-reduction wave at the top-level runtime-singleton layer.

The following parser-owned wiring layers have now been extracted into dedicated bundle runtimes:

- `parser_config_runtime.py`
- `parser_dependency_bundle_runtime.py`
- `parser_document_table_bundle_runtime.py`
- `parser_table_helper_bundle_runtime.py`
- `parser_ocr_table_inference_bundle_runtime.py`
- `parser_provider_bundle_runtime.py`
- `parser_provider_state_runtime.py`
- `parser_vision_bundle_runtime.py`
- `parser_visual_payload_bundle_runtime.py`
- `parser_image_bundle_runtime.py`
- `parser_dispatch_bundle_runtime.py`
- `parser_docx_content_bundle_runtime.py`
- `parser_visual_context_bundle_runtime.py`
- `parser_visual_execution_bundle_runtime.py`
- `parser_semantic_foundation_bundle_runtime.py`
- `parser_run_state_runtime.py`

The following `main.py`-level bundle entries have now also been introduced:

- `app/runtime/main_support_bundle.py`
- `app/runtime/main_extraction_bundle.py`
- `app/runtime/main_policy_bundle.py`
- `app/runtime/main_progress_bundle.py`
- `app/runtime/main_platform_bundle.py`
- `app/runtime/main_geometry_bundle.py`
- `app/runtime/main_nonpdf_bundle.py`
- `app/runtime/main_workflow_bundle.py`
- `app/runtime/main_service_bundle.py`
- `app/runtime/main_entry_bundle.py`

### Current Meaning

The parser migration is no longer just a high-level intent.

It now has a stable decomposition pattern:

- parser-owned configuration is externalized
- parser-owned provider kwargs and provider caches are externalized
- parser-owned image, dispatch, docx, vision, visual payload, visual context, and visual execution wiring are externalized
- parser-owned run state is externalized
- parser still owns orchestration order and the remaining parsing rules, but much less raw constructor noise remains in the file

In practical terms:

`parser.py` is now primarily a staged initializer plus workflow coordinator, not a giant constructor-and-helpers blob.

And:

`main.py` has started moving away from a flat top-level list of runtime singleton instantiations toward explicit bundle-based assembly.

More concretely, `main.py` now has a clearer staged assembly pattern:

- support/runtime singleton assembly through `main_support_bundle.py`
- extraction execution context assembly through `main_extraction_bundle.py`
- path, environment, and policy assembly through `main_policy_bundle.py`
- progress, heartbeat, and ramp assembly through `main_progress_bundle.py`
- CORS, bounded-env, and process-pool/bootstrap assembly through `main_platform_bundle.py`
- bbox/geometry helper assembly through `main_geometry_bundle.py`
- nonpdf preflight, budget, and warning/diagnostics helper assembly through `main_nonpdf_bundle.py`
- document workflow assembly through `main_workflow_bundle.py`
- active service/support singleton assembly through `main_service_bundle.py`
- app callback and router-edge assembly through `main_entry_bundle.py`
- request/job/tool HTTP assembly through `http_runtime_bundle.py`

### Workflow Safety Qualification

These extractions were regression-validated against the current workflow-preserving suites:

- parser bundle unit tests
- `backend/tests/test_module2_main_support_bundle.py`
- `backend/tests/test_module2_main_extraction_bundle.py`
- `backend/tests/test_module2_main_policy_bundle.py`
- `backend/tests/test_module2_main_progress_bundle.py`
- `backend/tests/test_module2_main_platform_bundle.py`
- `backend/tests/test_module2_main_geometry_bundle.py`
- `backend/tests/test_module2_main_nonpdf_bundle.py`
- `backend/tests/test_module2_main_workflow_bundle.py`
- `backend/tests/test_module2_main_service_bundle.py`
- `backend/tests/test_module2_main_entry_bundle.py`
- `backend/module2/tests/test_parse_document_in_subprocess.py`
- the broader `backend/tests/test_module2_*` matrix
- FastAPI/auth/extraction route and service regression tests

No evidence from this migration wave indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Remaining High-Value Work

At this point, continuing to split tiny constructor calls one by one is no longer the highest-value migration activity.

The next useful work should focus on:

- continuing to reduce remaining glue concentration in `backend/module2/app/main.py`
- evaluating whether `parser.py` should stop after its current thin-composition stage instead of being fragmented further for low-value gains
- beginning a similar decomposition pass for `backend/module4/app/main.py`

Within `main.py`, the most suitable next safe slice is now:

- continuing to peel off the remaining result-quality / visual-contract helper glue that still sits directly in the entry file, while preserving current route contracts and artifact semantics

One related cleanup was also validated in this wave:

- `app/routes/router_bundle.py` now supports both unified-backend and direct-module import contexts, which reduces one of the existing test-entry fragility points without changing route behavior

Another important clarification from this wave is:

- `main_extraction_bundle.py` now owns the extraction execution context glue that used to sit directly in `main.py`, including runtime fingerprinting, cache-version composition, stream-router construction, extraction concurrency semaphores, and parse-slot coordination
- `main_policy_bundle.py` now owns the path, environment, and policy glue that used to sit directly in `main.py`, including artifact-root resolution, extraction job state root resolution, office/visual toggle policies, provider preflight construction, and related entry-time configuration helpers
- `main_progress_bundle.py` now owns the progress-control glue that used to sit directly in `main.py`, including heartbeat progression, parse/extract ramp heuristics, and the shared progress wrapper used across the document pipeline
- `main_platform_bundle.py` now owns the platform-level glue that used to sit directly in `main.py`, including CORS origin resolution, bounded env parsing, process-pool lifecycle wiring, and bootstrap/runtime pool integration
- `main_geometry_bundle.py` now owns the bbox/geometry glue that used to sit directly in `main.py`, including bbox normalization, page extraction, and meaningful-bbox filtering for downstream trace and quick-fallback helpers
- `main_nonpdf_bundle.py` now owns the nonpdf helper glue that used to sit directly in `main.py`, including text decoding fallback, nonpdf preflight profiling, budget resolution, soft-warning normalization, recovered-warning stripping, and visual diagnostics promotion

### Updated Practical Judgment

The Module 2 parser is now in a late-middle migration stage:

- not fully finished
- no longer thickly entangled at the wiring layer
- still preserving the live workflow
- now ready for more selective, higher-value cleanup rather than indiscriminate micro-splitting

The Module 2 main entry is also now in a clear middle-stage decomposition state:

- top-level support singletons are externalized
- extraction execution context is externalized
- path, environment, and policy assembly is externalized
- progress, heartbeat, and ramp assembly is externalized
- platform/bootstrap/process-pool assembly is externalized
- bbox/geometry helper assembly is externalized
- nonpdf helper assembly is externalized
- workflow assembly is externalized
- active service/support singleton assembly is externalized
- app callback and router-edge assembly is externalized
- HTTP/runtime job assembly is externalized
- but remaining result-quality / visual-contract helper glue still need another careful pass

## 2026-03-27 Increment: Quality And Visual Contract Extraction

The next migration slice described above has now been executed.

This wave extracted the remaining low-risk quality and visual-contract helper glue from `backend/module2/app/main.py` into:

- `backend/module2/app/runtime/main_quality_bundle.py`

This new bundle now owns the following previously inlined entry-file responsibilities:

- table cell counting
- figure dataframe cell counting
- meaningful-value detection
- result quality snapshot calculation
- table quality averaging
- table source distribution counting
- figure source distribution counting
- figure page collection
- gemini-source presence checks
- visual chain contract construction

The Module 2 main entry continues to preserve the existing workflow, but now consumes those helpers through bundle wiring instead of directly defining them inline.

### Regression Validation For This Increment

The following validation passed after the extraction:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_quality_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_quality_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_quality_bundle.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- broader regression: `backend/tests/test_module2_*`
- unified backend regression:
  - `backend/tests/test_create_app_routes.py`
  - `backend/tests/test_extraction_service.py`
  - `backend/tests/test_extraction_router.py`
  - `backend/tests/test_assistant_router.py`
  - `backend/tests/test_auth_repository.py`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

The next safe migration target inside `backend/module2/app/main.py` is no longer the extracted quality/visual-contract helper layer.

The next highest-value low-risk slice is now:

- remaining schema auto-inference and semantic-closure glue that can be isolated without changing the live extraction rules
- only after that, any still-residual quick-table fallback helper glue that is purely compositional

The migration principle remains unchanged:

- keep the full workflow intact
- move responsibilities rather than rewriting them
- prefer small bundle extraction plus regression proof over large one-shot relocation

## 2026-03-27 Increment: Quick Table Fallback Extraction

After the quality and visual-contract helper extraction stabilized, the next low-risk rules-only slice was also migrated.

This wave extracted the quick-table fallback helper glue from `backend/module2/app/main.py` into:

- `backend/module2/app/runtime/main_quick_extract_bundle.py`

This new bundle now owns:

- numeric coercion for quick fallback matching
- field-hint tokenization for table lookup
- quick extraction from table cell/header matches

The main entry now consumes that behavior through bundle wiring, while the original fallback logic and downstream workflow order remain unchanged.

### Regression Validation For This Increment

The following validation passed after the extraction:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_quick_extract_bundle.py backend/module2/app/runtime/main_quality_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_quick_extract_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_quality_bundle.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- broader regression: `backend/tests/test_module2_*`
- unified backend regression:
  - `backend/tests/test_create_app_routes.py`
  - `backend/tests/test_extraction_service.py`
  - `backend/tests/test_extraction_router.py`
  - `backend/tests/test_assistant_router.py`
  - `backend/tests/test_auth_repository.py`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After the quick-table helper extraction, the highest-value remaining `main.py` work is now concentrated in the more semantics-heavy rule layer.

The next migration should therefore stay conservative and focus on:

- small schema auto-inference helper clusters that can be moved as pure rule bundles
- semantic-closure / low-value filtering glue only when it can be proven by regression

The migration should continue to avoid:

- rewriting live extraction rules during relocation
- mixing structural migration with business-logic redesign

## 2026-03-27 Increment: Result Filter Extraction

The next rules-only postprocess slice has also now been migrated out of `backend/module2/app/main.py`.

This wave extracted the low-value result filtering helper glue into:

- `backend/module2/app/runtime/main_result_filter_bundle.py`

This new bundle now owns:

- semantic text normalization for result-value comparison
- low-value result-value detection
- auto-result filtering
- shadowed auto-result pruning
- effective quality schema field adjustment after auto-result filtering

This extraction keeps the filtering rules intact while reducing the amount of postprocess rule glue embedded directly inside the Module 2 main entry.

### Regression Validation For This Increment

The following validation passed after the extraction:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_result_filter_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_result_filter_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_result_filter_bundle.py backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- broader regression: `backend/tests/test_module2_*`
- unified backend regression:
  - `backend/tests/test_create_app_routes.py`
  - `backend/tests/test_extraction_service.py`
  - `backend/tests/test_extraction_router.py`
  - `backend/tests/test_assistant_router.py`
  - `backend/tests/test_auth_repository.py`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After the result-filter extraction, the next most suitable `main.py` migration target is the schema-rule layer that still mixes:

- schema field normalization
- semantic label strength scoring
- conservative semantic closure
- canonical field selection

That next wave should still remain conservative:

- extract pure rule helpers first
- avoid altering the live selection thresholds during relocation
- keep the existing workflow and test matrix as the release gate

## 2026-03-27 Increment: Schema Field Normalization Extraction

The schema field normalization and pruning helper layer has now also been migrated out of `backend/module2/app/main.py`.

This wave extracted the schema-name normalization helper glue into:

- `backend/module2/app/runtime/main_schema_fields_bundle.py`

This new bundle now owns:

- schema field tokenization
- schema field dedup-key generation
- schema field sort-key comparison
- low-value auto-schema field-name detection
- schema field candidate upsert and type merge
- shadowed auto-schema field pruning
- filtered auto-schema field normalization
- request-schema field normalization

The Module 2 main entry now consumes those schema-field rules through bundle wiring, while preserving the existing selection thresholds and downstream schema contracts.

### Regression Validation For This Increment

The following validation passed after the extraction:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_schema_fields_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_schema_fields_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_schema_fields_bundle.py backend/tests/test_module2_main_result_filter_bundle.py backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_quality_bundle.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_post_parse_quality_runtime.py -q`
- broader regression: `backend/tests/test_module2_*`
- unified backend regression:
  - `backend/tests/test_create_app_routes.py`
  - `backend/tests/test_extraction_service.py`
  - `backend/tests/test_extraction_router.py`
  - `backend/tests/test_assistant_router.py`
  - `backend/tests/test_auth_repository.py`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Schema Request Parsing Extraction

The schema request parsing helper layer has also been migrated out of `backend/module2/app/main.py`.

This wave extracted the request-schema parsing helper glue into:

- `backend/module2/app/runtime/main_schema_request_bundle.py`

This new bundle now owns:

- mojibake repair for schema-form payloads
- schema payload scoring
- schema-form JSON parsing and validation

This keeps the public schema-form handling behavior intact while removing another isolated pure-helper block from the entry file.

### Regression Validation For This Increment

The following validation passed after the extraction:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_schema_fields_bundle.py backend/module2/app/runtime/main_schema_request_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_schema_fields_bundle.py backend/tests/test_module2_main_schema_request_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_schema_fields_bundle.py backend/tests/test_module2_main_schema_request_bundle.py backend/tests/test_module2_main_result_filter_bundle.py backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_quality_bundle.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_post_parse_quality_runtime.py -q`
- broader regression: `backend/tests/test_module2_*`
- unified backend regression:
  - `backend/tests/test_create_app_routes.py`
  - `backend/tests/test_extraction_service.py`
  - `backend/tests/test_extraction_router.py`
  - `backend/tests/test_assistant_router.py`
  - `backend/tests/test_auth_repository.py`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After the schema-field and schema-request helper extractions, the next most suitable `main.py` migration target is the semantics-heavy but still pure rule layer that includes:

- semantic label signal detection
- semantic weakness scoring
- conservative semantic closure candidate selection
- canonical schema field ranking

That next wave should still keep the same migration discipline:

- move helpers before redesigning thresholds
- preserve the current extraction workflow
- use the existing `backend/tests/test_module2_*` and unified backend matrix as the release gate

## 2026-03-27 Increment: Schema Semantics Extraction

The semantic label analysis helper layer has now been migrated out of `backend/module2/app/main.py`.

This wave extracted the semantic helper glue into:

- `backend/module2/app/runtime/main_schema_semantics_bundle.py`

This new bundle now owns:

- exact-token semantic detection
- fragment semantic detection
- semantic signal flag construction
- weak-label detection
- semantic label strength scoring
- semantic closure alias-fragment blocking

This extraction keeps the existing semantic scoring behavior intact while removing another dense pure-rule block from the Module 2 entry file.

### Regression Validation For This Increment

The following validation passed after the extraction:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_schema_semantics_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_schema_semantics_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_schema_semantics_bundle.py backend/tests/test_module2_main_schema_fields_bundle.py backend/tests/test_module2_main_schema_request_bundle.py backend/tests/test_module2_main_result_filter_bundle.py backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_quality_bundle.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- broader regression: `backend/tests/test_module2_*`
- unified backend regression:
  - `backend/tests/test_create_app_routes.py`
  - `backend/tests/test_extraction_service.py`
  - `backend/tests/test_extraction_router.py`
  - `backend/tests/test_assistant_router.py`
  - `backend/tests/test_auth_repository.py`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Schema Selection Extraction

The semantic-closure and canonical-selection helper layer has also now been migrated out of `backend/module2/app/main.py`.

This wave extracted the schema-selection helper glue into:

- `backend/module2/app/runtime/main_schema_selection_bundle.py`

This new bundle now owns:

- semantic closure candidate picking
- conservative semantic closure application
- canonical schema field selection scoring
- best canonical schema field selection

This keeps the current closure thresholds and canonical ranking behavior intact while further reducing the concentration of schema rules in the entry file.

### Regression Validation For This Increment

The following validation passed after the extraction:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_schema_semantics_bundle.py backend/module2/app/runtime/main_schema_selection_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_schema_semantics_bundle.py backend/tests/test_module2_main_schema_selection_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_schema_semantics_bundle.py backend/tests/test_module2_main_schema_selection_bundle.py backend/tests/test_module2_main_schema_fields_bundle.py backend/tests/test_module2_main_schema_request_bundle.py backend/tests/test_module2_main_result_filter_bundle.py backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_quality_bundle.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- broader regression: `backend/tests/test_module2_*`
- unified backend regression:
  - `backend/tests/test_create_app_routes.py`
  - `backend/tests/test_extraction_service.py`
  - `backend/tests/test_extraction_router.py`
  - `backend/tests/test_assistant_router.py`
  - `backend/tests/test_auth_repository.py`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Latest Completed Slice

Since the previous stage assessment, the next `main.py`-focused migration wave has now been completed in eight additional steps:

- schema context helper extraction into `backend/module2/app/runtime/main_schema_context_bundle.py`
- heuristic schema inference helper extraction into `backend/module2/app/runtime/main_schema_inference_bundle.py`
- LLM-assisted schema inference helper extraction into `backend/module2/app/runtime/main_schema_llm_bundle.py`
- schema resolution orchestration extraction into `backend/module2/app/runtime/main_schema_resolution_bundle.py`
- dynamic schema-informed extract-timeout helper extraction into `backend/module2/app/runtime/main_schema_timeout_bundle.py`
- document IO helper extraction into `backend/module2/app/runtime/main_document_io_bundle.py`
- schema primitive helper extraction into `backend/module2/app/runtime/main_schema_primitives_bundle.py`
- low-value quick-fallback guard extraction into `backend/module2/app/runtime/main_value_guard_bundle.py`

This increment also completed the corresponding `main.py` wiring cleanup:

- removed the old inline schema context helper implementations from `backend/module2/app/main.py`
- removed the old inline heuristic schema inference helper implementations from `backend/module2/app/main.py`
- removed the old inline schema LLM helper implementations from `backend/module2/app/main.py`
- removed the old inline schema resolution orchestration implementation from `backend/module2/app/main.py`
- removed the old inline dynamic schema timeout helper implementation from `backend/module2/app/main.py`
- removed the old inline document IO helper implementations from `backend/module2/app/main.py`
- removed the old inline schema primitive helper implementations from `backend/module2/app/main.py`
- removed the old inline low-value quick-fallback guard implementation from `backend/module2/app/main.py`
- switched schema inference call sites to `module2_main_schema_inference_bundle.infer_schema_fields_heuristic(...)`
- switched schema LLM call sites to `module2_main_schema_llm_bundle.infer_schema_fields_llm(...)`
- switched schema resolution call sites to `module2_main_schema_resolution_bundle.resolve_effective_schema(...)`
- switched dynamic timeout call sites to `module2_main_schema_timeout_bundle.resolve_dynamic_extract_timeout_sec(...)`
- switched Word and DOC conversion call sites to `module2_main_document_io_bundle.*`
- switched schema primitive consumers to `module2_main_schema_primitives_bundle.*`
- switched low-value quick-fallback call sites to `module2_main_value_guard_bundle.is_low_value_quick_fallback_value(...)`
- corrected bundle initialization order so `backend/module2/app/main.py` can import cleanly again when started as `module2`'s FastAPI app

The migration remains responsibility-preserving rather than behavior-reducing:

- heuristic schema field discovery logic still exists
- figure and markdown schema context logic still exists
- LLM-assisted schema field discovery logic still exists
- auto/manual schema resolution orchestration still exists
- word-file dynamic extract-timeout scaling still exists
- Word -> PDF and DOC -> DOCX async conversion wrappers still exist
- PDF region crop helper behavior still exists
- schema primitive normalization and field typing rules still exist
- low-value quick-fallback suppression still exists
- schema semantics and schema selection still run after candidate generation

New regression coverage added in this wave:

- `backend/tests/test_module2_main_schema_context_bundle.py`
- `backend/tests/test_module2_main_schema_inference_bundle.py`
- `backend/tests/test_module2_main_schema_llm_bundle.py`
- `backend/tests/test_module2_main_schema_resolution_bundle.py`
- `backend/tests/test_module2_main_schema_timeout_bundle.py`
- `backend/tests/test_module2_main_document_io_bundle.py`
- `backend/tests/test_module2_main_schema_primitives_bundle.py`
- `backend/tests/test_module2_main_value_guard_bundle.py`

Validation executed for this increment:

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_schema_inference_bundle.py backend/module2/app/runtime/main_schema_llm_bundle.py backend/module2/app/runtime/main_schema_resolution_bundle.py backend/module2/app/runtime/main_schema_timeout_bundle.py backend/module2/app/runtime/main_document_io_bundle.py backend/module2/app/runtime/main_schema_primitives_bundle.py backend/module2/app/runtime/main_value_guard_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_schema_inference_bundle.py backend/tests/test_module2_main_schema_llm_bundle.py backend/tests/test_module2_main_schema_resolution_bundle.py backend/tests/test_module2_main_schema_timeout_bundle.py backend/tests/test_module2_main_document_io_bundle.py backend/tests/test_module2_main_schema_primitives_bundle.py backend/tests/test_module2_main_value_guard_bundle.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_main_value_guard_bundle.py backend/tests/test_module2_main_schema_primitives_bundle.py backend/tests/test_module2_main_document_io_bundle.py backend/tests/test_module2_main_schema_timeout_bundle.py backend/tests/test_module2_main_schema_resolution_bundle.py backend/tests/test_module2_main_schema_llm_bundle.py backend/tests/test_module2_main_schema_inference_bundle.py backend/tests/test_module2_main_schema_context_bundle.py backend/tests/test_module2_main_schema_semantics_bundle.py backend/tests/test_module2_main_schema_selection_bundle.py backend/tests/test_module2_main_schema_fields_bundle.py backend/tests/test_module2_main_schema_request_bundle.py backend/tests/test_module2_main_result_filter_bundle.py backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_quality_bundle.py backend/tests/test_module2_main_service_bundle.py backend/tests/test_module2_main_workflow_bundle.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_word_input_preparation_runtime.py backend/tests/test_module2_office_preview_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_postprocess_runtime.py backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After the schema, document IO, and value-guard helper extractions, `backend/module2/app/main.py` is now effectively a composition root.

At this point the safest next migration target is no longer `main.py` itself.
The next high-value targets move one level deeper into the runtime/core layer:

- `backend/module2/app/core/document_pipeline_runtime.py` which is still the largest orchestration center at roughly 406 lines
- `backend/module2/app/core/word_input_preparation_runtime.py` which still contains the Word-family branch coordination
- `backend/module2/app/core/document_postprocess_runtime.py` if additional response assembly cleanup is needed after that

The next safe extraction should therefore focus on:

- the Word/non-PDF branch orchestration inside `document_pipeline_runtime.py`
- any helper-only subpaths inside `word_input_preparation_runtime.py` that do not change the DOCX -> PDF -> parse workflow

A likely next runtime target is:

- `backend/module2/app/core/document_pipeline_runtime.py` decomposition helpers

That next wave should continue following the same migration discipline:

- extract pure helper layers first
- keep the live extraction thresholds unchanged during relocation
- use the existing module2 and unified backend regression matrix as the release gate

## 2026-03-27 Increment: Word Conversion Execution Extraction

The Word-family conversion execution layer has now been migrated out of
`backend/module2/app/core/word_input_preparation_runtime.py`.

This wave introduced:

- `backend/module2/app/core/word_conversion_execution_runtime.py`

This new runtime now owns the execution details for:

- `Word -> PDF` preview conversion execution
- `Word -> PDF` timeout handling and progress emission
- `Word -> PDF` failure-to-fallback resolution handoff
- `DOC -> DOCX` fast-track conversion execution
- `DOC -> DOCX` timeout exhaustion and terminal failure surfacing

At the same time, `backend/module2/app/core/word_input_preparation_runtime.py`
was reduced to a thinner coordinator that now keeps responsibility for:

- precondition validation
- branch selection policy
- parse-input state initialization
- final `.pdf -> VisualTrack` normalization

This keeps the migration responsibility-preserving rather than behavior-reducing:

- the DOCX -> PDF branch still uses the same preview and timeout policy
- the native DOCX recovery fallback still uses the same resolution contract
- the DOC -> DOCX fast-track branch still uses the same conversion outcome builders
- the outer document pipeline contract remains unchanged

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_word_conversion_execution_runtime.py`
- existing `backend/tests/test_module2_word_input_preparation_runtime.py` updated for module import and delegation coverage

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/word_input_preparation_runtime.py backend/module2/app/core/word_conversion_execution_runtime.py backend/tests/test_module2_word_input_preparation_runtime.py backend/tests/test_module2_word_conversion_execution_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_word_conversion_execution_runtime.py backend/tests/test_module2_word_input_preparation_runtime.py backend/tests/test_module2_office_preview_runtime.py backend/tests/test_module2_document_pipeline_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After this extraction, `backend/module2/app/core/word_input_preparation_runtime.py`
is no longer the best next target.

The next highest-value runtime target is now:

- `backend/module2/app/core/document_pipeline_runtime.py`

The safest next decomposition points inside that file are the still-dense
mid/late orchestration blocks:

- visual chain contract validation
- schema session resolution handoff shaping
- extraction graph execution handoff shaping
- final `DocumentPipelineOutcome` assembly

The migration discipline should remain unchanged:

- keep the public extraction contract frozen
- move helper-orchestration layers before changing thresholds or policies
- continue using the existing module2 and unified backend regression matrix as the release gate

## 2026-03-27 Increment: Document Pipeline Finalize Extraction

The next safe post-Word-preparation slice has now also been migrated out of
`backend/module2/app/core/document_pipeline_runtime.py`.

This wave introduced:

- `backend/module2/app/core/document_pipeline_finalize_runtime.py`

This new runtime now owns:

- visual chain contract construction handoff
- visual chain contract terminal validation
- final `DocumentPipelineOutcome` assembly

At the same time, `backend/module2/app/core/document_pipeline_runtime.py`
was reduced so it now delegates those post-parse finalize responsibilities
instead of keeping them inline.

This keeps the migration responsibility-preserving rather than behavior-reducing:

- parse recovery still happens in the same order
- schema session resolution still happens in the same place in the workflow
- extraction graph execution still happens in the same place in the workflow
- the returned pipeline outcome shape is unchanged

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_document_pipeline_finalize_runtime.py`
- existing `backend/tests/test_module2_document_pipeline_runtime.py` updated for package import and finalize-runtime integration coverage

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/document_pipeline_finalize_runtime.py backend/module2/app/core/document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_finalize_runtime.py backend/tests/test_module2_document_pipeline_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_document_pipeline_finalize_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_workflow_runtime.py backend/tests/test_module2_word_conversion_execution_runtime.py backend/tests/test_module2_word_input_preparation_runtime.py backend/tests/test_module2_office_preview_runtime.py backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After this finalize extraction, the next highest-value work inside
`backend/module2/app/core/document_pipeline_runtime.py` is no longer
contract validation or result assembly.

The next safest remaining decomposition points are:

- schema session resolution handoff shaping
- extraction graph execution handoff shaping
- any remaining logging-only or response-shaping glue around those two phases

The migration discipline should remain unchanged:

- keep the public workflow contract frozen
- move orchestration wrappers before changing live extraction logic
- continue using the existing module2 and unified backend regression matrix as the release gate

## 2026-03-27 Increment: Document Pipeline Schema And Graph Handoff Extraction

The next safe decomposition step inside
`backend/module2/app/core/document_pipeline_runtime.py` has now also been completed.

This wave introduced:

- `backend/module2/app/core/document_pipeline_schema_runtime.py`
- `backend/module2/app/core/document_pipeline_graph_runtime.py`

These new runtimes now own:

- schema session handoff shaping
- schema-session semaphore scoping
- schema resolution result unpacking and schema-stage logging
- extraction graph handoff shaping
- extraction graph result unpacking and graph-stage logging

At the same time, `backend/module2/app/core/document_pipeline_runtime.py`
was reduced further so it now delegates:

- visual chain contract validation to `document_pipeline_finalize_runtime.py`
- schema-stage handoff to `document_pipeline_schema_runtime.py`
- graph-stage handoff to `document_pipeline_graph_runtime.py`

This keeps the migration responsibility-preserving rather than behavior-reducing:

- schema resolution still occurs after parse recovery
- extraction graph execution still occurs after schema resolution
- the same semaphores, helpers, and timeouts are still passed through
- the outer `DocumentPipelineOutcome` contract remains unchanged

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_document_pipeline_schema_runtime.py`
- `backend/tests/test_module2_document_pipeline_graph_runtime.py`
- existing `backend/tests/test_module2_document_pipeline_runtime.py` updated with delegation coverage

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/document_pipeline_runtime.py backend/module2/app/core/document_pipeline_schema_runtime.py backend/module2/app/core/document_pipeline_graph_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_schema_runtime.py backend/tests/test_module2_document_pipeline_graph_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_schema_runtime.py backend/tests/test_module2_document_pipeline_graph_runtime.py backend/tests/test_module2_document_pipeline_finalize_runtime.py backend/tests/test_module2_document_workflow_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_word_conversion_execution_runtime.py backend/tests/test_module2_word_input_preparation_runtime.py backend/tests/test_module2_office_preview_runtime.py backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After the finalize, schema, and graph handoff extractions, the next remaining
high-value work inside `backend/module2/app/core/document_pipeline_runtime.py`
is now concentrated in the front half of the pipeline:

- document input plan to parse-input handoff shaping
- parse preparation and parse recovery handoff shaping
- parse-stage logging and progress-message normalization

The migration discipline should remain unchanged:

- keep the public workflow contract frozen
- keep the existing parse and fallback policies unchanged during relocation
- continue using the existing module2 and unified backend regression matrix as the release gate

## 2026-03-27 Increment: Document Pipeline Parse Handoff Extraction

The next safe front-half decomposition step inside
`backend/module2/app/core/document_pipeline_runtime.py` has now also been completed.

This wave introduced:

- `backend/module2/app/core/document_pipeline_parse_runtime.py`

This new runtime now owns:

- parse preparation handoff shaping
- parse recovery handoff shaping
- parse-stage timeout and extract-timeout carry-forward
- parse-stage result unpacking
- parse-stage logging

At the same time, `backend/module2/app/core/document_pipeline_runtime.py`
was reduced further so it now delegates:

- parse-stage handoff to `document_pipeline_parse_runtime.py`
- visual chain contract validation to `document_pipeline_finalize_runtime.py`
- schema-stage handoff to `document_pipeline_schema_runtime.py`
- graph-stage handoff to `document_pipeline_graph_runtime.py`

This keeps the migration responsibility-preserving rather than behavior-reducing:

- parse preparation still occurs before parse recovery
- the existing parse fallback policy still remains in `document_parse_recovery_runtime.py`
- parse-stage elapsed-time accounting still uses the same `parse_ms` window
- the outer `DocumentPipelineOutcome` contract remains unchanged

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_document_pipeline_parse_runtime.py`
- existing `backend/tests/test_module2_document_pipeline_runtime.py` updated with parse-stage delegation coverage

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/document_pipeline_runtime.py backend/module2/app/core/document_pipeline_parse_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_parse_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_document_pipeline_parse_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_schema_runtime.py backend/tests/test_module2_document_pipeline_graph_runtime.py backend/tests/test_module2_document_pipeline_finalize_runtime.py backend/tests/test_module2_document_workflow_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_word_conversion_execution_runtime.py backend/tests/test_module2_word_input_preparation_runtime.py backend/tests/test_module2_office_preview_runtime.py backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After the parse, finalize, schema, and graph handoff extractions, the next
highest-value work inside `backend/module2/app/core/document_pipeline_runtime.py`
is now concentrated in the very front edge of the pipeline:

- document input plan handoff shaping
- word-input preparation handoff shaping
- parse-stage progress-message normalization cleanup if needed

The migration discipline should remain unchanged:

- keep the public workflow contract frozen
- keep Word/DOC conversion policy unchanged during relocation
- continue using the existing module2 and unified backend regression matrix as the release gate

## 2026-03-27 Increment: Document Pipeline Input Handoff Extraction

The next safe front-edge decomposition step inside
`backend/module2/app/core/document_pipeline_runtime.py` has now also been completed.

This wave introduced:

- `backend/module2/app/core/document_pipeline_input_runtime.py`

This new runtime now owns:

- document input-plan handoff shaping
- input-plan result unpacking
- word-input preparation handoff shaping
- pre-parse input-state assembly

At the same time, `backend/module2/app/core/document_pipeline_runtime.py`
was reduced further so it now delegates:

- input-stage handoff to `document_pipeline_input_runtime.py`
- parse-stage handoff to `document_pipeline_parse_runtime.py`
- visual chain contract validation to `document_pipeline_finalize_runtime.py`
- schema-stage handoff to `document_pipeline_schema_runtime.py`
- graph-stage handoff to `document_pipeline_graph_runtime.py`

This keeps the migration responsibility-preserving rather than behavior-reducing:

- the same document input planning logic still runs first
- the same Word/DOC preparation logic still runs before parse-stage orchestration
- the same parse/schema/graph ordering still remains intact
- the outer `DocumentPipelineOutcome` contract remains unchanged

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_document_pipeline_input_runtime.py`
- existing `backend/tests/test_module2_document_pipeline_runtime.py` updated with input-stage delegation coverage

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/document_pipeline_runtime.py backend/module2/app/core/document_pipeline_input_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_input_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_document_pipeline_input_runtime.py backend/tests/test_module2_document_pipeline_parse_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_schema_runtime.py backend/tests/test_module2_document_pipeline_graph_runtime.py backend/tests/test_module2_document_pipeline_finalize_runtime.py backend/tests/test_module2_document_workflow_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_word_conversion_execution_runtime.py backend/tests/test_module2_word_input_preparation_runtime.py backend/tests/test_module2_office_preview_runtime.py backend/tests/test_module2_post_parse_quality_runtime.py backend/tests/test_module2_schema_session_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

After the input, parse, finalize, schema, and graph handoff extractions,
`backend/module2/app/core/document_pipeline_runtime.py` is now close to a
true mid-pipeline coordinator.

The next high-value work is therefore no longer aggressive further splitting
of this file for its own sake.

The next safer directions are now:

- progress-message normalization cleanup where mojibake strings still exist
- constructor and dependency surface normalization if the runtime signatures become too wide
- shifting attention back to other still-heavy orchestration centers such as
  `backend/module2/app/core/document_postprocess_runtime.py` or selected
  rule-heavy leftovers in `backend/module2/app/core/parser.py`

The migration discipline should remain unchanged:

- keep the public workflow contract frozen
- prefer readability and interface clarity over cosmetic over-fragmentation
- continue using the existing module2 and unified backend regression matrix as the release gate

## 2026-03-27 Increment: Chinese Compatibility Cleanup and Full Regression Confirmation

After `document_pipeline_runtime.py` was reduced to the five-stage coordinator

- input
- parse
- finalize
- schema
- graph

this increment focused on the next safest stabilization task:

- cleaning mojibake / source-encoding residue without changing the preserved mainline behavior

### What Was Cleaned In This Increment

The following user-visible or workflow-adjacent compatibility points were normalized:

- `backend/module2/app/core/document_pipeline_runtime.py`
  - parsed progress message restored to proper Chinese:
    - `版面解析完成，正在抽取字段与图表`
- `backend/module2/app/core/document_workflow_runtime.py`
  - finalizing progress message restored to proper Chinese:
    - `抽取完成，正在整理结果与缓存`
- `backend/module2/app/core/extraction_graph_runtime.py`
  - extraction progress message restored to proper Chinese:
    - `正在抽取字段、表格、图片与来源信息`
- `backend/module2/app/runtime/main_schema_context_bundle.py`
  - schema context labels normalized:
    - `表格语义`
    - `图表语义`
- `backend/module2/app/runtime/cache_clear.py`
  - cache-clear response message normalized:
    - `模块二缓存已清理，scope={normalized_scope}`
- `backend/module2/app/main.py`
  - `_DATE_FIELD_TOKENS` restored to intended Chinese tokens:
    - `日期`
    - `时间`
    - `年份`
    - `年月`
    - `季度`
    - `时点`
- `backend/module2/app/runtime/main_nonpdf_bundle.py`
  - non-PDF preflight figure keyword regex restored to intended Chinese/English coverage:
    - `图表`
    - `图\d+`
    - `表\d+`
    - `figure`
    - `chart`
    - `diagram`
    - `柱状图`
    - `折线图`
    - `饼图`
- `backend/module2/app/runtime/main_quick_extract_bundle.py`
  - numeric fallback normalization repaired so Chinese punctuation is handled cleanly:
    - strips `,`
    - strips `，`
    - strips `、`
    - strips `%`
    - strips `％`

This kept the migration responsibility-preserving rather than behavior-reducing:

- no cache-clear orchestration behavior was changed
- no non-PDF budget policy was changed
- no document workflow stage ordering was changed
- no `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4` handoff was changed
- no `auth` routing or unified FastAPI composition was removed

### Regression Coverage Added Or Updated In This Increment

- `backend/tests/test_module2_document_workflow_runtime.py`
- `backend/tests/test_module2_main_schema_context_bundle.py`
- `backend/tests/test_module2_cache_clear_runtime.py`
- `backend/tests/test_module2_main_nonpdf_bundle.py`
- `backend/tests/test_module2_main_quick_extract_bundle.py`
- `backend/tests/test_module2_main_source_literals.py`

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/document_pipeline_runtime.py backend/module2/app/core/document_workflow_runtime.py backend/module2/app/core/extraction_graph_runtime.py backend/module2/app/runtime/main_schema_context_bundle.py backend/module2/app/runtime/cache_clear.py backend/module2/app/runtime/main_nonpdf_bundle.py backend/module2/app/runtime/main_quick_extract_bundle.py backend/module2/app/main.py backend/tests/test_module2_document_workflow_runtime.py backend/tests/test_module2_main_schema_context_bundle.py backend/tests/test_module2_cache_clear_runtime.py backend/tests/test_module2_main_nonpdf_bundle.py backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_source_literals.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_document_pipeline_input_runtime.py backend/tests/test_module2_document_pipeline_parse_runtime.py backend/tests/test_module2_document_pipeline_runtime.py backend/tests/test_module2_document_pipeline_schema_runtime.py backend/tests/test_module2_document_pipeline_graph_runtime.py backend/tests/test_module2_document_pipeline_finalize_runtime.py backend/tests/test_module2_document_workflow_runtime.py backend/tests/test_module2_main_schema_context_bundle.py backend/tests/test_module2_extraction_graph_runtime.py backend/tests/test_module2_cache_clear_runtime.py backend/tests/test_module2_main_nonpdf_bundle.py backend/tests/test_module2_main_quick_extract_bundle.py backend/tests/test_module2_main_source_literals.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that the five-stage `document_pipeline` coordinator is stable and the most visible
source-encoding residue has been cleared, the next safest migration slice is no longer
message cleanup.

The next high-confidence work should return to responsibility extraction:

- continue splitting `backend/module2/app/core/parser.py`
  - especially remaining pure-rule helpers in table merge / figure matching
- keep outer runtime orchestration frozen while moving pure helpers downward
- continue deleting only dead code paths, not active workflow branches
- keep every slice behind the same regression gate:
  - module2 runtime tests
  - subprocess parse test
  - unified backend route/service tests

## 2026-03-27 Increment: Parser PDF Entry Adapter Extraction

After re-checking `backend/module2/app/core/parser.py`, the previously planned
"table merge / figure matching" next step was re-evaluated against the current tree.

By this point, those lower-level responsibilities had already been substantially moved into:

- `table_merge_runtime.py`
- `figure_matching_runtime.py`
- related parser bundle runtimes

So the next genuinely useful and still-safe slice was no longer another tiny rule extraction.

The highest-value remaining seam inside `parser.py` was the PDF entry adapter layer:

- PDF reader preparation
- PDF parse entry orchestration
- visual-first parse handoff adaptation
- OCR fallback adaptation
- parser-run-state patch application around those entrypoints

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_pdf_entry_runtime.py`

This new runtime now owns:

- `prepare_pdf_reader(...)`
- `parse_pdf(...)`
- `parse_pdf_visual_first(...)`
- `parse_pdf_with_ocr(...)`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now delegates
its PDF entry adapter work to `ParserPdfEntryRuntime` rather than carrying those state-bridging
wrappers inline.

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `PdfParseRuntime` still owns the actual PDF strategy selection
- `PdfVisualParseRuntime` still owns visual-first execution
- `PdfOcrRuntime` still owns OCR fallback execution
- `ParserRunStateRuntime` still remains the single mutable parser-run-state holder
- `ParserStateRuntime` still remains the state-patch normalizer
- `parser.py` only got thinner at the adapter layer; no parse algorithm was downgraded or bypassed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_pdf_entry_runtime.py`

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_pdf_entry_runtime.py backend/tests/test_module2_parser_pdf_entry_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_pdf_entry_runtime.py backend/tests/test_module2_pdf_parse_runtime.py backend/tests/test_module2_pdf_native_parse_runtime.py backend/tests/test_module2_pdf_ocr_runtime.py backend/tests/test_module2_parser_provider_bundle_runtime.py backend/tests/test_module2_parser_state_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that the PDF entry adapter layer is no longer embedded directly in `parser.py`,
the next safest parser-side slices are:

- DOCX / XLSX / image / plain-text entry adapters that still bridge runtime results into parser state
- further constructor-surface normalization inside `parser.py` if the initialization section remains too wide
- only after that, consider any remaining helper relocations if they clearly reduce responsibility rather than just moving lines around

## 2026-03-27 Increment: Parser Non-PDF Entry Adapter Extraction

After the PDF entry adapter layer was moved out of `parser.py`, the next safest
continuation was the remaining non-PDF entry bridges that still lived inline in the parser:

- DOCX state handoff
- relaxed DOCX state handoff
- XLSX state handoff
- image state handoff
- plain-text state handoff

These were not parse algorithms themselves. They were adapter code that:

- called an already-existing runtime
- normalized the returned payload into parser state patches
- applied those patches back into `ParserRunStateRuntime`
- raised a stable error when a state update returned no parse result

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_nonpdf_entry_runtime.py`

This new runtime now owns:

- `parse_docx(...)`
- `parse_docx_relaxed(...)`
- `parse_xlsx(...)`
- `parse_image(...)`
- `parse_plain(...)`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now delegates
those non-PDF entry adapters to `ParserNonPdfEntryRuntime` rather than carrying the
state-bridging wrappers inline.

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `DocxDocumentRuntime` still owns DOCX parsing
- `XlsxParseRuntime` still owns XLSX parsing
- `ImageDocumentRuntime` still owns image parsing
- `plain_text_parser.py` still owns plain-text parsing
- `ParserStateRuntime` still owns state-patch normalization
- `ParserRunStateRuntime` still owns mutable parser run state
- no fallback policy, OCR policy, visual policy, or Gemini policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_nonpdf_entry_runtime.py`

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_nonpdf_entry_runtime.py backend/tests/test_module2_parser_nonpdf_entry_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_nonpdf_entry_runtime.py backend/tests/test_module2_document_dispatch_runtime.py backend/tests/test_module2_parser_pdf_entry_runtime.py backend/tests/test_module2_parser_state_runtime.py backend/tests/test_module2_docx_document_runtime.py backend/tests/test_module2_xlsx_parse_runtime.py backend/tests/test_module2_image_document_runtime.py backend/tests/test_module2_plain_text_parser.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that both PDF and non-PDF entry adapters have been moved out of `parser.py`,
the next safest work is no longer file-type entry bridging.

The next high-confidence directions are:

- continue shrinking `parser.py` constructor / initialization surface
  - especially the long `_init_*` chains that only wire bundle runtimes together
- consider extracting the DOCX-via-PDF bridge and chart-merge state adapter if we want one more safe parser slice
- only then revisit any remaining helper relocations where the responsibility gain is still meaningful

## 2026-03-27 Increment: Parser DOCX-via-PDF Bridge Extraction

After the non-PDF entry adapters were moved out of `parser.py`, the next safest
and still workflow-relevant seam was the DOCX-via-PDF bridge layer that remained inline.

This layer was still doing parser-owned adapter work around:

- `DocxViaPdfRuntime` result handoff
- last-parse stats overlay
- DOCX chart-xml merge trigger
- merged figure-block state writeback

These were not document parsing algorithms themselves. They were bridge logic that
connected already-existing runtimes back into `ParserRunStateRuntime`.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_docx_pdf_entry_runtime.py`

This new runtime now owns:

- `parse_docx_via_pdf(...)`
- `merge_docx_chart_xml_into_pdf_figures(...)`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now delegates
the DOCX-via-PDF bridge layer to `ParserDocxPdfEntryRuntime` rather than carrying
that stats-and-state adapter logic inline.

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `DocxViaPdfRuntime` still owns DOCX-to-PDF conversion handoff
- `DocxChartMergeRuntime` still owns chart-xml/dataframe merge logic
- `WordPdfContextRuntime` still owns chart-merge stats patch construction
- `ParserRunStateRuntime` still owns mutable parse stats and figure-block state
- no DOCX conversion policy, PDF parse policy, MinerU behavior, or Gemini behavior was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_docx_pdf_entry_runtime.py`

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_docx_pdf_entry_runtime.py backend/tests/test_module2_parser_docx_pdf_entry_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_docx_pdf_entry_runtime.py backend/tests/test_module2_docx_via_pdf_runtime.py backend/tests/test_module2_docx_chart_merge_runtime.py backend/tests/test_module2_word_pdf_context_runtime.py backend/tests/test_module2_parser_nonpdf_entry_runtime.py backend/tests/test_module2_parser_pdf_entry_runtime.py backend/tests/test_module2_document_dispatch_runtime.py backend/tests/test_module2_docx_document_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that `parser.py` has already shed:

- PDF entry adapters
- non-PDF entry adapters
- DOCX-via-PDF bridge adapters

the next safest work is no longer parse-entry bridging.

The next high-confidence directions are:

- continue shrinking the parser initialization surface
  - especially long `_init_*` chains that only wire dependencies together
- consider extracting selected visual/image enhancement adapters such as low-quality-page Gemini enhancement if they still exist only as thin bridges
- after that, re-evaluate whether further helper relocation is still producing real responsibility reduction

## 2026-03-27 Increment: Parser Bootstrap Wiring Extraction

After `parser.py` had already shed:

- PDF entry adapters
- non-PDF entry adapters
- DOCX-via-PDF bridge adapters

the next safest work moved from parse-entry bridging to parser bootstrap wiring.

The highest-value remaining setup seam was the purely-constructive initialization layer:

- support runtime / bundle creation
- provider state runtime creation

These responsibilities were not parse logic. They were bootstrap-only wiring code
that constructed already-existing runtimes and attached them to the parser instance.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_bootstrap_runtime.py`

This new runtime now owns:

- `build_support_runtime_attrs(...)`
- `build_provider_state_runtime(...)`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now:

- builds support runtimes through `ParserBootstrapRuntime`
- builds `ParserProviderStateRuntime` through `ParserBootstrapRuntime`
- no longer carries the previous inline support/provider bootstrap implementations

This keeps the migration responsibility-preserving rather than behavior-reducing:

- the same runtime classes are still instantiated
- the same provider factories are still wired
- lazy provider creation still remains in `ParserProviderStateRuntime`
- no parse policy, OCR policy, MinerU policy, visual policy, or Gemini policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_bootstrap_runtime.py`

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_provider_state_runtime.py backend/tests/test_module2_parser_docx_pdf_entry_runtime.py backend/tests/test_module2_parser_nonpdf_entry_runtime.py backend/tests/test_module2_parser_pdf_entry_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that parser entry bridges and the first bootstrap wiring layer are both out of `parser.py`,
the next safest directions are:

- continue shrinking the remaining `_init_*` wiring chains for grouped runtime construction
- prefer extracting only those init segments that are mostly constructor composition, not parse behavior
- after that, re-evaluate whether `parser.py` should stop shrinking and hand attention back to other heavy orchestration centers

## 2026-03-27 Increment: Parser Document-Table Bootstrap Extraction

After the first parser bootstrap layer was removed from `parser.py`, the next safest
remaining setup seam was the document-table runtime construction chain.

This chain was still dominated by constructor composition for:

- non-PDF table helpers
- DOCX table parse helpers
- XLSX helpers
- table merge helpers
- OCR table utility helpers

These responsibilities were still bootstrap-only wiring. They were not parse policies.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_document_table_bootstrap_runtime.py`

This new runtime now owns grouped table-related bootstrap wiring for:

- `_table_header`
- `_nonpdf_table_runtime`
- `_nonpdf_table_rows_runtime`
- `_nonpdf_text_runtime`
- `_docx_parse_runtime`
- `_xlsx_runtime`
- `_xlsx_table_runtime`
- `_xlsx_parse_runtime`
- `_table_merge_runtime`
- `_pdf_fitz_table_runtime`
- `_ocr_table_utils`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that whole document-table runtime family through
`ParserDocumentTableBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserDocumentTableBundleRuntime` still owns table/docx/xlsx kwarg shaping
- `ParserTableHelperBundleRuntime` still owns table-helper kwarg shaping
- `OcrTableUtils`, `TableMergeRuntime`, `XlsxParseRuntime`, and related runtimes still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no table extraction policy, XLSX parsing policy, OCR policy, or merge policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_document_table_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_document_table_bootstrap_runtime.py backend/tests/test_module2_parser_document_table_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_document_table_bootstrap_runtime.py backend/tests/test_module2_parser_provider_state_runtime.py backend/tests/test_module2_parser_docx_pdf_entry_runtime.py backend/tests/test_module2_parser_nonpdf_entry_runtime.py backend/tests/test_module2_parser_pdf_entry_runtime.py backend/tests/test_module2_parser_document_table_bundle_runtime.py backend/tests/test_module2_parser_table_helper_bundle_runtime.py backend/tests/test_module2_docx_document_runtime.py backend/tests/test_module2_xlsx_parse_runtime.py backend/tests/test_module2_table_merge_runtime.py backend/tests/test_module2_ocr_table_utils.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that parser entry bridges, the first bootstrap layer, and the document-table bootstrap
chain are all out of `parser.py`, the next safest directions are:

- continue extracting grouped `_init_*` chains that are still mostly constructor composition
- avoid touching `_init_*` segments where callback shaping itself starts to encode behavior
- re-evaluate whether remaining parser shrinkage is still the highest-yield migration target versus shifting attention back to other orchestration files

## 2026-03-27 Increment: Parser Visual-Payload Bootstrap Extraction

After the document-table bootstrap chain was removed from `parser.py`, the next safest
remaining setup seam was the visual-payload runtime construction chain.

This chain was still dominated by constructor composition for:

- figure semantics helpers
- figure vision payload helpers
- visual figure builder helpers
- table payload helpers
- table vision payload helpers
- visual table builder helpers
- visual cue / page signal helpers

These responsibilities were still bootstrap-only wiring. They were not parse execution policies.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_visual_payload_bootstrap_runtime.py`

This new runtime now owns grouped visual-payload bootstrap wiring for:

- `_figure_semantics`
- `_figure_vision_payload`
- `_visual_figure_builder`
- `_table_payload`
- `_table_vision_payload`
- `_visual_table_builder`
- `_visual_table_cue_runtime`
- `_visual_page_signal_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that whole visual-payload runtime family through
`ParserVisualPayloadBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserVisualPayloadBundleRuntime` still owns payload kwarg shaping
- `FigureSemanticsRuntime`, `TablePayloadRuntime`, `VisualTableBuilderRuntime`, and related runtimes still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no figure/table payload policy, visual cue policy, or page-signal policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_visual_payload_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_visual_payload_bootstrap_runtime.py backend/tests/test_module2_parser_visual_payload_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_visual_payload_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_visual_payload_bundle_runtime.py backend/tests/test_module2_figure_semantics.py backend/tests/test_module2_figure_vision_payload.py backend/tests/test_module2_visual_figure_builder.py backend/tests/test_module2_table_payload_runtime.py backend/tests/test_module2_table_vision_payload.py backend/tests/test_module2_visual_table_builder.py backend/tests/test_module2_visual_page_signal_runtime.py backend/tests/test_module2_visual_table_cue_runtime.py backend/tests/test_module2_image_vision_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest <expanded backend/tests/test_module2_*.py set> -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that parser entry bridges, bootstrap support wiring, document-table bootstrap wiring,
and visual-payload bootstrap wiring are all out of `parser.py`, the next safest directions are:

- continue extracting grouped `_init_*` chains only where they remain mostly constructor composition
- avoid crossing into sections where callback shaping itself starts to encode parse behavior
- re-evaluate whether the highest-yield next target is still `parser.py` or whether another orchestration file has become the better migration frontier

## 2026-03-27 Increment: Parser Image Bootstrap Extraction

After the visual-payload bootstrap chain was removed from `parser.py`, the next safest
remaining setup seam was the image runtime construction chain.

This chain was still dominated by constructor composition for:

- image OCR collection runtime
- image Gemini vision enhancement runtime
- image OCR post-processing runtime
- image top-level document orchestration runtime

These responsibilities were still bootstrap-only wiring. They were not image parsing policy.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_image_bootstrap_runtime.py`

This new runtime now owns grouped image bootstrap wiring for:

- `_image_ocr_runtime`
- `_image_vision_runtime`
- `_image_parse_runtime`
- `_image_document_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that whole image runtime family through
`ParserImageBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserImageBundleRuntime` still owns image kwarg shaping
- `ImageOcrRuntime`, `ImageVisionRuntime`, `ImageParseRuntime`, and `ImageDocumentRuntime` still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- the wrapper bridge `_enhance_low_quality_pages_with_gemini_vision(...)` remains in `parser.py`, so parser-owned run-state access is unchanged
- no image OCR policy, Gemini vision policy, or image parse policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_image_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/module2/app/core/parser_image_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_image_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_image_bootstrap_runtime.py backend/tests/test_module2_image_ocr_runtime.py backend/tests/test_module2_image_vision_runtime.py backend/tests/test_module2_image_parse_runtime.py backend/tests/test_module2_image_document_runtime.py backend/tests/test_module2_parser_nonpdf_entry_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_*.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that parser entry bridges, bootstrap support wiring, document-table bootstrap wiring,
visual-payload bootstrap wiring, and image bootstrap wiring are all out of `parser.py`,
the next safest directions are:

- extract the remaining vision-transport constructor chain into a focused bootstrap runtime
- keep avoiding PDF OCR/native execution chains where callback shaping is already part of behavior
- only move grouped `_init_*` segments that are still mostly runtime assembly rather than parse policy

## 2026-03-27 Increment: Parser Vision-Transport Bootstrap Extraction

After the image bootstrap chain was removed from `parser.py`, the next safest
remaining setup seam was the Gemini vision transport construction chain.

This chain was still dominated by constructor composition for:

- Gemini native transport URL/header helpers
- vision response normalization helpers
- vision request execution helpers
- DOCX chart-to-PDF figure matching helpers

These responsibilities were still bootstrap-only wiring. They were not transport or matching policy changes.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_vision_transport_bootstrap_runtime.py`

This new runtime now owns grouped vision transport bootstrap wiring for:

- `_gemini_native_transport_runtime`
- `_vision_response_runtime`
- `_vision_request_runtime`
- `_figure_matching_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that whole transport runtime family through
`ParserVisionTransportBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserVisionBundleRuntime` still owns transport kwarg shaping
- `GeminiNativeTransportRuntime`, `VisionResponseRuntime`, `VisionRequestRuntime`, and `FigureMatchingRuntime` still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no Gemini request policy, fallback policy, response normalization policy, or figure matching policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_vision_transport_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/module2/app/core/parser_vision_transport_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_vision_transport_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_*.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Parser Visual-Context Bootstrap Extraction

After the vision transport chain was removed from `parser.py`, the next safest
remaining setup seam was the visual profile/context construction chain.

This chain was still dominated by constructor composition for:

- PDF visual-profile classification runtime
- visual runtime-limits resolution runtime
- visual status-field normalization runtime
- visual PDF bootstrap/runtime-limit bridge
- visual PDF native-context preparation runtime
- visual object context runtime
- visual layout selection runtime

These responsibilities were still bootstrap-only wiring. They were not visual execution policy.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_visual_context_bootstrap_runtime.py`

This new runtime now owns grouped visual profile/context bootstrap wiring for:

- `_pdf_visual_profile_runtime`
- `_visual_runtime_limits_runtime`
- `_visual_status_builder_runtime`
- `_visual_pdf_bootstrap_runtime`
- `_visual_pdf_prepare_runtime`
- `_visual_object_context_runtime`
- `_visual_layout_selector_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that whole visual profile/context runtime family through
`ParserVisualContextBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserVisualContextBundleRuntime` still owns visual-context kwarg shaping
- `PdfVisualProfileRuntime`, `VisualRuntimeLimitsRuntime`, `VisualPdfBootstrapRuntime`, `VisualPdfPrepareRuntime`, `VisualObjectContextRuntime`, and `VisualLayoutSelectorRuntime` still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no visual profile classification policy, runtime-limit policy, PDF context preparation policy, or layout selection policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_visual_context_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/module2/app/core/parser_visual_context_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_visual_context_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_*.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that parser entry bridges, bootstrap support wiring, document-table bootstrap wiring,
visual-payload bootstrap wiring, image bootstrap wiring, vision-transport bootstrap wiring,
and visual profile/context bootstrap wiring are all out of `parser.py`, the next safest directions are:

- evaluate whether the remaining visual execution/finalize chain can be grouped into one more bootstrap-only extraction
- keep avoiding direct extraction of `pdf_ocr` and `pdf_native` constructor/callback blocks until the execution-side seams are clearer
- continue preferring grouped `_init_*` segments only where they are still runtime assembly rather than parse behavior

## 2026-03-27 Increment: Parser Visual-Execution Bootstrap Extraction

After the visual profile/context chain was removed from `parser.py`, the next safest
remaining setup seam was the visual execution/finalize construction chain.

This chain was still dominated by constructor composition for:

- visual vision job execution runtime
- visual job planning runtime
- visual result materialization runtime
- visual execution orchestration runtime
- visual finalize/text-only/orchestrator runtimes
- PDF visual parse / PDF parse entrypoint runtimes

These responsibilities were still bootstrap-only wiring. They were not PDF OCR/native behavior changes.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_visual_execution_bootstrap_runtime.py`

This new runtime now owns grouped visual execution bootstrap wiring for:

- `_visual_vision_jobs_runtime`
- `_visual_job_planner_runtime`
- `_visual_result_materializer_runtime`
- `_visual_execution_runtime`
- `_visual_parse_finalizer_runtime`
- `_visual_text_only_builder_runtime`
- `_visual_parse_orchestrator_runtime`
- `_pdf_visual_parse_runtime`
- `_pdf_parse_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that whole visual execution runtime family through
`ParserVisualExecutionBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserVisualExecutionBundleRuntime` still owns visual-execution kwarg shaping
- `VisualExecutionRuntime`, `VisualParseFinalizerRuntime`, `VisualParseOrchestratorRuntime`, `PdfVisualParseRuntime`, and `PdfParseRuntime` still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no visual-first selection policy, vision execution policy, text-only fallback policy, or PDF route policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_visual_execution_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/module2/app/core/parser_visual_execution_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_visual_execution_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_visual_execution_bootstrap_runtime.py backend/tests/test_module2_visual_execution_runtime.py backend/tests/test_module2_visual_vision_jobs.py backend/tests/test_module2_visual_parse_finalizer.py backend/tests/test_module2_visual_text_only_builder.py backend/tests/test_module2_visual_parse_orchestrator.py backend/tests/test_module2_pdf_visual_parse_runtime.py backend/tests/test_module2_pdf_parse_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_visual_job_planner.py backend/tests/test_module2_visual_result_materializer.py backend/tests/test_module2_visual_pdf_bootstrap.py backend/tests/test_module2_visual_pdf_prepare.py backend/tests/test_module2_visual_layout_selector.py backend/tests/test_module2_visual_status_builder.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_*.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Parser DOCX Bootstrap Extraction

After the visual execution chain was removed from `parser.py`, the next safest
remaining setup seam was the DOCX dispatch/content construction chain.

This chain was still dominated by constructor composition for:

- DOCX via PDF conversion runtime
- top-level document dispatch runtime
- DOCX enrichment runtime
- DOCX native document runtime
- DOCX chart-xml merge runtime

These responsibilities were still bootstrap-only wiring. They were not DOCX parse policy changes.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_docx_bootstrap_runtime.py`

This new runtime now owns grouped DOCX bootstrap wiring for:

- `_docx_via_pdf_runtime`
- `_document_dispatch_runtime`
- `_docx_enrichment`
- `_docx_document_runtime`
- `_docx_chart_merge_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that whole DOCX runtime family through
`ParserDocxBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserDispatchBundleRuntime` and `ParserDocxContentBundleRuntime` still own DOCX kwarg shaping
- `ParserDependencyBundleRuntime` still owns DOCX enrichment kwarg bundling
- `DocxViaPdfRuntime`, `DocumentDispatchRuntime`, `DocxEnrichmentRuntime`, `DocxDocumentRuntime`, and `DocxChartMergeRuntime` still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no DOCX routing policy, DOCX native parsing policy, media enrichment policy, or chart merge policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_docx_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/module2/app/core/parser_docx_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_docx_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_docx_bootstrap_runtime.py backend/tests/test_module2_docx_via_pdf_runtime.py backend/tests/test_module2_document_dispatch_runtime.py backend/tests/test_module2_docx_enrichment.py backend/tests/test_module2_docx_document_runtime.py backend/tests/test_module2_docx_chart_merge_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_*.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that parser entry bridges, bootstrap support wiring, document-table bootstrap wiring,
visual-payload bootstrap wiring, image bootstrap wiring, vision-transport bootstrap wiring,
visual profile/context bootstrap wiring, visual execution bootstrap wiring, and DOCX bootstrap
wiring are all out of `parser.py`, the next safest directions are:

- re-evaluate whether remaining `pdf_ocr` / `pdf_native` constructor blocks still justify further parser splitting
- if the remaining parser blocks are no longer “mostly wiring”, stop shrinking parser and shift focus to dead-code cleanup / packaging boundaries
- continue refusing any migration step that would weaken the preserved mainline `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Parser PDF Bootstrap Extraction

After the DOCX bootstrap chain was removed from `parser.py`, the next safest
remaining setup seam was the PDF OCR/native construction chain.

This chain was still dominated by constructor composition for:

- PDF OCR fallback runtime
- native PDF parse runtime

Even though the callback graph is large, parser-side behavior was still only:

- build dependency bundle
- instantiate runtime
- assign runtime attribute

That made it suitable for one more bootstrap-only extraction without changing OCR/native policy.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_pdf_bootstrap_runtime.py`

This new runtime now owns grouped PDF bootstrap wiring for:

- `_pdf_ocr_runtime`
- `_pdf_native_parse_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that PDF runtime pair through
`ParserPdfBootstrapRuntime` rather than carrying the bundle wiring inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserDependencyBundleRuntime` still owns PDF OCR/native kwarg bundling
- `PdfOcrRuntime` and `PdfNativeParseRuntime` still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no OCR page-budget policy, native parse policy, or Gemini-vision trigger policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_pdf_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/module2/app/core/parser_pdf_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_pdf_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_pdf_bootstrap_runtime.py backend/tests/test_module2_pdf_ocr_runtime.py backend/tests/test_module2_pdf_native_parse_runtime.py backend/tests/test_module2_parser_pdf_entry_runtime.py backend/tests/test_module2_pdf_parse_runtime.py backend/tests/test_module2_pdf_visual_parse_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_*.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Parser Semantic Bootstrap Extraction

After the PDF bootstrap chain was removed from `parser.py`, the next safest
remaining setup seam was the OCR/figure semantic foundation construction chain.

This chain was still dominated by constructor composition for:

- OCR table inference runtime
- figure text runtime
- table pruning runtime
- figure inference runtime
- content normalization runtime

These responsibilities were still bootstrap-only wiring. They were not semantic rule changes.

### What Was Extracted In This Increment

This wave introduced:

- `backend/module2/app/core/parser_semantic_bootstrap_runtime.py`

This new runtime now owns grouped semantic bootstrap wiring for:

- `_ocr_table_inference`
- `_figure_text_runtime`
- `_table_pruning_runtime`
- `_figure_inference`
- `_content_normalization_runtime`

At the same time, `backend/module2/app/core/parser.py` was reduced further so it now
builds that semantic runtime family through
`ParserSemanticBootstrapRuntime` rather than carrying the constructor chain inline.

### Why This Is Still Safe

This keeps the migration responsibility-preserving rather than behavior-reducing:

- `ParserOcrTableInferenceBundleRuntime` still owns OCR table threshold/callback kwarg shaping
- `ParserSemanticFoundationBundleRuntime` still owns figure/content semantic kwarg shaping
- `OcrTableInferenceRuntime`, `FigureTextRuntime`, `TablePruningRuntime`, `FigureInferenceRuntime`, and `ContentNormalizationRuntime` still own the actual behavior
- parser-side callers still consume the same runtime attributes after construction
- no OCR table inference policy, figure cue policy, table pruning policy, or normalization policy was changed

### New Regression Coverage Added In This Increment

- `backend/tests/test_module2_parser_semantic_bootstrap_runtime.py`
- `backend/tests/test_module2_parser_bootstrap_runtime.py` updated for the new bootstrap member

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_bootstrap_runtime.py backend/module2/app/core/parser_semantic_bootstrap_runtime.py backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_semantic_bootstrap_runtime.py`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_parser_bootstrap_runtime.py backend/tests/test_module2_parser_semantic_bootstrap_runtime.py backend/tests/test_module2_figure_semantics.py backend/tests/test_module2_figure_vision_payload.py backend/tests/test_module2_visual_figure_builder.py backend/tests/test_module2_table_payload_runtime.py backend/tests/test_module2_content_normalization_runtime.py backend/tests/test_module2_table_pruning_runtime.py backend/tests/test_module2_parser_visual_payload_bootstrap_runtime.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_module2_*.py -q`
- `PYTHONPATH=backend python -m pytest backend/module2/tests/test_parse_document_in_subprocess.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_create_app_routes.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py backend/tests/test_extraction_module2_execution_facade.py backend/tests/test_assistant_router.py backend/tests/test_auth_repository.py backend/tests/test_module2_extraction_support_router.py -q`

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that parser entry bridges, bootstrap support wiring, document-table bootstrap wiring,
visual-payload bootstrap wiring, image bootstrap wiring, vision-transport bootstrap wiring,
visual profile/context bootstrap wiring, visual execution bootstrap wiring, DOCX bootstrap wiring,
PDF bootstrap wiring, and semantic bootstrap wiring are all out of `parser.py`, the next safest directions are:

- stop treating parser shrinkage as the default goal and reassess whether any remaining `_init_*` segments are still mostly wiring
- if the remaining parser sections are now dominated by behavior rather than construction, shift the migration frontier to dead-code cleanup, packaging boundaries, and unused legacy process removal
- continue refusing any change that weakens the preserved mainline `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Desktop Packaging Boundary Tightening

This increment deliberately did **not** continue forcing more code out of `parser.py`.
Instead, it moved to the safer and higher-yield frontier identified above:

- packaging boundary cleanup
- stale desktop output cleanup
- desktop verification hardening

### Why This Increment Was Safe

The goal here was to remove obviously non-runtime payload from desktop builds without touching
document parsing behavior, extraction orchestration, or the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

No parser policy, extraction fallback policy, auth behavior, assistant prompt behavior, or
module4 sync behavior was changed in this increment.

### What Was Changed

The desktop/tooling layer was tightened in four places:

- `package.json`
  - added `desktop:clean`
  - updated `desktop:pack` and `desktop:dist` to clean stale `dist-electron` output first
- `scripts/clean-desktop-output.cjs`
  - new safe cleanup utility that only removes desktop output paths inside the workspace
- `electron-builder.json`
  - stopped duplicating `scripts/**/*.cjs` into app `files`
  - excluded extra non-runtime payload from backend resources:
    - `trace_rois`
    - `backend/module2/tools`
    - `backend/module2/check_db.py`
- `scripts/desktop-doctor.cjs`
  - now detects incomplete packaged output roots more accurately
  - now explicitly verifies absence of:
    - legacy nested module2 backend tree
    - legacy `trace_rois`
    - `backend/module2/tools`
    - `backend/module2/check_db.py`
    - `backend/module4/workspaces`

### Important Boundary Decision Preserved

`backend/module2/.cache` was **not** blanket-excluded.

That was intentional because the unified runtime still allows bundled MinerU runtime models under:

- `backend/module2/.cache/mineru_runtime_models`

Removing that directory would risk runtime regression in packaged mode.

### Validation Executed For This Increment

- `node -e "const fs=require('fs'); JSON.parse(fs.readFileSync('package.json','utf8')); JSON.parse(fs.readFileSync('electron-builder.json','utf8')); console.log('json-ok');"`
- `node scripts/clean-desktop-output.cjs --dry-run`
- `node scripts/clean-desktop-output.cjs`
- `npm run desktop:pack`
- `node scripts/desktop-doctor.cjs`

### Packaged Output Result

`desktop:pack` now succeeds again, and `desktop-doctor` passes with packaged checks confirming:

- packaged runtime root exists
- unified backend entry exists
- frontend dist exists
- packaged `start-backend-fastapi.cjs` exists
- packaged `.venv-module2-py311` exists
- packaged module2 artifacts are absent
- packaged legacy nested backend tree is absent
- packaged `trace_rois` are absent
- packaged `backend/module2/tools` is absent
- packaged `backend/module2/check_db.py` is absent
- packaged module4 workspaces are absent

### Desktop Smoke Follow-Up Completed For Backend Mode

After the first packaging-boundary pass, packaged smoke was still hanging because:

- gateway readiness required healthy `module2`
- but packaged unified extraction keeps `module2` sidecar lazy by default
- so `/gateway/ready` remained degraded until something explicitly forced `ensure_sidecar=True`

This was resolved in `scripts/desktop-smoke.cjs` by:

- switching the default smoke mode to packaged backend mode
- warming `module2` sidecar through `GET /extract/jobs/status/desktop_smoke_probe`
  - a `404 Extraction job not found` response is treated as successful warmup because it proves the sidecar is alive
- checking readiness with an explicit scope
  - backend smoke uses `scope=backend`
- replacing open-ended polling behavior with bounded timeout-based diagnostics
- surfacing a single explicit early-exit error if the packaged process exits before smoke completes

`package.json` now reflects this with:

- `desktop:smoke` -> backend-mode packaged smoke
- `desktop:smoke:electron` -> optional explicit electron-mode smoke

### Validation Executed For Smoke Follow-Up

- `node --check scripts/desktop-smoke.cjs`
- `npm run desktop:smoke`

### Current Smoke Status

Backend-mode packaged smoke now passes and verifies:

- packaged executable launches
- unified FastAPI starts inside packaged runtime
- `module2` sidecar can be lazily warmed and becomes healthy
- gateway backend readiness becomes `ok`
- auth/module2/module4 all report healthy through packaged backend readiness

Electron-mode smoke remains an **optional manual follow-up** and is still environment-sensitive in the
current terminal session because the packaged desktop process exited before smoke completed.

So the current conclusion is:

- packaged output filtering is materially tighter and cleaner
- stale desktop build output is automatically cleaned before new packaging
- directory packaging succeeds
- packaged runtime content passes `desktop-doctor`
- backend-mode packaged smoke now passes and is suitable as the default automated desktop gate

## 2026-03-27 Increment: FastAPI Startup Topology Explicitization

After the desktop packaging boundary was tightened and backend-mode packaged smoke
was stable again, the next safest cleanup frontier was startup topology clarity.

Before this increment, backend start/dev entrypoints still mixed two concerns:

- generic backend orchestration
- FastAPI-first orchestration defaults

That arrangement was still operational, but it left the FastAPI topology too implicit.
For a project that is deliberately converging toward:

- unified FastAPI public entry
- preserved `auth`
- managed Module 2 sidecar behavior
- preserved Module 4 upstream

the backend launcher layer should describe those choices directly rather than only
through environment mutation and transitive `require(...)` chains.

### Why This Increment Was Safe

This increment only clarified process orchestration defaults.
It did **not** change:

- public API routes
- extraction job semantics
- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`
- Module 2 parse policy
- Module 4 graph behavior
- auth business logic ownership

In other words, it was topology clarification, not workflow simplification.

### What Was Changed

The launcher layer was tightened in five places:

- `scripts/backend-service-runner.cjs`
  - new shared helper for backend service selection and managed process lifecycle
- `scripts/start-backend.cjs`
  - now explicitly builds the generic backend topology through the shared runner
- `scripts/dev-backend.cjs`
  - now explicitly builds the generic dev topology through the shared runner
- `scripts/start-backend-fastapi.cjs`
  - now explicitly builds the FastAPI-first topology through the shared runner
- `scripts/dev-backend-fastapi.cjs`
  - now explicitly builds the FastAPI-first dev topology through the shared runner

### Topology Decision Made Explicit

The launcher defaults are now intentionally split into two stable modes.

Generic backend mode keeps the historical compatibility topology:

- `AUTH_COMPAT_ENABLED = true`
- `MODULE2_ENABLED = true`
- `MODULE4_ENABLED = true`

FastAPI backend mode now states the unified topology directly:

- `AUTH_COMPAT_ENABLED = false`
- `MODULE2_ENABLED = false`
- `MODULE4_ENABLED = true`

That means the FastAPI entry no longer "happens to behave correctly" only because a wrapper
mutated environment variables before delegating to another script.
It now declares its intended runtime shape at the composition root.

### Validation Executed For This Increment

- `node --check scripts/backend-service-runner.cjs`
- `node --check scripts/start-backend.cjs`
- `node --check scripts/dev-backend.cjs`
- `node --check scripts/start-backend-fastapi.cjs`
- `node --check scripts/dev-backend-fastapi.cjs`
- `npm run desktop:pack`
- `node scripts/desktop-doctor.cjs`
- `npm run desktop:smoke`

### Validation Result

This increment passed the same packaged regression gate that had already been established:

- directory packaging succeeds
- packaged runtime content still passes `desktop-doctor`
- packaged backend smoke still passes
- packaged `auth`, `module2`, and `module4` all report healthy readiness
- packaged Module 2 sidecar still warms lazily and becomes healthy
- packaged assistant/auth/module4 readiness remains intact behind the unified backend entry

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Updated Next Safe Slice

Now that the FastAPI backend topology is explicit and regression-verified, the next safest
migration frontier is **not** another speculative parser split.

The better next moves are:

- audit `package.json` `start:*` and `dev:*` entries and label which are canonical versus compatibility-only
- keep `start-auth`, `start-module2`, and `start-module4` for operational/debug use until callers truly disappear
- continue removing ambiguous legacy process paths only after packaged regression remains boring
- then return to high-value internal decomposition, prioritizing `backend/module4/app/main.py` orchestration seams over cosmetic parser shrinkage

## 2026-03-27 Increment: Canonical Start/Dev Command Convergence

Once the FastAPI startup topology was made explicit and regression-verified,
the next low-risk cleanup was to remove ambiguity at the root `npm` command layer.

Before this increment, the repository still exposed an inversion:

- desktop and packaged runtime paths were already FastAPI-first
- explicit `*:fastapi` commands were already the preferred unified entry
- but root `npm run dev` and `npm run start` still pointed at the older compatibility topology

That mismatch increased operator confusion and made the "correct" project entry
depend on remembering a special suffix rather than following the default command.

### What Was Changed

The command surface was converged in `package.json`:

- `dev` now points to `scripts/dev-all-fastapi.cjs`
- `start` now points to `scripts/start-backend-fastapi.cjs`
- `dev:backend` now points to `scripts/dev-backend-fastapi.cjs`
- `start:backend` now points to `scripts/start-backend-fastapi.cjs`

At the same time, the historical compatibility topology was preserved under explicit names:

- `dev:compat`
- `start:compat`
- `dev:backend:compat`
- `start:backend:compat`

This preserves no-downgrade behavior:

- the compatibility tree still exists when needed
- the unified FastAPI path is now the canonical default
- desktop and CLI defaults now point at the same architecture direction

### Documentation Updated Alongside The Commands

The operator-facing docs were updated so the command surface remains understandable:

- `backend/README.md`
- `backend/auth/README.md`

### Validation Executed For This Increment

- `node -e "const fs=require('fs'); const pkg=JSON.parse(fs.readFileSync('package.json','utf8')); console.log(pkg.scripts.dev, pkg.scripts.start)"`
- direct startup probe for `scripts/start-backend-fastapi.cjs`
  - warm Module 2 sidecar through `/extract/jobs/status/script_probe`
  - confirm `GET /gateway/ready?scope=backend`
- direct startup probe for `scripts/start-backend.cjs`
  - confirm compatibility topology still reaches backend readiness
- port cleanup confirmation for:
  - `3001`
  - `3003`
  - `8000`
  - `8100`

### Validation Result

Both launcher families still reached healthy backend readiness:

- FastAPI-first default topology passed
- compatibility topology also passed
- no listener residue remained after process-tree cleanup

This means the command-surface convergence did not remove the preserved workflow.

### Updated Next Safe Slice

With command defaults now aligned to the unified architecture, the next safe migration
priority should be:

- continue shrinking operator-facing ambiguity and dead process paths
- then shift the main code migration frontier toward `backend/module4/app/main.py`
- keep refusing any "cleanup" that would weaken the preserved mainline `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

## 2026-03-27 Increment: Module4 Medium-Grain Ingest Runtime Extraction

After the command surface was converged, the next migration step deliberately changed strategy.

Earlier Module 2 work had used many fine-grained runtime extractions to safely peel logic out of
oversized files. That was useful in the parser-heavy phase, but continuing the exact same pattern
inside Module 4 would have created too many new tiny files and increased operator cognitive load.

This increment therefore adopted a **medium-grain extraction** approach:

- move one coherent mainline responsibility cluster at a time
- prefer one substantial service module over many micro-files
- keep `main.py` compatible for tests and current callers through thin wrapper functions

### What Was Extracted

This wave introduced:

- `backend/module4/app/services/ingest_runtime.py`

This service now owns the main ingest/rebuild job pipeline responsibilities that had been embedded
directly in `backend/module4/app/main.py`, including:

- recoverable job replay
- job-stage update helpers
- alert emission helper
- per-document graph ingest orchestration
- batch ingest execution
- rebuild execution
- ingest job submission
- rebuild job submission
- input counting for rebuild planning

`backend/module4/app/main.py` now keeps the public route handlers and lifecycle composition, while
delegating the heavy ingest/rebuild execution path to this service module.

### Important Compatibility Decision

This increment did **not** remove the historic function names from `backend/module4/app/main.py`.

Thin wrapper functions were intentionally preserved for:

- `_process_document`
- `_run_document_ingest_job`
- `_run_ingest_job`
- `_run_rebuild_job`

This was important because the existing Module 4 test suite still monkeypatches those symbols on
`module4_main`. Preserving those names allowed the migration to reduce `main.py` concentration
without breaking current test hooks or operational expectations.

### Why This Increment Was Safe

This change preserved behavior while changing placement:

- no route contract was changed
- no graph schema contract was changed
- no alert/rule semantics were changed
- no evidence linking behavior was changed
- no rebuild semantics were simplified

The goal was structural concentration reduction, not workflow reduction.

### Validation Executed For This Increment

- `python -m py_compile backend/module4/app/main.py backend/module4/app/services/ingest_runtime.py backend/module4/app/services/__init__.py`
- `python -m pytest tests/test_module4_api.py -q` executed from `backend/module4`

### Validation Result

The Module 4 API regression suite passed after this extraction:

- 19 tests passed
- monkeypatch-based tests against `module4_main._process_document` still worked
- ingest, rebuild, evidence, alerts, graph file views, explain, simulate, and health endpoints all remained covered by the existing suite

### Structural Result

This increment reduced concentration in the Module 4 entry file while avoiding file explosion:

- `backend/module4/app/main.py` decreased materially
- one medium-grain service file now carries the ingest/rebuild orchestration cluster
- the migration direction is now better aligned with "fewer, more coherent files" rather than "many tiny runtime shards"

### Updated Next Safe Slice

With the ingest/rebuild mainline now partially lifted out of `backend/module4/app/main.py`,
the next safest Module 4 moves are:

- continue extracting **coherent clusters**, not micro-helpers
- next prefer graph view / evidence / explain-simulate support seams over tiny utility fragmentation
- keep preserving wrapper compatibility where tests or callers still rely on `module4_main`

## 2026-03-27 Increment: Module4 Medium-Grain Query Runtime Extraction

After the ingest/rebuild cluster was moved out of `backend/module4/app/main.py`, the next
highest-yield seam was not another micro-helper split.

The safer move was to lift out the entire **query-side runtime cluster** as one coherent service:

- graph file listing and detail shaping
- tenant/file graph views
- neighborhood and node detail composition
- alert/rule/evidence response shaping
- graph/evidence normalization and projection runtime status shaping

This increment therefore continued the same medium-grain strategy instead of returning to a
"one helper, one file" migration pattern.

### What Was Extracted

This wave introduced:

- `backend/module4/app/services/query_runtime.py`

This service now owns the main query-side response assembly that had still been concentrated in
`backend/module4/app/main.py`, including:

- `normalize_graph_node_row`
- `normalize_graph_edge_row`
- `normalize_graph_file_row`
- `normalize_alert_row`
- `normalize_rule_row`
- `normalize_evidence_row`
- `projection_runtime_status`
- node and edge evidence loading
- graph stats construction
- graph file / tenant graph response composition
- alert action / evidence / rules response composition

At the same time, `backend/module4/app/main.py` was rewired so the public route handlers delegate
to `query_runtime.py` while preserving the existing API contracts.

### Important Compatibility Decision

This increment again preserved compatibility at the `module4_main` surface instead of forcing all
tests and callers to move immediately.

Thin wrapper functions were intentionally kept in `backend/module4/app/main.py` for the symbols
that are still used by the current explain path or monkeypatch-based tests:

- `_normalize_graph_node_row`
- `_load_evidence_for_node`
- `_run_document_ingest_job`
- `_run_ingest_job`
- `_run_rebuild_job`
- `_update_job_stage`

During regression, strict downstream tests exposed that the first ingest extraction had bypassed
the historical `_update_job_stage` monkeypatch seam and had also assumed every storage double
implemented `assign_graph_version`.

Those compatibility seams were restored without rolling back the service split:

- `run_document_ingest_job(...)` now accepts an optional `update_job_stage_callback`
- `backend/module4/app/main.py` passes `_update_job_stage` into that service
- graph version assignment now only runs when the storage implementation actually exposes
  `assign_graph_version`

This keeps the migrated runtime aligned with the old test seam while preserving the new service
boundary.

### Why This Increment Was Safe

The change remained placement-oriented rather than behavior-reducing:

- no public route path was changed
- no response schema contract was changed
- no alert, evidence, rule, or graph semantics were simplified
- no ingest/rebuild job semantics were removed
- `module4_healthz` still reports the same projection runtime meaning, but now through the
  service layer

The goal was to thin `main.py` while keeping the preserved mainline intact:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Validation Executed For This Increment

- `python -m py_compile backend/module4/app/main.py backend/module4/app/services/ingest_runtime.py backend/module4/app/services/query_runtime.py backend/module4/app/services/__init__.py`
- `python -m pytest tests/test_module4_api.py -q` executed from `backend/module4`
- `python -m pytest tests/test_module4_strict_downstream_sync.py -q` executed from `backend/module4`
- full Module 4 regression suite executed from `backend/module4`:
  - all `tests/test_module4*.py`

### Validation Result

This increment passed the full current Module 4 test surface:

- 45 Module 4 tests passed
- query routes now delegate through `query_runtime.py`
- strict monkeypatch/downstream compatibility checks still pass
- no evidence from this increment indicates regression in the preserved workflow line

### Structural Result

This increment materially reduced `backend/module4/app/main.py` concentration again while still
avoiding file explosion:

- `backend/module4/app/main.py` is now approximately `1549` lines
- `backend/module4/app/services/ingest_runtime.py` carries the ingest/rebuild cluster
- `backend/module4/app/services/query_runtime.py` carries the query/normalization cluster

That means Module 4 is no longer just "service folder exists" in name only.
It now has two real medium-grain service boundaries carrying the two heaviest runtime clusters.

### Updated Next Safe Slice

Now that Module 4 ingest and query mainlines both have real service boundaries, the next safest
Module 4 migration target is:

- extract the remaining **explain / simulate** orchestration cluster as one coherent service block

After that, the next worthwhile cleanup is:

- remove residual dead query-era helpers and imports from `backend/module4/app/main.py`
- reassess whether any remaining storage-shaping logic still belongs in the entry file
- only then consider deeper packaging and legacy process retirement work

## 2026-03-27 Increment: Module4 Explain/Simulate Runtime Extraction

Once the ingest cluster and query cluster were both moved behind service boundaries, the next
best Module 4 target was no longer graph list/detail code.

The remaining concentration hot spot in `backend/module4/app/main.py` was the
**explain / simulate orchestration block**:

- alert-based explanation assembly
- node-based explanation assembly
- simulation context inflation and reuse
- deterministic rule simulation over inline or reused alert context

This was a good next slice because it was a coherent orchestration cluster, but still smaller
and safer than touching storage, GraphRAG import, or public route contracts.

### What Was Extracted

This wave introduced:

- `backend/module4/app/services/insight_runtime.py`

This service now owns:

- explain response composition
- simulate response composition
- simulation context normalization
- simulation context reuse from alert payloads

`backend/module4/app/main.py` now keeps the route handlers and shared dependency wiring, while
delegating the explain/simulate orchestration body into the service layer.

### Important Boundary Decision

This increment deliberately did **not** move the lower-level deterministic rule evaluation logic
out of `main.py`.

That logic is still shared with the ingest path through:

- `_rule_scope`
- `_evaluate_rule_hit`

So the extraction boundary stayed at the orchestration layer:

- `main.py` still owns shared rule-policy helpers
- `insight_runtime.py` owns explain/simulate coordination

This keeps the service split medium-grain instead of fragmenting shared policy into several small files.

### Why This Increment Was Safe

The route contracts did not change:

- `/module4/explain`
- `/module4/simulate`

The request/response schemas also stayed the same:

- `ExplainRequest` / `ExplainResponse`
- `SimulateRequest` / `SimulateResponse`

The migration was again placement-oriented rather than behavior-reducing:

- alert context reuse still works
- inline context simulation still works
- node explanation still resolves graph evidence
- no storage schema or graph query semantics were changed

### Validation Executed For This Increment

- `python -m py_compile backend/module4/app/main.py backend/module4/app/services/ingest_runtime.py backend/module4/app/services/query_runtime.py backend/module4/app/services/insight_runtime.py backend/module4/app/services/__init__.py`
- `python -m pytest tests/test_module4_api.py -q` executed from `backend/module4`
- `python -m pytest tests/test_module4_strict_downstream_sync.py -q` executed from `backend/module4`
- full Module 4 regression suite executed from `backend/module4`:
  - all `tests/test_module4*.py`

### Validation Result

This increment also passed the current full Module 4 regression surface:

- 45 Module 4 tests passed
- simulate tests covering inline deterministic contexts still passed
- simulate tests covering alert-payload context reuse still passed
- strict downstream compatibility tests still passed

No evidence from this increment indicates regression in the preserved mainline:

- `docx -> PDF -> MinerU -> Gemini -> assistant/auth/module4`

### Structural Result

Module 4 now has three real medium-grain runtime service boundaries:

- `backend/module4/app/services/ingest_runtime.py`
- `backend/module4/app/services/query_runtime.py`
- `backend/module4/app/services/insight_runtime.py`

At this point:

- `backend/module4/app/main.py` is down to approximately `1348` lines
- the heaviest non-entry orchestration clusters are no longer embedded directly in the route file

That means the Module 4 decomposition is no longer in "early service folder only" territory.
It has crossed into a meaningful mid-stage internal split.

### Updated Next Safe Slice

With ingest, query, and explain/simulate all now on service boundaries, the next safest Module 4
work is not another immediate new file by default.

The better next moves are:

- audit `backend/module4/app/main.py` for residual dead helpers and imports left behind by the three migrations
- identify whether any remaining storage-shaping or health/lifecycle glue should stay in `main.py`
- only create another service file if a remaining block is still a genuinely coherent cluster

This is more aligned with the current project constraint:

- do not keep creating too many tiny files

## 2026-03-27 Increment: Module4 Artifact Support Runtime Extraction

After the ingest, query, and explain/simulate orchestration clusters had all been lifted out of
`backend/module4/app/main.py`, the biggest remaining concentration was no longer route logic.

The next coherent block was the shared **artifact support runtime** used across multiple Module 4
service helpers:

- artifact text cleanup
- low-signal filtering
- artifact snippet generation
- artifact display-name selection
- artifact attribute shaping and merge helpers

This block was still living inside `main.py` even though it was already acting like a reusable
pure helper layer for the service runtime family.

### What Was Extracted

This wave introduced:

- `backend/module4/app/services/artifact_runtime.py`

This service-support file now owns the shared pure artifact helpers that were previously embedded
in `backend/module4/app/main.py`, including:

- `_as_dict`
- `_as_list`
- `_artifact_summary_snippet`
- `_artifact_display_name_from_attrs`
- `_normalize_artifact_attrs_for_response`
- `_merge_artifact_node_attrs`
- `_build_artifact_node_attrs`
- `_build_artifact_node_display_name`
- `_choose_artifact_display_name`

`backend/module4/app/main.py` now imports those helpers directly instead of carrying the
implementation inline.

### Why This Increment Was Safe

This was the safest kind of refactor in the whole Module 4 program:

- the extracted functions are pure helpers
- no route contract changed
- no DB contract changed
- no graph schema contract changed
- no ingest/query/explain/simulate public behavior was intentionally changed

The shift was structural:

- helper code moved out of the entry file
- helper call sites remained the same
- service helper wiring still points to the same logical functions, now imported from the support module

### Validation Executed For This Increment

- `python -m py_compile backend/module4/app/main.py backend/module4/app/services/artifact_runtime.py backend/module4/app/services/ingest_runtime.py backend/module4/app/services/query_runtime.py backend/module4/app/services/insight_runtime.py backend/module4/app/services/__init__.py`
- `python -m pytest tests/test_module4_api.py -q` executed from `backend/module4`
- `python -m pytest tests/test_module4_strict_downstream_sync.py -q` executed from `backend/module4`
- full Module 4 regression suite executed from `backend/module4`:
  - all `tests/test_module4*.py`

### Validation Result

This increment also passed the full current Module 4 regression surface:

- 45 Module 4 tests passed
- no ingest/rebuild regression evidence appeared
- no query/evidence/alerts regression evidence appeared
- no explain/simulate regression evidence appeared

### Structural Result

With this increment complete:

- `backend/module4/app/main.py` is now approximately `821` lines
- `backend/module4/app/services/artifact_runtime.py` is approximately `518` lines

That means the Module 4 entry file is now much closer to its intended role:

- application composition root
- route layer
- lifecycle and dependency wiring

rather than a mixed file containing pure artifact helpers, query assembly, ingest orchestration,
and explain/simulate logic all together.

### Updated Stage Judgment

Module 4 should no longer be described as merely in an "early service split" state.

The more accurate description now is:

- public routes still live in `backend/module4/app/main.py`
- shared pure helper support has been extracted
- ingest orchestration has been extracted
- query shaping has been extracted
- explain/simulate orchestration has been extracted

So Module 4 is now in a **meaningful mid-stage to late-mid-stage internal decomposition** state,
not an early-stage one.

### Updated Next Safe Slice

Now that the remaining oversized pure helper block is also out of `main.py`, the next safest work
is not necessarily another new file.

The better next actions are:

- audit the remaining `main.py` code for whether any residual glue is still too business-heavy for an entry file
- decide whether health/lifecycle wiring should remain in `main.py` as composition-root responsibility
- resist creating more files unless another block is clearly a coherent runtime cluster

## 2026-03-27 Increment: Module4 Rule Runtime Extraction

After artifact support was extracted, the biggest remaining non-entry concern inside
`backend/module4/app/main.py` was the shared deterministic rule policy cluster:

- rule scope derivation
- rule expression evaluation
- template rendering for rule hit text
- rule hit payload assembly

This cluster was still serving both:

- ingest-time rule evaluation
- simulate-time rule evaluation

That made it a good final medium-grain candidate because it was:

- shared
- pure logic
- not route-specific
- not lifecycle-specific

### What Was Extracted

This wave introduced:

- `backend/module4/app/services/rule_runtime.py`

This service-support file now owns the deterministic rule policy helpers that had still been
embedded in `backend/module4/app/main.py`, including:

- `SUPPORTED_RULE_KINDS`
- `_rule_scope`
- `_evaluate_rule_hit`
- rule expression comparison and path lookup helpers
- template expansion helpers used to build rule-hit title/summary text

At the same time, `backend/module4/app/services/ingest_runtime.py` was updated to reuse
`SUPPORTED_RULE_KINDS` from the same source instead of maintaining a separate duplicate constant.

### Why This Increment Was Safe

This was another pure policy extraction rather than a workflow rewrite:

- no route changed
- no request/response schema changed
- no graph persistence contract changed
- no auth, assistant, or extraction gateway contract changed

The business meaning remained the same:

- ingest still evaluates deterministic rules
- simulate still evaluates deterministic rules
- the same rule-hit payload structure is still emitted downstream

### Validation Executed For This Increment

- `python -m py_compile backend/module4/app/main.py backend/module4/app/services/rule_runtime.py backend/module4/app/services/artifact_runtime.py backend/module4/app/services/ingest_runtime.py backend/module4/app/services/query_runtime.py backend/module4/app/services/insight_runtime.py backend/module4/app/services/__init__.py`
- `python -m pytest tests/test_module4_api.py -q` executed from `backend/module4`
- `python -m pytest tests/test_module4_strict_downstream_sync.py -q` executed from `backend/module4`
- full Module 4 regression suite executed from `backend/module4`:
  - all `tests/test_module4*.py`

### Validation Result

This increment also passed the full current Module 4 regression surface:

- 45 Module 4 tests passed
- no ingest-time rule regression evidence appeared
- no simulate-time rule regression evidence appeared
- strict downstream compatibility tests still passed

### Structural Result

With this increment complete:

- `backend/module4/app/main.py` is now approximately `722` lines
- the remaining code in `main.py` is much closer to:
  - environment/config bootstrapping
  - dependency assembly
  - lifecycle control
  - route layer
  - compatibility wrappers still needed by tests/current callers

At this point, Module 4's major internal responsibilities are materially separated into:

- `artifact_runtime.py`
- `rule_runtime.py`
- `ingest_runtime.py`
- `query_runtime.py`
- `insight_runtime.py`

### Updated Stage Judgment

At this point, the accurate description of Module 4 is no longer just "mid-stage decomposition".

It is now closer to:

- **late-mid-stage decomposition with the main entry file mostly reduced to composition-root responsibilities**

This is a meaningful threshold because the remaining content in `backend/module4/app/main.py`
is now mostly the kind of code that often should remain in an entry file.

### Updated Next Safe Slice

Now that both the shared helper layer and the shared rule-policy layer are out of `main.py`,
the next safest move is **not automatically another extraction**.

The better next move is:

- freeze the current Module 4 internal boundaries
- only do another split if a clearly oversized business cluster reappears
- otherwise shift attention back to broader backend convergence and packaging/workflow validation

## 2026-03-27 Increment: Unified Extraction Artifact/Preview Runtime Extraction

After the Module 4 entry file had already crossed into a late-mid-stage decomposition state,
the highest-value next migration target was no longer another Module 4 split.

The better target shifted back to the unified FastAPI extraction gateway, specifically:

- `backend/app/modules/extraction/service.py`

At that point, the extraction service file was still carrying a large mixed cluster that was not
really "service orchestration" anymore:

- artifact root and artifact file serving helpers
- office preview request validation
- office preview in-memory job state
- office preview disk record recovery
- office preview threaded conversion runner

Those responsibilities were tightly coupled with each other, but only loosely coupled with the
rest of `ExtractionService`.

This made them a good medium-grain extraction candidate.

### What Was Extracted

This wave introduced:

- `backend/app/modules/extraction/artifact_runtime.py`

This new medium-grain runtime now owns:

- artifact path resolution
- artifact root selection
- artifact file serving and HEAD response shaping
- office preview job state and locking
- office preview disk-cache record loading and recovery
- office preview conversion execution and artifact materialization

`backend/app/modules/extraction/service.py` now delegates those responsibilities into the runtime
layer while preserving the existing public route contracts and helper names.

### Important Compatibility Decision

This increment intentionally preserved compatibility at the extraction service surface instead of
forcing all callers and tests to move immediately.

The following names still remain available from `backend/app/modules/extraction/service.py` as
compatibility wrappers or re-exported state:

- `office_preview_jobs`
- `office_preview_lock`
- `serve_artifact_file(...)`
- `resolve_artifact_path(...)`
- `artifact_root_dir(...)`
- `build_head_response_for_file(...)`
- `resolve_module2_path(...)`

This mattered because the current backend test fixtures still clear `office_preview_jobs` through
the service module, and the migration goal here was responsibility transfer, not surface churn.

### Why This Increment Was Safe

This was a boundary cleanup, not a workflow rewrite:

- no `/extract/*` route changed
- no artifact URL contract changed
- no office preview job payload shape changed
- no cache-clear response contract changed
- no Electron-facing unified backend contract changed

The preserved workflow remains:

- `docx -> PDF preview -> extraction artifact exposure -> downstream parse/assistant/module4 chain`

### Validation Executed For This Increment

- `python -m py_compile backend/app/modules/extraction/service.py backend/app/modules/extraction/artifact_runtime.py backend/tests/test_extraction_artifact_runtime.py`
- `python -m pytest backend/tests/test_extraction_artifact_runtime.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py -q`
- `python -m pytest backend/tests/test_extraction*.py -q` executed from the repository root

### Validation Result

This increment passed the current extraction regression surface:

- extraction-specific syntax checks passed
- targeted artifact/preview/service/router tests passed
- the full current `backend/tests/test_extraction*.py` suite passed:
  - 24 tests passed

No evidence from this increment indicates regression in the unified extraction mainline.

### Structural Result

With this increment complete:

- `backend/app/modules/extraction/service.py` dropped from roughly `1071` lines to roughly `527` lines
- `backend/app/modules/extraction/artifact_runtime.py` now carries the cohesive artifact/preview runtime cluster in roughly `444` lines

That means the unified extraction layer has now started its own meaningful medium-grain
decomposition instead of leaving all runtime concerns embedded in one service file.

### Updated Next Safe Slice

Now that artifact and office preview responsibilities are out of the extraction service, the next
best extraction-layer target is no longer cache-clear glue.

The next safest move is:

- extract the remaining `summary / trace` runtime cluster from `backend/app/modules/extraction/service.py`

That is now the best follow-up because it is:

- coherent
- mostly pure logic
- contract-preserving
- easy to regression-test without touching the public gateway surface

The recommended order after this increment is:

1. keep the new extraction artifact/preview runtime boundary stable
2. extract `summarize_document(...)` and `trace_locate(...)` plus their pure helpers
3. reassess whether any residual cache-clear or header-forward helpers are still large enough to move
4. avoid creating new files unless the next block is again a genuinely coherent medium-grain cluster

## 2026-03-27 Increment: Unified Extraction Summary/Trace Runtime Extraction

After the artifact and office-preview responsibilities were moved out of
`backend/app/modules/extraction/service.py`, the next best extraction-layer target became the
remaining `summary / trace` logic cluster.

At that point, the service file was still carrying:

- summary assembly for extracted-document payloads
- trace-hit derivation from extraction results
- trace-hit filtering and result shaping
- figure display-kind inference for summary presentation

This cluster was highly coherent and mostly pure logic, which made it a better next target than
the remaining cache-clear and header-forward glue.

### What Was Extracted

This wave introduced:

- `backend/app/modules/extraction/summary_runtime.py`

`backend/app/modules/extraction/service.py` now delegates:

- `summarize(...)`
- `trace_locate(...)`
- compatibility wrappers `summarize_document(...)` and `trace_locate(...)`

to the new runtime file.

### Important Compatibility Decision

This increment did **not** hand-copy the historical summary text constants into the new file.

During migration, direct literal transfer exposed an encoding-risk issue in terminal rendering for
the old Chinese summary text block. Instead of changing wording or risking drift, the new
`summary_runtime.py` now acts as a thin bridge over the already-stable Module 2 document-tools
support runtime:

- it reuses the existing summary text behavior from
  `backend/module2/app/runtime/document_tools_support.py`
- it keeps unified extraction response schemas in `backend/app/modules/extraction/schemas.py`
- it still owns the unified-gateway side trace-hit bootstrap when `document.trace_hits` is empty

This preserved behavior while avoiding an unsafe text-literal migration.

### Why This Increment Was Safe

This was still a contract-preserving structural change:

- no `/extract/summarize` route changed
- no `/extract/trace/locate` route changed
- no request or response schema changed
- no office preview, artifact, assistant, auth, or Module 4 route changed

The unified extraction gateway remained the public owner of these endpoints, while the summary and
trace logic simply moved behind a runtime boundary.

### Validation Executed For This Increment

- `python -m py_compile backend/app/modules/extraction/service.py backend/app/modules/extraction/summary_runtime.py backend/tests/test_extraction_summary_runtime.py`
- `python -m pytest backend/tests/test_extraction_summary_runtime.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py -q`
- `python -m py_compile backend/tests/test_extraction_runtime_routes.py`
- `python -m pytest backend/tests/test_extraction_runtime_routes.py backend/tests/test_extraction_summary_runtime.py backend/tests/test_extraction_service.py backend/tests/test_extraction_router.py -q`
- full extraction regression executed from the repository root:
  - `python -m pytest backend/tests/test_extraction*.py -q`

### Validation Result

This increment passed the current extraction regression surface:

- summary runtime syntax checks passed
- targeted summary/service/router tests passed
- real summarize/trace route integration tests passed
- the full current extraction suite passed:
  - 28 tests passed

No evidence from this increment indicates regression in the unified extraction mainline.

### Structural Result

With this increment complete:

- `backend/app/modules/extraction/service.py` is now approximately `231` lines
- `backend/app/modules/extraction/summary_runtime.py` now carries the summary/trace logic in
  approximately `126` lines

This means the unified extraction service file is now much closer to its intended role:

- gateway orchestration
- dependency delegation
- cache-clear merge glue
- compatibility-level helper exports

rather than a mixed file that also owns preview execution, artifact serving, summary assembly,
and trace filtering internals.

### Updated Stage Judgment

At this point, unified extraction should no longer be described as merely having a "single large
service file with a few helpers moved out."

It is now better described as:

- a stable unified FastAPI extraction gateway
- with real medium-grain runtime boundaries for:
  - artifact and office-preview support
  - summary and trace support
  - sidecar/upstream/execution coordination
  - shadow job compatibility

That is a meaningful internal decomposition milestone, even though the public extraction surface
remains unchanged.

### Updated Next Safe Slice

Now that both of the major coherent clusters are out of `backend/app/modules/extraction/service.py`,
the next safest move is **not automatically another extraction-layer file**.

The better next actions are:

1. freeze the new extraction boundaries and keep them stable
2. only move `_normalize_cache_clear_scope`, `_merge_cache_clear_payload`, or
   `_forward_module2_context_headers` if they later grow again
3. shift the main migration focus back to the broader backend program:
   - Module 2 parser/core remaining concentration
   - packaging boundary cleanup
   - workflow-level regression validation

## 2026-03-27 Increment: Module2 Main Schema Pipeline Assembly Extraction

After unified extraction was reduced to stable runtime boundaries, the next safest backend target
was not another extraction-layer split.

The better next target shifted back to `backend/module2/app/main.py`, which had become less of a
route/business file and more of a long top-level assembly script.

At that point, one of the clearest remaining concentration zones inside `main.py` was the schema
pipeline assembly cluster:

- result-filter bundle wiring
- schema context bundle wiring
- schema fields/request/inference wiring
- schema llm/semantics/selection wiring
- schema resolution/timeout wiring

This cluster was coherent, assembly-oriented, and lower risk than touching the parser core again.

### What Was Extracted

This wave introduced:

- `backend/module2/app/runtime/main_schema_pipeline_bundle.py`

This new runtime assembly file now owns the coordinated construction of:

- `result_filter_bundle`
- `schema_context_bundle`
- `schema_fields_bundle`
- `schema_request_bundle`
- `schema_inference_bundle`
- `schema_llm_bundle`
- `schema_semantics_bundle`
- `schema_selection_bundle`
- `schema_resolution_bundle`
- `schema_timeout_bundle`

`backend/module2/app/main.py` now calls a single
`build_module2_main_schema_pipeline_bundle(...)` entry and then exposes the returned runtime
members back onto the historical module-level names used by the rest of the file.

### Important Boundary Decision

This increment deliberately kept the Chinese token literals and schema cue constants in
`backend/module2/app/main.py`.

That was important for two reasons:

- those literals are part of the current source-level UTF-8 safety checks
- the goal of this increment was assembly concentration reduction, not another round of text-asset relocation

So this wave extracted assembly wiring, but did **not** try to move every constant out of the
entry file.

### Why This Increment Was Safe

This was an assembly refactor, not a behavior rewrite:

- no `/extract/*` route changed
- no parser contract changed
- no schema inference rule implementation changed
- no office-preview, assistant, auth, or Module 4 contract changed

The schema runtime pieces that existed before still exist after this increment; they are just now
assembled behind one coherent runtime-bundle seam instead of being wired inline in `main.py`.

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_schema_pipeline_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_schema_pipeline_bundle.py`
- Module 2 main entry import smoke executed with `backend/module2` as the package root:
  - `import app.main as main_module`
  - verified `main_module.module2_main_entry_bundle` and `main_module.module2_main_schema_resolution_bundle`
- targeted schema/main tests:
  - `python -m pytest backend/tests/test_module2_main_schema_pipeline_bundle.py backend/tests/test_module2_main_source_literals.py backend/tests/test_module2_main_schema_context_bundle.py backend/tests/test_module2_main_schema_resolution_bundle.py backend/tests/test_module2_main_entry_bundle.py backend/tests/test_module2_main_service_bundle.py -q`
- full current main-assembly suite:
  - `python -m pytest backend/tests/test_module2_main_*.py -q`

### Validation Result

This increment passed the current Module 2 main-assembly regression surface:

- syntax checks passed
- real `app.main` import smoke passed
- targeted schema/main tests passed
- the full current `backend/tests/test_module2_main_*.py` suite passed

No evidence from this increment indicates regression in the Module 2 entry wiring.

### Structural Result

With this increment complete:

- `backend/module2/app/main.py` dropped from approximately `814` lines to approximately `747` lines
- `backend/module2/app/runtime/main_schema_pipeline_bundle.py` now carries the schema assembly
  cluster in approximately `178` lines

That means `main.py` has moved one step closer to the role it should have in the final structure:

- public entry
- lifecycle hook registration
- bundle composition root
- router registration

rather than also directly spelling out every schema runtime assembly edge inline.

### Updated Next Safe Slice

Now that unified extraction is stable and the Module 2 schema assembly cluster is no longer
embedded inline in `main.py`, the next best move is:

1. keep this new `main_schema_pipeline_bundle.py` boundary stable
2. reassess whether `main.py` still contains another genuinely coherent assembly cluster worth
   lifting as one unit
3. otherwise shift the next major migration slice back to the remaining parser/core concentration
   or broader workflow/package validation work

This is more aligned with the current constraint:

- keep moving in medium-grain increments
- avoid creating many tiny files
- preserve the full working chain while converging structure

## Module2 Main Foundation Assembly Extraction

After the schema pipeline assembly cluster moved out, `backend/module2/app/main.py` still had one
more large, highly coherent assembly band in its front half:

- support runtime construction
- platform/bootstrap assembly
- storage and graph creation
- policy / geometry / document-io / nonpdf / quality / progress bundle wiring
- service bundle wiring
- extraction bundle wiring
- http runtime wiring

This was still not business logic. It was infrastructure composition written inline at module
scope, which made `main.py` heavier than it needed to be and made the remaining composition root
harder to read.

### What Was Extracted

This wave introduced:

- `backend/module2/app/runtime/main_foundation_bundle.py`

This new runtime assembly file now owns the coordinated construction of:

- `storage`
- `graph`
- `main_support_bundle`
- `main_platform_bundle`
- `main_schema_primitives_bundle`
- `main_policy_bundle`
- `main_geometry_bundle`
- `main_document_io_bundle`
- `main_value_guard_bundle`
- `main_nonpdf_bundle`
- `main_quick_extract_bundle`
- `main_quality_bundle`
- `main_progress_bundle`
- `main_service_bundle`
- `main_extraction_bundle`
- `http_runtime_bundle`

`backend/module2/app/main.py` now builds one
`build_module2_main_foundation_bundle(...)` object, then rebinds the historical module-level names
back onto the bundle members so existing imports, test seams, and runtime consumers keep seeing the
same public surface.

### Important Boundary Decision

This increment intentionally kept the late-bound callback seams in `main.py`:

- `document_workflow_runtime.execute(...)` for job execution
- `module2_main_schema_request_bundle.parse_schema_form_json(...)` for schema form parsing
- `module2_main_schema_fields_bundle.is_low_value_auto_schema_field_name(...)` for quick extract filtering

That means the old dependency timing is preserved. The new bundle centralizes the assembly, but it
does not force eager evaluation of workflow or schema objects that are still built later in the
file.

### Why This Increment Was Safe

This was still an assembly refactor, not a behavior rewrite:

- no extract route contract changed
- no assistant / auth / Module 4 contract changed
- no parser algorithm changed
- no docx -> pdf -> MinerU -> Gemini path changed
- no packaging path policy changed

The same concrete runtimes still back the system. They are now just composed behind one
medium-grain infrastructure bundle instead of being spelled out inline in `main.py`.

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/main.py backend/module2/app/runtime/main_foundation_bundle.py backend/module2/app/runtime/__init__.py backend/tests/test_module2_main_foundation_bundle.py`
- targeted main-assembly regression:
  - `python -m pytest <all backend/tests/test_module2_main_*.py> backend/tests/test_module2_main_foundation_bundle.py -q`
- real Module 2 entry import smoke executed with `backend/module2` as package root:
  - `import app.main as main_module`
  - verified `main_module.module2_main_foundation_bundle`
  - verified `main_module.module2_main_entry_bundle`
  - verified `main_module.document_workflow_runtime`

### Validation Result

This increment passed the current Module 2 main-entry regression surface:

- syntax checks passed
- new foundation bundle unit test passed
- full current `backend/tests/test_module2_main_*.py` suite passed
- real `app.main` import smoke passed

No evidence from this increment indicates regression in the current complete Module 2 wiring.

### Structural Result

With this increment complete:

- `backend/module2/app/main.py` dropped from approximately `747` lines to approximately `677` lines
- `backend/module2/app/runtime/main_foundation_bundle.py` now carries the remaining front-half
  infrastructure assembly cluster

That moves `main.py` closer to the intended end state:

- entry module
- lifecycle registration
- schema/workflow/entry composition coordination
- router registration

rather than also owning the full low-level infrastructure assembly inline.

### Updated Next Safe Slice

Now that the foundation assembly is stable, the next safest move is:

1. freeze unified extraction and the new foundation boundary
2. reassess whether `backend/module2/app/main.py` still has another genuinely coherent cluster
   worth lifting as one unit
3. if not, move back into the remaining parser/core pure-rule concentration using the same
   medium-grain approach

At this point, `main.py` is no longer the highest-risk concentration zone it was before. That
means later slices can be chosen more selectively, instead of forcing more assembly extraction just
for the sake of line count.

## Parser Initialization Assembly Extraction

After the Module 2 entry layer was reduced again, the next highest-value concentration was no
longer `main.py`.

The better target moved back into `backend/module2/app/core/parser.py`, but not into parsing
algorithms first.

At this stage, `parser.py` had become heavily weighted toward constructor-time bootstrap and
initialization assembly:

- support runtime wiring
- provider-state wiring
- config/bootstrap phase ordering
- semantic / visual / pdf-image runtime assembly
- docx dispatch runtime assembly

That made `NativeDocumentParser` look more like a long inline bootstrap coordinator than a parser
facade.

### What Was Extracted

This wave introduced:

- `backend/module2/app/core/parser_initialization_runtime.py`

This new runtime now owns the coordinated initialization flow for the parser bootstrap phases:

- support runtime attr population
- provider-state runtime creation
- core parse config bootstrap
- OCR/table/docx-media/table-merge config bootstrap
- document-table bootstrap
- semantic/vision bootstrap
- pdf-image bootstrap
- visual pipeline bootstrap
- docx dispatch bootstrap

`backend/module2/app/core/parser.py` now delegates that long constructor-time initialization to
`ParserInitializationRuntime.initialize(...)`, then keeps:

- the parser facade class
- entrypoint parse methods
- provider kwarg helpers
- parse wrapper methods
- OCR engine caching
- top-level subprocess entrypoint

### Important Boundary Decision

This increment also added a small factory-injection seam for provider factories used during
initialization. That seam exists to keep the new runtime testable without changing runtime behavior
for production code.

In the follow-up pass immediately after this extraction, the remaining inline document-table
bootstrap was also folded into the same `parser_initialization_runtime.py` file instead of
introducing yet another new file. That kept file count under control while preserving the original
bootstrap order.

In the next follow-up pass, the remaining provider-side helper logic in `parser.py` was also
reduced without introducing new files:

- native Gemini key priority resolution moved behind `ParserProviderBundleRuntime`
- visual backend availability detection moved behind `ParserProviderBundleRuntime`
- stale heavy imports were removed from `parser.py`

That kept the parser facade focused on parse coordination instead of also carrying provider-side
environment probing details.

### Why This Increment Was Safe

This was still assembly concentration reduction, not a parsing rewrite:

- no parse algorithm changed
- no MinerU flow changed
- no Gemini visual extraction logic changed
- no docx -> pdf fallback policy changed
- no parser entry contract changed

The same parser-owned runtimes still execute the real work after this increment. They are just no
longer all wired inline in the parser constructor.

### Validation Executed For This Increment

- `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_initialization_runtime.py backend/tests/test_module2_parser_initialization_runtime.py`
- parser runtime regression suite:
  - `python -m pytest <all backend/tests/test_module2_parser_*.py> backend/tests/test_module2_parser_initialization_runtime.py -q`
- real parser import smoke with `backend/module2` as package root:
  - `import app.core.parser as parser_module`
  - verified `parser_module.NativeDocumentParser`
  - verified `parser_module.parse_document_in_subprocess`
- provider helper follow-up validation:
  - `python -m py_compile backend/module2/app/core/parser.py backend/module2/app/core/parser_provider_bundle_runtime.py backend/tests/test_module2_parser_provider_bundle_runtime.py`
  - `python -m pytest backend/tests/test_module2_parser_provider_bundle_runtime.py backend/tests/test_module2_parser_initialization_runtime.py <all backend/tests/test_module2_parser_*.py> -q`
  - real parser import smoke repeated with `backend/module2` as package root

### Validation Result

This increment passed the current parser bootstrap/runtime regression surface:

- syntax checks passed
- new parser initialization runtime test passed
- full current `backend/tests/test_module2_parser_*.py` suite passed
- real parser import smoke passed

No evidence from this increment indicates regression in the current parser initialization chain.

### Structural Result

With this increment complete:

- `backend/module2/app/core/parser.py` dropped from approximately `789` lines to approximately `307` lines
- `backend/module2/app/core/parser_initialization_runtime.py` now carries the parser bootstrap
  assembly in approximately `490` lines
- `backend/module2/app/core/parser_provider_bundle_runtime.py` now owns the small provider-side
  helper rules in approximately `106` lines

This is a substantial structural improvement because `parser.py` is now much closer to the role it
should play:

- parser facade
- parse entry wrappers
- state handoff coordinator

instead of also being the single place where the full constructor-time runtime graph is assembled.

### Updated Next Safe Slice

With parser initialization now separated, the next safest move is **not** another immediate large
bootstrap extraction.

The better next target is to reassess the remaining parser/core concentration for one of these:

1. remaining pure-rule concentration in figure/table matching and merge logic, if a clean cluster
   still exists outside already-extracted runtimes
2. package-boundary normalization around parser-adjacent runtimes, where
   it improves readability without affecting runtime behavior
3. workflow/package validation work, if further structural extraction stops improving readability
   enough to justify the risk

This keeps the migration aligned with the current constraint set:

- preserve the full working chain
- avoid tiny-file fragmentation
- keep each increment medium-grain and regression-backed
