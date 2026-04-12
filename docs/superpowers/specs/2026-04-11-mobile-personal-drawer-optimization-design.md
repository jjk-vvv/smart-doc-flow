# 2026-04-11 Mobile Personal Drawer Optimization Design

## Background

The mobile frontend for Smart Doc Flow lives in `frontend-app/`. The current mobile shell already supports:

- a bottom navigation with `dashboard / deepread_extraction / fusion`
- an avatar-triggered personal drawer from the left side
- a dashboard-specific mobile entry surface
- desktop/mobile shell separation inside `frontend-app/App.tsx`

The remaining issue is not functional correctness, but product quality. The personal drawer works, yet it still feels too much like a generic navigation list instead of a professional, account-centric mobile side panel. In addition, the avatar entry on non-dashboard pages should feel more uniform so users can develop a stable mental model: tapping the avatar always opens the same personal menu.

This work must remain narrow and safe:

- do not change backend behavior
- do not change Module 2 parsing workflows
- do not restore a standalone `我的` bottom-tab entry
- do not introduce large-scale shell rewrites

## Goals

1. Make the mobile personal drawer feel closer to a polished QQ-style personal side panel while preserving the product's professional analysis-workbench tone.
2. Unify the avatar-triggered personal menu entry across dashboard and non-dashboard mobile pages.
3. Improve drawer hierarchy, grouping, spacing, and motion without changing routing semantics.
4. Reduce `App.tsx` responsibility only where it directly improves maintainability for this mobile feature.

## Non-Goals

- redesigning desktop navigation
- changing login/auth API behavior
- changing bottom navigation information architecture
- refactoring unrelated page content
- introducing decorative visual language that conflicts with the product's professional tone

## User Experience Summary

### Entry Model

On mobile, the avatar is the single primary entry point for personal/account actions. Users should not need to scan the bottom navigation for a separate profile tab.

### Drawer Model

The left drawer should read as:

1. account identity area
2. common app destinations
3. account/settings actions
4. one clear bottom primary action such as login or logout

### Behavioral Rules

- tapping the avatar opens the drawer
- tapping the overlay closes the drawer
- selecting a destination closes the drawer and navigates
- opening account-related actions closes the drawer before opening a modal
- the same avatar affordance should be visible and recognizable on dashboard and non-dashboard mobile surfaces

## Current Problems

### Visual Hierarchy

The drawer content is functional but still reads as a stack of similar buttons. The account area, navigation area, and settings area do not yet feel distinct enough.

### Consistency

The dashboard and non-dashboard pages already expose the same capability, but the presentation is not yet unified enough to feel like one coherent mobile shell pattern.

### Maintainability

`frontend-app/App.tsx` currently owns too much of the mobile drawer view structure. The file is still workable, but this feature will be safer to evolve if the drawer presentation and related mobile shell affordances are better bounded.

## Proposed Approach

### Recommended Approach

Use a small-scope structural optimization:

- keep current routing and state flow
- extract the mobile personal drawer presentation into a dedicated component
- optionally extract the mobile avatar trigger into a tiny reusable component if this reduces duplication
- preserve current tab semantics and workbench transitions

This approach balances quality and safety. It improves clarity and polish without turning the task into a shell rewrite.

### Why Not a Full Shell Rewrite

A full mobile shell rewrite would increase regression risk across onboarding, workbench transitions, and route-specific top chrome. That is not justified for the current request.

## Component Boundaries

### `frontend-app/App.tsx`

Responsibilities after this change:

- own mobile/desktop shell state
- own active tab state
- own drawer open/close state
- own auth modal/account security modal state
- pass data and callbacks into mobile shell subcomponents

It should stop owning detailed drawer markup where possible.

### New Mobile Drawer Component

Suggested responsibility:

- render the mobile personal drawer surface
- render account header, grouped navigation items, settings items, and bottom action
- remain stateless with respect to navigation and modal decisions
- receive all state through props

### Optional Mobile Avatar Trigger Component

Suggested responsibility:

- render the reusable circular avatar button
- encapsulate consistent size, border, label, and icon/avatar text behavior

This should only be introduced if it genuinely reduces duplication with low risk.

### `frontend-app/pages/dashboard/MobileDashboard.tsx`

Responsibilities should remain:

- render the mobile dashboard content
- expose an `onOpenDrawer` entry point
- avoid duplicating drawer logic

## Visual Design Direction

The drawer should feel:

- professional and composed
- account-centric rather than menu-centric
- mobile-native rather than admin-dashboard-like

Specific visual adjustments:

- stronger account header block with clearer identity emphasis
- more explicit grouping labels and spacing between groups
- fewer competing borders and less “every row is the same card” feeling
- refined contrast and depth that stay within the existing blue-slate product language
- purposeful motion, not flashy motion

## Interaction Design

### Drawer Motion

- keep left-to-right slide-in
- refine easing and perceived weight so the drawer feels less abrupt
- ensure overlay supports clear focus separation from page content

### Navigation Feedback

- active destination should remain immediately recognizable
- tap targets must remain large and stable for touch use

### Accessibility

- preserve `aria-label` on avatar and close affordances
- preserve background content de-emphasis while drawer is open
- keep keyboard and screen-reader semantics at least as good as current behavior

## Error Handling and Safety

- if user data is absent, drawer header falls back to a neutral guest state
- if login/account actions fail later, this feature must not interfere with existing modal behavior
- if a page is already in a special mobile workbench mode, the avatar entry must still open the same drawer without disturbing ongoing page state beyond overlaying the shell

## Implementation Plan

1. Document the feature boundary and acceptance criteria.
2. Inspect current mobile shell rendering in `App.tsx` and `MobileDashboard.tsx`.
3. Extract the mobile personal drawer into a focused component under `frontend-app/components/` or another existing mobile-appropriate location.
4. Optionally extract a shared mobile avatar trigger only if it reduces duplication cleanly.
5. Adjust the drawer layout, grouping, spacing, and visual hierarchy.
6. Keep all navigation and modal behavior unchanged from the user's perspective.
7. Run `npm run build` in `frontend-app`.
8. Use `agent-browser` on the live mobile page to verify:
   - avatar opens the drawer
   - drawer closes correctly
   - navigation still works
   - no standalone `我的` bottom tab appears
   - dashboard and non-dashboard avatar entry look consistent

## Acceptance Criteria

- mobile bottom nav still contains only `首页 / 提取 / 融合`
- the personal menu is opened from the avatar, not from a bottom-tab profile entry
- dashboard and non-dashboard mobile pages expose a visually consistent avatar entry
- the drawer has clearer account, navigation, and settings hierarchy
- login/logout and account security actions still function through existing modals
- build passes in `frontend-app`
- browser regression confirms the interaction path works on a mobile viewport

## Risks

### Over-Refactor Risk

If too much shell code is moved at once, regressions may appear in unrelated mobile page flows. Mitigation: keep extraction limited to the drawer and optionally the avatar trigger.

### Visual Drift Risk

If the drawer becomes too consumer-like, it may conflict with the product's workbench identity. Mitigation: retain the existing blue-slate base, restrained accents, and evidence-oriented tone.

### State Coupling Risk

Drawer behavior touches navigation and auth-related UI. Mitigation: keep state ownership in `App.tsx`; only move presentational markup outward.

## Test Strategy

- static build verification via `frontend-app` build
- real browser verification using `agent-browser` with mobile viewport
- spot-check dashboard, extraction page, and another non-dashboard page
- verify drawer open/close, navigation, and modal entry paths
