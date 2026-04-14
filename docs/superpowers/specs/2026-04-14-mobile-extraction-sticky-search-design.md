# 2026-04-14 Mobile Extraction Sticky Search Design

## Background

The mobile extraction experience lives in `frontend-app/pages/deepread/MobileDeepReadPage.tsx` and is rendered through the protected `deepread_extraction` tab inside `frontend-app/App.tsx`.

The current mobile page already has the core workbench structure in place:

- a hero header with the title `AI文档处理`
- a prominent search input for parsed records
- upload shortcuts
- parsed document list
- preview and artifact panels
- bottom mobile navigation

Functionally the page works, but the top search area still behaves like a static hero block. Once the user scrolls deeper into the page, the search capability is no longer visually anchored, and content moving upward can feel crowded against the top area. The requested improvement is to make the search experience feel continuous during scrolling: the hero search should gradually become a sticky top search bar instead of abruptly disappearing.

## Goals

1. Create a mobile-native scroll transition where the hero search visually transforms into a sticky top search bar.
2. Add clear layer separation so scrolling content does not visually collide with the pinned search area.
3. Preserve the current page visual language instead of redesigning the whole extraction page.
4. Keep the interaction safe for the existing search/filter logic and the rest of the extraction workflow.
5. Validate the behavior on the live authenticated mobile frontend using the real mobile page.

## Non-Goals

- redesigning the desktop deep read workbench
- changing extraction backend behavior
- changing parsed document filtering semantics
- rewriting the mobile page information architecture
- introducing a permanently fixed top app bar unrelated to search

## User Experience Summary

### Interaction Model

The search control should feel like one continuous tool with two visual states:

1. a hero-state search box in the top content block
2. a pinned-state search bar that takes over near the top edge during scroll

The user should perceive this as a morphing transition, not as two unrelated controls.

### Scroll Transition Rules

- At the top of the page, the hero search remains dominant and the sticky shell stays visually dormant.
- As the user scrolls down, the hero search subtly lifts, scales down slightly, and fades.
- Over the same range, the sticky shell fades in, settles into the safe-area-aware top region, and becomes the active visible search surface.
- Once the sticky shell is established, subsequent content scrolls underneath a protected top layer with enough color separation and depth to avoid overlap.

### Visual Layering Rules

- The sticky layer must not be transparent enough for incoming content to feel stacked on top of it.
- The sticky layer should use a restrained gradient, soft blur, and a bottom divider or shadow to clarify depth.
- The effect should feel professional and calm, aligned with the current cyan-to-slate page palette.

## Current Problems

### Disconnected Search Presence

The current search input exists only in the hero area. After the user scrolls, the page loses a stable search anchor.

### Weak Scroll Hierarchy

The current top section does not provide a dedicated pinned visual layer, so upward-moving content can feel too close to the top chrome.

### Abruptness Risk

If this is solved by simply making the existing search box `position: sticky` or `fixed`, the transition will likely feel abrupt and visually heavy, especially on a mobile viewport.

## Proposed Approach

### Recommended Approach

Use a dual-shell morphing pattern:

- retain the current hero search block in normal document flow
- add a fixed sticky search shell at the top of the mobile viewport
- drive both shells from a shared `searchQuery` state
- compute a scroll progress value from the relationship between the hero search anchor and the sticky target region
- use that progress to animate opacity, translation, scale, and backdrop intensity

This approach keeps the interaction feeling continuous while staying implementation-safe. It avoids unstable layout shifts that are common when trying to transform a single DOM node directly from in-flow content into a fixed top bar.

### Why Not a Single-Node Sticky Conversion

Trying to convert a single input from in-flow content to a sticky/fixed element often produces:

- layout jumps
- position flicker
- awkward keyboard/focus behavior
- brittle threshold logic across device sizes

The dual-shell model is more robust while still delivering the intended perception of one evolving control.

## Component Boundaries

### `frontend-app/pages/deepread/MobileDeepReadPage.tsx`

This file should continue owning:

- page-level mobile extraction state
- `searchQuery`
- upload and document list state
- preview and artifact tab state

This change should only add small, focused interaction state for the mobile sticky-search behavior:

- refs for hero-search anchor and sticky shell
- scroll progress state
- derived visual-state values for hero and sticky search presentation

### Search Presentation Unit

The search presentation remains inside the same page file for now because:

- it is tightly coupled to this page's specific header layout
- the user requested a precise mobile page interaction change rather than a reusable global component
- extracting prematurely would increase risk without clear reuse

The code should still be locally structured so the hero search and sticky search shell are understandable as distinct view concerns.

## Visual Design Direction

The sticky state should feel:

- lighter than a full navigation bar
- more structured than the current free-floating hero input
- safely layered above scrolling content

Recommended visual ingredients:

- a top fixed shell using a pale cyan-to-white gradient
- backdrop blur for separation
- a subtle bottom border and soft shadow
- slightly denser padding than the hero search so the pinned state reads as “toolbar-grade”
- smooth opacity and position interpolation rather than sudden snapping

## Interaction Design

### Hero Search State

- large, friendly, and integrated into the hero area
- full visual prominence
- normal content-flow placement

### Transition State

- hero search gradually fades and rises
- sticky shell gradually appears from above with reduced vertical offset
- title/hero area remains readable; no hard collapse is required

### Sticky Search State

- fixed beneath the safe area
- remains clearly visible while content scrolls below
- keeps the same search text as the hero state
- supports touch interaction without exposing duplicate visual focus confusion

## Error Handling and Safety

- If scroll measurements are temporarily unavailable, the page should safely default to hero-state search.
- If the user never scrolls enough to trigger the transition, the page should still behave exactly like the current page.
- If the page content is too short to meaningfully scroll, the sticky shell should not become visually dominant.
- The transition must not interfere with upload controls, document list interaction, or bottom navigation.

## Implementation Plan

1. Add a scroll-progress mechanism tied to the hero search anchor and sticky target shell.
2. Introduce a fixed sticky search shell with safe-area-aware positioning and layered background treatment.
3. Animate the hero search block using the same progress value so it appears to morph into the sticky shell.
4. Keep both shells bound to the existing `searchQuery` state.
5. Prevent visual collision by adding a fixed top gradient/backdrop layer and tuned shadow/divider depth.
6. Preserve the current extraction-page structure and all existing filtering logic.
7. Run `npm run build` in `frontend-app`.
8. Use live browser monitoring on the authenticated mobile extraction page to verify:
   - top-state hero search is unchanged in intent
   - scrolling causes a smooth sticky takeover
   - pinned search remains readable
   - upward-scrolling content no longer visually collides with the search bar
   - the page still works with the existing mobile navigation and extraction UI

## Acceptance Criteria

- the mobile extraction page still loads correctly in authenticated state
- the hero search is visible and usable at the top of the page
- the sticky search gradually appears during downward scroll instead of snapping in abruptly
- the sticky top layer visibly separates itself from scrolling content using color/depth treatment
- search text remains synchronized during the transition
- upload shortcuts, parsed document list, preview panel, and artifact panel remain functional
- `frontend-app` builds successfully
- live browser verification on a mobile viewport confirms the intended interaction

## Risks

### Duplicate Input Risk

Using two rendered search inputs can create interaction ambiguity if both feel active at the same time. Mitigation: keep them visually crossfaded and make the active state obvious through opacity and pointer behavior.

### Scroll Threshold Risk

Hard-coded thresholds can behave poorly across mobile sizes. Mitigation: derive the transition from measured element positions rather than a raw page-scroll constant wherever possible.

### Visual Overdesign Risk

An overly strong sticky layer could feel like a second app bar and reduce content space. Mitigation: keep the shell compact, soft, and consistent with the existing page palette.

## Test Strategy

- static build verification via `frontend-app`
- live mobile-browser verification on the authenticated `deepread_extraction` page
- progressive scroll checks at the top, mid-transition, and fully pinned states
- spot-check search typing in both top and sticky states
- confirm that upload, document selection, preview, and bottom navigation still behave as before
