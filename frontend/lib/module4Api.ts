import type { ExtractionDocument } from './extractionStore';

export type Module4GraphNode = {
  node_id: string;
  node_type: string;
  canonical_key: string;
  display_name: string;
  confidence: number;
  attrs: Record<string, unknown>;
};

export type Module4GraphEdge = {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: string;
  direction: string;
  confidence: number;
  risk_score: number;
  attrs: Record<string, unknown>;
};

export type Module4GraphResponse = {
  nodes: Module4GraphNode[];
  edges: Module4GraphEdge[];
  stats: {
    node_count: number;
    edge_count: number;
    by_node_type: Record<string, number>;
    by_relation_type: Record<string, number>;
  };
};

export type Module4AlertItem = {
  alert_id: string;
  rule_id: string;
  severity: "yellow" | "orange" | "red";
  status: "open" | "ack" | "resolved" | "false_positive";
  subject_node_id?: string | null;
  title: string;
  summary: string;
  risk_score: number;
  payload: Record<string, unknown>;
  detected_at?: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
};

export type Module4AlertListResponse = {
  total: number;
  items: Module4AlertItem[];
};

export type Module4EvidenceItem = {
  evidence_id: string;
  doc_id: string;
  object_type: string;
  object_id: string;
  ref_id?: string | null;
  page_no?: number | null;
  snippet: string;
  locator: Record<string, unknown>;
  bbox: unknown[];
  artifact_url?: string | null;
  confidence: number;
  created_at?: string | null;
};

export type Module4EvidenceListResponse = {
  total: number;
  items: Module4EvidenceItem[];
};

export type Module4IngestResponse = {
  job_id: string;
  batch_id: string;
  status: string;
};

const ensureOk = async (res: Response) => {
  if (res.ok) return;
  const text = await res.text();
  throw new Error(text || `HTTP ${res.status}`);
};

export const ingestModule4Documents = async (
  documents: ExtractionDocument[],
  params?: { tenantId?: string; sourceBatchKey?: string }
): Promise<Module4IngestResponse | null> => {
  if (!Array.isArray(documents) || documents.length === 0) return null;
  const body: Record<string, unknown> = {
    source: "module2",
    documents,
  };
  if (params?.tenantId) body.tenant_id = params.tenantId;
  if (params?.sourceBatchKey) body.source_batch_key = params.sourceBatchKey;
  const res = await fetch("/module4/ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await ensureOk(res);
  return (await res.json()) as Module4IngestResponse;
};

export const fetchModule4Graph = async (params?: {
  tenantId?: string;
  nodeTypes?: string[];
  relationTypes?: string[];
  limitNodes?: number;
  limitEdges?: number;
}): Promise<Module4GraphResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set("tenant_id", params.tenantId);
  if (params?.nodeTypes && params.nodeTypes.length > 0) query.set("node_types", params.nodeTypes.join(","));
  if (params?.relationTypes && params.relationTypes.length > 0) query.set("relation_types", params.relationTypes.join(","));
  if (params?.limitNodes) query.set("limit_nodes", String(params.limitNodes));
  if (params?.limitEdges) query.set("limit_edges", String(params.limitEdges));

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const res = await fetch(`/module4/graph${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4GraphResponse;
};

export const fetchModule4Alerts = async (params?: {
  tenantId?: string;
  status?: string;
  severity?: string;
  page?: number;
  pageSize?: number;
}): Promise<Module4AlertListResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set("tenant_id", params.tenantId);
  if (params?.status) query.set("status", params.status);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const res = await fetch(`/module4/alerts${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4AlertListResponse;
};

export const ackModule4Alert = async (
  alertId: string,
  actor = "user",
  comment = "",
  tenantId?: string
): Promise<void> => {
  const res = await fetch(`/module4/alerts/${encodeURIComponent(alertId)}/ack`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor, comment, tenant_id: tenantId }),
  });
  await ensureOk(res);
};

export const resolveModule4Alert = async (
  alertId: string,
  actor = "user",
  comment = "",
  resolution = "",
  tenantId?: string
): Promise<void> => {
  const res = await fetch(`/module4/alerts/${encodeURIComponent(alertId)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor, comment, resolution, tenant_id: tenantId }),
  });
  await ensureOk(res);
};

export const fetchModule4EvidenceByEdge = async (
  edgeId: string,
  params?: { tenantId?: string; page?: number; pageSize?: number }
): Promise<Module4EvidenceListResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set("tenant_id", params.tenantId);
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const res = await fetch(`/module4/evidence/edge/${encodeURIComponent(edgeId)}${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4EvidenceListResponse;
};
