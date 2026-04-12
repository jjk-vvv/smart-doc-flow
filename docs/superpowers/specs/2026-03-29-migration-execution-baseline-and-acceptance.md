# Migration Execution Baseline And Acceptance

Date: 2026-03-29

## Goal

This document locks the execution baseline for the next migration phase.

The working rule is:

- prioritize migration completion over cosmetic optimization
- do not degrade behavior while migrating
- finish the remaining structural migration first
- run a full real workflow regression before large-scale cleanup, deduplication, or style polishing

## Execution Strategy

The migration now follows a two-pass model.

### Pass 1: Structural Migration Completion

Focus:

- finish responsibility migration
- keep public contracts stable
- preserve the full working workflow
- reduce oversized orchestration surfaces
- avoid creating many tiny files unless a boundary is clearly coherent

Do not prioritize:

- code-style cleanup
- large naming cleanup
- comment beautification
- aggressive dead-code deletion
- early compatibility retirement

### Pass 2: Post-Migration Cleanup And Optimization

Only after the full workflow passes end-to-end:

- remove confirmed dead code
- merge over-fragmented files where safe
- normalize naming and error messages
- tighten packaging exclusions
- perform focused bug fixes and quality cleanup

## Frozen Public Contracts

These contracts must remain stable during the current migration wave unless correctness requires a targeted fix:

- `/api/*`
- `/extract/*`
- `/module4/*`
- auth cookie and session behavior
- extraction job creation and polling semantics
- artifact path and artifact URL semantics
- Module2 to Module4 sync payload semantics
- frontend same-origin API usage

## Non-Degradation Acceptance Rules

The migration is only acceptable if all of the following remain true:

1. Auth remains available through the unified FastAPI backend.
2. Frontend file upload still reaches the unified backend entry.
3. PDF files still run through the current extraction chain.
4. DOC and DOCX files still support preview or conversion and enter the PDF-oriented parsing path where required.
5. MinerU-driven parsing artifacts still remain part of the active workflow.
6. Figure and chart understanding still retains Gemini Vision capability.
7. `extract/jobs/create` and `extract/jobs/status` remain usable.
8. `extract/batch` remains usable.
9. `extract/summarize` remains usable.
10. `extract/trace/locate` remains usable.
11. Assistant1 grounded chat remains usable on extracted document artifacts.
12. Module2 extraction results still sync into Module4.
13. Module4 graph, evidence, alerts, rules, explain, and simulate remain usable.
14. Packaging must not include runtime junk, transient test output, or unrelated artifact files.

## Required End-To-End Workflow Regression

Before this migration can be considered complete, the project must pass a full workflow run covering:

1. Register, login, `me`, and logout.
2. Upload a PDF through the unified backend and complete extraction.
3. Upload a DOCX through the unified backend and complete the conversion-plus-extraction path.
4. Verify extracted structured fields are present.
5. Verify trace hits and summarize responses are present.
6. Verify Assistant1 answers against the extracted file context.
7. Verify Module2 -> Module4 sync occurs.
8. Verify Module4 graph file view and graph detail endpoints return usable data.
9. Verify alerts and evidence are queryable.
10. Verify cache clear followed by rerun still works.

## Required Regression Inputs

The full workflow regression should use a stable sample set that includes:

- one PDF with structured fields
- one DOCX that requires preview or conversion
- one document with figures or charts
- one image input

## Current Migration Priorities

The next migration work should happen in this order:

1. keep the public contracts frozen
2. continue Module4 orchestration consolidation
3. keep Module2 on medium-grain runtime bundles without further tiny-file explosion
4. reduce compatibility ambiguity without deleting required bridges too early
5. run full workflow regression
6. only then start broad cleanup and optimization

## Current Phase Decision

For the current repository state, the most efficient safe move is:

- continue structural migration now
- postpone most cleanup and bug-sweeping until after the main migration closes
- allow targeted fixes immediately when a migration step causes workflow risk

That means:

`migrate first, but never knowingly ship a regression into the next step.`
