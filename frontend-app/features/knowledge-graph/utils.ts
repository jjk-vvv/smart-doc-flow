import { readExtractionDocuments } from '../../shared/state/extractionDocuments';
import { readWorkbenchSession } from '../../shared/state/workbenchSession';
import type { Module4GraphEdge, Module4GraphNode, Module4GraphFileItem } from '../../shared/api/knowledgeGraph';

export const OVERVIEW_NODE_TYPES = new Set([
  'document',
  'business_context',
  'topic',
  'observation',
  'claim',
  'business_alert',
  'entity',
  'field',
  'risk',
  'community',
  'community_report',
]);
export const OVERVIEW_COMMUNITY_RELATIONS = new Set(['in_community']);
export const OVERVIEW_SEMANTIC_RELATIONS = new Set([
  'extracts',
  'has_entity',
  'has_report',
  'related',
  'related_to',
  'links_to',
  'describes_context',
  'has_topic',
  'has_observation',
  'states_claim',
  'raises_business_alert',
  'grounded_in',
]);

export const fileGraphReadySourceKey = (fileHash: string, versionId = '') =>
  `graphrag:artifact:file:${fileHash}:${versionId || 'latest'}`;

export const fileGraphPendingSourceKey = (fileHash: string) => `graphrag:artifact:file-pending:${fileHash}`;

export const graphFileHasUsableVersion = (item?: Module4GraphFileItem | null) =>
  Boolean(item && item.status === 'ready');

export const graphFileSourceKey = (item?: Module4GraphFileItem | null, fileHash = '') =>
  fileGraphReadySourceKey(fileHash || String(item?.file_hash || '').trim(), String(item?.active_version_id || ''));

export const ARTIFACT_PATTERNS = [
  /^pdf_[a-z0-9_-]+_[ft]\d+$/i,
  /^page_\d+_(figure|table|image|chunk)_\d+$/i,
  /^[a-z0-9_-]+_[ft]\d+$/i,
  /^[0-9a-f]{8}-[0-9a-f-]{27}$/i,
  /^[0-9a-f]{16,}$/i,
];

export const GENERIC_ENTITY_NAME_MAP: Record<string, string> = {
  geo: 'Geo',
  indicator: 'Indicator',
  facility: 'Facility',
  person: 'Person',
  event: 'Event',
  organization: 'Organization',
  org: 'Organization',
  location: 'Location',
};

export const getActiveExtractionFileHash = () => {
  const session = readWorkbenchSession();
  const sessionFileHash = String(session?.activeDocFileHash || '').trim();
  if (sessionFileHash) return sessionFileHash;
  const docs = readExtractionDocuments();
  if (docs.length === 0) return '';
  const activeIndex = Math.max(0, Number(session?.activeDocIndex || 0));
  return String(docs[activeIndex]?.file_hash || docs[0]?.file_hash || '').trim();
};

export const normalizeText = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim();

export const normalizeTypeKey = (value: unknown) =>
  normalizeText(value)
    .replace(/^__|__$/g, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/\s+/g, '_')
    .toLowerCase() || 'node';

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const asRecord = (value: unknown) => (isRecord(value) ? value : {});
export const asList = (value: unknown) => (Array.isArray(value) ? value : []);

export const firstText = (...values: unknown[]) => {
  for (const value of values) {
    const text = normalizeText(value);
    if (text) return text;
  }
  return '';
};

export const nestedText = (value: unknown, ...path: string[]) => {
  let current: unknown = value;
  for (const key of path) {
    if (!isRecord(current)) return '';
    current = current[key];
  }
  return normalizeText(current);
};

export const numberOrNull = (value: unknown) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, max));

export const otherNodeIdOfEdge = (edge: Module4GraphEdge, nodeId: string) =>
  edge.source_node_id === nodeId ? edge.target_node_id : edge.source_node_id;

export const buildDegreeMap = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const degreeMap = new Map<string, number>();
  nodes.forEach((node) => degreeMap.set(node.node_id, 0));
  edges.forEach((edge) => {
    degreeMap.set(edge.source_node_id, (degreeMap.get(edge.source_node_id) || 0) + 1);
    degreeMap.set(edge.target_node_id, (degreeMap.get(edge.target_node_id) || 0) + 1);
  });
  return degreeMap;
};

export const shortText = (value: string, max = 30) => {
  const text = normalizeText(value);
  return text.length > max ? `${text.slice(0, Math.max(0, max - 1))}...` : text;
};

export const stripFileExtension = (value: string) => value.replace(/\.(pdf|doc|docx|xls|xlsx|txt|md)$/i, '');

export const prettifyToken = (value: string) =>
  normalizeText(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\b[a-z]/g, (char) => char.toUpperCase());

export const stripWrappingQuotes = (value: unknown) =>
  normalizeText(value)
    .replace(/^[`"']+/, '')
    .replace(/[`"']+$/, '')
    .trim();

export const cleanArtifactText = (value: unknown) =>
  stripWrappingQuotes(value)
    .replace(/^chart:\s*/i, '')
    .replace(/^table:\s*/i, '')
    .replace(/\b(?:pdf|mineru|gemini|vision)[\w-]*_[ft]\d+\b/gi, '')
    .replace(/\bpage_\d+_(?:figure|table|image|chunk)_\d+\b/gi, '')
    .replace(/\((?:pdf|mineru|gemini|vision)[^)]+\)/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
