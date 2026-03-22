# Module 2 PDF.js Viewer Standardization Design

Date: 2026-03-22

## Summary

This design formalizes the next refinement pass for the Module 2 document preview experience.

The user request was framed as:

`change PDF file rendering to a frontend PDF.js-based rendering approach`

After reviewing the current implementation, the correct conclusion is:

- Module 2 already uses frontend `pdfjs-dist` rendering for PDF preview
- Word preview already follows the intended unified path:
  - backend converts `doc` or `docx` to previewable PDF
  - frontend renders the resulting PDF through the current custom PDF.js canvas viewer
- the core problem is not rendering technology selection
- the core problem is that the current custom viewer structure and shell styling do not yet behave or feel like a clean professional document reader

The approved direction is therefore:

`keep the existing frontend PDF.js route -> standardize the custom viewer -> simplify PDF-mode shell chrome -> preserve all existing trace and jump interactions`

This spec is intentionally conservative about contracts and aggressive about viewer clarity.
It aims to make the preview feel more like a real reading surface without destabilizing extraction, trace location, or Word/PDF convergence.

## Why This Spec Exists

The current Module 2 preview is functionally strong, but visually and structurally it still shows several signs of an evolved-in-place implementation:

- PDF mode already renders correctly, but the reading surface feels like a canvas stack inside a designed card shell rather than a natural document reader
- PDF mode currently inherits workbench-stage chrome that is suitable for a general preview area, but too heavy for long-form document reading
- the current structure mixes loading, page rendering, visible-page detection, jump-to-page behavior, and PDF-shell presentation inside the same component region
- the preview is deeply coupled to source-location workflows, so replacing the viewer stack casually would create regression risk

The result is a mismatch:

- the technical foundation is already correct
- the user-perceived experience is still not at the expected level

This spec narrows the work to the right problem:

`improve the existing PDF.js viewer implementation rather than changing rendering technology`

## Relationship To Earlier Specs

This design builds on and refines:

- `docs/superpowers/specs/2026-03-15-module2-deep-read-workbench-redesign-design.md`
- `docs/superpowers/specs/2026-03-16-module2-professional-workbench-polish-design.md`
- `docs/superpowers/specs/2026-03-17-module2-seamless-resizable-workbench-design.md`

Where those earlier specs define the overall Module 2 workbench language, this document focuses specifically on the PDF and Word preview surface inside that workbench.

This spec should be treated as the active reference for any implementation that changes PDF preview behavior or PDF-mode presentation.

## Current Implementation Snapshot

The current implementation already confirms the following:

- frontend dependency already includes `pdfjs-dist`
- PDF preview is loaded on the frontend through `pdfjs-dist`
- Word preview is normalized through converted PDF before rendering
- visible-page state is already derived inside the current PDF preview component
- trace-card click behavior already jumps to PDF pages
- page-count UI already depends on the current PDF preview state
- trace overlays and evidence highlight logic are layered on the current preview stage

Important current file references:

- `frontend/components/DeepReadWorkbench.tsx`
- `frontend/package.json`

The PDF preview implementation currently exists as a custom `PdfCanvasPreview` component embedded inside `DeepReadWorkbench.tsx`.

That means the work does not begin from zero.
It begins from a functioning but overly entangled implementation.

## Core Diagnosis

The preview problems are not primarily caused by PDF.js itself.
They come from the interaction between viewer structure and workbench shell layout.

### 1. PDF Mode Uses Too Many Visual Layers

The current PDF experience is visually read as:

`workbench stage -> PDF container card -> per-page cards`

This creates a "card inside card" feeling.
Instead of feeling like the user is reading a document, it feels like the user is inspecting a document widget.

### 2. PDF Mode Has More Than One Scroll Context

The current workbench center region includes a larger preview-area layout shell, while the PDF viewer also owns its own internal scroll container.

That layering is technically workable, but it weakens the feeling of a single coherent reading surface.
It also makes future sticky controls, page awareness, and text-layer alignment harder to reason about.

### 3. Viewer Logic And Viewer Presentation Are Too Coupled

The current implementation combines:

- PDF loading
- page rendering
- stack sizing
- visible-page detection
- jump-to-page behavior
- loading and error overlays
- shell rendering

inside one viewer block that is still embedded in a much larger page component.

This makes the preview harder to evolve safely.

### 4. PDF Preview Is Not An Isolated Product Unit Yet

The viewer is currently an implementation detail inside a large workbench file.
It is not yet treated as a standalone product surface with a clear interface.

That is the main structural reason the preview still feels less polished than the surrounding capability deserves.

## Goals

- Preserve the current frontend PDF.js rendering foundation.
- Preserve the current Word-to-PDF unified preview path.
- Make PDF mode feel like a clean professional reading surface rather than a decorative preview card.
- Standardize the viewer into a dedicated component boundary with a clear interface.
- Preserve page-count reporting, visible-page reporting, and jump-to-page behavior.
- Preserve compatibility with trace-card page jumps and future trace-overlay alignment.
- Reduce layout and styling complexity specifically for PDF mode.
- Create an implementation path with low regression risk and clear regression checks.

## Non-Goals

- Do not replace frontend PDF.js with browser-native PDF rendering.
- Do not replace the viewer with `react-pdf` in this pass.
- Do not embed the official full PDF.js web viewer in this pass.
- Do not redesign the overall Module 2 workbench shell again.
- Do not change backend preview APIs or extraction contracts.
- Do not rewrite the entire `DeepReadWorkbench.tsx` file in one uncontrolled pass.
- Do not introduce text selection, search indexing, annotation editing, or collaborative commenting in this pass.

## Hard Constraints

### 1. Preserve Word/PDF Unified Preview Semantics

For preview purposes:

- `pdf` files render directly
- `doc` and `docx` files continue to render through converted PDF when preview conversion is available

The user should continue to experience Word and PDF as one coherent page-based preview family.

### 2. Preserve Trace And Evidence Navigation

Any viewer refactor must preserve or preserve compatible equivalents for:

- current page count
- current visible page
- jump-to-page from trace cards
- jump-to-page from field items
- preview reset behavior when active document changes

### 3. Preserve Existing Frontend/Backend Contracts

This refactor must not require backend changes for:

- preview conversion
- extraction result loading
- trace hit loading
- evidence artifact linking

### 4. Keep Regression Risk Low

The implementation must prefer:

- extraction of a dedicated viewer component
- interface compatibility
- shell simplification

over:

- technology replacement
- wholesale preview rewrite
- backend-driven preview redesign

## Option Comparison

Three realistic paths were considered.

### Option A: Keep Current PDF.js Route And Refactor The Custom Viewer

Summary:

`retain pdfjs-dist -> extract a cleaner viewer -> simplify PDF shell -> preserve interfaces`

Advantages:

- lowest regression risk
- preserves all current trace and jump behavior
- preserves Word/PDF convergence
- keeps the implementation aligned with the current codebase
- solves the real problem instead of swapping libraries

Costs:

- still requires careful component surgery inside a large file
- does not automatically give us advanced text-layer features unless we add them later

### Option B: Switch To react-pdf

Summary:

`replace custom PDF.js loading with a React wrapper on top of PDF.js`

Advantages:

- slightly more declarative component model
- potentially cleaner page rendering primitives

Costs:

- still ultimately depends on PDF.js
- does not solve the shell and layout problems by itself
- introduces migration work without guaranteed UX benefit
- adds avoidable regression surface for trace coupling

### Option C: Replace With Official PDF.js Full Viewer Or Browser-Native Preview

Summary:

`delegate more of preview behavior to a prebuilt viewer surface`

Advantages:

- standard viewer behavior out of the box
- built-in viewer controls in some variants

Costs:

- highest integration friction
- much harder to align with current trace-card and field-card interactions
- more difficult to style into the current workbench
- browser-native preview gives away too much control

### Recommendation

Option A is the best and most appropriate path.

This is the approved direction because it improves the exact pain point the user is feeling while preserving the interaction model the product already depends on.

## Approved Design

The approved direction is:

`standardize the existing PDF.js viewer into a dedicated PDF-mode reader component`

This means the work should be understood as:

- not a viewer technology migration
- not a backend preview redesign
- not a generic polish pass

It is specifically:

`a PDF-mode reader cleanup and component-boundary standardization pass`

## Target User Experience

When a PDF or converted Word document is opened, the preview should feel:

- like a real reading surface
- visually calm
- structurally simple
- easy to navigate by page
- clearly synchronized with trace and result actions

It should not feel:

- like a card gallery
- like a framed demo canvas
- like a page embedded inside too many layers of product chrome

The desired mental model is:

`I am reading the document in the center, and the trace panel is steering me inside that reading surface`

not:

`I am interacting with a preview widget in the center while the right panel separately points at it`

## Architecture

### 1. Extract A Dedicated PDF Viewer Component

The current `PdfCanvasPreview` should become a dedicated viewer unit with a clearer contract.

Recommended target shape:

- `PdfJsViewer`

Responsibilities:

- load PDF document
- own the single PDF-mode scroll container
- render page canvases
- report page count
- report visible page
- accept jump-to-page requests
- own loading and error states specific to PDF preview

This component should not know about:

- assistant state
- result-panel layout
- extraction summary logic
- broader workbench orchestration beyond its input and output props

### 2. Separate Viewer Shell From Workbench Shell

The workbench should decide:

- whether the active file is in PDF mode
- which preview URL to use
- when to request a page jump

The PDF viewer should decide:

- how pages are laid out
- how scrolling maps to visible page
- how page canvases are sized and rendered

This separation makes future changes safer and much easier to test.

### 3. Make PDF Mode A Single-Scroll Reading Surface

PDF mode should present one primary reader scroll container.

The center workbench region may still exist as a layout boundary, but PDF reading itself should feel like one continuous reading context.

That means implementation should avoid:

- nested scroll ambiguity
- decorative inner shells that visually compete with the page stack
- multiple layers of padding and card chrome around the document

### 4. Keep Page-State APIs Stable

The following state contract should remain stable or stable-by-equivalent:

- viewer reports `pageCount`
- viewer reports `visiblePage`
- workbench sends `scrollRequest`
- workbench derives `currentPdfPage`
- trace and field interactions continue to trigger page jumps through one central function

This is the compatibility bridge that lets us refactor viewer internals without destabilizing the rest of Module 2.

## Visual Design Rules For PDF Mode

### 1. Reduce Outer Chrome

The current outer rounded card, ring, and heavy shadow around the PDF mode container should be reduced.

PDF mode should feel closer to:

- a reading surface
- a clean paper stage

and less like:

- a premium dashboard card

### 2. Keep Page Separation But Make It Lighter

Individual pages should remain visually separable.
That is useful for long documents and page-awareness.

However, the page shell should become lighter:

- smaller radius
- softer or smaller shadow
- less ring emphasis

The page itself should be the focus, not its container.

### 3. Let The Document Own More Horizontal Presence

The viewer should prioritize document readability over decorative stage margins.

That means:

- less wasted shell padding
- clearer centering
- stronger "reader" proportion in wide layouts

### 4. Keep Controls Functional, Not Dominant

Zoom, rotate, and page navigation controls stay.
But the document must remain the dominant visual element.

The controls are command tools, not the hero of the region.

## Data Flow

The intended flow remains:

1. user selects a file
2. workbench resolves preview source:
   - direct PDF URL for PDF
   - converted PDF URL for Word when available
3. workbench renders PDF-mode viewer
4. viewer loads PDF through `pdfjs-dist`
5. viewer reports page count
6. viewer reports visible page as user scrolls
7. trace-card or field-card action requests a target page
8. workbench emits a page jump request
9. viewer scrolls to the target page

This flow is already present conceptually.
The implementation goal is to make it more explicit and less tangled.

## Error Handling

The viewer should continue to support:

- loading state while PDF is being fetched or rendered
- error state when PDF cannot be loaded or rendered
- fallback open-in-new-window link when preview rendering fails

However, error handling should become viewer-local and visually scoped to the reading surface, not mixed with unrelated workbench state.

For Word preview specifically:

- if conversion is pending, the workbench continues to show the conversion state
- once converted PDF is ready, the viewer becomes responsible for PDF loading and rendering feedback

## Testing Strategy

### Functional Regression

Verify that the following remain correct:

- PDF page count is displayed correctly
- visible page changes as the user scrolls
- clicking a trace card jumps to the correct page
- clicking a field item jumps to the correct page
- changing active document resets the PDF page state correctly
- Word preview still renders through converted PDF when preview conversion is available

### UX Regression

Verify that the following visibly improve:

- PDF mode no longer feels like layered cards
- document pages occupy the center more naturally
- scrolling feels like one reading surface
- page navigation feels visually consistent with what the user sees

### Future-Safe Regression Checks

The refactor should leave a stable path for:

- adding a text layer later
- aligning trace overlay coordinates more cleanly
- adding page virtualization for very long PDFs later

## Implementation Sequence

The implementation should proceed in this order:

1. extract the current PDF preview logic into a dedicated viewer component boundary
2. preserve the existing page-count and visible-page callback contract
3. preserve the existing scroll-request contract
4. simplify PDF-mode outer shell styling
5. simplify per-page card styling
6. ensure there is one primary reader scroll context in PDF mode
7. run Word and PDF preview regression checks with trace-card jumps
8. only after that, consider optional second-pass improvements such as text layer support

## Risks

### 1. Trace Navigation Regression

If page reporting or jump behavior changes subtly, trace-card clicks may still scroll, but not land at the expected visual position.

Mitigation:

- preserve current page APIs
- test with real trace-card jumps after refactor

### 2. Overlay Alignment Regression

If shell sizing or viewport scaling changes without care, future or existing overlay boxes may become visually misaligned.

Mitigation:

- keep viewer scaling logic explicit
- re-check overlay rendering after shell cleanup

### 3. Word Preview Inconsistency

If the refactor assumes only direct PDF behavior, converted Word preview may regress.

Mitigation:

- treat converted Word preview as part of the core supported PDF-mode path

## Acceptance Criteria

This design is successful when all of the following are true:

- Module 2 still uses frontend PDF.js rendering for PDF-mode preview
- Word preview still uses converted PDF and renders through the same PDF viewer path
- the preview visibly feels more like a reader and less like a decorative preview card
- page count, visible page, and jump-to-page behavior still work
- trace-card and field-card navigation still land the user on the right page
- the refactor leaves behind a clearer component boundary for future evolution

## Final Decision

The correct product and engineering choice is:

`do not replace the rendering technology`

The best next step is:

`refactor and standardize the existing PDF.js viewer so that PDF mode behaves like a proper document reader inside Module 2`
