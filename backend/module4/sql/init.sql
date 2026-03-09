CREATE SCHEMA IF NOT EXISTS module4;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS module4.jobs (
  job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  job_type TEXT NOT NULL CHECK (job_type IN ('ingest','rebuild_graph','run_rules','simulate')),
  status TEXT NOT NULL CHECK (status IN ('queued','running','success','failed','cancelled')),
  progress NUMERIC(5,2) NOT NULL DEFAULT 0,
  error_message TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  result JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS module4.ingest_batches (
  batch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  source TEXT NOT NULL CHECK (source IN ('module2','module3','manual','api')),
  source_batch_key TEXT,
  job_id UUID REFERENCES module4.jobs(job_id) ON DELETE SET NULL,
  raw_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source, source_batch_key)
);

CREATE TABLE IF NOT EXISTS module4.documents (
  doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  batch_id UUID REFERENCES module4.ingest_batches(batch_id) ON DELETE SET NULL,
  file_name TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  track TEXT,
  diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, file_hash)
);

CREATE TABLE IF NOT EXISTS module4.evidence (
  evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  evidence_key TEXT,
  doc_id UUID REFERENCES module4.documents(doc_id) ON DELETE CASCADE,
  object_type TEXT NOT NULL CHECK (object_type IN ('field','table','figure','text')),
  object_id TEXT,
  ref_id TEXT,
  page_no INT,
  snippet TEXT,
  locator JSONB NOT NULL DEFAULT '{}'::jsonb,
  bbox JSONB NOT NULL DEFAULT '[]'::jsonb,
  artifact_url TEXT,
  confidence NUMERIC(5,4) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module4.nodes (
  node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  node_type TEXT NOT NULL,
  canonical_key TEXT NOT NULL,
  display_name TEXT NOT NULL,
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence NUMERIC(5,4) NOT NULL DEFAULT 0,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, node_type, canonical_key)
);

CREATE TABLE IF NOT EXISTS module4.edges (
  edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  source_node_id UUID NOT NULL REFERENCES module4.nodes(node_id) ON DELETE CASCADE,
  target_node_id UUID NOT NULL REFERENCES module4.nodes(node_id) ON DELETE CASCADE,
  relation_type TEXT NOT NULL,
  direction TEXT NOT NULL DEFAULT 'out' CHECK (direction IN ('out','bi')),
  attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
  confidence NUMERIC(5,4) NOT NULL DEFAULT 0,
  risk_score NUMERIC(6,3) NOT NULL DEFAULT 0,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_node_id, target_node_id, relation_type)
);

CREATE TABLE IF NOT EXISTS module4.edge_evidence (
  edge_id UUID NOT NULL REFERENCES module4.edges(edge_id) ON DELETE CASCADE,
  evidence_id UUID NOT NULL REFERENCES module4.evidence(evidence_id) ON DELETE CASCADE,
  PRIMARY KEY (edge_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS module4.rules (
  rule_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('yellow','orange','red')),
  rule_kind TEXT NOT NULL CHECK (rule_kind IN ('deterministic','semantic','anomaly')),
  expr JSONB NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  version INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module4.alerts (
  alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  alert_key TEXT,
  rule_id TEXT NOT NULL REFERENCES module4.rules(rule_id),
  severity TEXT NOT NULL CHECK (severity IN ('yellow','orange','red')),
  status TEXT NOT NULL CHECK (status IN ('open','ack','resolved','false_positive')) DEFAULT 'open',
  subject_node_id UUID REFERENCES module4.nodes(node_id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  risk_score NUMERIC(6,3) NOT NULL DEFAULT 0,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  acknowledged_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module4.alert_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_id UUID NOT NULL REFERENCES module4.alerts(alert_id) ON DELETE CASCADE,
  action TEXT NOT NULL CHECK (action IN ('created','ack','resolved','reopened','false_positive','comment')),
  actor TEXT NOT NULL DEFAULT 'system',
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module4.feedback_labels (
  feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  alert_id UUID REFERENCES module4.alerts(alert_id) ON DELETE SET NULL,
  label TEXT NOT NULL CHECK (label IN ('valid','invalid','uncertain')),
  comment TEXT,
  actor TEXT NOT NULL DEFAULT 'user',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE module4.evidence ADD COLUMN IF NOT EXISTS evidence_key TEXT;
ALTER TABLE module4.alerts ADD COLUMN IF NOT EXISTS alert_key TEXT;

CREATE INDEX IF NOT EXISTS idx_m4_jobs_tenant_status ON module4.jobs (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_m4_nodes_tenant_type ON module4.nodes (tenant_id, node_type);
CREATE INDEX IF NOT EXISTS idx_m4_edges_tenant_rel ON module4.edges (tenant_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_m4_alerts_tenant_status ON module4.alerts (tenant_id, status, severity, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_m4_evidence_doc_page ON module4.evidence (doc_id, page_no);
CREATE UNIQUE INDEX IF NOT EXISTS uq_m4_alerts_tenant_key ON module4.alerts (tenant_id, alert_key) WHERE alert_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_m4_evidence_tenant_key ON module4.evidence (tenant_id, evidence_key) WHERE evidence_key IS NOT NULL;
