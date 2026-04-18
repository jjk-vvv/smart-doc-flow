# Document Workbench Homepage Redesign

## Goal

Replace the current web `dashboard` homepage with a Tencent Docs-inspired document workbench homepage that is:

- document-first instead of dashboard-first
- suitable for real day-to-day operator work
- capable of carrying files into module1, module2, module3, and module4
- centered on file queue, preview, and toolbox continuity
- visually close to Tencent Docs in information architecture and interaction rhythm, without copying Tencent brand assets

The redesigned homepage must make the web entry feel like the platform's primary document operating surface.

## Product Context

The product is a professional document-intelligence workspace for operators who need to upload documents, inspect previews, move files between AI modules, and continue work without losing context.

The homepage should feel:

- precise
- trustworthy
- intelligently capable
- document-centric
- calm and operational rather than flashy

The user explicitly wants:

- a Tencent Docs-like homepage shell
- upload + folder management
- central file queue
- click file to preview in a full-screen mode
- `docx` preview via `docx -> pdf`
- a right-side toolbox tied to module workflows
- drag-and-drop from the file queue into module upload targets
- module1 quick prompts that prefill but do not auto-send
- module3 inline source/template staging without page jump
- module2/module4 lightweight upload entry points and visible linkage

## Non-Goals

This redesign does not attempt to:

- clone Tencent logos, brand graphics, or proprietary visual assets
- redesign the mobile homepage in the same pass
- rewrite existing module workbenches end-to-end
- build a true backend-backed cloud drive in this pass

Folder and file organization at homepage level may start from a frontend-managed workspace session model, as long as the user-facing workflow is coherent and does not block later backend persistence.

## Design Direction

The homepage should use a high-similarity Tencent Docs shell, but its center of gravity must shift toward this product's stronger preview and downstream-AI workflow abilities.

Visual direction:

- light technical workspace
- pale blue-slate structural base
- restrained blue accents for primary actions
- dense but calm workbench layout
- subtle layered surfaces instead of dashboard cards everywhere
- full-screen preview as the "power state"

The one memorable thing should be:

"This homepage is not a landing page or dashboard. It is a document operating system for AI workflows."

## Primary User Stories

1. A user uploads one or more documents and immediately sees them appear in a central queue.
2. A user creates folders and keeps uploaded files organized by topic or task.
3. A user clicks a file and enters a full-screen preview state.
4. A user previews a `docx` file through converted PDF rather than a broken or degraded Word preview.
5. A user drags a file from the queue into a module action target in the toolbox.
6. A user opens module1 from the toolbox with a file and a prefabricated prompt, but the message is not sent automatically.
7. A user prepares module3 inputs from the homepage by assigning a template file, source files, and user requirements, without leaving the homepage.
8. A user sends a file into module2 or module4 from the homepage and then manually switches to those modules for deeper work.
9. A user closes the right toolbox while staying in preview and reopens it on demand.

## Information Architecture

## Default Homepage State

The homepage will have three persistent regions:

1. Left rail
   - top brand/header area
   - primary navigation
   - folder tree
   - quick management actions

2. Center document workspace
   - search and top actions
   - queue filters and sort controls
   - recent document list / working document queue
   - batch operations and empty states

3. Right toolbox
   - selected file summary
   - module1 quick prompts
   - module2 intake
   - module3 staged upload zone
   - module4 intake
   - recent handoff traces / hints

## Full-Screen Preview State

Clicking a queue item transitions the page into a preview takeover state.

In this state:

- left rail collapses away
- center becomes the large preview canvas
- a top floating preview toolbar appears
- the right toolbox becomes a closable slide-out panel
- closing the toolbox expands preview width
- a compact reopen button remains pinned at the upper-right edge

This state is the primary answer to the user's requirement that preview should be direct and immersive.

## Component Model

## 1. Homepage Shell

Responsibilities:

- provide the document-workbench page background, spacing system, and overall layout
- switch between default mode and preview takeover mode
- preserve selected file, folder, and toolbox state

Dependencies:

- homepage workspace session state
- queue data
- preview state
- module handoff helpers

## 2. Workspace Session Layer

Responsibilities:

- persist homepage folders, queue items, selected file, and lightweight UI state
- act as the shared "handoff bridge" between homepage and downstream modules

Initial persistence approach:

- frontend localStorage-backed session store

Why:

- module2 and module3 already use local persistence patterns
- this minimizes backend risk for the first pass
- it creates a stable integration seam for later backend persistence

The workspace session layer should store:

- folders
- uploaded queue items
- recent file selection
- preview entry metadata
- module handoff drafts

## 3. File Queue

Responsibilities:

- render queue rows in a Tencent Docs-like document list/table rhythm
- support upload, rename, move to folder, remove from queue, and drag start
- expose metadata such as type, updated time, source, and readiness

Queue row capabilities:

- single click selects
- primary click opens full-screen preview
- hover shows secondary actions
- drag payload can be consumed by toolbox drop targets

## 4. Upload and Folder Management

Responsibilities:

- support `新建文件夹`
- support homepage-level uploads
- assign uploaded files to current folder
- surface upload progress and failure states

Initial scope:

- local file ingestion into homepage queue
- folder tree and naming in session store
- no hard dependency on a new backend storage service

## 5. Preview Runtime

Responsibilities:

- choose appropriate preview strategy by file type
- drive full-screen takeover mode
- coordinate preview toolbar, zoom, close, and toolbox docking

Preview rules:

- `pdf`: direct PDF preview
- `docx`: convert to PDF first, then preview
- text-like files: text preview
- images: image preview
- xlsx: spreadsheet preview surface if already supported, otherwise structured preview fallback

Implementation note:

The preview runtime should reuse proven logic from the existing document-processing workbench rather than re-inventing conversion and PDF behaviors.

## 6. Right Toolbox

Responsibilities:

- display actions that are always relative to the current selected file
- provide direct handoff entry points to downstream modules
- support click and drag-drop workflows
- remain available in both default homepage mode and preview mode

The toolbox must not become a generic control sidebar. It is a context-sensitive action surface for the current document.

## 7. Module Handoff Bridge

Responsibilities:

- convert homepage file context into module-specific draft state
- make downstream modules open into a meaningful prepared state

Module-specific behaviors:

### Module1

- expose quick prompts under module1
- clicking a quick prompt writes prompt text plus current file attachment into a module1 handoff draft
- homepage navigates to module1
- the input is prefilled
- the file is attached
- nothing is auto-submitted

### Module2

- expose a lightweight upload/drop target
- user can send a selected file into module2 preparation state
- homepage may navigate or simply leave the file staged depending on final implementation detail
- the intent must reflect module2 as the upstream step for extraction

### Module3

- expose two explicit slots:
  - template file
  - source file set
- support drag from queue into either slot
- support a requirement input field
- synchronize those values into module3 state without forcing immediate navigation

### Module4

- expose a lightweight upload/drop target
- visually connect module4 to module2 with an "extract -> graph" relationship hint
- if the current file already has module2-derived structured signals later, the bridge can evolve toward richer downstream continuity

## Data Model

## Homepage Queue Item

Each homepage queue item should capture:

- stable id
- file name
- extension / mime
- size
- folder id
- created / updated timestamps
- source kind
- raw `File` handling metadata when available
- preview readiness status
- conversion status for `docx`
- preview asset references

## Folder Node

Each folder should capture:

- stable id
- display name
- parent folder id or root
- created / updated timestamps

## Module Handoff Draft

The handoff store should support:

- `module1`: draft text, attached homepage item ids
- `module2`: staged homepage item ids
- `module3`: staged template item id, staged source item ids, draft requirements
- `module4`: staged homepage item ids

## Interaction Design

## Homepage Default Flow

1. User lands on the document workbench homepage.
2. User sees left navigation, center queue, and right toolbox.
3. User uploads files or creates folders.
4. Files appear in the central queue.
5. User selects or drags files.
6. Toolbox actions activate for the selected file.

## Preview Flow

1. User clicks a file row.
2. Homepage enters full-screen preview takeover.
3. If file is `docx`, show conversion progress state.
4. Preview becomes visible.
5. Right toolbox is shown as a closable panel.
6. User can close toolbox, continue previewing, and reopen it later.

## Drag-and-Drop Flow

1. User drags a queue row.
2. Compatible module targets highlight.
3. Dropping on module2/module4 upload zones stages the file there.
4. Dropping on module3 template/source zones writes into the matching slot.
5. Visual confirmation appears immediately.

## Module1 Quick Prompt Flow

1. User is on homepage or preview mode with a selected file.
2. User clicks a module1 quick prompt chip.
3. Homepage writes a module1 draft payload.
4. Navigation switches to module1.
5. Module1 opens with input text and file attached.
6. User manually sends the message.

## Error and Edge Handling

The spec must explicitly handle the following cases:

- uploaded file cannot be previewed
- `docx -> pdf` conversion fails
- user opens preview before conversion completes
- user drags unsupported file type into a module slot
- module3 receives no template or no source file
- queue is empty
- folder has no files
- selected file is removed while preview is open
- local session data is malformed or missing
- downstream module handoff payload becomes stale

Fallback rules:

- preview errors should degrade to a clear "download or open in module" state, not a blank canvas
- malformed local state should reset safely
- unsupported drag targets should refuse the drop with an explicit visual state

## Visual Design Requirements

The implementation should borrow Tencent Docs structure and rhythm, but keep this product's identity.

Required visual characteristics:

- light document workbench shell
- slim top command area
- narrow but useful left navigation
- center-first document list with strong scanability
- restrained blue accent system
- subtle layered surfaces, not dashboard card overload
- refined shadows and borders
- full-screen preview that feels premium and deliberate

Forbidden directions:

- generic admin dashboard cards
- glass-heavy AI demo aesthetics
- purple gradient AI look
- dark-mode-first neon styling
- dashboard KPI hero sections as the homepage focal point

## Technical Reuse Strategy

To reduce regression risk, reuse rather than rewrite:

- `frontend/pages/doc-processing/DocProcessingWorkbench.tsx`
  - file preview categories
  - `docx -> pdf` conversion logic
  - fullscreen preview experience primitives

- `frontend/lib/fusionGridStore.ts`
  - module3 local persistence pattern

- `frontend/shared/state/workbenchSession.ts`
  - module2 local session persistence pattern

- `frontend/shared/state/extractionDocuments.ts`
  - cross-page storage + event synchronization pattern

The homepage should get its own focused session store instead of overloading existing module stores.

## Proposed Frontend Units

1. `frontend/pages/dashboard/Dashboard.tsx`
   - replaced with the new homepage composition shell

2. `frontend/pages/dashboard/home-session.ts`
   - homepage workspace session model and persistence helpers

3. `frontend/pages/dashboard/home-types.ts`
   - queue item, folder, preview, and handoff types

4. `frontend/pages/dashboard/home-handoff.ts`
   - module handoff writing helpers

5. `frontend/pages/dashboard/home-preview.ts`
   - preview adapter logic and `docx` conversion bridge

6. `frontend/pages/dashboard/components/*`
   - left rail
   - queue header
   - queue list
   - preview overlay
   - toolbox panel

These units should keep the new homepage understandable without forcing all logic into one giant file.

## Integration Requirements

## App Routing

No new top-level route is required. The redesign replaces the existing `dashboard` tab content.

## Module1 Integration

Module1 needs a lightweight homepage draft consumption path. The module1 page must be able to read and then clear a homepage-generated draft.

## Module3 Integration

Module3 should accept homepage synchronization into its local state shape so the homepage can populate template, docset, and draft requirements.

## Module2 and Module4 Integration

For this pass, homepage-to-module2 and homepage-to-module4 handoff may start as staged draft state plus optional navigation assistance, rather than fully automatic processing kickoff.

## Testing Strategy

Implementation is only acceptable if verified through browser-level checks.

Required checks:

1. Homepage default state renders correctly.
2. Upload actions add files to queue.
3. New folder creation and rename behave correctly.
4. Clicking a queue file opens full-screen preview.
5. `docx` enters conversion state and then previews as PDF.
6. Right toolbox can close and reopen in preview mode.
7. Module1 quick prompt writes draft and navigates without auto-send.
8. Module3 template/source staging writes into module3 state correctly.
9. Module2/module4 drag targets accept staged files without breaking homepage state.
10. Empty state and failure states remain visually coherent.

## Acceptance Criteria

The redesign is successful when:

- the web homepage no longer reads like a dashboard overview
- it reads like a document workbench
- upload, folder, queue, preview, and toolbox are all first-class
- preview is immersive and can dismiss the left rail
- the right toolbox is closable in preview mode
- homepage actions genuinely feed module workflows
- the design feels close to Tencent Docs in structure and interaction logic, while still belonging to this project

## Self-Review

Status: Approved for implementation planning

Review notes:

- scope is focused on the web homepage and cross-module handoff surface
- preview, state, and module integration boundaries are explicitly separated
- drag/drop, preview failure, conversion failure, and stale local state are covered
- backend-backed storage is intentionally deferred to avoid over-scoping this pass
