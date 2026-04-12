# Post-Analysis High-Efficiency Migration Execution Plan

Date: 2026-03-29

## Purpose

This note converts the current repository assessment into an execution-oriented migration plan.

It is intentionally practical.
It does not redefine the architecture.
It defines how to finish the migration with:

- preserved full workflow
- high migration speed
- bounded regression risk
- packaging readiness

This plan should be read together with:

- `docs/superpowers/specs/2026-03-29-final-optimal-project-architecture-and-directory-blueprint.md`
- `docs/superpowers/specs/2026-03-29-migration-execution-baseline-and-acceptance.md`
- `docs/superpowers/specs/2026-03-29-live-workflow-regression-entrypoints.md`

## Current Stage

The project is no longer deciding whether to unify.
The project is already in the middle of structural convergence.

The most accurate stage label is:

`unified public backend established, internal engine convergence still in progress, workflow acceptance not yet fully closed`

That means:

- `backend/app` is already the public backend authority
- `backend/module2` is still the real extraction engine
- `backend/module4` is still the real graph and risk engine
- frontend and Electron already align with the unified gateway direction
- the remaining work is mostly structural convergence, cleanup discipline, and live workflow closure

## The Full Workflow That Must Be Preserved

The migration is only successful if the current end-to-end workflow remains intact:

1. auth register, login, me, logout
2. frontend upload through unified FastAPI
3. PDF extraction through the current Module2 chain
4. DOC or DOCX async conversion or preview path into the PDF-oriented parsing chain where required
5. MinerU-driven parsing artifacts remain part of the live workflow
6. Gemini Vision figure or chart enhancement remains part of the live workflow
7. summarize and trace remain usable
8. assistant1 grounded answers remain usable
9. Module2 -> Module4 sync remains usable
10. Module4 graph, alerts, rules, explain, and simulate remain usable
11. Electron packaged runtime remains aligned with the unified backend entry

Everything in this plan is subordinate to that workflow.

## What Must Not Be Mistaken For Source

The repository still contains several classes of non-source content.

These are not migration targets and should not drive architecture decisions:

- `.runlogs/**`
- `frontend/.runlogs/**`
- `module2/runlogs/**`
- `backend/module2/artifacts/**`
- `backend/module4/workspaces/**`
- `backend/backend/**`
- `dist-electron/**`
- test snapshots and temporary regression output

The rule is:

`runtime output is part of the product lifecycle, but not part of the source architecture`

## Execution Strategy

The fastest safe migration path is not to keep splitting every large file into many tiny files.

The correct strategy now is:

- freeze public contracts
- isolate runtime junk and historical residue
- finish medium-grain engine convergence
- run real workflow regression
- only then do broad cleanup and dead-code retirement

## Workstream A: Public Contract Freeze

Keep these stable during the current wave:

- `/api/*`
- `/extract/*`
- `/module4/*`
- auth cookie semantics
- extraction job create and poll semantics
- artifact path and artifact URL semantics
- DOCX preview and conversion semantics
- Module2 -> Module4 document sync payload semantics

This is the boundary that allows fast internal migration without frontend churn.

## Workstream B: Repository Hygiene And Classification

Objective:

- stop runtime garbage and historical leftovers from polluting migration work

Immediate actions:

- keep packaging exclusions strict
- keep `.gitignore` aligned with runtime-output directories
- stop treating `backend/backend/**` as source
- stop treating root `module2/runlogs/**` as source
- stop treating historical `trace_rois` and old extraction artifacts as source

Important note:

- do not delete historical material blindly if it might still be useful for debugging
- classify first, exclude from packaging and migration scope second, physically remove only when confirmed safe

## Workstream C: Module4 Convergence First

Module4 is the best next structural target because it is already relatively close to a stable layered shape.

Priority order inside Module4:

1. keep `app/main.py` moving toward a thin-entry shape
2. continue pushing orchestration into `services/app_runtime.py`
3. split `db/storage.py` by responsibility only when the read and write seams are clear
4. keep GraphRAG capability files explicitly secondary to the current ingest mainline

Why this is the best next engine move:

- lower risk than deep Module2 parser surgery
- meaningful architectural payoff
- directly helps packaging and maintainability

## Workstream D: Module2 Medium-Grain Convergence

Module2 is still the highest-risk engine, so it should not be migrated through many more tiny-file cuts.

The preferred direction now is:

- keep `app/main.py` as a composition root only
- keep `core/parser.py` as a parser facade only
- merge over-fragmented runtime helpers into medium-grain coherent bundles where that improves readability

The next Module2 work should be organized around coherent clusters such as:

- parse entry and dispatch
- non-PDF preparation and conversion
- PDF visual parsing and vision orchestration
- table and figure pure-rule logic
- schema pipeline assembly
- trace and artifact response support

Do not optimize for:

- maximum number of files
- cosmetic symmetry
- moving logic just because a file is still large

Optimize for:

- clearer responsibility boundaries
- reduced cross-file hopping cost
- preserved runtime behavior

## Workstream E: Frontend Mainline Decomposition

Only two frontend files are currently severe concentration risks:

- `frontend/components/DeepReadWorkbench.tsx`
- `frontend/components/knowledge-nexus/KnowledgeNexusNeo4j.tsx`

The correct target shape is not MVVM.
The correct target shape is feature decomposition:

- page shell
- upload and task area
- preview area
- results and trace area
- assistant area
- graph canvas
- graph detail and analysis panel

Do not spend the next migration wave on non-mainline frontend files first.

## Workstream F: Live Workflow Regression Closure

The migration should only be treated as structurally complete after live workflow confidence is good.

Execution order:

1. start unified backend and frontend
2. run `npm run wait:gateway`
3. run `npm run qa:live:workflow:smoke`
4. then run `npm run qa:live:workflow`
5. then run desktop-oriented smoke where needed

The smoke sequence exists to shorten the feedback loop before the full regression run.

## Immediate Next Execution Order

The best high-efficiency next order is:

1. keep unified gateway remnants clean and consistent
2. keep live regression entrypoints usable and fast
3. continue Module4 thin-entry convergence
4. then return to Module2 medium-grain convergence
5. then decompose the two giant frontend workbench files
6. then run the full real workflow acceptance
7. only after that, retire confirmed dead or compatibility-only code

## Immediate Do / Delay Decisions

Do now:

- unified gateway residual cleanup
- smoke-regression entrypoint completion
- Module4 entry and runtime convergence
- Module2 medium-grain convergence
- explicit source vs runtime-output classification

Delay:

- broad compatibility retirement
- broad dead-code deletion
- cosmetic naming cleanup
- aggressive frontend non-mainline cleanup
- any migration that changes public contracts

## Success Criteria For This Plan

This execution plan is working if:

- migration continues without workflow regressions
- new structural changes reduce complexity without creating another tiny-file explosion
- live regression becomes easier to run, not harder
- packaging exclusions remain trustworthy
- the codebase moves closer to the final architecture blueprint without sacrificing the current product path

## Final Execution Principle

The current repository should now follow this rule:

`finish structural migration quickly, but only through bounded moves that keep the full workflow alive and make final acceptance easier.`
