Unified backend overview for Smart Doc Flow.

Authoritative backend framework:

- FastAPI is the primary backend framework.
- The main app entrypoint is `backend/app/main.py`.
- The application factory is `backend/app/create_app.py`.

Current backend topology:

- `backend/app/`
  - unified FastAPI gateway and business modules
  - this is the long-term primary backend architecture
- `backend/shared/`
  - shared contracts and cross-service primitives
  - contains `contracts`, `tenancy`, `security`, `exceptions`, `logging`, `utils`
- `backend/auth/`
  - compatibility proxy only
  - keeps historical auth/chat entrypoints alive on port `3003`
  - should not be treated as the main backend anymore
- `backend/compat/auth_proxy/`
  - canonical target location for the legacy auth compatibility layer
  - current startup still points at `backend/auth` during migration compatibility
- `backend/app/modules/module2/`
  - specialized extraction/assistant runtime under the unified FastAPI module tree
  - in FastAPI-first mode this runtime is attached by the unified backend through the extraction sidecar manager unless `MODULE2_ENABLED=1` is explicitly restored
- `backend/app/modules/module4/`
  - specialized graph/runtime upstream
  - in FastAPI-first mode this runtime is now expected to be attached by the unified gateway through the Module 4 sidecar manager unless `MODULE4_ENABLED=1` is explicitly restored
  - preferred Python runtime is now the repo-root `.venv-module4-py311`
  - legacy standalone `backend/module4` layout has been removed from the project layout

Recommended runtime entrypoints:

- `npm run dev`
  - canonical full-stack dev entry
  - FastAPI-first mode without auth compat by default
  - defaults `MODULE2_ENABLED=0` and `MODULE4_ENABLED=0`, so unified FastAPI is the only backend entry
  - extraction jobs attach to the managed Module 2 sidecar path instead of requiring a separately booted `module2` process
  - graph routes attach to the managed Module 4 sidecar path instead of requiring a separately booted `module4` process
- `npm run dev:fastapi`
  - FastAPI-first mode without auth compat
  - defaults `MODULE2_ENABLED=0` and `MODULE4_ENABLED=0`, so unified FastAPI is the only backend entry
  - extraction jobs attach to the managed Module 2 sidecar path instead of requiring a separately booted `module2` process
  - graph routes attach to the managed Module 4 sidecar path instead of requiring a separately booted `module4` process
- `npm run dev:compat`
  - compatibility-oriented full-stack dev entry
  - restores auth compat plus standalone module2/module4 startup for old debugging flows
- `npm run start`
  - canonical production-style backend startup
  - FastAPI-first single-entry topology by default
- `npm run start:fastapi`
  - production-style FastAPI-only backend startup
  - defaults `MODULE2_ENABLED=0` and `MODULE4_ENABLED=0`, matching the single-entry runtime expected by desktop packaging
- `npm run start:compat`
  - compatibility-oriented production-style backend startup
  - restores the historical auth compat and standalone module startup shape

Public port contract:

- frontend public entry: `3000`
- frontend-app public entry: `3002`
- unified FastAPI backend public entry: `3001`
- `3003`, `8010`, `8001`, and `8100` are internal compatibility or sidecar ports
- frontend code should target `3001` by default and only reach older upstream ports through explicit developer overrides

Desktop runtime entrypoints:

- `npm run desktop:dev`
  - starts FastAPI-first backend plus Vite dev server, then launches Electron
  - Electron uses the frontend dev server as renderer and keeps backend startup outside the main process
- `npm run desktop:local`
  - builds the frontend, starts FastAPI-first backend, then launches Electron against the local gateway
  - this is the closest source-tree rehearsal for packaged desktop behavior
- `npm run desktop:doctor`
  - checks the source-tree desktop prerequisites
  - if you want to validate a packaged output directory, set `DESKTOP_DOCTOR_OUTPUT_DIR=dist-electron-rebuild4` or another output folder before running it
- packaged Electron runtime
  - `electron/main.cjs` now manages FastAPI startup internally by default
  - default behavior is `AUTH_COMPAT_ENABLED=0`, `MODULE2_ENABLED=0`, `UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE=managed`, and `UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE=managed`
  - unified FastAPI becomes the single desktop backend entry, while extraction jobs and graph routes still preserve the original Module 2 and Module 4 runtime semantics through their managed sidecars
  - packaged desktop runtime now defaults `SMART_DOC_FLOW_DATA_ROOT` to Electron `userData/runtime-data`, so newly generated auth data, extraction artifacts, caches, and module4 workspaces are written into a user-writable data directory instead of the packaged app resources
  - runtime history folders such as `module2/artifacts` and `module4/workspaces` are intentionally excluded from packaging, so historical trace images and workspace outputs from the source tree are not baked into the desktop app
  - `SMART_DOC_FLOW_ELECTRON_LOG_FILE` can be used to persist Electron main-process startup logs during packaging smoke tests
  - `desktop:doctor` now also checks that the packaged Module 4 Python runtime exists and can import `graphrag`
  - `desktop:smoke` now probes `/module4/healthz` after gateway readiness so packaged graph runtime failures surface early

Testing:

- install dev test tooling: `python -m pip install -r backend/requirements-dev.txt`
- run unified FastAPI tests: `python -m pytest`

Configuration layering:

- `backend/.env`
  - recommended authoritative config for the unified FastAPI backend
- `backend/auth/.env`
  - compat proxy specific config
- `backend/app/modules/module2/.env`
  - module2 advanced upstream config
- `backend/app/modules/module4/.env`
  - module4 advanced upstream config

FastAPI-first extraction sidecar controls:

- `UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE=auto`
  - default safe mode
  - unified backend auto-attaches to an existing local `module2`, or starts one on demand for extraction job routes
- `UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE=managed`
  - recommended for packaging validation and single-entry desktop runtime
  - unified backend eagerly ensures the managed `module2` process during startup and treats startup failure as fatal
- `UNIFIED_EXTRACT_MODULE2_SIDECAR_MODE=disabled`
  - opt-out mode if you explicitly want to manage `module2` yourself
- `MODULE2_ENABLED=1`
  - optional override to restore the old separate `module2` startup behavior in `dev:fastapi` or `start:fastapi`

FastAPI-first graph sidecar controls:

- `UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE=auto`
  - default safe mode for direct Python/test execution
  - unified gateway auto-attaches to an existing local `module4`, or starts one when proxied graph routes require it
- `UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE=managed`
  - recommended for unified dev startup, packaged desktop runtime, and production-style single-entry startup
  - unified gateway eagerly ensures the managed `module4` process during startup and treats startup failure as fatal
- `UNIFIED_GATEWAY_MODULE4_SIDECAR_MODE=disabled`
  - opt-out mode if you explicitly want to manage `module4` yourself
- `MODULE4_ENABLED=1`
  - optional override to restore the old separate `module4` startup behavior in `dev:fastapi` or `start:fastapi`

Runtime env loading is now scope-aware:

- FastAPI gateway loads `backend/.env` first-class, plus Module 2 env, plus a
  narrow auth legacy fallback for transitional auth keys only
- for the FastAPI gateway, `backend/.env` is now later in precedence than the
  fallback scopes, so overlapping keys in `backend/.env` win
- auth compat loads `backend/.env` plus `backend/auth/.env`
- module2 loads `backend/.env` plus `backend/app/modules/module2/.env`
- module4 loads `backend/.env` plus `backend/app/modules/module4/.env`
- module4 startup now resolves directly to the repo-root `.venv-module4-py311`

Data/storage direction:

- runtime-generated auth data should live under the managed runtime/data root
- legacy `backend/auth/users.json` is kept only for safe migration fallback
- the FastAPI auth module now migrates legacy users into the managed storage path automatically

FastAPI module structure:

- `backend/app/modules/auth/`
  - standardized layering (`api/services/repositories/schemas/domain`) with
    compatibility adapters to existing auth implementation
- `backend/app/modules/module1/`
  - standardized layering plus compatibility bridge to current placeholder path
- `backend/app/modules/module2/`
  - standardized layering (`api/services/repositories/schemas/domain/core/integrations/resources`)
    wrapping existing extraction + assistant routes
- `backend/app/modules/module3/`
  - standardized layering (`api/services/repositories/schemas/models/domain/core`)
    wrapping module3 FastAPI routes
  - controlled by `UNIFIED_GATEWAY_MODULE3_ROUTER_MODE` (`auto` / `disabled` / `required`)
- `backend/app/modules/module4/`
  - standardized layering (`api/services/repositories/schemas/domain/core/integrations/resources`)
    wrapping current gateway/module4 integration path
- `backend/app/modules/frontend_static/`
  - packaged frontend static asset serving
- legacy adapters retained during migration:
  - `backend/app/modules/assistant/`
  - `backend/app/modules/extraction/`
  - `backend/app/modules/gateway/`
  - `backend/app/modules/module1_placeholder/`

Unified route assembly:

- `backend/app/factory.py`
  - canonical FastAPI app factory (`create_app`)
- `backend/app/create_app.py`
  - compatibility import shim that re-exports `create_app`
- `backend/app/modules/registry.py`
  - module-level router registration for API v1 assembly

Service-internal standard structure (migration target):

- `app/api/v1/endpoints`
  - HTTP routing layer only
- `app/services`
  - application orchestration/use-case layer
- `app/domain`
  - core domain rules and workflows
- `app/repositories`
  - data access abstraction layer
- `app/db`
  - database connection and persistence substrate
- `app/schemas`
  - API request/response models
- `app/integrations`
  - external systems and adapters
- `app/core`
  - settings, lifecycle, exceptions, middleware
- `app/resources`
  - static prompts/rules/templates
- `app/utils`
  - generic utility helpers
