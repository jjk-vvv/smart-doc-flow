# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Smart Doc Flow** is a unified FastAPI + React + Electron monorepo providing an intelligent document processing platform with extraction, AI assistant, and knowledge graph visualization.

## Development Commands

### Starting the Application

```bash
npm run dev              # FastAPI backend + Vite frontend (recommended)
npm run dev:backend      # Backend only (FastAPI gateway)
npm run dev:frontend     # Frontend Vite dev server only (port 3000)
npm run dev:module2      # Module 2 extraction service only
npm run dev:module4      # Module 4 knowledge graph service only
npm run start            # Production FastAPI startup
```

`npm run dev` defaults `MODULE2_ENABLED=0` and `MODULE4_ENABLED=0` — extraction and graph routes attach through managed sidecars, not separate processes.

### Desktop App

```bash
npm run desktop:dev      # Electron with dev servers
npm run desktop:local    # Build + launch Electron with backend (closest to packaged behavior)
npm run desktop:pack     # Package app (no signing)
npm run desktop:dist     # Create Windows installer
npm run desktop:doctor   # Check desktop prerequisites
npm run desktop:smoke    # Validate packaged output
```

### Testing

```bash
# Backend (from repo root)
python -m pytest                              # All tests
python -m pytest backend/tests/test_foo.py   # Single test file
python -m pytest -k "test_name"              # Single test by name

# Install test dependencies first if needed:
pip install -r backend/requirements-dev.txt

# Frontend E2E (requires running backend)
npm run qa:module2:frontend        # Deep read frontend regression
npm run qa:module2:assistant       # Assistant streaming check
npm run qa:module2:trace           # Trace/extraction regression
npm run qa:module4:live            # Knowledge graph multi-doc
npm run qa:live:workflow           # Full workflow (waits for gateway first)
npm run qa:live:workflow:smoke     # Minimal smoke test
```

### Running Python Services Directly (without Node)

```bash
python backend/run_service.py backend   # Unified gateway (port 3001)
python backend/run_service.py module2   # Extraction sidecar (port 8010)
python backend/run_service.py module4   # Knowledge graph sidecar (port 8100)
python backend/run_service.py backend --reload   # With hot reload
```

`run_service.py` auto-selects the correct Python venv: `.venv-module4-py311` for module4, `.venv-module2-py311` or `.venv` for everything else.

### Frontend Build

```bash
npm run build            # Build frontend to frontend/dist/
```

## Architecture

### Three-Tier Structure and Port Contract

```
Frontend (React/Vite :3000)
    ↓ HTTP/JSON
Backend Gateway (FastAPI :3001)  ← Primary unified entry point
    ↓ HTTP/Subprocess (managed sidecars)
  Module 2 (Extraction :8010)
  Module 4 (Knowledge Graph :8100)
  Auth Compat Proxy :3003 (legacy, optional)
```

Frontend code should always target `:3001`. Ports `3003`, `8010`, and `8100` are internal sidecar ports — not for direct frontend use.

### Backend (`backend/app/`)

The FastAPI application is created in `create_app.py` and mounts six feature modules as routers:

| Module path | Responsibility |
|---|---|
| `modules/auth/` | Register, login, logout, JWT validation |
| `modules/assistant/` | Streaming AI chat (configurable LLM provider) |
| `modules/extraction/` | Document parse jobs, artifact storage, summaries |
| `modules/gateway/` | Health/readiness checks, upstream proxy routing |
| `modules/module1_placeholder/` | Extensible module shell page |
| `modules/frontend_static/` | Serves `frontend/dist/` in production |

**Sidecar management**: Module 2 and Module 4 run as managed sidecars — spawned and monitored by the gateway. Controlled via env vars:
- `UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE` — `auto` (default), `managed`, `disabled`
- `UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE` — `auto` (default), `managed`, `disabled`

**Legacy directories** — do not treat as primary:
- `backend/auth/` — compatibility proxy only, keeps historical entrypoints alive on port `3003`
- `backend/app/modules/module2/` — specialized extraction upstream (attached via sidecar in normal mode)
- `backend/module4/` — specialized graph upstream (attached via sidecar in normal mode); preferred venv is repo-root `.venv-module4-py311`

### Frontend (`frontend/`)

`App.tsx` is the root component with tab-based navigation. Key feature areas:

| Component | Purpose |
|---|---|
| `Dashboard` | Upload hub, extraction job status |
| `DeepReadWorkbench` | Document viewer + extracted results |
| `AIAssistant` | Streaming multi-turn chat |
| `KnowledgeNexus` | Neo4j graph visualization |
| `FusionGrid` | Multi-document analysis |

Vite proxies `/api`, `/extract`, `/module4`, `/gateway` to the backend (default `http://localhost:3001`). Override with `VITE_BACKEND_ENTRY_URL`.

### Electron (`electron/main.cjs`)

Spawns the FastAPI process, resolves the gateway URL, creates a `BrowserWindow`, and manages the full app lifecycle. In packaged runtime, `SMART_DOC_FLOW_DATA_ROOT` defaults to Electron `userData/runtime-data` so auth data, extraction artifacts, and caches go to a user-writable location rather than the packaged resources.

## Configuration

Copy `backend/.env.example` to `backend/.env` and set values. Key variable groups:

- `GATEWAY_HOST/PORT/CORS_ORIGINS` — Server binding
- `AUTH_*` — JWT secret, token expiry, bcrypt rounds, SMS/SMTP
- `ASSISTANT1_*` — LLM provider, model, temperature, streaming
- `MODULE2_*` — Upstream URL, file size limits, job TTLs, LibreOffice path
- `MODULE4_*` — Graph upstream URL
- `AUTH_COMPAT_ENABLED` — Set `0` (default) unless legacy compat needed

## Test Layout

All backend tests live in `backend/tests/`. pytest is configured via `pytest.ini` (test path: `backend/tests`, pattern: `test_*.py`). `conftest.py` provides shared fixtures.

E2E frontend tests use Playwright and are driven by `npm run qa:*` scripts.

## Ops / Maintenance Scripts

```bash
npm run ops:normalize-layout              # Normalize runtime directory layout
npm run ops:clean-backend-runtime-dirs    # Clean backend runtime working dirs
```

## Design Context

Smart Doc Flow is a professional document-intelligence workspace for human operators working with AI — not a casual consumer chat product. See `.impeccable.md` for the full design brief. Key directives:

- **Document-first**: every interaction should help users inspect source material, extracted structure, and evidence
- **Aesthetic**: professional analysis workbench with blue-slate structural base, high information density, and restrained accent colors — avoid trendy AI demo UI, neon sci-fi dashboards, or glass-heavy templates
- **Tone**: calm confidence, evidence-aware, technically fluent — not playful or over-marketed

## Tech Stack Summary

- **Backend**: FastAPI 0.116+, Pydantic 2, Uvicorn, PyJWT, bcrypt
- **Frontend**: React 19, TypeScript 5.8, Vite 6, Tailwind CSS 4, Vercel AI SDK, Three.js, Neo4j NVL, PDF.js, Recharts
- **Desktop**: Electron 41, electron-builder (Windows NSIS target)
- **Tests**: pytest + httpx (backend), Playwright (frontend E2E)
