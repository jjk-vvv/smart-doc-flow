import { buildApiUrl, ensureOk, resolveApiBase } from './client';
import { getCurrentUser } from './auth';

export type Module4GraphNode = {
  node_id: string;
  node_type: string;
  canonical_key: string;
  display_name: string;
  confidence: number;
  attrs: Record<string, unknown>;
  updated_at?: string | null;
  type_label?: string;
  category?: string;
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
  isBaseEdge?: boolean;
  baseEdgeReason?: string | null;
  updated_at?: string | null;
  relation_label?: string;
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
  source?: string;
  workspace_id?: string | null;
};

export type Module4GraphProjectionStatus = {
  status: string;
  projected_nodes: number;
  projected_edges: number;
  source_node_count: number;
  source_edge_count: number;
  skipped_reason?: string | null;
  error_message?: string | null;
  labels: string[];
  relationship_type: string;
};

export type Module4GraphFileItem = {
  graph_file_id: string;
  tenant_id: string;
  file_hash: string;
  file_name: string;
  workspace_id?: string | null;
  graph_mode: string;
  source: string;
  status: string;
  current_job_id?: string | null;
  active_version_id?: string | null;
  last_error?: string | null;
  node_count: number;
  edge_count: number;
  metadata: Record<string, unknown>;
  projection?: Module4GraphProjectionStatus | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_indexed_at?: string | null;
};

export type Module4GraphFileListResponse = {
  items: Module4GraphFileItem[];
};

export type Module4GraphFileDetailResponse = {
  item: Module4GraphFileItem;
};

export type Module4AlertItem = {
  alert_id: string;
  rule_id: string;
  severity: 'yellow' | 'orange' | 'red';
  status: 'open' | 'ack' | 'resolved' | 'false_positive';
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

export type Module4RuleItem = {
  rule_id: string;
  name: string;
  severity: 'yellow' | 'orange' | 'red';
  rule_kind: 'deterministic';
  expr: Record<string, unknown>;
  enabled: boolean;
  version: number;
  updated_at?: string | null;
};

export type Module4RuleListResponse = {
  items: Module4RuleItem[];
};

export type Module4RuleUpsertRequest = {
  name: string;
  severity: 'yellow' | 'orange' | 'red';
  rule_kind: 'deterministic';
  expr: Record<string, unknown>;
  enabled: boolean;
};

export type Module4RuleUpsertResponse = {
  ok: boolean;
  rule: Module4RuleItem;
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

export type Module4JobResponse = {
  job_id: string;
  tenant_id: string;
  job_type: 'ingest' | 'rebuild_graph' | 'run_rules' | 'simulate';
  status: 'queued' | 'running' | 'success' | 'failed' | 'cancelled';
  progress: number;
  error_message?: string | null;
  payload: Record<string, unknown>;
  result: Record<string, unknown>;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type Module4RuntimeDependencyStatus = {
  configured: boolean;
  reachable?: boolean | null;
  missing_fields: string[];
  error_message?: string | null;
};

export type Module4GraphRAGRuntimeStatus = {
  ready: boolean;
  check_mode: string;
  python_bin: string;
  python_bin_exists: boolean;
  graphrag_module_available: boolean;
  module_error_message?: string | null;
  prompt_assets_root: string;
  prompt_assets_ok: boolean;
  missing_prompt_assets: string[];
  config_missing_fields: string[];
  runtime_versions: Record<string, string>;
  tiktoken_encoding_ready?: boolean | null;
  tiktoken_encoding_error_message?: string | null;
  oneapi: Module4RuntimeDependencyStatus;
  neo4j: Module4RuntimeDependencyStatus;
};

export type Module4ProjectionRuntimeStatus = {
  enabled: boolean;
  configured: boolean;
  can_project: boolean;
  database: string;
  max_nodes: number;
  max_edges: number;
  timeout_sec: number;
  missing_fields: string[];
  labels: string[];
  relationship_type: string;
};

export type Module4HealthzResponse = {
  status: string;
  db_connected: boolean;
  jobs_in_queue: number;
  last_connect_error?: string | null;
  graphrag: Module4GraphRAGRuntimeStatus;
  projection_runtime: Module4ProjectionRuntimeStatus;
  now: string;
};

export type Module4IngestResponse = {
  job_id: string;
  batch_id: string;
  status: string;
};

export type Module4NodeDetailResponse = {
  node: Module4GraphNode | null;
  graph: Module4GraphResponse;
  file?: Module4GraphFileItem | null;
  evidence: Module4EvidenceItem[];
  edge_evidence: Record<string, Module4EvidenceItem[]>;
};

export type Module4GraphRagQueryMode = 'local' | 'global' | 'drift' | 'basic';

export type Module4GraphRagQueryRequest = {
  tenantId?: string;
  fileHash: string;
  query: string;
  mode?: Module4GraphRagQueryMode;
  responseType?: string;
  communityLevel?: number;
  dynamicCommunitySelection?: boolean;
  verbose?: boolean;
};

export type Module4GraphRagQueryResponse = {
  answer: string;
  mode: Module4GraphRagQueryMode;
  query: string;
  response_type: string;
  community_level?: number | null;
  dynamic_community_selection: boolean;
  file_hash: string;
  graph_file_id?: string | null;
  active_version_id?: string | null;
  workspace_id?: string | null;
  context_data: Record<string, Array<Record<string, unknown>>>;
  linked_node_ids: string[];
  linked_node_resolution?: Record<string, unknown>;
  source: string;
};

export type Module4ExplainRequest = {
  tenantId?: string;
  alertId?: string;
  nodeId?: string;
  targetNodeId?: string;
};

export type Module4ExplainResponse = {
  conclusion: string;
  reasoning_steps: string[];
  evidence: Record<string, unknown>[];
};

export type Module4SimulateRequest = {
  tenantId?: string;
  scenarioName?: string;
  params?: Record<string, unknown>;
  scope?: Record<string, unknown>;
};

export type Module4SimulateResponse = {
  impacts: Array<{
    metric: string;
    value: unknown;
  }>;
  changed_alerts: Record<string, unknown>[];
  summary: string;
};

const resolveModule4ApiBase = (): string => {
  const envBase = resolveApiBase(import.meta.env.VITE_BACKEND_ENTRY_URL || '');
  if (!envBase || typeof window === 'undefined') {
    return envBase;
  }

  const localHostnames = new Set(['localhost', '127.0.0.1', '::1']);
  const isElectron = typeof navigator !== 'undefined' && /electron/i.test(String(navigator.userAgent || ''));
  const isLoopbackHost = (host: string) => localHostnames.has(String(host || '').trim().toLowerCase());
  const isLoopbackBase = (value: string) => {
    try {
      return isLoopbackHost(new URL(value).hostname);
    } catch {
      return false;
    }
  };

  // Desktop/local renderers should use the co-located gateway or Vite proxy.
  // Otherwise a stale public FRP URL can return HTML/502 and pollute graph UI.
  if (isElectron && !isLoopbackHost(window.location.hostname)) {
    return 'http://127.0.0.1:3001';
  }
  if (
    (window.location.protocol === 'file:' || isLoopbackHost(window.location.hostname))
    && /^https?:\/\//i.test(envBase)
    && !isLoopbackBase(envBase)
  ) {
    return '';
  }

  return envBase;
};

type Module4AuthHeaders = Record<string, string>;

let module4AuthHeadersCache: Module4AuthHeaders | null = null;
let module4AuthHeadersPromise: Promise<Module4AuthHeaders> | null = null;

const resolveModule4AuthHeaders = async (): Promise<Module4AuthHeaders> => {
  if (module4AuthHeadersCache) {
    return module4AuthHeadersCache;
  }
  if (module4AuthHeadersPromise) {
    return module4AuthHeadersPromise;
  }

  module4AuthHeadersPromise = (async () => {
    try {
      const payload = await getCurrentUser();
      const user = payload?.user;
      const userId = String(user?.id || '').trim();
      const tenantId = String(user?.tenantId || userId).trim();
      const headers: Module4AuthHeaders = {};
      if (userId) headers['X-Authenticated-User-Id'] = userId;
      if (tenantId) {
        headers['X-Authenticated-Tenant-Id'] = tenantId;
        headers['X-Tenant-Id'] = tenantId;
      }
      module4AuthHeadersCache = headers;
      return headers;
    } catch {
      module4AuthHeadersCache = {};
      return {};
    } finally {
      module4AuthHeadersPromise = null;
    }
  })();

  return module4AuthHeadersPromise;
};

const withModule4AuthHeaders = async (init: RequestInit = {}): Promise<RequestInit> => {
  const mergedHeaders = new Headers(init.headers || undefined);
  const authHeaders = await resolveModule4AuthHeaders();
  Object.entries(authHeaders).forEach(([key, value]) => {
    if (value && !mergedHeaders.has(key)) {
      mergedHeaders.set(key, value);
    }
  });
  return {
    ...init,
    headers: mergedHeaders,
  };
};

const module4Fetch = async (path: string, init: RequestInit = {}) => {
  const { url } = buildApiUrl(path, resolveModule4ApiBase());
  const initWithHeaders = await withModule4AuthHeaders(init);
  return fetch(url, {
    credentials: 'include',
    ...initWithHeaders,
  });
};

export const fetchModule4JobStatus = async (
  jobId: string,
  params?: { tenantId?: string; statusOnly?: boolean }
): Promise<Module4JobResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.statusOnly) query.set('status_only', 'true');
  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/jobs/${encodeURIComponent(jobId)}${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4JobResponse;
};

export const fetchModule4Healthz = async (params?: {
  probe?: 'basic' | 'deep';
}): Promise<Module4HealthzResponse> => {
  const query = new URLSearchParams();
  if (params?.probe) query.set('probe', params.probe);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/healthz${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4HealthzResponse;
};

export const fetchModule4Graph = async (params?: {
  tenantId?: string;
  nodeTypes?: string[];
  relationTypes?: string[];
  limitNodes?: number;
  limitEdges?: number;
}): Promise<Module4GraphResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.nodeTypes?.length) query.set('node_types', params.nodeTypes.join(','));
  if (params?.relationTypes?.length) query.set('relation_types', params.relationTypes.join(','));
  if (params?.limitNodes) query.set('limit_nodes', String(params.limitNodes));
  if (params?.limitEdges) query.set('limit_edges', String(params.limitEdges));

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/graph${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4GraphResponse;
};

export const fetchModule4GraphFiles = async (params?: {
  tenantId?: string;
  status?: string;
  limit?: number;
}): Promise<Module4GraphFileListResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.status) query.set('status', params.status);
  if (params?.limit) query.set('limit', String(params.limit));

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/graph/files${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4GraphFileListResponse;
};

export const fetchModule4GraphFileDetail = async (
  fileHash: string,
  params?: { tenantId?: string }
): Promise<Module4GraphFileDetailResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/graph/files/${encodeURIComponent(fileHash)}${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4GraphFileDetailResponse;
};

export const fetchModule4FileGraph = async (
  fileHash: string,
  params?: {
    tenantId?: string;
    nodeTypes?: string[];
    relationTypes?: string[];
    limitNodes?: number;
    limitEdges?: number;
  }
): Promise<Module4GraphResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.nodeTypes?.length) query.set('node_types', params.nodeTypes.join(','));
  if (params?.relationTypes?.length) query.set('relation_types', params.relationTypes.join(','));
  if (params?.limitNodes) query.set('limit_nodes', String(params.limitNodes));
  if (params?.limitEdges) query.set('limit_edges', String(params.limitEdges));

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/graph/files/${encodeURIComponent(fileHash)}/view${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4GraphResponse;
};

export const fetchModule4Neighborhood = async (
  nodeId: string,
  params?: {
    tenantId?: string;
    depth?: number;
    relationTypes?: string[];
    limit?: number;
  }
): Promise<Module4GraphResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.depth) query.set('depth', String(params.depth));
  if (params?.relationTypes?.length) query.set('relation_types', params.relationTypes.join(','));
  if (params?.limit) query.set('limit', String(params.limit));

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/graph/neighborhood/${encodeURIComponent(nodeId)}${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4GraphResponse;
};

export const fetchModule4FileNeighborhood = async (
  fileHash: string,
  nodeId: string,
  params?: {
    tenantId?: string;
    depth?: number;
    relationTypes?: string[];
    limit?: number;
  }
): Promise<Module4GraphResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.depth) query.set('depth', String(params.depth));
  if (params?.relationTypes?.length) query.set('relation_types', params.relationTypes.join(','));
  if (params?.limit) query.set('limit', String(params.limit));

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(
    `/module4/graph/files/${encodeURIComponent(fileHash)}/neighborhood/${encodeURIComponent(nodeId)}${suffix}`
  );
  await ensureOk(res);
  return (await res.json()) as Module4GraphResponse;
};

export const fetchModule4NodeDetail = async (
  nodeId: string,
  params?: { tenantId?: string; depth?: number; limit?: number; fileHash?: string }
): Promise<Module4NodeDetailResponse> => {
  if (params?.fileHash) {
    const query = new URLSearchParams();
    if (params?.tenantId) query.set('tenant_id', params.tenantId);
    query.set('depth', String(params?.depth ?? 1));
    query.set('limit', String(params?.limit ?? 160));
    const suffix = query.toString() ? `?${query.toString()}` : '';
    const res = await module4Fetch(
      `/module4/graph/files/${encodeURIComponent(params.fileHash)}/node/${encodeURIComponent(nodeId)}${suffix}`
    );
    await ensureOk(res);
    return (await res.json()) as Module4NodeDetailResponse;
  }

  const graph = await fetchModule4Neighborhood(nodeId, {
    tenantId: params?.tenantId,
    depth: params?.depth ?? 1,
    limit: params?.limit ?? 160,
  });

  return {
    node: graph.nodes.find((item) => item.node_id === nodeId) ?? null,
    graph,
    file: null,
    evidence: [],
    edge_evidence: {},
  };
};

export const searchModule4GraphRag = async (
  body: Module4GraphRagQueryRequest
): Promise<Module4GraphRagQueryResponse> => {
  const res = await module4Fetch('/module4/query/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: body.tenantId,
      file_hash: body.fileHash,
      query: body.query,
      mode: body.mode ?? 'local',
      response_type: body.responseType ?? 'multiple paragraphs',
      community_level: body.communityLevel ?? 2,
      dynamic_community_selection: body.dynamicCommunitySelection ?? false,
      verbose: body.verbose ?? false,
    }),
  });
  if (res.status === 401 || res.status === 403) {
    throw new Error('模块四查询未授权，请重新登录后重试。');
  }
  await ensureOk(res);
  return (await res.json()) as Module4GraphRagQueryResponse;
};

export const fetchModule4Alerts = async (params?: {
  tenantId?: string;
  status?: string;
  severity?: string;
  page?: number;
  pageSize?: number;
}): Promise<Module4AlertListResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.status) query.set('status', params.status);
  if (params?.severity) query.set('severity', params.severity);
  if (params?.page) query.set('page', String(params.page));
  if (params?.pageSize) query.set('page_size', String(params.pageSize));

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/alerts${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4AlertListResponse;
};

export const fetchModule4Rules = async (params?: {
  enabledOnly?: boolean;
}): Promise<Module4RuleListResponse> => {
  const query = new URLSearchParams();
  if (params?.enabledOnly) query.set('enabled_only', 'true');

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/rules${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4RuleListResponse;
};

export const updateModule4Rule = async (
  ruleId: string,
  body: Module4RuleUpsertRequest
): Promise<Module4RuleUpsertResponse> => {
  const res = await module4Fetch(`/module4/rules/${encodeURIComponent(ruleId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: body.name,
      severity: body.severity,
      rule_kind: body.rule_kind,
      expr: body.expr,
      enabled: body.enabled,
    }),
  });
  await ensureOk(res);
  return (await res.json()) as Module4RuleUpsertResponse;
};

export const ackModule4Alert = async (
  alertId: string,
  actor = 'user',
  comment = '',
  tenantId?: string
): Promise<void> => {
  const res = await module4Fetch(`/module4/alerts/${encodeURIComponent(alertId)}/ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor, comment, tenant_id: tenantId }),
  });
  await ensureOk(res);
};

export const resolveModule4Alert = async (
  alertId: string,
  actor = 'user',
  comment = '',
  resolution = '',
  tenantId?: string
): Promise<void> => {
  const res = await module4Fetch(`/module4/alerts/${encodeURIComponent(alertId)}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor, comment, resolution, tenant_id: tenantId }),
  });
  await ensureOk(res);
};

export const explainModule4 = async (body: Module4ExplainRequest): Promise<Module4ExplainResponse> => {
  const res = await module4Fetch('/module4/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: body.tenantId,
      alert_id: body.alertId,
      node_id: body.nodeId,
      target_node_id: body.targetNodeId,
    }),
  });
  await ensureOk(res);
  return (await res.json()) as Module4ExplainResponse;
};

export const simulateModule4 = async (body: Module4SimulateRequest): Promise<Module4SimulateResponse> => {
  const res = await module4Fetch('/module4/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: body.tenantId,
      scenario_name: body.scenarioName,
      params: body.params ?? {},
      scope: body.scope ?? {},
    }),
  });
  await ensureOk(res);
  return (await res.json()) as Module4SimulateResponse;
};

export const fetchModule4EvidenceByEdge = async (
  edgeId: string,
  params?: { tenantId?: string; page?: number; pageSize?: number }
): Promise<Module4EvidenceListResponse> => {
  const query = new URLSearchParams();
  if (params?.tenantId) query.set('tenant_id', params.tenantId);
  if (params?.page) query.set('page', String(params.page));
  if (params?.pageSize) query.set('page_size', String(params.pageSize));

  const suffix = query.toString() ? `?${query.toString()}` : '';
  const res = await module4Fetch(`/module4/evidence/edge/${encodeURIComponent(edgeId)}${suffix}`);
  await ensureOk(res);
  return (await res.json()) as Module4EvidenceListResponse;
};
