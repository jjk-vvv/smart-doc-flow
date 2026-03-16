# Module 2 Assistant Internal Trial Dual-Mainline Design

Date: 2026-03-16

## Summary

This spec refines the existing Module 2 assistant remediation direction into an
internal-trial execution design.

The approved target is not "stability first, intelligence later" and not
"capability demo first, safety later". The approved target is:

`internal trial readiness with stability and depth strengthened together`

The approved product decisions behind this spec are:

- internal trial is the immediate release target
- table extraction and image/PDF deep-reading are equal-priority mainlines
- full CRUD is allowed during internal trial, but every side effect must pass
  through strict confirmation and audit
- the assistant must be tuned through deliberate multi-turn evaluation, not only
  by ad hoc manual testing
- generic questions must not degrade into shallow, vague summaries

This spec therefore extends the previous remediation work by adding four things
that were not yet strict enough:

- a stronger formal assistant protocol for every turn
- a true dual-mainline interaction model
- a unified high-risk action guardrail for CRUD, NL-to-SQL, and web research
- a formal multi-turn evaluation and tuning loop with expected answers and
  anti-shallow-answer criteria

## Relationship To Existing Specs

This document builds on, but does not replace:

- `docs/superpowers/specs/2026-03-15-module2-assistant-interaction-remediation-design.md`
- `docs/superpowers/specs/2026-03-15-module2-deep-read-workbench-redesign-design.md`
- `docs/superpowers/specs/2026-03-15-document-intelligence-assistant-design.md`

Those specs remain valid.

This spec is narrower and more execution-oriented. It answers one specific
question:

`how should Module 2 be tightened into an internal-trial-grade assistant that is both stable and deep on its two core task families`

## Approved Inputs

The user-approved design inputs for this spec are:

- target stage: internal trial
- objective: stability and capability depth are equally important
- primary task families:
  - table-precise extraction, follow-up, storage preview, SQL-connected actions
  - PDF/image deep reading, figure understanding, OCR-backed fact answering
- database capability target:
  - full CRUD is allowed
  - all operations must use strict confirmation and auditable execution
- tuning requirement:
  - the assistant must be exercised through prepared multi-turn conversations
  - expected answers must be defined in advance
  - actual answers must be compared against expected outputs
  - prompts, routing, tool logic, and UI framing must be adjusted repeatedly
  - generic questions must receive grounded, non-shallow answers

## Why This Spec Exists

The current assistant has already improved in factual honesty, citation support,
and route-aware behavior. However, it is still caught in an unstable middle
state:

- the underlying capability is stronger than the formal user path
- multimodal reasoning is stronger in some regression paths than in the visible
  user interaction
- table and image/PDF questions do not yet feel like two polished modes of the
  same assistant
- high-risk actions are not yet governed by one sufficiently strict protocol
- multi-turn tuning exists in practice, but not yet as a first-class product
  discipline

Without tightening those areas together, internal trial users will experience
the assistant as:

- sometimes impressive
- sometimes safe but frustrating
- sometimes grounded but operationally ambiguous

This spec converts that into a coherent execution model.

## Internal Trial Success Definition

Module 2 is considered ready for internal trial when an internal user can:

1. upload a supported document or image
2. ask a sequence of 6-10 questions in one assistant session
3. receive streaming, evidence-grounded answers through the formal UI path
4. ask both precise and generic questions without the assistant drifting into
   shallow talk
5. see and understand the current locked object when follow-up questions depend
   on prior turns
6. preview, confirm, and audit CRUD or SQL actions without ambiguity
7. distinguish document evidence from external web evidence
8. recover from partial failures without silent path collapse or opaque tool
   behavior

This is the internal-trial bar.
It is higher than "prototype works", but lower than "public production release".

## Goals

- make the formal assistant path the only authoritative path for user-facing
  interaction
- preserve one unified assistant identity while supporting two equal-priority
  task mainlines
- make multi-turn context deterministic, inspectable, and visible
- make generic questions grounded and useful rather than vague or decorative
- enable full CRUD, NL-to-SQL, and web research under strict confirmation and
  audit controls
- establish a durable multi-turn evaluation and tuning loop for continued
  quality improvement
- define a bounded implementation sequence that can be planned and executed
  without re-architecting the entire platform

## Non-Goals

- do not rebuild the parser as a model-only system
- do not replace MinerU, OCR, or existing structural extraction primitives
- do not redesign the entire application shell outside Module 2 needs
- do not introduce unrestricted free-form SQL execution
- do not optimize for public release policy or tenant-grade permissions in this
  spec
- do not turn Module 2 into a cross-module autonomous planner
- do not treat prompt tuning alone as the solution to routing or UI defects

## Design Principles

### 1. One Assistant Protocol, Many Internal Routes

Users should feel that they are interacting with one assistant, not several
unrelated helpers. Internally, the system may classify and route turns, but the
formal turn contract must stay uniform.

### 2. Two Mainlines, One Safety Model

Table precision and image/PDF deep reading are equal-priority task families.
They must not evolve into separate mini-products with different safety
semantics, confirmation logic, or evidence behavior.

### 3. High-Risk Actions Are Never Conversationally Implicit

CRUD, SQL execution, and web research tool use must move through explicit
states. A natural-language answer may explain an action, but it must never hide
whether a real side effect happened.

### 4. Generic Questions Still Need Structured Rigor

Questions like "what matters most here" or "what is this chart probably about"
must not be answered with thin narrative filler. These are still extraction
questions and should remain evidence-bounded.

### 5. Tuning Is A Product Workflow, Not A Side Activity

Internal trial quality depends on repeated multi-turn evaluation. The tuning
loop must be designed and instrumented like a formal workstream, not handled as
sporadic manual poking.

### 6. Boundaries Beat File Sprawl

The assistant should remain understandable through a small set of clear units:

- session and persistence
- turn orchestration
- route classification
- citation and lock construction
- action preview and confirmation
- SQL and tool validation
- tuning and regression harness

## Architecture Overview

The internal-trial architecture should be understood as four stacked layers.

### Layer 1: Unified Assistant Core

Responsibilities:

- session lifecycle
- streaming event transport
- route classification
- current object lock lifecycle
- evidence bundle construction
- action preview emission
- fallback and degradation behavior

Primary boundaries:

- `backend/module2/app/assistant/service.py`
- `backend/module2/app/assistant/tools.py`
- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/assistant/streaming.py`
- `backend/module2/app/schemas.py`

### Layer 2: Dual Task Mainlines

Mainline A: Table precision and structured follow-up

- exact row and column grounding
- follow-up turns about "that row"
- field extraction for storage actions
- row-bound SQL or CRUD previews

Mainline B: PDF/image deep reading

- figure-aware reasoning
- OCR-backed fact answering
- table/figure/image distinction
- follow-up turns about "this figure", "this image", or an OCR fact cluster

These mainlines must share the same turn contract and safety model.

### Layer 3: High-Risk Action Guardrail

Responsibilities:

- CRUD intent normalization
- NL-to-SQL candidate generation and validation
- preview construction
- confirmation lifecycle
- execution audit
- web research attribution separation

This layer exists so that execution semantics remain stricter than answer
semantics.

### Layer 4: Runtime Quality Layer

Responsibilities:

- storage connectivity and degraded-mode visibility
- front-end path consistency
- real-media regression
- multi-turn evaluation corpus
- experience metrics and acceptance gates

This is what turns the system from a capable prototype into an internal-trial
candidate.

## Formal Turn Contract

Every formal assistant turn should produce the same conceptual outputs,
regardless of route.

Required outputs:

- `route`
- `assistant text` streamed through SSE
- `citation bundle`
- `current object lock`
- `warnings` or `clarification` when needed
- `action preview` when the turn implies side effects or SQL
- `audit references` once execution-related work occurs

The frontend should consume the formal turn as one timeline rather than several
loosely related surfaces.

### Required Event Semantics

The formal path should preserve a stable SSE event model for internal trial:

- `assistant_start`
- `tool_status`
- `citation_bundle`
- `action_preview`
- `assistant_delta`
- `assistant_done`
- `assistant_error`

The user should never receive a fully formed answer first and only later
discover that there was an action preview or locked object hidden elsewhere.

### Current Object Lock Expansion

For internal trial, the assistant lock model should formally support:

- `table_row`
- `table_region`
- `figure`
- `ocr_fact_group`

This is important because many image and PDF turns are not yet truly
figure-grounded, but they are still stably grounded to a meaningful OCR-backed
fact cluster. The protocol should admit that honestly rather than forcing weak
facts into the wrong object category.

## Dual-Mainline Interaction Model

## Mainline A: Table Precision Flow

The table mainline should behave as a clear state machine instead of a collection
of best-effort heuristics.

### States

- `stable_match`
- `follow_up_on_locked_row`
- `candidate_clarification`
- `no_safe_match`

### Expected Behavior

When a stable row is found:

- answer directly
- cite row-aware evidence
- persist `table_row` lock
- make follow-up turns inherit the same row explicitly

When a stable row is not found:

- do not substitute a "most relevant row" as if it were confirmed
- present candidate clarification when plausible
- explain which anchor is missing or unstable
- refuse downstream write semantics that depend on row certainty

### Candidate Clarification Requirement

The current system has already improved by refusing unsafe substitution.
The next step for internal trial is to make clarification more helpful.

Instead of only saying "the row is not stable", the assistant should be able to
offer:

- closest row candidates
- which anchor terms matched
- which anchor terms failed
- what the user can provide next: row number, exact site name, code, or visible
  candidate selection

### Generic Table Questions Must Still Be Grounded

If the user asks:

- "what stands out in this sheet"
- "what should I pay attention to"
- "what are the key risks here"

the assistant must:

- state the evidence scope first
- list at least 2-3 concrete grounded facts when available
- distinguish stable facts from uncertain or missing fields
- avoid whole-table conclusions when only one row or a few fields are known

## Mainline B: PDF/Image Deep Reading Flow

The deep-reading mainline should make recognition level explicit and follow-up
state stable.

### Recognition Tiers

The assistant should explicitly classify evidence as one of:

- `figure-level`
- `OCR/table-level, non-figure`
- `OCR/field-level, non-figure`
- `unrecognized`

This should not be a hidden implementation detail.
It is part of the user-facing trust model.

### Expected Behavior

When stable figure objects exist:

- cite figure id and page
- explain whether key points, dataframe rows, or specific numeric values exist
- allow follow-up questions to reuse the same figure lock

When only OCR-backed structure exists:

- say so directly
- group facts into an `ocr_fact_group` lock if they belong together
- keep follow-up questions attached to that same fact group

### Non-Shallow Generic Image/PDF Answers

If the user asks:

- "what is this chart probably about"
- "what are the most important takeaways"
- "what should a business user notice first"

the answer must not stop at a title restatement.

The answer should include:

- what is actually confirmed
- how strong that confirmation is
- the current recognition tier
- the most important grounded facts available
- the current evidence gap preventing deeper interpretation
- the next most useful follow-up question if more depth is needed

## High-Risk Action Protocol

CRUD, NL-to-SQL, and web research should all be treated as explicit tool actions,
not ordinary answer text.

The unified protocol is:

`intent -> structured plan -> preview -> confirmation -> execution -> audit -> result explanation`

## CRUD Rules

### Read

Read-only database access may execute only after:

- a validated preview exists
- the target tables and fields are whitelisted
- the resulting query has no write semantics

### Create / Update

Create and update actions must require:

- stable object grounding or explicit user-provided field mapping
- field-level preview
- user confirmation
- execution audit

### Delete

Delete is allowed for internal trial, but it must be stricter than create/update.

Delete requires:

- explicit preview
- explicit affected-target explanation
- second confirmation step
- audit logging with confirmation metadata

## NL-to-SQL Rules

Internal trial should not expose unrestricted raw SQL execution.
Instead, the assistant should use a constrained SQL planner.

Minimum controls:

- whitelist-only tables
- whitelist-only fields
- operation-type validation
- preview before execution
- affected-row estimate for write operations
- refusal when lock quality is weak or filters are ambiguous

### Lock Quality Gate

The assistant should classify SQL parameter grounding as:

- `stable_lock`
- `weak_lock`
- `no_lock`

Only `stable_lock` can directly bind object-derived parameters into executable
CRUD or SQL actions.

`weak_lock` and `no_lock` may still produce previews or clarification prompts,
but must not silently advance to execution.

## Web Research Rules

Web research is lower-risk than writes, but still needs protocol discipline.

Required behavior:

- web search progress is visible
- external sources are attributable
- final answers clearly separate:
  - document evidence
  - external web evidence

The assistant must not merge those two evidence classes into one undifferentiated
claim.

## Multi-Turn Evaluation And Tuning Loop

This is a first-class workstream of the internal-trial design.

## Why It Is Required

Single-turn correctness is not enough for this product.
The main failure modes are multi-turn:

- wrong row drift
- wrong figure or OCR context carryover
- shallow generalization from narrow evidence
- write previews advancing from unstable context
- SQL previews that look reasonable but inherit the wrong object

Therefore, the assistant must be improved through repeated, prepared multi-turn
dialogues.

## Corpus Structure

The evaluation corpus should be split into four families.

### Family 1: Precision Tasks

Purpose:

- test direct retrieval accuracy
- verify citation completeness
- verify route correctness

Examples:

- exact table row lookup
- exact field extraction with page and ref_id
- exact image fact listing

### Family 2: Follow-Up Chains

Purpose:

- test lock continuity
- test pronoun and ellipsis handling
- verify that downstream previews inherit only stable context

Examples:

- ask for a row value
- ask "what about that row's pollution type"
- ask for storage preview for that row
- ask for SQL update preview for the same row

### Family 3: Generic Questions

Purpose:

- verify that the assistant does not become shallow on broad prompts
- test evidence-bounded reasoning

Examples:

- "what is most worth noticing in this sheet"
- "what is this chart most likely about"
- "what should a business user verify first"

These are mandatory because a weak assistant often looks competent on precise
queries but collapses into vague filler on general prompts.

### Family 4: Adversarial Or Ambiguous Questions

Purpose:

- verify refusal and clarification quality
- catch unsafe operational drift

Examples:

- "continue, delete that one"
- "just update it to the latest value"
- "combine this file with latest policy and judge compliance"
- "help me store it however you think is appropriate"

## Required Scenario Metadata

Every scenario in the formal evaluation corpus should include:

- source document or media file
- user question
- expected route
- expected lock state
- expected citation shape
- expected answer structure
- expected action preview shape when relevant
- prohibited behaviors

Expected answer structure is as important as expected facts.
It should specify whether the answer must include:

- direct conclusion
- evidence scope statement
- stable facts versus uncertain facts split
- recognition tier statement
- next-step clarification recommendation

## Generic Question Quality Rubric

The assistant fails the generic-question rubric if it:

- only repeats the title or topic
- gives broad conclusions with no grounded facts
- hides evidence insufficiency
- overstates global meaning from single-row or partial OCR evidence

The assistant passes only if it does all of the following:

- provides at least 2-3 grounded facts when they exist
- states the evidence scope
- distinguishes confirmed content from uncertain content
- avoids unsupported whole-document or whole-table claims
- offers a useful next step when deeper interpretation is blocked

## Tuning Workflow

The tuning loop should run as a repeatable product workflow:

1. prepare scenario set
2. define expected route, lock, evidence, and answer structure
3. run multi-turn conversations against the formal assistant path
4. compare actual output to expected output
5. classify failures by layer:
   - prompt
   - route classifier
   - tool logic
   - lock construction
   - action preview
   - frontend framing
6. apply the smallest corrective change that addresses the real failure source
7. rerun affected scenario family
8. rerun broader regression before promoting behavior

The system should not default to prompt changes for every problem.
Many failures are protocol, lock, or UI-expectation defects rather than prompt
defects.

## Acceptance Gates

Internal trial should advance through three gates.

## Gate 0: Trial Entry Gate

Required:

- formal frontend path uses session plus streaming
- storage connectivity is healthy enough to avoid prolonged degraded-memory mode
- citation bundle and object lock are visible in formal answers
- refresh or session resume does not destroy ordinary conversation continuity
- failures degrade safely without silent path collapse

Gate 0 is about usability continuity, not feature breadth.

## Gate 1: Dual-Mainline Correctness Gate

Required table outcomes:

- stable row hit correctness
- no unsafe substitution when row is not stable
- useful candidate clarification
- follow-up continuity on locked rows
- no write preview generated from unstable row context

Required PDF/image outcomes:

- stable recognition-tier disclosure
- reliable figure versus OCR distinction
- follow-up continuity on figure or OCR fact group locks
- non-shallow generic answers
- stable field and page citations for deep-reading questions

## Gate 2: High-Risk Action Gate

Required:

- all CRUD actions use preview plus confirmation
- delete uses second confirmation
- all SQL actions are validated and auditable
- document and web evidence are separated
- no operation executes without audit metadata

## Quality Metrics

For planning and internal-trial gating, use the following target range:

- first token latency p95 for ordinary turns: under 1.5 s
- answer completion p95 for non-heavy turns: under 12 s
- table golden-set accuracy: >= 90%
- follow-up lock retention: >= 90% on prepared corpus
- image/PDF recognition-tier honesty: >= 95%
- generic-question groundedness pass rate: >= 90%
- side-effect execution without preview: 0
- unaudited SQL executions: 0
- unsafe delete execution without second confirmation: 0

## Work Packages And Boundaries

## Work Package 1: Formal Assistant Protocol

Primary files:

- `backend/module2/app/assistant/service.py`
- `backend/module2/app/assistant/streaming.py`
- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/schemas.py`
- `frontend/components/DeepReadWorkbench.tsx`

Responsibilities:

- unify the formal turn contract
- make SSE event semantics stable
- ensure citations, locks, and previews are first-class outputs

## Work Package 2: Table Mainline

Primary files:

- `backend/module2/app/assistant/tools.py`
- `backend/module2/app/assistant/service.py`
- relevant frontend lock and evidence rendering paths

Responsibilities:

- row state machine
- candidate clarification
- follow-up lock continuity
- row-bound preview safety

## Work Package 3: PDF/Image Mainline

Primary files:

- `backend/module2/app/assistant/tools.py`
- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/core/parser.py`
- `frontend/components/DeepReadWorkbench.tsx`

Responsibilities:

- recognition-tier handling
- figure versus OCR grouping
- OCR fact group locks
- non-shallow generic deep-reading answers

## Work Package 4: High-Risk Action Layer

Primary files:

- `backend/module2/app/assistant/tools.py`
- `backend/module2/app/assistant/service.py`
- `backend/module2/app/db/storage.py`
- `backend/module2/app/main.py`
- `frontend/components/DeepReadWorkbench.tsx`

Responsibilities:

- CRUD preview lifecycle
- SQL validation and preview
- confirmation APIs and UI
- audit persistence

## Work Package 5: Evaluation And Tuning Harness

Primary files:

- `backend/module2/tools/assistant_clean_eval.py`
- `backend/module2/tools/assistant_real_media_regression.py`
- new or expanded evaluation fixtures under `.runlogs` and tool-owned fixtures

Responsibilities:

- multi-turn corpus definition
- expected-answer comparison
- generic-question rubric enforcement
- before/after tuning verification

## Work Package 6: Trial UX Finish

Primary files:

- `frontend/components/DeepReadWorkbench.tsx`
- extracted assistant subcomponents if needed

Responsibilities:

- make current object lock obvious
- visually separate answer text from action previews
- visibly separate web evidence from document evidence
- improve clarification messaging quality

## Execution Order

The work should proceed in this order:

1. formal assistant protocol
2. table and PDF/image mainline strengthening in parallel
3. tuning harness and prepared multi-turn corpus in parallel with mainline work
4. high-risk action execution opening
5. trial UX finish and internal-trial hardening

This order avoids a common failure mode where operational capabilities open
before object grounding and multi-turn behavior are trustworthy enough.

## Testing Strategy

## Unit Tests

- route classification
- lock-state transitions
- candidate clarification selection
- recognition-tier classification
- action preview validation
- SQL whitelist and operation validation

## Integration Tests

- session creation and restoration
- SSE event ordering
- citation and lock emission
- confirm and cancel lifecycle
- audit persistence

## End-To-End Tests

- upload -> ask precise table question -> follow-up -> preview -> cancel
- upload -> ask precise table question -> follow-up -> preview -> confirm
- upload PDF/image -> ask overview -> ask deeper follow-up -> inspect citations
- ask generic table question and verify grounded answer shape
- ask generic image/PDF question and verify non-shallow answer shape
- ask web-connected question and verify evidence separation

## Browser-Based Trial Monitoring

Preferred:

- `agent-browser` for formal page monitoring and interaction walkthroughs

Fallback:

- Playwright-based scripts when Windows CDP or local browser launch makes
  `agent-browser` unstable

The browser tooling choice should not change the acceptance criteria.

## Risks And Mitigations

### Risk 1: Runtime Drift Between Strong Regression Paths And Formal UI Path

Mitigation:

- route regression tooling and formal frontend through the same assistant service
- treat path mismatch as a P0 defect

### Risk 2: Wrong Lock, Then Wrong Preview, Then Wrong SQL

Mitigation:

- introduce explicit lock quality states
- prohibit execution from weak or missing locks
- require candidate clarification before advancing

### Risk 3: Generic Answers Sound Good But Carry Little Information

Mitigation:

- add generic-question rubric
- make rubric part of the formal corpus
- reject shallow answers even if they are fluent

### Risk 4: High-Risk Actions Blur Into Chat Language

Mitigation:

- separate answer text from action preview in protocol and UI
- persist execution audit independently of narrative response

### Risk 5: Persistent Degraded-Memory Mode Undermines Trial Quality

Mitigation:

- treat storage connectivity as trial-entry gating
- do not claim internal-trial readiness while session persistence remains
  structurally unreliable

## Approval State

Approved by user for design direction:

- internal trial as the immediate target
- stability and capability depth weighted equally
- table and image/PDF flows treated as equal-priority mainlines
- full CRUD allowed only with strict confirmation and audit
- multi-turn prepared conversations required for tuning
- generic questions must not receive shallow answers

Design status:

- ready for spec review
- ready for user review
- implementation planning should begin only after user reviews this written spec
