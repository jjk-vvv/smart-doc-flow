# Module 2 Professional Workbench Polish Design

Date: 2026-03-16

## Summary

This design upgrades the current Module 2 frontend into a more professional, trustworthy, and visually memorable analysis workbench without changing the Module 2 backend contract.

The approved direction is:

`keep the current three-column workbench -> add a module-level top control bar -> preserve the existing upload hero inside the preview stage -> reorganize the right panel into a more coherent analysis console -> add restrained, purposeful motion`

This spec is intentionally narrower than a full product-shell redesign.
It focuses on one specific outcome:

`make Module 2 feel like a premium document analysis workstation while preserving the current frontend/backend interaction model`

This design builds on and refines:

- `docs/superpowers/specs/2026-03-15-module2-deep-read-workbench-redesign-design.md`

The earlier redesign doc established the `Blueprint Theater` direction.
This spec narrows that direction to the user-approved constraints for the current implementation pass:

- keep the three-column workbench
- add a top bar
- preserve the existing preview upload component
- do not break current Module 2 frontend/backend interactions
- allow tasteful motion so the page does not feel static

## Why This Spec Exists

The current Module 2 page is already functionally strong, but it still feels closer to a capable feature page than to a fully designed professional analysis environment.

The current frontend has three specific experience gaps:

- the page lacks a strong module-level control layer, so important workflow state is scattered
- the three columns exist, but their visual hierarchy and responsibilities are not yet crisp enough
- the page has many useful features, but the overall composition still feels flatter and more generic than the underlying capability deserves

At the same time, the current implementation already supports valuable behavior that must not be disrupted:

- extraction job creation and polling
- preview conversion and preview recovery
- summarize and trace APIs
- assistant session restore and streaming chat
- local session persistence
- end-to-end automation selectors and realistic regression flows

This spec therefore optimizes for a high-quality frontend redesign that is structurally ambitious but behaviorally conservative.

## Goals

- Preserve the current three-column workbench as the structural foundation.
- Add a dedicated Module 2 top control bar that makes the page feel like a complete workstation instead of a page with isolated panels.
- Make the page feel more professional, trustworthy, and premium without turning it into a flashy AI demo.
- Improve visual hierarchy so the preview stage reads as the main evidence surface, not just one panel among three.
- Improve coordination between file selection, preview, results, trace, and assistant.
- Reorganize the right side into a more coherent analysis console while still supporting existing result, trace, and assistant behaviors.
- Preserve the current frontend/backend interaction contract for Module 2.
- Preserve the current preview upload hero component and its current interaction model.
- Add restrained, purposeful motion that improves perceived quality and feedback without making the workbench feel noisy.
- Create an implementation path that keeps regression risk low and testability high.

## Non-Goals

- Do not redesign Module 4 or the overall platform shell.
- Do not replace the current parsing pipeline, preview pipeline, or assistant service contracts.
- Do not introduce a new frontend architecture that depends on backend API changes.
- Do not redesign the central upload hero component inside the preview stage.
- Do not change the meaning or sequencing of extraction, summarize, trace, assistant, or preview requests.
- Do not treat motion as a visual gimmick or a branding layer.
- Do not rewrite the entire `DeepReadWorkbench.tsx` file in one uncontrolled pass.

## Hard Constraints

These constraints are approved and must be treated as implementation boundaries.

### 1. Keep The Three-Column Workbench

The page must retain the current structural model:

- left: file/task rail
- center: preview stage
- right: result and assistant area

This is a refinement pass, not a shell replacement.

### 2. Add A Module-Level Top Bar

The redesign must include a top bar specific to Module 2.
This bar is not a second platform navigation bar.
It is a module control layer for identity, status, and high-value actions.

### 3. Preserve The Existing Upload Hero Component

The upload effect component rendered inside the preview stage empty state must not be redesigned in this pass.
Its visual core and interaction behavior stay intact.

This means the redesign may adjust the surrounding preview-stage chrome, but not the upload hero itself.

### 4. Preserve Frontend/Backend Interaction Contracts

The redesign must not require API contract changes for the current Module 2 workflow.

The frontend must preserve compatibility with the existing behavior around:

- `POST /extract/jobs/create`
- `GET /extract/jobs/status/{job_id}`
- `POST /extract/summarize`
- `POST /extract/trace/locate`
- `POST /extract/assistant/session`
- `POST /extract/assistant/chat/stream`
- compatibility handling for `POST /extract/assistant/query`
- `POST /extract/preview/office/start`
- `GET /extract/preview/office/status/{job_id}`

No implementation decision in this redesign may assume a new backend payload or changed endpoint semantics.

### 5. Preserve Critical Frontend Stability Hooks

The redesign should preserve, or preserve compatible equivalents for, the following:

- current workbench session storage
- assistant session restoration behavior
- preview recovery behavior
- key `data-testid` selectors used by existing automation where feasible

This is especially important for:

- file upload
- extraction start
- assistant input and send
- assistant dialog
- results and trace surfaces that are already part of realistic browser checks

### 6. Motion Is Allowed But Must Be Workbench-Appropriate

The page may use more motion than it does today, but the motion must remain:

- fast
- sparse
- status-oriented
- compatible with a professional analysis tool

## Current State Snapshot

The current page already provides these major regions:

- a left file-oriented panel
- a center preview area with upload hero and preview controls
- a right smart unit area with `结果` and `助手` tabs

Important current implementation facts:

- the central preview empty state already has a recognizable upload hero and should be preserved
- the right panel still contains distinct result and trace sections in the `结果` mode
- assistant interactions, streaming, session restore, and trace-related behaviors already exist in the current frontend logic
- the component mixes layout, orchestration, derivation, and rendering concerns in one large file

This means the redesign should improve clarity and presentation while carefully reusing current interaction logic.

## Approved Design Direction

The approved visual and product direction is:

`professional trusted analysis workbench with design character`

The page should feel:

- precise
- competent
- calm
- premium
- visually designed
- not bland

The page should not feel:

- like a generic admin dashboard
- like a flashy AI landing page
- like a static enterprise form

The recommended translation is:

- retain the blue-slate structural language
- increase hierarchy and density discipline
- add one clear top control layer
- make the center preview feel like a document stage
- make the right panel feel like a true analysis console
- use small amounts of cyan and restrained warm focus accents to create memorability

## Target User Experience

### Primary First Impression

When the page opens, the user should immediately understand:

- this is Module 2
- this is a document analysis workstation
- the system has clear workflow state
- the center is where evidence is inspected
- the right side is where extraction and assistant analysis are controlled

### Primary Interaction Flow

The dominant mental flow should be:

`pick file -> inspect preview -> examine extracted content -> verify evidence -> ask or refine through assistant`

The page should visually support that flow without forcing the user to infer it from isolated cards.

## Information Architecture

The page should be reorganized into four major regions:

1. `Module 2 Top Control Bar`
2. `Document Rail`
3. `Preview Stage`
4. `Analysis Console`

The current assistant remains inside the right-side analysis console rather than becoming a separate page.

## Region Design

### 1. Module 2 Top Control Bar

The new top bar is a required part of the redesign.

It should contain three responsibility groups.

#### Module Identity Group

Shows:

- Module 2 label
- Chinese title for the module
- a short description such as document parsing, extraction, trace, and assistant collaboration

Purpose:

- frame the page as a workstation
- reduce the feeling that the user landed in an isolated upload page

#### Task Status Group

Shows compact status pills or strips for:

- current file count
- extraction state
- active document name
- warning or soft-alert state
- last completed action or last updated time

Purpose:

- bring workflow state to one predictable place
- reduce state scattering between left, center, and right regions

#### High-Value Action Group

Shows module-level actions such as:

- upload or add files
- start extraction
- rerun extraction
- export results
- clear workbench
- open rules or configuration

These must be clearly separated from local preview-only controls.

#### Top Bar Visual Rules

- thinner and more refined than a dashboard hero
- strong enough to feel intentional
- not thick enough to steal the page from the preview stage
- separated from the workbench body with a clear bottom edge or boundary
- able to support light status animation without turning into a monitoring dashboard

### 2. Document Rail

The left rail should shift from a generic `folder` feel into a stronger document-workflow rail.

Recommended role:

- queue and file context, not decorative whitespace

It should show:

- selected files in the current workbench
- current active document
- per-file status
- file type and readiness hints
- rule configuration entry

It should visually behave as the lightest of the three workbench columns.
It supports the workflow, but does not compete with the preview stage.

#### Document Rail Rules

- current file gets clear active emphasis
- non-active files remain compact and easy to scan
- status badges are concise, not noisy
- the bottom rule action remains available but feels integrated into the rail

### 3. Preview Stage

The center must become the clear evidence stage of the page.

The redesign should strengthen:

- stage framing
- preview toolbar quality
- page visibility and location awareness
- focus response after a result-triggered jump

The redesign must not replace the existing upload hero component.

#### Preview Stage Rules

- keep the current upload hero untouched
- redesign only the surrounding stage frame and chrome
- maintain current preview controls and preview logic
- make page jumps feel acknowledged through subtle stage feedback

Recommended visual additions:

- stronger architectural frame around the preview viewport
- subtler blueprint or measurement cues around the stage chrome
- clearer page indicator treatment
- better visual feedback after result-driven navigation

### 4. Analysis Console

The right side should evolve from a loosely grouped smart unit panel into a more coherent analysis console.

This console should still preserve the existing major user capabilities:

- view extraction results
- view trace-related context
- use the assistant

The redesign should reorganize these capabilities rather than reinvent them.

#### Primary Modes

The analysis console keeps two major modes:

- `结果`
- `助手`

`结果` is the evidence-analysis mode.
`助手` is the conversational reasoning mode.

#### Results Mode Structure

Recommended stack:

1. `Results Summary Strip`
2. `Category Switcher`
3. `Inline Status Or Trace Banner`
4. `Result List`
5. `Contextual Evidence Expansion`

This structure allows trace context to live closer to the content item that triggered it instead of feeling like a detached subsystem.

The redesign should remain compatible with the current trace API and trace rendering logic.
It should change presentation and organization first, not payload assumptions.

#### Assistant Mode Structure

The assistant remains in the right column, but visually aligns with the same console language.

It should show:

- current document context
- summary state
- assistant dialog
- streaming or processing state
- composer

The assistant should feel like it is working on the current analysis context, not like a generic floating chat widget.

## Right-Panel Compatibility Strategy

The current frontend already contains logic for:

- result search
- trace grouping
- active field and trace synchronization
- assistant session restore
- assistant streaming

The redesign must keep these behaviors available while improving composition.

This means:

- trace data may be visually integrated more tightly with results
- result cards may expose evidence inline
- assistant and results may be better coordinated

But:

- trace lookup behavior must still be supported
- current preview jump behavior must still work
- assistant must still be able to operate against the active document state

## Visual System

### Palette Strategy

Recommended palette roles:

- structural base: current blue and slate family
- secondary navigation energy: cyan
- focus accent: restrained coral or warm neutral accent
- semantic states: existing success, warning, and error tones

The palette should feel deliberate rather than decorative.

### Surface Strategy

The page should use layered surfaces:

- outer atmospheric shell
- top control bar
- workbench base
- preview stage frame
- active console cards

Not every region should use the same glass treatment or same border language.

### Typography Strategy

Typography should emphasize:

- stronger module identity in the top bar
- crisp but compact panel headings
- high legibility for extracted values
- restrained helper text

The interface should feel editorially disciplined, not oversized or toy-like.

### Decorative Language

Allowed:

- faint blueprint grid or measurement hints
- selective glows on active controls
- subtle linework
- precise dividers and micro-badges

Avoid:

- noisy rainbow gradients
- purple-heavy AI styling
- excessive blur everywhere
- overly dramatic neon aesthetics

## Motion Strategy

Motion is explicitly approved in this redesign, but it must behave like a professional workbench.

### Motion Goals

- prevent the UI from feeling stiff
- help users notice state changes
- support visual hierarchy
- confirm navigation and selection

### Allowed Motion Patterns

#### Page Entry

- top bar enters first with a light fade and upward settle
- workbench regions follow with a restrained stagger

#### Top Bar State Feedback

- status pills may pulse or refresh subtly when extraction state changes
- primary action button may use a restrained ready-state emphasis

#### Document Rail

- new file items fade and settle into the queue
- active file transitions smoothly between inactive and active state

#### Preview Stage

- result-driven page jump triggers a brief stage focus response
- page indicator updates feel deliberate, not abrupt

#### Analysis Console

- `结果 / 助手` mode switch uses short fade-and-slide transitions
- category switcher uses a moving active indicator
- selected result cards expand smoothly to reveal contextual evidence

### Motion Non-Goals

Do not add:

- long looping hero animation
- exaggerated bounce effects
- continuous shimmer across large surfaces
- distracting flashing around evidence or page highlights

## Behavioral Compatibility Rules

The redesign must preserve the current behavior model across these flows:

### Extraction Flow

- file selection
- extraction task creation
- status polling
- final document application
- export behavior

### Preview Flow

- PDF rendering
- Office preview conversion
- preview recovery from cached or restored session state
- page jump via current field and trace interactions

### Trace Flow

- trace locate request path
- trace-derived page navigation
- artifact and snippet visibility when available

### Assistant Flow

- session creation or restoration
- assistant streaming chat
- existing fallback or compatibility handling
- current active document scoping

### State Persistence Flow

- restored workbench session
- restored selected files
- restored active document
- restored assistant session binding per file when available

## Freeze Zones

The following parts are intentionally frozen for this implementation pass:

### Upload Hero Freeze Zone

The center upload component itself is not redesigned.
No new interaction model, no new visual core, and no changed upload affordance is allowed in this zone.

### Backend Contract Freeze Zone

No new required request payloads or response shapes may be introduced for the current Module 2 workflows.

### Regression Hook Freeze Zone

Critical `data-testid` and session behavior used by automated checks should be preserved wherever reasonably possible.

## Component And State Boundaries

This redesign should reduce risk by extracting presentation and derivation concerns without changing the backend interaction contract.

Recommended units:

### `Module2TopBar`

Purpose:

- render module identity, status, and top-level actions

Consumes:

- current active file
- workbench processing state
- summary metrics already known to the frontend

Does not own:

- extraction request logic
- preview logic

### `DocumentRail`

Purpose:

- render file queue and file state presentation

Consumes:

- selected files
- active document
- extraction job state

Does not own:

- file parsing logic

### `PreviewStageShell`

Purpose:

- wrap the current preview renderer and upload hero in stronger stage framing

Consumes:

- preview mode
- page state
- jump state

Does not own:

- actual upload hero internals
- PDF or Office renderer implementation

### `AnalysisConsole`

Purpose:

- coordinate right-panel mode switching and shared console framing

Consumes:

- current result state
- assistant state
- selected document context

Does not own:

- backend request logic

### `ResultCatalogModel`

Purpose:

- normalize current result and evidence state for display without changing payload contracts

Consumes:

- current field items
- trace hits
- search state
- active selection

Produces:

- grouped categories
- current visible items
- summary counters
- selected evidence model

## Implementation Plan

This design includes an implementation-plan baseline so that coding can begin only after user review of the written spec.

### Workstream 1: Shell Refactor

Tasks:

- introduce the Module 2 top control bar
- rebalance workbench column hierarchy
- preserve current three-column shell logic

Exit criteria:

- page has a distinct module-level control layer
- page still uses the same underlying workbench structure

### Workstream 2: Left And Center Region Polish

Tasks:

- restyle the document rail
- upgrade preview-stage chrome
- preserve the central upload hero unchanged
- preserve preview controls and current preview behavior

Exit criteria:

- upload hero is unchanged
- preview stage feels more intentional and more central

### Workstream 3: Analysis Console Reorganization

Tasks:

- refine `结果 / 助手` mode shell
- introduce a tighter result-summary and category layer
- visually integrate trace context closer to result items
- preserve current result, trace, and assistant behavior

Exit criteria:

- right side reads as one analysis console
- result and evidence browsing feel more coherent

### Workstream 4: Motion And Polish

Tasks:

- add restrained entry motion
- add file-state transitions
- add preview jump confirmation feedback
- add console mode-switch transitions

Exit criteria:

- the page feels more alive without feeling noisy
- motion does not interfere with current workflows

### Workstream 5: Regression Verification

Tasks:

- verify extraction flow still works
- verify preview and trace still work
- verify assistant session and streaming still work
- verify key automation selectors remain available

Exit criteria:

- no broken Module 2 frontend/backend contract
- no broken upload hero behavior

## Testing Strategy

### Compatibility Checks

- extraction creation and polling still work
- summary requests still work
- trace locate still works
- assistant session restore still works
- assistant streaming still works
- preview conversion and recovery still work

### UI Checks

- top bar does not crowd or destabilize the workbench
- left rail remains readable with multiple files
- preview stage remains the main visual anchor
- right console remains usable in both `结果` and `助手` modes

### Freeze-Zone Checks

- upload hero is unchanged in structure and interaction
- backend payload expectations are unchanged
- key `data-testid` selectors remain compatible

### Motion Checks

- motion is fast and purposeful
- no distracting loops or flashes
- no motion blocks user input during important tasks

### Browser Verification

Use browser verification to confirm:

- top bar hierarchy
- upload hero unchanged
- extraction start path intact
- result selection still drives preview navigation
- assistant still streams in the redesigned shell

## Acceptance Criteria

The redesign is successful only if all of the following are true:

- the page keeps the current three-column workbench foundation
- the page gains a clear Module 2 top control bar
- the center upload hero component remains unchanged
- Module 2 frontend/backend interaction contracts remain intact
- the preview stage is visually more dominant and more intentional
- the right side feels like a cohesive analysis console rather than loosely stacked blocks
- the page feels more professional and premium without becoming flashy
- purposeful motion improves liveliness without harming trust or usability
- existing regression-sensitive flows remain functional

## Risks

- a shell polish effort can still accidentally break critical request sequencing if layout refactor and logic refactor become entangled
- visual integration of results and trace can drift into behavior change if presentation and data derivation are not kept separate
- top-bar additions can make the page feel crowded if status density is not disciplined
- motion can reduce perceived seriousness if it is not aggressively constrained

## Spec Review Notes

Self-review completed for this spec.

Review focus:

- the approved three-column boundary is preserved
- the new top bar is explicitly module-scoped rather than a second global navigation layer
- the upload hero component is protected as a freeze zone
- current Module 2 frontend/backend contracts remain unchanged in the design
- motion remains restrained and workbench-appropriate
- implementation workstreams are scoped to frontend structure, presentation, and safe state organization

Review result:

- approved for user review

## Approval State

Approved by user for current direction:

- keep the three-column workbench
- add a top bar
- preserve the current upload hero component
- preserve Module 2 frontend/backend interaction behavior
- add restrained motion
- optimize toward a professional, trustworthy, and visually memorable analysis workbench

Design status:

- written
- self-reviewed
- ready for user review after commit
