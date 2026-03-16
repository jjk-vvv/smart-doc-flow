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

If PostgreSQL is temporarily unavailable, `MODULE4_DB_CONNECT_TIMEOUT_SEC` controls how fast the service falls back to memory mode.
Use `MODULE4_FORCE_MEMORY_MODE=1` when you want deterministic local testing without a database.
`MODULE4_ALERT_LOW_CONF_THRESHOLD` controls the built-in low-confidence rule threshold when default rules are seeded.

3. Run API:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
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
- prompt assets present
- GraphRAG runtime configuration populated

`probe=deep` additionally attempts to reach:

- OneAPI status endpoint derived from `MODULE4_GRAPHRAG_API_BASE`
- Neo4j using the configured credentials

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
- `GET /module4/healthz` returns `status=degraded` when the service is running in memory fallback mode.
- `GET /module4/healthz` also reports GraphRAG runtime readiness. Use `probe=deep` when you want live OneAPI and Neo4j reachability checks.
- Tenant-scoped APIs can resolve tenant from request body/query or the `X-Tenant-Id` header.
