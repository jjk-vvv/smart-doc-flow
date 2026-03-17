# Module 4 Morandi Graph Workbench Redesign

Date: 2026-03-18

## Summary

This design redefines the Module 4 frontend as a graph-first review workbench for documents that have already entered the system through Module 2.

The approved product path is:

`upload in module 2 -> module 2 persists and extracts -> module 4 follows the synchronized file -> module 4 renders the knowledge graph as the primary workspace -> users inspect graph structure, evidence, and alerts in context`

The key approved product decisions are:

- Module 4 does not own file upload
- Module 4 is downstream of Module 2 and should express that clearly in the UI
- the default Module 4 experience must prioritize the graph canvas
- manual selection of other already-synced files must remain available, but only as a secondary action
- the visual direction should use a gentle Morandi blue palette
- the graph canvas background should feel designed and memorable through foggy gradients, precise grid structure, and soft glow, without sacrificing readability

This spec focuses on the Module 4 frontend layout, product hierarchy, visual language, interaction flow, and component boundaries.
It does not change the backend graph APIs or the upstream Module 2 upload contract.

## Why This Spec Exists

The current Module 4 frontend is functionally rich but product-wise mispositioned.

The current page behaves too much like an independent admin console, while the actual business role of Module 4 is:

- a downstream synchronized graph view
- a graph review and evidence inspection workspace
- a specialist analysis stage after Module 2 upload and extraction

As a result, the current UI has four major problems:

- it visually implies that Module 4 is a separate file workspace
- it gives too much space to status, rules, and control surfaces before showing the graph
- it repeats file and graph state across multiple regions
- it does not match the now-approved seamless, professional design language established for Module 2

Without correcting those problems, Module 4 will continue to feel fragmented even if the graph data itself is correct.

## Goals

- Make Module 4 read as a downstream graph review workbench, not a file-entry page.
- Make the graph canvas the first visual and functional priority.
- Preserve all valuable existing Module 4 capabilities while reorganizing them around the graph.
- Keep manual switching between already-synced files, but clearly subordinate it to the default "follow current Module 2 file" path.
- Replace the current warm paper-like visual system with a professional Morandi blue analysis system.
- Introduce a graph background treatment that feels refined and memorable without overwhelming nodes, labels, and edges.
- Reduce repeated states, duplicated actions, and over-segmented card stacks.
- Align Module 4 with the broader product language already approved for Module 2: seamless, immersive, professional, Chinese-first, and trustworthy.
- Keep all user-visible copy Chinese-only in the final UI, with precise and domain-appropriate wording.

## Non-Goals

- Do not add any file upload entry to Module 4.
- Do not move upload ownership away from Module 2.
- Do not remove the ability to inspect historical already-synced files.
- Do not redesign the backend graph generation pipeline in this spec.
- Do not remove graph modes, layout modes, alerts, rule toggles, explain, or simulate capabilities.
- Do not turn Module 4 into a full-screen decorative showcase that hurts graph readability.
- Do not create a visually generic SaaS admin console.

## Approved Product Decisions

The following decisions were explicitly confirmed during brainstorming and are fixed inputs to this design:

- Module 4 should not present itself as an upload workspace.
- Module 4 must reflect the real data chain: Module 2 uploads, Module 4 synchronizes and reviews.
- manual file selection must remain, but it is secondary to automatic following of the current Module 2 file.
- the default visual priority is `graph canvas first`.
- the color system should be a gentle Morandi blue family.
- the graph background should use `foggy gradients + fine grid + soft glow`.
- the interface should feel professional and well-designed, not plain and not flashy.

## Current State Findings

### 1. The page role is visually incorrect

The current interface exposes file source switching, file selection, file state, graph status, projection status, runtime chips, and file cards as if Module 4 were an independent file management workspace.

But the actual product chain is:

- Module 2 owns ingestion
- Module 4 owns graph review

This mismatch causes users to infer the wrong mental model for the module.

### 2. The graph is not the first-class focus

At common desktop widths, the graph is squeezed between:

- a fixed-width left sidebar
- a fixed-width right detail panel
- an unusually tall toolbar region above the graph

The result is that the graph, which should be the core object, is visually subordinate to control surfaces.

### 3. State information is repeated across too many areas

The current page repeats information such as:

- current file
- graph status
- projection status
- runtime health
- node and edge counts

These states appear in the hero region, file panel, toolbar chips, and graph summary bar.
This increases noise without increasing understanding.

### 4. Too many first-screen controls compete equally

The first screen currently contains:

- source switching
- graph mode switching
- layout switching
- fit view
- zoom in/out
- refresh
- file selection
- rule selection and toggles
- node search
- type filters
- alerts

This makes the page look busy and managerial instead of focused and analytical.

### 5. The current visual language does not align with the approved product direction

The current Module 4 palette and layout system lean toward:

- warm paper surfaces
- card stacking
- decorative hero paneling
- many framed status chips

This is inconsistent with the seamless, professional, immersive workbench direction established for Module 2.

### 6. Some components already behave like demoted or legacy regions

The current frontend still contains runtime and job panels that are rendered in the component tree but hidden in CSS.
This is a sign that the page has not yet been truly simplified.

## Product Definition

Module 4 should be defined as:

`the graph review workbench for the current synchronized document, with optional access to other already-synced files`

The default user story is:

1. upload and process a document in Module 2
2. open Module 4
3. immediately see the graph for the current synchronized document
4. inspect graph structure
5. select nodes and follow evidence, alerts, and analysis
6. optionally switch to another already-synced file when needed

The wrong user story is:

1. enter Module 4
2. decide where the file should come from
3. manage file context inside Module 4
4. then maybe inspect the graph

This spec is intended to eliminate that wrong experience.

## Information Architecture

The redesigned page should use three primary regions:

- `Top Workbench Bar`
- `Primary Graph Canvas`
- `Right Context Panel`

Optional secondary surfaces may appear as drawers, overlays, or compact panels, but the core layout should remain graph-centric.

### Top Workbench Bar

Purpose:

- show the current synchronized file context
- express whether the page is following Module 2 or manually viewing another file
- expose only the highest-value global graph controls

This bar should be narrow, dense, and operational.
It must not become another content-heavy header block.

### Primary Graph Canvas

Purpose:

- dominate the page
- carry the graph as the main analytical object
- host lightweight canvas tools such as search, type filtering, and zoom actions

The graph should feel like the workbench itself, not like content placed inside a dashboard card.

### Right Context Panel

Purpose:

- respond to the current node selection
- show node details, evidence, related alerts, and analysis tools
- stay secondary until the user selects something meaningful

This panel should be quiet in the idle state and rich in the focused state.

## Layout Blueprint

### 1. Top Workbench Bar

The top bar should contain the following, in priority order:

- current document name
- current sync mode:
  - follow current document
  - manual review of already-synced file
- graph availability state:
  - ready
  - syncing
  - failed
  - temporary result
- graph mode switch:
  - overview graph
  - evidence graph
- layout switch:
  - force layout
  - hierarchical layout
- fit view
- a unified refresh
- secondary file selection entry for already-synced files

The top bar should not contain:

- a large hero title block
- repeated runtime chips
- repeated node and edge metrics
- repeated file status cards
- long explanatory paragraphs

### 2. Primary Graph Canvas

The graph canvas should:

- occupy the majority of horizontal and vertical space
- remain continuously visible as the main screen object
- keep local controls lightweight and near the canvas
- support the existing graph functions:
  - overview graph
  - evidence graph
  - search
  - type filtering
  - fit view
  - zoom
  - refresh
  - node selection
  - neighborhood expansion

Canvas controls should be clustered as tools around the graph, not presented as large form-like panels.

### 3. Right Context Panel

The right panel should be structured into tabs or sectional zones:

- node overview
- evidence chain
- alert handling
- analysis

These map directly to existing Module 4 capabilities:

- node attributes and related nodes
- node evidence and edge evidence
- alert acknowledge and resolve actions
- explain and simulate actions with rule-scoped context

The right panel should:

- collapse visually in the idle state
- become prominent only after node focus
- not permanently consume large width when empty

## Component Retain / Demote / Remove Matrix

### Retain

The following features remain core:

- graph canvas
- overview and evidence graph modes
- layout mode switching
- fit view
- zoom actions
- graph refresh
- node search
- node type filtering
- node detail
- related nodes
- node evidence
- edge evidence
- related alerts
- alert acknowledge / resolve
- explain
- simulate
- manual selection of already-synced files

### Demote

The following features remain but move to secondary presentation:

- manual file selection
  - from a large primary control block to a compact top-bar entry
- rules control
  - from a large persistent left panel to a drawer, modal, or right-panel analysis tab
- global alerts list
  - from a persistent left-column content block to a collapsible or tabbed secondary region
- type filters
  - from a full sidebar content section to a compact graph tool strip or filter flyout
- search
  - from a standalone left block to a graph tool control

### Remove Or Merge

The following page structures should be removed or merged away:

- large hero panel
- metric card cluster
- diagnostic card cluster
- dedicated current-file status card
- repeated toolbar chip chains for duplicate state
- repeated refresh entry points
- wide empty-state detail panel that permanently reserves space
- component structures that are already hidden in CSS, such as legacy runtime or job panels

## Visual Direction

### Design Intent

The page should feel like:

- a professional graph analysis terminal
- calm and trustworthy
- visually refined
- Chinese-first
- spatially immersive

It should not feel like:

- a paper dashboard
- a generic enterprise SaaS admin
- a loud neon tech demo
- a flat utility page

### Color System

The primary color family should be Morandi blue.

Recommended layers:

- `Base Surface`
  - soft fog blue
  - pale slate blue
  - low-contrast blue-gray
- `Structural Tone`
  - muted steel blue
  - gray-blue dividers
  - soft desaturated ink-blue text hierarchy
- `Interactive Accent`
  - a slightly brighter but still restrained lake blue
- `Soft Highlight`
  - near-silver or very pale blue light for canvas glow and selected halo
- `Risk Tones`
  - muted yellow, amber, and red with reduced saturation so they harmonize with the main palette

### Typography

Use the same Chinese Google font family already approved elsewhere in the product.

Typography principles:

- titles are compact and confident
- status language is short and exact
- graph labels prioritize readability
- evidence text favors clarity over decoration
- empty-state text explains what happened and what to do next
- final UI copy must be Chinese-only, concise, and specific to graph review tasks

### Panel Treatment

Panel language should move away from stacked floating cards.

The new principles are:

- fewer hard panel edges
- clearer role separation
- more continuity between workbench zones
- thinner and more precise dividers
- background and density differences instead of heavy card nesting

## Graph Canvas Background Design

The graph canvas should be the one place where the page feels noticeably special.
The background treatment must remain subordinate to graph readability.

### Background Composition

The canvas background should use four layers:

1. `Fog Gradient Base`
   - a calm Morandi blue atmospheric gradient
   - slightly deeper in one corner, lighter in another

2. `Precision Grid`
   - a very fine technical grid
   - low-contrast and dense enough to imply structure
   - never strong enough to compete with links

3. `Soft Local Glow`
   - 1-2 restrained glow regions
   - ideally aligned with graph center-of-mass or a compositional corner

4. `Depth Texture`
   - very subtle layered haze or blurred geometry
   - adds richness in empty areas

### Rules For Background Restraint

- no strong radial neon
- no saturated blue
- no obvious animated particles behind labels
- no visual effect that lowers node-label contrast
- no decorative illustration unrelated to graph semantics

### Why This Works

This treatment gives the graph area a memorable presence without breaking its analytical purpose.
It creates a feeling of a live, high-value analysis surface rather than a blank white utility canvas.

## Node And Edge Visual Hierarchy

### Nodes

Nodes should remain clean and data-first.

Recommended behavior:

- default nodes are restrained and legible
- selected nodes gain a soft halo and stronger outline
- pinned or actively focused nodes receive a secondary emphasis state
- node categories use a coherent muted palette rather than unrelated bright colors

### Edges

Edges should become more visually disciplined.

Recommended behavior:

- default edges remain light and secondary
- focused neighborhoods gain stronger edge contrast
- evidence paths and alert-relevant relations can gain emphasis when relevant

### Labels

Labels should be more intentional than decorative.

Recommended behavior:

- default labels favor major semantic nodes
- focused state reveals local detail labels
- labels should remain readable against the designed canvas background

## Functional Mapping To Current Module 4 Features

This redesign explicitly preserves the current working capabilities.

### Graph Mode

Current:

- overview graph
- evidence graph

New placement:

- top workbench bar as a primary global toggle

### Layout Mode

Current:

- force layout
- hierarchical layout

New placement:

- top workbench bar as a primary global toggle

### File Context

Current:

- follow current file
- manual file selection

New behavior:

- default follows Module 2 current document
- manual selection stays available as a compact secondary control
- the UI must clearly express when the user is viewing a different already-synced file

### Rules

Current:

- visible rule list
- per-rule enable/disable
- selected rule context for explain and simulate

New placement:

- not a persistent large sidebar block
- exposed through a secondary surface or analysis tab

### Alerts

Current:

- global alert list
- acknowledge
- resolve

New placement:

- node-relevant alerts inside the right context panel
- optional secondary global alert drawer for cross-node review

### Explain And Simulate

Current:

- explain result
- simulate result
- selected rule context

New placement:

- right-panel analysis section
- contextual to the currently focused node or alert

## State Design

### State 1: No active Module 2 file

The canvas should show a direct, clear empty state:

- no graph yet
- guidance that the user should upload and process a document in Module 2 first

This state should not encourage file import inside Module 4.

### State 2: File exists, graph still synchronizing

The page should:

- keep the current document visible in the top bar
- show a clear syncing state
- allow the user to understand that Module 4 is waiting for downstream graph readiness

### State 3: Graph ready

The page should:

- render the graph immediately
- reduce nonessential explanatory chrome
- let the user start graph inspection with minimal ceremony

### State 4: Temporary fallback graph

The page should:

- clearly explain that the current result is temporary
- avoid overstating readiness
- keep the warning concise and non-alarmist

### State 5: Manual historical file view

The page should:

- clearly indicate that the user is viewing another already-synced file
- provide a one-step return to the follow-current-document mode

### State 6: Sync failure

The page should:

- explain that the selected file did not complete graph synchronization
- keep the current document context visible
- offer a clear next step instead of scattering failure information across multiple chips and cards

## Interaction Model

### Default Page Entry

On entering Module 4:

- read the current active Module 2 file
- if a synchronized graph is available, render it directly
- if not, present the correct status state without suggesting upload inside Module 4

### Manual File Switch

When the user manually selects another file:

- switch context to that already-synced file
- update graph, status, and right-panel context
- mark the page as being in manual view

### Return To Follow Mode

Users must be able to return to the follow-current-document mode in one explicit action.

### Node Selection

Selecting a node should:

- focus the right context panel
- show relevant evidence
- show node-relevant alerts
- preserve graph continuity

### Canvas Tools

Canvas tools should:

- feel local to graph analysis
- remain compact
- not duplicate global controls

## Accessibility And Motion

### Accessibility

- primary toggles must have visible focus states
- selected and inactive states must not rely only on color
- top-bar and panel controls must remain keyboard reachable
- empty states must clearly communicate next steps in Chinese

### Motion

Motion should be subtle and instrumental:

- graph fade-in on load
- soft transitions between modes
- selected node emphasis
- right-panel reveal transitions
- light breathing or shimmer for sync-in-progress states

Motion should not:

- bounce aggressively
- flash brightly
- create decorative movement unrelated to task flow

## Technical Boundaries

This redesign should preserve current frontend-backend interaction behavior.

The spec assumes:

- no change to Module 4 ownership of graph APIs
- no change to Module 2 upload ownership
- no new upload flow inside Module 4
- no disruption to existing explain, simulate, alert, or graph mode capabilities

The redesign should mostly be achieved through:

- layout restructuring
- component re-hierarchy
- visual-system replacement
- state presentation cleanup
- selective demotion of controls

## Risks

### Risk 1: Over-collapsing useful controls

If too many tools are hidden at once, the page may feel cleaner but slower for power users.

Mitigation:

- keep core graph controls visible
- demote secondary controls, do not remove them blindly

### Risk 2: Background design hurting readability

If the graph background becomes too decorative, labels and links will suffer.

Mitigation:

- keep effects low-contrast
- validate with dense and sparse graph samples
- prioritize node-label legibility over visual spectacle

### Risk 3: Manual file view becoming confusing

If the page does not clearly distinguish follow mode from manual mode, users may misread the current graph context.

Mitigation:

- make the current mode explicit in the top bar
- provide a one-click return to follow mode

### Risk 4: Feature sprawl returning through side panels

If rules, alerts, and analysis are simply moved without rethinking hierarchy, the page may still feel overloaded.

Mitigation:

- define strict primary, secondary, and contextual zones
- do not allow secondary content to reclaim first-screen dominance

## Testing Strategy

### Product Flow Tests

- entering Module 4 with an active Module 2 file defaults to the synchronized current file
- entering Module 4 without an active Module 2 file shows the correct empty guidance
- manual file switching changes graph context without implying upload ownership
- returning to follow mode restores the current Module 2 file

### Layout And Visual Tests

- the graph canvas occupies the majority of first-screen space on desktop
- the right panel does not permanently waste space in the idle state
- top bar height remains compact
- repeated state chips and duplicate status blocks are removed

### Functional Regression Tests

- graph modes still switch correctly
- layout modes still switch correctly
- fit view still works
- refresh still works
- search still filters correctly
- node type filtering still works
- node selection still loads detail correctly
- alerts can still be acknowledged and resolved
- explain and simulate still run under the same conditions

### Visual QA Tests

- Morandi blue palette stays consistent across light and dark themes
- graph background remains readable for dense and sparse graphs
- focused node halo is noticeable but restrained
- alert colors remain legible without dominating the palette

## Acceptance Criteria

This redesign is successful only when all of the following are true:

- Module 4 no longer looks like an independent file-entry workspace.
- The default Module 4 path clearly follows the current Module 2 document.
- Manual selection of other already-synced files remains available but is visually secondary.
- The graph canvas is the primary first-screen object.
- Large hero content, repeated status blocks, and redundant control surfaces are removed or demoted.
- Rules, alerts, evidence, explain, and simulate remain available without dominating the page.
- The visual system uses a gentle Morandi blue palette rather than the previous warm paper-like palette.
- The graph background feels intentionally designed through fog gradient, precision grid, and soft glow.
- The redesigned page feels more consistent with the approved Module 2 workbench direction.
- The redesign does not break existing Module 4 frontend-backend interactions.

## Final Recommendation

The correct next move for Module 4 is not a cosmetic polish pass on the current layout.
It is a role correction plus layout correction:

- redefine the page as a downstream synchronized graph review workbench
- make the graph canvas the center of the experience
- demote file switching, rules, alerts, and duplicated status display
- rebuild the visual language around Morandi blue analytical calm
- use the graph background as the distinctive design highlight

This is the most reliable way to make Module 4 feel coherent with the rest of the product while preserving the real functional value that already exists in the current graph workbench.
