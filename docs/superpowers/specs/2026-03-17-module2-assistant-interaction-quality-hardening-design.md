# Module 2 Assistant Interaction Quality Hardening Design

Date: 2026-03-17

## Summary

This design turns the latest interaction-quality assessment into a focused hardening spec for the Module 2 information extraction assistant.

This document does not replace the earlier session, streaming, or dual-mainline assistant specs.
It narrows the next design target to one specific product question:

`how do we make the current assistant feel like one trustworthy, natural, evidence-grounded task partner instead of a capable system that still leaks internal process and instability into the user experience`

The approved direction remains aligned with the previously accepted `Approach B`, but this spec adds a new emphasis:

- answer quality is not only factual accuracy
- answer quality includes naturalness, continuity, restraint, and trust framing
- one-answer-box streaming behavior is part of assistant correctness, not only frontend polish
- knowledge questions and web-style questions must be handled as first-class assistant work, not as accidental fallback cases
- runtime latency and model mismatch are now treated as direct interaction-quality defects

This design builds on:

- `docs/superpowers/specs/2026-03-15-module2-assistant-interaction-remediation-design.md`
- `docs/superpowers/specs/2026-03-16-module2-assistant-internal-trial-dual-mainline-design.md`

Those specs established the assistant architecture and trial direction.
This spec tightens the user-visible quality bar.

## Why This Spec Exists

The current Module 2 assistant is now in a mixed state:

- some core retrieval behaviors are already strong
- some multimodal behaviors are now honest and better routed
- the frontend has partially moved toward one streaming answer
- but the overall interaction still feels less mature than the underlying capability

The current quality gap is no longer mainly:

`can the system retrieve something useful`

The current quality gap is now:

`can the system present the right answer, the right level of certainty, and the right next step in one coherent assistant interaction`

This matters because users do not judge the system by internal route quality.
They judge it by whether it feels:

- clear
- grounded
- natural
- continuous across turns
- safe when actions are implied
- honest when knowledge or web evidence is missing

Without this hardening pass, the assistant will continue to feel:

- impressive in some exact extraction scenarios
- overly mechanical in fallback scenarios
- too close to a process monitor when model or tool degradation happens
- weaker than it really is on broad or knowledge-style questions

## Current Evidence Snapshot

This design is grounded in the current repository state and recent regression evidence.

Observed strengths:

- real-media Excel regression already proves stable row-specific lookup and multi-turn row continuity
- PDF figure overview can now enumerate figure-level objects and admit when key points are still missing
- the backend now includes explicit `knowledge_explain` and `web_research` routes
- fallback answer writing has already become more human-facing than the earlier `结论 / 依据 / 补充说明` boilerplate
- the frontend event pipeline has already been partially refactored so tool progress can attach to the current streaming assistant message

Observed weaknesses:

- there is still no fresh frontend proof that the formal UI no longer renders internal tool flow as separate assistant-like message blocks
- old regression evidence clearly shows visible leakage of tool-state text into the user dialogue
- runtime sampling against the real model is currently unstable enough to create latency and timeout pressure on the interaction
- Module 2 runtime model configuration is not yet aligned with the user-requested `gemini-3.1-pro`
- knowledge-style answers have improved routing, but there is not yet a dedicated acceptance corpus proving they are deep, practical, and non-shallow
- web-style questions are currently honest about lacking live results, but still do not provide true grounded external retrieval
- DOCX parsing instability still blocks part of the assistant experience before the interaction layer even begins

## Problem Statement

The current assistant has crossed the line from prototype to usable tool, but it still fails an important product bar:

`the user should be able to ask a document question, a follow-up question, a knowledge question, or a database-action question and feel that one assistant is helping them think and act inside the document`

Instead, some current turns still feel like:

- a useful answer plus process residue
- a structured preview plus internal reasoning exposed too literally
- a safe fallback that is technically correct but emotionally and conversationally stiff

This spec exists to remove that gap.

## Goals

- Make the assistant answer as one coherent streamed response in the formal user path.
- Prevent internal processing language from dominating the user-visible answer surface.
- Preserve evidence grounding while making answers feel more human, calm, and direct.
- Improve answer depth for knowledge-style document-processing questions.
- Improve recognition-tier honesty and continuity for image, figure, and OCR-backed follow-up questions.
- Make database and SQL-related turns read like trustworthy assistance rather than preview-state dumps.
- Treat runtime latency and model mismatch as answer-quality issues, not only infrastructure issues.
- Create a concrete acceptance model for naturalness, groundedness, and continuity.

## Non-Goals

- Do not redesign the entire Module 2 workbench layout in this spec.
- Do not replace the parsing stack or OCR pipeline in this interaction-quality pass.
- Do not introduce unconstrained autonomous planning.
- Do not fake live web search when grounded external retrieval is unavailable.
- Do not optimize for marketing tone, personality theatrics, or exaggerated friendliness.
- Do not reduce safety language so far that risky actions become ambiguous.

## Quality Principles

### 1. The User Should Read One Answer, Not A Transcript Of System Internals

The assistant may internally classify routes, invoke retrieval logic, build locks, and emit progress events.
The user should not have to mentally reconstruct those layers from the dialogue itself.

The formal conversation should read as:

- question
- streamed answer
- evidence and preview companions

not as:

- question
- internal phase report
- route-adjacent answer
- fallback explanation
- tool-state residue

### 2. Naturalness Must Not Break Truthfulness

The goal is not to make the assistant sound chatty.
The goal is to make it sound like a competent document-processing partner.

Natural language here means:

- direct answer first
- evidence and scope framed clearly
- next step phrased in useful human terms
- uncertainty stated plainly

Natural language does not mean:

- pretending certainty
- hiding missing evidence
- omitting the difference between preview and execution

### 3. One Turn Must Preserve Three Things

Every formal answer should preserve:

- the user’s real question
- the strongest grounded evidence
- the next actionable mental step

If any one of these is lost, the answer quality drops:

- no direct answer means the user feels blocked
- no evidence means the user cannot trust it
- no next step means the assistant feels passive or shallow

### 4. Broad Questions Still Need Engineering Rigor

When users ask broad questions such as:

- what matters most here
- what is this chart likely about
- what is the difference between OCR and layout analysis
- what is the right way to store these extracted values

the assistant must still:

- bound the evidence scope
- distinguish stable from unstable claims
- provide practical reasoning, not only definitions
- show what is document-specific versus what is general method knowledge

### 5. Safety Language Must Feel Reassuring, Not Bureaucratic

The assistant should clearly stop unsafe execution.
But blocking language should read like a careful professional explanation, not like a system refusal template.

## Current Quality Assessment

The current assistant can be assessed across eight user-visible dimensions.

### 1. Precise Table Extraction

Current state:

- strong

Evidence:

- real-media regression proves exact row lookup
- row follow-up continuity already works in prepared Excel scenarios

Risk:

- still depends heavily on whether the question contains stable row anchors

### 2. Multi-Turn Context Continuity

Current state:

- moderately strong for table-row follow-up
- not yet equally mature for figures, images, and OCR fact groups

Risk:

- users can still fall out of the correct mental object if the lock is weak or the recognition tier is not clearly surfaced

### 3. Figure And Image Deep Reading

Current state:

- improved but uneven

Strength:

- figure-level object enumeration is now more honest

Weakness:

- image and OCR-backed follow-up still need deeper, more stable context carryover
- deep-reading answers can still flatten into safe but thin summaries when figure evidence is partial

### 4. Knowledge-Style Question Answering

Current state:

- structurally improved, but not yet proven by a dedicated evaluation corpus

Strength:

- dedicated route now exists

Weakness:

- no current regression gate proves answers are consistently practical, layered, and non-shallow

### 5. Web-Style Question Handling

Current state:

- safe but incomplete

Strength:

- the assistant now avoids pretending it has searched live sources when it has not

Weakness:

- real grounded external search is still missing
- user experience remains in a conservative holding pattern rather than a full capability

### 6. Database And NL-to-SQL Interaction Quality

Current state:

- safety posture is good
- interaction phrasing is still too mechanical in blocked or preview-heavy turns

Weakness:

- previews can read like state dumps rather than assistant explanations with a companion preview card

### 7. One-Box Streaming Experience

Current state:

- backend and frontend code are moving in the right direction
- visual acceptance is not yet fully re-proven in the formal path

Risk:

- old evidence shows visible fragmentation
- current code appears to improve the event merge path, but missing fresh proof prevents declaring this issue closed

### 8. Runtime Responsiveness

Current state:

- unstable enough to affect perceived quality

Weakness:

- recent real sampling attempts timed out
- runtime model mismatch may be contributing to lower-quality interaction than the approved target

## Design Scope

This hardening pass should focus on five tightly bounded work areas.

## Work Area 1: Answer Presentation Contract

This area defines what the user should actually read.

### Target Contract

Every assistant turn should render as:

- one streamed assistant answer body
- optional inline progress hint during generation
- optional evidence block
- optional action preview block
- optional lock banner

The answer body remains primary.
Evidence, preview, and lock remain companion structures.

### Prohibited User-Visible Patterns

The formal path should not show any of the following as separate assistant-style message cards in ordinary use:

- raw tool names
- route names
- fallback mode names
- internal status codes
- execution-phase narration that duplicates the final answer

### Allowed Exception

If the user explicitly asks:

- what did you call
- what tool did you use
- how did you get this answer

then the assistant may expose that information in a separate explanatory mode.

## Work Area 2: Natural Answer Writing Policy

This area governs how answers should sound.

### Default Answer Shape

For most factual document turns:

- first sentence: direct answer or direct limitation
- second section: strongest evidence and scope
- third section: next step or follow-up prompt

For knowledge-style turns:

- begin with the practical distinction or concept answer
- follow with 2-4 concrete engineering implications
- connect back to the current document only when the current evidence supports that bridge

### Style Targets

Answers should be:

- professional
- calm
- supportive
- detailed when needed
- concise when the answer is simple

Answers should not feel:

- theatrical
- bureaucratic
- over-formatted
- like log output
- like a textbook table of contents

### Safety Wording Target

Unsafe or blocked actions should be phrased in user-centric language such as:

- what is not safe yet
- why it is not safe yet
- what would make it safe

not only:

- blocked
- no_lock
- unresolved

## Work Area 3: Deep Context Continuity

This area ensures the assistant can carry forward the right object across turns.

### Target Lock Semantics

The assistant should explicitly and reliably preserve:

- `table_row`
- `figure`
- `ocr_fact_group`
- `field`

### Context Carryover Requirement

When the user says:

- that row
- this figure
- that image
- the numbers you just mentioned
- continue with that one

the assistant should either:

- reuse the correct locked object and say so naturally
- or explain clearly why the previous lock is insufficient

### Image And Figure Requirement

Image and figure follow-up should be hardened around three user-visible concepts:

- current recognition tier
- current stable object
- what can and cannot be read from that object

This avoids a common failure mode where OCR fragments are mistakenly presented as full figure understanding.

## Work Area 4: Knowledge And Web Question Quality

This area formalizes two newer answer families.

### Knowledge Question Requirement

The assistant must be able to answer questions about:

- OCR versus layout analysis
- table recovery versus raw OCR
- why row locking matters before storage
- how extracted values should be landed into a database
- why NL-to-SQL needs validation and confirmation
- common sources of extraction error

Each answer should cover:

- concept
- boundary
- practical workflow
- common pitfalls
- relation to the current document when valid

### Web Question Requirement

There are two supported modes:

- no live results available
- live grounded retrieval available

When no live results are available:

- the assistant must say so plainly
- it may still provide general knowledge
- it must not imply that external facts were retrieved

When live grounded retrieval is available in a future phase:

- external evidence must be explicitly separated from document evidence
- sources, timestamps, and links must be preserved

## Work Area 5: Runtime And Model Alignment

This area treats runtime configuration as part of interaction quality.

### Model Alignment Requirement

The runtime model should be aligned with the approved primary assistant model, not only listed as a fallback.

The current mismatch between requested model and active runtime model is considered a quality issue because it affects:

- answer depth
- long-form coherence
- tool-use reliability
- latency behavior

### Latency Requirement

Streaming quality should be evaluated by:

- first visible progress
- first answer token
- full answer completion
- timeout frequency

A streaming assistant that frequently stalls, times out, or falls back mid-turn is failing interaction quality even if the final fallback text is correct.

## Proposed Approaches

Three possible hardening approaches exist.

### Approach A: Prompt-Only Tone Improvement

What it does:

- rewrites the system prompt
- softens fallback phrasing
- leaves protocol, runtime, and acceptance structure mostly unchanged

Benefits:

- fast
- low implementation risk

Costs:

- does not fix fragmented rendering
- does not fix runtime instability
- does not prove knowledge answers are deep enough
- does not close the document-evidence versus external-evidence gap

### Approach B: Contract And Quality Hardening

What it does:

- hardens the user-visible answer contract
- aligns model runtime with approved target
- strengthens deep context continuity
- formalizes knowledge and web answer behavior
- adds explicit acceptance criteria and regression coverage

Benefits:

- solves the real problem instead of polishing only tone
- keeps current architecture intact
- supports safe future expansion into grounded web search and richer multimodal answers

Costs:

- broader than a prompt-only pass
- requires frontend, backend, and evaluation work to move together

### Approach C: Capability Expansion First

What it does:

- adds more tools and more external actions first
- delays answer-shape and interaction cleanup

Benefits:

- may increase apparent surface capability quickly

Costs:

- amplifies current interaction roughness
- makes the assistant feel stronger but less trustworthy

## Recommendation

This design recommends `Approach B`.

The interaction problem is now structural enough that prompt-only edits are insufficient.
At the same time, broad capability expansion before interaction hardening would magnify the exact trust problems the user is reacting to.

## Acceptance Criteria

The assistant should not be considered hardened until it passes the following acceptance checks.

## A. One-Answer-Box Acceptance

Required:

- one user turn produces one assistant answer card in the formal dialogue
- progress can appear inline during streaming
- evidence and action preview can appear as companion blocks attached to that answer
- tool-state text does not appear as separate assistant-style cards in normal use

Failure examples:

- separate `工具状态` cards remain visible in the conversation
- fallback mode text renders as if it were a second assistant answer

## B. Naturalness Acceptance

Required:

- answer begins by responding to the actual question
- answer sounds like a professional helper, not a system trace
- blocked actions explain what is missing in user terms
- no route names, tool names, or internal labels appear unless explicitly requested

Failure examples:

- answer body reads like execution status
- preview status and lock labels dominate the prose

## C. Groundedness Acceptance

Required:

- precise extraction answers cite stable evidence
- broad answers state evidence scope
- image and figure answers state recognition tier honestly
- knowledge answers separate general method from document-specific evidence

Failure examples:

- claiming chart meaning from title-only evidence
- claiming external recency without live search
- implying execution from preview-only state

## D. Context Continuity Acceptance

Required:

- table-row follow-up preserves the correct row when stable
- image and figure follow-up preserves the correct figure or OCR fact group when stable
- when carryover is not safe, the assistant clearly says what broke and what to clarify

Failure examples:

- follow-up silently switches to another row
- OCR facts are promoted into figure-level claims without evidence

## E. Knowledge Answer Depth Acceptance

Required:

- concept answer is followed by practical engineering implications
- at least two concrete pitfalls, decision points, or workflow steps are given when the question calls for depth
- answer does not stop at definitions

Failure examples:

- OCR versus layout explained in one shallow sentence
- table extraction described without mentioning structural recovery and error sources

## F. Web Honesty Acceptance

Required:

- no live web result means explicit no-live-result disclosure
- future live web mode must separate external evidence from document evidence

Failure examples:

- assistant says it searched when it did not
- assistant merges general knowledge and current news into one undifferentiated answer

## G. Runtime Acceptance

Required:

- configured assistant runtime uses the approved primary model
- first visible response feels prompt enough for interactive use
- timeout and fallback frequency stays low enough that fallback is exception behavior, not the normal path

## Evaluation Corpus Expansion

This hardening pass requires a more focused corpus than the current extraction-heavy regressions.

The new quality corpus should include at least six scenario families.

### 1. Exact Table Retrieval

Examples:

- direct row-value lookup
- direct cited follow-up on the same row

### 2. Unsafe Table Follow-Up

Examples:

- unresolved row anchor
- attempt to preview storage or SQL after weak grounding

### 3. Figure And OCR Tier Questions

Examples:

- list figure objects
- explain what is figure-level versus OCR-backed only
- ask a follow-up on the same image object

### 4. Knowledge Questions

Examples:

- OCR versus layout analysis
- why row locks matter
- why NL-to-SQL needs strict confirmation
- common errors in document landing pipelines

### 5. Generic Broad Questions

Examples:

- what matters most in this sheet
- what should I verify first in this chart
- what is the likely focus of this document

### 6. Web-Style Questions

Examples:

- ask for latest trends
- ask for policy or standards updates
- ask to separate current document evidence from external information

Every scenario should define:

- user question
- expected route
- expected lock behavior
- expected answer shape
- prohibited phrases or behaviors

## Metrics

The hardening pass should track at least these quality metrics:

- one-card answer pass rate
- exact-answer groundedness pass rate
- follow-up lock retention rate
- knowledge-answer depth pass rate
- generic-question non-shallow pass rate
- false live-search implication rate
- preview versus execution confusion rate
- timeout or fallback rate per scenario family

## Verification Strategy

This hardening pass should be verified through three complementary layers.

### 1. Backend Contract Verification

Purpose:

- confirm routing, lock behavior, fallback behavior, and preview behavior are correct independent of UI rendering

Required checks:

- route selection for extraction, knowledge, and web-style questions
- lock continuity across prepared follow-up turns
- preview-versus-execution semantics for database and SQL intents
- no fake live-search claims when live retrieval is unavailable

### 2. Real-Media Answer Verification

Purpose:

- verify that actual answers on real documents remain grounded, detailed, and non-shallow

Required checks:

- exact-answer scenarios with expected citations
- follow-up scenarios with expected continuity
- knowledge scenarios with expected practical depth
- broad-question scenarios with explicit evidence scope and non-shallow reasoning

Each real-media scenario should record:

- the question
- the expected answer structure
- the expected lock state
- the actual answer
- pass or fail notes

### 3. Formal Frontend Path Verification

Purpose:

- ensure the shipped user path matches the intended assistant quality

Required checks:

- one turn renders as one assistant answer card
- progress remains inline rather than fragmenting into extra answer cards
- companion evidence and action previews attach to the same assistant turn
- assistant completion leaves one stable final answer instead of residue from intermediate states

If browser automation is blocked in the local environment, the team may temporarily fall back to scripted frontend verification or DOM-level checks.
However, the issue is not considered closed until the formal page path is visually re-verified.

## Implementation Boundaries

This design intentionally stays within the existing Module 2 surfaces:

- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/assistant/service.py`
- `backend/module2/app/assistant/tools.py`
- `backend/module2/app/assistant/provider.py`
- `frontend/components/DeepReadWorkbench.tsx`
- `backend/module2/tools/assistant_clean_eval.py`
- `backend/module2/tools/assistant_real_media_regression.py`
- frontend automation and targeted verification scripts

This design does not require a new assistant service architecture.
It requires tightening the current one.

## Execution Order

This hardening work should proceed in the following order:

1. align runtime model and timeout expectations
2. finalize the one-answer-box rendering contract
3. harden knowledge and web question answer policy
4. deepen image, figure, and OCR context continuity
5. expand the evaluation corpus and acceptance checks
6. rerun formal frontend verification before declaring the issue closed

This order is important because there is little value in polishing answer writing if the runtime model is misaligned or the frontend still fragments the answer surface.

## Risks And Mitigations

### Risk 1: Prompt Changes Hide Rather Than Solve Structural Problems

Mitigation:

- treat prompt edits as one layer only
- verify frontend and runtime acceptance separately

### Risk 2: Naturalness Work Reduces Safety Explicitness

Mitigation:

- keep preview, confirmation, and audit semantics unchanged
- change phrasing and presentation, not safety logic

### Risk 3: Image Context Remains Weaker Than Table Context

Mitigation:

- explicitly prioritize figure and OCR fact-group continuity in the next evaluation pass

### Risk 4: Model Mismatch Continues To Distort Quality Assessment

Mitigation:

- align active runtime model before drawing final conclusions about answer quality

### Risk 5: Frontend Looks Fixed In Code But Not In Actual Use

Mitigation:

- require fresh formal-path visual verification, not only code-path reasoning

## Approval State

Approved by user for design direction:

- the latest interaction-quality assessment should be expanded into a formal remediation design
- the assistant should feel more natural and human while staying evidence-grounded
- one streamed answer box is part of the product requirement
- knowledge questions, extraction questions, database preview questions, and future web questions all belong to the same assistant quality bar

Design status:

- ready for self-review
- ready for user review after self-review
- implementation planning should begin only after the user reviews this written spec
