# Live Workflow Regression Entrypoints

Date: 2026-03-29

## Purpose

This note records the current live regression entrypoints that align with the unified FastAPI backend direction.

The main rule is:

- prefer the unified backend gateway on port `3001`
- keep the frontend on port `3000`
- treat `8000`, `8100`, and `3003` as internal engine or compatibility ports, not public frontend targets
- use the existing Playwright live scenarios through top-level scripts instead of manually remembering individual file paths

## Default Runtime Assumptions

- frontend app: `http://127.0.0.1:3000`
- unified FastAPI backend gateway: `http://127.0.0.1:3001`

Module2 frontend regression scripts now prefer the unified backend by default instead of the older `8000` or `8001` assumptions.
Frontend runtime address discovery now also stays on the unified gateway path by default. If you need a one-off direct upstream debug session, use the explicit override env or localStorage settings instead of relying on automatic `8000` probing.

## Root Entrypoints

From the repository root:

- `npm run wait:gateway`
  - waits for `/gateway/ready`
- `npm run qa:module2:frontend`
  - runs the main Module2 frontend live extraction regression
- `npm run qa:module2:assistant`
  - runs the Module2 assistant streaming live regression
- `npm run qa:module2:trace`
  - runs the Module2 trace-panel regression
- `npm run qa:module4:live`
  - runs the Module4 live multi-document graph regression
- `npm run qa:live:workflow:smoke`
  - runs a faster smoke version of the unified live workflow sequence:
    - wait for gateway
    - one-round Module2 frontend extraction regression
    - Module2 trace regression
    - Module2 assistant regression
    - Module4 live graph regression
- `npm run qa:live:workflow`
  - runs the current unified live workflow sequence:
    - wait for gateway
    - Module2 frontend extraction regression
    - Module2 assistant regression
    - Module4 live graph regression

## Frontend Entrypoints

From `frontend/` directly:

- `npm run module2:frontend-realistic`
- `npm run module2:assistant-check`
- `npm run module2:trace-regression`
- `npm run module4:frontend-check`
- `npm run module4:live-multidoc`

## Key Environment Variables

Useful overrides:

- `MODULE2_APP_URL`
- `MODULE2_API_BASE_OVERRIDE`
- `MODULE2_API_BASE`
- `MODULE2_EXTRACT_URL`
- `MODULE2_TRACE_URL`
- `MODULE4_API_BASE`
- `MODULE4_TENANT`
- `PLAYWRIGHT_EXECUTABLE_PATH`
- `MODULE2_PLAYWRIGHT_EXECUTABLE_PATH`
- `MODULE4_PLAYWRIGHT_EXECUTABLE_PATH`

## Practical Usage Order

Recommended local execution order:

1. start the unified backend and frontend
2. run `npm run wait:gateway`
3. run `npm run qa:module2:frontend`
4. run `npm run qa:module2:assistant`
5. run `npm run qa:module4:live`

If you want a single command, use:

- `npm run qa:live:workflow:smoke`
- `npm run qa:live:workflow`

## Scope Note

These commands are the current live regression entrypoints.
They are not yet the final full acceptance closure for the entire product.

The final acceptance target remains:

- auth
- upload
- DOCX to PDF path
- PDF parse path
- MinerU artifacts
- Gemini-enhanced figure or chart understanding
- summarize and trace
- assistant grounded answers
- Module2 to Module4 sync
- Module4 graph usage

This document only ensures the regression entrypoints are now aligned with the unified backend direction.
