# Backend Unified Architecture

This document defines the canonical backend structure and migration rules.

## Top-Level Domains

- `app/` (gateway runtime, compatibility-kept path)
- `module2/` (document extraction runtime)
- `module4/` (graph/insight runtime)
- `shared/` (cross-service contracts/primitives)
- `compat/` (legacy adapters/proxies)
- `tests/` (cross-service integration tests)

## Service Internal Standard

Each Python service converges to:

- `app/api/v1/endpoints`
- `app/services`
- `app/domain`
- `app/repositories`
- `app/db`
- `app/schemas`
- `app/integrations`
- `app/core`
- `app/resources`
- `app/utils`

## Migration Rules

1. New code should target standard directories first.
2. Legacy directories stay as compatibility layers until imports are fully moved.
3. API routing entry should come from `app/api/v1/*`.
4. Environment loading should be centralized in service entry/core settings.
5. Runtime data and artifacts must remain outside code directories.

