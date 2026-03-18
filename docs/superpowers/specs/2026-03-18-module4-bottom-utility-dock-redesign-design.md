# Module 4 Bottom Utility Dock Redesign

Date: 2026-03-18

## Summary

This spec defines a focused redesign for the bottom utility region in Module 4.

The approved direction is to convert the current always-visible utility block into a graph-first bottom dock that:

- is collapsed by default
- leaves only a slim control strip visible in the default state
- expands upward to a fixed height when activated
- keeps the two functional regions visible in parallel after expansion
- rebalances the inner proportions so the left and right regions feel symmetrical
- preserves all existing Module 4 interactions and backend contracts

This is a refinement spec for the already approved Morandi blue graph workbench direction.
It does not replace the broader Module 4 layout strategy. It improves one specific region that is currently too visually heavy and too space-consuming relative to the graph canvas.

## Why This Spec Exists

The current bottom utility region is functionally useful but visually overcommitted.

It reduces the graph canvas area even when the user does not need search, type filtering, or alert review.
It also creates a composition problem:

- the graph canvas, which should remain the primary analytical object, loses too much vertical space
- the utility region reads like a permanently open secondary workspace rather than an on-demand assistive surface
- the two inner panels do not feel balanced enough in size, rhythm, or density
- the current block introduces unnecessary visual weight near the bottom of the page

Because Module 4 has already been explicitly defined as graph-first, this region must behave like a secondary dock rather than a fixed, dominant panel.

## Goals

- Give more visible area back to the graph canvas in the default state.
- Make the bottom region feel symmetrical, tidy, and intentional.
- Preserve parallel visibility of `search and filtering` on the left and `pending alerts` on the right.
- Use a professional, IDE-style dock interaction instead of a large exposed utility slab.
- Keep the visual language aligned with the approved light Morandi blue theme.
- Preserve all current frontend-backend interactions and existing user workflows.
- Improve the perceived hierarchy of the page: graph first, utilities second.

## Non-Goals

- Do not remove node search.
- Do not remove node-type filtering.
- Do not remove alert preview, acknowledgment, or resolution actions.
- Do not move these utilities into a new right-side permanent panel.
- Do not add drag-resize behavior in this iteration.
- Do not change graph rendering logic, data fetching, alert APIs, or selection logic.
- Do not introduce extra status blocks, duplicated toolbars, or decorative surfaces that compete with the graph.

## Approved Decisions

The following decisions were explicitly confirmed during brainstorming and are fixed inputs:

- the bottom utility region should be `collapsed by default`
- the collapsed state should leave only a `slim control strip`
- expanding should use `upward slide into a fixed height`
- the expanded state should keep `left and right panels visible in parallel`
- the redesign should make the area look `more symmetrical`
- the graph canvas should gain more usable space and stronger visual priority

## Current State Findings

### 1. The dock is visually open when it should be latent

The utility area is always rendered as a full block, which means it occupies meaningful vertical space even when the user is not actively searching or reviewing alerts.

This is inconsistent with the graph-first product hierarchy.

### 2. The internal proportions are slightly unbalanced

The current layout uses an intentionally uneven grid that favors the left side.
That difference is not large enough to feel purposeful, but it is large enough to feel slightly off-center.

The result is a layout that reads as asymmetrical without gaining a clear functional advantage.

### 3. The left and right regions do not share the same visual rhythm

The left side contains a search shell and type chips with wrapping behavior.
The right side contains stacked alert cards with their own card rhythm.
Because their spacing systems are not normalized tightly enough, the whole region feels less coordinated than the rest of the page.

### 4. The region currently steals attention from the graph

The graph should dominate first glance.
Instead, the exposed bottom block pulls a surprising amount of attention due to its height, its strong framing, and the density of its inner content.

## Product Definition

This region should be understood as:

`a bottom utility dock that supports graph review without competing with the graph canvas`

Its job is not to be a second workspace.
Its job is to stay quiet until the user needs it, and then provide fast access to filtering and alert handling in a controlled, compact form.

## Interaction Model

The dock should support exactly two user-visible states.

### 1. Collapsed State

This is the default state on page load.

Behavior:

- only a slim control strip is visible
- the strip stays attached to the bottom edge of the graph work area
- the strip shows concise summary information:
  - dock title
  - current node count
  - current open alert count
  - expand icon
- the strip behaves like a button and can be activated by click or keyboard

Visual intent:

- understated
- integrated with the page
- clearly interactive
- not visually louder than the graph toolbar

### 2. Expanded State

When the strip is activated, the dock slides upward and reveals the full bottom utility area.

Behavior:

- expansion uses a fixed height on desktop
- the content reveals as a single unified dock, not as separate floating cards
- the left and right panes appear simultaneously
- the same strip remains as the dock header and now exposes the collapse action
- the user can collapse the dock by clicking the toggle again

Animation:

- upward transform plus opacity fade
- short and smooth
- no bounce, no spring exaggeration, no theatrical scaling

## Layout Blueprint

### Overall Structure

The bottom region should be refactored into:

1. `Dock Shell`
2. `Dock Control Strip`
3. `Dock Body`
4. `Left Utility Pane`
5. `Right Utility Pane`

The dock body should only occupy full height in the expanded state.
In the collapsed state, the shell should visually compress to the height of the control strip.

### Expanded Height

The expanded desktop dock should use a fixed height in the approximate range of `200px - 220px`.

That range is large enough to:

- keep the two-column layout readable
- show a meaningful portion of the alert list
- preserve a much larger graph canvas than the current design

### Pane Proportions

The current slightly skewed layout should be replaced by a nearly symmetrical split.

Approved target:

- desktop: `1fr / 1fr`

An extremely small asymmetry such as `1.02fr / 0.98fr` is acceptable if needed for final optical balance, but the visual read should be effectively symmetrical.

### Responsive Behavior

On narrower widths, the dock can continue to stack vertically inside the expanded state, but it should still preserve the same top-level interaction model:

- collapsed by default
- slim trigger strip
- fixed-height expanded presentation

The responsive version should not create a second interaction pattern.

## Visual Design

### Hierarchy

The graph canvas remains the hero surface.
The dock should feel like a supporting layer that can surface quickly and retreat cleanly.

### Surface Treatment

The dock should continue using the approved light Morandi blue system, but with lighter structural weight than the current region.

Preferred treatment:

- soft blue-tinted base
- restrained top divider against the graph area
- subtle inner highlight
- modest shadow only when expanded

It should not read as a heavy card or a gray footer slab.

### Control Strip

The collapsed strip should feel precise and refined.

Recommended composition:

- left: dock title in concise Chinese
- center or adjacent: small count chips for node count and alert count
- right: expand/collapse affordance

The strip should not contain duplicated operational buttons.

### Inner Panel Symmetry

The left and right panes should align on:

- top baseline
- title position
- description spacing
- section padding
- content start line

The center divider should be light and architectural, not bold.

### Content Density

Left pane adjustments:

- search shell remains full width
- type chips keep their current function but use tighter, more even row rhythm
- chip area should feel organized rather than scattered

Right pane adjustments:

- alert cards should be slightly more compact
- top summary row should align visually with the left pane title block
- list height should feel deliberate, not like a leftover scroll box

## Copy Direction

All visible UI copy in this redesigned region must remain Chinese-only and concise.

The dock should use precise labels appropriate to an analysis workbench.
Avoid:

- duplicated wording
- generic dashboard terminology
- leftover English
- overlong helper paragraphs

The collapsed strip title should be short and clear, for example a concise label in the direction of `search and alerts`, while the final UI copy itself remains Chinese.

## Technical Boundaries

This redesign must not affect existing data or action flows.

### Existing Logic That Must Stay Intact

- query filtering via the existing `filters.query` state
- node-type filtering via the existing `filters.nodeTypes` state
- alert preview rendering
- alert opening via `openNodeFromAlert`
- alert acknowledgment via `handleAckAlert`
- alert resolution via `handleResolveAlert`
- existing graph counts and alert counts
- existing node selection and inspector behavior

### New UI State

This redesign should introduce only a small local UI state for the dock itself, such as:

- `isUtilityDockOpen`

No new network state, persistence contract, or backend payload is required.

Collapsing or expanding the dock must not reset:

- the current search query
- the current active type filters
- the current alert list contents

## Component Boundaries

The implementation should keep the changes contained to the existing Module 4 frontend region.

### Primary Files

- `frontend/components/knowledge-nexus/KnowledgeNexusNeo4j.tsx`
- `frontend/global.css`

### JSX Responsibilities

In `KnowledgeNexusNeo4j.tsx`:

- add local open/closed dock state
- restructure the current utility header into a reusable control strip
- wrap the current utility content in an expandable dock body
- keep existing filter and alert child controls intact
- preserve current `data-testid` values where they already exist

### CSS Responsibilities

In `global.css`:

- refactor the dock shell so collapsed and expanded states are visually distinct
- create the slim control strip styling
- implement the upward reveal transition
- rebalance the grid to near-symmetry
- normalize inner panel spacing and alignment
- reduce the visual heaviness of the dock when compared with the graph canvas

## Accessibility and Usability

The dock toggle must be operable as a real button with proper state exposure.

Requirements:

- keyboard accessible
- clear focus treatment
- `aria-expanded` on the toggle control
- collapsed state still exposes summary information clearly
- transition should not hide state changes from assistive interpretation

## Error Handling and Edge Cases

The redesign must preserve sensible behavior in the following cases:

- no active alerts
- no active filters
- extremely long type-chip collections
- narrow desktop widths where the panes stack
- rapid repeated open/close interactions

The dock should remain visually stable when:

- alert counts change after user actions
- filter results reduce node counts significantly
- the alert list becomes empty after resolve actions

## Acceptance Criteria

The redesign is complete when all of the following are true:

- the bottom utility region is collapsed by default on initial render
- the collapsed state leaves only a slim visible control strip
- clicking the strip expands the dock upward to a fixed height
- clicking again collapses the dock cleanly
- the expanded dock keeps the left and right panes visible together
- the two panes feel visually balanced and nearly symmetrical
- the graph canvas has visibly more space in the default state than before
- search, type filtering, alert open, acknowledge, and resolve behaviors still work
- no backend API behavior changes are required
- the dock styling remains aligned with the approved Morandi blue light theme

## Testing Strategy

Implementation validation should include:

- visual verification at standard desktop width
- visual verification at narrower responsive widths
- regression check for search and type filtering behavior
- regression check for alert open, acknowledge, and resolve actions
- keyboard toggle verification for the dock strip
- build verification for the frontend bundle

If browser validation is performed, the review should specifically check that:

- the graph canvas reads as the first priority when the page opens
- the collapsed strip does not feel visually heavy
- the expanded state feels smooth and architectural rather than card-like

## Implementation Notes for the Next Step

This spec is intentionally limited to a single, focused UI redesign.

It should be implemented as an incremental change inside the existing Module 4 workbench rather than as a broader layout rewrite.
That keeps scope tight, preserves the already approved graph-first architecture, and minimizes the risk of unintended interaction regressions.
