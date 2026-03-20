# Module 4 Backend

Global knowledge graph and risk intelligence service.

## Quick Start

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

Module 4 GraphRAG execution is aligned to the project `ragtest` baseline and now expects:

- `graphrag==0.3.0`
- `pandas`
- `neo4j`
- `pyarrow`

2. Copy environment file:

```powershell
Copy-Item .env.example .env
```

Module 4 now starts in strict database mode. If PostgreSQL is unavailable, startup fails instead of silently falling back.
`MODULE4_DB_CONNECT_TIMEOUT_SEC` controls how quickly startup reports the connection failure.
`MODULE4_ALERT_LOW_CONF_THRESHOLD` controls the built-in low-confidence rule threshold when default rules are seeded.
Leave `MODULE4_GRAPHRAG_PYTHON_BIN=python` unless you deliberately need a custom runtime.
When the value is generic, Module 4 now auto-prefers `backend/module4/.venv` so the GraphRAG runtime stays local to this repo instead of silently borrowing `D:\ragtest`.

Module 4 no longer accepts direct file uploads. The only supported ingest path is:

- Module 2 upload and parse
- Module 2 auto-sync parsed `documents`
- Module 4 ingest `documents` and build file-scoped graph state

3. Run API:

```powershell
npm run dev:module4
```

`npm run dev:module4` now fixed-prefers `backend/module4/.venv` for the Module 4 runtime.

If you want to override the interpreter explicitly:

```powershell
$env:MODULE4_PYTHON="D:\smart_doc_flow\smart-doc-flow\backend\module4\.venv\Scripts\python.exe"
npm run dev:module4
```

4. (Optional) start from repository root:

```powershell
npm run dev:module4
```

## Runtime Readiness

Use the health endpoint to distinguish a basic local runtime check from a deeper dependency reachability check:

```powershell
Invoke-WebRequest http://127.0.0.1:8100/module4/healthz
Invoke-WebRequest http://127.0.0.1:8100/module4/healthz?probe=deep
```

`probe=basic` reports whether Module 4 has the local prerequisites to run GraphRAG:

- python executable available
- `graphrag` importable in that python runtime
- `tiktoken.get_encoding("cl100k_base")` available in that runtime
- prompt assets present
- GraphRAG runtime configuration populated

The health payload now also includes runtime version details for the active GraphRAG python environment.

`probe=deep` additionally attempts to reach:

- OneAPI status endpoint derived from `MODULE4_GRAPHRAG_API_BASE`
- Neo4j using the configured credentials

## Neo4j Projection

When a file-scoped graph reaches `ready`, Module 4 now attempts a downstream Neo4j projection for the active graph version.

- Projection is best-effort and does not fail the document ingest job when Neo4j is unavailable.
- The projector refreshes its credentials from the active workspace runtime before each write.
- `MODULE4_NEO4J_PROJECT_TIMEOUT_SEC` controls how long Module 4 waits before recording projection failure and preserving the main ingest success path.
- `MODULE4_NEO4J_PROJECT_MAX_NODES` and `MODULE4_NEO4J_PROJECT_MAX_EDGES` cap the graph size that will be pushed downstream in one projection attempt.

## Main APIs

- `POST /module4/ingest`
- `GET /module4/jobs/{job_id}`
- `POST /module4/rebuild`
- `GET /module4/graph`
- `GET /module4/graph/neighborhood/{node_id}`
- `GET /module4/alerts`
- `POST /module4/alerts/{alert_id}/ack`
- `POST /module4/alerts/{alert_id}/resolve`
- `GET /module4/evidence`
- `GET /module4/evidence/edge/{edge_id}`
- `GET /module4/rules`
- `PUT /module4/rules/{rule_id}`
- `POST /module4/explain`
- `POST /module4/simulate`
- `GET /module4/healthz`

## Rule Engine

Rules are stored in `module4.rules` and are applied during `ingest`.

- Supported `rule_kind`: `deterministic`
- Recommended `expr` fields:
  - `scope`: `field` or `document`
  - `path`: dotted path in context (for example `confidence`, `diagnostics.quality_status`)
  - `op`: `eq|neq|lt|lte|gt|gte|contains|in|exists|not_exists|non_empty|is_empty`
  - `value`: comparison target
  - `risk_score` or `risk_formula` (`1_minus_confidence`)
  - `title` / `summary`: template strings (for example `{file_name}`, `{field_name}`, `{confidence}`)

## Stability Notes

- Ingest batches are deduplicated by `source_batch_key`; when omitted, the service derives a stable key from the payload.
- Re-ingesting the same payload reuses existing alerts and evidence instead of inflating counts.
- `POST /module4/rebuild` clears tenant graph data and replays saved ingest batches for that tenant.
- In-flight ingest / rebuild jobs are re-queued on graceful shutdown so they can be recovered on the next startup when PostgreSQL is available.
- `GET /module4/healthz` also reports GraphRAG runtime readiness. Use `probe=deep` when you want live OneAPI and Neo4j reachability checks.
- Tenant-scoped APIs can resolve tenant from request body/query or the `X-Tenant-Id` header.
