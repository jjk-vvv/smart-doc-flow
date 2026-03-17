# Module 2 Result Panel Hierarchy And Tab Design

Date: 2026-03-17

## Summary

This design refines the right-side analysis area of Module 2 into a more layered, better aligned, and more disciplined panel without changing any Module 2 frontend/backend interaction contract.

The approved direction is:

`browser-tab style view switch -> layered result panel -> clearer section headers -> stronger alignment discipline`

This spec is intentionally narrow.
It does not reopen the full-page workbench redesign.
It focuses on one specific user-facing problem:

`the right-side result panel still feels visually uneven, and the current tab switcher and trace section do not yet read like a polished professional analysis surface`

## Why This Spec Exists

The recent seamless workbench pass improved the overall shell and the tab interaction quality, but the latest review surfaced a more specific visual issue inside the right panel:

- the `结果与助手` header still mixes title, subtitle, icon, and switching controls at the same visual level
- the current view switch is improved, but it still reads more like a segmented control than an embedded workstation tab strip
- the `抽取结果` and `原文定位` areas are separated by lines, but they do not yet feel like fully formed sections
- the `原文定位` title row is not visually balanced, especially in empty states where the title, count, and empty helper copy drift apart

The result is a panel that is functional but not yet compositionally trustworthy.

This spec therefore narrows the work from "general polish" to a more exact outcome:

`turn the right-side result area into a layered analysis panel whose tab switch reads like a browser tab, and whose internal sections are aligned like a professional workstation`

## Relationship To Earlier Specs

This design builds on and further constrains:

- `docs/superpowers/specs/2026-03-16-module2-professional-workbench-polish-design.md`
- `docs/superpowers/specs/2026-03-17-module2-seamless-resizable-workbench-design.md`

Those specs remain active for the overall page direction.

This new spec takes precedence only for the right-side panel in these areas:

- top-right tab switch styling
- right panel internal hierarchy
- section header structure
- `原文定位` alignment and empty-state presentation

## Goals

- Preserve the current right-side two-view model:
  - `提取结果`
  - `智能助手`
- Make the tab switch feel like an embedded browser-style tab rather than a floating segmented button group.
- Make the `结果与助手` area feel layered and sectional instead of flat and line-split.
- Give `抽取结果` and `原文定位` their own stable section identity and visual rhythm.
- Correct alignment issues inside the trace section, especially around:
  - title row baseline
  - right-aligned count
  - sync badge placement
  - empty-state text placement
- Keep current result, trace, and assistant interaction logic unchanged.
- Preserve current selectors, data flow, and existing workbench state behavior wherever possible.

## Non-Goals

- Do not redesign the left pane or center preview pane in this pass.
- Do not change backend endpoints, payloads, or polling behavior.
- Do not redesign the upload hero in the preview empty state.
- Do not convert the right panel into independent floating cards.
- Do not introduce decorative English labels or new duplicated controls.
- Do not rewrite the entire right panel logic into a new data architecture.

## Hard Constraints

### 1. No Frontend/Backend Contract Changes

This visual redesign must remain compatible with the current Module 2 behavior around:

- extraction job creation and polling
- result rendering
- trace locate calls
- assistant session restore
- assistant streaming chat
- preview restore and workbench session persistence

### 2. No Functional Regression In Existing Result And Trace Behavior

The redesign must preserve:

- active field selection
- trace highlight and trace jump behavior
- current document state rendering
- result search and copy behaviors
- assistant input and send behavior
- current empty-state logic for no document, no fields, and no trace hits

### 3. Chinese-First Product Copy Must Stay Precise

The redesigned panel must keep user-facing Chinese concise and accurate.

Avoid:

- internal naming
- repeated wording
- decorative English
- vague or ornamental labels

### 4. The Panel Must Stay Seamless With The Workbench

The right panel may gain more internal layering, but it must still feel docked into the seamless workbench shell.

This means:

- no floating card stack
- no oversized card shadows
- no detached tab pill floating above the content

## Current Problems To Solve

### 1. Header Hierarchy Is Flat

The right panel header currently places:

- icon
- title
- subtitle
- tab switch

in one compressed row without enough structural separation.

This weakens the primary reading order.

### 2. The Tab Switch Still Reads As A Control, Not A View Surface

Even after the recent refinement, the switch still behaves visually like a compact control cluster.

The user-approved target is closer to:

- browser tab
- docked workbench tab
- selected view cap that visually connects to the content area

### 3. `抽取结果` And `原文定位` Do Not Yet Read As Complete Sections

The current implementation uses dividers, but the internal composition still feels like one long column split by lines.

That creates weak section identity.

### 4. `原文定位` Is Not Properly Balanced

The most visible alignment issue is inside the `原文定位` area:

- the title row does not establish a strong baseline between icon, title, sync status, and count
- the count can feel detached from the title
- the empty helper text sits too close to the divider and does not feel anchored to the section body

This makes the section feel accidental rather than designed.

## Approved Direction

The approved direction is:

`browser-tab style switch + layered analysis panel + sectional headers + aligned trace section`

The panel should feel:

- integrated
- structured
- calm
- premium
- legible
- trustworthy

The panel should not feel:

- like a loose stack of UI strips
- like a card dashboard
- like a mobile segmented control dropped into a desktop workbench

## Right Panel Information Architecture

The right-side area should be organized into three clear levels.

### Level 1: Panel Frame Header

This is the outer identity layer of the right panel.

It contains:

- panel icon
- panel title: `结果与助手`
- one short supporting line
- tab switch on the right

Rules:

- the title block and tab block must feel like two separate responsibilities
- the title block establishes panel identity
- the tab block establishes current view
- they should not compete for equal visual weight

### Level 2: Active View Cap

The active tab visually becomes the "cap" of the current content view.

This is the key behavioral difference from a segmented control.

Rules:

- selected tab shares the same surface language as the content below
- selected tab appears visually attached to the content area
- inactive tab remains lighter and quieter

### Level 3: Internal Sections

Inside `提取结果`, the content is split into distinct sections:

1. `抽取结果`
2. `原文定位`
3. result list body

Each section needs:

- a stable header row
- its own spacing rhythm
- a content body that begins after deliberate inset spacing

## Browser-Tab Style Switch Design

### Visual Model

The switch should resemble a desktop browser tab or docked workbench tab.

Selected tab:

- shaped like an embedded tab, not a pill
- slightly raised through surface contrast, not through dramatic shadow
- visually connected to the content plane below
- top corners rounded, bottom edge visually merged into the content section

Inactive tab:

- lighter text
- minimal or transparent surface
- hover feedback through subtle tint, not aggressive movement

### Structural Rules

- The tab rail sits inside the right panel header, aligned to the top-level title block.
- The active tab width is content-driven but disciplined by a minimum width.
- Tabs must not feel compressed or toy-like.
- The active tab and content surface must share border and background logic.

### Motion Rules

The switch animation should feel precise and system-like.

Recommended motion:

- selected tab relocation: `180ms-220ms`
- text color transition: `120ms-160ms`
- view content transition: `220ms-260ms`

Animation character:

- no bounce
- no playful goo effect
- no exaggerated scale pop
- use controlled lateral or fade transitions only

## `提取结果` View Structure

The `提取结果` view should be divided into two fixed sectional headers followed by the result content body.

### Section A: `抽取结果`

Purpose:

- declare the result-focused region
- show field count or filtered count
- optionally show active document context and compact summary metrics

Rules:

- section header row should have left icon + title and right count badge
- count badge should align to the same baseline as the title row, not drift vertically
- supporting document metadata sits below as a subordinate strip only when relevant

### Section B: `原文定位`

Purpose:

- declare trace navigation as its own secondary but still important section
- group trace count, sync state, and trace-type chips in one disciplined structure

Rules:

- `原文定位` must become a true section header, not just a text label above a list
- the header row uses:
  - left: icon + title
  - right: optional sync badge + count badge
- all items in the header row share a common vertical center
- the count badge must stay visually close to the title row, not flush against the panel edge
- the helper copy or empty state must begin inside the section body with clear top padding

## Alignment Rules For `原文定位`

This is the most important detailed rule set in the spec.

### Header Alignment

- icon and title text share one centerline
- title and right-side badges are aligned by optical center, not arbitrary line-height
- right-side badge group is right-aligned as a compact inline cluster
- badge spacing must be tighter than section-to-body spacing

### Body Start

- the section body starts after a clear vertical gap below the header row
- empty-state text must not sit directly on the divider
- the first text line of the empty state aligns with the content inset of trace cards

### Empty State Presentation

When there are no trace hits:

- show the empty helper inside the body area, not as a loose label
- use subdued text color
- keep one concise line by default
- if a second line is needed, it should be smaller and secondary

### Count And Sync Placement

- the sync badge should appear before the count badge when both are present
- the count badge should use compact width and never float against the far edge alone
- if only count exists, it should still remain grouped with the title row through spacing balance

## Visual Hierarchy And Spacing Rules

### Outer Header

- right panel outer header: compact but clearly separate from content
- title block spacing should be slightly larger than internal section spacing

### Internal Section Rhythm

Recommended hierarchy:

- panel header
- active tab cap
- section header
- section body

Recommended spacing pattern:

- panel header to active content: tight
- section header to section body: medium
- section to section: medium-strong
- body item to body item: compact and consistent

### Surface Treatment

- use surface contrast to show hierarchy, not heavy card chrome
- section headers may use a faint tinted strip or subtle inset background
- avoid large shadows
- use border, tonal contrast, and disciplined padding instead

## `智能助手` View Relationship

The assistant view does not need a full redesign in this pass, but it must inherit the same tab-cap logic and panel framing.

Rules:

- assistant tab should use the same browser-tab style switch
- assistant view should enter as the sibling of `提取结果`, not as a differently styled panel
- assistant header spacing should feel compatible with the result view, even if the body content model differs

## Data Flow And Behavior Preservation

The redesign changes presentation, not behavior.

The following state model remains unchanged:

- `smartUnitTab` still controls active view
- result, trace, and assistant derived data continue using current sources
- active field and active trace linkage remain unchanged
- result search remains unchanged
- assistant input, send, and streaming behavior remain unchanged

The preferred implementation approach is:

- preserve current state variables
- preserve current request calls
- preserve current test selectors where practical
- reshape only the rendering shell and motion strategy

## Error Handling And Edge Cases

The new structure must still render correctly for:

- no document selected
- document selected but no extracted fields
- extracted fields present but no trace hits
- trace hits present and syncing
- assistant available but no prior messages
- error and warning banners appearing above result content

The visual structure must not collapse when any one section is empty.

That means:

- section headers remain stable even when bodies are empty
- count badges degrade gracefully to zero
- helper text does not shift the panel into a visually broken state

## Testing And Validation

Implementation should be validated with:

### Layout Checks

- right panel header remains aligned at normal desktop widths
- selected tab visually attaches to active content area
- `原文定位` header row keeps stable alignment in empty and populated states

### Interaction Checks

- switching between `提取结果` and `智能助手` preserves current behavior
- trace list click-to-jump still works
- result field click-to-jump still works
- assistant input and send still work

### Regression Checks

- no backend request sequence changes
- no workbench session restore regressions
- no visual overlap in narrow but supported workbench widths

## Implementation Notes

Preferred implementation scope:

- continue editing `frontend/components/DeepReadWorkbench.tsx`
- avoid broad refactors unrelated to the right panel
- extract small rendering helpers only if they improve clarity without destabilizing current behavior

Implementation should proceed in three small passes:

1. reshape tab switch into browser-tab structure
2. rebuild result view into layered sections with corrected alignment
3. validate empty states, populated states, and current interactions

## Out Of Scope For This Pass

These ideas are explicitly deferred:

- multi-row assistant utility tabs
- dockable or detachable side panes
- cross-panel breadcrumb navigation
- global redesign of all inner badges across the application
- backend changes to expose new trace metadata solely for presentation
