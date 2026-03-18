# Module 4 Strict Downstream Sync Design

Date: 2026-03-18

## Goal

Turn Module 4 into a strict downstream graph service for Module 2.

After this change:

- Users upload files only in Module 2.
- Module 2 parses files and produces structured `documents`.
- Module 2 automatically syncs `documents` to Module 4.
- Module 4 no longer accepts file uploads.
- Module 4 no longer uses fallback, partial-success, or memory-degraded mainline behavior.
- Module 4 frontend displays only real Module 4 state.

## Current Problems

The current implementation has two different ingest mainlines:

1. Document ingest from Module 2 structured outputs.
2. Upload ingest through Module 4 file normalization + GraphRAG.

These two paths create conflicting semantics:

- Module 4 still accepts uploads even though Module 2 is the real upload/parsing owner.
- Module 4 frontend still renders local fallback graphs from Module 2 state.
- Partial-success and degraded-memory behaviors blur the definition of success.
- Health and UI states mix strict readiness with fallback readiness.

## Target Architecture

### Formal Mainline

1. User uploads file in Module 2.
2. Module 2 completes parsing and extraction.
3. Module 2 writes one `document_batch` outbox entry.
4. Module 2 delivers `documents` to `POST /module4/ingest`.
5. Module 4 processes `documents` into graph nodes, edges, evidence, and alerts.
6. Module 4 stores graph state and exposes it to the frontend.
7. Module 4 frontend renders only Module 4 persisted state.

### Removed From Mainline

- Module 2 upload-to-Module-4 sync payloads.
- Module 4 `/module4/sync/uploads`.
- Module 4 upload normalization path.
- Module 4 local frontend fallback graph rendering.
- Module 4 partial-success semantics.
- Module 4 degraded-memory runtime semantics.

## State Model

### Module 2 -> Module 4 Sync Outbox

- `queued`
- `delivering`
- `delivered`
- `failed`

### Module 4 Graph File Status

- `queued`
- `processing_documents`
- `ready`
- `failed`

The following states are not part of the new mainline:

- `normalizing_inputs`
- `validating_runtime`
- `indexing`
- `importing_graph`
- `partial`
- `degraded`
- `local-fallback`

## API Contract

### Module 2 -> Module 4 Request

`POST /module4/ingest`

Allowed payload:

```json
{
  "tenant_id": "default",
  "source": "module2",
  "source_batch_key": "stable-batch-key",
  "documents": [ ... ]
}
```

Rejected payloads:

- any payload containing `uploads`
- any payload where `source != "module2"`
- empty `documents`

## Implementation Plan

### P0: Mainline Boundary

1. Enable Module 2 document sync by default.
2. Remove Module 2 upload sync path.
3. Restrict Module 4 ingest to document batches from Module 2 only.
4. Remove Module 4 upload sync endpoint from the formal API.

### P1: Remove Degraded Mainline Behavior

1. Remove local fallback rendering in Module 4 frontend.
2. Remove partial-success semantics from Module 4 mainline.
3. Stop treating degraded-memory mode as valid service behavior.

### P2: Simplify UI and Health Semantics

1. Render only real persisted Module 4 state.
2. Show processing / ready / failed states only.
3. Keep GraphRAG runtime information, if retained, as auxiliary diagnostics rather than readiness gating.

## File-Level Change List

### Module 2

- `backend/module2/.env.example`
- `backend/module2/.env`
- `backend/module2/app/main.py`

### Module 4

- `backend/module4/app/schemas.py`
- `backend/module4/app/main.py`
- `backend/module4/app/db/storage.py`
- `backend/module4/.env.example`
- `backend/module4/README.md`

### Frontend

- `frontend/components/knowledge-nexus/KnowledgeNexusNeo4j.tsx`
- `frontend/lib/module4Api.ts`

## Validation Plan

1. Verify Module 2 creates only `document_batch` outbox entries.
2. Verify Module 4 rejects upload-based ingest.
3. Verify Module 4 document ingest produces `processing_documents -> ready`.
4. Verify frontend no longer renders local fallback graphs.
5. Verify failure states are explicit and do not degrade into partial success.

## Notes

- Existing legacy GraphRAG upload code may remain temporarily as dead code during transition, but it must not remain reachable from the production path.
- Existing historical upload-based batches may fail rebuild after the contract change; this is acceptable as long as the failure is explicit and not silently degraded.
