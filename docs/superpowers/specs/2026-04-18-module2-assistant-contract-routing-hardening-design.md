# Module 2 Assistant Contract And Routing Hardening Design

Date: 2026-04-18

## Summary

This design hardens the current Module 2 built-in assistant without changing the document parsing workflow, retrieval storage model, or unrelated frontend behavior.

The target is narrow:

- stop incorrect frontend snapshot short-circuits
- route preview-style write intents into preview-safe database drafting
- add lightweight runtime answer guardrails for provenance, temporal comparison, preview, and ambiguity
- keep the assistant UI user-facing and calm, without exposing internal toolchain as the main answer

## Problems To Fix

The current interaction defects are concentrated in three overlapping layers:

1. Intent routing is not requirement-aware enough.
2. Frontend snapshot short-circuiting is too permissive.
3. Answer contracts exist in prompts but are not enforced at runtime.

This causes four recurring user-visible failures:

- provenance questions may collapse into bare field values
- temporal comparison questions may collapse into a single year field
- preview-only action requests may miss the preview path and degrade into lookup answers
- generic deictic questions may guess instead of asking for clarification

## Goals

- Preserve existing Module 2 extraction and assistant APIs.
- Improve correctness for provenance, comparison, preview, and ambiguity turns.
- Keep snapshot answers only for truly safe, exact, low-ambiguity questions.
- Avoid document-specific, city-specific, or field-specific hardcoding.
- Add focused regression coverage for the repaired failure classes.

## Non-Goals

- Do not redesign the assistant UI.
- Do not alter module2 parsing outputs, trace artifacts, or retrieval indexing.
- Do not change other modules' routing behavior.
- Do not add new business-specific templates tied to one dataset.

## Design

### 1. Requirement-Aware Intent Signals

Extend the assistant intent-signal layer with narrow requirement detectors:

- provenance-needed
- temporal-comparison-needed
- preview-only action request
- generic deictic reference
- write-preview intent

These signals do not create a new autonomous planner.
They only tighten routing decisions and downstream safeguards.

### 2. Snapshot Fast-Path Narrowing

Frontend snapshot short-circuiting should be disallowed when the question requires:

- temporal comparison
- preview-only action planning
- unresolved deictic clarification

Exact-field detection must also become stricter so labels like `gross_value` are not misread as a generic `value` lookup.

### 3. Preview Routing Alignment

When the user is clearly asking for a write-oriented preview, the runtime should draft a write preview safely instead of downgrading to read-only lookup behavior.

This means:

- no automatic execution
- no execute tool unless the question truly asks for execution
- write-draft preview remains eligible even when the user says `do not execute`

### 4. Runtime Answer Guardrails

After the model answer is produced, add a lightweight repair layer:

- provenance questions must mention evidence/source category or explicitly state missing provenance
- temporal comparison questions must not degrade into a single-field value answer
- generic deictic questions without a current object lock must clarify instead of guessing
- preview-only questions must not end as plain field lookups

This guardrail should prefer correction by using existing frontend evidence helpers instead of inventing new answer content.

### 5. Stability Scope

Keep streaming changes minimal:

- preserve one terminal done path
- avoid replacing a valid answer with a weaker fallback
- do not alter unrelated stream protocol semantics

Frontend edits are optional and only allowed if a current assistant entry blocker is still reproduced during validation.

## Files In Scope

- `backend/app/modules/module2/assistant_1/intent_router.py`
- `backend/app/modules/module2/assistant_1/response_planner.py`
- `backend/app/modules/module2/assistant_1/frontend_grounding.py`
- `backend/app/modules/module2/assistant_1/prompt_blocks.py`
- `backend/app/modules/module2/assistant_1/agent_runtime.py`
- `backend/app/modules/module2/assistant_1/stream_runtime.py`
- targeted backend tests under `backend/tests/`

## Validation

Regression coverage must include:

- preview-style write request with `do not execute`
- provenance question that should not return only a value
- temporal comparison question that must not collapse to `statistical_year`
- generic `what is this value` question that must clarify when no lock exists

Success means the assistant becomes stricter where it used to guess, and more useful where it used to flatten preview or comparison requests into the wrong answer shape.
