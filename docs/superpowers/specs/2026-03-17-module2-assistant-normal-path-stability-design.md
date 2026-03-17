# Module 2 Assistant Normal-Path Stability Design

Date: 2026-03-17

## Summary

This design focuses on one specific problem inside the Module 2 information extraction assistant:

`why the normal assistant path is still unstable enough to cause apparent model timeouts, brittle streaming, and degraded answer quality even when the system is not truly down`

This is intentionally a narrower design than the earlier interaction-quality hardening spec.
The earlier spec focused on how the assistant should feel to the user.
This spec focuses on why the mainline assistant path is still fragile underneath that user experience and how to fix it in the right order.

The key conclusion is:

- the current timeout issue is not only model latency
- the current normal path is affected by upstream stream-compatibility mismatch
- the system currently uses an overly narrow definition of "first token"
- the current fallback path is not truly independent from the failing path
- the extraction side still sends overly large prompts in some routes, which increases truncation and instability

Because of that, this design recommends a three-stage sequence:

1. fix provider compatibility and timeout semantics first
2. reduce prompt and context load second
3. add true resilience layers only after the normal path is healthy

## Why This Needs Its Own Spec

The current user-visible symptoms include:

- model timeout
- streamed answer not starting in time
- streamed answer starting but not producing visible content
- fallback answering too often
- extraction answers truncating under long prompts
- overall quality being judged as "the model is unstable"

Those symptoms look like one problem from the surface, but they are not one problem.
If the team treats everything as "the model is slow" and keeps adding fallback patches, the assistant will remain hard to reason about and hard to improve.

This needs a separate normal-path stability spec because the system currently mixes four different failure classes into one visible outcome:

- provider protocol incompatibility
- timeout accounting mismatch
- same-provider fallback recursion
- route-specific context overload

Without splitting those classes, the team cannot tell whether a fix is real or just another layer of masking.

## Relationship To Existing Specs

This design extends but does not replace:

- `docs/superpowers/specs/2026-03-17-module2-assistant-interaction-quality-hardening-design.md`

That earlier document defines the user-visible quality bar:

- one streamed answer box
- more natural answers
- better figure and OCR continuity
- better knowledge-style response quality

This new document defines the infrastructure and contract changes required so the assistant can reliably meet that bar in real operation.

In short:

- the interaction-quality spec says what the user should experience
- this normal-path stability spec says what must change so that experience is reliably deliverable

## Current Evidence Snapshot

This design is based on the current Module 2 runtime configuration, source code, local debug logs, and raw upstream provider probing.

### Runtime Configuration Observed

Current runtime values observed in `backend/module2/.env`:

- `MODULE2_ASSISTANT_API_BASE=https://hiapi.online/v1`
- `MODULE2_ASSISTANT_MODEL=gemini-3.1-pro`
- `MODULE2_ASSISTANT_TEMPERATURE=1.0`
- `MODULE2_ASSISTANT_FIRST_TOKEN_TIMEOUT_SEC=12`
- `MODULE2_ASSISTANT_STREAM_IDLE_TIMEOUT_SEC=20`
- `MODULE2_ASSISTANT_MAX_TOKENS=2200`

### Source-Level Evidence

Current provider behavior in `backend/module2/app/assistant/provider.py`:

- streaming logic only yields when `choices[].delta.content` is non-empty
- `delta.reasoning_content` is ignored
- empty but valid stream frames are ignored
- no provider event classification exists between "frame received" and "visible content emitted"

Current service behavior in `backend/module2/app/assistant/service.py`:

- timeout accounting starts before any visible content exists
- "first token timeout" currently really means "no visible delta.content was yielded"
- an active upstream stream can therefore be misclassified as dead
- the fallback completion path still relies on the same provider family and does not function as a truly independent recovery channel

### Upstream SSE Probe Evidence

Raw probing against the current compatible endpoint showed the following pattern:

- first provider frame arrived at about 5.98 seconds
- the first streamed chunk contained empty `delta.content`
- subsequent chunks carried `delta.reasoning_content`
- later chunks returned `finish_reason=stop`
- some runs also emitted `finish_reason=content_filter`
- some runs produced no stable final visible content chunk at all

This is strong evidence that at least part of the observed "timeout" behavior is actually:

- active stream received
- provider produced semantically meaningful events
- local parser did not treat those events as stream progress
- service timer still expired waiting for a visible token

### Prompt Load Evidence

Assistant answer prompting itself was not the primary issue in the sampled normal chat turn.
One sampled built message was about `1763` characters total, which is not abnormally large.

However, extraction-side debug evidence showed severe context load in at least one route:

- file: `backend/module2/.runlogs/module2-llm-debug/20260317/003712_475842_field_extract_gemini-3-pro.json`
- `prompt_tokens: 38529`
- `completion_tokens: 2193`
- `finish_reason: "length"`

This confirms a separate but related normal-path problem:

- some extraction prompts are large enough to invite truncation
- truncation degrades answer completeness
- large upstream requests also increase latency and instability pressure

## Problem Statement

The Module 2 assistant does not currently have a trustworthy definition of healthy streaming on its mainline path.

As a result:

- the system may treat a live provider stream as dead
- the user sees avoidable timeout or fallback behavior
- the team cannot distinguish protocol mismatch from true model slowness
- fallback usage is inflated
- large extraction contexts continue to push some routes into truncation

The real problem is therefore not:

`the model is occasionally slow`

The real problem is:

`the system lacks a robust normal-path contract for compatible streaming, timeout accounting, route-specific token budgeting, and failure-class separation`

## Goals

- Make normal-path streaming compatible with the observed upstream provider behavior.
- Split timeout semantics into meaningful phases instead of one ambiguous "first token timeout".
- Prevent active reasoning-only or empty-content streams from being misclassified as dead immediately.
- Make fallback behavior truly diagnostic and meaningfully separate from the primary failing mode.
- Reduce extraction prompt overload enough to materially lower truncation risk.
- Add observability so the team can see whether failures come from provider protocol, latency, content filtering, or prompt size.
- Support the earlier interaction-quality goal of one stable streamed answer box by making the backend stream contract reliable.

## Non-Goals

- This spec does not redesign the full assistant UX.
- This spec does not replace the provider or model by default.
- This spec does not attempt true model fine-tuning.
- This spec does not solve every OCR or parsing weakness in Module 2.
- This spec does not add unrestricted autonomous SQL execution.
- This spec does not claim live web retrieval support where it does not yet exist.

## Root Cause Analysis

### Root Cause 1: Provider Stream Semantics Mismatch

The current provider implementation assumes that a valid stream becomes meaningful only when `delta.content` contains visible text.

That assumption is too narrow for the observed upstream endpoint behavior.
The endpoint can emit:

- empty content frames
- reasoning frames
- termination frames
- content-filter termination

before ever emitting visible answer content in the exact shape the local parser expects.

This means the current logic is effectively checking:

`did I receive visible answer text`

when it should be checking a richer sequence:

`did I connect`
`did I receive the first frame`
`did I receive semantic activity`
`did I receive visible content`
`how did the stream end`

### Root Cause 2: Timeout Definition Mismatch

`MODULE2_ASSISTANT_FIRST_TOKEN_TIMEOUT_SEC` is currently used as if it measures whether the provider has started responding.

In practice, it measures something closer to:

`time until a non-empty content delta was yielded to the UI`

Those are not the same thing.
If the provider is connected and actively streaming but only producing reasoning frames or empty deltas at first, the current code still times out as though nothing happened.

This creates false timeout classification and makes log-based diagnosis misleading.

### Root Cause 3: Fallback Is Not Truly Decoupled

When the stream path fails, the system often falls back to another completion path that still depends on the same provider family and similar assumptions.

That means current fallback behavior has two weaknesses:

- it is not a truly independent resilience layer
- it blurs the diagnosis because the system can "recover" without proving the mainline path is fixed

This produces a misleading development loop:

- mainline stream remains unhealthy
- fallback makes the UI look less broken
- root cause remains unresolved

### Root Cause 4: Extraction Prompt Overload

Some extraction paths are sending prompt payloads large enough to cause `finish_reason="length"`.

That indicates at least one of the following:

- too much raw document context is being injected
- insufficient route-specific compression exists
- table, figure, or field evidence is not being budgeted aggressively enough
- output length is consuming capacity that should have been reserved for answer completion

This is a separate problem from stream compatibility, but it directly affects normal-path stability because large requests amplify latency, truncation, and provider variance.

### Root Cause 5: Insufficient Observability

The current system does not yet record a reliable distinction between:

- stream opened
- first frame received
- first semantic frame received
- first visible text received
- finish reason
- provider content filter
- fallback trigger cause

Without those metrics, the team cannot measure whether a change actually fixes the mainline path.

## Design Principles

### 1. Normal Path Must Be Measurable Before It Is Optimized

If the system cannot tell the difference between:

- connection delay
- first frame delay
- first visible text delay
- truncation
- content filtering

then the team is optimizing blind.

### 2. Active Streams Must Not Be Classified As Dead Too Early

A stream that is connected and emitting compatible events should not be treated as a timeout simply because visible text has not yet arrived.

### 3. Compatibility Fixes Come Before Provider Replacement

Before changing providers or building a dual-provider architecture, the current provider contract must be made compatible with the actual upstream behavior.
Otherwise the team risks treating a local parser bug as a provider-quality judgment.

### 4. Token Budgeting Must Be Route-Specific

The assistant should not handle field extraction, table grounding, figure explanation, and knowledge answers with one undifferentiated context strategy.
Each route needs its own evidence budget and output budget.

### 5. Fallback Should Be Rare And Informative

Fallback is still useful, but after this design it should mean:

- exceptional recovery path
- clear cause category
- independent or materially different path when possible

not:

- the normal way the system survives ordinary turns

## Proposed Approaches

### Approach A: Tune Timeouts And Add More Fallback

What it does:

- increase `FIRST_TOKEN_TIMEOUT_SEC`
- increase `STREAM_IDLE_TIMEOUT_SEC`
- keep current parsing assumptions
- improve fallback wording

Benefits:

- fastest to ship
- lowest code change count

Costs:

- does not fix semantic mismatch with the upstream stream
- false timeout classification can still happen
- longer timeout windows may only hide the problem
- fallback remains overused

### Approach B: Fix Mainline Contract First

What it does:

- hardens provider compatibility
- splits timeout semantics into multiple measurable phases
- records stream lifecycle telemetry
- reduces route-specific prompt overload
- keeps fallback but stops relying on it as the main recovery mechanism

Benefits:

- addresses the actual root causes
- improves both reliability and diagnosis
- supports later interaction-quality improvements

Costs:

- broader than a timeout tweak
- requires provider, service, prompt-budget, and evaluation changes together

### Approach C: Introduce Dual-Provider Resilience Immediately

What it does:

- keeps working around the current provider path by adding a second provider or second model mainline

Benefits:

- may reduce user-visible failures faster in some cases

Costs:

- risks masking parser and timeout defects
- adds operational complexity before the current path is understood
- makes diagnosis harder if both paths are not clearly instrumented

## Recommendation

This design recommends `Approach B`, followed by optional parts of `Approach C` only after `Approach B` is verified.

The right order is:

1. provider compatibility and timeout semantics
2. route-specific token budget reduction
3. optional independent resilience layer

This order matters because otherwise the team may build expensive resilience around a mainline path that was incorrectly implemented in the first place.

## Proposed Design

## Core Units And Interfaces

To keep this work implementable and testable, the stability remediation should be split into four small units with clear boundaries.

### Unit 1: Provider Stream Event Parser

Purpose:

- translate raw upstream SSE frames into a small internal event model

Owns:

- frame parsing
- finish-reason extraction
- reasoning-versus-content distinction
- low-level malformed-frame handling

Does not own:

- timeout policy
- fallback selection
- frontend event emission

Primary interface:

- input: raw provider stream frames
- output: normalized provider stream events

### Unit 2: Stream Lifecycle Controller

Purpose:

- consume normalized provider events and decide whether the stream is healthy, degraded, empty, filtered, or timed out

Owns:

- connect and phase timeout accounting
- first-frame versus first-visible-content classification
- stream idle detection
- fallback trigger reason

Does not own:

- raw frame parsing
- answer writing policy
- route evidence selection

Primary interface:

- input: normalized provider stream events
- output: user-visible text deltas plus structured lifecycle diagnostics

### Unit 3: Route Budget Policy

Purpose:

- decide how much structural context each route is allowed to send downstream

Owns:

- per-route evidence caps
- per-route serialization caps
- per-route output token guidance
- overload compaction strategy

Does not own:

- field matching correctness itself
- frontend rendering
- database execution logic

Primary interface:

- input: route name plus extracted evidence objects
- output: bounded answer context ready for prompting

### Unit 4: Stability Regression Harness

Purpose:

- verify the previous three units under mocked and real-provider scenarios

Owns:

- mocked SSE scenario tests
- real-provider smoke checks
- extraction overload regression
- stability acceptance reporting

Does not own:

- runtime serving logic
- production fallback wording

Primary interface:

- input: prepared test scenarios and live configuration
- output: pass or fail evidence with failure classification

## Work Area 1: Provider Compatibility Layer

The provider layer in `backend/module2/app/assistant/provider.py` should stop modeling streaming as a plain `Iterable[str]`.

Instead, the internal representation should support at least a lightweight event model such as:

- `stream_opened`
- `frame_received`
- `reasoning_delta`
- `content_delta`
- `finish`
- `error`

The public service layer does not need to expose all of these to the frontend, but it must be able to distinguish them internally.

### Required Compatibility Behavior

- empty valid frames should count as stream activity, not immediate dead air
- reasoning-only frames should count as semantic activity
- visible content frames remain the only frames that produce user-facing text
- finish reasons such as `stop`, `length`, and `content_filter` should be captured explicitly
- a stream that ends without visible content must be classified separately from a transport timeout

### Why This Matters

This change solves the central false-negative problem:

- the provider may be alive
- the stream may be active
- the local parser currently cannot prove that

After this change, the system can know whether the problem is:

- no connection
- no frames
- no visible content
- filtered content
- truncated completion

## Work Area 2: Timeout Semantics Split

The service layer in `backend/module2/app/assistant/service.py` should replace the current binary timeout model with four distinct timing concepts:

- `connect_timeout`
- `first_frame_timeout`
- `first_visible_content_timeout`
- `stream_idle_timeout`

At minimum, the system must track and log:

- time to first frame
- time to first semantic activity
- time to first visible content
- total stream duration

### Classification Rules

Suggested classification logic:

- if connection cannot be established: `connect_timeout`
- if connection opens but no frame arrives: `first_frame_timeout`
- if frames arrive but no visible content ever appears and finish occurs: `empty_completion` or `filtered_completion`
- if frames and visible content start but then stall: `stream_idle_timeout`

### User-Visible Impact

The frontend still only needs a single graceful answer stream.
But backend classification must stop collapsing all early non-content states into "first token timeout".

## Work Area 3: Real Fallback Decoupling

Fallback should remain in the system, but its design intent must change.

### Required Rules

- same-provider retry should not be treated as a distinct resilience layer
- fallback trigger cause must be tagged clearly
- fallback should choose a materially different path where possible
- if no independent path exists, logs must state that the fallback is same-provider degraded mode

### Short-Term Recommendation

Before adding a second provider, fallback can still be improved by splitting it into:

- `same_provider_non_stream_recovery`
- `conservative_local_answer`

That alone makes diagnosis much clearer.

### Longer-Term Recommendation

Only after the mainline stream is healthy should the system consider:

- second provider
- second model
- queue-based delayed completion recovery

## Work Area 4: Route-Specific Prompt And Token Budgeting

The current extraction stack needs explicit budget rules instead of loosely accumulating evidence.

### Budget Policy

Each assistant route should have its own limits for:

- maximum structural evidence objects
- maximum rows per table
- maximum columns or cells per row slice
- maximum figure evidence items
- maximum trace-hit snippets
- maximum serialized context size
- maximum output tokens

### Immediate High-Priority Routes

Priority order:

1. field extraction and field explanation
2. table lookup and row-grounded follow-up
3. figure and OCR-context explanation
4. knowledge-style answers

### Required Reductions

For overloaded routes, the system should prefer:

- top-k evidence selection
- row slicing rather than whole-table dumping
- figure summary compaction
- trace-hit deduplication
- explicit answer-context serialization caps

### Success Criterion

The goal is not to make prompts small at any cost.
The goal is to keep the best evidence while materially reducing `finish_reason="length"` events and avoiding unnecessary latency inflation.

## Work Area 5: Observability And Diagnostics

This work area is mandatory.
Without it, the rest of the changes cannot be validated.

### Required Telemetry Fields

Per assistant turn or per provider invocation, record at least:

- provider model
- route
- request mode: stream or complete
- estimated context size
- configured max tokens
- time to connect
- time to first frame
- time to first semantic activity
- time to first visible content
- total duration
- finish reason
- provider error class
- fallback trigger cause
- whether fallback path is same-provider or independent

### Required Diagnostic Categories

The system should classify failures into at least:

- transport failure
- connect timeout
- first frame timeout
- empty completion
- filtered completion
- length truncation
- stream idle timeout
- parser compatibility error
- fallback recovery used

## Work Area 6: Evaluation And Acceptance Gates

The current evaluation flow should be expanded so that the team validates normal-path health directly instead of inferring it from user-visible failures only.

### Required Evaluation Families

1. `healthy short factual turn`
2. `reasoning-before-visible-content stream`
3. `empty-content then stop`
4. `content-filtered completion`
5. `normal stream with visible deltas`
6. `large-context extraction turn`
7. `same-provider fallback path`

### Regression Expectations

For each scenario, record:

- expected event sequence
- expected classification
- whether user-visible text should appear
- whether fallback should trigger
- whether the result is considered healthy, degraded, or failed

## Acceptance Criteria

The normal-path stability work should not be considered complete until the following conditions are met.

## A. Provider Compatibility Acceptance

Required:

- active upstream streams that emit valid non-content frames are no longer immediately classified as dead
- reasoning-only frames are recognized as semantic activity
- stream completion without visible text is classified distinctly from connection timeout

Failure examples:

- live stream still logged as `first_token timeout`
- content-filter finish still indistinguishable from transport timeout

## B. Timeout Semantics Acceptance

Required:

- logs and diagnostics separate connect, first frame, first visible content, and idle timeout phases
- timeout labels correspond to the real failing phase

Failure examples:

- every early failure still appears under one generic timeout label

## C. Fallback Decoupling Acceptance

Required:

- fallback cause is visible in diagnostics
- same-provider degraded recovery is not mislabeled as an independent fallback lane
- ordinary healthy turns should not require fallback

Failure examples:

- fallback usage remains common but root-cause logs remain ambiguous

## D. Prompt Budget Acceptance

Required:

- targeted extraction routes show a material reduction in `finish_reason="length"` frequency
- evidence quality remains sufficient for correct extraction

Failure examples:

- prompt overload persists above the current baseline
- aggressive truncation reduction destroys answer groundedness

## E. User-Visible Stability Acceptance

Required:

- the one-answer-box streaming flow becomes materially more stable because the backend now emits visible deltas or classified graceful recovery more reliably
- fewer turns drop into emergency fallback purely because the stream never produced `delta.content`

Failure examples:

- user still frequently sees fallback text even on ordinary turns where the provider was actually active

## F. Observability Acceptance

Required:

- a failed or degraded turn can be diagnosed from logs without reproducing it manually
- the team can tell whether the problem was latency, provider semantics, content filter, truncation, or true no-content completion

Failure examples:

- team still needs ad hoc raw probing for every timeout incident

## Verification Strategy

Verification should happen in four layers.

### 1. Provider Unit Verification

Test the provider parser against mocked SSE sequences that simulate:

- empty content frame
- reasoning-only frame
- visible content frame
- finish without visible text
- content-filter finish
- malformed frame

The goal is to prove that parsing and classification are correct independent of the UI.

### 2. Service Timeout Verification

Test the service streaming wrapper with controlled event timing to verify:

- first frame timeout
- visible-content timeout
- idle timeout
- successful visible streaming
- graceful empty completion classification

### 3. Real Provider Smoke Verification

Run a small real-provider regression against the configured endpoint and record:

- first frame latency
- first visible content latency
- finish reason
- visible answer availability
- fallback rate

This should be small but repeatable, not a one-off manual probe.

### 4. Extraction Load Verification

Run targeted extraction regression on known heavy documents and compare:

- prompt token count
- completion token count
- finish reason
- answer completeness
- latency

## Implementation Boundaries

This design should stay focused on the following files and adjacent helpers:

- `backend/module2/app/assistant/provider.py`
- `backend/module2/app/assistant/service.py`
- `backend/module2/app/assistant/prompting.py`
- `backend/module2/app/assistant/tools.py`
- `backend/module2/tools/assistant_clean_eval.py`
- `backend/module2/tools/assistant_real_media_regression.py`
- `backend/module2/tools/extract_job_regression.py`

If additional helper modules are needed for stream event typing or diagnostics, they should stay local to the Module 2 assistant package and keep interfaces narrow.

## Execution Order

The implementation sequence should be:

1. add provider event typing and compatibility parsing
2. split timeout phases and classification in service layer
3. add structured diagnostics for stream lifecycle and fallback cause
4. reduce prompt budgets on the worst extraction routes
5. rerun targeted regressions
6. only then decide whether a second provider lane is still necessary

## Risks And Mitigations

### Risk 1: Compatibility Work Accidentally Delays Visible Text Too Long

Mitigation:

- keep a separate first-visible-content timer even after accepting reasoning-only frames as semantic progress

### Risk 2: Over-Instrumentation Adds Noise

Mitigation:

- store detailed metrics in logs and debug artifacts
- keep frontend-facing messaging simple

### Risk 3: Prompt Compression Hurts Answer Accuracy

Mitigation:

- evaluate groundedness and extraction correctness together with token reduction

### Risk 4: Same-Provider Recovery Still Hides Root Cause

Mitigation:

- label degraded same-provider recovery explicitly
- do not count it as a mainline success

### Risk 5: Team Jumps To Dual-Provider Too Early

Mitigation:

- make dual-provider work conditional on post-fix evidence that the current path is healthy but still insufficient

## Approval State

Approved by user for direction:

- stop treating this mainly as a fallback-patching problem
- analyze and fix the normal path systematically
- focus first on protocol compatibility, timeout semantics, and context load

Design status:

- written
- ready for spec self-review
- ready for user review after self-review
- implementation planning should begin only after user reviews this written spec
