CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS doc_knowledge_document (
    id uuid PRIMARY KEY,
    file_hash text NOT NULL UNIQUE,
    file_name text NOT NULL,
    source_bundle_json jsonb NOT NULL,
    merged_raw_markdown text,
    merged_clean_markdown text,
    build_stats_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doc_knowledge_unit (
    id text PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES doc_knowledge_document(id) ON DELETE CASCADE,
    file_hash text NOT NULL,
    unit_type text NOT NULL,
    title text,
    content text NOT NULL,
    page_start integer,
    page_end integer,
    source_block_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    unit_meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1536) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doc_ingest_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_hash text NOT NULL,
    status text NOT NULL,
    stage text NOT NULL,
    warning_count integer NOT NULL DEFAULT 0,
    error_text text,
    stats_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    finished_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_doc_knowledge_unit_file_hash ON doc_knowledge_unit(file_hash);
CREATE INDEX IF NOT EXISTS idx_doc_knowledge_unit_type ON doc_knowledge_unit(unit_type);
