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
import { cn } from '../../lib/utils';
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
  searchModule4GraphRag,
  simulateModule4,
  updateModule4Rule,
  type Module4AlertItem,
  type Module4EvidenceItem,
  type Module4ExplainResponse,
  type Module4GraphEdge,
  type Module4GraphFileItem,
  type Module4GraphNode,
  type Module4GraphResponse,
  type Module4GraphRagQueryMode,
  type Module4GraphRagQueryResponse,
  type Module4HealthzResponse,
  type Module4JobResponse,
  type Module4NodeDetailResponse,
  type Module4RuleItem,
  type Module4SimulateResponse,
} from '../../shared/api/knowledgeGraph';
import { subscribeExtractionUpdates } from '../../shared/state/extractionDocuments';
import {
  ARTIFACT_PATTERNS,
  GENERIC_ENTITY_NAME_MAP,
  OVERVIEW_COMMUNITY_RELATIONS,
  OVERVIEW_NODE_TYPES,
  OVERVIEW_SEMANTIC_RELATIONS,
  asList,
  asRecord,
  clamp,
  cleanArtifactText,
  fileGraphPendingSourceKey,
  firstText,
  getActiveExtractionFileHash,
  graphFileHasUsableVersion,
  graphFileSourceKey,
  isRecord,
  nestedText,
  normalizeText,
  normalizeTypeKey,
  numberOrNull,
  prettifyToken,
  shortText,
  stripFileExtension,
  stripWrappingQuotes,
} from '../../features/knowledge-graph/utils';
import {
  buildSemanticSectorPositions,
  semanticZoneOfNode,
  type SemanticZoneKey,
  zoneStrengthOf,
} from '../../features/knowledge-graph/layoutPlanner';
import { buildNodeConnectionNarrative } from '../../features/knowledge-graph/detailNarrative';
import { KnowledgeGraphLegend } from '../../features/knowledge-graph/GraphLegend';
import { buildLegendEdgeItems, buildLegendNodeItems } from '../../features/knowledge-graph/legendModel';
import { resolveGraphNodeOverlaps } from '../../features/knowledge-graph/overlapResolver';
import { buildGraphRevealModel } from '../../features/knowledge-graph/revealModel';
import {
  edgeVisualPaletteOf,
  relationToneOf,
  visualSpecOf,
} from '../../features/knowledge-graph/renderTheme';

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
  chunk: '切片',
  entity: '实体',
  field: '字段',
  figure: '图表',
  image: '图片',
  table: '表格',
  risk: '风险',
  community: '社区',
  covariate: '协变量',
  node: '节点',
};

const RELATION_LABELS: Record<string, string> = {
  contains: '包含',
  related: '关联',
  related_to: '关联',
  links_to: '链接到',
  part_of: '属于',
  has_entity: '包含实体',
  has_chunk: '包含切片',
  has_field: '包含字段',
  has_warning: '包含警告',
  has_finding: '包含发现',
  has_evidence: '包含证据',
  in_community: '属于社区',
};

Object.assign(TYPE_LABELS, {
  business_context: 'Business Context',
  topic: 'Topic',
  observation: 'Observation',
  claim: 'Claim',
  business_alert: 'Business Alert',
});

Object.assign(RELATION_LABELS, {
  extracts: 'Extracts',
  describes_context: 'Context',
  has_topic: 'Topic',
  has_observation: 'Observation',
  states_claim: 'Claim',
  raises_business_alert: 'Business Alert',
  grounded_in: 'Grounded In',
  supported_by: 'Supported By',
});

// Enforce ASCII-safe labels to avoid mojibake in environments with mixed encodings.
Object.assign(TYPE_LABELS, {
  document: '文档',
  chunk: '分块',
  entity: '实体',
  field: '字段',
  figure: '图表',
  image: '图像',
  table: '表格',
  risk: '风险',
  community: '社区',
  covariate: '协变量',
  node: '节点',
  business_context: '业务上下文',
  topic: '主题',
  observation: '观察',
  claim: '结论',
  business_alert: '业务预警',
});

Object.assign(RELATION_LABELS, {
  contains: '包含',
  related: '关联',
  related_to: '关联到',
  links_to: '链接到',
  part_of: '属于',
  has_entity: '包含实体',
  has_chunk: '包含分块',
  has_field: '包含字段',
  has_warning: '包含告警',
  has_finding: '包含发现',
  has_evidence: '包含证据',
  in_community: '属于社区',
  extracts: '抽取',
  describes_context: '描述上下文',
  has_topic: '包含主题',
  has_observation: '包含观察',
  states_claim: '陈述结论',
  raises_business_alert: '触发业务预警',
  grounded_in: '依据于',
  supported_by: '由…支撑',
});

// Force precise Chinese labels with unicode escapes to avoid encoding-dependent mojibake.
Object.assign(TYPE_LABELS, {
  document: '\u6587\u6863',
  chunk: '\u5206\u5757',
  entity: '\u5b9e\u4f53',
  field: '\u5b57\u6bb5',
  figure: '\u56fe\u8868',
  image: '\u56fe\u50cf',
  table: '\u8868\u683c',
  risk: '\u98ce\u9669',
  community: '\u793e\u533a',
  community_report: '\u793e\u533a\u62a5\u544a',
  covariate: '\u534f\u53d8\u91cf',
  node: '\u8282\u70b9',
  business_context: '\u4e1a\u52a1\u4e0a\u4e0b\u6587',
  topic: '\u4e3b\u9898',
  observation: '\u89c2\u5bdf',
  claim: '\u7ed3\u8bba',
  business_alert: '\u4e1a\u52a1\u9884\u8b66',
});

Object.assign(RELATION_LABELS, {
  contains: '\u5305\u542b',
  related: '\u5173\u8054',
  related_to: '\u5173\u8054\u5230',
  links_to: '\u94fe\u63a5\u5230',
  part_of: '\u5c5e\u4e8e',
  has_entity: '\u5305\u542b\u5b9e\u4f53',
  has_chunk: '\u5305\u542b\u5206\u5757',
  has_field: '\u5305\u542b\u5b57\u6bb5',
  has_warning: '\u5305\u542b\u544a\u8b66',
  has_finding: '\u5305\u542b\u53d1\u73b0',
  has_evidence: '\u5305\u542b\u8bc1\u636e',
  in_community: '\u5c5e\u4e8e\u793e\u533a',
  has_report: '\u5305\u542b\u62a5\u544a',
  extracts: '\u62bd\u53d6',
  describes_context: '\u63cf\u8ff0\u4e0a\u4e0b\u6587',
  has_topic: '\u5305\u542b\u4e3b\u9898',
  has_observation: '\u5305\u542b\u89c2\u5bdf',
  states_claim: '\u9648\u8ff0\u7ed3\u8bba',
  raises_business_alert: '\u89e6\u53d1\u4e1a\u52a1\u9884\u8b66',
  grounded_in: '\u4f9d\u636e\u4e8e',
  supported_by: '\u7531\u2026\u652f\u6491',
});

const EMPTY_GRAPH: Module4GraphResponse = {
  nodes: [],
  edges: [],
  source: 'graphrag:artifact:empty',
  workspace_id: null,
  stats: {
    node_count: 0,
    edge_count: 0,
    by_node_type: {},
    by_relation_type: {},
  },
};


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
      !/^(?:citations?|notes?|references?)[:\s]*$/i.test(line) &&
      !/^\[\d+\]/.test(line)
  );

  const titleLike =
    contentLines.find((line) => /^appendix\s+[a-z0-9]+[:.]?\s+.+$/i.test(line)) ||
    contentLines.find((line) => /^chapter\s+\d+[:.]?\s+.+$/i.test(line)) ||
    contentLines.find((line) => /\b(19|20)\d{2}\b/.test(line) && /[A-Za-z\u4e00-\u9fa5]/.test(line)) ||
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
  const stripped = text.replace(/[^\p{L}\p{N}]+/gu, '');
  return stripped.length === 0;
};

const looksLikeLowSignalArtifactTitle = (value: unknown, objectId: unknown = '') => {
  const text = cleanArtifactText(value);
  if (!text) return true;
  if (looksLikePlaceholderText(text)) return true;
  if (looksLikeFileNameText(text)) return true;
  const lower = text.toLowerCase();
  if (/^(?:page|p)\s*\d+$/i.test(lower)) return true;
  const normalizedObjectId = normalizeText(objectId).toLowerCase();
  if (normalizedObjectId && lower.includes(normalizedObjectId)) return true;
  return /(?:^|\s)(table|figure|image|fig|chart)[\s_-]*\d+(?:\s|$)/i.test(lower);
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
    field_extract_error: '字段抽取错误',
    table_extract_error: '表格抽取错误',
    parse_error: '解析错误',
    warning: '警告',
  };
  const label = titleMap[code] || prettifyToken(code);
  const detail = normalizeText(rest.join(':'));
  return detail ? `${label}: ${detail}` : label;
};

const alertFileHashOf = (alert: Module4AlertItem) => {
  const payload = asRecord(alert.payload);
  return firstText(payload.file_hash, nestedText(payload, 'context', 'file_hash'));
};

const typeKeyOf = (node: Module4GraphNode | string) => {
  if (typeof node === 'string') return normalizeTypeKey(node);
  return normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
};

const isRefactorEntityField = (node: Module4GraphNode) => {
  if (typeKeyOf(node) !== 'field') return false;
  const attrs = asRecord(node.attrs);
  return normalizeTypeKey(attrs.entity_kind) === 'refactor_extracted_entity';
};

const presentTypeLabel = (node: Module4GraphNode | string) => {
  if (typeof node !== 'string' && isRefactorEntityField(node)) {
    return 'Entity';
  }
  const key = typeKeyOf(node);
  if (TYPE_LABELS[key]) return TYPE_LABELS[key];
  if (typeof node === 'string') return prettifyToken(key);
  return prettifyToken(firstText(node.type_label, node.category, node.node_type, 'Node'));
};

const legacyPresentRelationLabel = (edge: Module4GraphEdge) =>
  RELATION_LABELS[normalizeTypeKey(edge.relation_label || edge.relation_type)] ||
  prettifyToken(firstText(edge.relation_label, edge.relation_type, 'Relation'));

const presentRelationLabel = (edge: Module4GraphEdge) =>
  (normalizeTypeKey(edge.relation_label || edge.relation_type) === 'overview_context'
    ? 'Overview Context'
    : '') ||
  RELATION_LABELS[normalizeTypeKey(edge.relation_label || edge.relation_type)] ||
  prettifyToken(firstText(edge.relation_label, edge.relation_type, 'Relation'));

const relationLabelOf = (edge: Module4GraphEdge) => {
  const key = normalizeTypeKey(edge.relation_label || edge.relation_type);
  if (key === 'overview_context') return 'Overview Context';
  return RELATION_LABELS[key] || prettifyToken(firstText(edge.relation_label, edge.relation_type, 'Relation'));
};

const edgeWeightText = (edge: Module4GraphEdge) => {
  const attrs = asRecord(edge.attrs);
  const weight = numberOrNull(attrs.weight);
  if (weight === null) return '';
  return `权重 ${weight.toFixed(2)}`;
};

const edgeRenderWidth = (edge: Module4GraphEdge) => {
  const confidence = clamp(Number(edge.confidence || 0), 0, 1);
  const baseWidth = Math.max(1.6, 1.2 + confidence * 2);
  const attrs = asRecord(edge.attrs);
  const weight = numberOrNull(attrs.weight);
  if (weight === null) return baseWidth;
  const weightBoost = Math.min(2.2, Math.log2(Math.max(1, weight) + 1) * 0.9);
  return clamp(baseWidth + weightBoost, 1.6, 5.4);
};

const typePriority = (value: string) => {
  const key = normalizeTypeKey(value);
  if (key === 'document') return 0;
  if (key === 'business_context') return 1;
  if (key === 'topic') return 2;
  if (key === 'business_alert') return 3;
  if (key === 'claim') return 4;
  if (key === 'observation') return 5;
  if (key === 'community') return 6;
  if (key === 'community_report') return 7;
  if (key === 'entity') return 8;
  if (key === 'risk') return 9;
  if (key === 'table') return 10;
  if (key === 'figure' || key === 'image') return 11;
  if (key === 'chunk') return 12;
  if (key === 'field') return 13;
  return 14;
};

const nodeRoleOf = (node: Module4GraphNode): GraphNodeRole => {
  const key = typeKeyOf(node);
  if (isRefactorEntityField(node)) return 'semantic';
  if (key === 'document') return 'anchor';
  if (
    key === 'entity' ||
    key === 'community' ||
    key === 'community_report' ||
    key === 'risk' ||
    key === 'business_context' ||
    key === 'topic' ||
    key === 'observation' ||
    key === 'claim' ||
    key === 'business_alert'
  ) {
    return 'semantic';
  }
  if (key === 'figure' || key === 'image' || key === 'table') return 'evidence';
  return 'structural';
};

const edgeRoleOf = (edge: Module4GraphEdge): GraphEdgeRole => {
  const key = normalizeTypeKey(edge.relation_type || edge.relation_label);
  if (key === 'overview_context') return 'anchor';
  if (OVERVIEW_SEMANTIC_RELATIONS.has(key)) return 'semantic';
  if (key.includes('evidence') || key.includes('support')) return 'evidence';
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

  if (typeKey === 'business_context' || typeKey === 'topic') {
    return normalizedDegree >= 0.24 || degree > 0 ? 'secondary' : 'tertiary';
  }

  if (typeKey === 'business_alert' || typeKey === 'claim' || typeKey === 'observation') {
    return normalizedDegree >= 0.2 || degree > 0 ? 'tertiary' : 'normal';
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
      : typeKey === 'business_context'
        ? 0.78
        : typeKey === 'topic'
          ? 0.72
          : typeKey === 'business_alert'
            ? 0.66
            : typeKey === 'claim'
              ? 0.58
              : typeKey === 'observation'
                ? 0.52
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

  const preferredKinds = [
    'business_context',
    'topic',
    'business_alert',
    'community',
    'entity',
    'claim',
    'observation',
  ];

  let fallbackTargets: Module4GraphNode[] = [];
  for (const kind of preferredKinds) {
    const matches = semanticNodes
      .filter((node) => typeKeyOf(node) === kind)
      .sort((left, right) => (degreeMap.get(right.node_id) || 0) - (degreeMap.get(left.node_id) || 0))
      .slice(0, kind === 'business_context' ? 2 : 3);
    if (matches.length > 0) {
      fallbackTargets = matches;
      break;
    }
  }

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
  if (key === 'business_context') score += 220;
  if (key === 'topic') score += 200;
  if (key === 'business_alert') score += 190;
  if (key === 'claim') score += 160;
  if (key === 'observation') score += 150;
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

const titleFromSnippet = (snippet: string, typeKey: string) => {
  const cleaned = cleanArtifactText(snippet);
  if (!cleaned) return '';

  if (typeKey === 'figure' || typeKey === 'image') {
    const figureMatch = cleaned.match(
      /(?:^|\b)(?:figure|fig\.?|image|caption)\s*[:#.-]?\s*(.+)$/i
    );
    if (figureMatch?.[1]) {
      return cleanArtifactText(figureMatch[1]);
    }
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

  if (key === 'business_context') {
    return firstText(
      cleanArtifactText(firstText(attrs.title, attrs.summary, attrs.domain, attrs.name)),
      primaryDisplay,
      'Business Context'
    );
  }

  if (key === 'topic') {
    return firstText(
      cleanArtifactText(firstText(attrs.topic_label, attrs.title, attrs.summary, attrs.name)),
      primaryDisplay,
      'Topic'
    );
  }

  if (key === 'observation') {
    return firstText(
      cleanArtifactText(firstText(attrs.summary, attrs.observation_label, attrs.metric_label, attrs.title)),
      primaryDisplay,
      'Observation'
    );
  }

  if (key === 'claim') {
    return firstText(
      cleanArtifactText(firstText(attrs.summary, attrs.claim_text, attrs.title, attrs.name)),
      primaryDisplay,
      'Claim'
    );
  }

  if (key === 'business_alert') {
    return firstText(
      cleanArtifactText(firstText(attrs.summary, attrs.alert_title, attrs.title, attrs.name)),
      primaryDisplay,
      'Business Alert'
    );
  }

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
      'Document'
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

  if (key === 'community_report') {
    return firstText(
      cleanArtifactText(firstText(attrs.title, attrs.report_title)),
      extractSemanticTitle(firstText(attrs.summary, attrs.description)),
      primaryDisplay,
      '社区报告'
    );
  }

  if (key === 'field') {
    if (isRefactorEntityField(node)) {
      return firstText(
        cleanArtifactText(firstText(attrs.value, attrs.name, attrs.title, attrs.field_name)),
        primaryDisplay,
        'Entity'
      );
    }
    return firstText(
      cleanArtifactText(firstText(attrs.field_name, attrs.name, attrs.title)),
      primaryDisplay,
      presentTypeLabel(node)
    );
  }

  if (key === 'risk') {
    return firstText(humanizeWarning(attrs.warning), cleanedDisplay, 'Risk');
  }

  if (key === 'chunk') {
    return firstText(
      extractSemanticTitle(attrs.text),
      extractSemanticTitle(attrs.raw_content),
      titleFromSnippet(firstText(attrs.snippet, attrs.text, cleanedDisplay), key),
      'Chunk'
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
      artifactTitle ? `${label} - ${artifactTitle}` : '',
      page ? `${label} - ${page}` : '',
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
    return lower === 'table' || /^table\b/.test(lower) || text.length <= 3;
  }

  if (typeKey === 'figure' || typeKey === 'image') {
    return (
      lower === 'image' ||
      lower === 'figure' ||
      lower === 'fig' ||
      /^fig\.?\b/.test(lower) ||
      text.length <= 4
    );
  }

  return false;
};

const compactDocumentCaption = (value: string) =>
  normalizeText(stripFileExtension(value))
    .replace(/[\uFFFD\u00EF\u00BF\u00BD?]{2,}/g, '')
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
          ? `${presentTypeLabel(node)} - ${refinedTitle}`
          : page
            ? `${presentTypeLabel(node)} - ${page}`
            : presentTypeLabel(node);
      return shortText(artifactBase, Math.max(10, maxLength));
    }

    const candidateHasPage = Boolean(page) && normalizeText(candidate).toLowerCase().includes(page.toLowerCase());
    return shortText(page && !candidateHasPage ? `${candidate} - ${page}` : candidate, maxLength);
  }

  return shortText(compact, maxLength);
};

const summaryOfNode = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const diagnostics = asRecord(attrs.diagnostics);
  const context = asRecord(attrs.context);
  const warning = humanizeWarning(attrs.warning);
  if (warning) return shortText(warning, 180);

  const typeKey = typeKeyOf(node);
  if (
    typeKey === 'business_context' ||
    typeKey === 'topic' ||
    typeKey === 'observation' ||
    typeKey === 'claim' ||
    typeKey === 'business_alert'
  ) {
    const semanticSummary = cleanArtifactText(
      firstText(attrs.summary, attrs.description, attrs.claim_text, attrs.metric_label, attrs.alert_kind)
    );
    if (semanticSummary) return shortText(semanticSummary, 180);
  }

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

  if (typeKey === 'document') {
    const parts = [
      numberOrNull(diagnostics.figure_count) ? String(diagnostics.figure_count) + ' figures' : '',
      numberOrNull(diagnostics.table_count) ? String(diagnostics.table_count) + ' tables' : '',
      numberOrNull(diagnostics.trace_hit_count) ? String(diagnostics.trace_hit_count) + ' trace hits' : '',
      firstText(diagnostics.quality_status) ? 'quality ' + String(diagnostics.quality_status) : '',
    ].filter(Boolean);
    if (parts.length) return parts.join(' | ');
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

  push('Type', presentTypeLabel(node));
  push('Domain', attrs.domain);
  push('Severity', attrs.severity);
  push('Source', firstText(attrs.source_doc, attrs.file_name, nestedText(context, 'doc_name')));
  if (firstText(attrs.page, nestedText(context, 'page'))) {
    push('Page', 'p.' + firstText(attrs.page, nestedText(context, 'page')));
  }
  if (node.confidence > 0) push('Confidence', String(Math.round(node.confidence * 100)) + '%');
  push('Object Type', attrs.object_type);
  push('Entity Kind', attrs.entity_kind);
  if (numberOrNull(diagnostics.figure_count)) push('Figures', diagnostics.figure_count);
  if (numberOrNull(diagnostics.table_count)) push('Tables', diagnostics.table_count);
  push('Quality Status', diagnostics.quality_status);

  return facts.slice(0, 8);
};

const attributeRowsOfNode = (node: Module4GraphNode): DetailFact[] => {
  const attrs = asRecord(node.attrs);
  const context = asRecord(attrs.context);
  const typeKey = typeKeyOf(node);
  const rows: DetailFact[] = [];
  const snippet = cleanArtifactText(firstText(attrs.snippet, nestedText(context, 'caption_hint')));

  const push = (label: string, value: unknown) => {
    const text = normalizeText(value);
    if (!text) return;
    if (rows.some((item) => item.label === label && item.value === text)) return;
    rows.push({ label, value: shortText(text, 200) });
  };

  if (snippet && !isRedundantArtifactPageSnippet(node, snippet)) {
    push('Snippet', snippet);
  }
  push('Warning', humanizeWarning(attrs.warning));
  push('Value', attrs.value);
  push('Entity Kind', attrs.entity_kind);
  if (typeKey === 'community_report') {
    push('报告摘要', attrs.summary);
  }
  const mentionChunkIds = asList(attrs.mention_chunk_ids).map((item) => normalizeText(item)).filter(Boolean);
  if (mentionChunkIds.length > 0) {
    push('命中分块', mentionChunkIds.slice(0, 6).join(', '));
  }
  push('Source Ref ID', firstText(attrs.source_ref_id, attrs.ref_id));
  push('File Hash', attrs.file_hash);

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

type SeedLaneKey = SemanticZoneKey;

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

/* Legacy local fallback removed. Module 4 renders persisted state only. */

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
  const labelsZh: Record<string, string> = {
    red: '\u9ad8\u5371',
    orange: '\u4e2d\u5371',
    yellow: '\u4f4e\u5371',
  };
  return labelsZh[normalized] || '\u672a\u77e5';
};

const alertStatusLabel = (value?: string) => {
  const normalized = String(value || '').toLowerCase();
  const labelsZh: Record<string, string> = {
    open: '\u5f85\u5904\u7406',
    ack: '\u5df2\u786e\u8ba4',
    resolved: '\u5df2\u89e3\u51b3',
    false_positive: '\u8bef\u62a5',
  };
  return labelsZh[normalized] || '\u672a\u77e5';
};
const UI_TEXT = {
  workspaceLabel: '工作空间',
  versionLabel: '版本',
  title: '知识图谱',
  description: '在不改变后端协议的前提下，探索实体、证据、结构与风险警报。',
  refresh: '刷新',
  refreshGraph: '刷新图谱',
  module2FallbackSource: '模块二（降级源）',
  module4Source: '模块四（主源）',
  graphCanvas: '图谱画布',
  utilityDockTitle: '工具坞',
  utilityFiltersTitle: '过滤器',
  utilityFiltersSubtitle: '控制图谱的范围与可见性。',
  collapseUtilityDock: '收起工具坞',
  expandUtilityDock: '展开工具坞',
  clearFilters: '清除过滤器',
  searchLabel: '搜索',
  searchPlaceholder: '搜索节点、边、证据或文件',
  scopeLabel: '范围',
  followActiveFile: '跟随当前文件',
  manualSelect: '手动选择',
  selectGraphFile: '选择图谱文件',
  followingActiveFile: '正在跟随当前活动文件',
  noGraphFileSelected: '未选择图谱文件',
  selectedFilePendingGraphRecord: '所选文件暂无图谱记录',
  currentAnalysisTarget: '当前分析目标',
  overviewGraph: '概览图谱',
  evidenceGraph: '证据图谱',
  forceLayout: '动态关系布局',
  hierarchicalLayout: '语义工作台布局',
  fitView: '适应画布',
  zoomIn: '放大',
  zoomOut: '缩小',
  nodeTypesTitle: '节点类型',
  nodeTypesSubtitle: '过滤可见的节点类别。',
  rulesTitle: '规则',
  rulesSubtitle: '检查与切换图谱规则。',
  allEnabledRules: '所有启用的规则',
  selectedRule: '选中的规则',
  selectRuleHint: '选择一条规则以查看详情。',
  enableRule: '启用规则',
  disableRule: '禁用规则',
  switchingRule: '切换规则中',
  ruleEnabled: '规则已启用',
  ruleDisabled: '规则已禁用',
  runtimeStatus: '运行时状态',
  runtimeHealthy: '健康',
  runtimeNotReady: '未就绪',
  graphRagLabel: 'GraphRAG',
  databaseLabel: '数据库',
  statusReady: '就绪',
  statusUnavailable: '不可用',
  statusConnected: '已连接',
  statusDisconnected: '已断开',
  jobStatus: '任务状态',
  jobIdle: '空闲',
  nodeCountMetric: '节点数',
  edgeCountMetric: '边数',
  alertCountMetric: '警报数',
  noRules: '暂无规则。',
  noAlerts: '暂无警报。',
  alertsTitle: '警报',
  alertsSubtitle: '追踪图谱与证据风险。',
  acknowledge: '确认',
  acknowledging: '确认中',
  resolve: '解决',
  resolving: '解决中',
  pinned: '已固定',
  pinNode: '固定节点',
  unpinNode: '取消固定',
  focusNode: '聚焦节点',
  expandNeighborhood: '展开邻居',
  expanding: '展开中',
  explainAction: '解释',
  explaining: '解释中',
  simulateAction: '模拟',
  simulating: '模拟中',
  closeDetails: '关闭详情',
  detailsPanel: '详情面板',
  attributesTitle: '属性',
  noNodeDetails: '暂无节点详情。',
  noEvidence: '暂无证据。',
  noEdgeEvidence: '暂无边证据。',
  artifactEvidence: '制品证据',
  documentEvidence: '文档证据',
  edgeRelations: '边关系',
  edgeEvidence: '边证据',
  nodeEvidence: '节点证据',
  emptyGraphTitle: '无图谱数据',
  emptyGraphBody: '当前选择暂无图谱数据可用。',
  openArtifact: '打开制品',
  relatedNodes: '相关节点',
  relatedAlerts: '相关警报',
  riskScore: '风险评分',
  simulationTitle: '模拟',
  simulationDetails: '模拟详情',
  reasoningSteps: '推理步骤',
  explanationTitle: '解释',
  simulationAlerts: '模拟警报',
  simulationImpacts: '模拟影响',
  simulationNeedsAlert: '模拟需要至少一个警报才能进行。',
  untitledAlert: '未命名警报',
  ruleFallback: '规则',
  graphResourcesLoadFailed: '图谱资源加载失败。',
  usingActiveGraphFile: '正在使用活动图谱文件。',
  activeGraphFileNotReady: '活动图谱文件尚未就绪。',
  coreDetails: '核心详情',
  analysisTitle: '分析',
  analysisTip: '在运行解释或模拟操作之前，请查阅所选警报、其支持证据以及相关的图谱上下文。',
  unresolvedAlerts: '未解决',
} as const;

const UI_TEXT_PATCH = {
  workspaceLabel: '工作空间',
  versionLabel: '版本',
  title: '知识图谱',
  description: '在不改变后端协议的前提下，探索实体、证据、结构与风险预警。',
  refresh: '刷新',
  refreshGraph: '刷新图谱',
  module2FallbackSource: '模块二（降级源）',
  module4Source: '模块四（主源）',
  graphCanvas: '图谱画布',
  utilityDockTitle: '工具坞',
  utilityFiltersTitle: '过滤器',
  utilityFiltersSubtitle: '控制图谱范围与可见性。',
  collapseUtilityDock: '收起工具坞',
  expandUtilityDock: '展开工具坞',
  clearFilters: '清除过滤器',
  searchLabel: '搜索',
  searchPlaceholder: '搜索节点、边、证据或文件',
  scopeLabel: '范围',
  followActiveFile: '跟随当前文件',
  manualSelect: '手动选择',
  selectGraphFile: '选择图谱文件',
  followingActiveFile: '正在跟随当前活动文件',
  noGraphFileSelected: '未选择图谱文件',
  selectedFilePendingGraphRecord: '所选文件暂时没有图谱记录',
  currentAnalysisTarget: '当前分析目标',
  overviewGraph: '概览图谱',
  evidenceGraph: '证据图谱',
  forceLayout: '力导布局',
  hierarchicalLayout: '分层布局',
  fitView: '适应画布',
  zoomIn: '放大',
  zoomOut: '缩小',
  nodeTypesTitle: '节点类型',
  nodeTypesSubtitle: '过滤可见的节点类别。',
  rulesTitle: '规则',
  rulesSubtitle: '检查与切换图谱规则。',
  allEnabledRules: '全部启用规则',
  selectedRule: '选中规则',
  selectRuleHint: '选择一条规则以查看详情。',
  enableRule: '启用规则',
  disableRule: '禁用规则',
  switchingRule: '切换规则中',
  ruleEnabled: '规则已启用',
  ruleDisabled: '规则已禁用',
  runtimeStatus: '运行时状态',
  runtimeHealthy: '健康',
  runtimeNotReady: '未就绪',
  graphRagLabel: 'GraphRAG',
  databaseLabel: '数据库',
  statusReady: '就绪',
  statusUnavailable: '不可用',
  statusConnected: '已连接',
  statusDisconnected: '已断开',
  jobStatus: '任务状态',
  jobIdle: '空闲',
  nodeCountMetric: '节点数',
  edgeCountMetric: '边数',
  alertCountMetric: '告警数',
  noRules: '暂无规则。',
  noAlerts: '暂无告警。',
  alertsTitle: '告警',
  alertsSubtitle: '追踪图谱与证据风险。',
  acknowledge: '确认',
  acknowledging: '确认中',
  resolve: '解决',
  resolving: '解决中',
  pinned: '已固定',
  pinNode: '固定节点',
  unpinNode: '取消固定',
  focusNode: '聚焦节点',
  expandNeighborhood: '展开邻居',
  expanding: '展开中',
  explainAction: '解释',
  explaining: '解释中',
  simulateAction: '模拟',
  simulating: '模拟中',
  closeDetails: '关闭详情',
  detailsPanel: '详情面板',
  attributesTitle: '属性',
  noNodeDetails: '暂无节点详情。',
  noEvidence: '暂无证据。',
  noEdgeEvidence: '暂无边证据。',
  artifactEvidence: '产物证据',
  documentEvidence: '文档证据',
  edgeRelations: '边关系',
  edgeEvidence: '边证据',
  nodeEvidence: '节点证据',
  emptyGraphTitle: '暂无图谱数据',
  emptyGraphBody: '当前选择暂无可用的图谱数据。',
  openArtifact: '打开产物',
  relatedNodes: '相关节点',
  relatedAlerts: '相关告警',
  riskScore: '风险评分',
  simulationTitle: '模拟',
  simulationDetails: '模拟详情',
  reasoningSteps: '推理步骤',
  explanationTitle: '解释',
  simulationAlerts: '模拟告警',
  simulationImpacts: '模拟影响',
  simulationNeedsAlert: '模拟至少需要一个告警上下文才能执行。',
  untitledAlert: '未命名告警',
  ruleFallback: '规则',
  graphResourcesLoadFailed: '图谱资源加载失败。',
  usingActiveGraphFile: '正在使用当前图谱文件。',
  activeGraphFileNotReady: '当前图谱文件尚未就绪。',
  coreDetails: '核心详情',
  analysisTitle: '分析',
  analysisTip: '在运行解释或模拟前，请先查看所选告警、支撑证据以及相关图谱上下文。',
  unresolvedAlerts: '未解决告警',
  queryPanelTitle: 'GraphRAG 检索',
  queryPanelSubtitle: '基于当前文件对应的 GraphRAG 工作区，按原生 local、global、drift、basic 逻辑进行检索。',
  queryPlaceholder: '输入问题后检索当前知识图谱',
  queryModeLabel: '检索模式',
  queryRun: '开始检索',
  queryRunning: '检索中',
  queryEmpty: '还没有检索结果。输入问题后即可调用当前 GraphRAG 工作区进行检索。',
  queryNeedsReadyGraph: '请先选择一个已构建完成的图谱文件，再进行检索。',
  queryNeedsText: '请输入要检索的问题。',
  queryFailed: 'GraphRAG 检索失败。',
  queryAnswerTitle: '检索回答',
  queryContextTitle: '上下文命中',
  queryLinkedNodesTitle: '关联节点',
  queryModeLocal: '本地 Local',
  queryModeGlobal: '全局 Global',
  queryModeDrift: '漂移 Drift',
  queryModeBasic: '基础 Basic',
} as const;

Object.assign(UI_TEXT, UI_TEXT_PATCH);

const UI_TEXT_RUNTIME = UI_TEXT as typeof UI_TEXT & Record<string, string>;


const graphFileStatusLabel = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase();
  const labelsZh: Record<string, string> = {
    ready: '\u5c31\u7eea',
    pending: '\u7b49\u5f85\u4e2d',
    queued: '\u6392\u961f\u4e2d',
    running: '\u8fd0\u884c\u4e2d',
    processing_documents: '\u5904\u7406\u6587\u6863\u4e2d',
    extracting: '\u62bd\u53d6\u4e2d',
    projecting: '\u6295\u5f71\u4e2d',
    failed: '\u5931\u8d25',
    skipped: '\u5df2\u8df3\u8fc7',
  };
  return labelsZh[normalized] || prettifyToken(String(value || ''));
};

const projectionStatusLabel = (value?: string | null) => {
  const normalized = String(value || '').toLowerCase();
  const labelsZh: Record<string, string> = {
    success: '\u6210\u529f',
    failed: '\u5931\u8d25',
    skipped: '\u5df2\u8df3\u8fc7',
    pending: '\u7b49\u5f85\u4e2d',
    queued: '\u6392\u961f\u4e2d',
    running: '\u8fd0\u884c\u4e2d',
    processing: '\u5904\u7406\u4e2d',
  };
  return labelsZh[normalized] || prettifyToken(String(value || ''));
};

const projectionSummary = (item?: Module4GraphFileItem | null) => {
  const projection = item?.projection;
  if (!projection?.status) return '\u6295\u5f71\u672a\u5f00\u59cb\u3002';
  if (projection.status === 'success') {
    return `\u5df2\u6295\u5f71 ${projection.projected_nodes ?? 0} \u4e2a\u8282\u70b9 / ${projection.projected_edges ?? 0} \u6761\u8fb9\u3002`;
  }
  if (projection.status === 'failed') {
    return projection.error_message
      ? `\u6295\u5f71\u5931\u8d25: ${projection.error_message}`
      : '\u6295\u5f71\u5931\u8d25\u3002';
  }
  if (projection.status === 'skipped') {
    return projection.skipped_reason
      ? `\u6295\u5f71\u5df2\u8df3\u8fc7: ${projection.skipped_reason}`
      : '\u6295\u5f71\u5df2\u8df3\u8fc7\u3002';
  }
  return `\u6295\u5f71\u72b6\u6001: ${projectionStatusLabel(projection.status)}`;
};

const isArtifactUnavailableError = (error: unknown) =>
  error instanceof Error && /GraphRAG artifacts unavailable/i.test(error.message || '');

const truthStatusOfGraphFile = (item?: Module4GraphFileItem | null) => {
  if (!item) return '\u672a\u77e5';
  if (item.status === 'failed') return '\u5931\u8d25';
  if (item.status === 'ready') return '\u5c31\u7eea';
  return graphFileStatusLabel(item.status);
};

const truthToneOfGraphFile = (item?: Module4GraphFileItem | null) => {
  if (!item) return 'border-slate-200 bg-slate-50 text-slate-600';
  if (item.status === 'failed') return 'border-rose-200 bg-rose-50 text-rose-700';
  if (item.status === 'ready') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  return 'border-sky-200 bg-sky-50 text-sky-700';
};

const stageLabelOfGraphFile = (item?: Module4GraphFileItem | null) => {
  if (!item) return '\u672a\u77e5';
  const stage = normalizeText(firstText((item as any).stage, (item as any).current_stage, (item as any).pipeline_stage));
  const normalizedStage = stage.toLowerCase();
  if (normalizedStage === 'failed') return '\u5931\u8d25';
  if (normalizedStage === 'success') return '\u5c31\u7eea';
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

const runtimeStatusLabel = (healthz?: Module4HealthzResponse | null) => {
  if (!healthz) return UI_TEXT.runtimeNotReady;
  return healthz.status === 'ok' || healthz.db_connected ? UI_TEXT.runtimeHealthy : UI_TEXT.runtimeNotReady;
};

const jobStatusLabel = (value?: Module4JobResponse['status'] | string | null) => {
  const normalized = String(value || '').toLowerCase();
  const labelsZh: Record<string, string> = {
    queued: '\u6392\u961f\u4e2d',
    running: '\u8fd0\u884c\u4e2d',
    success: '\u6210\u529f',
    failed: '\u5931\u8d25',
    cancelled: '\u5df2\u53d6\u6d88',
  };
  return labelsZh[normalized] || prettifyToken(String(value ?? ''));
};

const ruleScopeLabel = (rule: Module4RuleItem) => {
  const expr = asRecord(rule.expr);
  const scope = firstText(expr.scope, expr.target_scope, expr.applies_to, expr.node_type, expr.edge_type);
  return scope ? prettifyToken(scope) : '\u5168\u5c40';
};

const ruleDisplayName = (rule: Module4RuleItem) => {
  const name = normalizeText(rule.name);
  return name || `${UI_TEXT.ruleFallback} ${rule.rule_id.slice(0, 8)}`;
};

const sortRulesForDisplay = (items: Module4RuleItem[]) =>
  [...items].sort((left, right) => {
    if (left.enabled !== right.enabled) return left.enabled ? -1 : 1;
    const severityOrder = { red: 0, orange: 1, yellow: 2 } as const;
    const severityDelta =
      (severityOrder[left.severity] ?? Number.MAX_SAFE_INTEGER) -
      (severityOrder[right.severity] ?? Number.MAX_SAFE_INTEGER);
    if (severityDelta !== 0) return severityDelta;
    return ruleDisplayName(left).localeCompare(ruleDisplayName(right), 'zh-CN');
  });

const simulationMetricLabel = (value: unknown) => {
  const normalized = normalizeText(value);
  if (!normalized) return 'Metric';
  const labels: Record<string, string> = {
    affected_nodes: 'Affected Nodes',
    affected_edges: 'Affected Edges',
    affected_alerts: 'Affected Alerts',
    risk_score: 'Risk Score',
    confidence: 'Confidence',
  };
  return labels[normalized] || prettifyToken(String(value ?? ''));
};

const metricValueText = (value: unknown): string => {
  if (value == null) return 'N/A';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const formatDateTime = (value?: string | null) => {
  const text = String(value || '').trim();
  if (!text) return 'Unknown';
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
  const objectId = normalizeText(item.object_id) || normalizeText(item.ref_id) || 'Unknown';
  const page = firstText((item as any).page, locator.page);
  const title = firstText(
    looksLikeLowSignalArtifactTitle(caption, objectId) ? '' : caption,
    page ? `P${page}` : '',
    previewHeaders.join(' / '),
    keyPoints.join(' / '),
    textBlocks[0],
    objectId
  );
  return `${objectLabel} - ${shortText(title, 32)}`;
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
  const titleParts = evidenceTitle(item).split(' - ');
  const titleText = cleanArtifactText(titleParts.length > 1 ? titleParts.slice(1).join(' - ') : titleParts[0]);
  const pageOnlyMatch = text.match(/^p\s*(\d+)$/i);
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
        <span>数据表预览</span>
        <span>{preview.rowCount} 行 / {preview.colCount} 列</span>
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
    item.page_no ? `P${item.page_no}` : '',
    firstText(locator.section, locator.anchor, locator.block_id),
    item.ref_id ? `Ref: ${item.ref_id}` : '',
  ].filter(Boolean);
  return parts.join(' / ') || 'Locator unavailable';
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

const graphFileNameKey = (item?: Module4GraphFileItem | null) =>
  String(item?.file_name || '')
    .trim()
    .toLowerCase();

const graphFileNodeCount = (item?: Module4GraphFileItem | null) => Number(item?.node_count || 0);

const graphFileEdgeCount = (item?: Module4GraphFileItem | null) => Number(item?.edge_count || 0);

const graphFileRecencyKey = (item?: Module4GraphFileItem | null) =>
  String(item?.last_indexed_at || item?.updated_at || item?.created_at || '');

const compareGraphFilesForPreference = (
  left?: Module4GraphFileItem | null,
  right?: Module4GraphFileItem | null
) => {
  const priorityDiff = graphFilePriority(left) - graphFilePriority(right);
  if (priorityDiff !== 0) return priorityDiff;

  const usableDiff = Number(graphFileHasUsableVersion(right)) - Number(graphFileHasUsableVersion(left));
  if (usableDiff !== 0) return usableDiff;

  const nodeCountDiff = graphFileNodeCount(right) - graphFileNodeCount(left);
  if (nodeCountDiff !== 0) return nodeCountDiff;

  const edgeCountDiff = graphFileEdgeCount(right) - graphFileEdgeCount(left);
  if (edgeCountDiff !== 0) return edgeCountDiff;

  const recencyDiff = graphFileRecencyKey(right).localeCompare(graphFileRecencyKey(left));
  if (recencyDiff !== 0) return recencyDiff;

  return String(left?.file_hash || '').localeCompare(String(right?.file_hash || ''), 'zh-CN');
};

const graphFileStatusBadge = (item?: Module4GraphFileItem | null) => {
  if (!item) return '未知状态';
  if (item.status === 'ready' && Number(item.node_count || 0) > 0) {
    return `已就绪 · ${Number(item.node_count || 0)} 节点`;
  }
  if (item.status === 'ready') return '已就绪';
  if (item.status === 'failed') return '失败';
  if (item.status === 'indexing' || item.status === 'importing_graph') return '构建中';
  if (item.status === 'preparing_input' || item.status === 'queued') return '排队中';
  return String(item.status || '处理中');
};

const graphFileOptionLabel = (
  item: Module4GraphFileItem,
  duplicateNameCounts: Record<string, number>
) => {
  const baseName = String(item.file_name || item.file_hash || '未命名文件').trim();
  const duplicateCount = duplicateNameCounts[graphFileNameKey(item)] || 0;
  if (duplicateCount <= 1) return baseName;
  return `${baseName} · ${graphFileStatusBadge(item)}`;
};

const sortGraphFilesForDisplay = (items: Module4GraphFileItem[]) => {
  const sorted = [...items].sort(compareGraphFilesForPreference);

  const preferredByName = new Map<string, true>();
  return sorted.filter((item) => {
    const key = graphFileNameKey(item);
    if (!key) return true;

    if (preferredByName.has(key)) {
      return false;
    }

    preferredByName.set(key, true);
    return true;
  });
};

const resolvePreferredGraphFile = (items: Module4GraphFileItem[], desiredFileHash = '') => {
  const sorted = [...items].sort(compareGraphFilesForPreference);
  const normalizedHash = desiredFileHash.trim();

  if (normalizedHash) {
    const desiredItem = items.find((item) => item.file_hash === normalizedHash) || null;
    if (desiredItem) {
      const desiredNameKey = graphFileNameKey(desiredItem);
      if (!desiredNameKey) return desiredItem;
      return sorted.find((item) => graphFileNameKey(item) === desiredNameKey) || desiredItem;
    }
  }

  return (
    sorted.find((item) => item.status === 'ready') ||
    sorted.find((item) => graphFileHasUsableVersion(item)) ||
    sorted[0] ||
    null
  );
};

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
  layoutGraph: Module4GraphResponse;
  layoutMode: LayoutMode;
  rootNodeId: string;
  selectedNodeId: string;
  pinnedNodeIds: string[];
  hiddenEdgeCountsByNode: Map<string, number>;
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
    lines.push(next && lines.length === maxLines - 1 ? `${slice.slice(0, Math.max(0, maxChars - 1))}...` : slice);
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
    label.length > 16 || /^[\[\(\{]/.test(label) || /\d{3,}/.test(label);

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

const buildHierarchyPositions = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) =>
  buildSemanticSectorPositions(nodes, edges);

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
  const curvatureBase = role === 'semantic' ? 0.05 : role === 'anchor' ? 0.014 : role === 'evidence' ? 0.028 : 0.022;
  const nearStraight = Math.abs(deltaY) < Math.max(18, distance * 0.1);
  const curvature = nearStraight
    ? Math.min(8, Math.max(1.2, distance * 0.013))
    : Math.min(16, Math.max(3.2, distance * curvatureBase));
  const direction = Math.abs(deltaY) <= 8 ? (deltaX >= 0 ? 1 : -1) : deltaY >= 0 ? 1 : -1;
  const controlX = (startX + endX) / 2 + normalX * curvature * direction;
  const controlY = (startY + endY) / 2 + normalY * curvature * direction;

  const t = 0.5;
  const labelX = (1 - t) ** 2 * startX + 2 * (1 - t) * t * controlX + t ** 2 * endX;
  const labelY = (1 - t) ** 2 * startY + 2 * (1 - t) * t * controlY + t ** 2 * endY;
  const path =
    'M ' +
    startX.toFixed(2) +
    ' ' +
    startY.toFixed(2) +
    ' Q ' +
    controlX.toFixed(2) +
    ' ' +
    controlY.toFixed(2) +
    ' ' +
    endX.toFixed(2) +
    ' ' +
    endY.toFixed(2);

  return {
    path,
    labelX,
    labelY,
  };
};

const Neo4jStyleForceGraph = forwardRef<ForceGraphHandle, ForceGraphProps>(
  (
    {
      graph,
      layoutGraph,
      layoutMode,
      rootNodeId,
      selectedNodeId,
      pinnedNodeIds,
      hiddenEdgeCountsByNode,
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
    const nodeMapRef = useRef(new Map<string, ForceGraphNodeDatum>());
    const nodeElementMapRef = useRef(new Map<string, SVGGElement>());
    const positionCacheRef = useRef(new Map<string, NodePositionState>());
    const viewportRef = useRef<ForceGraphViewport>({ x: 0, y: 0, zoom: 1 });
    const animationFrameRef = useRef<number | null>(null);
    const viewportAnimationRef = useRef<number | null>(null);
    const previousVisibleEdgeIdsRef = useRef(new Set<string>());
    const revealResetTimerRef = useRef<number | null>(null);
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
      source: 'canvas' | 'root-node';
      nodeId?: string;
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

    const layoutGraphSignature = useMemo(() => {
      const nodeSignature = layoutGraph.nodes
        .map((node) => node.node_id)
        .sort()
        .join('|');
      const edgeSignature = layoutGraph.edges
        .map((edge) => edge.edge_id)
        .sort()
        .join('|');
      return nodeSignature + '::' + edgeSignature;
    }, [layoutGraph.edges, layoutGraph.nodes]);

    const renderGraphSignature = useMemo(() => {
      const nodeSignature = graph.nodes
        .map((node) => node.node_id)
        .sort()
        .join('|');
      const edgeSignature = graph.edges
        .map((edge) => edge.edge_id)
        .sort()
        .join('|');
      return nodeSignature + '::' + edgeSignature;
    }, [graph.edges, graph.nodes]);

    const [newlyRevealedEdgeIds, setNewlyRevealedEdgeIds] = useState<Set<string>>(new Set());

    useEffect(() => {
      setHoveredEdgeId('');
    }, [renderGraphSignature]);

    useEffect(() => {
      const currentIds = new Set(graph.edges.map((edge) => edge.edge_id));
      const previousIds = previousVisibleEdgeIdsRef.current;
      const revealed = [...currentIds].filter((edgeId) => !previousIds.has(edgeId));
      previousVisibleEdgeIdsRef.current = currentIds;

      if (revealResetTimerRef.current != null) {
        window.clearTimeout(revealResetTimerRef.current);
        revealResetTimerRef.current = null;
      }

      if (revealed.length === 0) {
        setNewlyRevealedEdgeIds(new Set());
        return;
      }

      const next = new Set(revealed);
      setNewlyRevealedEdgeIds(next);
      revealResetTimerRef.current = window.setTimeout(() => {
        setNewlyRevealedEdgeIds(new Set());
        revealResetTimerRef.current = null;
      }, 360);
    }, [graph.edges]);

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
        nodeElement.setAttribute('transform', 'translate(' + x + ' ' + y + ')');
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

        const topInset = containerSize.height < 720 ? 84 : 96;
        const bottomInset = containerSize.height < 720 ? 74 : 82;
        const leftInset = containerSize.width < 960 ? 74 : 146;
        const rightInset = 34;
        const safeWidth = Math.max(1, containerSize.width - leftInset - rightInset);
        const safeHeight = Math.max(1, containerSize.height - topInset - bottomInset);
        const safeCenterX = leftInset + safeWidth / 2;
        const safeCenterY = topInset + safeHeight / 2;

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
              x: safeCenterX - nodeX * targetZoom,
              y: safeCenterY - nodeY * targetZoom,
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
          Math.min(safeWidth / width, safeHeight / height) * 0.92,
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
            x: safeCenterX - centerX * targetZoom,
            y: safeCenterY - centerY * targetZoom,
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
      if (!layoutGraph.nodes.length) {
        nodesRef.current = [];
        nodeMapRef.current = new Map();
        simulationRef.current?.stop();
        simulationRef.current = null;
        return () => undefined;
      }

      const cachedPositions = positionCacheRef.current;
      const seedPositions = buildHierarchyPositions(layoutGraph.nodes, layoutGraph.edges);
      const pinnedSet = new Set(pinnedNodeIds);
      const importanceContext = buildNodeImportanceContext(layoutGraph.nodes, layoutGraph.edges);

      const nextNodes = layoutGraph.nodes.map((node) => {
        const visual = visualSpecOf(node);
        const isDocumentNode = typeKeyOf(node) === 'document';
        const degree = importanceContext.degreeMap.get(node.node_id) || 0;
        const emphasisTier = emphasisTierOfNode(node, degree, importanceContext);
        const importance = nodeImportanceOf(node, degree, emphasisTier, importanceContext);
        const seeded = seedPositions.get(node.node_id);
        const seedLane = seeded?.zoneKey ?? semanticZoneOfNode(node, importanceContext.rootNodeId);
        const densityRatio = clamp(degree / Math.max(1, importanceContext.maxDegree), 0, 1);
        const tierRadiusBoost =
          isDocumentNode
            ? emphasisTier === 'primary'
              ? 2.2
              : emphasisTier === 'secondary'
                ? 1.2
                : emphasisTier === 'tertiary'
                  ? 0.4
                  : 0
            : emphasisTier === 'primary'
              ? 4.2
              : emphasisTier === 'secondary'
                ? 2.4
                : emphasisTier === 'tertiary'
                  ? 1
                  : 0;
        const radius = clamp(
          visual.minRadius + (visual.maxRadius - visual.minRadius) * (densityRatio * 0.72 + emphasisTierWeight(emphasisTier) * 0.38),
          visual.minRadius,
          visual.maxRadius + tierRadiusBoost
        );
        const label = captionOfNode(node, emphasisTier === 'primary' ? 28 : visual.size > 64 ? 24 : 18);
        const cached = cachedPositions.get(node.node_id);
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
          laneX: seeded?.anchorX ?? 0,
          laneY: seeded?.anchorY ?? 0,
          x,
          y,
          fx: isPinned ? cached?.fx ?? x : null,
          fy: isPinned ? cached?.fy ?? y : null,
        } satisfies ForceGraphNodeDatum;
      });

      const resolvedSeedPositions = resolveGraphNodeOverlaps(
        nextNodes.map((node) => {
          const cached = cachedPositions.get(node.id);
          const keepCachedPosition =
            Boolean(cached) && (pinnedSet.has(node.id) || node.id === rootNodeId);
          return {
            id: node.id,
            x: keepCachedPosition ? cached?.x ?? node.x : node.seedX,
            y: keepCachedPosition ? cached?.y ?? node.y : node.seedY,
            radius: node.radius,
            anchorX: node.laneX,
            anchorY: node.laneY,
            zoneKey: node.seedLane,
            fixed: keepCachedPosition,
            isRoot: node.id === rootNodeId,
          };
        }),
        {
          iterations: layoutGraph.nodes.length > 90 ? 24 : 34,
          intraZoneGap: layoutGraph.nodes.length > 120 ? 14 : 18,
          interZoneGap: layoutGraph.nodes.length > 120 ? 10 : 14,
        }
      );

      nextNodes.forEach((node) => {
        const resolved = resolvedSeedPositions.get(node.id);
        if (!resolved) return;
        node.seedX = resolved.x;
        node.seedY = resolved.y;

        const cached = cachedPositions.get(node.id);
        if (!cached || (!pinnedSet.has(node.id) && node.id !== rootNodeId)) {
          node.x = resolved.x;
          node.y = resolved.y;
        }
      });

      const nextLinks = layoutGraph.edges.map((edge) => ({
        id: edge.edge_id,
        edge,
        label: relationLabelOf(edge),
        color: relationToneOf(edge),
        width: edgeRenderWidth(edge),
        source: edge.source_node_id,
        target: edge.target_node_id,
      })) satisfies ForceGraphLinkDatum[];

      nodesRef.current = nextNodes;
      nodeMapRef.current = new Map(nextNodes.map((node) => [node.id, node]));

      simulationRef.current?.stop();

      if (layoutMode === HierarchicalLayoutType) {
        nextNodes.forEach((node) => {
          const cached = cachedPositions.get(node.id);
          const position = resolvedSeedPositions.get(node.id) || seedPositions.get(node.id) || { x: 0, y: 0 };
          const nextX = cached?.x ?? position.x;
          const nextY = cached?.y ?? position.y;
          node.x = nextX;
          node.y = nextY;
          node.fx = nextX;
          node.fy = nextY;
          cachedPositions.set(node.id, {
            x: nextX,
            y: nextY,
            fx: nextX,
            fy: nextY,
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
              if (typeKey.includes('overview_context')) return 214;
              if (typeKey.includes('community')) return 184;
              if (typeKey.includes('part')) return 124;
              if (typeKey.includes('entity')) return 110;
              if (typeKey.includes('related')) return 116;
              if (typeKey.includes('evidence')) return 142;
              return 116;
            })
            .strength((link) => {
              const typeKey = normalizeTypeKey(link.edge.relation_type);
              if (typeKey.includes('overview_context')) return 0.16;
              if (typeKey.includes('community')) return 0.2;
              if (typeKey.includes('part')) return 0.28;
              if (typeKey.includes('entity')) return 0.22;
              if (typeKey.includes('evidence')) return 0.18;
              return 0.16;
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
              if (typeKey === 'community') return (-920 - radiusInfluence) * emphasisMultiplier;
              if (typeKey === 'document') return (-700 - radiusInfluence) * emphasisMultiplier;
              if (typeKey === 'chunk') return (layoutGraph.nodes.length > 180 ? -240 : -290) * emphasisMultiplier;
              return ((layoutGraph.nodes.length > 180 ? -350 : -420) - radiusInfluence * 0.28) * emphasisMultiplier;
            })
            .distanceMax(760)
        )
        .force('center', forceCenter<ForceGraphNodeDatum>(0, 0))
        .force(
          'lane-x',
          forceX<ForceGraphNodeDatum>((node) => node.laneX).strength((node) => zoneStrengthOf(node.seedLane).x)
        )
        .force(
          'lane-y',
          forceY<ForceGraphNodeDatum>((node) => node.laneY).strength((node) => zoneStrengthOf(node.seedLane).y)
        )
        .force(
          'seed-x',
          forceX<ForceGraphNodeDatum>((node) => node.seedX).strength(layoutGraph.nodes.length > 180 ? 0.024 : 0.036)
        )
        .force(
          'seed-y',
          forceY<ForceGraphNodeDatum>((node) => node.seedY).strength(layoutGraph.nodes.length > 180 ? 0.022 : 0.032)
        )
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
        .alphaDecay(0.062)
        .velocityDecay(0.4)
        .on('tick', () => {
          nextNodes.forEach((node) => {
            cachedPositions.set(node.id, {
              x: Number(node.x || 0),
              y: Number(node.y || 0),
              fx: node.fx ?? null,
              fy: node.fy ?? null,
            });
          });
          if (simulation.alpha() <= 0.06) {
            simulation.stop();
          }
          scheduleRender();
        });

      simulationRef.current = simulation;
      scheduleRender();

      return () => {
        simulation.stop();
      };
    }, [layoutGraph.nodes, layoutGraph.edges, layoutGraphSignature, layoutMode, pinnedNodeIds, rootNodeId, scheduleRender]);

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
          if (activePan.moved) {
            suppressClickRef.current = true;
          }
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
        if (revealResetTimerRef.current != null) window.clearTimeout(revealResetTimerRef.current);
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
        source: 'canvas',
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
    const renderLinks = graph.edges.map((edge) => ({
      id: edge.edge_id,
      edge,
      label: relationLabelOf(edge),
      color: relationToneOf(edge),
      width: edgeRenderWidth(edge),
      source: nodeMapRef.current.get(edge.source_node_id) || edge.source_node_id,
      target: nodeMapRef.current.get(edge.target_node_id) || edge.target_node_id,
    })) satisfies ForceGraphLinkDatum[];
    const legendNodeItems = buildLegendNodeItems(layoutGraph.nodes);
    const legendEdgeItems = buildLegendEdgeItems(graph.edges);

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
          <g transform={'translate(' + viewport.x + ' ' + viewport.y + ') scale(' + viewport.zoom + ')'}>
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
              const labelWidth = Math.max(64, labelText.length * 7.2 + 18);
              const edgeRole = edgeRoleOf(link.edge);
              const isBaseEdge = Boolean(link.edge.isBaseEdge);
              const isNewlyRevealed = !isBaseEdge && newlyRevealedEdgeIds.has(link.id);
              const palette = edgeVisualPaletteOf(link.edge, {
                source: source.node,
                target: target.node,
                rootNodeId,
              });
              const strokeColor = dimmed ? mixHexColor(palette.stroke, '#dbe4f0', 0.64) : palette.stroke;
              const glowColor = dimmed ? 'rgba(203,213,225,0.08)' : palette.glow;
              const tracerColor = dimmed ? 'rgba(255,255,255,0.14)' : palette.tracer;
              const targetOpacity =
                dimmed ? 0.12 : active ? 0.9 : isBaseEdge ? 0.58 : edgeRole === 'semantic' ? 0.28 : 0.18;
              const targetWidth = active
                ? Math.min(isBaseEdge ? 3.9 : 3.2, link.width + 0.52)
                : Math.max(isBaseEdge ? 1.3 : 0.92, link.width - (isBaseEdge ? 0.18 : 0.48));
              const glowWidth = targetWidth + (isBaseEdge ? 2.4 : active ? 1.6 : 1.1);
              const showTracer = (isBaseEdge || active || isNewlyRevealed) && !dimmed;

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
                    stroke={glowColor}
                    strokeOpacity={isBaseEdge ? targetOpacity * 0.28 : targetOpacity * 0.16}
                    strokeWidth={glowWidth}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    pointerEvents="none"
                  />
                  <path
                    d={geometry.path}
                    pathLength={1}
                    fill="none"
                    stroke={strokeColor}
                    strokeOpacity={targetOpacity}
                    strokeWidth={targetWidth}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeDasharray={isNewlyRevealed ? '1' : palette.dash ?? (edgeRole === 'anchor' ? '7 7' : undefined)}
                    strokeDashoffset={isNewlyRevealed ? 1 : undefined}
                    onMouseEnter={() => setHoveredEdgeId(link.id)}
                    onMouseLeave={() => setHoveredEdgeId((current) => (current === link.id ? '' : current))}
                  >
                    {isNewlyRevealed && (
                      <>
                        <animate attributeName="stroke-dashoffset" from="1" to="0" dur="0.3s" fill="freeze" />
                        <animate attributeName="stroke-opacity" from="0" to={String(targetOpacity)} dur="0.22s" fill="freeze" />
                      </>
                    )}
                  </path>
                  {showTracer && (
                    <path
                      d={geometry.path}
                      pathLength={1}
                      fill="none"
                      stroke={tracerColor}
                      strokeOpacity={isBaseEdge ? 0.9 : active ? 0.62 : 0.32}
                      strokeWidth={Math.max(0.95, targetWidth * 0.52 + palette.tracerWidthBoost)}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeDasharray={palette.tracerDash}
                      pointerEvents="none"
                    >
                      <animate
                        attributeName="stroke-dashoffset"
                        from="1"
                        to="0"
                        dur={palette.tracerDuration}
                        repeatCount="indefinite"
                      />
                    </path>
                  )}
                  {showLabel && (
                    <g transform={'translate(' + geometry.labelX + ' ' + geometry.labelY + ')'}>
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
              const hiddenRelationCount = hiddenEdgeCountsByNode.get(node.id) || 0;
              const hasHiddenRelations = hiddenRelationCount > 0;
              const isDocumentNode = typeKeyOf(node.node) === 'document';
              const nodeFill = isDimmed ? mixHexColor(node.color, '#e2e8f0', 0.56) : node.color;
              const haloRadius =
                node.radius +
                (isSelected
                  ? isDocumentNode ? 4 : 5
                  : node.emphasisTier === 'primary'
                    ? isDocumentNode ? 3 : 4.5
                    : node.emphasisTier === 'secondary'
                      ? 2.5
                    : node.emphasisTier === 'tertiary'
                        ? 1.5
                        : 0.5);
              const haloFill = isSelected
                ? 'rgba(31,90,140,0.08)'
                : hasHiddenRelations
                  ? hexToRgba(node.color, isDimmed ? 0.018 : 0.052)
                : node.emphasisTier === 'primary'
                  ? hexToRgba(node.color, isDimmed ? 0.012 : 0.036)
                  : node.emphasisTier === 'secondary'
                    ? hexToRgba(node.color, isDimmed ? 0.01 : 0.024)
                    : node.emphasisTier === 'tertiary'
                      ? hexToRgba(node.color, isDimmed ? 0.008 : 0.016)
                      : 'rgba(255,255,255,0)';
              const outerRingStroke = isSelected
                ? '#1F5A8C'
                : node.emphasisTier === 'primary'
                  ? mixHexColor(node.color, '#ffffff', 0.74)
                  : node.emphasisTier === 'secondary'
                    ? mixHexColor(node.color, '#ffffff', 0.66)
                    : 'rgba(255,255,255,0.9)';
              const outerRingOpacity =
                isSelected ? 0.3 : hasHiddenRelations ? 0.16 : node.emphasisTier === 'primary' ? 0.14 : 0;
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
              const isPanningRoot =
                panStateRef.current?.source === 'root-node' && panStateRef.current?.nodeId === node.id;
              const shouldShowInnerRing =
                isSelected || isDocumentNode || node.emphasisTier === 'primary';
              const nodeTypeKey = typeKeyOf(node.node);
              const nodeShape =
                nodeTypeKey === 'business_alert' || nodeTypeKey === 'risk'
                  ? 'diamond'
                  : nodeTypeKey === 'table' || nodeTypeKey === 'figure' || nodeTypeKey === 'image'
                    ? 'panel'
                    : 'circle';
              const nodeStroke =
                isSelected
                  ? '#1F5A8C'
                  : isPinned
                    ? '#0f172a'
                    : hasHiddenRelations
                      ? mixHexColor(node.color, '#0f172a', 0.28)
                      : node.emphasisTier === 'primary'
                        ? mixHexColor(node.color, '#0f172a', 0.18)
                        : node.emphasisTier === 'secondary'
                          ? mixHexColor(node.color, '#0f172a', 0.12)
                          : 'rgba(255,255,255,0.92)';
              const nodeStrokeWidth =
                isSelected
                  ? 2.2
                  : isPinned
                    ? 1.8
                    : hasHiddenRelations
                      ? 1.7
                      : node.emphasisTier === 'primary'
                        ? 1.6
                        : node.emphasisTier === 'secondary'
                          ? 1.4
                          : 1.1;

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
                  transform={'translate(' + (node.x || 0) + ' ' + (node.y || 0) + ')'}
                  onPointerDown={(event) => {
                    if (event.button !== 0) return;
                    event.preventDefault();
                    event.stopPropagation();
                    try {
                      event.currentTarget.setPointerCapture?.(event.pointerId);
                    } catch {
                      // Synthetic pointer probes may not have an active native pointer.
                    }
                    if (node.id === rootNodeId) {
                      const current = viewportRef.current;
                      panStateRef.current = {
                        source: 'root-node',
                        nodeId: node.id,
                        pointerId: event.pointerId,
                        startClientX: event.clientX,
                        startClientY: event.clientY,
                        originX: current.x,
                        originY: current.y,
                        moved: false,
                      };
                      setHoveredEdgeId('');
                      suppressClickRef.current = false;
                      return;
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
                  style={{ cursor: isDragging || isPanningRoot ? 'grabbing' : 'grab' }}
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
                          key={String(node.id) + '-detached-' + line + '-' + index}
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
                  {nodeShape === 'circle' && (
                    <circle
                      r={node.radius}
                      fill={nodeFill}
                      stroke={nodeStroke}
                      strokeWidth={nodeStrokeWidth}
                    />
                  )}
                  {nodeShape === 'panel' && (
                    <rect
                      x={-node.radius * 1.08}
                      y={-node.radius * 0.78}
                      width={node.radius * 2.16}
                      height={node.radius * 1.56}
                      rx={Math.max(8, node.radius * 0.42)}
                      fill={nodeFill}
                      stroke={nodeStroke}
                      strokeWidth={nodeStrokeWidth}
                    />
                  )}
                  {nodeShape === 'diamond' && (
                    <rect
                      x={-node.radius * 0.82}
                      y={-node.radius * 0.82}
                      width={node.radius * 1.64}
                      height={node.radius * 1.64}
                      rx={Math.max(4, node.radius * 0.18)}
                      transform="rotate(45)"
                      fill={nodeFill}
                      stroke={nodeStroke}
                      strokeWidth={nodeStrokeWidth}
                    />
                  )}
                  {shouldShowInnerRing && nodeShape === 'circle' && (
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
                  {shouldShowInnerRing && nodeShape === 'panel' && (
                    <rect
                      x={-node.radius * 0.78}
                      y={-node.radius * 0.52}
                      width={node.radius * 1.56}
                      height={node.radius * 1.04}
                      rx={Math.max(6, node.radius * 0.28)}
                      fill="none"
                      stroke={
                        isSelected
                          ? 'rgba(255,255,255,0.96)'
                          : node.emphasisTier === 'primary'
                            ? 'rgba(255,255,255,0.58)'
                            : 'rgba(255,255,255,0.42)'
                      }
                      strokeWidth={node.emphasisTier === 'primary' ? 1.1 : 0.9}
                    />
                  )}
                {hasHiddenRelations && (
                    <g
                      transform={'translate(' + (node.radius * 0.72).toFixed(2) + ' ' + (-node.radius * 0.72).toFixed(2) + ')'}
                      pointerEvents="none"
                    >
                      <circle
                        r={hiddenRelationCount > 9 ? 10 : 9}
                        fill={isDimmed ? 'rgba(51,65,85,0.44)' : 'rgba(15,23,42,0.92)'}
                        stroke={isDimmed ? 'rgba(226,232,240,0.42)' : 'rgba(255,255,255,0.88)'}
                        strokeWidth={1.15}
                      />
                      <text
                        textAnchor="middle"
                        dominantBaseline="central"
                        fontSize={hiddenRelationCount > 9 ? 8.5 : 9}
                        fontWeight={800}
                        fill="rgba(248,250,252,0.98)"
                      >
                        {hiddenRelationCount > 9 ? '9+' : String(hiddenRelationCount)}
                      </text>
                    </g>
                  )}
                  {shouldShowLabel &&
                    !detachedLabel &&
                    labelLines.map((line, index) => (
                      <text
                        key={String(node.id) + '-' + line + '-' + index}
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
        <KnowledgeGraphLegend
          nodeItems={legendNodeItems}
          edgeItems={legendEdgeItems}
          className="max-md:left-3 max-md:right-3 max-md:w-auto"
        />
      </div>
    );
  }
);

export const KnowledgeNexus: React.FC = () => {
  const nvlRef = useRef<ForceGraphHandle | null>(null);
  const rootSectionRef = useRef<HTMLElement | null>(null);
  const graphHostRef = useRef<HTMLDivElement | null>(null);
  const toolbarMenuRef = useRef<HTMLDivElement | null>(null);
  const sourceRef = useRef('graphrag:artifact:empty');
  const fitPendingRef = useRef(true);
  const graphDataRef = useRef<Module4GraphResponse>(EMPTY_GRAPH);

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
  const [queryMode, setQueryMode] = useState<Module4GraphRagQueryMode>('local');
  const [queryText, setQueryText] = useState('');
  const [querying, setQuerying] = useState(false);
  const [queryResult, setQueryResult] = useState<Module4GraphRagQueryResponse | null>(null);
  const [queryError, setQueryError] = useState('');
  const [filters, setFilters] = useState<FilterState>({ query: '', nodeTypes: [] });
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(HierarchicalLayoutType);
  const [graphViewMode, setGraphViewMode] = useState<GraphViewMode>('overview');
  const [hasUserSelectedGraphView, setHasUserSelectedGraphView] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [detail, setDetail] = useState<Module4NodeDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [isGraphSwitching, setIsGraphSwitching] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [ackingAlertId, setAckingAlertId] = useState('');
  const [resolvingAlertId, setResolvingAlertId] = useState('');
  const [, setMessage] = useState('');
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
  const duplicateGraphFileNameCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    graphFiles.forEach((item) => {
      const key = graphFileNameKey(item);
      if (!key) return;
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [graphFiles]);
  const currentProjection = currentGraphFile?.projection || null;
  const canUseFileGraph = Boolean(currentFileHash && graphFileHasUsableVersion(currentGraphFile));
  const overviewGraph = useMemo(() => buildOverviewGraph(graphData), [graphData]);
  const preferEvidenceView = useMemo(
    () => shouldPreferEvidenceGraph(graphData, overviewGraph),
    [graphData, overviewGraph]
  );
  useEffect(() => {
    graphDataRef.current = graphData;
  }, [graphData]);
  const effectiveGraphViewMode: GraphViewMode =
    !hasUserSelectedGraphView && graphViewMode === 'overview' && preferEvidenceView
      ? 'evidence'
      : graphViewMode;
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

  const fullGraphSignature = useMemo(() => {
    const nodeSignature = graphData.nodes
      .map((node) => node.node_id)
      .sort()
      .join('|');
    const edgeSignature = graphData.edges
      .map((edge) => edge.edge_id)
      .sort()
      .join('|');
    return nodeSignature + '::' + edgeSignature;
  }, [graphData.edges, graphData.nodes]);

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

  const filteredGraphDegreeMap = useMemo(
    () => buildEdgeDegreeMap(filteredGraph.nodes, filteredGraph.edges),
    [filteredGraph.edges, filteredGraph.nodes]
  );
  const graphRootNodeId = useMemo(
    () => pickLayoutRootId(filteredGraph.nodes, filteredGraphDegreeMap),
    [filteredGraph.nodes, filteredGraphDegreeMap]
  );
  const revealModel = useMemo(
    () =>
      buildGraphRevealModel({
        graph: filteredGraph,
        rootNodeId: graphRootNodeId,
        selectedNodeId,
        viewMode: effectiveGraphViewMode,
      }),
    [effectiveGraphViewMode, filteredGraph, graphRootNodeId, selectedNodeId]
  );
  const layoutGraph = revealModel.layoutGraph;
  const visibleGraph = revealModel.visibleGraph;
  const hiddenEdgeCountsByNode = revealModel.hiddenEdgeCountsByNode;

  const graphSignature = useMemo(() => {
    const nodeSignature = layoutGraph.nodes
      .map((node) => node.node_id)
      .sort()
      .join('|');
    const edgeSignature = layoutGraph.edges
      .map((edge) => edge.edge_id)
      .sort()
      .join('|');
    return nodeSignature + '::' + edgeSignature;
  }, [layoutGraph.edges, layoutGraph.nodes]);

  const selectedNode = useMemo(
    () => graphNodeMap.get(selectedNodeId) || detail?.node || null,
    [detail?.node, graphNodeMap, selectedNodeId]
  );

  const currentSelectionGraph = useMemo(
    () => (selectedNodeId ? subgraphForNode(visibleGraph, selectedNodeId) : EMPTY_GRAPH),
    [selectedNodeId, visibleGraph]
  );

  const detailGraph = detail?.graph?.nodes.length ? detail.graph : currentSelectionGraph;
  const detailNode = detail?.node || selectedNode;
  const selectionNeighborhood = useMemo(
    () => (selectedNodeId ? selectionNeighborhoodOf(visibleGraph, selectedNodeId) : null),
    [selectedNodeId, visibleGraph]
  );

  const detailEdges = useMemo(() => {
    if (!detailNode) return [];
    return detailGraph.edges.filter(
      (edge) => edge.source_node_id === detailNode.node_id || edge.target_node_id === detailNode.node_id
    );
  }, [detailGraph.edges, detailNode]);

  const detailVisibleEdges = useMemo(() => {
    if (!detailNode) return [];
    return visibleGraph.edges.filter(
      (edge) => edge.source_node_id === detailNode.node_id || edge.target_node_id === detailNode.node_id
    );
  }, [detailNode, visibleGraph.edges]);

  const detailNodeMap = useMemo(() => {
    const entries = new Map<string, Module4GraphNode>();
    graphData.nodes.forEach((node) => entries.set(node.node_id, node));
    detailGraph.nodes.forEach((node) => entries.set(node.node_id, node));
    return entries;
  }, [detailGraph.nodes, graphData.nodes]);

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
  const detailHiddenEdgeCount = detailNode ? hiddenEdgeCountsByNode.get(detailNode.node_id) || 0 : 0;
  const detailConnectionNarrative = useMemo(
    () =>
      detailNode
        ? buildNodeConnectionNarrative({
            node: detailNode,
            rootNodeId: graphRootNodeId,
            visibleEdges: detailVisibleEdges,
            hiddenEdgeCount: detailHiddenEdgeCount,
            nodeMap: detailNodeMap,
            viewMode: effectiveGraphViewMode,
          })
        : null,
    [
      detailHiddenEdgeCount,
      detailNode,
      detailNodeMap,
      detailVisibleEdges,
      effectiveGraphViewMode,
      graphRootNodeId,
    ]
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
  const utilityNodeCountLabel = String(filteredGraph.nodes.length) + ' ' + UI_TEXT.nodeCountMetric;
  const utilityAlertCountLabel = String(openAlertCount) + ' ' + UI_TEXT.alertCountMetric;
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
  const nodeEvidenceTitle = isArtifactDetailNode ? UI_TEXT.artifactEvidence : UI_TEXT.edgeEvidence;
  const edgeEvidenceTitle = isDocumentDetailNode ? UI_TEXT.documentEvidence : UI_TEXT.edgeEvidence;

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
      const neighborhood = selectionNeighborhoodOf(visibleGraph, nodeId);
      fitGraph(neighborhood ? [...neighborhood.nodeIds] : [nodeId]);
    },
    [fitGraph, visibleGraph]
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

        let nextGraph = graphDataRef.current;
        let nextSource = sourceRef.current || 'graphrag:artifact:file-empty';
        let nextGraphFiles: Module4GraphFileItem[] = [];
        let effectiveFileHash = desiredFileHash;
        let desiredGraphFile: Module4GraphFileItem | null = null;

        if (graphFilesResult.status === 'fulfilled') {
          const rawGraphFiles = graphFilesResult.value.items;
          nextGraphFiles = sortGraphFilesForDisplay(rawGraphFiles);
          setGraphFiles(nextGraphFiles);
          desiredGraphFile = desiredFileHash
            ? rawGraphFiles.find((item) => item.file_hash === desiredFileHash) || null
            : null;
          const preferredGraph = resolvePreferredGraphFile(rawGraphFiles, desiredFileHash);
          effectiveFileHash = String(
            desiredGraphFile
              ? preferredGraph?.file_hash || desiredFileHash
              : effectiveFileHash || preferredGraph?.file_hash || ''
          ).trim();
          if (
            sourceMode === 'manual-select' &&
            effectiveFileHash &&
            manualFileHash.trim() !== effectiveFileHash
          ) {
            setManualFileHash(effectiveFileHash);
          }
        } else {
          setGraphFiles([]);
          setApiError(
            graphFilesResult.reason instanceof Error
              ? graphFilesResult.reason.message
              : UI_TEXT.graphResourcesLoadFailed
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
          setActiveDocFileHash(
            desiredGraphFile ? effectiveFileHash || desiredFileHash : desiredFileHash || effectiveFileHash
          );
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
            setMessage(UI_TEXT.usingActiveGraphFile);
          } catch (fileGraphError) {
            console.warn('[KnowledgeNexusNeo4j] Failed to load active graph file, falling back.', fileGraphError);
            nextSource = fileGraphPendingSourceKey(effectiveFileHash);
            setMessage(UI_TEXT.activeGraphFileNotReady);
            if (!isArtifactUnavailableError(fileGraphError)) {
              setApiError(fileGraphError instanceof Error ? fileGraphError.message : UI_TEXT.graphResourcesLoadFailed);
            }
          }
        } else if (!activeGraphFile) {
          nextGraph = EMPTY_GRAPH;
          nextSource = 'graphrag:artifact:file-empty';
        }

        sourceRef.current = nextSource;
        fitPendingRef.current = true;
        startTransition(() => setGraphData(nextGraph));
      } catch (error) {
        setGraphFiles([]);
        setAlerts([]);
        setRules([]);
        setApiError(error instanceof Error ? error.message : UI_TEXT.graphResourcesLoadFailed);
      } finally {
        if (!options?.silent) setLoading(false);
      }
    },
    [manualFileHash, sourceMode]
  );

  const refreshGraphFiles = useCallback(async () => {
    const next = await fetchModule4GraphFiles({ limit: 200 });
    setGraphFiles(sortGraphFilesForDisplay(next.items));
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
            ? '已展开 ' + displayNameOfNode(nodeForMessage) + ' 的邻居节点。'
            : '已展开节点的邻居。'
        );
        window.setTimeout(() => focusNode(nodeId), 160);
      } catch (error) {
        setApiError(error instanceof Error ? error.message : '展开节点邻居失败。');
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

  const focusQueryNode = useCallback(
    async (nodeId: string) => {
      const normalizedNodeId = String(nodeId || '').trim();
      if (!normalizedNodeId || !canUseFileGraph || !currentFileHash) return;

      if (!graphNodeMap.has(normalizedNodeId)) {
        try {
          const neighborhood = await fetchModule4FileNeighborhood(currentFileHash, normalizedNodeId, {
            depth: 1,
            limit: 220,
          });
          sourceRef.current = graphFileSourceKey(currentGraphFile, currentFileHash);
          fitPendingRef.current = true;
          startTransition(() => {
            setGraphData((current) => mergeGraph(current, neighborhood));
          });
        } catch (error) {
          setApiError(error instanceof Error ? error.message : UI_TEXT_RUNTIME.queryFailed);
          return;
        }
      }

      openInspector(normalizedNodeId);
      window.setTimeout(() => focusNode(normalizedNodeId), 120);
    },
    [canUseFileGraph, currentFileHash, currentGraphFile, focusNode, graphNodeMap, openInspector]
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
          setApiError(error instanceof Error ? error.message : '展开节点邻居失败。');
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
        setApiError(error instanceof Error ? error.message : '更新选中规则失败。');
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
      setApiError(error instanceof Error ? error.message : '生成解释失败。');
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
          ? 'workbench-' + primaryDetailAlert.rule_id + '-' + selectedRule.rule_id
          : 'workbench-' + primaryDetailAlert.rule_id,
        scope: {
          alert_id: primaryDetailAlert.alert_id,
          ...(selectedRule ? { rule_id: selectedRule.rule_id } : {}),
        },
      });
      setSimulateResult(next);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '模拟当前场景失败。');
    } finally {
      setSimulating(false);
    }
  }, [primaryDetailAlert, selectedRule]);

  const handleRunGraphRagQuery = useCallback(async () => {
    if (!canUseFileGraph || !currentFileHash) {
      setQueryError(UI_TEXT_RUNTIME.queryNeedsReadyGraph);
      return;
    }

    const normalizedQuery = queryText.trim();
    if (!normalizedQuery) {
      setQueryError(UI_TEXT_RUNTIME.queryNeedsText);
      return;
    }

    setQuerying(true);
    setQueryError('');
    try {
      const result = await searchModule4GraphRag({
        fileHash: currentFileHash,
        query: normalizedQuery,
        mode: queryMode,
        responseType: 'multiple paragraphs',
        communityLevel: 2,
        dynamicCommunitySelection: queryMode === 'global',
      });
      setQueryResult(result);
      if (result.linked_node_ids.length > 0) {
        void focusQueryNode(result.linked_node_ids[0]);
      }
    } catch (error) {
      const nextMessage = error instanceof Error ? error.message : UI_TEXT_RUNTIME.queryFailed;
      setQueryError(nextMessage);
      setApiError(nextMessage);
    } finally {
      setQuerying(false);
    }
  }, [canUseFileGraph, currentFileHash, focusQueryNode, queryMode, queryText]);

  const handleAckAlert = useCallback(async (alertId: string) => {
    setAckingAlertId(alertId);
    try {
      await ackModule4Alert(alertId);
      await refreshAlerts();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '确认警报失败。');
    } finally {
      setAckingAlertId('');
    }
  }, [refreshAlerts]);

  const handleResolveAlert = useCallback(
    async (alertId: string) => {
      setResolvingAlertId(alertId);
      try {
        await resolveModule4Alert(alertId, 'user', '由用户从知识图谱面板解决。');
        await refreshAlerts();
      } catch (error) {
        setApiError(error instanceof Error ? error.message : '解决警报失败。');
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
    setQueryResult(null);
    setQueryError('');
  }, [currentFileHash]);

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
      setLoading(false);
      setIsGraphSwitching(false);
      return () => undefined;
    }
    if (sourceRef.current === graphFileSourceKey(currentGraphFile, currentFileHash)) {
      setLoading(false);
      setIsGraphSwitching(false);
      return () => undefined;
    }

    let cancelled = false;
    setLoading(true);
    setIsGraphSwitching(true);
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
        if (isArtifactUnavailableError(error)) {
          setMessage(UI_TEXT.activeGraphFileNotReady);
          return;
        }
        setApiError(error instanceof Error ? error.message : UI_TEXT.graphResourcesLoadFailed);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
        setIsGraphSwitching(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentFileHash, currentGraphFile]);

  useEffect(() => {
    if (hasUserSelectedGraphView || graphViewMode !== 'overview' || !preferEvidenceView) return;
    fitPendingRef.current = true;
    setGraphViewMode('evidence');
    setMessage('已为选定的图谱上下文切换至证据视图。');
  }, [graphViewMode, hasUserSelectedGraphView, preferEvidenceView]);

  useEffect(() => {
    setHasUserSelectedGraphView(false);
  }, [currentFileHash]);

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
    const fallbackGraph = subgraphForNode(visibleGraph, selectedNodeId);
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
  }, [canUseFileGraph, currentFileHash, graphNodeMap, selectedNodeId, visibleGraph]);

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

  const queryContextSummary = useMemo(() => {
    if (!queryResult) return [] as Array<{ key: string; label: string; count: number }>;
    const labels: Record<string, string> = {
      reports: '社区报告',
      entities: '实体',
      relationships: '关系',
      claims: '声明',
      sources: '来源',
    };
    return Object.entries(queryResult.context_data || {})
      .map(([key, rows]) => ({
        key,
        label: labels[key] || prettifyToken(key),
        count: Array.isArray(rows) ? rows.length : 0,
      }))
      .filter((item) => item.count > 0);
  }, [queryResult]);

  const queryLinkedNodes = useMemo(() => {
    if (!queryResult) return [] as Array<{ nodeId: string; label: string }>;
    return queryResult.linked_node_ids.map((nodeId) => {
      const graphNode = graphNodeMap.get(nodeId);
      return {
        nodeId,
        label: graphNode ? displayNameOfNode(graphNode) : shortText(nodeId.split('::').slice(-1)[0] || nodeId, 20),
      };
    });
  }, [graphNodeMap, queryResult]);

  const queryModeOptions: Array<{ value: Module4GraphRagQueryMode; label: string }> = [
    { value: 'local', label: UI_TEXT_RUNTIME.queryModeLocal },
    { value: 'global', label: UI_TEXT_RUNTIME.queryModeGlobal },
    { value: 'drift', label: UI_TEXT_RUNTIME.queryModeDrift },
    { value: 'basic', label: UI_TEXT_RUNTIME.queryModeBasic },
  ];

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
      label: UI_TEXT.graphRagLabel,
      value: healthz?.graphrag?.ready ? UI_TEXT.statusReady : UI_TEXT.statusUnavailable,
      tone: healthz?.graphrag?.ready
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-rose-200 bg-rose-50 text-rose-700',
    },
    {
      label: UI_TEXT.databaseLabel,
      value: healthz?.db_connected ? UI_TEXT.statusConnected : UI_TEXT.statusDisconnected,
      tone: healthz?.db_connected
        ? 'border-teal-200 bg-teal-50 text-teal-700'
        : 'border-rose-200 bg-rose-50 text-rose-700',
    },
    {
      label: UI_TEXT.jobStatus,
      value: currentJob ? jobStatusLabel(currentJob.status) : UI_TEXT.jobIdle,
      tone: currentJob ? jobTone(currentJob) : 'border-slate-200 bg-slate-50 text-slate-600',
    },
  ];

  const toolbarGraphStatusLabel = currentGraphFile
    ? graphFileStatusLabel(currentGraphFile.status)
    : currentFileHash
      ? UI_TEXT.selectedFilePendingGraphRecord
      : UI_TEXT.noGraphFileSelected;
  const toolbarSourceModeLabel =
    sourceMode === 'manual-select' ? UI_TEXT.manualSelect : UI_TEXT.followActiveFile;
  const toolbarSourceFileLabel =
    currentGraphFile?.file_name ||
    graphFiles.find((item) => item.file_hash === currentFileHash)?.file_name ||
    (sourceMode === 'manual-select' ? UI_TEXT.selectGraphFile : UI_TEXT.followingActiveFile);
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
    <section ref={rootSectionRef} className="module4-workbench module4-ide-shell relative">
      <div className="pointer-events-none absolute inset-0 z-10 flex h-full flex-col lg:flex-row">
        {/* Bottom Utility Dock */}
        <div className={cn(
          "absolute bottom-6 z-30 flex flex-col items-center pointer-events-none px-6 transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
          detailNode ? "left-0 right-[360px]" : "left-0 right-0"
        )}>
          <div className="w-full max-w-[860px] flex flex-col items-center">
            <AnimatePresence>
              {isUtilityDockOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 16, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 16, scale: 0.98 }}
                  transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
                  className="pointer-events-auto mb-4 w-full overflow-hidden rounded-2xl border border-white/80 bg-white/85 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.15),0_0_0_1px_rgba(255,255,255,0.5)] backdrop-blur-2xl ring-1 ring-black/5"
                >
                <div className="flex h-[220px]">
                  {/* Left Pane: Filters */}
                  <div className="flex w-1/2 flex-col border-r border-slate-200/50 p-5">
                    <div className="mb-4">
                      <h3 className="text-sm font-semibold text-slate-800">{UI_TEXT.utilityFiltersTitle}</h3>
                      <p className="text-[11px] text-slate-500">{UI_TEXT.utilityFiltersSubtitle}</p>
                    </div>
                    <div className="mb-5 flex items-center gap-3">
                      <div className="relative flex-1">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={14} />
                        <input
                          type="text"
                          placeholder={UI_TEXT.searchPlaceholder}
                          value={filters.query}
                          onChange={(e) => setFilters({...filters, query: e.target.value})}
                          className="h-9 w-full rounded-xl border border-slate-200 bg-slate-50/50 pl-9 pr-4 text-xs text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100/50"
                        />
                      </div>
                    </div>
                    <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
                      <div className="flex flex-wrap gap-2">
                        {nodeTypes.map((type) => {
                          const isActive = filters.nodeTypes.includes(type);
                          const count = nodeTypeCounts[type] || 0;
                          return (
                            <button
                              key={type}
                              type="button"
                              onClick={() => {
                                setFilters(prev => {
                                  const newTypes = prev.nodeTypes.includes(type)
                                    ? prev.nodeTypes.filter(t => t !== type)
                                    : [...prev.nodeTypes, type];
                                  return { ...prev, nodeTypes: newTypes };
                                });
                              }}
                              className={cn(
                                "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all",
                                isActive
                                  ? "bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200"
                                  : "bg-slate-50 text-slate-600 ring-1 ring-inset ring-slate-200/60 hover:bg-slate-100"
                              )}
                            >
                              <div className={cn(
                                "h-2 w-2 rounded-full",
                                isActive ? "bg-blue-500" : "bg-slate-300"
                              )} />
                              {type}
                              <span className={cn(
                                "ml-1 rounded-full px-1.5 py-0.5 text-[10px]",
                                isActive ? "bg-blue-100/50 text-blue-600" : "bg-slate-200/50 text-slate-500"
                              )}>
                                {count}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                  {/* Right Pane: Alerts */}
                  <div className="flex w-1/2 flex-col p-5 bg-slate-50/30">
                    <div className="mb-4 flex items-center justify-between">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-800">{UI_TEXT.alertsTitle}</h3>
                        <p className="text-[11px] text-slate-500">{UI_TEXT.alertsSubtitle}</p>
                      </div>
                      {openAlertCount > 0 && (
                        <span className="rounded-full bg-amber-100/60 px-2.5 py-1 text-[10px] font-semibold text-amber-700 border border-amber-200/50">
                          {openAlertCount} {UI_TEXT.unresolvedAlerts || '未解决'}
                        </span>
                      )}
                    </div>

                    <div className="flex-1 overflow-y-auto custom-scrollbar pr-2 space-y-2">
                      {alertPreviewItems.length === 0 ? (
                        <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-slate-200/80 bg-slate-50/50 px-4 text-xs text-slate-400">
                          {UI_TEXT.noAlerts}
                        </div>
                      ) : (
                        alertPreviewItems.map((alert) => (
                          <div
                            key={alert.alert_id}
                            className="group flex flex-col gap-2 rounded-xl border border-white bg-white/60 p-3 shadow-sm transition-all hover:border-slate-200 hover:bg-white hover:shadow-md backdrop-blur-sm"
                          >
                            <button
                              type="button"
                              onClick={() => void openNodeFromAlert(alert)}
                              className="w-full text-left"
                            >
                              <div className="flex items-start gap-2.5">
                                <div
                                  className={cn(
                                    'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border shadow-sm',
                                    alert.severity === 'red'
                                      ? 'border-rose-200 bg-rose-50 text-rose-600'
                                      : alert.severity === 'orange'
                                        ? 'border-amber-200 bg-amber-50 text-amber-700'
                                        : 'border-yellow-200 bg-yellow-50 text-yellow-700'
                                  )}
                                >
                                  <AlertTriangle size={14} />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-1.5">
                                    <span className="rounded bg-white shadow-sm border border-slate-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-500">
                                      {severityLabel(alert.severity)}
                                    </span>
                                    <span className="text-[10px] text-slate-400">{alertStatusLabel(alert.status)}</span>
                                  </div>
                                  <div className="mt-1 truncate text-xs font-semibold text-slate-800">{alert.title}</div>
                                </div>
                              </div>
                            </button>

                            <div className="flex items-center justify-between pl-9">
                              <div className="text-[10px] font-medium text-slate-400">{UI_TEXT.riskScore + ' ' + Math.round(alert.risk_score)}</div>
                              <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                  type="button"
                                  onClick={() => void handleAckAlert(alert.alert_id)}
                                  disabled={ackingAlertId === alert.alert_id}
                                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 hover:shadow-sm disabled:opacity-50"
                                >
                                  {ackingAlertId === alert.alert_id ? UI_TEXT.acknowledging : UI_TEXT.acknowledge}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleResolveAlert(alert.alert_id)}
                                  disabled={resolvingAlertId === alert.alert_id}
                                  className="rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-medium text-emerald-700 transition hover:border-emerald-300 hover:bg-emerald-100 hover:shadow-sm disabled:opacity-50"
                                >
                                  {resolvingAlertId === alert.alert_id ? UI_TEXT.resolving : UI_TEXT.resolve}
                                </button>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <motion.button
            layout
            type="button"
            onClick={() => setIsUtilityDockOpen(!isUtilityDockOpen)}
            className={cn(
              "pointer-events-auto flex h-12 items-center gap-5 rounded-full border border-white/60 bg-white/80 px-6 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.1)] backdrop-blur-xl transition-all hover:bg-white hover:shadow-[0_4px_24px_-4px_rgba(0,0,0,0.15)]",
              isUtilityDockOpen && "bg-white border-blue-200/80 shadow-[0_8px_30px_-4px_rgba(59,130,246,0.15)]"
            )}
          >
            <div className="flex items-center gap-2.5">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-sm">
                <Network size={14} />
              </div>
              <span className="text-[13px] font-bold tracking-wide text-slate-800">{UI_TEXT.utilityDockTitle}</span>
            </div>
            
            <div className="h-4 w-px bg-slate-200"></div>

            <div className="flex items-center gap-2">
              <span className="flex items-center gap-1.5 rounded-full bg-slate-100/80 px-2.5 py-1 text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-200/80">
                <Orbit size={12} className="text-blue-500" />
                {utilityNodeCountLabel}
              </span>
              <span className={cn(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors border border-transparent",
                openAlertCount > 0 
                  ? "bg-amber-50 text-amber-700 border-amber-200/60 hover:bg-amber-100" 
                  : "bg-slate-100/80 text-slate-600 hover:bg-slate-200/80"
              )}>
                <AlertTriangle size={12} className={openAlertCount > 0 ? "text-amber-500" : "text-slate-400"} />
                {utilityAlertCountLabel}
              </span>
            </div>

            <div className="h-4 w-px bg-slate-200"></div>

            <div className="flex items-center gap-2 text-slate-400 group">
              <span className="text-[11px] font-medium uppercase tracking-wider group-hover:text-slate-600 transition-colors">
                {isUtilityDockOpen ? UI_TEXT.collapseUtilityDock : UI_TEXT.expandUtilityDock}
              </span>
              <motion.div animate={{ rotate: isUtilityDockOpen ? 180 : 0 }} transition={{ duration: 0.3 }}>
                <ChevronDown size={14} className="text-slate-500 group-hover:text-slate-700 transition-colors" />
              </motion.div>
            </div>
          </motion.button>
          </div>
        </div>
        <div className="module4-ide-main pointer-events-none absolute inset-0 z-10">
          {/* Graph workspace header */}
          <header className="pointer-events-auto absolute left-6 top-6 z-20 flex items-center gap-4 rounded-2xl border border-blue-100/60 bg-[#fbfcfd]/90 px-5 py-3 shadow-sm backdrop-blur-md">
            <div className="flex items-center gap-3">
              <div className="text-base font-semibold tracking-tight text-slate-800">全域知识图谱</div>
            </div>
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
                      {graphFileOptionLabel(item, duplicateGraphFileNameCounts)}
                    </option>
                  ))}
                </select>
              </div>
          </header>

          <div className="relative flex min-h-0 flex-1 flex-row overflow-hidden pointer-events-none h-full w-full">
            
            {/* Left rail and canvas area */}
            <div className="relative flex h-full flex-1 flex-col overflow-hidden">
              {/* Canvas controls */}
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
                      setHasUserSelectedGraphView(true);
                      if (false && preferEvidenceView) {
                        setGraphViewMode('evidence');
                        setMessage('已为选定的上下文切换至图谱概览。');
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
                      setHasUserSelectedGraphView(true);
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

              {/* Viewport zoom controls */}
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

              <div className="pointer-events-auto px-6 pb-4 pt-2">
                <div className="rounded-2xl border border-slate-200/80 bg-white/92 p-4 shadow-[0_18px_40px_-24px_rgba(15,23,42,0.45)] backdrop-blur-md">
                  <div className="flex flex-col gap-2 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-900">{UI_TEXT_RUNTIME.queryPanelTitle}</div>
                      <p className="mt-1 text-xs leading-5 text-slate-500">{UI_TEXT_RUNTIME.queryPanelSubtitle}</p>
                    </div>
                    <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-medium text-slate-600">
                      {currentGraphFile?.file_name || UI_TEXT_RUNTIME.queryNeedsReadyGraph}
                    </div>
                  </div>

                  <div className="mt-4 flex flex-col gap-3 xl:flex-row">
                    <label className="flex min-w-[168px] flex-col gap-1.5 text-[11px] font-medium text-slate-600">
                      <span>{UI_TEXT_RUNTIME.queryModeLabel}</span>
                      <select
                        value={queryMode}
                        onChange={(event) => setQueryMode(event.target.value as Module4GraphRagQueryMode)}
                        className="h-10 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm text-slate-700 outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100/60"
                      >
                        {queryModeOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="relative flex-1">
                      <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                      <input
                        type="text"
                        value={queryText}
                        onChange={(event) => {
                          setQueryText(event.target.value);
                          if (queryError) setQueryError('');
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            void handleRunGraphRagQuery();
                          }
                        }}
                        placeholder={UI_TEXT_RUNTIME.queryPlaceholder}
                        className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-10 pr-4 text-sm text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100/60"
                      />
                    </div>

                    <button
                      type="button"
                      onClick={() => void handleRunGraphRagQuery()}
                      disabled={querying}
                      className={cn(
                        'inline-flex h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition',
                        querying
                          ? 'cursor-wait border border-blue-200 bg-blue-50 text-blue-600'
                          : 'border border-blue-600 bg-blue-600 text-white hover:bg-blue-700'
                      )}
                    >
                      <RefreshCw size={15} className={cn(querying && 'animate-spin')} />
                      {querying ? UI_TEXT_RUNTIME.queryRunning : UI_TEXT_RUNTIME.queryRun}
                    </button>
                  </div>

                  {queryError ? (
                    <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                      {queryError}
                    </div>
                  ) : null}

                  {queryResult ? (
                    <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
                      <div className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                          {UI_TEXT_RUNTIME.queryAnswerTitle}
                        </div>
                        <div className="max-h-[180px] overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-slate-700">
                          {queryResult.answer}
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div className="rounded-2xl border border-slate-200 bg-white p-4">
                          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                            {UI_TEXT_RUNTIME.queryContextTitle}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {queryContextSummary.length > 0 ? (
                              queryContextSummary.map((item) => (
                                <span
                                  key={item.key}
                                  className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600"
                                >
                                  {item.label} {item.count}
                                </span>
                              ))
                            ) : (
                              <span className="text-xs text-slate-400">0</span>
                            )}
                          </div>
                        </div>

                        <div className="rounded-2xl border border-slate-200 bg-white p-4">
                          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                            {UI_TEXT_RUNTIME.queryLinkedNodesTitle}
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {queryLinkedNodes.length > 0 ? (
                              queryLinkedNodes.map((item) => (
                                <button
                                  key={item.nodeId}
                                  type="button"
                                  onClick={() => void focusQueryNode(item.nodeId)}
                                  className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 transition hover:bg-blue-100"
                                >
                                  {shortText(item.label, 18)}
                                </button>
                              ))
                            ) : (
                              <span className="text-xs text-slate-400">-</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-3 text-xs leading-5 text-slate-500">{UI_TEXT_RUNTIME.queryEmpty}</p>
                  )}
                </div>
              </div>

              <div
                ref={graphHostRef}
                data-testid="module4-graph-host"
                className="pointer-events-auto module4-graph-host relative min-h-[420px] flex-1 overflow-hidden bg-white"
              >
                {isGraphSwitching && (
                  <div className="pointer-events-none absolute right-6 top-24 z-10">
                    <div className="flex max-w-sm items-center gap-3 rounded-2xl border border-slate-200 bg-white/96 px-4 py-3 shadow-sm backdrop-blur-md">
                      <RefreshCw size={16} className="animate-spin text-blue-600" />
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-slate-800">正在切换图谱</div>
                        <div
                          className="truncate text-xs text-slate-500"
                          title={currentGraphFile?.file_name || currentFileHash}
                        >
                          {currentGraphFile?.file_name || '正在加载所选文件对应的知识图谱'}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
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
                    graph={visibleGraph}
                    layoutGraph={layoutGraph}
                    layoutMode={layoutMode}
                    rootNodeId={graphRootNodeId}
                    selectedNodeId={selectedNodeId}
                    pinnedNodeIds={pinnedNodeIds}
                    hiddenEdgeCountsByNode={hiddenEdgeCountsByNode}
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

                    {detailConnectionNarrative && (
                      <div className="space-y-2 rounded-xl border border-slate-200/80 bg-slate-50/80 p-3 dark:border-slate-800/80 dark:bg-slate-900/40">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <div className="text-[11px] font-semibold tracking-[0.14em] text-slate-500 dark:text-slate-400">
                              图谱定位
                            </div>
                            <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                              {detailConnectionNarrative.title}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                              可见关系 {detailVisibleEdges.length}
                            </span>
                            <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                              折叠关系 {detailHiddenEdgeCount}
                            </span>
                          </div>
                        </div>
                        <p className="text-[11px] leading-5 text-slate-600 dark:text-slate-300">
                          {detailConnectionNarrative.summary}
                        </p>
                        <div className="space-y-1.5">
                          {detailConnectionNarrative.bullets.map((item, index) => (
                            <div
                              key={'cn-' + detailConnectionNarrative.title + '-' + String(index) + '-' + item}
                              className="flex items-start gap-2 rounded-lg bg-white/80 px-2.5 py-2 text-[11px] leading-5 text-slate-600 dark:bg-slate-950/40 dark:text-slate-300"
                            >
                              <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400 dark:bg-slate-500" />
                              <span>{item}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {false && detailConnectionNarrative && (
                      <div className="space-y-2 rounded-xl border border-slate-200/80 bg-slate-50/80 p-3 dark:border-slate-800/80 dark:bg-slate-900/40">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <div className="text-[11px] font-semibold tracking-[0.14em] text-slate-500 dark:text-slate-400">
                              图谱定位
                            </div>
                            <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                              {detailConnectionNarrative.title}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                              可见关系 {detailVisibleEdges.length}
                            </span>
                            <span className="rounded-full border border-slate-200 bg-white px-2 py-1 text-[10px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                              折叠关系 {detailHiddenEdgeCount}
                            </span>
                          </div>
                        </div>
                        <p className="text-[11px] leading-5 text-slate-600 dark:text-slate-300">
                          {detailConnectionNarrative.summary}
                        </p>
                        <div className="space-y-1.5">
                          {detailConnectionNarrative.bullets.map((item, index) => (
                            <div
                              key={detailConnectionNarrative.title + '-' + String(index) + '-' + item}
                              className="flex items-start gap-2 rounded-lg bg-white/80 px-2.5 py-2 text-[11px] leading-5 text-slate-600 dark:bg-slate-950/40 dark:text-slate-300"
                            >
                              <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400 dark:bg-slate-500" />
                              <span>{item}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {detailFactsOfNode(detailNode).length > 0 && (
                      <div className="space-y-2" data-testid="module4-detail-core-info">
                        <h4 className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">
                          {UI_TEXT.coreDetails}
                        </h4>
                        <div className="grid grid-cols-2 gap-y-2 gap-x-3 rounded-md border border-slate-100 dark:border-slate-800/60 bg-slate-50/30 dark:bg-slate-800/20 p-2.5">
                          {detailFactsOfNode(detailNode).map((fact) => (
                            <div key={fact.label + '-' + fact.value} className="min-w-0">
                              <div className="text-[10px] font-medium text-slate-500 dark:text-slate-400 mb-0.5">{fact.label}</div>
                              <div className="text-[11px] text-slate-700 dark:text-slate-300 truncate" title={fact.value}>{fact.value}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {typeKeyOf(detailNode) === 'community_report' && (
                      <div className="space-y-2" data-testid="module4-detail-community-report">
                        <h4 className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">社区报告</h4>
                        <div className="rounded-lg border border-violet-100 bg-violet-50/70 p-3 dark:border-violet-900/40 dark:bg-violet-900/15">
                          <div className="grid grid-cols-2 gap-2 text-[11px]">
                            <div className="text-slate-500 dark:text-slate-400">社区 ID</div>
                            <div className="text-right font-medium text-slate-700 dark:text-slate-200">
                              {normalizeText(asRecord(detailNode.attrs).community_id) || '-'}
                            </div>
                            <div className="text-slate-500 dark:text-slate-400">报告 ID</div>
                            <div className="text-right font-medium text-slate-700 dark:text-slate-200">
                              {normalizeText(asRecord(detailNode.attrs).report_id) || '-'}
                            </div>
                          </div>
                          <div className="mt-2 border-t border-violet-100 pt-2 text-[11px] leading-relaxed text-slate-700 dark:border-violet-900/50 dark:text-slate-300">
                            {normalizeText(asRecord(detailNode.attrs).summary) || '暂无报告摘要。'}
                          </div>
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
                                  {Math.round(alert.risk_score)} pts
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
                        {UI_TEXT.analysisTitle}
                      </h4>

                      <div className="rounded-md bg-indigo-50/40 dark:bg-indigo-900/10 p-3 border border-indigo-100/50 dark:border-indigo-800/30">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-100 dark:border-indigo-800/30 rounded px-1.5 py-0.5 text-[10px] font-medium text-indigo-600 dark:text-indigo-400">
                            {analysisTargetLabel
                              ? UI_TEXT.currentAnalysisTarget + ': ' + shortText(analysisTargetLabel, 28)
                              : UI_TEXT.currentAnalysisTarget}
                          </span>
                          {primaryDetailAlert && (
                            <span className="bg-rose-50 dark:bg-rose-900/30 border border-rose-100 dark:border-rose-800/30 rounded px-1.5 py-0.5 text-[10px] font-medium text-rose-600 dark:text-rose-400">
                              {severityLabel(primaryDetailAlert.severity)}
                            </span>
                          )}
                        </div>

                        <p className="mt-2 text-[11px] leading-relaxed text-slate-600 dark:text-slate-400">
                          {UI_TEXT.analysisTip}
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
                                    {UI_TEXT.explanationTitle}
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
                                      {UI_TEXT.reasoningSteps}
                                    </summary>
                                    <div className="mt-2 space-y-1.5">
                                      {explainResult.reasoning_steps.map((step, index) => (
                                        <div
                                          key={String(index + 1) + '-' + step}
                                          className="rounded bg-slate-50 dark:bg-slate-800/40 px-2.5 py-1.5 text-[11px] leading-relaxed text-slate-700 dark:text-slate-300 border border-slate-100 dark:border-slate-700/50"
                                        >
                                          {String(index + 1) + '. ' + step}
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
                                    {UI_TEXT.simulationTitle}
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
                                      {UI_TEXT.simulationDetails}
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
                                                key={item.metric + '-' + metricValueText(item.value)}
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
                                                  key={firstText(payload.alert_id, payload.rule_id, payload.title, index) + '-' + String(index)}
                                                  className="rounded-md bg-slate-50 dark:bg-slate-800/40 px-3 py-2.5 border border-slate-100 dark:border-slate-700/50"
                                                >
                                                  <div className="flex flex-wrap items-center gap-1.5">
                                                    <span className="rounded bg-white dark:bg-slate-900 px-1.5 py-0.5 text-[9px] font-medium text-slate-600 dark:text-slate-300 shadow-sm border border-slate-200 dark:border-slate-700">
                                                      {firstText(payload.rule_id, payload.alert_id, UI_TEXT.ruleFallback)}
                                                    </span>
                                                    {firstText(payload.severity) && (
                                                      <span className="rounded bg-rose-50 dark:bg-rose-900/30 px-1.5 py-0.5 text-[9px] font-medium text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-800/30">
                                                        {severityLabel(firstText(payload.severity))}
                                                      </span>
                                                    )}
                                                  </div>
                                                  <div className="mt-1.5 text-xs font-semibold text-slate-800 dark:text-slate-200">
                                                    {firstText(payload.title, payload.context_label, payload.summary, UI_TEXT.untitledAlert)}
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
                                        <div className="flex items-center gap-1.5">
                                          {edgeWeightText(edge) && (
                                            <span
                                              className="border px-2 py-0.5 rounded text-[10px] font-semibold text-slate-500 dark:text-slate-400"
                                              style={{
                                                borderColor: relationToneOf(edge) + '40',
                                                backgroundColor: relationToneOf(edge) + '10',
                                              }}
                                            >
                                              {edgeWeightText(edge)}
                                            </span>
                                          )}
                                          <span
                                            className="border px-2 py-0.5 rounded text-[10px] font-semibold text-slate-500 dark:text-slate-400"
                                            style={{
                                              borderColor: relationToneOf(edge) + '40',
                                              backgroundColor: relationToneOf(edge) + '14',
                                            }}
                                          >
                                            {Math.round(edge.confidence * 100)}%
                                          </span>
                                        </div>
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
                                                    key={item.evidence_id + '-edge-chip-' + String(index)}
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
                                  {UI_TEXT.noEdgeEvidence}
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
                                            key={item.evidence_id + '-chip-' + String(index)}
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
                                              key={item.evidence_id + '-chip-' + String(index)}
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
                                            borderColor: relationToneOf(edge) + '40',
                                            backgroundColor: relationToneOf(edge) + '14',
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
                                                    key={item.evidence_id + '-edge-chip-' + String(index)}
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
                            {UI_TEXT.attributesTitle}
                          </h4>
                          <div className="space-y-2">
                            {attributeRowsOfNode(detailNode).map((row) => (
                              <div
                                key={row.label + '-' + row.value}
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
                                <div className="flex items-center gap-1.5">
                                  {edgeWeightText(edge) && (
                                    <span
                                      className="border px-2 py-0.5 rounded text-[10px] font-semibold text-slate-500 dark:text-slate-400"
                                      style={{ borderColor: relationToneOf(edge) + '40', backgroundColor: relationToneOf(edge) + '10' }}
                                    >
                                      {edgeWeightText(edge)}
                                    </span>
                                  )}
                                  <span
                                    className="border px-2 py-0.5 rounded text-[10px] font-semibold text-slate-500 dark:text-slate-400"
                                    style={{ borderColor: relationToneOf(edge) + '40', backgroundColor: relationToneOf(edge) + '14' }}
                                  >
                                    {Math.round(edge.confidence * 100)}%
                                  </span>
                                </div>
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

