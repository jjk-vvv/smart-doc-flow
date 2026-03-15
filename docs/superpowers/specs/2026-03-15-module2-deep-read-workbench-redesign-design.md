# Module 2 Deep Read Workbench Redesign

Date: 2026-03-15

## Summary

This design upgrades Module 2 from a functional document parsing page into a stable, high-clarity document analysis workbench.

The approved interaction model is:

`upload document -> parse document -> show extraction categories inside the extraction results panel -> click a category to reveal only that category's content -> click a specific content item to jump the center preview to the corresponding page`

The previous standalone trace panel will be removed from the right-side results area.
Trace becomes part of the extraction results experience instead of a separate vertical block.

The approved visual direction is a `Blueprint Theater` style:

- keep the current blue-slate theme as the structural base
- avoid a single-color blue wash
- introduce controlled coral and cyan accents for focus and navigation
- make the center preview the visual stage
- make the right panel feel like a precise analysis console rather than a plain card list

This redesign is intentionally scoped to Module 2.
It does not redesign global navigation, Module 4, or unrelated assistant flows.

## Goals

- Remove the standalone trace box from the extraction results area.
- Make extraction categories such as `字段`, `表格`, `图片`, and `其他` act as explicit switches at the top of the results panel.
- Ensure clicking a specific content item jumps only to the matching page in the center preview.
- Preserve the existing project theme direction based on slate and blue while making the page visibly more refined and distinctive.
- Reduce interaction fragmentation between `fieldItems`, `traceHits`, and PDF preview navigation.
- Improve visual hierarchy so the page feels like a designed professional workbench instead of a generic glass-card dashboard.
- Refactor the Module 2 frontend in a focused way so the result-navigation area is easier to maintain and test.
- Preserve current parsing data contracts as much as possible and avoid unnecessary backend coupling for the UI upgrade.

## Non-Goals

- Do not redesign Module 4 or the overall product shell.
- Do not replace the current parsing pipeline as part of this design.
- Do not introduce a new standalone trace details page or a new modal-based trace workflow.
- Do not shift the project into an unrelated color system such as purple, warm beige, or red-black.
- Do not refactor every concern inside `DeepReadWorkbench.tsx` in one pass. Only the boundaries needed for this redesign should move.
- Do not require users to jump to image artifact viewers as the primary navigation outcome. The required behavior is page jump in the center preview when a page exists.

## Current Problems

### Interaction Problems

- The right panel currently splits `抽取结果` and `溯源定位` into two stacked sections. This duplicates context and forces the user to scan in two places for one task.
- The existing trace grouping creates a long vertical list that does not match the approved behavior of category switching.
- A user can already click some field items to jump pages, but the interaction is not presented as the primary organizing principle of the results area.
- The current model uses both `activeFieldKey` and `activeTraceKey`, but their presentation is fragmented. The user sees multiple lists instead of one coherent navigation surface.
- Trace error, trace counts, and field results are visually separated even though they belong to the same mental model: "where did this extracted content come from?"

### Visual Problems

- The current page uses many good building blocks such as glass surfaces, slate neutrals, and blue accents, but the overall composition still feels flat.
- The page relies on repeated rounded cards and local color accents rather than a strong stage-based layout.
- Blue is used frequently across buttons, pills, highlights, and surfaces, but without enough contrast from secondary accent colors or stronger depth cues.
- The center preview is functionally important but does not yet feel like the visual anchor of the page.
- Empty, loading, warning, and completed states are readable but not memorable.

### Structural Problems

- `frontend/components/DeepReadWorkbench.tsx` is currently about 4006 lines long and mixes document lifecycle, preview rendering, result derivation, trace derivation, assistant UI, and styling in one file.
- The results area contains dense JSX with mixed responsibilities:
  - filter/search UI
  - trace grouping
  - table and figure rendering
  - click-to-jump behavior
  - copy actions
  - warning surfaces
- Existing logic such as `traceHits`, `traceGroups`, `traceTypeStats`, `activeFieldKey`, `activeTraceKey`, and `jumpToPdfPage` is workable, but it is not organized around the approved UI model.

## Product Decision

The approved product behavior is:

- no standalone trace box
- extraction categories are shown explicitly at the top of the extraction results area
- clicking a category shows only that category's content block
- clicking a specific content item jumps the center preview to the corresponding page
- page jump is the primary trace outcome

This means Module 2 should present trace as an inline evidence-navigation capability embedded in extraction results, not as a separate subsystem in the UI.

## Design References And Interpretation

The visual system should borrow principles from strong market examples without copying their colors or layouts directly:

- `Linear`: use its disciplined panel boundaries and high-density clarity
- `Vercel`: use its center-stage breathing room and strong focal hierarchy
- `Stripe`: use its selective highlight strategy so only key surfaces glow
- `Raycast`: use its concentrated emphasis logic for active regions, but not its red-black palette

The translation into this product is:

- structural base: blue-slate technical workbench
- emphasis accents: coral for active selection, cyan for navigation glow and preview guidance
- atmosphere: light grid, faint blueprint lines, restrained glass and depth
- tone: precise, analytical, premium, and document-centric

## Target User Experience

### Overall Composition

The page remains a three-part workbench, but the visual hierarchy becomes more intentional:

- left side: document and task rail
- center: preview stage
- right side: extraction console

The center preview must become the visual anchor.
The right panel must become the interaction anchor.
The left side remains supportive and lighter in emphasis.

### Preview Stage

The center preview area should feel like a focused document stage:

- stronger framing around the preview viewport
- subtle blueprint-grid or measurement-line treatment in the surrounding chrome
- clearer current-page visibility
- more deliberate highlight treatment when a result item triggers a page jump
- less generic panel treatment than the current card stack

### Extraction Console

The right-side extraction panel should become a single coherent console with three layers:

1. summary and search
2. category switcher
3. category-specific result content

There is no separate trace container below it.

## Information Architecture

### Top-Level Regions

- `Workbench Header`
- `Document Rail`
- `Preview Stage`
- `Extraction Console`
- `Assistant Panel`

The redesign focuses mainly on `Preview Stage` and `Extraction Console`, while preserving compatibility with the existing `Assistant Panel`.

### Extraction Console Structure

The extraction console should be organized as:

1. `Results Summary Bar`
2. `Category Switcher`
3. `Inline State Banner`
4. `Category Content Region`

#### Results Summary Bar

Shows:

- result count
- average confidence
- parse warnings when present
- search input
- copy current visible results action

This bar remains compact and should not compete visually with the category switcher.

#### Category Switcher

The switcher is the primary interaction surface of the panel.
It replaces the old standalone trace section header and trace stat pills.

It should display available categories only when they contain content.
Recommended order:

1. `字段`
2. `表格`
3. `图片`
4. `其他`

Each category chip shows:

- label
- count
- active state

The active chip should use blue as the structural color, coral as the selected underline or notch accent, and cyan as a subtle glow or outline assist.

#### Inline State Banner

This region communicates local state without creating extra panel clutter.

Examples:

- `当前展示：字段 12 项`
- `当前分类暂无可跳转页码`
- `溯源定位异常，已显示可用抽取内容`

Trace errors should appear here rather than inside a separate trace box.

#### Category Content Region

This region shows only the active category's items.
It should not show all categories in one continuous stream.

## Result Data Model

The view layer should normalize result content into a single front-end shape before rendering.

Recommended UI model:

```ts
type WorkbenchResultCategory = "field" | "table" | "image" | "other";

type WorkbenchResultItem = {
  id: string;
  category: WorkbenchResultCategory;
  title: string;
  summary: string;
  confidence: number | null;
  pageNumber: number | null;
  fieldKey?: string | null;
  traceKey?: string | null;
  artifactUrl?: string | null;
  locatorSummary?: string | null;
  tablePreview?: {
    headers: string[];
    rows: string[][];
  } | null;
  imageMeta?: {
    modes: string[];
    keyPoints: string[];
  } | null;
};
```

This shape should be derived from existing `fieldItems` and `traceHits`.
No backend contract change is required for the first implementation pass.

## Interaction Model

### Default Category Selection

When a document becomes active:

- choose the first non-empty category in the preferred order
- preserve the user's previous category if the same category still exists for the new view
- if no category has content, show the empty state in the content region

### Category Switching

When the user clicks a category chip:

- set the active category
- update the content region to only show items of that category
- keep search input applied within the active category
- preserve the center preview and current page unless the user then clicks an item

### Result Item Click

When the user clicks a specific content item:

- set the active result item
- synchronize `activeFieldKey` when the item maps to a field
- synchronize `activeTraceKey` when the item maps to a trace hit
- if the active renderer is PDF and `pageNumber` exists, call `jumpToPdfPage(pageNumber)`
- visually confirm the jump by updating the preview stage highlight

### Preview Synchronization

When the visible PDF page changes due to scroll:

- update the current page indicator
- optionally highlight items in the active category that belong to the visible page
- do not auto-switch categories based on scroll

### Search Behavior

Search should apply inside the active category only.

This keeps the UI predictable:

- category = the user's current scope
- search = a filter inside that scope

### Copy Behavior

The copy action in the results summary bar should copy only the currently visible items in the active category and current search state.

### Keyboard And Accessibility Behavior

- category chips must be keyboard focusable and operable
- result cards must be keyboard focusable and operable
- active state must not depend on color alone
- page jump feedback must have readable textual support such as `P6`

## Category-Specific Rendering

### Fields

Field items are the most frequent and should be the most compact.

Each field card should show:

- field label
- extracted value
- confidence
- page badge when present

When a field has trace mapping, the card behaves as the page-jump trigger.

### Tables

Table items should show:

- concise table title
- page badge
- locator summary when present
- a small preview grid using existing table data

The card should remain scannable and not expand into a full spreadsheet.

### Images

Image items should show:

- image label
- page badge when present
- optional artifact thumbnail
- key points or content modes

The click action still prioritizes center preview page jump.
Opening the artifact remains a secondary action only.

### Other

Other items should be visually quieter and serve as overflow for content that does not cleanly belong to the main three categories.

## Visual System

### Core Palette

The design must preserve the current theme direction in `frontend/global.css`.

Recommended palette behavior:

- structural primary: existing blue
- structural neutrals: slate and cool gray
- active accent: muted coral
- assist accent: cool cyan
- status accents: existing emerald and amber for success and warnings

The key rule is:

- blue structures the interface
- coral marks user focus
- cyan marks navigation energy
- emerald and amber remain semantic states

### Surface Strategy

The page should use a layered surface model:

- outer atmospheric background
- workbench shell
- stage frames
- active cards

Not every region should use the same glass treatment.
The center preview frame should be more architectural.
The right panel should be denser and more precise.

### Decorative Language

Use restrained, theme-safe detail rather than loud decoration:

- subtle measurement lines
- faint grid overlays
- low-opacity blueprint-style texture
- controlled glow on active chips and active preview indicators
- sharper sectional dividers

Avoid:

- loud rainbow gradients
- purple-heavy glow
- oversized glass blur everywhere
- generic "AI dashboard" motifs

### Motion

Motion should be purposeful and sparse:

- stagger entrance for summary, switcher, and content region
- quick active-category transition
- preview page-jump confirmation pulse
- hover lift on cards kept subtle

## Component And Hook Boundaries

This redesign should improve maintainability without rewriting all of Module 2.

Recommended extraction units:

### `useWorkbenchResultCatalog`

Purpose:
Normalize `fieldItems` and `traceHits` into category counts, active-category content, visible items, and copy text.

Consumes:

- `fieldItems`
- `traceHits`
- `resultSearchQuery`
- active category

Produces:

- category counts
- normalized items
- visible items
- empty-state metadata
- copy payload

Does not own:

- preview navigation
- layout rendering

### `ExtractionCategorySwitcher`

Purpose:
Render the category chips and active state.

Consumes:

- category counts
- active category
- change handler

Produces:

- accessible category switch UI

Does not own:

- result card rendering

### `ExtractionResultList`

Purpose:
Render the current category's visible items and wire item click behavior.

Consumes:

- visible normalized items
- active item id
- click handlers

Produces:

- category-specific cards

Does not own:

- search input
- summary bar

### `PreviewStageChrome`

Purpose:
Wrap the existing preview renderer with stronger stage framing and active page feedback.

Consumes:

- current page
- page count
- jump state

Produces:

- visual preview shell

Does not own:

- PDF rendering internals

### `useResultSelectionSync`

Purpose:
Coordinate active result item, `activeFieldKey`, `activeTraceKey`, and page jump requests.

Consumes:

- normalized result item click events
- preview renderer state

Produces:

- synchronized selection state
- jump requests

Does not own:

- UI rendering

These boundaries keep the refactor focused on the redesigned experience instead of forcing a full workbench rewrite.

## Data Flow

The new front-end data flow should be:

1. existing parse payload populates `fieldItems` and `traceHits`
2. `useWorkbenchResultCatalog` derives normalized categories and items
3. `ExtractionCategorySwitcher` selects one active category
4. `ExtractionResultList` renders only that category's visible items
5. item click calls `useResultSelectionSync`
6. selection sync updates `activeFieldKey`, `activeTraceKey`, and preview jump request
7. `PreviewStageChrome` reflects the jump with stage-level feedback

## Error Handling And Edge Cases

### Missing Trace Data

If `traceHits` is empty but `fieldItems` exists:

- still show category switching
- show `字段` content normally
- show no-page state on cards without page mapping

### Missing Page Numbers

If an item has no `pageNumber`:

- the card remains viewable
- the jump affordance is visually muted
- clicking does not throw or create noisy warnings

### Non-PDF Preview Modes

If the active renderer is not PDF:

- selection still updates
- page jump is skipped
- the card can still show locator hints or artifact actions when available

### Trace Lookup Error

If trace lookup fails:

- show an inline banner in the extraction console
- do not create or restore a separate trace box
- keep category content available when possible

### Empty Category

If the active category has no items:

- show a dedicated empty state for that category
- preserve the switcher so the user can move to another category

### Large Result Sets

If a category contains many items:

- the list should remain virtual-scroll friendly in structure
- avoid excessive preview payloads in each card
- keep thumbnails and mini tables bounded

## Implementation Strategy

This redesign should be implemented in a focused sequence:

1. normalize result categories and visible item derivation
2. replace standalone trace UI with integrated category switching
3. migrate click-to-jump logic onto normalized result items
4. restyle preview stage and extraction console
5. polish loading, empty, warning, and completed states
6. verify the full workflow in the browser with real documents

The first implementation pass should reuse existing backend payloads.
Only introduce backend changes if a front-end gap is proven during implementation.

## Testing Strategy

### Unit-Level Checks

- category counts are derived correctly from `fieldItems` and `traceHits`
- default category selection chooses the first available category
- active-category search filters only the current category
- normalized result items preserve page numbers and trace mapping

### Interaction Checks

- clicking a category switches visible content
- clicking a field item updates active field and jumps preview page
- clicking a table or image item with a page number jumps preview page
- items without page numbers do not trigger invalid jumps

### Visual Checks

- category switcher remains readable in light and dark themes
- center preview is visibly the main stage
- active state remains distinct without relying only on blue fill
- empty, warning, and loading states fit the new visual system

### Browser Verification

Use `agent-browser` to verify:

- the category switcher behavior
- page jump behavior in the center preview
- the absence of the old standalone trace box
- layout quality at desktop widths and narrower widths used by the current app

## Success Criteria

The redesign is successful when all of the following are true:

- the old standalone trace box is gone
- the extraction results area uses explicit category switching
- only the active category's content is shown at one time
- clicking a specific item correctly jumps the center preview to the matching page
- the page looks materially more designed while still feeling like the same product
- the blue-slate theme remains intact, but the interface no longer feels like a single-tone blue dashboard
- the Module 2 result-navigation area becomes easier to reason about than the current mixed trace-and-results implementation
