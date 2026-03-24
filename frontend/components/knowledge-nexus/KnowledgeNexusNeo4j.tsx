import React, {
  forwardRef,
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { flushSync } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Focus,
  Minus,
  Network,
  Orbit,
  Pin,
  Plus,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  ForceDirectedLayoutType,
  HierarchicalLayoutType,
} from '@neo4j-nvl/base';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force';
import {
  ackModule4Alert,
  explainModule4,
  fetchModule4Alerts,
  fetchModule4FileGraph,
  fetchModule4FileNeighborhood,
  fetchModule4GraphFiles,
  fetchModule4Healthz,
  fetchModule4JobStatus,
  fetchModule4NodeDetail,
  fetchModule4Rules,
  resolveModule4Alert,
  simulateModule4,
  updateModule4Rule,
  type Module4AlertItem,
  type Module4EvidenceItem,
  type Module4ExplainResponse,
  type Module4GraphEdge,
  type Module4GraphFileItem,
  type Module4GraphNode,
  type Module4GraphResponse,
  type Module4HealthzResponse,
  type Module4JobResponse,
  type Module4NodeDetailResponse,
  type Module4RuleItem,
  type Module4SimulateResponse,
} from '../../lib/module4Api';
import {
  readExtractionDocuments,
  subscribeExtractionUpdates,
} from '../../lib/extractionStore';
import { readWorkbenchSession } from '../../lib/workbenchSession';

const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

type FilterState = {
  query: string;
  nodeTypes: string[];
};

type LayoutMode = typeof ForceDirectedLayoutType | typeof HierarchicalLayoutType;
type GraphViewMode = 'overview' | 'evidence';
type ToolbarMenu = 'summary' | 'source' | 'layout';

type InspectorState = {
  nodeId: string;
  x: number;
  y: number;
};

type DetailFact = {
  label: string;
  value: string;
};

type GraphNodeRole = 'anchor' | 'semantic' | 'structural' | 'evidence';
type GraphEdgeRole = 'semantic' | 'structural' | 'evidence' | 'anchor';
type NodeEmphasisTier = 'primary' | 'secondary' | 'tertiary' | 'normal';

const TYPE_LABELS: Record<string, string> = {
  document: '文档',
  chunk: '文本片段',
  entity: '实体',
  field: '字段',
  figure: '图像',
  image: '图像',
  table: '表格',
  risk: '风险',
  community: '主题社区',
  covariate: '协变量',
  node: '节点',
};

const RELATION_LABELS: Record<string, string> = {
  contains: '包含',
  related: '关联',
  related_to: '关联',
  links_to: '链接',
  part_of: '属于',
  has_entity: '包含实体',
  has_chunk: '包含片段',
  has_field: '包含字段',
  has_warning: '风险提示',
  has_finding: '包含发现',
  has_evidence: '包含证据',
  in_community: '归属社区',
};

const EMPTY_GRAPH: Module4GraphResponse = {
  nodes: [],
  edges: [],
  source: 'storage',
  workspace_id: null,
  stats: {
    node_count: 0,
    edge_count: 0,
    by_node_type: {},
    by_relation_type: {},
  },
};

const OVERVIEW_NODE_TYPES = new Set(['document', 'entity', 'community']);
const OVERVIEW_COMMUNITY_RELATIONS = new Set(['in_community']);
const OVERVIEW_SEMANTIC_RELATIONS = new Set(['related', 'related_to', 'links_to']);

const fileGraphReadySourceKey = (fileHash: string, versionId = '') =>
  `storage:file:${fileHash}:${versionId || 'latest'}`;
const fileGraphPendingSourceKey = (fileHash: string) => `storage:file-pending:${fileHash}`;

const graphFileHasUsableVersion = (item?: Module4GraphFileItem | null) =>
  Boolean(item && item.status === 'ready');

const graphFileSourceKey = (item?: Module4GraphFileItem | null, fileHash = '') =>
  fileGraphReadySourceKey(fileHash || String(item?.file_hash || '').trim(), String(item?.active_version_id || ''));

const ARTIFACT_PATTERNS = [
  /^pdf_[a-z0-9_-]+_[ft]\d+$/i,
  /^page_\d+_(figure|table|image|chunk)_\d+$/i,
  /^[a-z0-9_-]+_[ft]\d+$/i,
  /^[0-9a-f]{8}-[0-9a-f-]{27}$/i,
  /^[0-9a-f]{16,}$/i,
];

const GENERIC_ENTITY_NAME_MAP: Record<string, string> = {
  geo: '地理实体',
  indicator: '指标实体',
  facility: '设施实体',
  person: '人物实体',
  event: '事件实体',
  organization: '组织实体',
  org: '组织实体',
  location: '地点实体',
};

const getActiveExtractionFileHash = () => {
  const session = readWorkbenchSession();
  const sessionFileHash = String(session?.activeDocFileHash || '').trim();
  if (sessionFileHash) return sessionFileHash;
  const docs = readExtractionDocuments();
  if (docs.length === 0) return '';
  const activeIndex = Math.max(0, Number(session?.activeDocIndex || 0));
  return String(docs[activeIndex]?.file_hash || docs[0]?.file_hash || '').trim();
};

const normalizeText = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim();

const normalizeTypeKey = (value: unknown) =>
  normalizeText(value)
    .replace(/^__|__$/g, '')
    .replace(/\s+/g, '_')
    .toLowerCase() || 'node';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const asRecord = (value: unknown) => (isRecord(value) ? value : {});
const asList = (value: unknown) => (Array.isArray(value) ? value : []);

const firstText = (...values: unknown[]) => {
  for (const value of values) {
    const text = normalizeText(value);
    if (text) return text;
  }
  return '';
};

const nestedText = (value: unknown, ...path: string[]) => {
  let current: unknown = value;
  for (const key of path) {
    if (!isRecord(current)) return '';
    current = current[key];
  }
  return normalizeText(current);
};

const numberOrNull = (value: unknown) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, max));

const shortText = (value: string, max = 30) => {
  const text = normalizeText(value);
  return text.length > max ? `${text.slice(0, Math.max(0, max - 1))}…` : text;
};

const stripFileExtension = (value: string) => value.replace(/\.(pdf|doc|docx|xls|xlsx|txt|md)$/i, '');

const prettifyToken = (value: string) =>
  normalizeText(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\b[a-z]/g, (char) => char.toUpperCase());

const stripWrappingQuotes = (value: unknown) =>
  normalizeText(value)
    .replace(/^[`"'“”‘’]+/, '')
    .replace(/[`"'“”‘’]+$/, '')
    .trim();

const cleanArtifactText = (value: unknown) =>
  stripWrappingQuotes(value)
    .replace(/^chart:\s*/i, '')
    .replace(/^table:\s*/i, '')
    .replace(/\b(?:pdf|mineru|gemini|vision)[\w-]*_[ft]\d+\b/gi, '')
    .replace(/\bpage_\d+_(?:figure|table|image|chunk)_\d+\b/gi, '')
    .replace(/\((?:pdf|mineru|gemini|vision)[^)]+\)/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();

const hexToRgb = (value: string) => {
  const hex = value.replace('#', '').trim();
  const normalized =
    hex.length === 3
      ? hex
          .split('')
          .map((char) => `${char}${char}`)
          .join('')
      : hex;
  const parsed = Number.parseInt(normalized, 16);
  if (!Number.isFinite(parsed) || normalized.length !== 6) return null;
  return {
    r: (parsed >> 16) & 255,
    g: (parsed >> 8) & 255,
    b: parsed & 255,
  };
};

const mixHexColor = (left: string, right: string, ratio: number) => {
  const source = hexToRgb(left);
  const target = hexToRgb(right);
  if (!source || !target) return left;
  const weight = clamp(ratio, 0, 1);
  const mix = (from: number, to: number) => Math.round(from + (to - from) * weight);
  return `#${[mix(source.r, target.r), mix(source.g, target.g), mix(source.b, target.b)]
    .map((channel) => channel.toString(16).padStart(2, '0'))
    .join('')}`;
};

const hexToRgba = (value: string, alpha: number) => {
  const rgb = hexToRgb(value);
  if (!rgb) return value;
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${clamp(alpha, 0, 1)})`;
};

const humanizeDocumentName = (value: unknown) => {
  const normalized = stripWrappingQuotes(value)
    .replace(/\.[a-z0-9]+$/i, '')
    .replace(/_hash-[a-z0-9]+$/i, '')
    .replace(/^[0-9]+(?:_[a-z0-9]+){0,3}_/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();

  return normalized ? prettifyToken(normalized) : '';
};

const extractSemanticTitle = (value: unknown, fallback = '') => {
  const lines = String(value ?? '')
    .split(/\r?\n+/)
    .map((line) =>
      normalizeText(line)
        .replace(/^\[page\s*\d+\]\s*/i, '')
        .replace(/\/c\d+/gi, '')
        .replace(/\s{2,}/g, ' ')
        .trim()
    )
    .filter(Boolean);

  const contentLines = lines.filter(
    (line) =>
      !/^注释[:：]?$/i.test(line) &&
      !/^notes?[:：]?$/i.test(line) &&
      !/^资料来源[:：]?$/i.test(line) &&
      !/^\[\d+\]/.test(line)
  );

  const titleLike =
    contentLines.find((line) => /\d{4}年.*(公报|报告|白皮书|年鉴|规划|方案|指南|手册|分析)/.test(line)) ||
    contentLines.find((line) => /^[一二三四五六七八九十]+、[\u4e00-\u9fa5A-Za-z0-9（）()《》“”/\-]{2,32}$/.test(line)) ||
    contentLines.find(
      (line) => /^第[一二三四五六七八九十0-9]+[章节篇部分卷][：:\s-]*[\u4e00-\u9fa5A-Za-z0-9（）()《》“”/\-]{2,32}$/.test(line)
    ) ||
    contentLines.find((line) => /^[A-Z]\.\d+\.\s+[A-Z][A-Z\s/&-]{6,}$/i.test(line)) ||
    contentLines.find((line) => /^[A-Z][A-Z\s/&-]{8,}$/.test(line)) ||
    contentLines.find(
      (line) =>
        /[\u4e00-\u9fa5A-Za-z]/.test(line) &&
        line.length >= 6 &&
        !/[=<>]/.test(line) &&
        !/^[0-9\s.,;:%()/-]+$/.test(line) &&
        !/^[0-9.%-]+$/.test(line)
    );

  const cleaned = cleanArtifactText(
    titleLike
      ?.replace(/^[A-Z]\.\d+\.\s*/i, '')
      .replace(/^appendix\s+[a-z]:\s*/i, '')
      .replace(/^chapter\s+\d+[:.]?\s*/i, '') || fallback
  );

  return cleaned ? shortText(cleaned, 42) : '';
};

const looksLikeArtifactName = (value: unknown) => {
  const text = normalizeText(value);
  return text ? ARTIFACT_PATTERNS.some((pattern) => pattern.test(text)) : false;
};

const looksLikeFileNameText = (value: unknown) => {
  const text = normalizeText(value);
  if (!text) return false;
  return /[\\/]/.test(text) || /\.(pdf|doc|docx|xls|xlsx|csv|txt|md|json|png|jpe?g|webp)$/i.test(text);
};

const looksLikePlaceholderText = (value: unknown) => {
  const text = normalizeText(value);
  if (!text) return true;
  const stripped = text.replace(/[?？·|/\\()[\]{}:;,.，。、“”‘’"'`~!@#$%^&*_+=-]+/g, '');
  return !/[A-Za-z0-9\u4e00-\u9fa5]/.test(stripped);
};

const looksLikeLowSignalArtifactTitle = (value: unknown, objectId: unknown = '') => {
  const text = cleanArtifactText(value);
  if (!text) return true;
  if (looksLikePlaceholderText(text)) return true;
  if (looksLikeFileNameText(text)) return true;
  const lower = text.toLowerCase();
  if (/^(?:位于)?第?\s*\d+\s*页$/i.test(text)) return true;
  if (/^(?:page|p)\s*\d+$/i.test(lower)) return true;
  const normalizedObjectId = normalizeText(objectId).toLowerCase();
  if (normalizedObjectId && lower.includes(normalizedObjectId)) return true;
  return /(?:^|\s)(table|figure|image|fig)[\s_-]*\d+(?:\s|$)/i.test(lower);
};

const looksLikeSystemGeneratedName = (value: unknown) => {
  const text = normalizeTypeKey(value);
  if (!text) return false;
  return [
    /^create_final_/,
    /^(entity|community|document|chunk|field|node|text_unit|relationship)[_-]?\d+$/,
    /^(graph|artifact|report|summary|cluster)[_-]?\d+$/,
    /^unnamed/,
  ].some((pattern) => pattern.test(text));
};

const looksLikeLowSignalEntityName = (value: unknown) => {
  const text = stripWrappingQuotes(value).replace(/\s+/g, '');
  if (!text) return true;
  return [
    /^\d{4,}$/,
    /^[A-Z]{0,3}\d{5,}$/i,
    /^[0-9a-f]{12,}$/i,
    /^\d+(?:\.\d+)?%?$/,
  ].some((pattern) => pattern.test(text));
};

const humanizeWarning = (value: unknown) => {
  const text = normalizeText(value);
  if (!text) return '';
  const [code, ...rest] = text.split(':');
  const titleMap: Record<string, string> = {
    quality_gate_degraded: '质量门控降级',
    field_extract_error: '字段抽取异常',
    table_extract_error: '表格抽取异常',
    parse_error: '解析异常',
    warning: '风险提示',
  };
  const label = titleMap[code] || prettifyToken(code);
  const detail = normalizeText(rest.join(':'));
  return detail ? `${label} · ${detail}` : label;
};

const alertFileHashOf = (alert: Module4AlertItem) => {
  const payload = asRecord(alert.payload);
  return firstText(payload.file_hash, nestedText(payload, 'context', 'file_hash'));
};

const typeKeyOf = (node: Module4GraphNode | string) => {
  if (typeof node === 'string') return normalizeTypeKey(node);
  return normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
};

const presentTypeLabel = (node: Module4GraphNode | string) => {
  const key = typeKeyOf(node);
  if (TYPE_LABELS[key]) return TYPE_LABELS[key];
  if (typeof node === 'string') return prettifyToken(key);
  return prettifyToken(firstText(node.type_label, node.category, node.node_type, '节点'));
};

const legacyPresentRelationLabel = (edge: Module4GraphEdge) =>
  RELATION_LABELS[normalizeTypeKey(edge.relation_label || edge.relation_type)] ||
  prettifyToken(firstText(edge.relation_label, edge.relation_type, '关联'));

const presentRelationLabel = (edge: Module4GraphEdge) =>
  (normalizeTypeKey(edge.relation_label || edge.relation_type) === 'overview_context'
    ? '文档上下文'
    : '') ||
  RELATION_LABELS[normalizeTypeKey(edge.relation_label || edge.relation_type)] ||
  prettifyToken(firstText(edge.relation_label, edge.relation_type, '关系'));

const relationLabelOf = (edge: Module4GraphEdge) => {
  const key = normalizeTypeKey(edge.relation_label || edge.relation_type);
  if (key === 'overview_context') return '概览上下文';
  return RELATION_LABELS[key] || prettifyToken(firstText(edge.relation_label, edge.relation_type, '关系'));
};

const typePriority = (value: string) => {
  const key = normalizeTypeKey(value);
  if (key === 'community') return 0;
  if (key === 'entity') return 1;
  if (key === 'document') return 2;
  if (key === 'risk') return 3;
  if (key === 'table') return 4;
  if (key === 'figure' || key === 'image') return 5;
  if (key === 'chunk') return 6;
  if (key === 'field') return 7;
  return 8;
};

const nodeRoleOf = (node: Module4GraphNode): GraphNodeRole => {
  const key = typeKeyOf(node);
  if (key === 'document') return 'anchor';
  if (key === 'entity' || key === 'community' || key === 'risk') return 'semantic';
  if (key === 'figure' || key === 'image' || key === 'table') return 'evidence';
  return 'structural';
};

const edgeRoleOf = (edge: Module4GraphEdge): GraphEdgeRole => {
  const key = normalizeTypeKey(edge.relation_type || edge.relation_label);
  if (key === 'overview_context') return 'anchor';
  if (OVERVIEW_SEMANTIC_RELATIONS.has(key)) return 'semantic';
  if (key.includes('evidence')) return 'evidence';
  return 'structural';
};

const buildEdgeDegreeMap = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const degreeMap = new Map<string, number>();
  nodes.forEach((node) => degreeMap.set(node.node_id, 0));
  edges.forEach((edge) => {
    degreeMap.set(edge.source_node_id, (degreeMap.get(edge.source_node_id) || 0) + 1);
    degreeMap.set(edge.target_node_id, (degreeMap.get(edge.target_node_id) || 0) + 1);
  });
  return degreeMap;
};

const pickLayoutRootId = (nodes: Module4GraphNode[], degreeMap: Map<string, number>) => {
  if (!nodes.length) return '';

  const rankNode = (node: Module4GraphNode) => ({
    node,
    isDocument: typeKeyOf(node) === 'document' ? 1 : 0,
    degree: degreeMap.get(node.node_id) || 0,
    typePriorityValue: typePriority(typeKeyOf(node)),
    label: displayNameOfNode(node),
  });

  return [...nodes]
    .map(rankNode)
    .sort((left, right) => {
      if (right.isDocument !== left.isDocument) return right.isDocument - left.isDocument;
      if (right.degree !== left.degree) return right.degree - left.degree;
      if (left.typePriorityValue !== right.typePriorityValue) {
        return left.typePriorityValue - right.typePriorityValue;
      }
      return left.label.localeCompare(right.label, 'zh-CN');
    })[0]?.node.node_id;
};

type NodeImportanceContext = {
  degreeMap: Map<string, number>;
  maxDegree: number;
  averageDegree: number;
  denseNodeThreshold: number;
  rootNodeId: string;
};

const buildNodeImportanceContext = (
  nodes: Module4GraphNode[],
  edges: Module4GraphEdge[]
): NodeImportanceContext => {
  const degreeMap = buildEdgeDegreeMap(nodes, edges);
  const degrees = nodes.map((node) => degreeMap.get(node.node_id) || 0);
  const maxDegree = Math.max(1, ...degrees);
  const averageDegree =
    degrees.length > 0 ? degrees.reduce((sum, degree) => sum + degree, 0) / degrees.length : 0;
  const denseNodeThreshold = Math.max(2, Math.ceil(averageDegree + Math.max(1.4, maxDegree * 0.16)));
  return {
    degreeMap,
    maxDegree,
    averageDegree,
    denseNodeThreshold,
    rootNodeId: pickLayoutRootId(nodes, degreeMap),
  };
};

const emphasisTierWeight = (tier: NodeEmphasisTier) => {
  if (tier === 'primary') return 1;
  if (tier === 'secondary') return 0.72;
  if (tier === 'tertiary') return 0.42;
  return 0;
};

const emphasisTierOfNode = (
  node: Module4GraphNode,
  degree: number,
  context: NodeImportanceContext
): NodeEmphasisTier => {
  const typeKey = typeKeyOf(node);
  const normalizedDegree = degree / Math.max(1, context.maxDegree);
  const isRoot = node.node_id === context.rootNodeId;
  const clearlyDense = degree >= context.denseNodeThreshold;

  if (typeKey === 'document' || (isRoot && normalizedDegree >= 0.82)) {
    return 'primary';
  }

  if (typeKey === 'community' && (normalizedDegree >= 0.38 || clearlyDense)) {
    return 'secondary';
  }

  if ((typeKey === 'entity' || typeKey === 'chunk' || typeKey === 'risk') && normalizedDegree >= 0.3) {
    return 'secondary';
  }

  if (
    clearlyDense ||
    normalizedDegree >= 0.22 ||
    ((typeKey === 'document' || typeKey === 'community') && degree > 0)
  ) {
    return 'tertiary';
  }

  return 'normal';
};

const nodeImportanceOf = (
  node: Module4GraphNode,
  degree: number,
  tier: NodeEmphasisTier,
  context: NodeImportanceContext
) => {
  const typeKey = typeKeyOf(node);
  const normalizedDegree = clamp(degree / Math.max(1, context.maxDegree), 0, 1);
  const typeBias =
    typeKey === 'document'
      ? 0.84
      : typeKey === 'community'
        ? 0.62
        : typeKey === 'entity'
          ? 0.44
          : typeKey === 'risk'
            ? 0.38
            : typeKey === 'chunk'
              ? 0.28
              : 0.2;
  const confidenceBias = clamp(Number(node.confidence || 0.55), 0.18, 1) * 0.12;
  const densityBias = normalizedDegree * 0.74;
  return clamp(typeBias + densityBias + confidenceBias + emphasisTierWeight(tier) * 0.34, 0, 1.85);
};

const edgePriorityScore = (
  edge: Module4GraphEdge,
  degreeMap: Map<string, number>,
  nodeMap: Map<string, Module4GraphNode>
) => {
  const source = nodeMap.get(edge.source_node_id);
  const target = nodeMap.get(edge.target_node_id);
  const sourceScore = degreeMap.get(edge.source_node_id) || 0;
  const targetScore = degreeMap.get(edge.target_node_id) || 0;
  const roleBonus =
    (source ? (nodeRoleOf(source) === 'semantic' ? 1.4 : 0.6) : 0) +
    (target ? (nodeRoleOf(target) === 'semantic' ? 1.4 : 0.6) : 0);
  return sourceScore + targetScore + roleBonus + Number(edge.confidence || 0);
};

const buildOverviewAnchorEdges = (
  documentNodes: Module4GraphNode[],
  semanticNodes: Module4GraphNode[],
  degreeMap: Map<string, number>
): Module4GraphEdge[] => {
  const anchor = documentNodes[0];
  if (!anchor) return [];

  const communityTargets = semanticNodes
    .filter((node) => typeKeyOf(node) === 'community')
    .sort((left, right) => (degreeMap.get(right.node_id) || 0) - (degreeMap.get(left.node_id) || 0))
    .slice(0, 2);

  const fallbackTargets =
    communityTargets.length > 0
      ? communityTargets
      : semanticNodes
          .filter((node) => typeKeyOf(node) === 'entity')
          .sort((left, right) => (degreeMap.get(right.node_id) || 0) - (degreeMap.get(left.node_id) || 0))
          .slice(0, 3);

  return fallbackTargets.map((target, index) => ({
    edge_id: `overview-anchor:${anchor.node_id}:${target.node_id}:${index}`,
    source_node_id: anchor.node_id,
    target_node_id: target.node_id,
    relation_type: 'OVERVIEW_CONTEXT',
    relation_label: 'Overview Context',
    direction: 'out',
    confidence: 1,
    risk_score: 0,
    attrs: {
      synthetic: true,
      edge_role: 'anchor',
      projection_mode: 'overview',
    },
    updated_at: null,
  }));
};

const OVERVIEW_MAX_ENTITY_NODES = 22;
const OVERVIEW_MAX_SEMANTIC_EDGES = 28;
const OVERVIEW_MAX_SEMANTIC_EDGES_PER_NODE = 3;

const overviewNodeScore = (node: Module4GraphNode, degreeMap: Map<string, number>) => {
  const key = typeKeyOf(node);
  const attrs = asRecord(node.attrs);
  const entityType = normalizeTypeKey(firstText(attrs.entity_type, attrs.object_type));
  const rawDisplay = firstText(node.display_name, attrs.name, attrs.title);
  let score = (degreeMap.get(node.node_id) || 0) * 8 + Number(node.confidence || 0) * 4;

  if (key === 'document') score += 240;
  if (key === 'community') score += 180;
  if (entityType.includes('geo') || entityType.includes('organization') || entityType.includes('event')) {
    score += 12;
  }
  if (!looksLikeLowSignalEntityName(rawDisplay)) score += 4;
  return score;
};

const sparsifyOverviewSemanticEdges = (
  edges: Module4GraphEdge[],
  degreeMap: Map<string, number>,
  nodeMap: Map<string, Module4GraphNode>
) => {
  if (edges.length <= OVERVIEW_MAX_SEMANTIC_EDGES) return edges;

  const usage = new Map<string, number>();
  const keep: Module4GraphEdge[] = [];

  for (const edge of [...edges].sort(
    (left, right) =>
      edgePriorityScore(right, degreeMap, nodeMap) - edgePriorityScore(left, degreeMap, nodeMap)
  )) {
    const sourceUsage = usage.get(edge.source_node_id) || 0;
    const targetUsage = usage.get(edge.target_node_id) || 0;
    if (sourceUsage >= OVERVIEW_MAX_SEMANTIC_EDGES_PER_NODE) continue;
    if (targetUsage >= OVERVIEW_MAX_SEMANTIC_EDGES_PER_NODE) continue;

    keep.push(edge);
    usage.set(edge.source_node_id, sourceUsage + 1);
    usage.set(edge.target_node_id, targetUsage + 1);
    if (keep.length >= OVERVIEW_MAX_SEMANTIC_EDGES) break;
  }

  return keep.length
    ? keep
    : [...edges]
        .sort(
          (left, right) =>
            edgePriorityScore(right, degreeMap, nodeMap) - edgePriorityScore(left, degreeMap, nodeMap)
        )
        .slice(0, OVERVIEW_MAX_SEMANTIC_EDGES);
};

const buildOverviewGraph = (graph: Module4GraphResponse): Module4GraphResponse => {
  const visibleNodes = graph.nodes.filter((node) => OVERVIEW_NODE_TYPES.has(typeKeyOf(node)));
  if (visibleNodes.length === 0) {
    return EMPTY_GRAPH;
  }

  const visibleNodeMap = new Map(visibleNodes.map((node) => [node.node_id, node]));
  const semanticEdges = graph.edges.filter((edge) => {
    const relationKey = normalizeTypeKey(edge.relation_type || edge.relation_label);
    return (
      visibleNodeMap.has(edge.source_node_id) &&
      visibleNodeMap.has(edge.target_node_id) &&
      OVERVIEW_SEMANTIC_RELATIONS.has(relationKey)
    );
  });

  const communityEdges = graph.edges.filter((edge) => {
    const relationKey = normalizeTypeKey(edge.relation_type || edge.relation_label);
    return (
      visibleNodeMap.has(edge.source_node_id) &&
      visibleNodeMap.has(edge.target_node_id) &&
      OVERVIEW_COMMUNITY_RELATIONS.has(relationKey)
    );
  });

  const overviewDegreeMap = buildEdgeDegreeMap(visibleNodes, [...semanticEdges, ...communityEdges]);

  const communityBuckets = new Map<string, Module4GraphEdge[]>();
  communityEdges.forEach((edge) => {
    const source = visibleNodeMap.get(edge.source_node_id);
    const target = visibleNodeMap.get(edge.target_node_id);
    if (!source || !target) return;
    const communityId =
      typeKeyOf(source) === 'community' ? source.node_id : typeKeyOf(target) === 'community' ? target.node_id : '';
    if (!communityId) return;
    const bucket = communityBuckets.get(communityId) || [];
    bucket.push(edge);
    communityBuckets.set(communityId, bucket);
  });

  const documentNodes = visibleNodes.filter((node) => typeKeyOf(node) === 'document');
  const communityNodes = visibleNodes.filter((node) => typeKeyOf(node) === 'community');
  const entityNodes = visibleNodes.filter((node) => {
    const key = typeKeyOf(node);
    return key !== 'document' && key !== 'community';
  });
  const retainedEntities =
    entityNodes.length <= OVERVIEW_MAX_ENTITY_NODES
      ? entityNodes
      : [...entityNodes]
          .sort((left, right) => overviewNodeScore(right, overviewDegreeMap) - overviewNodeScore(left, overviewDegreeMap))
          .slice(0, OVERVIEW_MAX_ENTITY_NODES);
  const candidateNodes = [...documentNodes, ...communityNodes, ...retainedEntities];
  const candidateNodeIds = new Set(candidateNodes.map((node) => node.node_id));
  const candidateNodeMap = new Map(candidateNodes.map((node) => [node.node_id, node]));

  const skeletonEdges: Module4GraphEdge[] = [];
  communityBuckets.forEach((bucket) => {
    bucket
      .filter((edge) => candidateNodeIds.has(edge.source_node_id) && candidateNodeIds.has(edge.target_node_id))
      .sort(
        (left, right) =>
          edgePriorityScore(right, overviewDegreeMap, candidateNodeMap) -
          edgePriorityScore(left, overviewDegreeMap, candidateNodeMap)
      )
      .slice(0, Math.min(3, bucket.length))
      .forEach((edge) => skeletonEdges.push(edge));
  });

  const sparsifiedSemanticEdges = sparsifyOverviewSemanticEdges(
    semanticEdges.filter((edge) => candidateNodeIds.has(edge.source_node_id) && candidateNodeIds.has(edge.target_node_id)),
    overviewDegreeMap,
    candidateNodeMap
  );

  const retainedEdges = [...sparsifiedSemanticEdges, ...skeletonEdges];
  const retainedNodeIds = new Set<string>();
  retainedEdges.forEach((edge) => {
    retainedNodeIds.add(edge.source_node_id);
    retainedNodeIds.add(edge.target_node_id);
  });

  const anchorEdges = buildOverviewAnchorEdges(documentNodes, [...communityNodes, ...retainedEntities], overviewDegreeMap);
  anchorEdges.forEach((edge) => {
    retainedNodeIds.add(edge.source_node_id);
    retainedNodeIds.add(edge.target_node_id);
  });

  let retainedNodes = candidateNodes.filter((node) => retainedNodeIds.has(node.node_id));
  if (retainedNodes.length < Math.min(candidateNodes.length, 4)) {
    retainedNodes = candidateNodes.slice(0, Math.min(candidateNodes.length, 8));
  }

  const nodes = retainedNodes.map((node) => ({
    ...node,
    attrs: {
      ...asRecord(node.attrs),
      node_role: nodeRoleOf(node),
      projection_mode: 'overview',
    },
  }));
  const nodeMap = new Map(nodes.map((node) => [node.node_id, node]));
  const edges = [...retainedEdges, ...anchorEdges]
    .filter((edge) => nodeMap.has(edge.source_node_id) && nodeMap.has(edge.target_node_id))
    .map((edge) => ({
      ...edge,
      attrs: {
        ...asRecord(edge.attrs),
        edge_role: edgeRoleOf(edge),
        projection_mode: 'overview',
      },
    }));

  return {
    nodes,
    edges,
    source: graph.source,
    workspace_id: graph.workspace_id || null,
    stats: buildStats(nodes, edges),
  };
};

const overviewProjectionHasSignal = (graph: Module4GraphResponse) => {
  if (graph.edges.length > 0) return true;
  if (graph.nodes.length > 1) return true;
  return graph.nodes.some((node) => typeKeyOf(node) !== 'document');
};

const shouldPreferEvidenceGraph = (rawGraph: Module4GraphResponse, overviewGraph: Module4GraphResponse) => {
  if (rawGraph.nodes.length === 0) return false;
  if (rawGraph.nodes.length === 1 && rawGraph.edges.length === 0) return false;
  return !overviewProjectionHasSignal(overviewGraph);
};

const preferredFitNodeIds = (graph: Module4GraphResponse, viewMode: GraphViewMode) => {
  if (!graph.nodes.length) return [];
  if (viewMode === 'evidence') {
    return graph.nodes.map((node) => node.node_id);
  }

  const degreeMap = buildEdgeDegreeMap(graph.nodes, graph.edges);
  const prioritized = graph.nodes.filter((node) => {
    const key = typeKeyOf(node);
    const degree = degreeMap.get(node.node_id) || 0;
    if (key === 'document') return true;
    if (key === 'community') return true;
    return degree > 0;
  });

  return (prioritized.length >= 4 ? prioritized : graph.nodes).map((node) => node.node_id);
};

const visualSpecOf = (node: Module4GraphNode) => {
  const key = typeKeyOf(node);
  const attrs = asRecord(node.attrs);
  const entityType = normalizeTypeKey(firstText(attrs.entity_type, attrs.object_type));

  if (key === 'document') return { color: '#2563EB', size: 50, minRadius: 24, maxRadius: 34 };
  if (key === 'entity') {
    if (entityType.includes('geo')) return { color: '#0F766E', size: 50, minRadius: 18, maxRadius: 28 };
    if (entityType.includes('organization')) return { color: '#2563EB', size: 50, minRadius: 18, maxRadius: 28 };
    if (entityType.includes('person')) return { color: '#E11D48', size: 50, minRadius: 18, maxRadius: 28 };
    if (entityType.includes('event')) return { color: '#F97316', size: 50, minRadius: 18, maxRadius: 28 };
    if (entityType.includes('indicator')) return { color: '#7C3AED', size: 50, minRadius: 18, maxRadius: 27 };
    if (entityType.includes('facility')) return { color: '#0891B2', size: 50, minRadius: 18, maxRadius: 27 };
    if (entityType.includes('project')) return { color: '#0EA5E9', size: 50, minRadius: 18, maxRadius: 27 };
    if (entityType.includes('material')) return { color: '#EA580C', size: 50, minRadius: 18, maxRadius: 27 };
    return { color: '#4F46E5', size: 50, minRadius: 18, maxRadius: 28 };
  }
  if (key === 'field') return { color: '#4F46E5', size: 44, minRadius: 14, maxRadius: 22 };
  if (key === 'community') return { color: '#D97706', size: 52, minRadius: 21, maxRadius: 32 };
  if (key === 'risk') return { color: '#F97316', size: 50, minRadius: 18, maxRadius: 28 };
  if (key === 'figure' || key === 'image') return { color: '#0EA5E9', size: 42, minRadius: 14, maxRadius: 22 };
  if (key === 'table') return { color: '#14B8A6', size: 44, minRadius: 15, maxRadius: 23 };
  if (key === 'chunk') return { color: '#64748B', size: 40, minRadius: 12, maxRadius: 20 };
  return { color: '#475569', size: 44, minRadius: 14, maxRadius: 22 };
};

const relationToneOf = (edge: Module4GraphEdge | string) => {
  const key = normalizeTypeKey(typeof edge === 'string' ? edge : edge.relation_type);
  if (key.includes('overview_context')) return '#CBD5E1';
  if (key.includes('community')) return '#F59E0B';
  if (key.includes('entity') || key.includes('field')) return '#4F46E5';
  if (key.includes('warning') || key.includes('risk')) return '#F97316';
  if (key.includes('contain') || key.includes('part')) return '#2563EB';
  if (key.includes('evidence')) return '#14B8A6';
  return '#94A3B8';
};

const titleFromSnippet = (snippet: string, typeKey: string) => {
  const cleaned = cleanArtifactText(snippet);
  if (!cleaned) return '';

  if (typeKey === 'figure' || typeKey === 'image') {
    const figureMatch =
      cleaned.match(/(图\s*\d+[^\|]*)/i) ||
      cleaned.match(/(figure\s*\d+[^\|]*)/i) ||
      cleaned.match(/([^|]+)/);
    return cleanArtifactText(figureMatch?.[1] || cleaned);
  }

  if (typeKey === 'table') {
    const titleMatch = cleaned.match(/标题[:：]?\s*([^|]+)/);
    if (titleMatch?.[1]) return `表格 · ${cleanArtifactText(titleMatch[1])}`;
    return cleanArtifactText(cleaned.split('|')[0] || cleaned);
  }

  return cleanArtifactText(cleaned.split('|')[0] || cleaned);
};

const fallbackEntityName = (value: unknown, humanReadableId: unknown) => {
  const normalized = normalizeTypeKey(value);
  const label = GENERIC_ENTITY_NAME_MAP[normalized];
  if (!label) return '';
  const suffix = normalizeText(humanReadableId);
  return suffix ? `${label} #${suffix}` : label;
};

const displayNameOfNode = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const context = asRecord(attrs.context);
  const key = typeKeyOf(node);
  const rawDisplay = firstText(node.display_name, node.canonical_key, node.node_id);
  const cleanedDisplay = cleanArtifactText(rawDisplay);
  const primaryDisplay = looksLikeSystemGeneratedName(cleanedDisplay) ? '' : cleanedDisplay;

  if (key === 'entity') {
    return firstText(
      looksLikeLowSignalEntityName(primaryDisplay) ? '' : primaryDisplay,
      cleanArtifactText(firstText(attrs.name, attrs.title)),
      fallbackEntityName(firstText(attrs.entity_type, attrs.object_type), attrs.human_readable_id),
      extractSemanticTitle(attrs.description),
      fallbackEntityName(primaryDisplay || cleanedDisplay, attrs.human_readable_id),
      presentTypeLabel(node)
    );
  }

  if (key === 'document') {
    return firstText(
      humanizeDocumentName(attrs.file_name),
      humanizeDocumentName(primaryDisplay || cleanedDisplay),
      extractSemanticTitle(attrs.raw_content),
      extractSemanticTitle(attrs.text),
      '文档'
    );
  }

  if (key === 'community') {
    return firstText(
      cleanArtifactText(firstText(attrs.title, attrs.name, attrs.community_title, attrs.report_title)),
      extractSemanticTitle(firstText(attrs.summary, attrs.description, attrs.text, attrs.raw_content)),
      primaryDisplay,
      presentTypeLabel(node)
    );
  }

  if (key === 'field') {
    return firstText(
      cleanArtifactText(firstText(attrs.field_name, attrs.name, attrs.title)),
      primaryDisplay,
      presentTypeLabel(node)
    );
  }

  if (key === 'risk') {
    return firstText(humanizeWarning(attrs.warning), cleanedDisplay, '风险提示');
  }

  if (key === 'chunk') {
    return firstText(
      extractSemanticTitle(attrs.text),
      extractSemanticTitle(attrs.raw_content),
      titleFromSnippet(firstText(attrs.snippet, attrs.text, cleanedDisplay), key),
      '文本片段'
    );
  }

  if (key === 'table' || key === 'figure' || key === 'image') {
    const label = presentTypeLabel(node);
    const captionHint = cleanArtifactText(nestedText(context, 'caption_hint'));
    const snippetTitle = titleFromSnippet(firstText(attrs.snippet, captionHint), key);
    const directTitle = cleanArtifactText(firstText(attrs.title, attrs.caption, attrs.name));
    const objectId = firstText(attrs.object_id, node.display_name);
    const artifactTitle = firstText(
      looksLikeLowSignalArtifactTitle(directTitle, objectId) ? '' : directTitle,
      looksLikeLowSignalArtifactTitle(captionHint, objectId) ? '' : captionHint,
      looksLikeLowSignalArtifactTitle(snippetTitle, objectId) ? '' : snippetTitle
    );
    const page = pageLocatorOfNode(node);

    return firstText(
      artifactTitle ? `${label} · ${artifactTitle}` : '',
      page ? `${label} · ${page}` : '',
      !looksLikeArtifactName(rawDisplay) && !looksLikePlaceholderText(primaryDisplay) ? primaryDisplay : '',
      !looksLikePlaceholderText(cleanedDisplay) ? cleanedDisplay : '',
      label
    );
  }

  if (!looksLikeArtifactName(rawDisplay) && primaryDisplay) {
    return primaryDisplay;
  }

  return firstText(
    extractSemanticTitle(attrs.description),
    cleanArtifactText(nestedText(context, 'caption_hint')),
    titleFromSnippet(firstText(attrs.snippet, nestedText(context, 'caption_hint')), key),
    cleanArtifactText(firstText(attrs.title, attrs.name, attrs.file_name)),
    primaryDisplay,
    cleanedDisplay,
    presentTypeLabel(node)
  );
};

const pageLocatorOfNode = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const context = asRecord(attrs.context);
  const page = firstText(attrs.page_no, attrs.page, nestedText(context, 'page'));
  return page ? `P${page}` : '';
};

const isRedundantArtifactPageSnippet = (node: Module4GraphNode, snippet: string) => {
  const typeKey = typeKeyOf(node);
  if (!(typeKey === 'table' || typeKey === 'figure' || typeKey === 'image')) return false;
  const page = pageLocatorOfNode(node);
  if (!page) return false;

  const normalizedSnippet = normalizeText(snippet).toLowerCase();
  const normalizedPage = page.toLowerCase();
  if (normalizedSnippet.includes(normalizedPage)) return true;

  const pageNumber = normalizedPage.replace(/^p/, '');
  const numericMatches = normalizedSnippet.match(/\d+/g) || [];
  if (numericMatches.length !== 1 || numericMatches[0] !== pageNumber) return false;

  return normalizedSnippet.length <= 16;
};

const isGenericArtifactCaption = (value: string, typeKey: string) => {
  const text = normalizeText(value);
  if (!text) return true;
  const lower = text.toLowerCase();

  if (typeKey === 'table') {
    return lower === 'table' || /^table\b/.test(lower) || /^(表格|表)$/.test(text) || text.length <= 3;
  }

  if (typeKey === 'figure' || typeKey === 'image') {
    return (
      lower === 'image' ||
      lower === 'figure' ||
      lower === 'fig' ||
      /^formula/.test(lower) ||
      /^(图像|图片|插图|公式图像)$/.test(text) ||
      text.length <= 4
    );
  }

  return false;
};

const compactDocumentCaption = (value: string) =>
  normalizeText(stripFileExtension(value))
    .replace(/[（(][^）)]{4,16}[）)]/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();

const captionOfNode = (node: Module4GraphNode, max = 22) => {
  const base = displayNameOfNode(node);
  const attrs = asRecord(node.attrs);
  const typeKey = typeKeyOf(node);
  const compact = typeKey === 'document' ? compactDocumentCaption(base) || stripFileExtension(base) : base;
  const maxLength = typeKey === 'document' ? Math.min(max, 18) : typeKey === 'chunk' ? Math.min(max, 16) : max;

  if (typeKey === 'table' || typeKey === 'figure' || typeKey === 'image') {
    const page = pageLocatorOfNode(node);
    const candidate = cleanArtifactText(compact);

    if (isGenericArtifactCaption(candidate, typeKey)) {
      const refinedTitle = cleanArtifactText(firstText(attrs.title, attrs.name));
      const artifactBase =
        refinedTitle && !looksLikeArtifactName(refinedTitle)
          ? `${presentTypeLabel(node)} · ${refinedTitle}`
          : page
            ? `${presentTypeLabel(node)} · ${page}`
            : presentTypeLabel(node);
      return shortText(artifactBase, Math.max(10, maxLength));
    }

    const candidateHasPage = Boolean(page) && normalizeText(candidate).toLowerCase().includes(page.toLowerCase());
    return shortText(page && !candidateHasPage ? `${candidate} · ${page}` : candidate, maxLength);
  }

  return shortText(compact, maxLength);
};

const summaryOfNode = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const diagnostics = asRecord(attrs.diagnostics);
  const context = asRecord(attrs.context);
  const warning = humanizeWarning(attrs.warning);
  if (warning) return shortText(warning, 180);

  const snippet = cleanArtifactText(
    firstText(
      nestedText(context, 'caption_hint'),
      attrs.snippet,
      nestedText(context, 'nearby_text'),
      extractSemanticTitle(attrs.text),
      extractSemanticTitle(attrs.raw_content)
    )
  );
  if (snippet && !isRedundantArtifactPageSnippet(node, snippet)) return shortText(snippet, 180);

  if (typeKeyOf(node) === 'document') {
    const parts = [
      numberOrNull(diagnostics.figure_count) ? `${diagnostics.figure_count} 张图` : '',
      numberOrNull(diagnostics.table_count) ? `${diagnostics.table_count} 张表` : '',
      numberOrNull(diagnostics.trace_hit_count) ? `${diagnostics.trace_hit_count} 条证据` : '',
      firstText(diagnostics.quality_status) ? `质量 ${diagnostics.quality_status}` : '',
    ].filter(Boolean);
    if (parts.length) return parts.join(' · ');
  }

  return '';
};

const detailFactsOfNode = (node: Module4GraphNode): DetailFact[] => {
  const attrs = asRecord(node.attrs);
  const diagnostics = asRecord(attrs.diagnostics);
  const context = asRecord(attrs.context);
  const facts: DetailFact[] = [];

  const push = (label: string, value: unknown) => {
    const text = normalizeText(value);
    if (!text) return;
    if (facts.some((item) => item.label === label && item.value === text)) return;
    facts.push({ label, value: text });
  };

  push('类型', presentTypeLabel(node));
  push('来源文档', firstText(attrs.source_doc, attrs.file_name, nestedText(context, 'doc_name')));
  if (firstText(attrs.page, nestedText(context, 'page'))) {
    push('页码', `第 ${firstText(attrs.page, nestedText(context, 'page'))} 页`);
  }
  if (node.confidence > 0) push('置信度', `${Math.round(node.confidence * 100)}%`);
  push('对象类型', attrs.object_type);
  if (numberOrNull(diagnostics.figure_count)) push('图像数', diagnostics.figure_count);
  if (numberOrNull(diagnostics.table_count)) push('表格数', diagnostics.table_count);
  push('质量状态', diagnostics.quality_status);

  return facts.slice(0, 8);
};

const attributeRowsOfNode = (node: Module4GraphNode): DetailFact[] => {
  const attrs = asRecord(node.attrs);
  const context = asRecord(attrs.context);
  const rows: DetailFact[] = [];
  const snippet = cleanArtifactText(firstText(attrs.snippet, nestedText(context, 'caption_hint')));

  const push = (label: string, value: unknown) => {
    const text = normalizeText(value);
    if (!text) return;
    if (rows.some((item) => item.label === label && item.value === text)) return;
    rows.push({ label, value: shortText(text, 200) });
  };

  if (snippet && !isRedundantArtifactPageSnippet(node, snippet)) {
    push('来源片段', snippet);
  }
  push('告警详情', humanizeWarning(attrs.warning));
  push('引用 ID', firstText(attrs.source_ref_id, attrs.ref_id));
  push('文件哈希', attrs.file_hash);

  return rows.slice(0, 8);
};

const buildStats = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const byNodeType: Record<string, number> = {};
  const byRelationType: Record<string, number> = {};

  nodes.forEach((node) => {
    const key = presentTypeLabel(node);
    byNodeType[key] = (byNodeType[key] || 0) + 1;
  });

  edges.forEach((edge) => {
    const key = relationLabelOf(edge);
    byRelationType[key] = (byRelationType[key] || 0) + 1;
  });

  return {
    node_count: nodes.length,
    edge_count: edges.length,
    by_node_type: byNodeType,
    by_relation_type: byRelationType,
  };
};

type SeedLaneKey =
  | 'anchor'
  | 'semantic-primary'
  | 'semantic-secondary'
  | 'structural'
  | 'evidence-primary'
  | 'evidence-secondary'
  | 'risk';

const SEED_LANE_LAYOUT: Record<
  SeedLaneKey,
  {
    x: number;
    y: number;
    spacing: number;
    sway: number;
  }
> = {
  anchor: { x: -298, y: 8, spacing: 148, sway: 10 },
  'semantic-primary': { x: 96, y: -168, spacing: 120, sway: 18 },
  'semantic-secondary': { x: 262, y: -286, spacing: 108, sway: 14 },
  structural: { x: -12, y: 168, spacing: 104, sway: 14 },
  'evidence-primary': { x: 334, y: 92, spacing: 112, sway: 18 },
  'evidence-secondary': { x: 468, y: 232, spacing: 102, sway: 14 },
  risk: { x: 482, y: -156, spacing: 96, sway: 12 },
};

const GRAPH_LAYER_GUIDES = [
  {
    id: 'semantic',
    label: '语义层',
    lanes: ['semantic-primary', 'semantic-secondary'] as SeedLaneKey[],
    x: -18,
    y: -332,
    width: 412,
    height: 224,
    fill: 'rgba(15, 118, 110, 0.035)',
    stroke: 'rgba(15, 118, 110, 0.12)',
    text: '#0f766e',
  },
  {
    id: 'structural',
    label: '结构层',
    lanes: ['structural'] as SeedLaneKey[],
    x: -172,
    y: 96,
    width: 352,
    height: 212,
    fill: 'rgba(100, 116, 139, 0.04)',
    stroke: 'rgba(100, 116, 139, 0.12)',
    text: '#475569',
  },
  {
    id: 'evidence',
    label: '证据层',
    lanes: ['evidence-primary', 'evidence-secondary'] as SeedLaneKey[],
    x: 214,
    y: 24,
    width: 382,
    height: 324,
    fill: 'rgba(14, 165, 233, 0.035)',
    stroke: 'rgba(14, 165, 233, 0.12)',
    text: '#0369a1',
  },
  {
    id: 'risk',
    label: '风险层',
    lanes: ['risk'] as SeedLaneKey[],
    x: 406,
    y: -222,
    width: 164,
    height: 116,
    fill: 'rgba(249, 115, 22, 0.03)',
    stroke: 'rgba(249, 115, 22, 0.12)',
    text: '#c2410c',
  },
] as const;

const seedLaneOfNode = (node: Module4GraphNode, rootId: string): SeedLaneKey => {
  if (node.node_id === rootId || typeKeyOf(node) === 'document') return 'anchor';

  const typeKey = typeKeyOf(node);
  if (typeKey === 'community') return 'semantic-secondary';
  if (typeKey === 'entity') return 'semantic-primary';
  if (typeKey === 'risk') return 'risk';
  if (typeKey === 'table') return 'evidence-primary';
  if (typeKey === 'figure' || typeKey === 'image') return 'evidence-secondary';
  return 'structural';
};

const buildSeedPositions = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const positionMap = new Map<string, NodePositionState>();
  if (!nodes.length) return positionMap;
  const degreeMap = buildEdgeDegreeMap(nodes, edges);

  const adjacency = new Map<string, Set<string>>();
  nodes.forEach((node) => adjacency.set(node.node_id, new Set()));
  edges.forEach((edge) => {
    adjacency.get(edge.source_node_id)?.add(edge.target_node_id);
    adjacency.get(edge.target_node_id)?.add(edge.source_node_id);
  });

  const rankedNodes = [...nodes].sort((left, right) => {
    const degreeDiff = (adjacency.get(right.node_id)?.size || 0) - (adjacency.get(left.node_id)?.size || 0);
    if (degreeDiff !== 0) return degreeDiff;
    const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
    if (typeDiff !== 0) return typeDiff;
    return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
  });

  const rootId = pickLayoutRootId(rankedNodes, degreeMap) || rankedNodes[0]?.node_id || nodes[0]?.node_id;
  const groups = new Map<SeedLaneKey, Module4GraphNode[]>();
  nodes.forEach((node) => {
    const lane = seedLaneOfNode(node, rootId);
    const bucket = groups.get(lane) || [];
    bucket.push(node);
    groups.set(lane, bucket);
  });

  (
    [
      'anchor',
      'semantic-primary',
      'semantic-secondary',
      'structural',
      'evidence-primary',
      'evidence-secondary',
      'risk',
    ] as SeedLaneKey[]
  ).forEach((laneKey) => {
    const group = groups.get(laneKey) || [];
    if (group.length === 0) return;

    const lane = SEED_LANE_LAYOUT[laneKey];
    const ordered = [...group].sort((left, right) => {
      const leftAdjacency = adjacency.get(left.node_id)?.size || 0;
      const rightAdjacency = adjacency.get(right.node_id)?.size || 0;
      if (rightAdjacency !== leftAdjacency) return rightAdjacency - leftAdjacency;

      const degreeDiff = (degreeMap.get(right.node_id) || 0) - (degreeMap.get(left.node_id) || 0);
      if (degreeDiff !== 0) return degreeDiff;

      const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
      if (typeDiff !== 0) return typeDiff;

      return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
    });

    const totalHeight = Math.max(0, (ordered.length - 1) * lane.spacing);

    ordered.forEach((node, index) => {
      const offset = index - (ordered.length - 1) / 2;
      const sway = Math.sign(offset) * Math.min(Math.abs(offset) * lane.sway, lane.sway * 2.25);
      const x =
        lane.x +
        Math.abs(offset) * lane.sway * 0.42 +
        (node.node_id === rootId ? 0 : Math.min(22, (degreeMap.get(node.node_id) || 0) * 3));
      const y = lane.y + index * lane.spacing - totalHeight / 2 + sway;

      positionMap.set(node.node_id, {
        x,
        y,
      });
    });
  });

  return positionMap;
};

const mergeGraph = (left: Module4GraphResponse, right: Module4GraphResponse): Module4GraphResponse => {
  const nodeMap = new Map<string, Module4GraphNode>();
  const edgeMap = new Map<string, Module4GraphEdge>();

  [...left.nodes, ...right.nodes].forEach((node) => nodeMap.set(node.node_id, node));
  [...left.edges, ...right.edges].forEach((edge) => edgeMap.set(edge.edge_id, edge));

  const nodes = [...nodeMap.values()];
  const edges = [...edgeMap.values()];

  return {
    nodes,
    edges,
    source: right.source || left.source,
    workspace_id: right.workspace_id || left.workspace_id || null,
    stats: buildStats(nodes, edges),
  };
};

/* Legacy local fallback removed. Module 4 renders persisted state only.
  // Legacy fallback is intentionally disabled; Module 4 renders persisted state only.
  return EMPTY_GRAPH;

  documents.slice(0, 12).forEach((document, documentIndex) => {
    const documentId = `local-doc-${document.file_hash || documentIndex}`;
    nodes.push({
      node_id: documentId,
      node_type: 'Document',
      canonical_key: document.file_hash || documentId,
      display_name: document.file_name || `文档 ${documentIndex + 1}`,
      confidence: 1,
      type_label: '文档',
      category: '文档',
      attrs: {
        file_name: document.file_name,
        file_hash: document.file_hash,
        track: document.track,
        diagnostics: document.diagnostics || {},
      },
    });

    Object.entries(document.result || {})
      .slice(0, 16)
      .forEach(([fieldName, entity], fieldIndex) => {
        const nodeId = `${documentId}-field-${fieldIndex}`;
        nodes.push({
          node_id: nodeId,
          node_type: 'Field',
          canonical_key: `${document.file_hash || documentId}-${fieldName}`,
          display_name: fieldName,
          confidence: Number(entity?.confidence || 0),
          type_label: '字段',
          category: '字段',
          attrs: {
            source_doc: document.file_name,
            field_name: fieldName,
            value: entity?.value ?? '',
            source_ref_id: entity?.source_ref_id,
          },
        });

        edges.push({
          edge_id: `${documentId}-field-edge-${fieldIndex}`,
          source_node_id: documentId,
          target_node_id: nodeId,
          relation_type: 'HAS_FIELD',
          relation_label: '包含字段',
          direction: 'out',
          confidence: Number(entity?.confidence || 0),
          risk_score: 0,
          attrs: {},
        });
      });

    (document.trace_hits || []).slice(0, 6).forEach((hit, hitIndex) => {
      const nodeId = `${documentId}-trace-${hitIndex}`;
      const objectType = normalizeTypeKey(hit.object_type || 'chunk');
      const nodeType =
        objectType === 'table'
          ? 'Table'
          : objectType === 'figure' || objectType === 'image'
            ? 'Figure'
            : 'Chunk';

      nodes.push({
        node_id: nodeId,
        node_type: nodeType,
        canonical_key: `${document.file_hash || documentId}-${hit.object_id || hitIndex}`,
        display_name: firstText(hit.object_id, hit.object_type, `证据 ${hitIndex + 1}`),
        confidence: Number(hit.confidence || 0.68),
        type_label: presentTypeLabel(nodeType),
        category: presentTypeLabel(nodeType),
        attrs: {
          source_doc: document.file_name,
          object_type: hit.object_type,
          object_id: hit.object_id,
          snippet: hit.snippet,
          page: hit.page,
          artifact_url: hit.artifact_url,
          context: {
            caption_hint: hit.snippet,
            page: hit.page,
          },
        },
      });

      edges.push({
        edge_id: `${documentId}-trace-edge-${hitIndex}`,
        source_node_id: documentId,
        target_node_id: nodeId,
        relation_type: 'HAS_EVIDENCE',
        relation_label: '包含证据',
        direction: 'out',
        confidence: Number(hit.confidence || 0.68),
        risk_score: 0,
        attrs: {},
      });
    });

    (document.errors || []).slice(0, 4).forEach((errorText, errorIndex) => {
      const nodeId = `${documentId}-risk-${errorIndex}`;
      nodes.push({
        node_id: nodeId,
        node_type: 'Risk',
        canonical_key: `${document.file_hash || documentId}-risk-${errorIndex}`,
        display_name: `风险提示 ${errorIndex + 1}`,
        confidence: 0.72,
        type_label: '风险',
        category: '风险',
        attrs: {
          source_doc: document.file_name,
          warning: errorText,
        },
      });

      edges.push({
        edge_id: `${documentId}-warning-edge-${errorIndex}`,
        source_node_id: documentId,
        target_node_id: nodeId,
        relation_type: 'HAS_WARNING',
        relation_label: '风险提示',
        direction: 'out',
        confidence: 0.72,
        risk_score: 0.8,
        attrs: {},
      });
    });
  });

  return {
    nodes,
    edges,
    source: 'local-fallback',
    workspace_id: null,
    stats: buildStats(nodes, edges),
  };
*/

const selectionNeighborhoodOf = (graph: Module4GraphResponse, nodeId: string) => {
  if (!nodeId) return null;

  const edges = graph.edges.filter(
    (edge) => edge.source_node_id === nodeId || edge.target_node_id === nodeId
  );
  const nodeIds = new Set<string>([nodeId]);
  const edgeIds = new Set<string>();

  edges.forEach((edge) => {
    nodeIds.add(edge.source_node_id);
    nodeIds.add(edge.target_node_id);
    edgeIds.add(edge.edge_id);
  });

  return { nodeIds, edgeIds };
};

const subgraphForNode = (graph: Module4GraphResponse, nodeId: string): Module4GraphResponse => {
  const neighborhood = selectionNeighborhoodOf(graph, nodeId);
  if (!neighborhood) {
    const nodes = graph.nodes.filter((node) => node.node_id === nodeId);
    return {
      ...EMPTY_GRAPH,
      nodes,
      stats: buildStats(nodes, []),
    };
  }

  const nodes = graph.nodes.filter((node) => neighborhood.nodeIds.has(node.node_id));
  const edges = graph.edges.filter((edge) => neighborhood.edgeIds.has(edge.edge_id));
  return {
    nodes,
    edges,
    source: graph.source,
    workspace_id: graph.workspace_id || null,
    stats: buildStats(nodes, edges),
  };
};

const severityLabel = (value?: string) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'red') return '高风险';
  if (normalized === 'orange') return '中风险';
  if (normalized === 'yellow') return '需关注';
  return '未知';
};

const alertStatusLabel = (value?: string) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'open') return '待处理';
  if (normalized === 'ack') return '已确认';
  if (normalized === 'resolved') return '已解决';
  if (normalized === 'false_positive') return '误报';
  return '未知';
};

const UI_TEXT = {
  workspaceLabel: '模块四 / 图谱工作台',
  title: '知识图谱工作台',
  description: '围绕当前文件展示图谱状态、证据链、告警与运行诊断，确保每一条关系都能回到真实来源。',
  refreshGraph: '刷新图谱',
  module2FallbackSource: '模块二临时结果',
  module4Source: '模块四知识图谱',
  graphCanvas: '图谱画布',
  graphStatus: '当前状态',
  sourceSwitch: '文件来源',
  graphMode: '视图模式',
  layoutMode: '布局方式',
  forceLayout: '力导布局',
  hierarchicalLayout: '层级布局',
  overviewGraph: '概览图',
  evidenceGraph: '证据图',
  nodeCountMetric: '节点',
  edgeCountMetric: '关系',
  alertCountMetric: '待处理告警',
  utilityDockTitle: '检索与告警',
  utilityFiltersTitle: '检索与筛选',
  utilityFiltersSubtitle: '快速定位节点，并收束当前图谱展示范围。',
  expandUtilityDock: '展开辅助栏',
  collapseUtilityDock: '收起辅助栏',
  searchLabel: '搜索节点',
  searchPlaceholder: '搜索实体、表格、文档或风险',
  nodeTypesTitle: '节点类型',
  nodeTypesSubtitle: '按类型筛选当前图谱',
  clearFilters: '清空',
  alertsTitle: '待处理告警',
  alertsSubtitle: '点击后定位到对应节点并进入核查',
  noAlerts: '当前筛选范围内没有待处理告警。',
  riskScore: '风险分',
  acknowledging: '确认中...',
  acknowledge: '确认',
  resolving: '解决中...',
  resolve: '解决',
  currentSummary: '当前图谱',
  followActiveFile: '跟随当前文件',
  manualSelect: '手动选择',
  currentFile: '当前文件',
  selectGraphFile: '请选择图谱文件',
  switchToHierarchy: '切换为层级布局',
  switchToForce: '切换为力导布局',
  fitView: '适应视图',
  emptyGraphTitle: '当前没有可渲染的图谱',
  emptyGraphBody: '没有节点满足当前筛选条件，请清空筛选或等待模块四图谱同步完成。',
  zoomIn: '放大',
  zoomOut: '缩小',
  refresh: '刷新',
  detailsPanel: '节点详情',
  noNodeDetails: '选择图谱中的节点后，这里会显示属性、证据、关联关系与邻接节点。',
  pinned: '已固定',
  closeDetails: '关闭详情',
  unpinNode: '取消固定',
  pinNode: '固定节点',
  focusNode: '聚焦节点',
  expanding: '扩展中...',
  expandNeighborhood: '扩展邻域',
  relatedNodes: '相关节点',
  nodeAttributes: '节点属性',
  edgeRelations: '邻接关系',
  fileStatus: '图谱状态',
  truthStatus: '真实状态',
  stage: '处理阶段',
  projection: '投影状态',
  runtimeStatus: '运行状态',
  runtimeHealthy: '运行正常',
  runtimeDegraded: '运行降级',
  runtimeNotReady: '运行未就绪',
  jobStatus: '当前作业',
  jobIdle: '当前没有进行中的作业。',
  rulesTitle: '规则控制',
  rulesSubtitle: '直接查看命中规则，并在工作台内启停确定性规则。',
  noRules: '当前还没有可用的规则。',
  ruleEnabled: '已启用',
  ruleDisabled: '已停用',
  enableRule: '启用',
  disableRule: '停用',
  switchingRule: '切换中...',
  selectedRule: '当前规则',
  allEnabledRules: '全部启用规则',
  scopeLabel: '作用域',
  versionLabel: '版本',
  analysisTitle: '研判工具',
  analysisSubtitle: '对当前节点或关联告警直接做解释与模拟。',
  explainAction: '生成解释',
  simulateAction: '运行模拟',
  explaining: '解释中...',
  simulating: '模拟中...',
  explainSummary: '解释结论',
  reasoningSteps: '分析步骤',
  explainEvidence: '解释证据',
  noExplainResult: '还没有生成解释结果。',
  simulationSummary: '模拟摘要',
  simulationImpacts: '影响指标',
  simulationAlerts: '命中结果',
  noSimulateResult: '还没有生成模拟结果。',
  simulationNeedsAlert: '模拟需要当前节点下至少有一条关联告警。',
  analysisUnavailableInFallback: '当前处于模块二临时结果视图，解释与模拟仅在模块四主链路打通时可用。',
  fallbackWarning: '当前为临时过渡视图，不代表模块四图谱已经打通。',
  selectRuleHint: '可选择单条规则做定向模拟，也可保留为全部启用规则。',
  currentAnalysisTarget: '当前分析对象',
  nodeEvidence: '节点证据',
  edgeEvidence: '关系证据',
  noEvidence: '当前节点还没有可展示的证据。',
  noEdgeEvidence: '当前节点相邻关系还没有证据挂载。',
  evidenceSnippet: '证据片段',
  evidenceLocator: '定位信息',
  openArtifact: '打开来源',
  relatedAlerts: '关联告警',
  noRelatedAlerts: '当前节点没有关联告警。',
  module4Unavailable: '模块四图谱尚未就绪',
  usingFallback: '正在展示模块二临时结果，仅用于过渡核查',
} as const;

Object.assign(UI_TEXT, {
  workspaceLabel: '图谱核查台',
  title: '知识图谱工作台',
  description: '围绕当前文件查看图谱状态、证据链和风险告警，让每一条关系都能回到真实来源。',
  module2FallbackSource: '临时结果视图',
  module4Source: '知识图谱',
  graphCanvas: '图谱画布',
  graphStatus: '当前状态',
  layoutMode: '布局方式',
  runtimeStatus: '运行诊断',
  runtimeHealthy: '运行正常',
  runtimeDegraded: '需要关注',
  runtimeNotReady: '尚未就绪',
  jobStatus: '同步任务',
  module4Unavailable: '图谱尚未就绪',
  usingFallback: '当前展示的是临时过渡结果，仅用于核查过渡。',
});

Object.assign(UI_TEXT, {
  workspaceLabel: '图谱核查台',
  title: '知识图谱工作台',
  description: '围绕当前文件查看图谱状态、证据链和风险告警，让每一条关系都能回到真实来源。',
  module2FallbackSource: '临时结果视图',
  module4Source: '知识图谱',
  graphCanvas: '图谱画布',
  graphStatus: '当前状态',
  layoutMode: '布局方式',
  runtimeStatus: '运行诊断',
  runtimeHealthy: '运行正常',
  runtimeDegraded: '需重点关注',
  runtimeNotReady: '尚未就绪',
  jobStatus: '同步任务',
  emptyGraphBody: '当前筛选条件下没有可展示的节点，请调整筛选条件或等待图谱同步完成。',
  analysisUnavailableInFallback: '当前处于临时结果视图，解释与模拟需在知识图谱主链路同步完成后使用。',
  fallbackWarning: '当前展示的是临时过渡结果，不代表知识图谱主链路已经完全同步。',
  selectRuleHint: '可以选择单条规则进行定向核查，也可以保留为全部启用规则。',
  module4Unavailable: '图谱尚未就绪',
  usingFallback: '当前展示的是临时过渡结果，仅用于核查过渡。',
});

Object.assign(UI_TEXT, {
  workspaceLabel: '图谱工作台',
  title: '全域知识图谱',
  description: '围绕当前文档查看实体关系、证据链与风险告警，让图谱成为页面的主视角。',
});

const projectionStatusLabel = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'success') return '已完成';
  if (normalized === 'failed') return '失败';
  if (normalized === 'skipped') return '已跳过';
  return '待处理';
};

const graphFileStatusLabel = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'ready') return '已就绪';
  if (normalized === 'processing_documents') return '文档入图中';
  if (normalized === 'running') return '处理中';
  if (normalized === 'indexing') return '索引中';
  if (normalized === 'importing_graph') return '导图中';
  if (normalized === 'preparing_input') return '准备输入';
  if (normalized === 'queued') return '排队中';
  if (normalized === 'failed') return '失败';
  return normalized || '未知';
};

const jobStatusLabel = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'queued') return '排队中';
  if (normalized === 'running') return '处理中';
  if (normalized === 'success') return '已完成';
  if (normalized === 'failed') return '失败';
  if (normalized === 'cancelled') return '已取消';
  return '未知';
};

const jobTypeLabel = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'ingest') return '入图同步';
  if (normalized === 'rebuild_graph') return '重建图谱';
  if (normalized === 'run_rules') return '运行规则';
  if (normalized === 'simulate') return '情景模拟';
  return normalized || '未知';
};

const RULE_DISPLAY_NAME_MAP: Record<string, string> = {
  RULE_DOC_ERRORS: '文档解析异常',
  RULE_QUALITY_DEGRADED: '质量门控降级',
  RULE_LOW_CONFIDENCE: '低置信度抽取',
};

const ruleDisplayName = (rule?: Module4RuleItem | null) => {
  const ruleId = normalizeText(rule?.rule_id);
  if (ruleId && RULE_DISPLAY_NAME_MAP[ruleId]) return RULE_DISPLAY_NAME_MAP[ruleId];

  const normalizedName = normalizeText(rule?.name);
  if (normalizedName === 'Document Parsing Errors') return '文档解析异常';
  if (normalizedName === 'Quality Gate Degraded') return '质量门控降级';
  if (normalizedName === 'Low Confidence Extraction') return '低置信度抽取';
  return normalizedName || '未命名规则';
};

const ruleScopeLabel = (rule?: Module4RuleItem | null) => {
  const scope = normalizeTypeKey(asRecord(rule?.expr).scope);
  if (scope === 'field') return '字段';
  if (scope === 'document') return '文档';
  return scope ? prettifyToken(scope) : '未声明';
};

const metricValueText = (value: unknown) => {
  if (typeof value === 'number') {
    const rounded = Number.isInteger(value) ? String(value) : value.toFixed(3);
    return rounded.replace(/\.?0+$/, '');
  }
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (Array.isArray(value) || isRecord(value)) return JSON.stringify(value, null, 2);
  return normalizeText(value) || '无';
};

const simulationMetricLabel = (value: string) => {
  const normalized = normalizeTypeKey(value);
  const labels: Record<string, string> = {
    simulated_contexts: '模拟上下文',
    evaluated_rules: '评估规则数',
    simulated_hits: '命中数量',
    hits_by_rule: '按规则命中',
    hits_by_severity: '按风险等级命中',
    avg_risk_delta: '平均风险变化',
    mode: '模拟模式',
    supported_rule_kinds: '支持规则类型',
  };
  return labels[normalized] || prettifyToken(value);
};

const sortRulesForDisplay = (items: Module4RuleItem[]) =>
  [...items].sort((left, right) => {
    const enabledDiff = Number(right.enabled) - Number(left.enabled);
    if (enabledDiff !== 0) return enabledDiff;
    const severityRank: Record<string, number> = { red: 0, orange: 1, yellow: 2 };
    const severityDiff = (severityRank[left.severity] ?? 99) - (severityRank[right.severity] ?? 99);
    if (severityDiff !== 0) return severityDiff;
    return left.name.localeCompare(right.name, 'zh-CN');
  });

const runtimeStatusLabel = (healthz?: Module4HealthzResponse | null) => {
  if (!healthz) return UI_TEXT.runtimeNotReady;
  if (healthz.status === 'ok' || healthz.db_connected) return UI_TEXT.runtimeHealthy;
  return UI_TEXT.runtimeNotReady;
};

const projectionTone = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'success') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (normalized === 'failed') return 'border-rose-200 bg-rose-50 text-rose-700';
  if (normalized === 'skipped') return 'border-amber-200 bg-amber-50 text-amber-700';
  return 'border-slate-200 bg-slate-100 text-slate-600';
};

const projectionSummary = (item?: Module4GraphFileItem | null) => {
  const projection = item?.projection;
  if (!projection?.status) return '待投影';
  if (projection.status === 'success') {
    return `已投影 · ${projection.projected_nodes} 个节点 / ${projection.projected_edges} 条关系`;
  }
  if (projection.status === 'failed') {
    return `投影失败${projection.error_message ? ' · 可重试' : ''}`;
  }
  if (projection.status === 'skipped') {
    return projection.skipped_reason ? `已跳过 · ${projection.skipped_reason}` : '已跳过';
  }
  return `投影状态 · ${projectionStatusLabel(projection.status)}`;
};

const truthStatusOfGraphFile = (item?: Module4GraphFileItem | null) => {
  if (!item) return '未同步';
  if (item.status === 'failed') return '失败';
  if (item.status === 'ready') return '已打通';
  return graphFileStatusLabel(item.status);
};

const truthToneOfGraphFile = (item?: Module4GraphFileItem | null) => {
  if (!item) return 'border-slate-200 bg-slate-50 text-slate-600';
  if (item.status === 'failed') return 'border-rose-200 bg-rose-50 text-rose-700';
  if (item.status === 'ready') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  return 'border-sky-200 bg-sky-50 text-sky-700';
};

const stageLabelOfGraphFile = (item?: Module4GraphFileItem | null) => {
  if (!item) return '未进入处理';
  const metadata = asRecord(item.metadata);
  const stage = firstText(metadata.failure_stage, metadata.stage);
  const normalizedStage = normalizeTypeKey(stage);
  if (normalizedStage === 'ready') return '已就绪';
  if (normalizedStage === 'processing_documents') return '文档入图中';
  if (normalizedStage === 'running') return '处理中';
  if (normalizedStage === 'indexing') return '索引中';
  if (normalizedStage === 'importing_graph') return '导图中';
  if (normalizedStage === 'preparing_input') return '准备输入';
  if (normalizedStage === 'queued') return '排队中';
  if (normalizedStage === 'failed') return '失败';
  if (normalizedStage === 'success') return '已完成';
  return stage || graphFileStatusLabel(item.status);
};

const runtimeTone = (healthz?: Module4HealthzResponse | null) => {
  if (!healthz) return 'border-slate-200 bg-slate-50 text-slate-600';
  if (healthz.status === 'ok' || healthz.db_connected) return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  return 'border-rose-200 bg-rose-50 text-rose-700';
};

const jobTone = (job?: Module4JobResponse | null) => {
  const normalized = String(job?.status || '').toLowerCase();
  if (normalized === 'success') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (normalized === 'failed' || normalized === 'cancelled') return 'border-rose-200 bg-rose-50 text-rose-700';
  if (normalized === 'running' || normalized === 'queued') return 'border-sky-200 bg-sky-50 text-sky-700';
  return 'border-slate-200 bg-slate-50 text-slate-600';
};

const formatDateTime = (value?: string | null) => {
  const text = String(value || '').trim();
  if (!text) return '未记录';
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date);
};

const evidenceTitle = (item: Module4EvidenceItem) => {
  const locator = asRecord(item.locator);
  const objectType = normalizeText(item.object_type) || 'evidence';
  const objectLabel = presentTypeLabel(objectType);
  const preview = asRecord(locator.table_preview);
  const previewHeaders = asList(preview.headers).map((value) => cleanArtifactText(value)).filter(Boolean).slice(0, 4);
  const caption = cleanArtifactText(firstText(locator.title, locator.caption));
  const keyPoints = asList(locator.key_points).map((value) => cleanArtifactText(value)).filter(Boolean).slice(0, 2);
  const textBlocks = asList(locator.text_blocks).map((value) => cleanArtifactText(value)).filter(Boolean).slice(0, 1);
  const objectId = normalizeText(item.object_id) || normalizeText(item.ref_id) || '未命名对象';
  const page = firstText((item as any).page, locator.page);
  const title = firstText(
    looksLikeLowSignalArtifactTitle(caption, objectId) ? '' : caption,
    page ? `P${page}` : '',
    objectId
  );
  return `${objectLabel} · ${shortText(title, 32)}`;
};

type EvidenceDataframePreview = {
  headers: string[];
  rows: string[][];
  rowCount: number;
  colCount: number;
};

const evidenceDataframePreview = (item: Module4EvidenceItem): EvidenceDataframePreview | null => {
  const locator = asRecord(item.locator);
  const candidates = [asRecord(locator.table_preview), asRecord(locator.dataframe)];
  for (const candidate of candidates) {
    const headers = asList(candidate.headers).map((value) => cleanArtifactText(value)).filter(Boolean).slice(0, 6);
    const rows = asList(candidate.rows)
      .map((row) =>
        Array.isArray(row) ? row.map((cell) => cleanArtifactText(cell)).slice(0, 6).filter((cell) => cell !== '') : []
      )
      .filter((row) => row.length > 0)
      .slice(0, 6);
    const rowCount = numberOrNull(candidate.row_count) || rows.length;
    const colCount = numberOrNull(candidate.col_count) || headers.length || Math.max(0, ...rows.map((row) => row.length));
    if (headers.length > 0 || rows.length > 0) {
      return {
        headers,
        rows,
        rowCount,
        colCount,
      };
    }
  }
  return null;
};

const evidenceInsightChips = (item: Module4EvidenceItem) => {
  const locator = asRecord(item.locator);
  const chips = [
    cleanArtifactText(firstText(locator.caption, locator.title)),
    ...asList(locator.key_points).map((value) => cleanArtifactText(value)).filter(Boolean).slice(0, 3),
  ].filter(Boolean);
  return chips.slice(0, 4);
};

const evidenceSnippetText = (item: Module4EvidenceItem) => {
  const text = cleanArtifactText(item.snippet);
  if (!text || looksLikePlaceholderText(text)) return '';
  const titleParts = evidenceTitle(item).split('·');
  const titleText = cleanArtifactText(titleParts.length > 1 ? titleParts.slice(1).join('·') : titleParts[0]);
  const pageOnlyMatch = text.match(/第\s*(\d+)\s*页/);
  if (pageOnlyMatch && titleText.toLowerCase().includes(`p${pageOnlyMatch[1]}`)) return '';
  if (titleText && normalizeText(text) === normalizeText(titleText)) return '';
  return text;
};

const renderEvidenceDataframe = (item: Module4EvidenceItem) => {
  const preview = evidenceDataframePreview(item);
  if (!preview) return null;
  return (
    <div className="mt-3 overflow-hidden border border-slate-200/90 dark:border-slate-700/80">
      <div className="flex items-center justify-between border-b border-slate-200/80 bg-slate-50/80 px-3 py-2 text-[11px] font-medium text-slate-500 dark:border-slate-700/80 dark:bg-slate-900/70 dark:text-slate-400">
        <span>DataFrame 预览</span>
        <span>
          {preview.rowCount} 行 · {preview.colCount} 列
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-xs">
          {preview.headers.length > 0 && (
            <thead>
              <tr className="bg-slate-50/70 dark:bg-slate-900/60">
                {preview.headers.map((header, index) => (
                  <th
                    key={`${header}-${index}`}
                    className="border-b border-r border-slate-200/80 px-3 py-2 text-left font-semibold text-slate-600 dark:border-slate-700/80 dark:text-slate-300"
                  >
                    {shortText(header, 28)}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {preview.rows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`} className="odd:bg-white even:bg-slate-50/50 dark:odd:bg-slate-950 dark:even:bg-slate-900/40">
                {row.map((cell, cellIndex) => (
                  <td
                    key={`cell-${rowIndex}-${cellIndex}`}
                    className="border-b border-r border-slate-200/70 px-3 py-2 align-top text-slate-600 dark:border-slate-700/70 dark:text-slate-300"
                  >
                    {shortText(cell, 42)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const evidenceLocatorText = (item: Module4EvidenceItem) => {
  const locator = asRecord(item.locator);
  const parts = [
    item.page_no ? `第 ${item.page_no} 页` : '',
    firstText(locator.section, locator.anchor, locator.block_id),
    item.ref_id ? `Ref: ${item.ref_id}` : '',
  ].filter(Boolean);
  return parts.join(' · ') || '未提供定位信息';
};

const graphFilePriority = (item?: Module4GraphFileItem | null) => {
  if (!item) return 99;
  if (item.status === 'ready' && item.projection?.status === 'success') return 0;
  if (item.status === 'ready') return 1;
  if (graphFileHasUsableVersion(item)) return 2;
  if (item.status === 'indexing' || item.status === 'importing_graph') return 3;
  if (item.status === 'preparing_input' || item.status === 'queued') return 4;
  if (item.status === 'failed') return 8;
  return 6;
};

const sortGraphFilesForDisplay = (items: Module4GraphFileItem[]) =>
  [...items].sort((left, right) => {
    const priorityDiff = graphFilePriority(left) - graphFilePriority(right);
    if (priorityDiff !== 0) return priorityDiff;
    const projectionDiff =
      projectionStatusLabel(left.projection?.status).localeCompare(projectionStatusLabel(right.projection?.status));
    if (projectionDiff !== 0) return projectionDiff;
    const indexedLeft = String(left.last_indexed_at || '');
    const indexedRight = String(right.last_indexed_at || '');
    if (indexedLeft !== indexedRight) return indexedRight.localeCompare(indexedLeft);
    return String(left.file_name || '').localeCompare(String(right.file_name || ''), 'zh-CN');
  });

type ForceGraphHandle = {
  fit: (nodeIds?: string[], options?: { animated?: boolean; outOnly?: boolean; maxZoom?: number }) => void;
  getScale: () => number;
  getPan: () => { x: number; y: number };
  setZoom: (zoom: number) => void;
  pinNode: (nodeId: string) => void;
  unPinNode: (nodeIds: string[] | string) => void;
  getNodeScreenPosition: (nodeId: string) => { x: number; y: number } | null;
};

type ForceGraphViewport = {
  x: number;
  y: number;
  zoom: number;
};

type ForceGraphPoint = {
  clientX: number;
  clientY: number;
};

type NodePositionState = {
  x: number;
  y: number;
  fx?: number | null;
  fy?: number | null;
};

type ForceGraphNodeDatum = SimulationNodeDatum & {
  id: string;
  node: Module4GraphNode;
  label: string;
  radius: number;
  degree: number;
  importance: number;
  emphasisTier: NodeEmphasisTier;
  color: string;
  seedLane: SeedLaneKey;
  seedX: number;
  seedY: number;
  laneX: number;
  laneY: number;
  x: number;
  y: number;
  fx: number | null;
  fy: number | null;
};

type ForceGraphLinkDatum = SimulationLinkDatum<ForceGraphNodeDatum> & {
  id: string;
  edge: Module4GraphEdge;
  label: string;
  color: string;
  width: number;
  source: string | ForceGraphNodeDatum;
  target: string | ForceGraphNodeDatum;
};

type ForceGraphProps = {
  graph: Module4GraphResponse;
  layoutMode: LayoutMode;
  selectedNodeId: string;
  pinnedNodeIds: string[];
  selectionNeighborhood: ReturnType<typeof selectionNeighborhoodOf>;
  onNodeClick: (nodeId: string, point: ForceGraphPoint) => void;
  onNodeDoubleClick: (nodeId: string) => void;
  onCanvasClick: () => void;
  onNodeDragEnd: (nodeId: string, point: ForceGraphPoint) => void;
  className?: string;
};

const DRAG_ACTIVATION_DISTANCE = 3;
const DRAG_CLICK_SUPPRESS_MS = 220;
const PAN_CLICK_SUPPRESS_MS = 120;

const splitNodeLabel = (value: string, maxChars = 8, maxLines = 2) => {
  const text = normalizeText(value);
  if (!text) return [''];
  const lines: string[] = [];
  for (let index = 0; index < text.length && lines.length < maxLines; index += maxChars) {
    const slice = text.slice(index, index + maxChars);
    const next = text.slice(index + maxChars);
    lines.push(next && lines.length === maxLines - 1 ? `${slice.slice(0, Math.max(0, maxChars - 1))}…` : slice);
  }
  return lines;
};

const shouldRenderNodeLabel = (
  node: ForceGraphNodeDatum,
  options: {
    graphSize: number;
    zoom: number;
    isSelected: boolean;
    isFocused: boolean;
  }
) => {
  if (options.isSelected) return true;
  if (options.isFocused) return true;

  const typeKey = typeKeyOf(node.node);
  if (typeKey === 'document' || typeKey === 'community' || node.emphasisTier === 'primary') {
    return options.zoom >= 1.08;
  }
  if (typeKey === 'entity' || typeKey === 'risk') {
    if (node.emphasisTier === 'secondary') return options.zoom >= 1.14;
    if (node.emphasisTier === 'tertiary') return options.zoom >= 1.2;
    return options.zoom >= 1.26;
  }

  const label = normalizeText(node.label);
  if (!label) return false;
  if (options.zoom < 1.02) return false;

  const highDensityType =
    typeKey === 'chunk' ||
    typeKey === 'field' ||
    typeKey === 'table' ||
    typeKey === 'figure' ||
    typeKey === 'image';

  const isVerbose =
    label.length > 16 || /^[[(（《【]/.test(label) || /[。；，、:：]/.test(label) || /\d{3,}/.test(label);

  if (!highDensityType) {
    if (node.emphasisTier === 'secondary') return options.zoom >= 1.18;
    if (node.emphasisTier === 'tertiary') return options.zoom >= 1.26;
    return options.zoom >= 1.34;
  }

  if (!isVerbose && node.emphasisTier === 'secondary') return options.zoom >= 1.24;
  if (node.emphasisTier === 'secondary') return options.zoom >= 1.3;
  if (node.emphasisTier === 'tertiary') return options.zoom >= 1.38;
  return options.zoom >= 1.48;
};

const buildHierarchyPositions = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const positionMap = new Map<string, { x: number; y: number }>();
  if (!nodes.length) return positionMap;
  const degreeMap = buildEdgeDegreeMap(nodes, edges);

  const adjacency = new Map<string, Set<string>>();
  nodes.forEach((node) => adjacency.set(node.node_id, new Set()));
  edges.forEach((edge) => {
    adjacency.get(edge.source_node_id)?.add(edge.target_node_id);
    adjacency.get(edge.target_node_id)?.add(edge.source_node_id);
  });

  const rankedNodes = [...nodes].sort((left, right) => {
    const degreeDiff = (adjacency.get(right.node_id)?.size || 0) - (adjacency.get(left.node_id)?.size || 0);
    if (degreeDiff !== 0) return degreeDiff;
    const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
    if (typeDiff !== 0) return typeDiff;
    return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
  });

  const rootId = pickLayoutRootId(rankedNodes, degreeMap) || rankedNodes[0]?.node_id || nodes[0]?.node_id;
  const levels = new Map<string, number>();
  const queue = rootId ? [rootId] : [];
  if (rootId) levels.set(rootId, 0);

  while (queue.length > 0) {
    const currentId = queue.shift() as string;
    const currentLevel = levels.get(currentId) || 0;
    (adjacency.get(currentId) || new Set()).forEach((neighborId) => {
      if (!levels.has(neighborId)) {
        levels.set(neighborId, currentLevel + 1);
        queue.push(neighborId);
      }
    });
  }

  let fallbackLevel = Math.max(0, ...Array.from(levels.values())) + 1;
  nodes.forEach((node) => {
    if (!levels.has(node.node_id)) {
      levels.set(node.node_id, fallbackLevel);
      fallbackLevel += 1;
    }
  });

  const columns = new Map<number, Module4GraphNode[]>();
  nodes.forEach((node) => {
    const level = levels.get(node.node_id) || 0;
    const bucket = columns.get(level) || [];
    bucket.push(node);
    columns.set(level, bucket);
  });

  Array.from(columns.entries())
    .sort((left, right) => left[0] - right[0])
    .forEach(([level, group]) => {
      const ordered = [...group].sort((left, right) => {
        const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
        if (typeDiff !== 0) return typeDiff;
        return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
      });

      const totalHeight = Math.max(0, (ordered.length - 1) * 136);
      ordered.forEach((node, index) => {
        positionMap.set(node.node_id, {
          x: level * 260,
          y: index * 136 - totalHeight / 2,
        });
      });
    });

  return positionMap;
};

const getLinkEndpoint = (value: string | ForceGraphNodeDatum) =>
  (typeof value === 'string' ? null : value) ?? null;

const stableHash = (value: string) => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return hash;
};

const curvedEdgeGeometry = (
  link: ForceGraphLinkDatum,
  source: ForceGraphNodeDatum,
  target: ForceGraphNodeDatum
) => {
  const sourceX = Number(source.x || 0);
  const sourceY = Number(source.y || 0);
  const targetX = Number(target.x || 0);
  const targetY = Number(target.y || 0);
  const deltaX = targetX - sourceX;
  const deltaY = targetY - sourceY;
  const distance = Math.max(1, Math.hypot(deltaX, deltaY));
  const unitX = deltaX / distance;
  const unitY = deltaY / distance;

  const startInset = source.radius + 4;
  const endInset = target.radius + 4;
  const startX = sourceX + unitX * startInset;
  const startY = sourceY + unitY * startInset;
  const endX = targetX - unitX * endInset;
  const endY = targetY - unitY * endInset;

  const normalX = -unitY;
  const normalY = unitX;
  const role = edgeRoleOf(link.edge);
  const curvatureBase =
    role === 'semantic' ? 0.072 : role === 'anchor' ? 0.02 : role === 'evidence' ? 0.038 : 0.03;
  const nearStraight = Math.abs(deltaY) < Math.max(18, distance * 0.1);
  const curvature = nearStraight
    ? Math.min(10, Math.max(1.5, distance * 0.016))
    : Math.min(22, Math.max(4, distance * curvatureBase));
  const direction =
    Math.abs(deltaY) <= 8
      ? deltaX >= 0
        ? 1
        : -1
      : deltaY >= 0
        ? 1
        : -1;
  const controlX = (startX + endX) / 2 + normalX * curvature * direction;
  const controlY = (startY + endY) / 2 + normalY * curvature * direction;

  const t = 0.5;
  const labelX = (1 - t) ** 2 * startX + 2 * (1 - t) * t * controlX + t ** 2 * endX;
  const labelY = (1 - t) ** 2 * startY + 2 * (1 - t) * t * controlY + t ** 2 * endY;

  return {
    path: `M ${startX.toFixed(2)} ${startY.toFixed(2)} Q ${controlX.toFixed(2)} ${controlY.toFixed(
      2
    )} ${endX.toFixed(2)} ${endY.toFixed(2)}`,
    labelX,
    labelY,
  };
};

const Neo4jStyleForceGraph = forwardRef<ForceGraphHandle, ForceGraphProps>(
  (
    {
      graph,
      layoutMode,
      selectedNodeId,
      pinnedNodeIds,
      selectionNeighborhood,
      onNodeClick,
      onNodeDoubleClick,
      onCanvasClick,
      onNodeDragEnd,
      className,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const simulationRef = useRef<Simulation<ForceGraphNodeDatum, ForceGraphLinkDatum> | null>(null);
    const nodesRef = useRef<ForceGraphNodeDatum[]>([]);
    const linksRef = useRef<ForceGraphLinkDatum[]>([]);
    const nodeMapRef = useRef(new Map<string, ForceGraphNodeDatum>());
    const nodeElementMapRef = useRef(new Map<string, SVGGElement>());
    const positionCacheRef = useRef(new Map<string, NodePositionState>());
    const viewportRef = useRef<ForceGraphViewport>({ x: 0, y: 0, zoom: 1 });
    const animationFrameRef = useRef<number | null>(null);
    const viewportAnimationRef = useRef<number | null>(null);
    const suppressClickRef = useRef(false);
    const dragStateRef = useRef<{
      nodeId: string;
      element: SVGGElement | null;
      pointerId: number;
      startClientX: number;
      startClientY: number;
      pointerOffsetX: number;
      pointerOffsetY: number;
      wasPinned: boolean;
      activated: boolean;
      moved: boolean;
    } | null>(null);
    const panStateRef = useRef<{
      pointerId: number;
      startClientX: number;
      startClientY: number;
      originX: number;
      originY: number;
      moved: boolean;
    } | null>(null);

    const [viewport, setViewport] = useState<ForceGraphViewport>({ x: 0, y: 0, zoom: 1 });
    const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
    const [hoveredEdgeId, setHoveredEdgeId] = useState('');
    const [, setTick] = useState(0);

    viewportRef.current = viewport;

    const graphSignature = useMemo(
      () =>
        `${graph.nodes.map((node) => node.node_id).sort().join('|')}::${graph.edges
          .map((edge) => edge.edge_id)
          .sort()
          .join('|')}`,
      [graph.edges, graph.nodes]
    );

    useEffect(() => {
      setHoveredEdgeId('');
    }, [graphSignature]);

    const scheduleRender = useCallback(() => {
      if (typeof window === 'undefined') return;
      if (animationFrameRef.current != null) return;
      animationFrameRef.current = window.requestAnimationFrame(() => {
        animationFrameRef.current = null;
        setTick((current) => current + 1);
      });
    }, []);

    const renderDragFrame = useCallback(() => {
      flushSync(() => {
        setTick((current) => current + 1);
      });
    }, []);

    const syncCachedNodePositions = useCallback(() => {
      const cachedPositions = positionCacheRef.current;
      nodesRef.current.forEach((node) => {
        cachedPositions.set(node.id, {
          x: Number(node.x || 0),
          y: Number(node.y || 0),
          fx: node.fx ?? null,
          fy: node.fy ?? null,
        });
      });
    }, []);

    const applyImmediateNodeTransform = useCallback((nodeId: string, x: number, y: number) => {
      const nodeElement = nodeElementMapRef.current.get(nodeId);
      if (!nodeElement) return;
      nodeElement.setAttribute('transform', `translate(${x} ${y})`);
    }, []);

    const animateViewport = useCallback(
      (next: ForceGraphViewport, animated = true) => {
        if (typeof window === 'undefined') {
          setViewport(next);
          return;
        }

        if (viewportAnimationRef.current != null) {
          window.cancelAnimationFrame(viewportAnimationRef.current);
          viewportAnimationRef.current = null;
        }

        if (!animated) {
          setViewport(next);
          return;
        }

        const start = viewportRef.current;
        const startTime = performance.now();
        const duration = 220;

        const step = (now: number) => {
          const progress = Math.min(1, (now - startTime) / duration);
          const eased = 1 - (1 - progress) ** 3;
          setViewport({
            x: start.x + (next.x - start.x) * eased,
            y: start.y + (next.y - start.y) * eased,
            zoom: start.zoom + (next.zoom - start.zoom) * eased,
          });
          if (progress < 1) {
            viewportAnimationRef.current = window.requestAnimationFrame(step);
          } else {
            viewportAnimationRef.current = null;
          }
        };

        viewportAnimationRef.current = window.requestAnimationFrame(step);
      },
      []
    );

    const toGraphPoint = useCallback(
      (clientX: number, clientY: number) => {
        const rect = containerRef.current?.getBoundingClientRect();
        const activeViewport = viewportRef.current;
        if (!rect) return { x: 0, y: 0 };
        return {
          x: (clientX - rect.left - activeViewport.x) / activeViewport.zoom,
          y: (clientY - rect.top - activeViewport.y) / activeViewport.zoom,
        };
      },
      []
    );

    const fitNodes = useCallback(
      (nodeIds?: string[], options?: { animated?: boolean; outOnly?: boolean; maxZoom?: number }) => {
        if (!containerSize.width || !containerSize.height) return;
        const activeNodes = nodesRef.current.filter((node) => !nodeIds?.length || nodeIds.includes(node.id));
        if (!activeNodes.length) return;

        if (activeNodes.length === 1) {
          const node = activeNodes[0];
          const currentViewport = viewportRef.current;
          const zoomLimit = options?.maxZoom ?? 1.14;
          const targetZoom = options?.outOnly ? Math.min(currentViewport.zoom, zoomLimit) : zoomLimit;
          const nodeX = Number(node.x || 0);
          const nodeY = Number(node.y || 0);

          animateViewport(
            {
              zoom: targetZoom,
              x: containerSize.width / 2 - nodeX * targetZoom,
              y: containerSize.height / 2 - nodeY * targetZoom,
            },
            options?.animated !== false
          );
          return;
        }

        const padding = activeNodes.length > 120 ? 28 : activeNodes.length > 64 ? 22 : 18;

        let minX = Number.POSITIVE_INFINITY;
        let minY = Number.POSITIVE_INFINITY;
        let maxX = Number.NEGATIVE_INFINITY;
        let maxY = Number.NEGATIVE_INFINITY;

        activeNodes.forEach((node) => {
          const radius = node.radius + padding;
          const x = Number(node.x || 0);
          const y = Number(node.y || 0);
          minX = Math.min(minX, x - radius);
          maxX = Math.max(maxX, x + radius);
          minY = Math.min(minY, y - radius);
          maxY = Math.max(maxY, y + radius);
        });

        const width = Math.max(1, maxX - minX);
        const height = Math.max(1, maxY - minY);
        const zoomLimit =
          options?.maxZoom ??
          (activeNodes.length <= 24 ? 1.18 : activeNodes.length <= 48 ? 1.1 : activeNodes.length === 1 ? 1.14 : 1.04);
        const nextZoom = clamp(
          Math.min(containerSize.width / width, containerSize.height / height) * 0.92,
          0.18,
          zoomLimit
        );
        const currentViewport = viewportRef.current;
        const targetZoom = options?.outOnly ? Math.min(currentViewport.zoom, nextZoom) : nextZoom;
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;

        animateViewport(
          {
            zoom: targetZoom,
            x: containerSize.width / 2 - centerX * targetZoom,
            y: containerSize.height / 2 - centerY * targetZoom,
          },
          options?.animated !== false
        );
      },
      [animateViewport, containerSize.height, containerSize.width]
    );

    useImperativeHandle(
      ref,
      () => ({
        fit: (nodeIds, options) => fitNodes(nodeIds, options),
        getScale: () => viewportRef.current.zoom,
        getPan: () => ({ x: viewportRef.current.x, y: viewportRef.current.y }),
        setZoom: (zoom: number) => {
          const rect = containerRef.current?.getBoundingClientRect();
          if (!rect) return;
          const current = viewportRef.current;
          const worldX = (containerSize.width / 2 - current.x) / current.zoom;
          const worldY = (containerSize.height / 2 - current.y) / current.zoom;
          const nextZoom = clamp(zoom, 0.18, 2.4);
          animateViewport({
            zoom: nextZoom,
            x: containerSize.width / 2 - worldX * nextZoom,
            y: containerSize.height / 2 - worldY * nextZoom,
          });
        },
        pinNode: (nodeId: string) => {
          const node = nodeMapRef.current.get(nodeId);
          if (!node) return;
          node.fx = node.x || 0;
          node.fy = node.y || 0;
          scheduleRender();
        },
        unPinNode: (nodeIds: string[] | string) => {
          const ids = Array.isArray(nodeIds) ? nodeIds : [nodeIds];
          ids.forEach((nodeId) => {
            const node = nodeMapRef.current.get(nodeId);
            if (!node || dragStateRef.current?.nodeId === nodeId) return;
            if (layoutMode === HierarchicalLayoutType) return;
            node.fx = null;
            node.fy = null;
          });
          simulationRef.current?.alpha(0.28).restart();
          scheduleRender();
        },
        getNodeScreenPosition: (nodeId: string) => {
          const node = nodeMapRef.current.get(nodeId);
          if (!node) return null;
          const activeViewport = viewportRef.current;
          return {
            x: activeViewport.x + Number(node.x || 0) * activeViewport.zoom,
            y: activeViewport.y + Number(node.y || 0) * activeViewport.zoom,
          };
        },
      }),
      [animateViewport, containerSize.height, containerSize.width, fitNodes, layoutMode, scheduleRender]
    );

    useEffect(() => {
      const target = containerRef.current;
      if (!target || typeof ResizeObserver === 'undefined') return () => undefined;

      const updateSize = () => {
        setContainerSize({
          width: Math.max(0, target.clientWidth),
          height: Math.max(0, target.clientHeight),
        });
      };

      updateSize();
      const observer = new ResizeObserver(() => updateSize());
      observer.observe(target);
      return () => observer.disconnect();
    }, []);

    useEffect(() => {
      if (!graph.nodes.length) {
        nodesRef.current = [];
        linksRef.current = [];
        nodeMapRef.current = new Map();
        simulationRef.current?.stop();
        simulationRef.current = null;
        return () => undefined;
      }

      const cachedPositions = positionCacheRef.current;
      const seedPositions =
        layoutMode === HierarchicalLayoutType
          ? buildHierarchyPositions(graph.nodes, graph.edges)
          : buildSeedPositions(graph.nodes, graph.edges);
      const pinnedSet = new Set(pinnedNodeIds);
      const importanceContext = buildNodeImportanceContext(graph.nodes, graph.edges);

      const nextNodes = graph.nodes.map((node) => {
        const visual = visualSpecOf(node);
        const isDocumentNode = typeKeyOf(node) === 'document';
        const degree = importanceContext.degreeMap.get(node.node_id) || 0;
        const emphasisTier = emphasisTierOfNode(node, degree, importanceContext);
        const importance = nodeImportanceOf(node, degree, emphasisTier, importanceContext);
        const seedLane = seedLaneOfNode(node, importanceContext.rootNodeId);
        const laneLayout = SEED_LANE_LAYOUT[seedLane];
        const densityRatio = clamp(degree / Math.max(1, importanceContext.maxDegree), 0, 1);
        const tierRadiusBoost =
          isDocumentNode
            ? emphasisTier === 'primary'
              ? 3.5
              : emphasisTier === 'secondary'
                ? 2
                : emphasisTier === 'tertiary'
                  ? 0.75
                  : 0
            : emphasisTier === 'primary'
              ? 6
              : emphasisTier === 'secondary'
                ? 3.5
                : emphasisTier === 'tertiary'
                  ? 1.5
                  : 0;
        const radius = clamp(
          visual.minRadius + (visual.maxRadius - visual.minRadius) * (densityRatio * 0.72 + emphasisTierWeight(emphasisTier) * 0.38),
          visual.minRadius,
          visual.maxRadius + tierRadiusBoost
        );
        const label = captionOfNode(node, emphasisTier === 'primary' ? 28 : visual.size > 64 ? 24 : 18);
        const cached = cachedPositions.get(node.node_id);
        const seeded = seedPositions.get(node.node_id);
        const x = cached?.x ?? seeded?.x ?? (Math.random() - 0.5) * 360;
        const y = cached?.y ?? seeded?.y ?? (Math.random() - 0.5) * 280;
        const isPinned = pinnedSet.has(node.node_id) || layoutMode === HierarchicalLayoutType;
        return {
          id: node.node_id,
          node,
          label,
          radius,
          degree,
          importance,
          emphasisTier,
          color: visual.color,
          seedLane,
          seedX: seeded?.x ?? x,
          seedY: seeded?.y ?? y,
          laneX: laneLayout.x,
          laneY: laneLayout.y,
          x,
          y,
          fx: isPinned ? cached?.fx ?? x : null,
          fy: isPinned ? cached?.fy ?? y : null,
        } satisfies ForceGraphNodeDatum;
      });

      const nextLinks = graph.edges.map((edge) => ({
        id: edge.edge_id,
        edge,
        label: relationLabelOf(edge),
        color: relationToneOf(edge),
        width: Math.max(1.6, 1.2 + edge.confidence * 2),
        source: edge.source_node_id,
        target: edge.target_node_id,
      })) satisfies ForceGraphLinkDatum[];

      nodesRef.current = nextNodes;
      linksRef.current = nextLinks;
      nodeMapRef.current = new Map(nextNodes.map((node) => [node.id, node]));

      simulationRef.current?.stop();

      if (layoutMode === HierarchicalLayoutType) {
        nextNodes.forEach((node) => {
          const position = seedPositions.get(node.id) || { x: 0, y: 0 };
          node.x = position.x;
          node.y = position.y;
          node.fx = position.x;
          node.fy = position.y;
          cachedPositions.set(node.id, {
            x: position.x,
            y: position.y,
            fx: position.x,
            fy: position.y,
          });
        });
        scheduleRender();
        return () => undefined;
      }

      const simulation = forceSimulation(nextNodes)
        .force(
          'link',
          forceLink<ForceGraphNodeDatum, ForceGraphLinkDatum>(nextLinks)
            .id((node) => node.id)
            .distance((link) => {
              const typeKey = normalizeTypeKey(link.edge.relation_type);
              if (typeKey.includes('overview_context')) return 236;
              if (typeKey.includes('community')) return 202;
              if (typeKey.includes('part')) return 134;
              if (typeKey.includes('entity')) return 116;
              if (typeKey.includes('related')) return 124;
              if (typeKey.includes('evidence')) return 152;
              return 120;
            })
            .strength((link) => {
              const typeKey = normalizeTypeKey(link.edge.relation_type);
              if (typeKey.includes('overview_context')) return 0.18;
              if (typeKey.includes('community')) return 0.22;
              if (typeKey.includes('part')) return 0.34;
              if (typeKey.includes('entity')) return 0.26;
              if (typeKey.includes('evidence')) return 0.22;
              return 0.19;
            })
        )
        .force(
          'charge',
          forceManyBody<ForceGraphNodeDatum>()
            .strength((node) => {
              const typeKey = typeKeyOf(node.node);
              const emphasisMultiplier =
                node.emphasisTier === 'primary'
                  ? 1.1
                  : node.emphasisTier === 'secondary'
                    ? 1.04
                    : node.emphasisTier === 'tertiary'
                      ? 1.01
                      : 1;
              const radiusInfluence = Math.max(0, node.radius - 18) * 6;
              if (typeKey === 'community') return (-980 - radiusInfluence) * emphasisMultiplier;
              if (typeKey === 'document') return (-760 - radiusInfluence) * emphasisMultiplier;
              if (typeKey === 'chunk') return (graph.nodes.length > 180 ? -260 : -320) * emphasisMultiplier;
              return ((graph.nodes.length > 180 ? -380 : -460) - radiusInfluence * 0.32) * emphasisMultiplier;
            })
            .distanceMax(760)
        )
        .force('center', forceCenter<ForceGraphNodeDatum>(0, 0))
        .force(
          'lane-x',
          forceX<ForceGraphNodeDatum>((node) => node.laneX).strength((node) => {
            if (node.seedLane === 'anchor') return 0.12;
            if (node.seedLane === 'risk') return 0.1;
            if (node.seedLane.startsWith('evidence')) return 0.086;
            if (node.seedLane.startsWith('semantic')) return 0.082;
            return 0.074;
          })
        )
        .force(
          'lane-y',
          forceY<ForceGraphNodeDatum>((node) => node.laneY).strength((node) => {
            if (node.seedLane === 'anchor') return 0.088;
            if (node.seedLane === 'risk') return 0.094;
            if (node.seedLane.startsWith('semantic')) return 0.076;
            if (node.seedLane.startsWith('evidence')) return 0.072;
            return 0.064;
          })
        )
        .force('seed-x', forceX<ForceGraphNodeDatum>((node) => node.seedX).strength(graph.nodes.length > 180 ? 0.024 : 0.036))
        .force('seed-y', forceY<ForceGraphNodeDatum>((node) => node.seedY).strength(graph.nodes.length > 180 ? 0.022 : 0.032))
        .force(
          'collide',
          forceCollide<ForceGraphNodeDatum>()
            .radius((node) => {
              const tierPadding =
                node.emphasisTier === 'primary'
                  ? 24
                  : node.emphasisTier === 'secondary'
                    ? 20
                    : node.emphasisTier === 'tertiary'
                      ? 16
                      : typeKeyOf(node.node) === 'chunk'
                        ? 12
                        : 15;
              return node.radius + tierPadding;
            })
            .iterations(4)
        )
        .alpha(0.68)
        .alphaDecay(0.05)
        .velocityDecay(0.34)
        .on('tick', () => {
          nextNodes.forEach((node) => {
            cachedPositions.set(node.id, {
              x: Number(node.x || 0),
              y: Number(node.y || 0),
              fx: node.fx ?? null,
              fy: node.fy ?? null,
            });
          });
          scheduleRender();
        });

      simulationRef.current = simulation;
      scheduleRender();

      return () => {
        simulation.stop();
      };
    }, [graph.nodes, graph.edges, graphSignature, layoutMode, pinnedNodeIds, scheduleRender]);

    useEffect(() => {
      const pinnedSet = new Set(pinnedNodeIds);
      nodesRef.current.forEach((node) => {
        const shouldPin = pinnedSet.has(node.id) || layoutMode === HierarchicalLayoutType;
        if (shouldPin) {
          node.fx = node.fx ?? node.x ?? 0;
          node.fy = node.fy ?? node.y ?? 0;
        } else if (dragStateRef.current?.nodeId !== node.id) {
          node.fx = null;
          node.fy = null;
        }
      });

      if (layoutMode === ForceDirectedLayoutType) {
        simulationRef.current?.alpha(0.24).restart();
      }
      scheduleRender();
    }, [layoutMode, pinnedNodeIds, scheduleRender]);

    useEffect(() => {
      const handlePointerMove = (event: PointerEvent) => {
        const activeDrag = dragStateRef.current;
        if (activeDrag) {
          if (event.pointerId !== activeDrag.pointerId) return;
          const node = nodeMapRef.current.get(activeDrag.nodeId);
          if (!node) return;

          event.preventDefault();
          const deltaX = event.clientX - activeDrag.startClientX;
          const deltaY = event.clientY - activeDrag.startClientY;
          const distance = Math.hypot(deltaX, deltaY);
          if (!activeDrag.activated) {
            if (distance < DRAG_ACTIVATION_DISTANCE) return;
            activeDrag.activated = true;
            activeDrag.moved = true;
            suppressClickRef.current = true;
            if (layoutMode === ForceDirectedLayoutType) {
              simulationRef.current?.alphaTarget(0.24);
              simulationRef.current?.alpha(0.3).restart();
            }
          }

          const nextPoint = toGraphPoint(event.clientX, event.clientY);
          const nextX = nextPoint.x - activeDrag.pointerOffsetX;
          const nextY = nextPoint.y - activeDrag.pointerOffsetY;
          node.fx = nextX;
          node.fy = nextY;
          node.x = nextX;
          node.y = nextY;
          applyImmediateNodeTransform(activeDrag.nodeId, nextX, nextY);
          if (layoutMode === ForceDirectedLayoutType) {
            simulationRef.current?.alphaTarget(0.22);
            simulationRef.current?.restart();
            simulationRef.current?.tick(1);
          }
          syncCachedNodePositions();
          renderDragFrame();
          return;
        }

        const activePan = panStateRef.current;
        if (activePan) {
          if (event.pointerId !== activePan.pointerId) return;
          const deltaX = event.clientX - activePan.startClientX;
          const deltaY = event.clientY - activePan.startClientY;
          activePan.moved = activePan.moved || Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2;
          setViewport((current) => ({
            ...current,
            x: activePan.originX + deltaX,
            y: activePan.originY + deltaY,
          }));
        }
      };

      const handlePointerUp = (event: PointerEvent) => {
        const activeDrag = dragStateRef.current;
        if (activeDrag) {
          if (event.pointerId !== activeDrag.pointerId) return;
          const node = nodeMapRef.current.get(activeDrag.nodeId);
          if (node) {
            if (activeDrag.activated) {
              node.fx = node.x ?? 0;
              node.fy = node.y ?? 0;
              if (layoutMode === ForceDirectedLayoutType) {
                simulationRef.current?.alphaTarget(0);
                simulationRef.current?.alpha(0.22).restart();
              }
              onNodeDragEnd(activeDrag.nodeId, {
                clientX: event.clientX,
                clientY: event.clientY,
              });
            } else {
              node.fx = activeDrag.wasPinned ? node.fx ?? node.x ?? 0 : null;
              node.fy = activeDrag.wasPinned ? node.fy ?? node.y ?? 0 : null;
              if (layoutMode === ForceDirectedLayoutType) {
                simulationRef.current?.alphaTarget(0);
              }
            }
          }
          const shouldSuppressClick = activeDrag.activated || activeDrag.moved;
          try {
            activeDrag.element?.releasePointerCapture?.(activeDrag.pointerId);
          } catch {
            // Synthetic pointer probes in tests may not own capture; ignore safely.
          }
          dragStateRef.current = null;
          if (shouldSuppressClick) {
            window.setTimeout(() => {
              suppressClickRef.current = false;
            }, DRAG_CLICK_SUPPRESS_MS);
          }
        }

        if (panStateRef.current) {
          if (event.pointerId !== panStateRef.current.pointerId) return;
          const wasMoved = panStateRef.current.moved;
          panStateRef.current = null;
          if (wasMoved) {
            window.setTimeout(() => {
              suppressClickRef.current = false;
            }, PAN_CLICK_SUPPRESS_MS);
          }
        }
      };

      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', handlePointerUp);
      window.addEventListener('pointercancel', handlePointerUp);
      return () => {
        window.removeEventListener('pointermove', handlePointerMove);
        window.removeEventListener('pointerup', handlePointerUp);
        window.removeEventListener('pointercancel', handlePointerUp);
      };
    }, [
      applyImmediateNodeTransform,
      layoutMode,
      onNodeDragEnd,
      renderDragFrame,
      scheduleRender,
      syncCachedNodePositions,
      toGraphPoint,
    ]);

    useEffect(() => {
      return () => {
        if (typeof window === 'undefined') return;
        if (animationFrameRef.current != null) window.cancelAnimationFrame(animationFrameRef.current);
        if (viewportAnimationRef.current != null) window.cancelAnimationFrame(viewportAnimationRef.current);
      };
    }, []);

    const handleWheel = useCallback(
      (event: React.WheelEvent<SVGSVGElement>) => {
        event.preventDefault();
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;

        const current = viewportRef.current;
        const cursorX = event.clientX - rect.left;
        const cursorY = event.clientY - rect.top;
        const worldX = (cursorX - current.x) / current.zoom;
        const worldY = (cursorY - current.y) / current.zoom;
        const nextZoom = clamp(current.zoom * (event.deltaY < 0 ? 1.08 : 0.92), 0.18, 2.4);
        setViewport({
          zoom: nextZoom,
          x: cursorX - worldX * nextZoom,
          y: cursorY - worldY * nextZoom,
        });
      },
      []
    );

    const handleBackdropPointerDown = useCallback((event: React.PointerEvent<SVGSVGElement>) => {
      if (event.button !== 0) return;
      const target = event.target as Element;
      if (target.closest('[data-force-node="true"]')) return;
      const current = viewportRef.current;
      panStateRef.current = {
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        originX: current.x,
        originY: current.y,
        moved: false,
      };
      setHoveredEdgeId('');
      suppressClickRef.current = false;
    }, []);

    const handleCanvasPointerUp = useCallback(() => {
      if (panStateRef.current?.moved) {
        suppressClickRef.current = true;
      }
    }, []);

    const renderNodes = nodesRef.current;
    const renderLinks = linksRef.current;

    return (
      <div ref={containerRef} className={cn('absolute inset-0', className)}>
        <svg
          className="absolute inset-0 h-full w-full touch-none select-none"
          onWheel={handleWheel}
          onPointerDown={handleBackdropPointerDown}
          onPointerUp={handleCanvasPointerUp}
          onClick={() => {
            if (suppressClickRef.current) {
              suppressClickRef.current = false;
              return;
            }
            onCanvasClick();
          }}
        >
          <rect x="0" y="0" width="100%" height="100%" fill="transparent" />
          <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.zoom})`}>
            {false &&
              layoutMode === ForceDirectedLayoutType &&
              GRAPH_LAYER_GUIDES.filter((guide) =>
                renderNodes.some((node) => guide.lanes.includes(node.seedLane))
              ).map((guide) => (
                <g key={guide.id} pointerEvents="none">
                  <rect
                    x={guide.x}
                    y={guide.y}
                    width={guide.width}
                    height={guide.height}
                    rx={24}
                    fill={guide.fill}
                    stroke={guide.stroke}
                    strokeWidth={1}
                    strokeDasharray="7 10"
                  />
                  <text
                    x={guide.x + 18}
                    y={guide.y + 26}
                    fontSize={11}
                    fontWeight={700}
                    fill={guide.text}
                    letterSpacing="0.12em"
                  >
                    {guide.label}
                  </text>
                </g>
              ))}
            {renderLinks.map((link) => {
              const source = getLinkEndpoint(link.source);
              const target = getLinkEndpoint(link.target);
              if (!source || !target) return null;

              const geometry = curvedEdgeGeometry(link, source, target);
              const inSelection = selectionNeighborhood ? selectionNeighborhood.edgeIds.has(link.id) : false;
              const hovered = hoveredEdgeId === link.id;
              const active = inSelection || hovered;
              const dimmed = selectionNeighborhood ? !inSelection && !hovered : false;
              const labelText = shortText(link.label, 14);
              const showLabel = hovered;
              const strokeColor = dimmed ? mixHexColor(link.color, '#dbe4f0', 0.64) : link.color;
              const labelWidth = Math.max(64, labelText.length * 7.2 + 18);
              const edgeRole = edgeRoleOf(link.edge);

              return (
                <g key={link.id}>
                  <path
                    d={geometry.path}
                    fill="none"
                    stroke="rgba(0,0,0,0)"
                    strokeOpacity={0}
                    strokeWidth={18}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    onMouseEnter={() => setHoveredEdgeId(link.id)}
                    onMouseLeave={() => setHoveredEdgeId((current) => (current === link.id ? '' : current))}
                  />
                  <path
                    d={geometry.path}
                    fill="none"
                    stroke={strokeColor}
                    strokeOpacity={dimmed ? 0.14 : active ? 0.92 : edgeRole === 'semantic' ? 0.34 : 0.2}
                    strokeWidth={active ? Math.min(4, link.width + 0.72) : Math.max(1.05, link.width - 0.3)}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeDasharray={edgeRole === 'anchor' ? '7 7' : undefined}
                    onMouseEnter={() => setHoveredEdgeId(link.id)}
                    onMouseLeave={() => setHoveredEdgeId((current) => (current === link.id ? '' : current))}
                  />
                  {showLabel && (
                    <g transform={`translate(${geometry.labelX} ${geometry.labelY})`}>
                      <rect
                        x={-labelWidth / 2}
                        y={-9}
                        width={labelWidth}
                        height={18}
                        rx={9}
                        fill="rgba(255,255,255,0.9)"
                        stroke="rgba(203,213,225,0.92)"
                      />
                      <text
                        textAnchor="middle"
                        dominantBaseline="central"
                        fontSize={9}
                        fontWeight={700}
                        fill={dimmed ? '#94a3b8' : '#334155'}
                      >
                        {labelText}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}

            {renderNodes.map((node) => {
              const isSelected = selectedNodeId === node.id;
              const isPinned = pinnedNodeIds.includes(node.id);
              const isFocused = selectionNeighborhood ? selectionNeighborhood.nodeIds.has(node.id) : false;
              const isDimmed = selectionNeighborhood ? !isFocused : false;
              const isDocumentNode = typeKeyOf(node.node) === 'document';
              const nodeFill = isDimmed ? mixHexColor(node.color, '#e2e8f0', 0.56) : node.color;
              const haloRadius =
                node.radius +
                (isSelected
                  ? isDocumentNode ? 6 : 8
                  : node.emphasisTier === 'primary'
                    ? isDocumentNode ? 5 : 8
                    : node.emphasisTier === 'secondary'
                      ? 5
                    : node.emphasisTier === 'tertiary'
                        ? 3
                        : 1);
              const haloFill = isSelected
                ? 'rgba(37,99,235,0.08)'
                : node.emphasisTier === 'primary'
                  ? hexToRgba(node.color, isDimmed ? 0.025 : 0.065)
                  : node.emphasisTier === 'secondary'
                    ? hexToRgba(node.color, isDimmed ? 0.018 : 0.045)
                    : node.emphasisTier === 'tertiary'
                      ? hexToRgba(node.color, isDimmed ? 0.014 : 0.028)
                      : 'rgba(255,255,255,0.04)';
              const outerRingStroke = isSelected
                ? '#1d4ed8'
                : node.emphasisTier === 'primary'
                  ? mixHexColor(node.color, '#ffffff', 0.74)
                  : node.emphasisTier === 'secondary'
                    ? mixHexColor(node.color, '#ffffff', 0.66)
                    : 'rgba(255,255,255,0.9)';
              const outerRingOpacity =
                node.emphasisTier === 'primary' ? 0.48 : node.emphasisTier === 'secondary' ? 0.22 : 0;
              const labelFontSize =
                node.emphasisTier === 'primary'
                  ? 11
                  : node.emphasisTier === 'secondary'
                    ? 11
                    : node.radius >= 24
                      ? 10
                      : 9;
              const shouldShowLabel = shouldRenderNodeLabel(node, {
                graphSize: graph.nodes.length,
                zoom: viewport.zoom,
                isSelected,
                isFocused,
              });
              const labelLines = splitNodeLabel(
                node.label,
                node.emphasisTier === 'primary' ? 11 : node.radius >= 32 ? 9 : node.radius >= 26 ? 8 : 7,
                node.emphasisTier === 'primary' ? 3 : 2
              );
              const detachedLabel = false;
              const detachedLabelLines = detachedLabel ? splitNodeLabel(node.label, 14, 2) : [];
              const detachedLabelWidth = detachedLabel
                ? Math.max(
                    148,
                    detachedLabelLines.reduce((max, line) => Math.max(max, line.length * 9.2 + 34), 0)
                  )
                : 0;
              const detachedLabelHeight = detachedLabel ? 18 + detachedLabelLines.length * 13 : 0;
              const detachedLabelY = detachedLabel ? -(node.radius + detachedLabelHeight + 22) : 0;
              const isDragging =
                dragStateRef.current?.nodeId === node.id && dragStateRef.current?.activated;
              const shouldShowInnerRing =
                isSelected || node.emphasisTier === 'primary' || node.emphasisTier === 'secondary';

              return (
                <g
                  key={node.id}
                  data-force-node="true"
                  ref={(element) => {
                    if (element) {
                      nodeElementMapRef.current.set(node.id, element);
                    } else {
                      nodeElementMapRef.current.delete(node.id);
                    }
                  }}
                  transform={`translate(${node.x || 0} ${node.y || 0})`}
                  onPointerDown={(event) => {
                    if (event.button !== 0) return;
                    event.preventDefault();
                    event.stopPropagation();
                    try {
                      event.currentTarget.setPointerCapture?.(event.pointerId);
                    } catch {
                      // Synthetic pointer probes may not have an active native pointer.
                    }
                    const pointerPoint = toGraphPoint(event.clientX, event.clientY);
                    const currentX = Number(node.x ?? 0);
                    const currentY = Number(node.y ?? 0);
                    node.fx = currentX;
                    node.fy = currentY;
                    dragStateRef.current = {
                      nodeId: node.id,
                      element: event.currentTarget,
                      pointerId: event.pointerId,
                      startClientX: event.clientX,
                      startClientY: event.clientY,
                      pointerOffsetX: pointerPoint.x - currentX,
                      pointerOffsetY: pointerPoint.y - currentY,
                      wasPinned: isPinned || layoutMode === HierarchicalLayoutType,
                      activated: false,
                      moved: false,
                    };
                    suppressClickRef.current = false;
                    if (layoutMode === ForceDirectedLayoutType) {
                      simulationRef.current?.alphaTarget(0.16);
                      simulationRef.current?.alpha(0.18).restart();
                    }
                  }}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (suppressClickRef.current) {
                      suppressClickRef.current = false;
                      return;
                    }
                    onNodeClick(node.id, {
                      clientX: event.clientX,
                      clientY: event.clientY,
                    });
                  }}
                  onDoubleClick={(event) => {
                    event.stopPropagation();
                    onNodeDoubleClick(node.id);
                  }}
                  style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
                >
                  {detachedLabel && (
                    <g pointerEvents="none">
                      <line
                        x1="0"
                        y1={detachedLabelY + detachedLabelHeight}
                        x2="0"
                        y2={-node.radius - 8}
                        stroke="rgba(148,163,184,0.78)"
                        strokeWidth={1.05}
                      />
                      <rect
                        x={-detachedLabelWidth / 2}
                        y={detachedLabelY}
                        width={detachedLabelWidth}
                        height={detachedLabelHeight}
                        rx={14}
                        fill="rgba(255,255,255,0.94)"
                        stroke="rgba(148,163,184,0.72)"
                        strokeWidth={1.1}
                      />
                      <circle cx={-detachedLabelWidth / 2 + 16} cy={detachedLabelY + 16} r={4} fill={nodeFill} />
                      {detachedLabelLines.map((line, index) => (
                        <text
                          key={`${node.id}-detached-${line}-${index}`}
                          x={0}
                          y={detachedLabelY + 17 + index * 13}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fontSize={index === 0 ? 11.5 : 10.5}
                          fontWeight={index === 0 ? 800 : 700}
                          fill="#0f172a"
                        >
                          {line}
                        </text>
                      ))}
                    </g>
                  )}
                  <circle
                    r={haloRadius}
                    fill={haloFill}
                  />
                  {outerRingOpacity > 0 && (
                    <circle
                      r={node.radius + (node.emphasisTier === 'primary' ? (isDocumentNode ? 4 : 6) : 4)}
                      fill="none"
                      stroke={outerRingStroke}
                      strokeOpacity={outerRingOpacity}
                      strokeWidth={node.emphasisTier === 'primary' ? (isDocumentNode ? 1.55 : 1.8) : 1.4}
                    />
                  )}
                  <circle
                    r={node.radius}
                    fill={nodeFill}
                    stroke={
                      isSelected
                        ? '#1d4ed8'
                        : isPinned
                          ? '#0f172a'
                          : node.emphasisTier === 'primary'
                            ? mixHexColor(node.color, '#0f172a', 0.24)
                            : node.emphasisTier === 'secondary'
                              ? mixHexColor(node.color, '#0f172a', 0.16)
                              : 'rgba(255,255,255,0.92)'
                    }
                    strokeWidth={
                      isSelected
                        ? 2.8
                        : isPinned
                          ? 2.1
                          : node.emphasisTier === 'primary'
                            ? 2.2
                            : node.emphasisTier === 'secondary'
                              ? 1.8
                              : 1.25
                    }
                  />
                  {shouldShowInnerRing && (
                    <circle
                      r={Math.max(9, node.radius - (node.emphasisTier === 'primary' ? 8 : 6))}
                      fill="none"
                      stroke={
                        isSelected
                          ? 'rgba(255,255,255,0.96)'
                          : node.emphasisTier === 'primary'
                            ? 'rgba(255,255,255,0.58)'
                            : 'rgba(255,255,255,0.4)'
                      }
                      strokeWidth={node.emphasisTier === 'primary' ? 1.15 : 0.95}
                    />
                  )}
                  {shouldShowLabel &&
                    !detachedLabel &&
                    labelLines.map((line, index) => (
                      <text
                        key={`${node.id}-${line}-${index}`}
                        textAnchor="middle"
                        dominantBaseline="central"
                        y={(index - (labelLines.length - 1) / 2) * (labelFontSize + 1)}
                        fontSize={labelFontSize}
                        fontWeight={800}
                        fill={isDimmed ? '#475569' : '#f8fafc'}
                        style={{ pointerEvents: 'none' }}
                      >
                        {line}
                      </text>
                    ))}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    );
  }
);

export const KnowledgeNexus: React.FC = () => {
  const nvlRef = useRef<ForceGraphHandle | null>(null);
  const graphHostRef = useRef<HTMLDivElement | null>(null);
  const toolbarMenuRef = useRef<HTMLDivElement | null>(null);
  const sourceRef = useRef('storage');
  const fitPendingRef = useRef(true);

  const [graphData, setGraphData] = useState<Module4GraphResponse>(EMPTY_GRAPH);
  const [graphFiles, setGraphFiles] = useState<Module4GraphFileItem[]>([]);
  const [alerts, setAlerts] = useState<Module4AlertItem[]>([]);
  const [healthz, setHealthz] = useState<Module4HealthzResponse | null>(null);
  const [currentJob, setCurrentJob] = useState<Module4JobResponse | null>(null);
  const [rules, setRules] = useState<Module4RuleItem[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState('');
  const [togglingRuleId, setTogglingRuleId] = useState('');
  const [explainResult, setExplainResult] = useState<Module4ExplainResponse | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [simulateResult, setSimulateResult] = useState<Module4SimulateResponse | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [filters, setFilters] = useState<FilterState>({ query: '', nodeTypes: [] });
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(ForceDirectedLayoutType);
  const [graphViewMode, setGraphViewMode] = useState<GraphViewMode>('overview');
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [detail, setDetail] = useState<Module4NodeDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [ackingAlertId, setAckingAlertId] = useState('');
  const [resolvingAlertId, setResolvingAlertId] = useState('');
  const [, setMessage] = useState('正在加载图谱工作台...');
  const [apiError, setApiError] = useState('');
  const [pinnedNodeIds, setPinnedNodeIds] = useState<string[]>([]);
  const [inspector, setInspector] = useState<InspectorState | null>(null);
  const [sourceMode, setSourceMode] = useState<'follow-active-doc' | 'manual-select'>('follow-active-doc');
  const [manualFileHash, setManualFileHash] = useState('');
  const [activeDocFileHash, setActiveDocFileHash] = useState('');
  const [activeToolbarMenu, setActiveToolbarMenu] = useState<ToolbarMenu | null>(null);
  const [isUtilityDockOpen, setIsUtilityDockOpen] = useState(false);

  const deferredFilters = useDeferredValue(filters);
  const currentFileHash =
    sourceMode === 'manual-select' ? manualFileHash.trim() : activeDocFileHash.trim();
  const currentGraphFile = useMemo(
    () => graphFiles.find((item) => item.file_hash === currentFileHash) || null,
    [currentFileHash, graphFiles]
  );
  const currentProjection = currentGraphFile?.projection || null;
  const canUseFileGraph = Boolean(currentFileHash && graphFileHasUsableVersion(currentGraphFile));
  const overviewGraph = useMemo(() => buildOverviewGraph(graphData), [graphData]);
  const preferEvidenceView = useMemo(
    () => shouldPreferEvidenceGraph(graphData, overviewGraph),
    [graphData, overviewGraph]
  );
  const effectiveGraphViewMode =
    graphViewMode === 'overview' && preferEvidenceView ? 'evidence' : graphViewMode;
  const projectedGraph = useMemo(
    () => (effectiveGraphViewMode === 'overview' ? overviewGraph : graphData),
    [effectiveGraphViewMode, graphData, overviewGraph]
  );

  const graphNodeMap = useMemo(
    () => new Map(graphData.nodes.map((node) => [node.node_id, node])),
    [graphData.nodes]
  );

  const nodeTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    projectedGraph.nodes.forEach((node) => {
      const label = presentTypeLabel(node);
      counts[label] = (counts[label] || 0) + 1;
    });
    return counts;
  }, [projectedGraph.nodes]);

  const nodeTypes = useMemo(
    () =>
      Object.keys(nodeTypeCounts).sort((left, right) => {
        const diff = typePriority(normalizeTypeKey(left)) - typePriority(normalizeTypeKey(right));
        return diff !== 0 ? diff : left.localeCompare(right, 'zh-CN');
      }),
    [nodeTypeCounts]
  );

  const fullGraphSignature = useMemo(
    () =>
      `${graphData.nodes.map((node) => node.node_id).sort().join('|')}::${graphData.edges
        .map((edge) => edge.edge_id)
        .sort()
        .join('|')}`,
    [graphData.edges, graphData.nodes]
  );

  const filteredGraph = useMemo(() => {
    const query = normalizeText(deferredFilters.query).toLowerCase();
    const activeTypes = new Set(deferredFilters.nodeTypes.map((item) => normalizeTypeKey(item)));

    const nodes = projectedGraph.nodes.filter((node) => {
      const typeMatch =
        activeTypes.size === 0 ||
        activeTypes.has(typeKeyOf(node)) ||
        activeTypes.has(normalizeTypeKey(presentTypeLabel(node)));
      if (!typeMatch) return false;
      if (!query) return true;

      const haystack = [
        displayNameOfNode(node),
        summaryOfNode(node),
        presentTypeLabel(node),
        normalizeText(asRecord(node.attrs).snippet),
        normalizeText(asRecord(node.attrs).file_name),
      ]
        .join(' ')
        .toLowerCase();

      return haystack.includes(query);
    });

    const nodeIds = new Set(nodes.map((node) => node.node_id));
    const edges = projectedGraph.edges.filter(
      (edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id)
    );

    return {
      nodes,
      edges,
      source: projectedGraph.source,
      workspace_id: projectedGraph.workspace_id || null,
      stats: buildStats(nodes, edges),
    } satisfies Module4GraphResponse;
  }, [deferredFilters, projectedGraph]);

  const graphSignature = useMemo(
    () =>
      `${filteredGraph.nodes.map((node) => node.node_id).sort().join('|')}::${filteredGraph.edges
        .map((edge) => edge.edge_id)
        .sort()
        .join('|')}`,
    [filteredGraph.edges, filteredGraph.nodes]
  );

  const selectedNode = useMemo(
    () => graphNodeMap.get(selectedNodeId) || detail?.node || null,
    [detail?.node, graphNodeMap, selectedNodeId]
  );

  const currentSelectionGraph = useMemo(
    () => (selectedNodeId ? subgraphForNode(filteredGraph, selectedNodeId) : EMPTY_GRAPH),
    [filteredGraph, selectedNodeId]
  );

  const detailGraph = detail?.graph?.nodes.length ? detail.graph : currentSelectionGraph;
  const detailNode = detail?.node || selectedNode;
  const selectionNeighborhood = useMemo(
    () => (selectedNodeId ? selectionNeighborhoodOf(filteredGraph, selectedNodeId) : null),
    [filteredGraph, selectedNodeId]
  );

  const detailEdges = useMemo(() => {
    if (!detailNode) return [];
    return detailGraph.edges.filter(
      (edge) => edge.source_node_id === detailNode.node_id || edge.target_node_id === detailNode.node_id
    );
  }, [detailGraph.edges, detailNode]);

  const detailNeighbors = useMemo(() => {
    if (!detailNode) return [];
    const neighborIds = new Set<string>();
    detailEdges.forEach((edge) => {
      neighborIds.add(edge.source_node_id);
      neighborIds.add(edge.target_node_id);
    });
    neighborIds.delete(detailNode.node_id);

    return detailGraph.nodes
      .filter((node) => neighborIds.has(node.node_id))
      .sort((left, right) => displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN'))
      .slice(0, 8);
  }, [detailEdges, detailGraph.nodes, detailNode]);

  const detailEvidence = useMemo(() => detail?.evidence || [], [detail?.evidence]);
  const detailEdgeEvidence = useMemo(() => detail?.edge_evidence || {}, [detail?.edge_evidence]);
  const detailEdgeEvidenceRows = useMemo(
    () =>
      detailEdges
        .map((edge) => ({
          edge,
          evidence: detailEdgeEvidence[edge.edge_id] || [],
        }))
        .filter((item) => item.evidence.length > 0),
    [detailEdgeEvidence, detailEdges]
  );

  const pinnedSet = useMemo(() => new Set(pinnedNodeIds), [pinnedNodeIds]);
  const visibleAlerts = useMemo(() => {
    return alerts.filter((item) => {
      const alertFileHash = alertFileHashOf(item);
      if (currentFileHash && alertFileHash) {
        return alertFileHash === currentFileHash;
      }
      return Boolean(item.subject_node_id && graphNodeMap.has(item.subject_node_id));
    });
  }, [alerts, currentFileHash, graphNodeMap]);
  const detailAlerts = useMemo(
    () => (detailNode ? visibleAlerts.filter((item) => item.subject_node_id === detailNode.node_id) : []),
    [detailNode, visibleAlerts]
  );
  const sourceLabel = UI_TEXT.module4Source;
  const graphViewModeLabel =
    effectiveGraphViewMode === 'overview' ? UI_TEXT.overviewGraph : UI_TEXT.evidenceGraph;
  const openAlertCount = visibleAlerts.filter((item) => item.status === 'open').length;
  const hasActiveFilters = Boolean(filters.query.trim() || filters.nodeTypes.length > 0);
  const alertPreviewItems = useMemo(() => visibleAlerts.slice(0, 4), [visibleAlerts]);
  const sortedRules = useMemo(() => sortRulesForDisplay(rules), [rules]);
  const enabledRuleCount = useMemo(() => rules.filter((item) => item.enabled).length, [rules]);
  const utilityNodeCountLabel = `${filteredGraph.nodes.length} 个${UI_TEXT.nodeCountMetric}`;
  const utilityAlertCountLabel = `${openAlertCount} 条${UI_TEXT.alertCountMetric}`;
  const utilityDockToggleLabel = isUtilityDockOpen ? UI_TEXT.collapseUtilityDock : UI_TEXT.expandUtilityDock;
  const selectedRule = useMemo(
    () => sortedRules.find((item) => item.rule_id === selectedRuleId) || null,
    [selectedRuleId, sortedRules]
  );
  const primaryDetailAlert = useMemo(
    () => [...detailAlerts].sort((left, right) => right.risk_score - left.risk_score)[0] || null,
    [detailAlerts]
  );
  const analysisTargetLabel = primaryDetailAlert
    ? primaryDetailAlert.title
    : detailNode
      ? displayNameOfNode(detailNode)
      : '';
  const canRunExplain = Boolean(primaryDetailAlert || detailNode);
  const canRunSimulate = Boolean(primaryDetailAlert);
  const detailNodeTypeKey = detailNode ? typeKeyOf(detailNode) : '';
  const isDocumentDetailNode = detailNodeTypeKey === 'document';
  const isArtifactDetailNode =
    detailNodeTypeKey === 'table' || detailNodeTypeKey === 'figure' || detailNodeTypeKey === 'image';
  const showNodeEvidenceSection =
    detailEvidence.length > 0 || (!isDocumentDetailNode && detailEdgeEvidenceRows.length === 0);
  const showEdgeEvidenceSection =
    detailEdgeEvidenceRows.length > 0 || (isDocumentDetailNode && detailEvidence.length === 0);
  const nodeEvidenceTitle = isArtifactDetailNode ? '来源证据' : UI_TEXT.nodeEvidence;
  const edgeEvidenceTitle = isDocumentDetailNode ? '关键证据关系' : UI_TEXT.edgeEvidence;

  const fitGraph = useCallback(
    (nodeIds?: string[], outOnly = false) => {
      const nvl = nvlRef.current;
      const ids = nodeIds?.length ? nodeIds : preferredFitNodeIds(filteredGraph, effectiveGraphViewMode);
      if (!nvl || !ids.length) return;

      nvl.fit(ids, {
        animated: true,
        outOnly,
        maxZoom: ids.length === 1 ? 1.14 : 1.04,
      });
    },
    [effectiveGraphViewMode, filteredGraph]
  );

  const focusNode = useCallback(
    (nodeId: string) => {
      const neighborhood = selectionNeighborhoodOf(filteredGraph, nodeId);
      fitGraph(neighborhood ? [...neighborhood.nodeIds] : [nodeId]);
    },
    [filteredGraph, fitGraph]
  );

  const openInspector = useCallback((nodeId: string, event?: { clientX: number; clientY: number }) => {
    const host = graphHostRef.current;
    let x = 24;
    let y = 24;
    const cardWidth = 348;
    const cardHeight = 520;

    if (host && event) {
      const rect = host.getBoundingClientRect();
      const localX = event.clientX - rect.left;
      const localY = event.clientY - rect.top;
      const preferredX = localX > rect.width * 0.62 ? localX - cardWidth - 22 : localX + 18;
      const preferredY = localY > rect.height * 0.7 ? localY - cardHeight + 40 : localY - 24;
      x = clamp(preferredX, 20, Math.max(20, rect.width - cardWidth));
      y = clamp(preferredY, 20, Math.max(20, rect.height - cardHeight));
    }

    if (host && !event) {
      const rect = host.getBoundingClientRect();
      const point = nvlRef.current?.getNodeScreenPosition(nodeId);
      if (point) {
        const preferredX = point.x > rect.width * 0.62 ? point.x - cardWidth - 22 : point.x + 22;
        const preferredY = point.y > rect.height * 0.7 ? point.y - cardHeight + 40 : point.y - 28;
        x = clamp(preferredX, 20, Math.max(20, rect.width - cardWidth));
        y = clamp(preferredY, 20, Math.max(20, rect.height - cardHeight));
      } else {
        x = clamp(rect.width - cardWidth, 20, Math.max(20, rect.width - cardWidth));
        y = 24;
      }
    }

    if (host) {
      x += host.offsetLeft;
      y += host.offsetTop;
    }

    setSelectedNodeId(nodeId);
    setInspector({ nodeId, x, y });
  }, []);

  const closeInspector = useCallback(() => {
    setSelectedNodeId('');
    setInspector(null);
    setDetail(null);
    setExplainResult(null);
    setSimulateResult(null);
  }, []);

  const loadGraph = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!options?.silent) setLoading(true);
      setApiError('');

      try {
        const desiredFileHash =
          sourceMode === 'manual-select' ? manualFileHash.trim() : getActiveExtractionFileHash();
        const [graphFilesResult, alertResult, healthzResult, rulesResult] = await Promise.allSettled([
          fetchModule4GraphFiles({ limit: 200 }),
          fetchModule4Alerts({ status: 'open', pageSize: 8 }),
          fetchModule4Healthz({ probe: 'basic' }),
          fetchModule4Rules(),
        ]);

        let nextGraph = EMPTY_GRAPH;
        let nextSource = 'storage:file-empty';
        let nextGraphFiles: Module4GraphFileItem[] = [];
        let effectiveFileHash = desiredFileHash;

        if (graphFilesResult.status === 'fulfilled') {
          nextGraphFiles = sortGraphFilesForDisplay(graphFilesResult.value.items);
          setGraphFiles(nextGraphFiles);
          const preferredGraph = desiredFileHash
            ? nextGraphFiles.find((item) => item.file_hash === desiredFileHash) || null
            : nextGraphFiles.find((item) => item.status === 'ready') || nextGraphFiles[0] || null;
          if (!effectiveFileHash) {
            effectiveFileHash = String(preferredGraph?.file_hash || '').trim();
          }
          if (sourceMode === 'manual-select' && !manualFileHash.trim() && effectiveFileHash) {
            setManualFileHash(effectiveFileHash);
          }
        } else {
          setGraphFiles([]);
          setApiError(
            graphFilesResult.reason instanceof Error
              ? graphFilesResult.reason.message
              : '图谱文件列表加载失败'
          );
        }

        if (alertResult.status === 'fulfilled') {
          setAlerts(alertResult.value.items);
        } else {
          setAlerts([]);
        }

        if (healthzResult.status === 'fulfilled') {
          setHealthz(healthzResult.value);
        }

        if (rulesResult.status === 'fulfilled') {
          setRules(sortRulesForDisplay(rulesResult.value.items));
        } else {
          setRules([]);
        }

        if (sourceMode !== 'manual-select') {
          setActiveDocFileHash(desiredFileHash || effectiveFileHash);
        }

        const activeGraphFile =
          nextGraphFiles.find((item) => item.file_hash === effectiveFileHash) || null;

        if (activeGraphFile && effectiveFileHash && graphFileHasUsableVersion(activeGraphFile)) {
          try {
            nextGraph = await fetchModule4FileGraph(effectiveFileHash, {
              limitNodes: 1200,
              limitEdges: 2400,
            });
            nextSource = graphFileSourceKey(activeGraphFile, effectiveFileHash);
            setMessage('当前文件图谱已同步完成，可继续查看证据、关系和告警。');
          } catch (error) {
            setApiError(error instanceof Error ? error.message : '文件级图谱加载失败');
          }
        } else if (activeGraphFile) {
          nextSource = fileGraphPendingSourceKey(effectiveFileHash);
          setMessage(`当前文件图谱状态：${graphFileStatusLabel(activeGraphFile.status)}，正在等待模块二解析结果同步到模块四。`);
        } else {
          setMessage(
            effectiveFileHash
              ? '当前文件尚未出现在模块四图谱列表中，请先在模块二完成解析并等待自动同步。'
              : '当前还没有可展示的单文件图谱数据，请先在模块二上传并解析文件。'
          );
        }

        sourceRef.current = nextSource;
        fitPendingRef.current = true;
        startTransition(() => setGraphData(nextGraph));
      } finally {
        if (!options?.silent) setLoading(false);
      }
    },
    [manualFileHash, sourceMode]
  );

  const refreshGraphFiles = useCallback(async () => {
    try {
      const result = await fetchModule4GraphFiles({ limit: 200 });
      setGraphFiles(sortGraphFilesForDisplay(result.items));
    } catch {
      // keep current file graph list on transient failures
    }
  }, []);

  const refreshHealthz = useCallback(async (probe: 'basic' | 'deep' = 'basic') => {
    try {
      const result = await fetchModule4Healthz({ probe });
      setHealthz(result);
    } catch {
      // keep previous health diagnostics on transient failures
    }
  }, []);

  const expandNeighborhood = useCallback(
    async (nodeId = selectedNodeId) => {
      if (!nodeId || !canUseFileGraph || !currentFileHash) return;
      setExpanding(true);
      try {
        const neighborhood = await fetchModule4FileNeighborhood(currentFileHash, nodeId, { depth: 1, limit: 280 });
        sourceRef.current = graphFileSourceKey(currentGraphFile, currentFileHash);
        fitPendingRef.current = true;
        startTransition(() => {
          setGraphData((current) => mergeGraph(current, neighborhood));
        });
        setDetail({
          node: neighborhood.nodes.find((item) => item.node_id === nodeId) || detailNode || null,
          graph: neighborhood,
          evidence: detailEvidence,
          edge_evidence: detailEdgeEvidence,
        });
        const nodeForMessage =
          neighborhood.nodes.find((item) => item.node_id === nodeId) || detailNode || selectedNode;
        setMessage(
          nodeForMessage
            ? `已扩展节点「${displayNameOfNode(nodeForMessage)}」的邻域。`
            : '已扩展节点邻域。'
        );
        window.setTimeout(() => focusNode(nodeId), 160);
      } catch (error) {
        setApiError(error instanceof Error ? error.message : '扩展邻域失败');
      } finally {
        setExpanding(false);
      }
    },
    [
      canUseFileGraph,
      currentFileHash,
      currentGraphFile,
      detailEdgeEvidence,
      detailEvidence,
      detailNode,
      focusNode,
      selectedNode,
      selectedNodeId,
    ]
  );

  const openNodeFromAlert = useCallback(
    async (item: Module4AlertItem) => {
      const nodeId = item.subject_node_id;
      if (!nodeId || !canUseFileGraph || !currentFileHash) return;

      if (!graphNodeMap.has(nodeId)) {
        try {
          const neighborhood = await fetchModule4FileNeighborhood(currentFileHash, nodeId, { depth: 1, limit: 200 });
          sourceRef.current = graphFileSourceKey(currentGraphFile, currentFileHash);
          fitPendingRef.current = true;
          startTransition(() => {
            setGraphData((current) => mergeGraph(current, neighborhood));
          });
        } catch (error) {
          setApiError(error instanceof Error ? error.message : '无法定位告警节点');
        }
      }

      openInspector(nodeId);
      window.setTimeout(() => focusNode(nodeId), 120);
    },
    [canUseFileGraph, currentFileHash, currentGraphFile, focusNode, graphNodeMap, openInspector]
  );

  const togglePin = useCallback(
    (nodeId = selectedNodeId) => {
      if (!nodeId) return;
      const nvl = nvlRef.current;
      setPinnedNodeIds((current) => {
        const shouldPin = !current.includes(nodeId);
        if (nvl) {
          if (shouldPin) {
            nvl.pinNode(nodeId);
          } else {
            nvl.unPinNode([nodeId]);
          }
        }
        return shouldPin ? [...current, nodeId] : current.filter((item) => item !== nodeId);
      });
    },
    [selectedNodeId]
  );

  const adjustZoom = useCallback(
    (delta: number) => {
      const nvl = nvlRef.current;
      if (!nvl) return;
      const nextZoom = clamp(nvl.getScale() + delta, 0.2, 2.4);
      nvl.setZoom(nextZoom);
    },
    []
  );

  const refreshAlerts = useCallback(async () => {
    const next = await fetchModule4Alerts({ status: 'open', pageSize: 8 });
    setAlerts(next.items);
  }, []);

  const refreshRules = useCallback(async () => {
    const next = await fetchModule4Rules();
    setRules(sortRulesForDisplay(next.items));
  }, []);

  const handleToggleRule = useCallback(
    async (rule: Module4RuleItem) => {
      setTogglingRuleId(rule.rule_id);
      try {
        await updateModule4Rule(rule.rule_id, {
          name: rule.name,
          severity: rule.severity,
          rule_kind: rule.rule_kind,
          expr: rule.expr,
          enabled: !rule.enabled,
        });
        await refreshRules();
        setSimulateResult(null);
      } catch (error) {
        setApiError(error instanceof Error ? error.message : '切换规则失败');
      } finally {
        setTogglingRuleId('');
      }
    },
    [refreshRules]
  );

  const handleExplainCurrent = useCallback(async () => {
    if (!primaryDetailAlert && !detailNode) return;

    setExplaining(true);
    setExplainResult(null);
    try {
      const next = await explainModule4(
        primaryDetailAlert ? { alertId: primaryDetailAlert.alert_id } : { nodeId: detailNode?.node_id }
      );
      setExplainResult(next);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '生成解释失败');
    } finally {
      setExplaining(false);
    }
  }, [detailNode, primaryDetailAlert]);

  const handleSimulateCurrent = useCallback(async () => {
    if (!primaryDetailAlert) {
      setApiError(UI_TEXT.simulationNeedsAlert);
      return;
    }

    setSimulating(true);
    setSimulateResult(null);
    try {
      const next = await simulateModule4({
        scenarioName: selectedRule
          ? `workbench-${primaryDetailAlert.rule_id}-${selectedRule.rule_id}`
          : `workbench-${primaryDetailAlert.rule_id}`,
        scope: {
          alert_id: primaryDetailAlert.alert_id,
          ...(selectedRule ? { rule_id: selectedRule.rule_id } : {}),
        },
      });
      setSimulateResult(next);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '运行模拟失败');
    } finally {
      setSimulating(false);
    }
  }, [primaryDetailAlert, selectedRule]);

  const handleAckAlert = useCallback(async (alertId: string) => {
    setAckingAlertId(alertId);
    try {
      await ackModule4Alert(alertId);
      await refreshAlerts();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '确认告警失败');
    } finally {
      setAckingAlertId('');
    }
  }, [refreshAlerts]);

  const handleResolveAlert = useCallback(
    async (alertId: string) => {
      setResolvingAlertId(alertId);
      try {
        await resolveModule4Alert(alertId, 'user', '从图谱工作台完成核查', '已核查处理');
        await refreshAlerts();
      } catch (error) {
        setApiError(error instanceof Error ? error.message : '解决告警失败');
      } finally {
        setResolvingAlertId('');
      }
    },
    [refreshAlerts]
  );

  useEffect(() => {
    setActiveDocFileHash(getActiveExtractionFileHash());
    void loadGraph();
  }, [loadGraph]);

  useEffect(() => {
    setExplainResult(null);
    setSimulateResult(null);
  }, [currentFileHash, selectedNodeId]);

  useEffect(() => {
    setSimulateResult(null);
  }, [selectedRuleId]);

  useEffect(() => {
    void refreshHealthz('basic');
    const timer = window.setInterval(() => {
      void refreshHealthz('basic');
    }, 15000);
    return () => window.clearInterval(timer);
  }, [refreshHealthz]);

  useEffect(() => {
    const handleExtractionUpdate = () => {
      const activeFileHash = getActiveExtractionFileHash();
      setActiveDocFileHash(activeFileHash);
      void refreshGraphFiles();
      void loadGraph({ silent: true });
    };

    const unsubscribe = subscribeExtractionUpdates(handleExtractionUpdate);
    return unsubscribe;
  }, [loadGraph, refreshGraphFiles]);

  useEffect(() => {
    const jobId = String(currentGraphFile?.current_job_id || '').trim();
    if (!jobId) {
      setCurrentJob(null);
      return () => undefined;
    }

    let cancelled = false;
    const loadJob = async () => {
      try {
        const job = await fetchModule4JobStatus(jobId);
        if (cancelled) return;
        setCurrentJob(job);
      } catch {
        if (cancelled) return;
        setCurrentJob(null);
      }
    };

    void loadJob();
    const timer = window.setInterval(() => {
      void loadJob();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentGraphFile?.current_job_id]);

  useEffect(() => {
    if (!currentGraphFile || !graphFileHasUsableVersion(currentGraphFile) || !currentFileHash) {
      return () => undefined;
    }
    if (sourceRef.current === graphFileSourceKey(currentGraphFile, currentFileHash)) {
      return () => undefined;
    }

    let cancelled = false;
    void fetchModule4FileGraph(currentFileHash, {
      limitNodes: 1200,
      limitEdges: 2400,
    })
      .then((graph) => {
        if (cancelled) return;
        sourceRef.current = graphFileSourceKey(currentGraphFile, currentFileHash);
        fitPendingRef.current = true;
        startTransition(() => setGraphData(graph));
      })
      .catch((error) => {
        if (cancelled) return;
        setApiError(error instanceof Error ? error.message : '文件级图谱加载失败');
      });

    return () => {
      cancelled = true;
    };
  }, [currentFileHash, currentGraphFile]);

  useEffect(() => {
    if (graphViewMode !== 'overview' || !preferEvidenceView) return;
    fitPendingRef.current = true;
    setGraphViewMode('evidence');
    setMessage('当前图谱以证据节点为主，已自动切换到证据图以保证完整展示。');
  }, [graphViewMode, preferEvidenceView]);

  useEffect(() => {
    if (!currentGraphFile || currentGraphFile.status === 'ready') {
      return () => undefined;
    }

    const timer = window.setInterval(() => {
      void refreshGraphFiles();
    }, 5000);

    return () => window.clearInterval(timer);
  }, [currentGraphFile, refreshGraphFiles]);

  useEffect(() => {
    fitPendingRef.current = true;

    const validNodeIds = new Set(graphData.nodes.map((node) => node.node_id));
    setPinnedNodeIds((current) => current.filter((nodeId) => validNodeIds.has(nodeId)));
  }, [effectiveGraphViewMode, fullGraphSignature, graphData.nodes]);

  useEffect(() => {
    if (!selectedNodeId) return;
    if (filteredGraph.nodes.some((node) => node.node_id === selectedNodeId)) return;
    closeInspector();
  }, [closeInspector, filteredGraph.nodes, selectedNodeId]);

  useEffect(() => {
    if (!selectedNodeId) {
      setDetail(null);
      return;
    }

    const fallbackNode = graphNodeMap.get(selectedNodeId) || null;
    const fallbackGraph = subgraphForNode(graphData, selectedNodeId);
    if (fallbackNode) {
      setDetail({ node: fallbackNode, graph: fallbackGraph, evidence: [], edge_evidence: {} });
    }
    if (!canUseFileGraph || !currentFileHash) {
      return;
    }

    let cancelled = false;
    void fetchModule4NodeDetail(selectedNodeId, {
      limit: 180,
      fileHash: currentFileHash,
    })
      .then((result) => {
        if (cancelled) return;
        setDetail(result);
      })
      .catch(() => {
        if (cancelled || !fallbackNode) return;
        setDetail({ node: fallbackNode, graph: fallbackGraph, evidence: [], edge_evidence: {} });
      });

    return () => {
      cancelled = true;
    };
  }, [canUseFileGraph, currentFileHash, graphData, graphNodeMap, selectedNodeId]);

  useEffect(() => {
    if (!filteredGraph.nodes.length || !fitPendingRef.current) return () => undefined;

    const delay = layoutMode === ForceDirectedLayoutType ? 280 : 120;
    const timer = window.setTimeout(() => {
      fitPendingRef.current = false;
      fitGraph(undefined, true);
    }, delay);

    return () => window.clearTimeout(timer);
  }, [filteredGraph.nodes.length, fitGraph, graphSignature, layoutMode]);

  useEffect(() => {
    const nvl = nvlRef.current;
    if (!nvl) return;

    const visibleIds = new Set(filteredGraph.nodes.map((node) => node.node_id));
    const toUnpin = filteredGraph.nodes
      .map((node) => node.node_id)
      .filter((nodeId) => !pinnedSet.has(nodeId));

    if (toUnpin.length) nvl.unPinNode(toUnpin);
    pinnedNodeIds.forEach((nodeId) => {
      if (visibleIds.has(nodeId)) nvl.pinNode(nodeId);
    });
  }, [filteredGraph.nodes, pinnedNodeIds, pinnedSet]);

  const selectedPinned = detailNode ? pinnedSet.has(detailNode.node_id) : false;

  const metricCards = [
    {
      label: UI_TEXT.nodeCountMetric,
      value: String(filteredGraph.nodes.length),
      tone: 'from-blue-500/12 to-blue-500/0 text-blue-700 border-blue-200/70',
    },
    {
      label: UI_TEXT.edgeCountMetric,
      value: String(filteredGraph.edges.length),
      tone: 'from-cyan-500/12 to-cyan-500/0 text-cyan-700 border-cyan-200/70',
    },
    {
      label: UI_TEXT.alertCountMetric,
      value: String(openAlertCount),
      tone: 'from-amber-500/12 to-amber-500/0 text-amber-700 border-amber-200/70',
    },
  ];
  const compactDiagnostics = [
    {
      label: UI_TEXT.runtimeStatus,
      value: runtimeStatusLabel(healthz),
      tone: runtimeTone(healthz),
    },
    {
      label: '图谱引擎',
      value: healthz?.graphrag?.ready ? '已就绪' : '未就绪',
      tone: healthz?.graphrag?.ready
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-rose-200 bg-rose-50 text-rose-700',
    },
    {
      label: '图数据库',
      value: healthz?.db_connected ? '已连接' : '未连接',
      tone: healthz?.db_connected
        ? 'border-teal-200 bg-teal-50 text-teal-700'
        : 'border-rose-200 bg-rose-50 text-rose-700',
    },
    {
      label: UI_TEXT.jobStatus,
      value: currentJob ? jobStatusLabel(currentJob.status) : '当前空闲',
      tone: currentJob ? jobTone(currentJob) : 'border-slate-200 bg-slate-50 text-slate-600',
    },
  ];

  const toolbarGraphStatusLabel = currentGraphFile
    ? graphFileStatusLabel(currentGraphFile.status)
    : currentFileHash
      ? '同步中'
      : '待选择';
  const toolbarSourceModeLabel =
    sourceMode === 'manual-select' ? UI_TEXT.manualSelect : UI_TEXT.followActiveFile;
  const toolbarSourceFileLabel =
    currentGraphFile?.file_name ||
    graphFiles.find((item) => item.file_hash === currentFileHash)?.file_name ||
    (sourceMode === 'manual-select' ? UI_TEXT.selectGraphFile : '等待同步当前文件');
  const toolbarLayoutLabel =
    layoutMode === ForceDirectedLayoutType ? UI_TEXT.forceLayout : UI_TEXT.hierarchicalLayout;

  useEffect(() => {
    if (!activeToolbarMenu) return () => undefined;

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (toolbarMenuRef.current?.contains(target)) return;
      setActiveToolbarMenu(null);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setActiveToolbarMenu(null);
      }
    };

    window.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeToolbarMenu]);

  useEffect(() => {
    if (!selectedRuleId) return;
    if (sortedRules.some((item) => item.rule_id === selectedRuleId)) return;
    setSelectedRuleId('');
  }, [selectedRuleId, sortedRules]);

  useEffect(() => {
    if (!import.meta.env.DEV || typeof window === 'undefined') return () => undefined;

    const debugApi = {
      openNode: (nodeId: string) => openInspector(nodeId),
      closeInspector,
      focusNode,
      expandNeighborhood,
      getGraph: () => graphData,
      getSelectedNodeId: () => selectedNodeId,
    };

    (window as Window & { __module4GraphDebug?: typeof debugApi }).__module4GraphDebug = debugApi;

    return () => {
      delete (window as Window & { __module4GraphDebug?: typeof debugApi }).__module4GraphDebug;
    };
  }, [closeInspector, expandNeighborhood, focusNode, graphData, openInspector, selectedNodeId]);

  return (
    <section className="module4-workbench module4-ide-shell relative">
      <div className="pointer-events-none absolute inset-0 z-10 flex h-full flex-col lg:flex-row">
        {false && (
        <aside
          className={cn(
            'pointer-events-auto module4-ide-sidebar absolute left-4 top-20 bottom-24 z-20 flex shrink-0 flex-col bg-white/80 backdrop-blur-xl shadow-xl border border-slate-200/60 rounded-[24px] overflow-hidden transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]',
            isUtilityDockOpen ? 'w-[320px] opacity-100' : 'w-[60px] opacity-100'
          )}
        >
          <div className="flex h-full flex-col">
            <div className="module4-utility-dock" data-state={isUtilityDockOpen ? 'open' : 'collapsed'}>
              <button
                type="button"
                className="module4-utility-strip flex-col justify-center gap-2 py-4"
                onClick={() => setIsUtilityDockOpen((current) => !current)}
                aria-expanded={isUtilityDockOpen}
                aria-controls="module4-utility-dock-panel"
                aria-label={utilityDockToggleLabel}
              >
                <div className="flex w-full items-center justify-between">
                  <span className={cn("module4-utility-strip-title whitespace-nowrap transition-all", !isUtilityDockOpen && "opacity-0 w-0 hidden")}>
                    {UI_TEXT.utilityDockTitle}
                  </span>
                  <span className="module4-utility-strip-toggle mx-auto">
                    <span className={cn("text-xs font-medium text-slate-600 transition-all", !isUtilityDockOpen && "hidden")}>
                      {utilityDockToggleLabel}
                    </span>
                    <ChevronDown size={16} className={cn("module4-utility-strip-icon", !isUtilityDockOpen && "-rotate-90")} />
                  </span>
                </div>
                {isUtilityDockOpen && (
                  <span className="module4-utility-strip-summary">
                    <span className="module4-toolbar-chip text-xs">{utilityNodeCountLabel}</span>
                    <span className="module4-toolbar-chip text-xs">{utilityAlertCountLabel}</span>
                  </span>
                )}
              </button>

              <AnimatePresence initial={false}>
                {isUtilityDockOpen ? (
                  <motion.div
                    id="module4-utility-dock-panel"
                    key="module4-utility-dock-panel"
                    className="module4-utility-body"
                    role="region"
                    aria-label={UI_TEXT.utilityDockTitle}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 8 }}
                    transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <div className="module4-utility-grid">
                      <section className="module4-utility-filters">
                        <div className="module4-utility-pane-head">
                          <div className="min-w-0">
                            <h3 className="text-sm font-semibold tracking-tight text-slate-900">
                              {UI_TEXT.utilityFiltersTitle}
                            </h3>
                            <p className="mt-1 text-xs leading-5 text-slate-500">{UI_TEXT.utilityFiltersSubtitle}</p>
                          </div>
                        </div>

                        <div className="module4-search-shell module4-utility-search mt-3 flex items-center gap-3 border border-slate-200 px-3 py-2.5">
                          <Search size={16} className="text-slate-400" />
                          <input
                            value={filters.query}
                            onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))}
                            placeholder={UI_TEXT.searchPlaceholder}
                            className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
                          />
                        </div>

                        <div className="module4-utility-subhead">
                          <div className="text-[11px] font-semibold tracking-[0.08em] text-slate-500">
                            {UI_TEXT.nodeTypesTitle}
                          </div>
                          {hasActiveFilters && (
                            <button
                              type="button"
                              onClick={() => setFilters({ query: '', nodeTypes: [] })}
                              className="module4-utility-clear-btn"
                            >
                              {UI_TEXT.clearFilters}
                            </button>
                          )}
                        </div>

                        <div className="module4-utility-chip-cloud custom-scrollbar">
                          {nodeTypes.map((label) => {
                            const active = filters.nodeTypes.includes(label);
                            const count = nodeTypeCounts[label] || 0;
                            const color = visualSpecOf({
                              node_id: label,
                              node_type: normalizeTypeKey(label),
                              canonical_key: label,
                              display_name: label,
                              confidence: 0,
                              attrs: {},
                            }).color;

                            return (
                              <button
                                key={label}
                                type="button"
                                onClick={() =>
                                  setFilters((current) => ({
                                    ...current,
                                    nodeTypes: current.nodeTypes.includes(label)
                                      ? current.nodeTypes.filter((item) => item !== label)
                                      : [...current.nodeTypes, label],
                                  }))
                                }
                                className={cn(
                                  'module4-node-chip inline-flex items-center gap-2 border px-3 py-1.5 text-xs font-medium transition',
                                  active
                                    ? 'border-slate-900 bg-slate-900 text-white'
                                    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
                                )}
                              >
                                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                                {label}
                                <span
                                  className={cn(
                                    'border px-1.5 py-0.5 text-[10px]',
                                    active
                                      ? 'border-white/20 bg-white/10 text-white'
                                      : 'border-slate-200 bg-slate-50 text-slate-500'
                                  )}
                                >
                                  {count}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </section>

                      <section className="module4-utility-alerts">
                        <div className="module4-utility-pane-head module4-utility-pane-head-alerts">
                          <div className="min-w-0">
                            <h3 className="text-sm font-semibold tracking-tight text-slate-900">{UI_TEXT.alertsTitle}</h3>
                            <p className="mt-1 text-xs leading-5 text-slate-500">{UI_TEXT.alertsSubtitle}</p>
                          </div>
                          <span className="border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
                            {openAlertCount}
                          </span>
                        </div>

                        <div className="module4-alert-stream custom-scrollbar">
                          {alertPreviewItems.length === 0 && (
                            <div className="border border-dashed border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-800/50 px-4 py-5 text-sm text-slate-500 dark:text-slate-400">
                              {UI_TEXT.noAlerts}
                            </div>
                          )}

                          {alertPreviewItems.map((alert) => (
                            <div
                              key={alert.alert_id}
                              className="module4-alert-card border border-slate-200 bg-white px-4 py-3"
                              data-testid={`module4-alert-card-${alert.alert_id}`}
                            >
                              <button
                                type="button"
                                onClick={() => void openNodeFromAlert(alert)}
                                className="w-full text-left"
                                data-testid={`module4-alert-open-${alert.alert_id}`}
                              >
                                <div className="flex items-start gap-3">
                                  <div
                                    className={cn(
                                      'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center border',
                                      alert.severity === 'red'
                                        ? 'border-rose-200 bg-rose-50 text-rose-600'
                                        : alert.severity === 'orange'
                                          ? 'border-amber-200 bg-amber-50 text-amber-700'
                                          : 'border-yellow-200 bg-yellow-50 text-yellow-700'
                                    )}
                                  >
                                    <AlertTriangle size={16} />
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                                        {severityLabel(alert.severity)}
                                      </span>
                                      <span className="text-[11px] text-slate-400">{alertStatusLabel(alert.status)}</span>
                                    </div>
                                    <div className="mt-2 text-sm font-semibold text-slate-900">{alert.title}</div>
                                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{alert.summary}</p>
                                  </div>
                                </div>
                              </button>

                              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                                <div className="text-[11px] text-slate-400">{`${UI_TEXT.riskScore} ${Math.round(alert.risk_score)}`}</div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => void handleAckAlert(alert.alert_id)}
                                    disabled={ackingAlertId === alert.alert_id}
                                    className="border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    {ackingAlertId === alert.alert_id ? UI_TEXT.acknowledging : UI_TEXT.acknowledge}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => void handleResolveAlert(alert.alert_id)}
                                    disabled={resolvingAlertId === alert.alert_id}
                                    className="border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-medium text-emerald-700 transition hover:border-emerald-300 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    {resolvingAlertId === alert.alert_id ? UI_TEXT.resolving : UI_TEXT.resolve}
                                  </button>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </section>
                    </div>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>

            <div className="hidden module4-ide-block module4-rule-panel px-6 py-5" style={{ display: 'none' }} aria-hidden="true">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    {UI_TEXT.rulesTitle}
                  </div>
                  <div className="mt-2 text-base font-semibold text-slate-950">
                    {selectedRule ? ruleDisplayName(selectedRule) : UI_TEXT.allEnabledRules}
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">{UI_TEXT.rulesSubtitle}</p>
                </div>
                <span className="border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600">
                  {`${enabledRuleCount}/${sortedRules.length}`}
                </span>
              </div>

              {selectedRule && (
                <div className="mt-4 border border-slate-200 bg-slate-50 px-3 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                      {severityLabel(selectedRule.severity)}
                    </span>
                    <span className="border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                      {`${UI_TEXT.scopeLabel} · ${ruleScopeLabel(selectedRule)}`}
                    </span>
                    <span className="border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                      {`${UI_TEXT.versionLabel} · v${selectedRule.version}`}
                    </span>
                  </div>
                </div>
              )}

              <p className="mt-3 text-xs leading-5 text-slate-500">{UI_TEXT.selectRuleHint}</p>

              <div className="mt-4 max-h-[340px] space-y-3 overflow-y-auto pr-1">
                {sortedRules.length === 0 && (
                  <div className="border border-dashed border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-800/50 px-4 py-5 text-sm text-slate-500 dark:text-slate-400">
                    {UI_TEXT.noRules}
                  </div>
                )}

                {sortedRules.map((rule) => {
                  const active = selectedRuleId === rule.rule_id;
                  return (
                    <div
                      key={rule.rule_id}
                      data-testid={`module4-rule-card-${rule.rule_id}`}
                      className={cn(
                        'border px-3 py-3 transition',
                        active ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white'
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedRuleId(rule.rule_id)}
                        className="w-full text-left"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span
                                className={cn(
                                  'border px-2 py-0.5 text-[10px] font-semibold',
                                  active
                                    ? 'border-white/20 bg-white/10 text-white'
                                    : 'border-slate-200 bg-slate-50 text-slate-600'
                                )}
                              >
                                {severityLabel(rule.severity)}
                              </span>
                              <span
                                className={cn(
                                  'border px-2 py-0.5 text-[10px] font-semibold',
                                  active
                                    ? 'border-white/20 bg-white/10 text-white'
                                    : 'border-slate-200 bg-slate-50 text-slate-600'
                                )}
                              >
                                {ruleScopeLabel(rule)}
                              </span>
                              <span
                                className={cn(
                                  'border px-2 py-0.5 text-[10px] font-semibold',
                                  rule.enabled
                                    ? active
                                      ? 'border-emerald-200/40 bg-emerald-400/15 text-emerald-100'
                                      : 'border-emerald-200 bg-emerald-50 text-emerald-700'
                                    : active
                                      ? 'border-white/20 bg-white/10 text-white/80'
                                      : 'border-slate-200 bg-slate-50 text-slate-500'
                                )}
                              >
                                {rule.enabled ? UI_TEXT.ruleEnabled : UI_TEXT.ruleDisabled}
                              </span>
                            </div>
                            <div className={cn('mt-2 text-sm font-semibold', active ? 'text-white' : 'text-slate-900')}>
                              {ruleDisplayName(rule)}
                            </div>
                          </div>
                          <span
                            className={cn(
                              'border px-2 py-0.5 text-[10px] font-semibold',
                              active ? 'border-white/20 bg-white/10 text-white' : 'border-slate-200 bg-slate-50 text-slate-500'
                            )}
                          >
                            {`v${rule.version}`}
                          </span>
                        </div>
                      </button>

                      <div className="mt-3 flex items-center justify-between gap-3">
                        <div className={cn('text-[11px]', active ? 'text-white/70' : 'text-slate-500')}>
                          {`${UI_TEXT.selectedRule} · ${rule.enabled ? UI_TEXT.ruleEnabled : UI_TEXT.ruleDisabled}`}
                        </div>
                        <button
                          type="button"
                          onClick={() => void handleToggleRule(rule)}
                          disabled={togglingRuleId === rule.rule_id}
                          data-testid={`module4-rule-toggle-${rule.rule_id}`}
                          className={cn(
                            'border px-3 py-1 text-[11px] font-medium transition disabled:cursor-not-allowed disabled:opacity-60',
                            active
                              ? 'border-white/20 bg-white/10 text-white hover:bg-white/20'
                              : rule.enabled
                                ? 'border-amber-200 bg-amber-50 text-amber-700 hover:border-amber-300 hover:bg-amber-100'
                                : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:border-emerald-300 hover:bg-emerald-100'
                          )}
                        >
                          {togglingRuleId === rule.rule_id
                            ? UI_TEXT.switchingRule
                            : rule.enabled
                              ? UI_TEXT.disableRule
                              : UI_TEXT.enableRule}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="hidden module4-ide-block module4-search-panel px-6 py-5" style={{ display: 'none' }} aria-hidden="true">
              <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                {UI_TEXT.searchLabel}
              </label>
              <div className="module4-search-shell flex items-center gap-3 border border-slate-200 bg-white px-3 py-2">
                <Search size={16} className="text-slate-400" />
                <input
                  value={filters.query}
                  onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))}
                  placeholder={UI_TEXT.searchPlaceholder}
                  className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
                />
              </div>
            </div>

            <div className="hidden module4-ide-scroll custom-scrollbar flex-1" style={{ display: 'none' }} aria-hidden="true">
              <section className="module4-ide-block module4-sidebar-section px-6 py-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">{UI_TEXT.nodeTypesTitle}</h3>
                    <p className="text-xs text-slate-500">{UI_TEXT.nodeTypesSubtitle}</p>
                  </div>
                  {filters.nodeTypes.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setFilters((current) => ({ ...current, nodeTypes: [] }))}
                      className="text-xs font-medium text-slate-600 transition hover:text-slate-900"
                    >
                      {UI_TEXT.clearFilters}
                    </button>
                  )}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {nodeTypes.map((label) => {
                    const active = filters.nodeTypes.includes(label);
                    const count = nodeTypeCounts[label] || 0;
                    const color = visualSpecOf({
                      node_id: label,
                      node_type: normalizeTypeKey(label),
                      canonical_key: label,
                      display_name: label,
                      confidence: 0,
                      attrs: {},
                    }).color;

                    return (
                      <button
                        key={label}
                        type="button"
                        onClick={() =>
                          setFilters((current) => ({
                            ...current,
                            nodeTypes: current.nodeTypes.includes(label)
                              ? current.nodeTypes.filter((item) => item !== label)
                              : [...current.nodeTypes, label],
                          }))
                        }
                        className={cn(
                          'module4-node-chip inline-flex items-center gap-2 border px-3 py-1.5 text-xs font-medium transition',
                          active
                            ? 'border-slate-900 bg-slate-900 text-white'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
                        )}
                      >
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                        {label}
                        <span
                          className={cn(
                            'border px-1.5 py-0.5 text-[10px]',
                            active
                              ? 'border-white/20 bg-white/10 text-white'
                              : 'border-slate-200 bg-slate-50 text-slate-500'
                          )}
                        >
                          {count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>

              <section className="module4-sidebar-section px-6 py-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">{UI_TEXT.alertsTitle}</h3>
                    <p className="text-xs text-slate-500">{UI_TEXT.alertsSubtitle}</p>
                  </div>
                  <span className="border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
                    {openAlertCount}
                  </span>
                </div>

                <div className="mt-4 space-y-3">
                  {visibleAlerts.length === 0 && (
                    <div className="border border-dashed border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-800/50 px-4 py-6 text-center text-sm text-slate-500 dark:text-slate-400">
                      {UI_TEXT.noAlerts}
                    </div>
                  )}

                  {visibleAlerts.map((alert) => (
                    <div
                      key={alert.alert_id}
                      className="module4-alert-card border border-slate-200 bg-white px-4 py-3"
                      data-testid={`module4-alert-card-${alert.alert_id}`}
                    >
                      <button
                        type="button"
                        onClick={() => void openNodeFromAlert(alert)}
                        className="w-full text-left"
                        data-testid={`module4-alert-open-${alert.alert_id}`}
                      >
                        <div className="flex items-start gap-3">
                          <div
                            className={cn(
                              'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center border',
                              alert.severity === 'red'
                                ? 'border-rose-200 bg-rose-50 text-rose-600'
                                : alert.severity === 'orange'
                                  ? 'border-amber-200 bg-amber-50 text-amber-700'
                                  : 'border-yellow-200 bg-yellow-50 text-yellow-700'
                            )}
                          >
                            <AlertTriangle size={16} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                                {severityLabel(alert.severity)}
                              </span>
                              <span className="text-[11px] text-slate-400">{alertStatusLabel(alert.status)}</span>
                            </div>
                            <div className="mt-2 text-sm font-semibold text-slate-900">{alert.title}</div>
                            <p className="mt-1 text-xs leading-5 text-slate-500">{alert.summary}</p>
                          </div>
                        </div>
                      </button>

                      <div className="mt-3 flex items-center justify-between gap-3">
                        <div className="text-[11px] text-slate-400">{`${UI_TEXT.riskScore} ${Math.round(alert.risk_score)}`}</div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void handleAckAlert(alert.alert_id)}
                            disabled={ackingAlertId === alert.alert_id}
                            className="border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {ackingAlertId === alert.alert_id ? UI_TEXT.acknowledging : UI_TEXT.acknowledge}
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleResolveAlert(alert.alert_id)}
                            disabled={resolvingAlertId === alert.alert_id}
                            className="border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-medium text-emerald-700 transition hover:border-emerald-300 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {resolvingAlertId === alert.alert_id ? UI_TEXT.resolving : UI_TEXT.resolve}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </aside>
        )}

        <div className="module4-ide-main pointer-events-none absolute inset-0 z-10">
          {/* 悬浮左上角控制面板 */}
          <header className="pointer-events-auto absolute left-6 top-6 z-20 flex items-center gap-4 rounded-2xl border border-blue-100/60 bg-[#fbfcfd]/90 px-5 py-3 shadow-sm backdrop-blur-md">
            <div className="flex items-center gap-3">
              <div className="text-base font-semibold tracking-tight text-slate-800">全域知识图谱</div>
              
              <div className="h-4 w-px bg-blue-200/50" />
              
              <div className="flex items-center gap-2">
                <select
                  data-testid="module4-file-select"
                  value={sourceMode === 'manual-select' ? manualFileHash : currentFileHash}
                  onChange={(event) => {
                    setManualFileHash(event.target.value);
                    setSourceMode('manual-select');
                  }}
                  className="bg-transparent text-sm font-medium text-slate-600 outline-none transition-colors hover:text-[#a3b8d7] cursor-pointer"
                >
                  <option value="">{UI_TEXT.followActiveFile}</option>
                  {graphFiles.map((item) => (
                    <option key={item.graph_file_id} value={item.file_hash}>
                      {item.file_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </header>

          <div className="relative flex min-h-0 flex-1 flex-row overflow-hidden pointer-events-none h-full w-full">
            
            {/* 左侧图谱区域 */}
            <div className="relative flex h-full flex-1 flex-col overflow-hidden">
              {/* 悬浮右上角控制面板 */}
              <div className="pointer-events-auto absolute right-6 top-6 z-20 flex items-center gap-5 rounded-2xl border border-blue-100/60 bg-[#fbfcfd]/90 px-4 py-2.5 shadow-sm backdrop-blur-md">
                <div className="flex items-center gap-2">
                  <select
                    data-testid="module4-layout-select"
                    value={layoutMode === ForceDirectedLayoutType ? 'force' : 'hierarchical'}
                    onChange={(e) => {
                      fitPendingRef.current = true;
                      setLayoutMode(e.target.value === 'force' ? ForceDirectedLayoutType : HierarchicalLayoutType);
                    }}
                    className="bg-transparent text-sm font-medium text-slate-600 outline-none transition-colors hover:text-[#a3b8d7] cursor-pointer"
                  >
                    <option value="force">{UI_TEXT.forceLayout}</option>
                    <option value="hierarchical">{UI_TEXT.hierarchicalLayout}</option>
                  </select>
                </div>

                <div className="h-4 w-px bg-blue-200/50" />

                <div className="flex items-center gap-1 rounded-lg bg-blue-50/50 p-0.5">
                  <button
                    type="button"
                    data-testid="module4-view-overview"
                    onClick={() => {
                      fitPendingRef.current = true;
                      if (preferEvidenceView) {
                        setGraphViewMode('evidence');
                        setMessage('当前图谱以证据节点为主，概览图暂不适用，已保持证据图展示。');
                        return;
                      }
                      setGraphViewMode('overview');
                    }}
                    className={cn(
                      'px-3 py-1 text-xs font-medium rounded-md transition-all',
                      effectiveGraphViewMode === 'overview' 
                        ? 'bg-white text-blue-600 shadow-sm border border-blue-100/50' 
                        : 'text-slate-500 hover:text-slate-800 hover:bg-slate-200/30'
                    )}
                  >
                    {UI_TEXT.overviewGraph}
                  </button>
                  <button
                    type="button"
                    data-testid="module4-view-evidence"
                    onClick={() => {
                      fitPendingRef.current = true;
                      setGraphViewMode('evidence');
                    }}
                    className={cn(
                      'px-3 py-1 text-xs font-medium rounded-md transition-all',
                      effectiveGraphViewMode === 'evidence' 
                        ? 'bg-white text-blue-600 shadow-sm border border-blue-100/50' 
                        : 'text-slate-500 hover:text-slate-800 hover:bg-slate-200/30'
                    )}
                  >
                    {UI_TEXT.evidenceGraph}
                  </button>
                </div>
              </div>

              {/* 悬浮右下角缩放控件 */}
              <div className="pointer-events-auto absolute bottom-8 right-8 z-20 flex items-center gap-1 rounded-2xl border border-blue-100/60 bg-[#fbfcfd]/90 px-2 py-1.5 shadow-lg backdrop-blur-xl">
                <button
                  type="button"
                  data-testid="module4-fit-view"
                  onClick={() => {
                    setActiveToolbarMenu(null);
                    fitGraph(undefined, true);
                  }}
                  className="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-slate-100 rounded-full transition-colors"
                  title={UI_TEXT.fitView}
                >
                  <Focus size={18} />
                </button>
                <div className="w-px h-4 bg-slate-200 mx-1" />
                <button
                  type="button"
                  data-testid="module4-zoom-in"
                  onClick={() => {
                    setActiveToolbarMenu(null);
                    adjustZoom(0.1);
                  }}
                  className="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-slate-100 rounded-full transition-colors"
                  aria-label={UI_TEXT.zoomIn}
                >
                  <Plus size={18} />
                </button>
                <button
                  type="button"
                  data-testid="module4-zoom-out"
                  onClick={() => {
                    setActiveToolbarMenu(null);
                    adjustZoom(-0.1);
                  }}
                  className="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-slate-100 rounded-full transition-colors"
                  aria-label={UI_TEXT.zoomOut}
                >
                  <Minus size={18} />
                </button>
                <div className="w-px h-4 bg-slate-200 mx-1" />
                <button
                  type="button"
                  data-testid="module4-refresh-graph"
                  onClick={() => {
                    setActiveToolbarMenu(null);
                    void loadGraph();
                  }}
                  className="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-slate-100 rounded-full transition-colors"
                  aria-label={UI_TEXT.refresh}
                >
                  <RefreshCw size={18} className={cn(loading && 'animate-spin')} />
                </button>
              </div>

              <div
                ref={graphHostRef}
                data-testid="module4-graph-host"
                className="pointer-events-auto module4-graph-host relative min-h-[420px] flex-1 overflow-hidden bg-white"
              >
                {filteredGraph.nodes.length === 0 ? (
                  <div className="absolute inset-0 flex items-center justify-center px-6">
                    <div className="module4-empty-state border border-dashed border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800/50 px-8 py-10 text-center">
                      <h3 className="text-xl font-semibold tracking-tight text-slate-900">{UI_TEXT.emptyGraphTitle}</h3>
                      <p className="mt-3 max-w-md text-sm leading-6 text-slate-600">{UI_TEXT.emptyGraphBody}</p>
                    </div>
                  </div>
                ) : (
                  <Neo4jStyleForceGraph
                    ref={nvlRef}
                    graph={filteredGraph}
                    layoutMode={layoutMode}
                    selectedNodeId={selectedNodeId}
                    pinnedNodeIds={pinnedNodeIds}
                    selectionNeighborhood={selectionNeighborhood}
                    onNodeClick={(nodeId, point) => {
                      openInspector(nodeId, point);
                    }}
                    onNodeDoubleClick={(nodeId) => {
                      openInspector(nodeId);
                      void expandNeighborhood(nodeId);
                    }}
                    onCanvasClick={closeInspector}
                    onNodeDragEnd={(nodeId) => {
                      setPinnedNodeIds((current) => Array.from(new Set([...current, nodeId])));
                    }}
                    className="absolute inset-0"
                  />
                )}
              </div>
            </div>

            <motion.aside
              layout
              transition={{ layout: { duration: 0.3, ease: [0.22, 1, 0.36, 1] } }}
              data-testid="module4-detail-aside"
              className={cn(
                'module4-details-aside custom-scrollbar pointer-events-auto flex shrink-0 flex-col overflow-y-auto bg-white/95 backdrop-blur-md shadow-[-4px_0_12px_rgba(0,0,0,0.03)] transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] dark:bg-slate-900/95 border-l border-slate-200/80 dark:border-slate-800/80',
                detailNode
                  ? 'w-[360px] opacity-100'
                  : 'w-0 opacity-0 overflow-hidden border-none'
              )}
            >
              <div className="sticky top-0 z-10 bg-white/90 backdrop-blur-sm border-b border-slate-100 dark:border-slate-800 dark:bg-slate-900/90 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {detailNode && (
                        <span className="inline-flex items-center rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                          {presentTypeLabel(detailNode)}
                        </span>
                      )}
                      {selectedPinned && (
                        <span className="inline-flex items-center rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:bg-amber-900/30 dark:text-amber-400">
                          {UI_TEXT.pinned}
                        </span>
                      )}
                    </div>
                    {detailNode ? (
                      <>
                        <h3
                          data-testid="module4-detail-title"
                          className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate"
                          title={displayNameOfNode(detailNode)}
                        >
                          {displayNameOfNode(detailNode)}
                        </h3>
                      </>
                    ) : (
                      <p className="text-xs text-slate-500">{UI_TEXT.noNodeDetails}</p>
                    )}
                  </div>

                  {detailNode && (
                    <button
                      type="button"
                      onClick={closeInspector}
                      className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 transition-colors"
                      aria-label={UI_TEXT.closeDetails}
                    >
                      <X size={14} strokeWidth={2} />
                    </button>
                  )}
                </div>
                {detailNode && summaryOfNode(detailNode) && (
                  <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed" title={summaryOfNode(detailNode)}>
                    {summaryOfNode(detailNode)}
                  </p>
                )}
              </div>

              <AnimatePresence mode="wait" initial={false}>
                {detailNode ? (
                  <motion.div
                    key={detailNode.node_id}
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    transition={{ duration: 0.2 }}
                    className="flex-1 px-4 py-3 space-y-4"
                  >
                    <div className="flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => togglePin(detailNode.node_id)}
                        className={cn(
                          "flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors border shadow-sm",
                          selectedPinned 
                            ? "bg-amber-50 text-amber-700 border-amber-200/60 hover:bg-amber-100" 
                            : "bg-white text-slate-700 border-slate-200/60 hover:bg-slate-50 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700"
                        )}
                      >
                        <Pin size={12} className={selectedPinned ? "fill-amber-700" : ""} />
                        {selectedPinned ? UI_TEXT.unpinNode : UI_TEXT.pinNode}
                      </button>
                      <button
                        type="button"
                        onClick={() => focusNode(detailNode.node_id)}
                        className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-white px-2 py-1.5 text-[11px] font-medium text-slate-700 transition-colors border border-slate-200/60 shadow-sm hover:bg-slate-50 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        <Focus size={12} />
                        {UI_TEXT.focusNode}
                      </button>
                      <button
                        type="button"
                        onClick={() => void expandNeighborhood(detailNode.node_id)}
                        className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-white px-2 py-1.5 text-[11px] font-medium text-blue-600 transition-colors border border-blue-200/60 shadow-sm hover:bg-blue-50 dark:bg-slate-800 dark:border-blue-900/30 dark:text-blue-400 dark:hover:bg-blue-900/20"
                      >
                        <Network size={12} />
                        {expanding ? UI_TEXT.expanding : UI_TEXT.expandNeighborhood}
                      </button>
                    </div>

                    {detailFactsOfNode(detailNode).length > 0 && (
                      <div className="space-y-2" data-testid="module4-detail-core-info">
                        <h4 className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">
                          核心信息
                        </h4>
                        <div className="grid grid-cols-2 gap-y-2 gap-x-3 rounded-md border border-slate-100 dark:border-slate-800/60 bg-slate-50/30 dark:bg-slate-800/20 p-2.5">
                          {detailFactsOfNode(detailNode).map((fact) => (
                            <div key={`${fact.label}-${fact.value}`} className="min-w-0">
                              <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400 mb-0.5">{fact.label}</div>
                              <div className="text-[11px] text-slate-700 dark:text-slate-300 truncate" title={fact.value}>{fact.value}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {detailAlerts.length > 0 && (
                      <div className="space-y-2">
                        <h4 className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">
                          {UI_TEXT.relatedAlerts}
                        </h4>
                        <div className="space-y-2">
                          {detailAlerts.map((alert) => (
                            <div key={alert.alert_id} className="rounded-md bg-white dark:bg-slate-800/30 p-3 border border-slate-100 dark:border-slate-800/60 shadow-sm">
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-1.5">
                                    <span className="bg-rose-50 dark:bg-rose-900/30 px-1.5 py-0.5 rounded text-[10px] font-medium text-rose-600 dark:text-rose-400">
                                      {severityLabel(alert.severity)}
                                    </span>
                                    <span className="text-[10px] text-slate-500">{alertStatusLabel(alert.status)}</span>
                                  </div>
                                  <div className="mt-1.5 text-xs font-semibold text-slate-900 dark:text-slate-100 truncate" title={alert.title}>{alert.title}</div>
                                  <p className="mt-1 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400 line-clamp-2" title={alert.summary}>{alert.summary}</p>
                                </div>
                                <span className="bg-slate-50 dark:bg-slate-900 px-1.5 py-0.5 rounded shadow-sm border border-slate-100 dark:border-slate-700 text-[10px] font-semibold text-slate-600 dark:text-slate-300 whitespace-nowrap">
                                  {Math.round(alert.risk_score)}分
                                </span>
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {alert.status === 'open' && (
                                  <button
                                    type="button"
                                    onClick={() => void handleAckAlert(alert.alert_id)}
                                    disabled={ackingAlertId === alert.alert_id}
                                    className="rounded bg-white dark:bg-slate-800 px-2 py-1 text-[10px] font-medium text-slate-600 dark:text-slate-300 shadow-sm border border-slate-200 dark:border-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    {ackingAlertId === alert.alert_id ? UI_TEXT.acknowledging : UI_TEXT.acknowledge}
                                  </button>
                                )}
                                {alert.status !== 'resolved' && (
                                  <button
                                    type="button"
                                    onClick={() => void handleResolveAlert(alert.alert_id)}
                                    disabled={resolvingAlertId === alert.alert_id}
                                    className="rounded bg-emerald-50 dark:bg-emerald-900/20 px-2 py-1 text-[10px] font-medium text-emerald-700 dark:text-emerald-400 border border-emerald-100 dark:border-emerald-800/30 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                    {resolvingAlertId === alert.alert_id ? UI_TEXT.resolving : UI_TEXT.resolve}
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="space-y-2" data-testid="module4-analysis-panel">
                      <h4 className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">
                        高级研判
                      </h4>

                      <div className="rounded-md bg-indigo-50/40 dark:bg-indigo-900/10 p-3 border border-indigo-100/50 dark:border-indigo-800/30">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-100 dark:border-indigo-800/30 rounded px-1.5 py-0.5 text-[10px] font-medium text-indigo-600 dark:text-indigo-400">
                            {analysisTargetLabel
                              ? `${UI_TEXT.currentAnalysisTarget} · ${shortText(analysisTargetLabel, 28)}`
                              : UI_TEXT.currentAnalysisTarget}
                          </span>
                          {primaryDetailAlert && (
                            <span className="bg-rose-50 dark:bg-rose-900/30 border border-rose-100 dark:border-rose-800/30 rounded px-1.5 py-0.5 text-[10px] font-medium text-rose-600 dark:text-rose-400">
                              {severityLabel(primaryDetailAlert.severity)}
                            </span>
                          )}
                        </div>

                        <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                          只在需要时对当前节点或关联告警做解释与模拟，避免和下方证据区重复展示。
                        </p>

                        {!primaryDetailAlert && (
                          <p className="mt-1 text-[10px] leading-relaxed text-amber-600">{UI_TEXT.simulationNeedsAlert}</p>
                        )}

                        <div className="mt-2.5 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => void handleExplainCurrent()}
                            disabled={!canRunExplain || explaining}
                            data-testid="module4-explain-btn"
                            className="flex-1 rounded-md bg-white dark:bg-slate-800 px-2 py-1.5 text-[11px] font-medium text-slate-700 dark:text-slate-200 shadow-sm border border-slate-200 dark:border-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {explaining ? UI_TEXT.explaining : UI_TEXT.explainAction}
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleSimulateCurrent()}
                            disabled={!canRunSimulate || simulating}
                            data-testid="module4-simulate-btn"
                            className="flex-1 rounded-md bg-indigo-500 px-2 py-1.5 text-[11px] font-medium text-white shadow-sm transition hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                              {simulating ? UI_TEXT.simulating : UI_TEXT.simulateAction}
                            </button>
                          </div>
                        </div>

                        {(explainResult || simulateResult) && (
                          <div className="mt-3 space-y-3 border-t border-slate-100 dark:border-slate-800/60 pt-3">
                            {explainResult && (
                              <div className="space-y-2" data-testid="module4-explain-result">
                                <div className="rounded-md border border-slate-200 dark:border-slate-700/80 bg-white dark:bg-slate-900/90 px-3 py-3 shadow-sm">
                                  <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                    最新解释
                                  </div>
                                  <div
                                    className="mt-1.5 text-xs font-medium text-slate-900 dark:text-slate-100 leading-relaxed"
                                    data-testid="module4-explain-conclusion"
                                  >
                                    {explainResult.conclusion}
                                  </div>
                                </div>
                                {explainResult.reasoning_steps.length > 0 && (
                                  <details className="rounded-md border border-slate-200 dark:border-slate-700/80 bg-white dark:bg-slate-900/90 px-3 py-3 shadow-sm">
                                    <summary className="cursor-pointer text-[10px] font-medium text-slate-500 dark:text-slate-400">
                                      查看推理过程
                                    </summary>
                                    <div className="mt-2 space-y-1.5">
                                      {explainResult.reasoning_steps.map((step, index) => (
                                        <div
                                          key={`${index + 1}-${step}`}
                                          className="rounded bg-slate-50 dark:bg-slate-800/40 px-2.5 py-1.5 text-[11px] leading-relaxed text-slate-700 dark:text-slate-300 border border-slate-100 dark:border-slate-700/50"
                                        >
                                          {`${index + 1}. ${step}`}
                                        </div>
                                      ))}
                                    </div>
                                  </details>
                                )}
                              </div>
                            )}

                            {simulateResult && (
                              <div className="space-y-2" data-testid="module4-simulate-result">
                                <div className="rounded-md border border-slate-200 dark:border-slate-700/80 bg-white dark:bg-slate-900/90 px-3 py-3 shadow-sm">
                                  <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                                    模拟结果
                                  </div>
                                  <div
                                    className="mt-1.5 text-xs font-medium text-slate-900 dark:text-slate-100 leading-relaxed"
                                    data-testid="module4-simulate-summary-text"
                                  >
                                    {simulateResult.summary}
                                  </div>
                                </div>
                                {(simulateResult.impacts.length > 0 || simulateResult.changed_alerts.length > 0) && (
                                  <details className="rounded-md border border-slate-200 dark:border-slate-700/80 bg-white dark:bg-slate-900/90 px-3 py-3 shadow-sm">
                                    <summary className="cursor-pointer text-[10px] font-medium text-slate-500 dark:text-slate-400">
                                      查看模拟细节
                                    </summary>
                                    <div className="mt-2 space-y-3">
                                      {simulateResult.impacts.length > 0 && (
                                        <div className="space-y-1.5">
                                          <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400">
                                            {UI_TEXT.simulationImpacts}
                                          </div>
                                          <div className="overflow-hidden rounded-md border border-slate-200 dark:border-slate-700 shadow-sm">
                                            {simulateResult.impacts.map((item, index) => (
                                              <div
                                                key={`${item.metric}-${metricValueText(item.value)}`}
                                                className={cn(
                                                  "grid grid-cols-[90px_minmax(0,1fr)] gap-2 bg-white dark:bg-slate-900 px-2.5 py-2",
                                                  index > 0 && "border-t border-slate-100 dark:border-slate-800"
                                                )}
                                              >
                                                <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400 self-center">
                                                  {simulationMetricLabel(item.metric)}
                                                </div>
                                                <div className="text-[11px] font-medium text-slate-700 dark:text-slate-200">
                                                  <pre className="overflow-x-auto whitespace-pre-wrap break-words font-sans">
                                                    {metricValueText(item.value)}
                                                  </pre>
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      )}

                                      {simulateResult.changed_alerts.length > 0 && (
                                        <div className="space-y-1.5">
                                          <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400">
                                            {UI_TEXT.simulationAlerts}
                                          </div>
                                          <div className="space-y-2">
                                            {simulateResult.changed_alerts.map((item, index) => {
                                              const payload = asRecord(item);
                                              return (
                                                <div
                                                  key={`${firstText(payload.alert_id, payload.rule_id, payload.title, index)}-${index}`}
                                                  className="rounded-md bg-slate-50 dark:bg-slate-800/40 px-3 py-2.5 border border-slate-100 dark:border-slate-700/50"
                                                >
                                                  <div className="flex flex-wrap items-center gap-1.5">
                                                    <span className="rounded bg-white dark:bg-slate-900 px-1.5 py-0.5 text-[9px] font-medium text-slate-600 dark:text-slate-300 shadow-sm border border-slate-200 dark:border-slate-700">
                                                      {firstText(payload.rule_id, payload.alert_id, '模拟结果')}
                                                    </span>
                                                    {firstText(payload.severity) && (
                                                      <span className="rounded bg-rose-50 dark:bg-rose-900/30 px-1.5 py-0.5 text-[9px] font-medium text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-800/30">
                                                        {severityLabel(firstText(payload.severity))}
                                                      </span>
                                                    )}
                                                  </div>
                                                  <div className="mt-1.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
                                                    {firstText(payload.title, payload.context_label, payload.summary, '模拟结果')}
                                                  </div>
                                                  {firstText(payload.summary) && (
                                                    <p className="mt-1 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
                                                      {firstText(payload.summary)}
                                                    </p>
                                                  )}
                                                </div>
                                              );
                                            })}
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </details>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {isDocumentDetailNode ? (
                        <>
                          {showEdgeEvidenceSection && (
                            <div className="space-y-3" data-testid="module4-detail-edge-evidence">
                              <h4 className="text-[13px] font-semibold text-slate-800 dark:text-slate-200 pb-1.5 border-b border-slate-100 dark:border-slate-800">
                                {edgeEvidenceTitle}
                              </h4>
                              {detailEdgeEvidenceRows.length > 0 ? (
                                <div className="space-y-3">
                                  {detailEdgeEvidenceRows.map(({ edge, evidence }) => (
                                    <div key={edge.edge_id} className="rounded-xl bg-slate-50/50 dark:bg-slate-800/30 p-3.5 border border-slate-100 dark:border-slate-700/50">
                                      <div className="flex items-center justify-between gap-3 mb-3">
                                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{relationLabelOf(edge)}</div>
                                        <span
                                          className="border px-2 py-0.5 rounded text-[10px] font-semibold text-slate-500 dark:text-slate-400"
                                          style={{
                                            borderColor: `${relationToneOf(edge)}40`,
                                            backgroundColor: `${relationToneOf(edge)}14`,
                                          }}
                                        >
                                          {Math.round(edge.confidence * 100)}%
                                        </span>
                                      </div>
                                      <div className="space-y-3">
                                        {evidence.map((item) => (
                                          <div key={item.evidence_id} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
                                            <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{evidenceLocatorText(item)}</div>
                                            <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{evidenceTitle(item)}</div>
                                            {evidenceSnippetText(item) && (
                                              <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                                                {evidenceSnippetText(item)}
                                              </p>
                                            )}
                                            {evidenceInsightChips(item).length > 0 && (
                                              <div className="mt-3 flex flex-wrap gap-2">
                                                {evidenceInsightChips(item).map((chip, index) => (
                                                  <span
                                                    key={`${item.evidence_id}-edge-chip-${index}`}
                                                    className="rounded-md border border-emerald-100/90 bg-emerald-50/70 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:border-emerald-900/80 dark:bg-emerald-950/40 dark:text-emerald-300"
                                                  >
                                                    {shortText(chip, 38)}
                                                  </span>
                                                ))}
                                              </div>
                                            )}
                                            {renderEvidenceDataframe(item)}
                                            {item.artifact_url && (
                                              <div className="mt-3">
                                                <a
                                                  href={item.artifact_url}
                                                  target="_blank"
                                                  rel="noreferrer"
                                                  className="rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-medium text-sky-700 shadow-sm transition hover:border-sky-300 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-900/30 dark:text-sky-300 dark:hover:border-sky-700 dark:hover:bg-sky-900/50"
                                                >
                                                  {UI_TEXT.openArtifact}
                                                </a>
                                              </div>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="px-3 py-4 text-sm text-slate-500 dark:text-slate-400">
                                  该文档的主要证据尚未挂到关系上。
                                </div>
                              )}
                            </div>
                          )}

                          {detailEvidence.length > 0 && (
                            <div className="space-y-2" data-testid="module4-detail-node-evidence">
                              <h4 className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">
                                {nodeEvidenceTitle}
                              </h4>
                              <div className="space-y-2">
                                {detailEvidence.map((item) => (
                                  <div key={item.evidence_id} className="rounded-md bg-white dark:bg-slate-800/30 p-3 border border-slate-100 dark:border-slate-800/60 shadow-sm">
                                    <div className="flex items-start justify-between gap-2">
                                      <div className="min-w-0">
                                        <div className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate" title={evidenceTitle(item)}>{evidenceTitle(item)}</div>
                                        <div className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400 truncate" title={evidenceLocatorText(item)}>{evidenceLocatorText(item)}</div>
                                      </div>
                                      <span className="shrink-0 rounded bg-slate-50 border border-slate-200 dark:border-slate-700 dark:bg-slate-900 px-1.5 py-0.5 text-[9px] font-medium text-slate-500 dark:text-slate-400 shadow-sm">
                                        {Math.round(item.confidence * 100)}%
                                      </span>
                                    </div>
                                    {evidenceSnippetText(item) && (
                                      <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-300 line-clamp-3" title={evidenceSnippetText(item)}>{evidenceSnippetText(item)}</p>
                                    )}
                                    {evidenceInsightChips(item).length > 0 && (
                                      <div className="mt-2 flex flex-wrap gap-1.5">
                                        {evidenceInsightChips(item).map((chip, index) => (
                                          <span
                                            key={`${item.evidence_id}-chip-${index}`}
                                            className="rounded border border-emerald-100 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-400"
                                          >
                                            {shortText(chip, 32)}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                    <div className="mt-2 text-[10px]">
                                      {renderEvidenceDataframe(item)}
                                    </div>
                                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                                      {item.artifact_url && (
                                        <a
                                          href={item.artifact_url}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="rounded border border-sky-200 bg-sky-50 px-2 py-1 text-[10px] font-medium text-sky-700 shadow-sm transition hover:border-sky-300 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-900/30 dark:text-sky-300 dark:hover:border-sky-700 dark:hover:bg-sky-900/50"
                                        >
                                          {UI_TEXT.openArtifact}
                                        </a>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      ) : (
                        <>
                          {showNodeEvidenceSection && (
                            <div className="space-y-2" data-testid="module4-detail-node-evidence">
                              <h4 className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">
                                {nodeEvidenceTitle}
                              </h4>
                              {detailEvidence.length > 0 ? (
                                <div className="space-y-2">
                                  {detailEvidence.map((item) => (
                                    <div key={item.evidence_id} className="rounded-md bg-white dark:bg-slate-800/30 p-3 border border-slate-100 dark:border-slate-800/60 shadow-sm">
                                      <div className="flex items-start justify-between gap-2">
                                        <div className="min-w-0">
                                          <div className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate" title={evidenceTitle(item)}>{evidenceTitle(item)}</div>
                                          <div className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400 truncate" title={evidenceLocatorText(item)}>{evidenceLocatorText(item)}</div>
                                        </div>
                                        <span className="shrink-0 rounded bg-slate-50 border border-slate-200 dark:border-slate-700 dark:bg-slate-900 px-1.5 py-0.5 text-[9px] font-medium text-slate-500 dark:text-slate-400 shadow-sm">
                                          {Math.round(item.confidence * 100)}%
                                        </span>
                                      </div>
                                      {evidenceSnippetText(item) && (
                                        <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-300 line-clamp-3" title={evidenceSnippetText(item)}>{evidenceSnippetText(item)}</p>
                                      )}
                                      {evidenceInsightChips(item).length > 0 && (
                                        <div className="mt-2 flex flex-wrap gap-1.5">
                                          {evidenceInsightChips(item).map((chip, index) => (
                                            <span
                                              key={`${item.evidence_id}-chip-${index}`}
                                              className="rounded border border-emerald-100 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-900/20 dark:text-emerald-400"
                                            >
                                              {shortText(chip, 32)}
                                            </span>
                                          ))}
                                        </div>
                                      )}
                                      <div className="mt-2 text-[10px]">
                                        {renderEvidenceDataframe(item)}
                                      </div>
                                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                                        {item.artifact_url && (
                                          <a
                                            href={item.artifact_url}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="rounded border border-sky-200 bg-sky-50 px-2 py-1 text-[10px] font-medium text-sky-700 shadow-sm transition hover:border-sky-300 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-900/30 dark:text-sky-300 dark:hover:border-sky-700 dark:hover:bg-sky-900/50"
                                          >
                                            {UI_TEXT.openArtifact}
                                          </a>
                                        )}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="px-3 py-4 text-sm text-slate-500 dark:text-slate-400">{UI_TEXT.noEvidence}</div>
                              )}
                            </div>
                          )}

                          {showEdgeEvidenceSection && (
                            <div className="space-y-3" data-testid="module4-detail-edge-evidence">
                              <h4 className="text-[13px] font-semibold text-slate-800 dark:text-slate-200 pb-1.5 border-b border-slate-100 dark:border-slate-800">
                                {edgeEvidenceTitle}
                              </h4>
                              {detailEdgeEvidenceRows.length > 0 ? (
                                <div className="space-y-3">
                                  {detailEdgeEvidenceRows.map(({ edge, evidence }) => (
                                    <div key={edge.edge_id} className="rounded-xl bg-slate-50/50 dark:bg-slate-800/30 p-3.5 border border-slate-100 dark:border-slate-700/50">
                                      <div className="flex items-center justify-between gap-3 mb-3">
                                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{relationLabelOf(edge)}</div>
                                        <span
                                          className="border px-2 py-0.5 rounded text-[10px] font-semibold text-slate-500 dark:text-slate-400"
                                          style={{
                                            borderColor: `${relationToneOf(edge)}40`,
                                            backgroundColor: `${relationToneOf(edge)}14`,
                                          }}
                                        >
                                          {Math.round(edge.confidence * 100)}%
                                        </span>
                                      </div>
                                      <div className="space-y-3">
                                        {evidence.map((item) => (
                                          <div key={item.evidence_id} className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 shadow-sm">
                                            <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{evidenceLocatorText(item)}</div>
                                            <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{evidenceTitle(item)}</div>
                                            {evidenceSnippetText(item) && (
                                              <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                                                {evidenceSnippetText(item)}
                                              </p>
                                            )}
                                            {evidenceInsightChips(item).length > 0 && (
                                              <div className="mt-3 flex flex-wrap gap-2">
                                                {evidenceInsightChips(item).map((chip, index) => (
                                                  <span
                                                    key={`${item.evidence_id}-edge-chip-${index}`}
                                                    className="rounded-md border border-emerald-100/90 bg-emerald-50/70 px-2.5 py-1 text-[11px] font-medium text-emerald-700 dark:border-emerald-900/80 dark:bg-emerald-950/40 dark:text-emerald-300"
                                                  >
                                                    {shortText(chip, 38)}
                                                  </span>
                                                ))}
                                              </div>
                                            )}
                                            {renderEvidenceDataframe(item)}
                                            {item.artifact_url && (
                                              <div className="mt-3">
                                                <a
                                                  href={item.artifact_url}
                                                  target="_blank"
                                                  rel="noreferrer"
                                                  className="rounded-md border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-medium text-sky-700 shadow-sm transition hover:border-sky-300 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-900/30 dark:text-sky-300 dark:hover:border-sky-700 dark:hover:bg-sky-900/50"
                                                >
                                                  {UI_TEXT.openArtifact}
                                                </a>
                                              </div>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="px-3 py-4 text-sm text-slate-500 dark:text-slate-400">{UI_TEXT.noEdgeEvidence}</div>
                              )}
                            </div>
                          )}
                        </>
                      )}

                      {detailNeighbors.length > 0 && (
                        <div className="space-y-3" data-testid="module4-detail-related-nodes">
                          <h4 className="text-[13px] font-semibold text-slate-800 dark:text-slate-200 pb-1.5 border-b border-slate-100 dark:border-slate-800">
                            {UI_TEXT.relatedNodes}
                          </h4>
                          <div className="flex flex-wrap gap-2">
                            {detailNeighbors.map((neighbor) => (
                              <button
                                key={neighbor.node_id}
                                type="button"
                                onClick={() => {
                                  startTransition(() => {
                                    setGraphData((current) => mergeGraph(current, detailGraph));
                                  });
                                  openInspector(neighbor.node_id);
                                  window.setTimeout(() => focusNode(neighbor.node_id), 120);
                                }}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                              >
                                <span
                                  className="h-2 w-2 rounded-full"
                                  style={{ backgroundColor: visualSpecOf(neighbor).color }}
                                />
                                {shortText(displayNameOfNode(neighbor), 20)}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {attributeRowsOfNode(detailNode).length > 0 && (
                        <div className="space-y-3" data-testid="module4-detail-attributes">
                          <h4 className="text-[13px] font-semibold text-slate-800 dark:text-slate-200 pb-1.5 border-b border-slate-100 dark:border-slate-800">
                            补充属性
                          </h4>
                          <div className="space-y-2">
                            {attributeRowsOfNode(detailNode).map((row) => (
                              <div
                                key={`${row.label}-${row.value}`}
                                className="flex items-start justify-between gap-3 rounded-lg bg-slate-50/50 dark:bg-slate-800/30 p-2.5 border border-slate-100 dark:border-slate-700/50"
                              >
                                <div className="text-[11px] font-medium text-slate-500 dark:text-slate-400">{row.label}</div>
                                <div className="max-w-[200px] text-right text-xs font-medium text-slate-700 dark:text-slate-200">{row.value}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {detailEdges.length > 0 && (
                        <div className="space-y-3" data-testid="module4-detail-relations">
                          <h4 className="text-[13px] font-semibold text-slate-800 dark:text-slate-200 pb-1.5 border-b border-slate-100 dark:border-slate-800">
                            {UI_TEXT.edgeRelations}
                          </h4>
                          <div className="space-y-2">
                            {detailEdges.slice(0, 6).map((edge) => (
                              <div key={edge.edge_id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-50/50 dark:bg-slate-800/30 p-2.5 text-[11px] text-slate-600 dark:text-slate-300 border border-slate-100 dark:border-slate-700/50">
                                <span className="font-medium">{relationLabelOf(edge)}</span>
                                <span
                                  className="border px-2 py-0.5 rounded text-[10px] font-semibold text-slate-500 dark:text-slate-400"
                                  style={{ borderColor: `${relationToneOf(edge)}40`, backgroundColor: `${relationToneOf(edge)}14` }}
                                >
                                  {Math.round(edge.confidence * 100)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                  </motion.div>
                ) : (
                  <motion.div
                    key="detail-empty"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    className="flex flex-1 items-center justify-center px-6 py-8"
                  >
                    <div className="module4-empty-state module4-detail-empty border border-dashed border-slate-300 dark:border-slate-600 bg-white/90 dark:bg-slate-800/50 px-6 py-8 text-center">
                      <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{UI_TEXT.detailsPanel}</div>
                      <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-slate-400">{UI_TEXT.noNodeDetails}</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.aside>
        </div>
      </div>
      </div>
    </section>
  );
};

