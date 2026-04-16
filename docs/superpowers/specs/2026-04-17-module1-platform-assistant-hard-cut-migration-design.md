# Module1 And Platform Assistant Hard-Cut Migration Design

Date: 2026-04-17

Status: approved-design

## Summary

This spec defines the approved migration design for:

- Module 1 document processing
- the platform-wide global assistant

The migration is a hard-cut architecture migration, not a compatibility-layer rollout.

The approved direction is:

- keep the backend module numbering model and land Module 1 formally at `backend/app/modules/module1`
- move the global assistant out of old Module 2 ownership and rebuild it as a FastAPI module at `backend/app/modules/platform_assistant`
- use `doc-processing` as the formal frontend product-domain identity for Module 1 on both web and mobile
- replace the current web `AI文档处理` placeholder path with the real Module 1 frontend
- add a fifth mobile bottom tab named `处理` for Module 1
- remove `deepread_interaction`, placeholder pages, old workbench entry files, and the old Node or Express assistant backend from the final architecture

This spec exists to turn the approved direction into a concrete, implementation-ready migration blueprint with:

- target directories
- ownership boundaries
- API contracts
- migration mappings
- cutover rules
- deletion rules
- regression acceptance

## Why This Spec Exists

The current project already has a unified FastAPI-based project shell, but Module 1 and the global assistant are still outside the real module system in different ways:

- Module 1 backend still exists as a standalone FastAPI app under `module1/backend`
- Module 1 frontend and mobile sources still exist as a separate root package under `module1/frontend` and `module1/mobile`
- the current web `AI文档处理` entry is still a placeholder
- the current mobile document interaction entry still uses the old workbench identity
- the current global assistant backend still exists as a standalone Node or Express app under `platform-usage-assistant/backend/server.cjs`
- the current live assistant chain in the product still leans on old Module 2 assistant ownership

This state creates four structural problems:

1. Product identity is unstable because Module 1 is represented by placeholder pages, old workbench pages, and legacy tab ids at the same time.
2. Backend ownership is unstable because the project shell expects a formal `module1`, but the real implementation still lives outside the unified module tree.
3. The global assistant is not truly platform-level because its runtime and context model still carry old module-specific assumptions.
4. The codebase remains harder to reason about because the same product behavior is spread across formal modules, legacy root projects, and old page identities.

This spec resolves those problems with a single approved architecture and a single approved final state.

## Approved Direction

The approved direction is a hard-cut migration with no compatibility route left in the final repository state.

That means the final architecture will:

- keep backend module numbering as `module1`
- use `doc-processing` as the formal frontend identity
- rebuild the platform assistant backend in FastAPI
- remove the old `deepread_interaction` identity from formal product use
- remove old placeholder pages
- remove old workbench entry files as formal Module 1 entrypoints
- remove the standalone Node or Express assistant backend from the final architecture

This is intentionally not a staged compatibility architecture.
It is a staged implementation process with a clean final architecture.

## Goals

- Make Module 1 a formal backend module inside `backend/app/modules`.
- Make the global assistant a formal FastAPI module inside `backend/app/modules`.
- Replace the web `AI文档处理` placeholder with the real Module 1 product page.
- Add a formal mobile Module 1 entry as the fifth bottom tab named `处理`.
- Unify Module 1 frontend ownership under a dedicated product domain named `doc-processing`.
- Unify the global assistant frontend ownership under a dedicated feature domain named `platform-assistant`.
- Connect both Module 1 and the platform assistant to the unified authentication and user-isolation model.
- Move runtime files and temporary work products out of the old source package roots.
- Remove duplicate product identities and old page shells from the final project structure.
- Preserve current core product capabilities while improving clarity and maintainability.

## Non-Goals

- Do not keep `deepread_interaction` as a formal long-term identity.
- Do not preserve the standalone Module 1 backend app as a formal runtime.
- Do not preserve the standalone platform assistant Node backend as a formal runtime.
- Do not keep placeholder or old workbench files as compatibility shells in the final state.
- Do not rewrite unrelated modules during this migration.
- Do not redesign Module 2 or Module 4 business behavior as part of this spec.
- Do not add a second state model for platform-assistant context just to preserve old Module 2 assistant coupling.

## Scope

This spec covers:

- Module 1 backend migration
- Module 1 web frontend migration
- Module 1 mobile frontend migration
- platform assistant backend FastAPI migration
- platform assistant web and mobile frontend migration
- navigation, registration, runtime, and deletion work required to complete that migration

This spec does not change the intended business role of:

- Module 2 extraction
- Module 3 fusion
- Module 4 knowledge graph
- the existing auth strategy outside the integration points needed by Module 1 and the platform assistant

## Current State Snapshot

### 1. Web Module 1 Entry Is Still A Placeholder

The web app still routes the `AI文档处理` position through a placeholder page instead of a formal Module 1 page.

Impact:

- the product identity is misleading
- the formal entry is not connected to the real source implementation

### 2. Mobile Module 1 Entry Still Uses Old Workbench Identity

The mobile app still uses the old document interaction workbench identity as the live entry path for Module 1-like behavior.

Impact:

- Module 1 does not have a clean mobile product identity
- old deepread-related semantics remain mixed into what should be Module 1

### 3. Backend Registry Already Expects Formal Module Wiring

The unified backend registry already expects a formal `module1` registration surface.

Impact:

- the current architecture already points toward the correct final shape
- the real code placement is what remains inconsistent

### 4. Module 1 Backend Source Is Still A Standalone App

The source implementation under `module1/backend` still uses its own standalone FastAPI app shape.

Impact:

- backend ownership remains split
- module runtime and source structure are not aligned

### 5. Global Assistant Backend Source Is Still A Standalone Node Runtime

The source implementation under `platform-usage-assistant/backend/server.cjs` still contains the assistant runtime as a separate Node or Express service.

Impact:

- the assistant is not yet part of the unified backend module system
- assistant runtime ownership is still outside the main architecture

### 6. Old Assistant Ownership Still Leaks Into The Live App

The current live assistant chain in the main app still relies on old assistant files and Module 2-adjacent ownership.

Impact:

- the assistant is not yet truly platform-level
- context and ownership boundaries remain blurred

## Final Architecture

## Backend Target Structure

```text
backend/app/modules/
  module1/
    __init__.py
    composition.py
    core/
      config.py
    api/
      router.py
      endpoints/
        health.py
        workbench.py
    schemas/
      workbench.py
    domain/
      models.py
    services/
      agent_service.py
      conversion_service.py
      preview_service.py
      modification_service.py
      save_service.py
      stream_service.py
      upload_service.py
    tests/

  platform_assistant/
    __init__.py
    composition.py
    api/
      router.py
      endpoints/
        health.py
        bootstrap.py
        chat.py
    schemas/
      chat.py
    services/
      context_service.py
      prompt_service.py
      guidance_service.py
      chat_service.py
    data/
      platform_facts.py
      page_configs.py
```

## Web Frontend Target Structure

```text
frontend/
  pages/
    doc-processing/
      DocProcessingPage.tsx
  features/
    doc-processing/
      components/
        DocProcessingWorkbench.tsx
        LuckysheetPreview.tsx
        ReportSelectionToolbar.tsx
      lib/
        workbenchSession.ts
        reportFormatting.js
        reportQuickEdit.ts
        reportRichFormatting.ts
        reportSelection.ts
    platform-assistant/
      components/
        PlatformAssistant.tsx
      lib/
        assistantContext.ts
        platformAssistant.ts
  shared/
    api/
      module1.ts
      platformAssistant.ts
```

## Mobile Frontend Target Structure

```text
frontend-app/
  pages/
    doc-processing/
      DocProcessingPage.tsx
  features/
    doc-processing/
      components/
        DocProcessingMobileWorkbench.tsx
        MobileComposer.tsx
        MobileCurrentFileCard.tsx
        MobileFollowUpSuggestions.tsx
        MobileMessageList.tsx
        MobilePreviewPage.tsx
        MobileReportPage.tsx
        MobileUtilityDrawer.tsx
      lib/
        workbenchSession.ts
        reportFormatting.js
        reportQuickEdit.ts
        reportRichFormatting.ts
        reportSelection.ts
    platform-assistant/
      components/
        PlatformAssistant.tsx
      lib/
        assistantContext.ts
        platformAssistant.ts
  shared/
    api/
      module1.ts
      platformAssistant.ts
```

## Naming And Product Identity

The final naming rules are:

- backend formal module name: `module1`
- frontend formal product-domain id: `doc-processing`
- web display label: `AI文档处理`
- mobile bottom-tab label: `处理`
- platform assistant backend module name: `platform_assistant`

The final architecture must not keep these as formal identities:

- `deepread_interaction`
- `module1-placeholder`
- old `DocInteractionWorkbench` page identities

## Module 1 Backend Design

## Backend Responsibility Boundaries

### `api/endpoints/workbench.py`

Purpose:

- expose Module 1 HTTP endpoints
- validate request payloads
- resolve authenticated user context
- delegate execution to focused services

Must not:

- contain large document-processing logic
- directly manage temp files or conversions
- embed prompt construction or export logic inline

### `services/upload_service.py`

Purpose:

- validate uploads
- normalize filenames and file metadata
- save source files into runtime workspace
- return canonical file handles for downstream services

### `services/preview_service.py`

Purpose:

- manage doc or docx to PDF preview flows
- manage office preview start, status, and artifact resolution
- produce canonical preview URLs and artifact references

### `services/stream_service.py`

Purpose:

- orchestrate streaming document-interaction behavior
- normalize conversation context
- invoke agent logic
- emit consistent response or stream structure

### `services/modification_service.py`

Purpose:

- apply requested document edits
- manage format patches and content mutations
- produce edit results suitable for preview and export

### `services/save_service.py`

Purpose:

- persist edited output into canonical runtime locations
- generate export results
- hand back canonical output references

### `services/conversion_service.py`

Purpose:

- contain lower-level conversion operations
- isolate external tools and conversion implementation details

### `services/agent_service.py`

Purpose:

- handle instruction interpretation and agent orchestration
- keep LLM or agent policy out of transport code

## Module 1 Runtime Layout

Module 1 runtime files must move out of the old source package and into the unified runtime root.

Approved runtime layout:

```text
backend/runtime-data/module1/{tenant_id}/{user_id}/{session_id}/
  uploads/
  previews/
  artifacts/
  exports/
  logs/
```

Meaning:

- `uploads/`: original uploaded files
- `previews/`: generated preview artifacts
- `artifacts/`: intermediate work products
- `exports/`: saved and exported edited files
- `logs/`: session-level processing records

This layout is required for:

- user isolation
- tenant isolation
- cleanup policy
- traceability
- production-style runtime hygiene

## Module 1 API Contract

Formal route prefix:

- `/module1`

Approved endpoints:

- `GET /module1/health`
- `POST /module1/operate-stream`
- `POST /module1/apply-modifications`
- `POST /module1/save-edited-document`
- `POST /module1/convert/docx-to-pdf`
- `POST /module1/convert/office/start`
- `GET /module1/convert/office/status/{job_id}`
- `GET /module1/convert/office/artifact/{job_id}`

Contract rules:

1. Module 1 responses must not expose raw disk paths.
2. Preview and artifact references must use formal platform URLs.
3. Authenticated user context must be available to write operations.
4. Artifact resolution must not depend on frontend-side host, port, or path guessing.

Preferred result shape for preview or export operations:

```json
{
  "job_id": "string",
  "artifact_id": "string",
  "status": "queued|processing|completed|failed",
  "preview_url": "string|null",
  "download_url": "string|null",
  "expires_at": "string|null"
}
```

## Module 1 Source Migration Matrix

| Old Source | New Target | Final Role |
|---|---|---|
| `module1/backend/main.py` | removed as formal runtime | replaced by unified module composition |
| `module1/backend/routes/document.py` | `backend/app/modules/module1/api/endpoints/workbench.py` | HTTP endpoint layer |
| `module1/backend/routes/health.py` | `backend/app/modules/module1/api/endpoints/health.py` | health endpoint layer |
| `module1/backend/models/document_models.py` | `backend/app/modules/module1/domain/models.py` | domain models |
| `module1/backend/schemas/api_schemas.py` | `backend/app/modules/module1/schemas/workbench.py` | HTTP and service schemas |
| `module1/backend/services/agent_service.py` | `backend/app/modules/module1/services/agent_service.py` | agent orchestration |
| `module1/backend/services/conversion_service.py` | `backend/app/modules/module1/services/conversion_service.py` | conversion primitives |
| `module1/backend/services/document_service.py` | split across `upload_service.py`, `stream_service.py`, `preview_service.py`, `modification_service.py`, `save_service.py` | focused service layer |
| `module1/backend/services/sandbox_service.py` | folded into upload and save flows | runtime file lifecycle support |
| `module1/backend/services/style_service.py` | folded into `modification_service.py` | document modification support |
| `module1/backend/core/config.py` | `backend/app/modules/module1/core/config.py` | module configuration |
| `module1/backend/tests/*` | `backend/app/modules/module1/tests/*` | module tests |

## Platform Assistant Backend Design

## Assistant Responsibility Boundaries

### `api/endpoints/bootstrap.py`

Purpose:

- return page-aware assistant starter state
- return approved prompt groups and starter cards for the current tab
- keep frontend starter behavior aligned across web and mobile

### `api/endpoints/chat.py`

Purpose:

- accept platform assistant chat requests
- accept normalized assistant context envelopes
- stream back assistant output

### `api/endpoints/health.py`

Purpose:

- expose assistant service readiness and health state

### `services/context_service.py`

Purpose:

- normalize page-level context envelopes
- validate context size and structure
- prevent context ambiguity across modules

### `services/prompt_service.py`

Purpose:

- assemble the assistant system prompt
- combine platform facts, page cues, and safe runtime context

### `services/guidance_service.py`

Purpose:

- resolve starter cards
- resolve guided action suggestions
- keep navigation recommendations structured and consistent

### `services/chat_service.py`

Purpose:

- execute actual assistant responses
- coordinate streaming
- apply fallback policy
- keep model-facing behavior isolated from routers

### `data/platform_facts.py`

Purpose:

- store stable platform facts
- prevent duplication of product facts across multiple frontends

### `data/page_configs.py`

Purpose:

- store tab-specific page cues, starter cards, and prompt groups
- define the assistant's page-aware guidance surface

## Assistant Formal Endpoints

Formal route prefix:

- `/api/platform-assistant`

Approved endpoints:

- `GET /api/platform-assistant/health`
- `GET /api/platform-assistant/bootstrap?tab=<tab_id>`
- `POST /api/platform-assistant/chat`

`bootstrap` is required.
It is not optional.

Reason:

- it lets web and mobile share one authoritative starter configuration source
- it removes duplicated frontend-maintained page-config logic
- it keeps the assistant platform-level instead of frontend-fragmented

## Assistant Context Contract

The assistant must not rely on implicit Module 2 localStorage reads as its formal context model.

Approved frontend-to-backend context envelope:

```ts
type AssistantContextEnvelope = {
  activeTab: string;
  pageCue: string;
  documents?: unknown[];
  selection?: Record<string, unknown> | null;
  moduleStatus?: Record<string, unknown> | null;
  sessionMeta?: {
    tenantId?: string;
    userId?: string;
    requestId?: string;
  };
};
```

Meaning:

- each page explicitly provides assistant context
- Module 1, Module 2, Module 3, and Module 4 can all use the same assistant protocol
- assistant ownership is platform-level, not Module 2-specific

## Assistant Streaming Contract

The assistant will use explicit SSE event types instead of retaining the old opaque `0:`-style stream as the formal protocol.

Approved stream shape:

```text
event: meta
data: {"tab":"doc-processing","request_id":"..."}

event: starter
data: {"title":"...","summary":"..."}

event: delta
data: {"text":"..."}

event: card
data: {"title":"...","summary":"...","steps":["..."]}

event: done
data: {"message_id":"..."}

event: error
data: {"message":"..."}
```

Reason:

- explicit event types are easier to maintain
- web and mobile can share one parser
- card outputs no longer need to be inferred from raw mixed text
- the protocol aligns better with a long-term FastAPI streaming implementation

## Web Frontend Design

## Formal Module 1 Web Entry

Approved web product identity:

- tab id: `doc-processing`
- label: `AI文档处理`

Approved page structure:

- `frontend/pages/doc-processing/DocProcessingPage.tsx`
- `frontend/features/doc-processing/components/DocProcessingWorkbench.tsx`

The web app must:

- remove `Module1PlaceholderPage` from formal use
- remove `deepread_interaction` from formal tab identity
- mount the real Module 1 page through `doc-processing`
- update sidebar navigation to target `doc-processing`

## Web Module 1 Frontend Migration Matrix

| Old Source | New Target | Final Role |
|---|---|---|
| `module1/frontend/components/DocInteractionWorkbench.tsx` | `frontend/features/doc-processing/components/DocProcessingWorkbench.tsx` | main web workbench |
| `module1/frontend/components/LuckysheetPreview.tsx` | `frontend/features/doc-processing/components/LuckysheetPreview.tsx` | spreadsheet preview |
| `module1/frontend/components/ReportSelectionToolbar.tsx` | `frontend/features/doc-processing/components/ReportSelectionToolbar.tsx` | report interaction tools |
| `module1/frontend/lib/workbenchSession.ts` | `frontend/features/doc-processing/lib/workbenchSession.ts` | workbench session state |
| `module1/frontend/lib/reportFormatting.js` | `frontend/features/doc-processing/lib/reportFormatting.js` | report formatting helper |
| `module1/frontend/lib/reportQuickEdit.ts` | `frontend/features/doc-processing/lib/reportQuickEdit.ts` | quick edit helper |
| `module1/frontend/lib/reportRichFormatting.ts` | `frontend/features/doc-processing/lib/reportRichFormatting.ts` | rich formatting helper |
| `module1/frontend/lib/reportSelection.ts` | `frontend/features/doc-processing/lib/reportSelection.ts` | report selection helper |

## Web Module 1 Client Contract

Create one authoritative client:

- `frontend/shared/api/module1.ts`

Rules:

- all Module 1 frontend code must call this client
- no component may hardcode `localhost:5000`
- no component may construct hidden legacy API roots inline

## Mobile Frontend Design

## Formal Mobile Module 1 Entry

Approved mobile product identity:

- tab id: `doc-processing`
- bottom-tab label: `处理`

This tab must be the fifth mobile bottom tab.

Approved mobile structure:

- `frontend-app/pages/doc-processing/DocProcessingPage.tsx`
- `frontend-app/features/doc-processing/components/DocProcessingMobileWorkbench.tsx`

## Mobile Module 1 Frontend Migration Matrix

| Old Source | New Target | Final Role |
|---|---|---|
| `module1/mobile/MobileComposer.tsx` | `frontend-app/features/doc-processing/components/MobileComposer.tsx` | mobile composer |
| `module1/mobile/MobileCurrentFileCard.tsx` | `frontend-app/features/doc-processing/components/MobileCurrentFileCard.tsx` | current file state |
| `module1/mobile/MobileFollowUpSuggestions.tsx` | `frontend-app/features/doc-processing/components/MobileFollowUpSuggestions.tsx` | follow-up actions |
| `module1/mobile/MobileMessageList.tsx` | `frontend-app/features/doc-processing/components/MobileMessageList.tsx` | message thread |
| `module1/mobile/MobilePreviewPage.tsx` | `frontend-app/features/doc-processing/components/MobilePreviewPage.tsx` | full-screen preview |
| `module1/mobile/MobileReportPage.tsx` | `frontend-app/features/doc-processing/components/MobileReportPage.tsx` | report view |
| `module1/mobile/MobileUtilityDrawer.tsx` | `frontend-app/features/doc-processing/components/MobileUtilityDrawer.tsx` | mobile utility drawer |

## Mobile Module 1 Client Contract

Create one authoritative client:

- `frontend-app/shared/api/module1.ts`

Rules:

- all Module 1 mobile code must call this client
- no mobile component may rely on old workbench-side fetch code
- the mobile page must not continue using old `deepread_interaction` semantics as formal ownership

## Platform Assistant Frontend Design

Approved web frontend files:

- `frontend/features/platform-assistant/components/PlatformAssistant.tsx`
- `frontend/features/platform-assistant/lib/assistantContext.ts`
- `frontend/features/platform-assistant/lib/platformAssistant.ts`

Approved mobile frontend files:

- `frontend-app/features/platform-assistant/components/PlatformAssistant.tsx`
- `frontend-app/features/platform-assistant/lib/assistantContext.ts`
- `frontend-app/features/platform-assistant/lib/platformAssistant.ts`

Responsibilities:

- `PlatformAssistant.tsx`: UI, message rendering, open or close behavior, card interactions
- `assistantContext.ts`: convert current page state into `AssistantContextEnvelope`
- `platformAssistant.ts`: call `bootstrap` and `chat` endpoints

The old global assistant frontend files must not remain as formal production ownership after cutover.

## Auth And Isolation Integration

Module 1 and the platform assistant must both integrate with the unified authentication and user-isolation model.

Required properties:

- Module 1 endpoints resolve authenticated user context
- platform assistant endpoints resolve authenticated user context
- assistant request context is scoped by current user
- runtime artifacts are written into user-scoped runtime paths
- logs can record at least `tenant_id`, `user_id`, `session_id`, and `request_id`
- no cross-user conversation or artifact reuse is allowed by design

This is required for:

- correctness
- production-style user isolation
- auditability
- future workspace and conversation-history features

## Navigation And Registry Cutover

The actual cutover happens in four places:

- backend module registry
- web app tab registry and page rendering
- web sidebar navigation
- mobile app bottom-tab navigation

Approved cutover actions:

1. register formal `module1` in the unified backend module registry
2. register formal `platform_assistant` in the unified backend module registry
3. replace web `AI文档处理` placeholder routing with `doc-processing`
4. add mobile fifth bottom tab `处理` with id `doc-processing`
5. switch root assistant mounting from old assistant files to the new platform-assistant feature
6. remove `deepread_interaction` from formal product identity

## Deletion Plan

The following files and directories are not allowed to remain as formal architecture after migration cutover.

### Old Frontend Placeholder And Workbench Files

- `frontend/pages/module1-placeholder/Module1PlaceholderPage.tsx`
- `frontend-app/pages/module1-placeholder/Module1PlaceholderPage.tsx`
- `frontend/pages/deepread/DocInteractionWorkbench.tsx`
- `frontend-app/pages/deepread/DocInteractionWorkbench.tsx`

### Old Assistant Ownership Files

- `frontend/components/AIAssistant.tsx`
- `frontend-app/components/AIAssistant.tsx`
- `backend/app/modules/module2/api/endpoints/assistant.py`
- `backend/app/modules/module2/services/api/assistant_service.py`
- `backend/app/services/assistant_prompting.py`

### Old Root Source Packages

- `module1`
- `platform-usage-assistant`

Deletion rule:

- delete old files only after the new chain is complete and regression checks pass
- do not keep old files as compatibility shells in the final state

## Migration Sequence

The migration must be implemented in this sequence.

### Phase 1: Formal Skeleton Landing

Create the formal module and feature directories:

- `backend/app/modules/module1`
- `backend/app/modules/platform_assistant`
- `frontend/pages/doc-processing`
- `frontend/features/doc-processing`
- `frontend/features/platform-assistant`
- `frontend-app/pages/doc-processing`
- `frontend-app/features/doc-processing`
- `frontend-app/features/platform-assistant`

No formal cutover happens in this phase.

### Phase 2: Module 1 Backend Migration

Move and split Module 1 backend logic into formal module services and endpoints.

Success condition:

- Module 1 formal backend endpoints are callable through the unified backend

### Phase 3: Platform Assistant Backend FastAPI Migration

Move the assistant backend capability into `platform_assistant`.

Success condition:

- formal `health`, `bootstrap`, and `chat` endpoints exist
- FastAPI assistant streaming works through the new route surface

### Phase 4: Web And Mobile Frontend Migration

Move Module 1 web and mobile features into the new product-domain directories.
Move assistant UI and client code into the new platform-assistant feature directories.

Success condition:

- new Module 1 pages and new assistant frontends are functional using the new backend surfaces

### Phase 5: Registry And Navigation Cutover

Switch the formal product entrypoints and backend registration:

- backend registry
- web app tabs
- web sidebar
- mobile bottom tab
- root assistant mounting

Success condition:

- the live formal app uses the new architecture

### Phase 6: Old Chain Removal And Regression

Remove old files and old root source packages after the new chain is verified.

Success condition:

- no formal old path remains
- regression acceptance passes

## Regression Acceptance Matrix

At minimum, the following checks must pass.

### Module 1 Web

1. Web `AI文档处理` opens the real Module 1 page.
2. Web file upload works.
3. Web preview flows work.
4. Web document interaction and edit flows work.
5. Web save and export flows work.

### Module 1 Mobile

6. Mobile fifth bottom tab `处理` appears and opens correctly.
7. Mobile file upload works.
8. Mobile interaction flow works.
9. Mobile full-screen preview works.

### Platform Assistant

10. Web assistant opens and receives correct bootstrap starter data.
11. Mobile assistant opens and receives correct bootstrap starter data.
12. Assistant chat streams correctly on web and mobile.
13. Assistant context changes by page identity instead of staying locked to old Module 2 assumptions.

### Isolation And Integration

14. Authenticated context is available to Module 1 write flows.
15. Authenticated context is available to platform assistant requests.
16. User isolation remains intact.
17. Module 2, Module 3, and Module 4 formal functionality is not degraded by the migration.

## Risks And Mitigations

### Risk 1: Old API Roots Remain In Module 1 Frontend Code

Mitigation:

- use one authoritative `shared/api/module1.ts` client per frontend
- remove inline base URL logic from components

### Risk 2: Platform Assistant Remains Secretly Coupled To Module 2 Context

Mitigation:

- require explicit `AssistantContextEnvelope`
- treat module-specific stores as page-level inputs, not assistant-owned global truth

### Risk 3: Mobile And Web Product Identity Drift Again

Mitigation:

- keep one formal id: `doc-processing`
- map display labels separately for web and mobile only

### Risk 4: Backend Registry Changes Before Formal Modules Are Ready

Mitigation:

- land module skeletons and runtime first
- cut registry only after the new surfaces are functional

### Risk 5: Old Files Are Deleted Too Early

Mitigation:

- delete only after new chain regression passes
- keep deletion as the final phase, not the opening phase

## Final Acceptance Criteria

This migration is complete only when all of the following are true:

- a formal `backend/app/modules/module1` exists and is the real Module 1 backend
- a formal `backend/app/modules/platform_assistant` exists and is the real assistant backend
- web `AI文档处理` points to `doc-processing`
- mobile has a fifth bottom tab named `处理`
- the platform assistant backend no longer depends on the old Node or Express service
- the platform assistant no longer depends on implicit Module 2-only localStorage semantics as its formal context model
- `deepread_interaction` no longer remains as the formal Module 1 identity
- old placeholder pages, old workbench page entry files, old assistant ownership files, and old root source packages are removed from the final architecture

## Implementation Readiness

This spec is considered ready for implementation planning because it now defines:

- the final architecture
- the approved naming model
- the backend and frontend directory targets
- module responsibility boundaries
- formal API surfaces
- assistant context and streaming contracts
- migration mappings
- cutover rules
- deletion rules
- regression gates

No compatibility route is part of the final architecture described by this spec.
