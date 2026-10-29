# Module 4 Backend

Global knowledge graph and risk intelligence service.

## Quick Start

1. Create the preferred repo-root unified virtual environment and install dependencies:

```powershell
python -m venv D:\smart_doc_flow\.venv
D:\smart_doc_flow\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Module 4 GraphRAG execution is aligned to the project `ragtest` baseline and now expects:

- `graphrag==0.3.0`
- `pandas>=2.2.2,<3` (GraphRAG 0.3 fails on pandas 3.x inside `create_base_text_units`)
- `neo4j`
- `pyarrow`

The separately published `graphrag-storage` package is not used by graphrag 0.3 and must not be installed: recent releases require `pandas~=3.0`, which breaks indexing.

2. Copy environment file:

```powershell
Copy-Item .env.example .env
```

Module 4 now starts in strict database mode. If PostgreSQL is unavailable, startup fails instead of silently falling back.
`MODULE4_DB_CONNECT_TIMEOUT_SEC` controls how quickly startup reports the connection failure.
`MODULE4_ALERT_LOW_CONF_THRESHOLD` controls the built-in low-confidence rule threshold when default rules are seeded.
Leave `MODULE4_GRAPHRAG_PYTHON_BIN=python` unless you deliberately need a custom runtime.
When the value is generic, Module 4 now resolves to the repo-root `D:\smart_doc_flow\smart-doc-flow\.venv`.
The historical `backend/module4/.venv` runtime has been removed from the project layout.
Legacy refactor indexing mode has been physically removed; Module 4 now runs GraphRAG pipeline only.

Query runtime behaviour (2026-10-29):

- Ingestion, artifact import, graph view, evidence, alerts and rebuild run on `graphrag==0.3.0`.
- `/module4/query/search` detects the installed runtime:
  - newer graphrag with `graphrag.api` uses the native GraphRAG search engines;
  - legacy 0.3.x uses `services/graphrag/artifact_query.py`, an artifact-only
    retrieval + chat-completion fallback. Responses are labelled
    `graphrag:query:<mode>:artifact_fallback`.
- The fallback answers from `create_final_text_units` and
  `create_final_community_reports`, so it needs no LanceDB/embedding store and no
  optional ML dependencies.
- Alerts are generated during ingestion (rule engine), including the reused-graph
  path. Alert severity/status flow is `open -> ack -> resolved`.

Module 4 no longer accepts direct file uploads. The only supported ingest path is:

- Module 2 upload and parse
- Module 2 auto-sync parsed `documents` (legacy-compatible)
- Module 4 ingest `documents` and build file-scoped graph state

Module 4 now also supports a GraphRAG-style text input mode in the same `/module4/ingest` payload:

- `text_corpus`: direct merged text corpus
- `source_texts[]`: optional source text entries with inline text and/or artifact paths
- `settings_overrides`: per-document chunk and embedding overrides (`chunk_size`, `chunk_overlap`, `embedding_model_name`)
- `metadata`: optional file-level metadata

When `documents[]` is empty but `text_corpus` or `source_texts[]` is provided, Module 4 synthesizes a single normalized document and proceeds with the same indexing pipeline.
If module2 diagnostics include `assistant1_source_markdown_artifact_path` and `assistant_payload_artifact_path`, Module 4 will read and merge those artifacts as high-quality text input.
You can now optionally control workflow behavior with:
- `MODULE4_GRAPHRAG_INDEXING_METHOD`
- `MODULE4_GRAPHRAG_EXECUTION_MODE` (`graphrag` by default; `deterministic_local` for offline deterministic indexing)
- `MODULE4_GRAPHRAG_WORKFLOWS`
- `MODULE4_GRAPHRAG_SKIP_WORKFLOWS`
- `MODULE4_GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS` (`0` by default for strict GraphRAG behavior)
- `MODULE4_GRAPHRAG_ALLOW_PARTIAL_IMPORT` (`0` by default for strict GraphRAG-first failure semantics)
- `MODULE4_INGEST_ALLOW_DOCUMENT_FALLBACK` (`0` by default to avoid implicit fallback graph writes)
- `MODULE4_GRAPHRAG_EXTRACT_GRAPH_PROMPT_FILE`
- `MODULE4_GRAPHRAG_SUMMARIZE_DESCRIPTIONS_PROMPT_FILE`
- `MODULE4_GRAPHRAG_EXTRACT_CLAIMS_PROMPT_FILE`
- `MODULE4_GRAPHRAG_COMMUNITY_REPORT_GRAPH_PROMPT_FILE`
- `MODULE4_GRAPHRAG_COMMUNITY_REPORT_TEXT_PROMPT_FILE`

Graph query runtime is now artifact-only (GraphRAG `create_final_*` outputs) with no storage projection fallback.

3. Run API:

```powershell
npm run dev:module4
```

`npm run dev:module4` now fixed-prefers `D:\smart_doc_flow\smart-doc-flow\.venv` for the Module 4 runtime.

If you want to override the interpreter explicitly:

```powershell
$env:MODULE4_PYTHON="D:\smart_doc_flow\smart-doc-flow\.venv\Scripts\python.exe"
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

- Provider API status endpoint derived from `MODULE4_GRAPHRAG_API_BASE`
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

## Public Case Graph Library

Module 4 can expose a small set of public read-only case graphs to every authenticated user without weakening tenant isolation.

- Registry file: `backend/app/modules/module4/resources/public_case_graphs.json`
- Optional override: `MODULE4_PUBLIC_CASE_REGISTRY_PATH`
- Each case entry points to an existing source graph by `source_tenant_id + source_file_hash`
- Public case list items are exposed with synthetic IDs such as `public_case::<case_id>`
- Graph rendering, node detail, and GraphRAG query reuse the source graph internally, but the public case remains read-only in the UI/API surface

## Non-PDF Alignment Eval

You can run a file-level alignment report against non-PDF files under the repository `datasets` folder:

```powershell
python backend/app/modules/module4/tools/nonpdf_alignment_eval.py --dataset-root D:\smart_doc_flow\smart-doc-flow\datasets
```

Optional arguments:

- `--limit <N>`: only evaluate the first N matched non-PDF files.
- `--tenant-id <id>`: logical tenant namespace used by the in-memory evaluation run.
- `--output <path>`: JSON report output path.

Default report path:

- `runtime-data/module4/nonpdf-alignment-report.json`
