# Module1 And Platform Assistant Hard-Cut Migration Status

Date: 2026-04-17

Status: in-progress

## Purpose

This document records the repository truth for the hard-cut migration of:

- Module 1 document processing
- the platform-wide global assistant

It replaces the earlier design draft that still described removed paths and standalone runtimes.

## Repository Truth

### Landed and live

- Module 1 backend now lives under `backend/app/modules/module1`.
- Platform assistant backend now lives under `backend/app/modules/platform_assistant`.
- Web Module 1 entry now uses `frontend/pages/doc-processing/DocProcessingWorkbench.tsx`.
- Mobile Module 1 entry now uses `frontend-app/pages/doc-processing/DocProcessingWorkbench.tsx`.
- Web platform assistant now uses `frontend/features/platform-assistant/components/PlatformAssistant.tsx`.
- Mobile platform assistant now uses `frontend-app/features/platform-assistant/components/PlatformAssistant.tsx`.
- The old root-level external `module1/` source package has been removed from the repository.
- The old web and mobile `DocInteractionWorkbench` formal entry files have been removed.
- Platform assistant context shaping is now extracted into dedicated `assistantContext.ts` files on both web and mobile.
- Module 1 domain dataclasses are now owned by `backend/app/modules/module1/domain/models.py`.

### Removed in this migration line

- standalone root `module1/`
- `frontend/pages/deepread/DocInteractionWorkbench.tsx`
- `frontend-app/pages/deepread/DocInteractionWorkbench.tsx`
- `platform-usage-assistant/`
- `backend/app/modules/module1/models/*`
- `backend/app/modules/module1/services/style_service.py`
- `backend/app/modules/module1/schemas/api_schemas.py`

## Current Live Structure

### Backend

```text
backend/app/modules/
  module1/
    composition.py
    main.py
    api/
      router.py
      endpoints/
        health.py
        workbench.py
    core/
      config.py
    domain/
      __init__.py
      models.py
    schemas/
      __init__.py
      workbench.py
    services/
      agent_service.py
      conversion_service.py
      document_service.py
      modification_service.py
      preview_service.py
      sandbox_service.py
      save_service.py
      stream_service.py
      upload_service.py
    tests/

  platform_assistant/
    composition.py
    api/
      router.py
      endpoints/
        health.py
        bootstrap.py
        chat.py
    data/
      page_configs.py
      platform_facts.py
    schemas/
      chat.py
    services/
      chat_service.py
      context_service.py
      guidance_service.py
      prompt_service.py
```

### Web frontend

```text
frontend/
  pages/
    doc-processing/
      DocProcessingWorkbench.tsx
      LuckysheetPreview.tsx
      ReportSelectionToolbar.tsx
      lib/
        reportFormatting.js
        reportQuickEdit.ts
        reportRichFormatting.ts
        reportSelection.ts
  features/
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

### Mobile frontend

```text
frontend-app/
  pages/
    doc-processing/
      DocProcessingWorkbench.tsx
      LuckysheetPreview.tsx
      ReportSelectionToolbar.tsx
      lib/
        reportFormatting.js
        reportQuickEdit.ts
        reportRichFormatting.ts
        reportSelection.ts
      mobile/
        MobileComposer.tsx
        MobileCurrentFileCard.tsx
        MobileFollowUpSuggestions.tsx
        MobileMessageList.tsx
        MobilePreviewPage.tsx
        MobileReportPage.tsx
        MobileUtilityDrawer.tsx
  features/
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

## What Is Complete

### Product identity

- `doc-processing` is now the formal Module 1 product identity on both web and mobile.
- Platform assistant is now a platform-level feature and no longer mounted through the old assistant surface.

### Runtime ownership

- Platform assistant runtime is formally owned by FastAPI under `backend/app/modules/platform_assistant`.
- Module 1 runtime is formally owned by FastAPI under `backend/app/modules/module1`.

### Source ownership cleanup

- Root-level external Module 1 source ownership has been removed.
- Dead schema and style placeholder files inside Module 1 have been removed.
- Domain dataclasses have moved out of a legacy `models/` package into `domain/`.

## What Is Still Intermediate

### Module 1 backend service purity

Module 1 is not yet fully structurally pure even though it is functionally live.

Current issue:

- `document_service.py` still contains the real implementation for health, preview conversion, save, modification, and stream flows.
- `preview_service.py`, `save_service.py`, `modification_service.py`, and `stream_service.py` are still thin delegating shells around that monolith.

Implication:

- the router and service boundaries look correct from the outside
- the internal business logic split is not yet finished

### Module 1 frontend internal placement

The route identity is correct, but the web and mobile Module 1 workbench implementation still lives directly under `pages/doc-processing`.

This is acceptable for the live product route, but it means the UI is not yet fully extracted into a dedicated reusable feature package.

### Historical docs

Older design and migration documents still mention:

- old assistant files
- old workbench identities
- removed external `module1` paths
- old Node assistant runtime

These files are documentation debt, not runtime debt.

## No-Compatibility Rules

The migration continues under these hard-cut rules:

- no revival of the removed root `module1/` package
- no reintroduction of old `DocInteractionWorkbench` product entry files
- no reintroduction of Node or Express assistant runtime ownership
- no permanent alias routes for old assistant ownership
- no new code may import removed Module 1 model or schema packages

## Remaining Migration Work

### Stage 1: finish Module 1 service split

Goal:

- move real capability code out of `document_service.py`

Required landing:

- preview logic owned by `preview_service.py`
- save logic owned by `save_service.py`
- modification logic owned by `modification_service.py`
- stream orchestration owned by `stream_service.py`
- upload lifecycle helpers owned by `upload_service.py` and `sandbox_service.py`
- health response logic moved out of `document_service.py`

Acceptance:

- no active router or service entry imports `handle_*` functions from `document_service.py`
- `document_service.py` is deleted or reduced to strictly internal helper utilities with a new name

### Stage 2: align tests to final ownership

Goal:

- stop testing the legacy monolith as the public entry surface

Required landing:

- update tests to target focused services and endpoint behavior
- keep route registration coverage in unified backend tests

### Stage 3: optional frontend feature extraction

Goal:

- extract reusable Module 1 UI internals without changing the live `doc-processing` route identity

Required landing:

- move workbench internals under `features/doc-processing`
- keep `pages/doc-processing` as route entry only

This is an internal organization improvement, not a compatibility layer.

### Stage 4: documentation cleanup

Goal:

- remove or rewrite stale migration docs that still describe deleted runtime chains

## Stability Guardrails

Every remaining migration slice must preserve:

- Module 1 upload, preview, chat, modification, and save behavior
- platform assistant bootstrap and chat behavior
- unified backend router registration
- existing auth and tenant isolation integration points

## Verification Baseline

The current migration line should continue to be validated with:

- `npm run build` in `frontend`
- `npm run build` in `frontend-app`
- `pytest backend/app/modules/module1/tests/test_conversion_service.py backend/app/modules/module1/tests/test_document_service.py backend/tests/test_create_app_routes.py`

## Short Reflection

The migration is already successful at the runtime ownership layer:

- the live app no longer depends on the old external Module 1 package
- the live app no longer depends on the old standalone assistant runtime

The remaining work is structural purification inside Module 1 itself:

- the public boundaries are now mostly correct
- the internal service decomposition is not yet complete

That means the next safe path is not another large product rewrite.
The next safe path is to keep cutting the `document_service.py` monolith into the focused service files that already exist, while preserving behavior and test coverage.
