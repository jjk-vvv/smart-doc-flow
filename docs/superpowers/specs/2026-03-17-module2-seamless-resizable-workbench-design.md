# Module 2 Seamless Resizable Workbench Design

Date: 2026-03-17

## Summary

This design revises the current Module 2 frontend direction into a tighter, larger-feeling, and more disciplined analysis workbench.

It supersedes the earlier "large polished top bar + floating three-card shell" approach with a new approved direction:

`compact control bar -> seamless three-pane workbench -> manual pane resizing -> precise Chinese copy -> self-hosted Google font`

This spec exists because the previous polish pass improved visual quality, but still left three user-facing problems unresolved:

- the top bar feels too large and too close to a page hero instead of a workbench command strip
- the three main panes still read as separated cards rather than one continuous analysis surface
- the page still contains wording and duplicate UI signals that feel internal, repetitive, or less precise than the desired product tone

The user-approved target is:

`a professional, trustworthy, spacious-feeling document analysis workstation that uses precise Chinese wording, avoids internal naming, avoids unnecessary English, keeps the upload hero intact, and allows users to resize the main panes manually`

## Why This Spec Exists

The current frontend has already established a stronger visual shell than the original Module 2 page, but the latest review surfaced a more exact product bar:

- the page must feel like one complete workbench, not several attractive cards placed side by side
- the page must use user-facing Chinese rather than internal product naming
- the page must remove duplicated summary blocks and duplicated global actions
- the page must support user-controlled spatial allocation between the document list, preview stage, and result panel

This spec therefore narrows the work from "general polish" to a more specific and more demanding outcome:

`convert Module 2 into a compact, seamless, resizable Chinese-first analysis workbench without breaking existing frontend/backend behavior`

## Relationship To Earlier Specs

This design builds on and refines:

- `docs/superpowers/specs/2026-03-15-module2-deep-read-workbench-redesign-design.md`
- `docs/superpowers/specs/2026-03-16-module2-professional-workbench-polish-design.md`

This new spec should be treated as the active design reference for the next implementation pass.

Where it differs from the previous polish spec, this document takes precedence.

## Goals

- Preserve the current three-pane workflow structure:
  - left: file list
  - center: document preview
  - right: results and assistant
- Compress the current top bar into a true workbench control strip rather than a large banner.
- Remove unnecessary English and all internal-facing Module labels from the user-facing UI.
- Use precise, natural, and product-appropriate Chinese across the page.
- Remove duplicate summaries, duplicate labels, and duplicate global actions.
- Convert the three-pane body into a seamless, continuous workbench rather than separated floating cards.
- Add manual horizontal resizing between left/center and center/right panes.
- Keep the current upload hero component unchanged inside the preview empty state.
- Preserve current frontend/backend interaction contracts and session behavior.
- Introduce a typography system based on a self-hosted Google font that supports a calm, premium Chinese interface tone.

## Non-Goals

- Do not redesign Module 4 or the platform shell.
- Do not replace the upload hero component inside the center preview empty state.
- Do not change backend payloads, endpoints, or request sequencing.
- Do not replace the existing preview rendering model for PDF, Office conversion, images, spreadsheets, or text.
- Do not introduce a fully dockable IDE-like layout system with arbitrary pane rearrangement.
- Do not force a whole-site typography migration in this pass.
- Do not rewrite the entire `DeepReadWorkbench.tsx` file in one uncontrolled refactor.

## Hard Constraints

### 1. No Internal Module Naming In The UI

The user-facing frontend must not display internal development labels such as:

- `模块二`
- `Module 2`
- any similar internal numbering or module naming artifacts

The page must read like a user product surface, not an internal tool or test page.

### 2. No Unnecessary English

The UI must not include decorative or redundant English labels such as:

- `Document Rail`
- `Analysis Console`
- other stylistic English overlays that are not required for user understanding

The copy system should be Chinese-first and fully understandable without English support text.

### 3. Copy Must Be Precise Chinese

All prominent labels, pane headings, state tags, and helper copy must use natural and accurate Chinese.

Avoid:

- internal development wording
- overly abstract labels
- mixed terminology for the same concept
- ornamental wording that sounds "designed" but not precise

### 4. The Upload Hero Must Remain Unchanged

The current central upload hero component and its interaction behavior must stay intact.

The redesign may change the shell around it, but must not redesign the upload hero itself.

### 5. Frontend/Backend Contracts Must Stay Compatible

The redesign must remain compatible with the current Module 2 flow around:

- `POST /extract/jobs/create`
- `GET /extract/jobs/status/{job_id}`
- `POST /extract/summarize`
- `POST /extract/trace/locate`
- `POST /extract/assistant/session`
- `POST /extract/assistant/chat/stream`
- compatibility path `POST /extract/assistant/query`
- `POST /extract/preview/office/start`
- `GET /extract/preview/office/status/{job_id}`

### 6. Existing Stability Hooks Must Be Preserved

The redesign should preserve or preserve compatible equivalents for:

- session restore behavior
- assistant session restore behavior
- preview recovery behavior
- key automation selectors such as upload, extract, assistant, and trace surfaces

### 7. Pane Resizing Must Be Manual But Disciplined

The workbench must support user-controlled resizing, but only within bounded limits.

This pass supports:

- left-to-center horizontal resize
- center-to-right horizontal resize

This pass does not support:

- arbitrary pane docking
- freeform drag reordering
- full layout editor behavior

## Current Problems To Solve

The current implementation still shows these experience problems:

- the top bar is visually too tall and occupies too much vertical priority
- large top summary cards duplicate information that could be expressed more tightly
- left, center, and right regions still read as separate floating cards because of visible gaps
- global actions are split between multiple areas, which weakens hierarchy
- user-facing naming is not yet fully aligned with the desired Chinese product tone
- typography is inconsistent and still relies on local Chinese system font assumptions

## Approved Direction

The approved direction is:

`compact control strip + seamless three-pane body + bounded pane resizing + Chinese-first copy + self-hosted Google font`

The page should feel:

- professional
- calm
- large-feeling
- precise
- trustworthy
- intentional

The page should not feel:

- like a floating card dashboard
- like an internal admin surface
- like a banner-led landing page
- like a multilingual visual experiment

## Information Architecture

The page should be organized into only two major macro-regions:

1. `Top Control Strip`
2. `Continuous Analysis Workbench`

The `Continuous Analysis Workbench` contains three panes:

- `文档列表`
- `文档预览`
- `结果与助手`

These three panes must feel like one connected system.

## Region Design

### 1. Top Control Strip

The top region becomes a compact horizontal control strip rather than a large hero.

It contains exactly three groups:

#### Title Group

Shows:

- primary title: `非结构化文档分析`
- one short line of scope such as `支持文档抽取、原文定位与结果核验`

It does not show:

- internal module numbering
- English decorative badges
- oversized descriptive copy

#### Status Group

Shows 3 to 4 compact status pills only:

- current document
- document count
- extraction state
- warning or prompt count when relevant

These are compact, one-line, and non-repetitive.

#### Global Action Group

Shows the only global action set on the page:

- `导入文档`
- `开始提取`
- `规则设置`
- `导出结果`
- `清空数据`

These actions should not be duplicated elsewhere in equivalent global form.

### 2. Continuous Analysis Workbench

The body below the control strip becomes one continuous workbench shell.

Visual rules:

- no visible gaps between left, center, and right macro-panes
- one outer workbench shell
- pane boundaries are defined by dividers and resize handles, not whitespace
- only the outer shell keeps the large corner treatment
- inner panes should not appear as three independent floating cards

### 3. Left Pane: `文档列表`

The left pane is responsible only for document inventory and per-file state.

Shows:

- pane title: `文档列表`
- current batch count
- file list
- file progress and status
- active document emphasis

Does not show:

- decorative English labels
- duplicated global status blocks
- duplicate global action buttons

The current bottom rule button should be removed if the same action is already available in the top strip.

Recommended final behavior:

- `规则设置` exists only in the top control strip

### 4. Center Pane: `文档预览`

The center pane remains the main evidence stage.

Shows:

- preview title
- preview-only toolbar actions
- current preview content
- unchanged upload hero in empty state
- current bottom status strip

The center toolbar should keep only preview-scoped actions such as:

- zoom
- rotate
- reset
- page navigation
- preview focus

It should not contain duplicate global actions such as extract, export, clear, or rules.

### 5. Right Pane: `结果与助手`

The right pane becomes a more disciplined result-and-assistant surface.

Main heading:

- `结果与助手`

Tabs:

- `抽取结果`
- `智能助手`

Within results mode, the page may still contain:

- `原文定位`
- result list
- warnings and error states

But these elements should not repeat the same high-level summary content already shown in the top control strip.

The right pane header should be simplified:

- remove large duplicated summary cards
- keep only lightweight contextual status when necessary

## Copy System

### Approved High-Level Labels

Use these as the primary copy baseline:

- page title: `非结构化文档分析`
- page subtitle: `支持文档抽取、原文定位与结果核验`
- left pane: `文档列表`
- center pane: `文档预览`
- right pane: `结果与助手`
- results tab: `抽取结果`
- assistant tab: `智能助手`
- trace section: `原文定位`

### Recommended Empty States

- `暂未导入文档`
- `请在预览区导入文件`
- `暂无抽取结果`
- `暂无定位信息`

### Copy Principles

- one concept should use one stable Chinese label
- avoid overlapping synonyms for the same feature
- avoid internal jargon
- avoid decorative English
- avoid abstract labels that are less clear than direct Chinese phrasing

## Typography System

### Font Strategy

The page should adopt a self-hosted Google font for Chinese UI typography.

Approved choice:

- `Noto Sans SC`

This font should be self-hosted rather than fetched directly from Google at runtime.

### Scope

This typography change should apply to Module 2 page styling first, rather than forcing a whole-site font migration in the same pass.

### Weights

Use:

- `400` for body and helper text
- `500` for interface controls and minor emphasis
- `700` for primary titles and section titles

### Implementation Rules

- define `@font-face` in shared frontend CSS
- expose a font variable such as `--font-ui`
- apply the new font at the Module 2 page root
- remove direct `Microsoft_YaHei` usage within the Module 2 workbench where touched

### Typography Goals

The page should feel:

- modern
- stable
- highly legible
- not flashy
- not platform-default

## Layout And Resizing System

### Seamless Pane Model

The current grid model should be replaced by a dynamic pane layout with no inter-pane gap.

Recommended structure:

- left pane width variable
- left resize handle
- center flexible pane
- right resize handle
- right pane width variable

### Resize Capabilities

This pass supports two horizontal resize interactions:

1. left pane vs center pane
2. center pane vs right pane

### Suggested Constraints

- left pane minimum: about `240px`
- left pane default: about `280px`
- left pane maximum: about `420px`
- right pane minimum: about `320px`
- right pane default: about `360px`
- right pane maximum: about `520px`
- center pane minimum: preserved so preview remains usable

### Resize Interaction Rules

- hover on handle reveals a stronger divider state
- pointer drag updates pane size live
- double click restores default width
- pane widths persist locally across reloads
- preview focus mode may hide the left pane, but should preserve its last manual width

### Resize Technical Notes

Resize changes must trigger appropriate downstream layout refresh where needed, especially for:

- PDF preview sizing
- Office preview sizing
- spreadsheet preview sizing

## Visual System

### Shell Strategy

The page should visually shift from:

- separated elevated cards

to:

- one continuous workbench shell with internal dividers

### Spacing Strategy

Important distinction:

- structural gaps between major panes should be removed
- internal content spacing inside each pane should remain measured and readable

This means:

- no macro-level pane gaps
- still keep controlled interior spacing for lists, forms, and result cards

### Border And Shadow Strategy

- reduce floating card feel
- weaken independent shadows on large pane shells
- rely more on shared shell boundaries and divider logic
- use shadows sparingly for local emphasis rather than for every major pane

### Motion Strategy

Motion should remain restrained and workbench-appropriate.

Keep:

- resize handle hover/active feedback
- small tab transitions
- small focus transitions after preview navigation
- smooth pane show/hide transitions

Reduce or remove:

- hero-like entry emphasis
- large floating hover lifts
- dramatic glow treatments
- oversized animated attention effects

## Behavior Preservation Rules

The redesign must preserve existing behavior around:

- file upload and merge behavior
- extraction creation and polling
- summarize requests
- trace locate requests
- assistant streaming and restore
- preview conversion and preview recovery
- result click to preview navigation
- active field and active trace synchronization

## Freeze Zones

### Upload Hero Freeze Zone

The center upload component itself must remain visually and behaviorally unchanged.

### API Freeze Zone

No backend contract changes are allowed for this pass.

### Selector Freeze Zone

Key `data-testid` selectors used by realistic automation should remain available or remain compatible.

## Recommended Implementation Structure

The implementation should stay low-risk and should prefer extraction of layout-specific concerns rather than broad behavioral refactor.

Recommended local units or derivations:

### `TopControlStrip`

Purpose:

- render the compact page title, summary pills, and global actions

### `ResizableWorkbenchLayout`

Purpose:

- own pane widths
- own resize handles
- restore and persist pane sizes

### `DocumentListPane`

Purpose:

- render file list only
- remove duplicate global actions

### `PreviewPane`

Purpose:

- keep preview-specific controls only
- host unchanged upload hero and preview surfaces

### `ResultsAndAssistantPane`

Purpose:

- simplify the right-side header
- keep results, trace, and assistant available without duplicate summary cards

## Implementation Plan

### Workstream 1: Copy And Typography Foundation

Tasks:

- define the final Chinese-facing label set
- add self-hosted `Noto Sans SC`
- apply page-level typography scope for Module 2
- remove internal module labels and unnecessary English from Module 2 UI

Exit criteria:

- no `模块二` or decorative English remains in the Module 2 workbench UI
- Module 2 uses the new font system locally

### Workstream 2: Compact Top Control Strip

Tasks:

- compress the current large top bar into a compact control strip
- remove the large duplicated summary cards
- keep only one global action row

Exit criteria:

- the top region reads as a command strip, not a hero banner

### Workstream 3: Seamless Workbench Shell

Tasks:

- remove macro pane gaps
- unify left/center/right into a continuous shell
- rebalance borders, radii, and shadows so the layout feels like one workbench

Exit criteria:

- the three panes feel connected rather than card-separated

### Workstream 4: Horizontal Pane Resizing

Tasks:

- implement left-center resize
- implement center-right resize
- persist widths locally
- restore widths safely
- ensure preview reflows after pane changes

Exit criteria:

- users can manually allocate width between panes without breaking preview usability

### Workstream 5: Duplicate Content And Action Cleanup

Tasks:

- remove duplicate rule action
- remove duplicate summary cards
- remove duplicate global actions from preview toolbar
- simplify right pane header state

Exit criteria:

- each feature or summary appears in one intentional location only

### Workstream 6: Verification

Tasks:

- verify extraction flow
- verify preview flow
- verify result-to-preview navigation
- verify assistant flow
- verify pane resize persistence and recovery
- verify upload hero remains unchanged

Exit criteria:

- no functional regression in current Module 2 flows

## Testing Strategy

### Behavior Checks

- extraction still starts and polls correctly
- preview still recovers correctly
- trace locate still updates current evidence
- assistant session restore still works
- assistant streaming still works

### Layout Checks

- top control strip remains compact on typical desktop sizes
- no visible macro gaps remain between the three main panes
- resizing does not collapse the preview into unusable widths
- left pane restore works after preview focus toggle

### Typography Checks

- the page renders correctly when the self-hosted font loads
- fallback behavior remains readable if font loading fails
- Chinese UI text remains visually consistent across the page

### Freeze-Zone Checks

- upload hero is unchanged
- API contracts are unchanged
- critical automation selectors remain compatible

## Acceptance Criteria

The redesign is successful only if all of the following are true:

- the page title is `非结构化文档分析`
- the Module 2 UI shows no internal module numbering
- the UI contains no unnecessary decorative English
- the page uses precise Chinese wording consistently
- the top area is a compact control strip rather than a large banner
- the three panes form one continuous workbench shell
- users can manually resize the main panes horizontally
- the upload hero remains unchanged
- backend interactions remain unchanged
- duplicate summaries and duplicate global actions are removed
- Module 2 adopts a self-hosted Google font strategy locally

## Risks

- pane resizing can destabilize preview layout if downstream viewers do not react well to width changes
- copy cleanup can accidentally remove useful context if "duplicate" information is removed too aggressively
- typography rollout can produce inconsistent render behavior if scoped too broadly
- shell unification can reduce readability if internal spacing is collapsed too far instead of only removing macro gaps

## Spec Review Notes

Self-review completed for this spec.

Review focus:

- the user-requested removal of internal module naming is explicitly captured
- decorative English removal is explicitly captured
- typography strategy is specific, scoped, and compatible with a self-hosted Google font
- seamless pane layout and manual resizing are bounded and implementation-oriented
- upload hero, backend contracts, and stability hooks remain protected

Review result:

- approved for user review

## Approval State

Approved by user for the following design direction:

- use `非结构化文档分析` as the page title
- do not show `模块二` or equivalent internal module labels in the UI
- do not use unnecessary English in the Module 2 page
- use precise Chinese copy
- use a self-hosted Google font
- compress the top bar
- remove duplicate fields and duplicate global actions
- make the main panes seamless
- allow manual horizontal resizing between panes

Design status:

- written
- self-reviewed
- ready for user review after commit
