# Backend Migration Map

This map tracks compatibility-preserving moves from legacy locations to the
standardized layered structure.

## Gateway

- Legacy routing source: `backend/app/modules/*/router.py`
- New API entry: `backend/app/api/v1/endpoints/*.py`
- App factory entry now mounts `app/api/v1/router.py`
- Unified backend endpoint modules now carry canonical route implementations:
  - `app/api/v1/endpoints/auth.py`
  - `app/api/v1/endpoints/assistant.py`
  - `app/api/v1/endpoints/extraction.py`
  - `app/api/v1/endpoints/gateway.py`
  - `app/api/v1/endpoints/frontend_static.py`
  - `app/api/v1/endpoints/module1_placeholder.py`
- Legacy module routers under `app/modules/*/router.py` are now compatibility
  adapters that delegate to `api/v1/endpoints/*`; `build_legacy_router()`
  emits `DeprecationWarning`.
- Canonical layered sources for unified gateway now live in:
  - `app/services/*`
  - `app/domain/*`
  - `app/repositories/*`
  - `app/core/*`
- Legacy service/schema/repository/storage paths under `app/modules/*`
  are compatibility module aliases (`sys.modules[__name__] = canonical_module`)
  so legacy imports and monkeypatch-based tests target canonical modules.
- Auth foundation internals now use core-layer canonical modules:
  - `app/core/auth_config.py`
  - `app/core/auth_security.py`
  - `app/core/auth_tenant.py`
  - `app/core/auth_notifier.py`
  with legacy `app/modules/auth/{config,security,tenant,notifier}.py`
  retained as compatibility aliases.
- Assistant foundation internals now use layered canonical modules:
  - `app/core/assistant_config.py`
  - `app/services/assistant_prompting.py`
  - `app/integrations/assistant_provider.py`
  with legacy `app/modules/assistant/{config,prompting,provider}.py`
  retained as compatibility aliases.
- `app/core/lifespan.py` now imports `get_auth_service` from canonical
  `app/services/auth_service.py` instead of legacy module path.
- Legacy package-level `router` exports from:
  - `app.modules.auth`
  - `app.modules.assistant`
  - `app.modules.extraction`
  remain available only for compatibility and now emit `DeprecationWarning`
  when accessed.

## Module2

- Legacy routing source: `backend/module2/app/routes/*.py`
- New API entry: `backend/module2/app/api/v1/endpoints/*.py`
- Runtime assembly now mounts `app/api/v1/router_bundle.py`
- HTTP orchestration canonical source is now `backend/module2/app/services/`:
  - `extraction_request_service.py`
  - `extraction_executor_service.py`
  - `office_preview_service.py`
  - `document_tools_service.py`
  - `extraction_job_service.py`
- Repository canonical source is now `backend/module2/app/repositories/`:
  - `runtime_state_repository.py`
  - `extraction_cache_repository.py`
  - `module4_sync_outbox_repository.py`
  - `bundle.py`
- Legacy runtime modules are now compatibility shims:
  - `runtime/extraction_requests.py`
  - `runtime/extraction_executor.py`
  - `runtime/office_preview.py`
  - `runtime/document_trace_runtime.py`
  - `runtime/extraction_jobs.py`
- Runtime HTTP bundle now wires service-layer implementations directly
  via `runtime/http_runtime_bundle.py`.
- Runtime internal service composition now imports canonical service modules
  directly (no longer via runtime wrappers) in:
  - `runtime/main_service_bundle.py`
  - `runtime/document_trace_hits_runtime.py`
  with `runtime/__init__.py` retained as compatibility export surface.
- `module2/app/composition/foundation.py` now provides canonical composition
  entrypoints for app assembly; `module2/app/bootstrap/foundation.py` remains
  a compatibility adapter.
- Foundation composition canonical source is now
  `module2/app/services/extraction/foundation_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/foundation_builder.py`.
- Entry orchestration canonical source is now
  `module2/app/services/extraction/entry_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/entry_builder.py` with canonical import
  surface `module2/app/bootstrap/entry.py`.
- Extraction orchestration canonical source is now
  `module2/app/services/extraction/extraction_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/extraction_builder.py` with canonical
  import surface `module2/app/bootstrap/extraction.py`.
- Service composition canonical source is now
  `module2/app/services/extraction/service_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/service_builder.py` with canonical import
  surface `module2/app/bootstrap/service.py`.
- Support/bootstrap-runtime canonical source is now
  `module2/app/services/extraction/support_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/support_builder.py` with canonical import
  surface `module2/app/bootstrap/support.py`.
- Document-io service canonical source is now
  `module2/app/services/extraction/document_io_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/document_io_builder.py` with canonical
  import surface `module2/app/bootstrap/document_io.py`.
- Platform service canonical source is now
  `module2/app/services/extraction/platform_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/platform_builder.py` with canonical import
  surface `module2/app/bootstrap/platform.py`.
- Policy service canonical source is now
  `module2/app/services/extraction/policy_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/policy_builder.py` with canonical import
  surface `module2/app/bootstrap/policy.py`.
- Geometry service canonical source is now
  `module2/app/services/extraction/geometry_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/geometry_builder.py` with canonical import
  surface `module2/app/bootstrap/geometry.py`.
- Progress service canonical source is now
  `module2/app/services/extraction/progress_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/progress_builder.py` with canonical import
  surface `module2/app/bootstrap/progress.py`.
- Quality service canonical source is now
  `module2/app/services/extraction/quality_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/quality_builder.py` with canonical import
  surface `module2/app/bootstrap/quality.py`.
- Nonpdf service canonical source is now
  `module2/app/services/extraction/nonpdf_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/nonpdf_builder.py` with canonical import
  surface `module2/app/bootstrap/nonpdf.py`.
- Quick-extract service canonical source is now
  `module2/app/services/extraction/quick_extract_builder.py`; bootstrap
  adapter remains at `module2/app/bootstrap/quick_extract_builder.py` with
  canonical import surface `module2/app/bootstrap/quick_extract.py`.
- Workflow orchestration canonical source is now
  `module2/app/services/extraction/workflow_builder.py`; runtime adapter
  remains at `module2/app/runtime/main_workflow_bundle.py`.
- Schema-primitives service canonical source is now
  `module2/app/services/schema/schema_primitives_builder.py`; bootstrap
  adapter remains at `module2/app/bootstrap/schema_primitives_builder.py`
  with canonical import surface `module2/app/bootstrap/schema_primitives.py`.
- Schema-pipeline service canonical source is now
  `module2/app/services/schema/schema_pipeline_builder.py`; bootstrap
  adapter remains at `module2/app/bootstrap/schema_pipeline_builder.py`
  with canonical import surface `module2/app/bootstrap/schema_pipeline.py`.
- Result-filter service canonical source is now
  `module2/app/services/schema/result_filter_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/result_filter_builder.py` with canonical
  import surface `module2/app/bootstrap/result_filter.py`.
- Schema-context service canonical source is now
  `module2/app/services/schema/schema_context_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/schema_context_builder.py` with canonical
  import surface `module2/app/bootstrap/schema_context.py`.
- Schema-fields service canonical source is now
  `module2/app/services/schema/schema_fields_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/schema_fields_builder.py` with canonical
  import surface `module2/app/bootstrap/schema_fields.py`.
- Schema-inference service canonical source is now
  `module2/app/services/schema/schema_inference_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/schema_inference_builder.py` with
  canonical import surface `module2/app/bootstrap/schema_inference.py`.
- Schema-llm service canonical source is now
  `module2/app/services/schema/schema_llm_builder.py`; bootstrap adapter
  remains at `module2/app/bootstrap/schema_llm_builder.py` with canonical
  import surface `module2/app/bootstrap/schema_llm.py`.
- Schema-semantics service canonical source is now
  `module2/app/services/schema/schema_semantics_builder.py`; bootstrap
  adapter remains at `module2/app/bootstrap/schema_semantics_builder.py`
  with canonical import surface `module2/app/bootstrap/schema_semantics.py`.
- Schema-selection service canonical source is now
  `module2/app/services/schema/schema_selection_builder.py`; bootstrap
  adapter remains at `module2/app/bootstrap/schema_selection_builder.py`
  with canonical import surface `module2/app/bootstrap/schema_selection.py`.
- Schema-resolution service canonical source is now
  `module2/app/services/schema/schema_resolution_builder.py`; bootstrap
  adapter remains at `module2/app/bootstrap/schema_resolution_builder.py`
  with canonical import surface `module2/app/bootstrap/schema_resolution.py`.
- `runtime/main_foundation_bundle.py` is now a compatibility shim that
  re-exports bootstrap foundation adapters (service-backed).
- `runtime/main_entry_bundle.py` is now a compatibility shim that
  re-exports bootstrap entry adapters (service-backed).
- `runtime/main_extraction_bundle.py` is now a compatibility shim that
  re-exports bootstrap extraction adapters (service-backed).
- `runtime/main_service_bundle.py` is now a compatibility shim that
  re-exports bootstrap service adapters (service-backed).
- `runtime/main_support_bundle.py` is now a compatibility shim that
  re-exports bootstrap support/bootstrap-runtime adapters (service-backed).
- `runtime/main_document_io_bundle.py` is now a compatibility shim that
  re-exports bootstrap document-io adapters (service-backed).
- `runtime/main_platform_bundle.py` is now a compatibility shim that
  re-exports bootstrap platform adapters (service-backed).
- `runtime/main_policy_bundle.py` is now a compatibility shim that
  re-exports bootstrap policy adapters (service-backed).
- `runtime/main_geometry_bundle.py` is now a compatibility shim that
  re-exports bootstrap geometry adapters (service-backed).
- `runtime/main_progress_bundle.py` is now a compatibility shim that
  re-exports bootstrap progress adapters (service-backed).
- `runtime/main_quality_bundle.py` is now a compatibility shim that
  re-exports bootstrap quality adapters (service-backed).
- `runtime/main_nonpdf_bundle.py` is now a compatibility shim that
  re-exports bootstrap nonpdf adapters (service-backed).
- `runtime/main_quick_extract_bundle.py` is now a compatibility shim that
  re-exports bootstrap quick-extract/value-guard adapters (service-backed).
- `runtime/main_schema_primitives_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-primitives/request/timeout builders.
- `runtime/main_schema_pipeline_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-pipeline adapters (service-backed).
- `runtime/main_result_filter_bundle.py` is now a compatibility shim that
  re-exports bootstrap result-filter adapters (service-backed).
- `runtime/main_schema_context_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-context adapters (service-backed).
- `runtime/main_schema_fields_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-fields adapters (service-backed).
- `runtime/main_schema_inference_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-inference adapters (service-backed).
- `runtime/main_schema_llm_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-llm adapters (service-backed).
- `runtime/main_schema_semantics_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-semantics adapters (service-backed).
- `runtime/main_schema_selection_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-selection adapters (service-backed).
- `runtime/main_schema_resolution_bundle.py` is now a compatibility shim that
  re-exports bootstrap schema-resolution adapters (service-backed).
- Extraction runtime logic fingerprint inputs now include the canonical
  `app/services/extraction/extraction_builder.py` source file and now track
  `app/services/extraction/service_builder.py` /
  `app/services/extraction/support_builder.py` /
  `app/services/extraction/document_io_builder.py` /
  `app/services/extraction/geometry_builder.py` /
  `app/services/extraction/progress_builder.py` /
  `app/services/extraction/quality_builder.py` /
  `app/services/extraction/quick_extract_builder.py` /
  `app/services/extraction/nonpdf_builder.py` /
  `app/services/schema/result_filter_builder.py` /
  `app/services/schema/schema_context_builder.py` /
  `app/services/schema/schema_fields_builder.py` /
  `app/services/schema/schema_inference_builder.py` /
  `app/services/schema/schema_llm_builder.py` /
  `app/services/schema/schema_pipeline_builder.py` /
  `app/services/schema/schema_primitives_builder.py` /
  `app/services/schema/schema_resolution_builder.py` /
  `app/services/schema/schema_selection_builder.py` /
  `app/services/schema/schema_semantics_builder.py`
  instead of legacy runtime service/quality/result-filter/schema-context/
  schema-fields/schema-inference/schema-llm/nonpdf/quick-extract/schema-pipeline/
  schema-primitives/schema-resolution/schema-selection/schema-semantics bundle
  paths.
- `runtime/__init__.py` keeps composition/bootstrap exports via lazy
  `__getattr__` forwarding to `composition/foundation.py`,
  `bootstrap/entry.py`, `bootstrap/service.py`, and `bootstrap/support.py`,
  preventing import-cycle regressions while preserving legacy symbol access.
- `module2/app/main.py` is now a standard FastAPI entrypoint that only exports
  `app` and `create_app` from `composition/application.py`.
- Module2 internal tests now import runtime handles directly from
  `app/composition/application.py` instead of `app/main.py`.
- Module2 local regression/e2e tool scripts now import `app` from
  `app/composition/application.py` instead of `app/main.py`.
- `runtime/__init__.py` now re-exports migrated symbols from canonical
  `services/*` modules (`document_tools_service`, `extraction_job_service`,
  `extraction_executor_service`, `extraction_request_service`,
  `office_preview_service`) so runtime wrappers are no longer on the primary
  import path.
- `app/api/v1/endpoints/*` now carries canonical route implementations.
- `app/routes/*` and `app/routes/router_bundle.py` are now compatibility
  adapters that delegate to `api/v1` and emit `DeprecationWarning`.
- Backend route regression tests now target `api/v1/endpoints/*` as primary
  surface, with a dedicated compatibility test for legacy `app/routes/*`.
- Backend runtime/service regression tests for document tools, extraction job,
  extraction request, executor, and office preview now load canonical
  `module2/app/services/*.py`; dedicated compatibility coverage remains in
  `backend/tests/test_module2_runtime_service_compat_shims.py`.
- Foundation/service wiring now prefers repository-layer methods for:
  - extraction cache query/save (`check_cache`, `find_recent_document_caches`, `save_extraction_result`)
  - module4 sync outbox read/write flows.
- App lifecycle/health/cache-clear wiring now prefers runtime-state repository methods
  (`connect`, `close`, `diagnostics`, `clear_runtime_cache`) with storage fallback kept
  only for compatibility.
- Canonical bootstrap path now passes repository dependencies directly, reducing
  explicit legacy `storage` passthrough in main assembly.
- Legacy constructor params that accept `storage` are now compatibility-only and
  emit `DeprecationWarning`; new code should pass `runtime_state_repository`
  / `outbox_repository` explicitly.
- `Module2MainFoundationBundle.storage` is now a compatibility property that emits
  `DeprecationWarning`; canonical access is
  `foundation_bundle.repository_bundle.legacy_storage`.
- `Module2RepositoryBundle.storage` is now a compatibility property that emits
  `DeprecationWarning`; canonical access is `repository_bundle.legacy_storage`.
- Repository-layer constructors now use `legacy_storage` as canonical parameter:
  - `RuntimeStateRepository(legacy_storage=...)`
  - `ExtractionCacheRepository(legacy_storage=...)`
  - `Module4SyncOutboxRepository(legacy_storage=...)`
  - `build_module2_repository_bundle(legacy_storage=...)`
  and accept `storage=...` only as compatibility input with `DeprecationWarning`.
- Runtime main-bundle shims now import canonical builders from
  `services/extraction/*_builder.py` and `services/schema/*_builder.py`
  (with `main_foundation_bundle.py` importing from `composition/foundation.py`)
  instead of importing through `bootstrap/*_builder.py`.
- Runtime package lazy exports in `runtime/__init__.py` now resolve entry,
  service, support, and schema-pipeline symbols from canonical
  `services/*`/`composition/*` modules rather than bootstrap surfaces.
- Sync-related canonical files are now concise and function-first:
  - `api/v1/endpoints/sync.py`
  - `routes/sync_router.py`
  - `runtime/sync_callback_bundle.py`
  while legacy `module4_sync*.py` files remain compatibility wrappers.
- Bootstrap non-builder surfaces (`bootstrap/*.py`, excluding `*_builder.py`)
  now import canonical `services/*` (and `composition/foundation.py` for
  foundation) directly rather than re-exporting through local bootstrap
  builder modules.

- Legacy orchestration modules remain in:
  - `backend/module2/app/runtime/`
  - `backend/module2/app/core/`
  - `backend/module2/app/assistant_1/`
- Standardized compatibility exports now available from:
  - `backend/module2/app/services/`
  - `backend/module2/app/repositories/`
  - `backend/module2/app/integrations/`
  - `backend/module2/app/resources/`

## Module4

- Legacy routing source: `backend/module4/app/router.py`
- New API entry: `backend/module4/app/api/v1/endpoints/module4.py`
- Main app now mounts `app/api/v1/router.py`
- Main composition entry now uses `module4/app/composition/runtime.py`
  as canonical runtime assembly surface.
- `module4/app/api/v1/endpoints/module4.py` now carries canonical route
  implementations.
- `module4/app/api/v1/router.py` now wires directly to
  `api/v1/endpoints/graph.build_router` (with `endpoints/module4.py` retained
  as a compatibility surface), avoiding any fallback through legacy
  `app/router.py`.
- `module4/app/router.py` is now a compatibility adapter that delegates to
  the `api/v1` endpoint and emits `DeprecationWarning`.
- `module4/app/main.py` is now a standard FastAPI entrypoint that only exports
  `app` and `create_app` from `composition/application.py`.
- Module4 internal tests/tools now import runtime hooks directly from
  `app/composition/application.py` instead of `app/main.py`.
- `module4/app/services/app_runtime.py` now exposes
  `build_default_composition_components(...)` as canonical naming, while
  `build_default_bootstrap_components(...)` remains compatibility alias.
- `module4/app/composition/runtime.py` now maps
  `build_default_composition_components` directly to the service-layer
  composition-named builder.

- Standardized compatibility exports now available from:
  - `backend/module4/app/repositories/`
  - `backend/module4/app/integrations/`
  - `backend/module4/app/resources/`

## Shared and Compatibility Layers

- Shared primitives root: `backend/shared/`
- Compatibility adapters root: `backend/compat/`
- Legacy auth proxy remains runnable from `backend/auth/` during migration.
- `backend/app/modules/extraction/module2_compat_worker.py` now imports
  module2 compat entrypoints from `module2/app/composition/application.py`
  so `module2/app/main.py` remains a thin FastAPI entrypoint.
