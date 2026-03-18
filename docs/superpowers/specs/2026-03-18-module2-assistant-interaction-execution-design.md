# Module 2 Assistant Interaction Execution Design

Date: 2026-03-18

## Summary

This design turns the latest interaction-quality assessment for the Module 2 information extraction assistant into an execution-ready remediation spec.

Earlier Module 2 assistant specs already established:

- assistant architecture
- dual-mainline internal-trial acceptance
- interaction-quality hardening goals
- normal-path stability priorities

This document is narrower and more operational.
It answers one implementation question:

`what should the team change first, in which files, and with which acceptance gates so the Module 2 assistant actually feels like one natural task assistant instead of a capable analysis workbench with conversation layered on top`

The key conclusion is:

- the current bottleneck is no longer mainly raw answer accuracy
- the current bottleneck is user-visible interaction structure
- prompt polishing alone will not close the gap
- the next work must be sequenced around user-perceived trust, continuity, and one-answer-box behavior

This spec is intentionally execution-oriented.
It does not replace the broader design documents.
It provides the shortest correct path from current state to a reviewable, shippable interaction experience.

## Relationship To Existing Specs

This spec builds on and narrows the direction from:

- `docs/superpowers/specs/2026-03-15-module2-assistant-interaction-remediation-design.md`
- `docs/superpowers/specs/2026-03-16-module2-assistant-internal-trial-dual-mainline-design.md`
- `docs/superpowers/specs/2026-03-17-module2-assistant-interaction-quality-hardening-design.md`
- `docs/superpowers/specs/2026-03-17-module2-assistant-normal-path-stability-design.md`

Those documents explain why the interaction quality is insufficient and what product bar should be met.
This document focuses on the concrete execution sequence required to meet that bar without destabilizing the system.

## Current State Snapshot

The current assistant is already beyond demo quality in some areas:

- exact table lookup is strong
- row-follow-up continuity is real
- safety direction for database actions is correct
- user-visible answer text is materially more natural than earlier revisions
- SSE streaming exists and is product-oriented in shape

But the system is still failing the intended experience bar for four main reasons:

1. the main chat surface still exposes too much system scaffolding
2. broad-question streaming is still not truly low-latency streaming
3. session persistence and audit trust are still weakened by degraded storage paths
4. figure / image deep-context behavior is still not stable enough to be relied on equally with table flows

The result is that the assistant currently feels like:

- a useful analysis workbench with conversation support

instead of:

- one natural, evidence-grounded, trustworthy task assistant

## Problem Statement

The team should no longer ask:

`how do we make the answers sound a little more human`

The correct question is now:

`how do we stop the product from continuously leaking system structure into the conversation, while preserving evidence, safety, and task control`

That distinction matters because current user dissatisfaction is mostly caused by:

- answer framing being interrupted by lock banners, warnings, previews, and evidence blocks
- route changes being perceptible as personality changes
- streaming behavior feeling staged rather than conversational
- persistence instability reducing trust in follow-up turns and audited actions

If the team only continues prompt tuning, the assistant will improve text quality while still feeling like a system.

## Goals

- Make the default assistant interaction read as one clean answer thread.
- Separate user-facing answer content from evidence, runtime, and action scaffolding.
- Make broad-question turns stream like genuine assistant responses rather than delayed chunk playback.
- Preserve strong safety gates for CRUD and SQL while making those flows feel more conversational.
- Raise persistence confidence so refresh, continuation, and audit feel trustworthy.
- Define a concrete execution sequence with file-level work boundaries and regression gates.

## Non-Goals

- Do not redesign the entire Module 2 workbench from scratch.
- Do not replace the parsing stack in this execution pass.
- Do not weaken execution confirmation or audit requirements.
- Do not pretend live web results exist where they do not.
- Do not optimize for exaggerated personality, humor, or artificial friendliness.

## Execution Principles

### 1. Fix What The User Sees Before Optimizing What The User Cannot See

If the main answer surface is still polluted by system scaffolding, further language improvements will be under-realized.

### 2. Treat One-Answer-Box Behavior As A Product Contract

This is not only UI polish.
The answer surface must have a strict boundary.
Evidence, previews, and runtime state are companions, not co-equal dialogue content.

### 3. Stability Before Feature Breadth

Image depth and live web research are important, but they should not be addressed before normal-path streaming and persistence are trustworthy.

### 4. Preserve Safety While Improving Naturalness

Database actions must remain gated by preview, confirmation, and audit.
The change target is how those controls are presented, not whether they exist.

## Execution Phases

### Phase 1: Clean The Main Answer Surface

Purpose:

- make the formal assistant area feel like a conversation rather than an instrument panel

Primary work:

- move citations out of default inline rendering
- move action preview out of default inline rendering
- move lock banner out of default high-salience placement
- move assistant warnings out of default peer-level chat placement

Primary files:

- `frontend/components/DeepReadWorkbench.tsx`

Acceptance bar:

- the main chat view defaults to user messages plus assistant answers only
- evidence, lock, preview, and warning content are still available but not visually co-leading

### Phase 2: Decouple Answer Messages From Runtime And Evidence Events

Purpose:

- stop using the assistant dialogue message as the aggregation object for every system concern

Primary work:

- split answer state from evidence state
- split answer state from action-preview state
- split answer state from runtime-progress state
- ensure SSE event handling updates the right layer without mutating the semantic meaning of the answer message

Primary files:

- `frontend/components/DeepReadWorkbench.tsx`

Acceptance bar:

- `tool_status`, `citation_bundle`, and `action_preview` can all occur without altering the assistant message into a system-residue container

### Phase 3: Make Broad-Question Streaming Truly Conversational

Purpose:

- remove the user-visible feel of delayed answer assembly on knowledge and summary turns

Primary work:

- narrow `complete_then_chunk_primary`
- prefer true provider streaming on broad routes
- reduce final answer overwrite behavior
- preserve repair paths only where necessary

Primary files:

- `backend/module2/app/assistant/service.py`
- `frontend/components/DeepReadWorkbench.tsx`

Acceptance bar:

- broad questions begin producing useful content early
- final rendered output does not visibly switch tone or structure at completion

### Phase 4: Restore Trust In Persistence And Continuation

Purpose:

- make context continuity and audited actions feel dependable

Primary work:

- stabilize database connectivity and asyncpg availability
- distinguish local development degradation from acceptance and production requirements
- expose storage health clearly rather than silently falling back in critical environments
- validate assistant session and message persistence through refresh and continuation scenarios

Primary files:

- `backend/module2/app/db/storage.py`
- `backend/module2/app/assistant/service.py`

Acceptance bar:

- refresh-follow-up continuity works consistently
- assistant sessions and messages are durably stored in normal-path operation

### Phase 5: Make Clarification And Database Actions Feel Human

Purpose:

- keep the current safety bar while reducing workflow rigidity in the visible interaction

Primary work:

- shorten clarification answer shape
- present the easiest next step first
- move heavy candidate details behind secondary reveal
- make database-action dialogue read like cautious professional help rather than system preview dumping

Primary files:

- `backend/module2/app/assistant/tools.py`
- `frontend/components/DeepReadWorkbench.tsx`

Acceptance bar:

- ambiguity feels like natural clarification, not process overhead
- database preview feels like an assistant-guided confirmation flow, not a standalone control plane

### Phase 6: Unify Persona Across Routes

Purpose:

- make the assistant feel like one assistant across exact extraction, broad explanation, database action, and web-style turns

Primary work:

- harmonize route-level fallback writing
- harmonize response structure expectations
- reduce route-specific style discontinuity

Primary files:

- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/assistant/tools.py`
- `backend/module2/app/assistant/service.py`

Acceptance bar:

- users should not feel a clear personality switch when moving between route types

### Phase 7: Harden Figure Depth And Web Research

Purpose:

- bring the weakest major assistant capabilities closer to table-flow reliability

Primary work:

- stabilize figure-depth honesty and routing
- separate shallow figure summary from deep visual interpretation
- make web-research output clearly distinguish document evidence, general knowledge, and live external results

Primary files:

- `backend/module2/app/assistant/service.py`
- related visual-backend and retrieval integration points

Acceptance bar:

- figure questions remain useful and honest under both strong and weak evidence
- web-style questions feel product-complete rather than boundary-only

## Work Items

### P0 Work Items

#### M2-CHAT-001 Main Chat Single-Answer Surface

Files:

- `frontend/components/DeepReadWorkbench.tsx`

Change target:

- remove inline-first rendering of citations, lock banner, action preview, and assistant warning blocks from the default answer flow

Done means:

- main answer surface shows one assistant answer at a time by default

#### M2-CHAT-002 Assistant Event And Message Separation

Files:

- `frontend/components/DeepReadWorkbench.tsx`

Change target:

- split assistant answer state from runtime state, evidence state, and action-preview state

Done means:

- system events can no longer easily leak back into the answer presentation model

#### M2-STREAM-001 Real Broad-Route Streaming

Files:

- `backend/module2/app/assistant/service.py`

Change target:

- reduce complete-then-chunk usage on broad routes

Done means:

- broad questions visibly begin sooner

#### M2-STREAM-002 Stream Finalization Consistency

Files:

- `frontend/components/DeepReadWorkbench.tsx`
- `backend/module2/app/assistant/service.py`

Change target:

- reduce visible rewrite between incremental answer and final answer

Done means:

- final answer no longer feels like a different narrator taking over

#### M2-STORAGE-001 Persistence Health And Session Trust

Files:

- `backend/module2/app/db/storage.py`
- `backend/module2/app/assistant/service.py`

Change target:

- repair normal-path persistence and degrade intentionally, not silently, in non-dev-critical environments

Done means:

- continuation trust is restored

#### M2-CLARIFY-001 Lightweight Clarification Flow

Files:

- `backend/module2/app/assistant/tools.py`
- `frontend/components/DeepReadWorkbench.tsx`

Change target:

- clarification answers become short, natural, and easy to act on

Done means:

- users know what to do next without reading system-heavy candidate context first

#### M2-DB-001 Conversational Database Action Framing

Files:

- `backend/module2/app/assistant/tools.py`
- `frontend/components/DeepReadWorkbench.tsx`

Change target:

- keep strict confirmation and audit, but move details out of main answer space

Done means:

- database action flows feel like careful assistant help rather than workflow cards

#### M2-WARN-001 Warning Surface Reduction

Files:

- `frontend/components/DeepReadWorkbench.tsx`

Change target:

- compress warning visibility into lower-salience user guidance

Done means:

- the user sees boundaries without feeling surrounded by diagnostics

### P1 Work Items

#### M2-PERSONA-001 Route Persona Alignment

Files:

- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/assistant/tools.py`
- `backend/module2/app/assistant/service.py`

#### M2-VISION-001 Figure And Image Depth Stability

Files:

- `backend/module2/app/assistant/service.py`
- related visual backend integration points

#### M2-WEB-001 Web Research Completion

Files:

- `backend/module2/app/assistant/service.py`
- related retrieval integration points

#### M2-EVAL-001 Interaction Quality Evaluation Expansion

Files:

- `backend/module2/tools/assistant_targeted_quality_eval.py`

#### M2-FE-REG-001 Frontend Single-Answer-Box Regression Checks

Files:

- frontend E2E and report generation scripts

## File-Level Boundaries

### Frontend

The frontend should prefer a focused decomposition of the current assistant surface instead of continuing to accumulate logic inside one file.

Recommended logical boundaries:

- `AssistantChatPanel`
- `AssistantMessageList`
- `AssistantEvidencePanel`
- `AssistantActionPanel`
- `assistantEventReducer`

This does not require a large redesign before starting.
It does require the team to stop treating `DeepReadWorkbench.tsx` as the long-term home for all assistant concerns.

### Backend

Backend changes should remain focused and incremental.
The current backend can support the remediation if boundaries are made clearer around:

- stream generation
- visible-answer polishing
- route-specific fallback writing
- storage health and degradation
- figure-depth handling
- web-research handling

## Regression Matrix

The same core question set should be reused after every major change.

### Exact Extraction

- `直接看当前表格，滕州新二中的 PM10 是多少？`
- `继续，刚才那一行的污染类型是什么？`

### Clarification

- `帮我把那条记录也看一下。`

### Broad Reasoning

- `这份表里最值得优先核对的风险点是什么？别泛泛而谈。`
- `OCR 和版面分析在这类文档里到底怎么分工？`

### Database Action

- `把刚才这条记录整理成入库预览，先别执行。`
- `为什么现在还不能执行？`
- `确认执行，把这条记录写入目标表。`

### Figure And Image

- `这张图主要在表达什么？`
- `这张图里 2019 到 2021 的变化趋势是什么？有没有明显拐点？`

### Web Research

- `顺便帮我查一下网上类似方案，和当前文档场景相比有什么差别？`

### Continuation

- refresh page
- ask a follow-up on the last locked object

## Acceptance Criteria

The execution pass is considered successful only if all of the following are true:

1. the main assistant area defaults to one-answer-box behavior
2. broad-route answers visibly stream instead of feeling staged
3. final answer rendering no longer visibly rewrites the assistant人格
4. assistant persistence is trustworthy in normal-path operation
5. clarification feels light and usable
6. database actions remain strict but feel conversational
7. image and figure questions become more stable without sacrificing honesty
8. route changes no longer strongly feel like personality changes

## Risks

### Risk 1: Hiding Too Much Evidence

If the team over-corrects on clean chat presentation, users may lose confidence in evidence grounding.

Mitigation:

- keep evidence accessible but secondary

### Risk 2: Stream Refactor Regresses Quality

If broad-route streaming is changed too aggressively, answer quality may drop before timing improves.

Mitigation:

- retain controlled repair paths
- measure first visible content and final content quality separately

### Risk 3: Naturalness Work Weakens Action Safety

If database flows are over-softened, users may misunderstand whether an action is previewed or executed.

Mitigation:

- preserve strict execution semantics
- change presentation, not authority boundaries

## Exit Criteria

This spec is complete when the team has:

- implemented the P0 work items
- re-run the shared regression matrix
- demonstrated cleaner one-answer-box interaction in the main assistant path
- shown that refresh-follow-up continuity and database audit paths are trustworthy

P1 work is not required to begin immediately, but P1 should not be deferred indefinitely because figure depth and web research remain visible product gaps.

## Implementation Readiness

This document is intended to be the last design-layer document before direct implementation work.
The recommended implementation order is:

1. `M2-CHAT-001`
2. `M2-CHAT-002`
3. `M2-STREAM-001`
4. `M2-STREAM-002`
5. `M2-STORAGE-001`
6. `M2-CLARIFY-001`
7. `M2-DB-001`
8. `M2-WARN-001`
9. P1 items in the order most constrained by current regressions
