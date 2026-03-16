# Module 2 File Parsing Stabilization Design

Date: 2026-03-16

## Summary

This design defines the approved remediation and optimization plan for Module 2 file parsing, extraction quality, trace rendering, and downstream consistency.

The approved direction is `Approach B`:

- stabilize the pipeline by layer instead of patching isolated symptoms
- keep the current frontend and backend contracts intact wherever possible
- prioritize extraction correctness and completeness over latency
- treat figure and table trace closure as a first-class requirement, not a UI afterthought
- validate every major change through repeatable backend and real frontend regressions

This spec is intentionally focused on Module 2.
It does not redesign the whole product.
It narrows the work to the current gap:

`Module 2 can now complete the main parsing path for multiple formats, but the quality, figure/table enhancement closure, persistence stability, and real-user regression coverage are not yet strong enough to call the workflow stable.`

The goal of this design is to turn that gap into:

- a bounded stabilization scope
- a stage-by-stage execution plan
- explicit quality gates
- concrete regression expectations
- a release-ready validation checklist

## Why This Spec Exists

Module 2 has already moved past the prototype stage in several important ways:

- PDF parsing no longer collapses into obvious junk schema fields on the known hard sample
- DOCX, XLSX, and MD can complete the main extraction path successfully
- DOCX to PDF preview and parsing conversion is functioning in the current frontend path
- Module 2 to Module 4 synchronization is working in real runs
- the trace surface can already render field hits, table previews, and image artifacts

However, the module is not yet stable enough for the intended quality bar.

Current observed weaknesses:

- PDF extraction can still produce semantically weak field values even when schema selection is no longer broken
- figure and image enhancement is not yet closed into DataFrame rendering on the frontend
- frontend regression evidence exists for a single successful real path, but not yet for a complete multi-file regression matrix
- runtime persistence is still degraded in Module 2 memory mode
- current regression confidence depends too much on ad hoc manual checks instead of a fixed validation gate

Without a design-level plan, the team risks repeating the same cycle:

- fix one visible bug
- re-run one sample
- discover a different layer is still incomplete
- patch again without clear closure criteria

This design replaces that cycle with a staged stabilization plan.

## Goals

- Make the file parsing chain stable across the target formats: PDF, DOCX, XLSX, and MD.
- Ensure DOCX reliably converts into PDF and then enters the same PDF extraction quality path where required.
- Improve PDF extraction so that the system outputs business-meaningful fields and values rather than merely syntactically valid ones.
- Close the MinerU artifact -> Gemini enhancement -> structured trace payload -> frontend rendering loop for tables and figures.
- Ensure trace localization and category rendering behave consistently in the current Module 2 workbench interaction model.
- Preserve existing frontend/backend request contracts unless a change is necessary for correctness.
- Verify that Module 2 uploads and extracted documents synchronize correctly to Module 4.
- Replace ad hoc validation with a repeatable backend and frontend regression matrix.

## Non-Goals

- Do not rebuild the entire Module 2 parser from scratch.
- Do not replace MinerU or the current hybrid extraction stack with a single-model approach.
- Do not redesign unrelated Module 1 or global app workflows.
- Do not introduce a new product interaction model for trace browsing.
- Do not optimize for latency before correctness and completeness are stable.
- Do not use broad refactors that are unrelated to extraction quality, trace closure, or runtime consistency.

## Current State Snapshot

### What Is Working

- Known hard PDF schema drift is significantly reduced after adding auto-schema quality filtering and quick fallback guards.
- Direct regression shows successful extraction for:
  - a hard English PDF sample
  - a DOCX sample with office-to-PDF conversion
  - an XLSX sample
  - an MD sample
- The current Module 2 runtime on port `8000` is serving the updated code path.
- Module 2 to Module 4 upload sync succeeds in the current environment.
- Real frontend regression evidence exists for at least one successful single-file path with screenshots and downstream sync evidence.

### What Is Not Stable Yet

- Some extracted field values remain weak or generic, especially in harder PDF cases.
- Figure enhancement is not yet resulting in rendered DataFrame output on the frontend.
- Multi-file and mixed-format frontend regression is not yet complete enough to certify the UI flow.
- Module 2 runtime storage is still degraded to memory mode, which weakens confidence in stateful behavior.
- Tooling for browser monitoring is not fully reliable in the current environment, which means regression automation needs an explicit fallback path.

## Product Problems To Solve

### Problem 1: Schema Quality Is Better, But Semantic Quality Is Still Uneven

Recent fixes removed the worst auto-schema failure mode, where low-value tokens like conjunctions could become extracted fields.
That was necessary, but it is not sufficient.

The remaining problem is subtler:

- the field name may look plausible
- the value may be non-null and traceable
- but the pair may still be low-value or semantically weak

The extraction system therefore needs a stronger notion of business usefulness, not just syntactic validity.

### Problem 2: Figure and Table Enhancement Is Not Yet Closed End-To-End

The system can already produce artifacts and some structured trace data for tables and figures.
The missing closure is that figure and image understanding is not consistently materialized into DataFrame-style output beneath the rendered artifact in the Module 2 trace area.

This is the most visible functional gap against the intended user experience.

### Problem 3: The Runtime Is More Stable Than Before, But Validation Is Not Yet Formalized

Some runs now complete cleanly and produce useful outputs.
That is encouraging, but not enough.
The product needs a fixed regression matrix and release gate.

Without that, the team cannot answer:

- which cases are known good
- which cases are partially good
- which cases are still unstable
- whether a new patch regresses a previously working format

### Problem 4: Frontend Success Exists, But Full User-Flow Certification Does Not

The current frontend workbench already supports:

- upload
- preview
- extraction
- trace grouping
- table preview containers
- figure DataFrame containers

But a complete real-user certification still requires:

- single-file validation for each key format
- multi-file mixed-format validation
- screenshot capture for all critical states
- confirmation that no layout collision or panel-state bug appears during those runs

### Problem 5: Persistence And Cross-Module Consistency Need To Become Operationally Trustworthy

Module 2 currently reports degraded memory mode for storage.
That creates uncertainty around:

- extraction job persistence
- assistant session continuity
- cache behavior
- replayability of task state

At the same time, Module 2 to Module 4 sync is working.
That means the system is close to operational consistency, but still has one unstable foundation layer.

## Design Principles

### 1. Stabilize By Layer, Not By Symptom

Every observed bug belongs to one of five layers:

- input routing
- extraction quality
- multimodal enhancement
- frontend rendering
- persistence and integration

This design fixes the system by layer so that each improvement has a stable boundary and a clear owner.

### 2. Prefer Fewer Correct Results Over More Misleading Results

For extraction quality, silent hallucinated certainty is worse than partial output.
When confidence is low or semantics are weak, the system should:

- downgrade
- trim
- mark partiality clearly

instead of presenting junk as a complete answer.

### 3. Trace Artifacts Are Product Output, Not Debug Output

MinerU crops, table previews, image artifacts, and DataFrame renderables are part of the actual user-facing result.
They must therefore be treated as first-class outputs with stable structure and validation, not best-effort extras.

### 4. Real Frontend Regression Is Mandatory

Backend-only regression is necessary, but not sufficient.
The product is only considered stable when real upload, preview, extraction, trace rendering, and sync behavior have been exercised through the actual frontend path.

### 5. Keep Contracts Stable Unless Correctness Requires Change

Module 2 already has a working frontend/backend interaction path.
This design avoids gratuitous contract changes.
Most improvements should happen behind the current API shape unless new explicit trace fields are necessary.

## Chosen Approach

The approved approach is a staged stabilization model with six phases:

1. establish a stable validation baseline
2. stabilize input routing and format-specific parse entry behavior
3. improve PDF extraction semantic quality
4. close table and figure Gemini enhancement end-to-end
5. stabilize frontend trace rendering and cross-module consistency
6. certify the system through a formal regression gate

This approach was chosen because it balances two constraints that matter here:

- correctness must improve quickly on the real failure cases
- frontend/backend interoperability must not be broken by large speculative rewrites

## Architecture Scope

This design affects five bounded units.

### Unit 1: Input Routing And Parse Entry

Responsibilities:

- determine the correct parse path per file type
- guarantee DOCX conversion and preview alignment
- record parse-route diagnostics

Primary touchpoints:

- `backend/module2/app/main.py`
- office preview and DOCX conversion helpers

Interface expectations:

- the extraction request contract remains stable
- diagnostics gain clearer route indicators

### Unit 2: Schema Planning And Extraction Quality Gate

Responsibilities:

- select extractable, business-meaningful schema fields
- prevent low-value auto-schema candidates
- prevent quick fallback from producing misleading output
- measure output quality beyond simple presence checks

Primary touchpoints:

- schema inference helpers
- fallback extraction helpers
- quality gate logic in `backend/module2/app/main.py`

Interface expectations:

- output schema remains a simple field map
- diagnostics become more explicit about why fields were accepted, dropped, or downgraded

### Unit 3: Table And Figure Enhancement Pipeline

Responsibilities:

- align MinerU artifacts with Gemini enhancement requests
- produce stable structured outputs for tables and figures
- normalize those outputs into frontend-consumable trace payloads

Primary touchpoints:

- parser post-processing
- Gemini enhancement calls
- trace hit assembly

Interface expectations:

- every figure/table object should have a stable artifact and enhancement status
- DataFrame-capable outputs should be explicit, not inferred only in the frontend

### Unit 4: Frontend Trace Rendering

Responsibilities:

- render grouped trace categories in the current interaction model
- show table previews and figure/image artifacts
- render DataFrame output beneath the relevant artifact
- keep panel layout stable during upload and extraction

Primary touchpoints:

- `frontend/components/DeepReadWorkbench.tsx`

Interface expectations:

- the current trace panel structure remains
- frontend rendering becomes more robust for partial, empty, and error states

### Unit 5: Persistence And Cross-Module Sync

Responsibilities:

- restore stable Module 2 persistence
- verify job, cache, and assistant state are not lost
- ensure extracted uploads and documents remain consistent when pushed to Module 4

Primary touchpoints:

- Module 2 storage layer
- sync task orchestration
- Module 4 ingest and job validation

Interface expectations:

- existing sync contract remains intact
- health checks and regression outputs become more diagnostic

## Data Flow Design

### Flow A: DOCX Path

1. User uploads a DOCX file.
2. Module 2 stores the uploaded artifact and creates preview metadata.
3. DOCX converts to PDF through the office conversion path.
4. The preview surface and extraction path use the same converted PDF lineage.
5. The converted PDF enters the shared PDF parsing and enhancement flow.
6. Result objects, trace hits, and artifacts are assembled into the extraction job payload.
7. Uploaded and extracted outputs synchronize to Module 4.

Success condition:

- preview PDF, parse PDF, trace artifacts, and final document payload all refer to one consistent lineage.

### Flow B: PDF Path

1. User uploads a PDF.
2. MinerU produces markdown, table candidates, images, and crop artifacts.
3. Schema planner combines heuristic inference and LLM planning.
4. Quality filters reject low-value field names before extraction.
5. Main extraction runs.
6. If fallback is required, fallback output still passes field and value quality guards.
7. Final field results, trace hits, and diagnostics are assembled.

Success condition:

- the system never falls back to obviously junk fields or values simply because a timeout occurred.

### Flow C: Table/Figure Enhancement Path

1. Parser identifies a figure or table artifact.
2. Artifact metadata is normalized into a stable trace object.
3. Gemini enhancement runs with type-specific prompting.
4. Enhancement output is normalized into:
   - raw response
   - summary text
   - structured rows and columns where applicable
   - status markers such as `success`, `partial`, `empty`, or `error`
5. Frontend renders the artifact and, when present, renders the DataFrame beneath it.

Success condition:

- users can see the actual parsed artifact and its corresponding structured interpretation in the same trace context.

## Phase Plan

## Phase 0: Validation Baseline

### Objective

Replace ad hoc confidence with a fixed regression baseline.

### Work

- define a standard sample set:
  - one hard English PDF
  - one Chinese DOCX
  - one XLSX
  - one MD
  - multi-file mixed-format sets for 2, 3, 4, and 5 files
- standardize runlog outputs:
  - `summary.json`
  - `final_payload.json`
  - frontend screenshots
  - trace state snapshots
  - Module 2 health snapshots
  - Module 4 sync snapshots
- define the mandatory metrics used for go/no-go decisions

### Acceptance Criteria

- every future change can be validated against the same sample matrix
- every run produces a stable artifact layout in `.runlogs`

## Phase 1: Input Routing And Parse Entry Stabilization

### Objective

Make every target file type enter the correct parsing route with explicit diagnostics.

### Work

- formalize route decisions for PDF, DOCX, XLSX, and MD
- ensure DOCX conversion lineage is explicit and consistent between preview and parse
- add or standardize diagnostics such as:
  - `office_pdf_converted`
  - `parse_input_name`
  - `word_parse_via_pdf`
  - `schema_source`
  - `quick_fallback_used`

### Acceptance Criteria

- for any sample file, the exact route and conversion path are visible in diagnostics
- preview and parse no longer drift for office files

## Phase 2: PDF Semantic Quality Hardening

### Objective

Upgrade PDF extraction from “no obvious junk” to “business-meaningful output.”

### Work

- extend low-value field-name filtering
- add stronger value-quality guards for fallback results
- introduce lightweight semantic validation by field type
- tighten quality-gate behavior so misleading outputs are downgraded or trimmed
- keep `quality_gate_ok` meaningful rather than permissive

### Acceptance Criteria

- hard PDF samples do not regress into junk schema fields
- semantically weak values are either improved or explicitly excluded
- no known hard PDF passes with a misleadingly optimistic quality status

## Phase 3: Table And Figure Gemini Closure

### Objective

Make table and figure enhancement a complete user-visible feature.

### Work

- define a normalized structure for enhanced table and figure trace objects
- split prompts and parsing logic by artifact type
- emit structured DataFrame payloads for table-like or chart-like visual outputs
- record enhancement status per artifact
- ensure artifacts displayed in trace are actual parse outputs, not synthetic placeholders

### Acceptance Criteria

- figure and table artifacts appear in trace with stable metadata
- relevant artifacts produce rendered DataFrames on the frontend
- `figure_hits_with_dataframe` is no longer zero for supported cases

## Phase 4: Frontend Trace Rendering Stabilization

### Objective

Ensure Module 2 trace browsing remains visually stable and semantically aligned with backend outputs.

### Work

- keep the current grouped-trace interaction model
- ensure clicking a category reveals the corresponding content region only
- preserve page-jump behavior to the center preview page
- strengthen empty, partial, and error rendering states for trace artifacts
- verify layout stability around upload, extraction progress, and trace expansion

### Acceptance Criteria

- no overlap or layout collision appears during upload or extraction
- trace categories, table previews, and DataFrames render consistently
- clicking categorized trace content always maps to the correct preview page

## Phase 5: Persistence And Cross-Module Consistency

### Objective

Move Module 2 from “working in degraded memory mode” toward operational stability.

### Work

- restore stable Module 2 storage connectivity
- verify extraction job state, cache, and assistant session continuity
- validate Module 2 upload and extracted result synchronization into Module 4
- preserve health metrics that clearly show sync and persistence status

### Acceptance Criteria

- Module 2 health no longer reports degraded memory mode in normal runs
- Module 2 and Module 4 agree on the uploaded and synchronized document set
- stateful behaviors are replayable and inspectable

## Phase 6: Regression Gate And Release Certification

### Objective

Turn the stabilization effort into an enforceable release gate.

### Work

- run single-file frontend regressions across the target formats
- run multi-file mixed-format regressions for 2, 3, 4, and 5 uploaded files
- capture screenshots for:
  - before upload
  - after upload
  - after extraction starts
  - final completed state
- store extraction payloads, trace state, and Module 4 sync state per round
- use browser automation with an explicit fallback path if `agent-browser` is unavailable in the current environment

### Acceptance Criteria

- all standard scenarios complete without UI breakage
- document count matches upload count
- figure and table trace outputs are present where expected
- Module 4 sync succeeds for all certified scenarios

## Error Handling And Degradation Design

### Extraction Quality Degradation

When extraction quality is uncertain:

- drop low-value schema candidates
- drop low-value fallback values
- downgrade quality status rather than pretending success

### Enhancement Partiality

When Gemini enhancement only partially succeeds:

- preserve the artifact
- preserve any valid extracted structure
- mark the enhancement state as partial
- render a clear partial-state UI instead of a blank region

### Storage Degradation

If storage is unavailable:

- continue only in explicitly labeled degraded mode
- expose degraded state in health and diagnostics
- do not silently treat degraded memory mode as production-ready stability

### Browser Regression Tooling Failure

If `agent-browser` is unavailable or cannot connect in the environment:

- record that as tooling failure, not product success
- use the repository Playwright regression path as the execution fallback
- retain screenshots and payloads so the regression still counts as evidence

## Testing Strategy

Testing is divided into four layers.

### Layer 1: Helper-Level Validation

- schema-field filtering behavior
- fallback value filtering behavior
- DataFrame normalization behavior
- trace object normalization behavior

### Layer 2: Direct Backend Regression

- run extraction jobs directly for standard samples
- compare:
  - status
  - field count
  - quality status
  - trace counts
  - presence of figure/table artifacts

### Layer 3: External HTTP Regression

- validate the actual running Module 2 service over HTTP
- verify cache clearing, job creation, polling, diagnostics, and sync metrics

### Layer 4: Real Frontend Regression

- simulate upload through the Module 2 frontend
- verify preview, extraction, trace rendering, screenshots, and Module 4 sync
- certify single and multi-file scenarios

## Metrics And Release Gates

The following metrics are required for release readiness:

- `quality_gate_ok` on the certified baseline set
- no known hard PDF producing junk schema fields
- `figure_hits_with_dataframe > 0` on supported visual samples
- `table_hits_with_artifact > 0` where tables are expected
- uploaded file count matches extracted document count
- Module 4 synchronization success across all certified runs
- no critical frontend layout regressions during upload and extraction
- Module 2 persistence no longer stuck in degraded memory mode during the release-ready path

## Risks

### Risk 1: Improving Field Quality May Reduce Field Count

This is acceptable if the remaining fields are materially better.
The system should prefer trustworthiness over shallow completeness.

### Risk 2: Figure DataFrame Support May Reveal Artifact Inconsistencies

Once figure rendering depends on structured payloads, hidden inconsistencies in artifact metadata may surface.
That is a desirable discovery, but it will require disciplined normalization.

### Risk 3: Frontend Certification Depends On Browser Tool Reliability

The environment has already shown instability with one browser automation path.
The plan therefore explicitly allows a real Playwright fallback while still recording the tooling issue.

### Risk 4: Persistence Repairs May Surface Existing Assumptions

Moving out of degraded memory mode may expose stale assumptions in jobs, cache, or assistant-state behavior.
That work should therefore happen after the core extraction and rendering path are already easier to inspect.

## Out Of Scope Cleanup

The following may be observed during the work but are not primary goals of this design unless they block stabilization:

- unrelated UI redesign
- unrelated assistant product changes
- broad schema or prompt refactors unrelated to extraction quality
- global application infrastructure changes outside Module 2 and its required Module 4 sync path

## Implementation Order

The recommended execution order is:

1. Phase 0: validation baseline
2. Phase 3: table and figure Gemini closure
3. Phase 2: PDF semantic quality hardening
4. Phase 4: frontend trace rendering stabilization
5. Phase 5: persistence and cross-module consistency
6. Phase 6: full regression gate and certification

Rationale:

- the most visible functional gap is figure/table closure
- PDF semantic quality is the next highest-risk correctness issue
- frontend rendering and persistence should be stabilized only once the data they consume is more trustworthy
- final certification should happen only after the lower layers are ready

## Deliverables

Each phase must produce concrete artifacts.

### Phase 0

- baseline sample manifest
- runlog structure standard
- quality metric checklist

### Phase 1

- parse-route diagnostics matrix
- DOCX preview/parse lineage notes

### Phase 2

- before/after hard-PDF comparison report
- updated schema-quality and fallback-quality rules

### Phase 3

- normalized figure/table trace schema
- sample Gemini enhancement outputs
- DataFrame payload examples

### Phase 4

- frontend screenshots
- trace rendering verification notes
- categorized trace interaction validation

### Phase 5

- Module 2 persistence health report
- Module 2 to Module 4 consistency report

### Phase 6

- regression summary report
- remaining risk list
- release readiness checklist

## Open Questions

These questions do not block the design, but they should be answered during execution:

- which figure types should be required to produce DataFrame output versus summary-only output
- whether certain weak-but-nonempty PDF values should be filtered or marked as partial
- which runtime storage backend repairs are sufficient for Module 2 to stop reporting degraded mode in the target environment
- whether `agent-browser` can be restored in the current environment or should remain a non-blocking tooling issue with documented fallback

## Approval Result

This design reflects the approved direction from the Module 2 stabilization brainstorming flow.
The next step, after user review of this written spec, is to turn the phases above into a concrete implementation task list without changing the approved scope.
