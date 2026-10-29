import type { Module4GraphEdge, Module4GraphNode, Module4GraphResponse } from '../../shared/api/knowledgeGraph';
import { asRecord, clamp, normalizeTypeKey } from './utils';
import type { GraphRenderCommunity, GraphRenderEdge, GraphRenderModel, GraphRenderNode } from './graphragViewModel';

const COMMUNITY_TYPE = 'community';
const ENTITY_TYPE = 'entity';
const DOCUMENT_TYPE = 'document';
const TEXT_UNIT_TYPE = 'textunit';
const CHUNK_TYPE = 'chunk';
const COVARIATE_TYPE = 'covariate';
const REPORT_TYPE = 'report';
const COMMUNITY_REPORT_TYPE = 'community_report';

const REL_RELATED_TO = 'related_to';
const REL_IN_COMMUNITY = 'in_community';
const REL_HAS_REPORT = 'has_report';
const REL_HAS_ENTITY = 'has_entity';
const REL_HAS_CHUNK = 'has_chunk';
const REL_MENTIONS = 'mentions';
const REL_EVIDENCE = 'evidence';

const COLORS = ['#6f42c1', '#0ea5e9', '#f59e0b', '#ef4444', '#10b981', '#3b82f6', '#f97316', '#14b8a6'];
const FALLBACK_COLOR = '#64748b';

const OVERVIEW_PER_COMMUNITY_LIMIT = 18;
const COMMUNITY_FOCUS_ENTITY_LIMIT = 24;
const DRILLDOWN_NEIGHBOR_LIMIT = 20;
const OVERVIEW_COMMUNITY_LIMIT = 14;
const OVERVIEW_BRIDGE_ENTITY_LIMIT = 20;
const OVERVIEW_BRIDGE_PER_COMMUNITY_LIMIT = 4;
const OVERVIEW_CORE_ENTITY_PER_COMMUNITY = 3;
const OVERVIEW_REPORTS_PER_COMMUNITY_LIMIT = 1;
const OVERVIEW_AGGREGATED_EDGE_LIMIT = 48;
const OVERVIEW_RELATED_PER_ENTITY_LIMIT = 3;
const OVERVIEW_MIN_RELATED_EDGES = 16;
const OVERVIEW_MAX_RELATED_EDGES = 180;
const OVERVIEW_RELATED_EDGE_MIN_SCORE = 0.34;

const NODE_TYPE_LABELS: Record<string, string> = {
  community: '\u793e\u533a',
  entity: '\u5b9e\u4f53',
  document: '\u6587\u6863',
  text_unit: '\u6587\u672c\u7247\u6bb5',
  textunit: '\u6587\u672c\u7247\u6bb5',
  chunk: '\u6587\u672c\u7247\u6bb5',
  covariate: '\u534f\u53d8\u91cf',
  report: '\u793e\u533a\u62a5\u544a',
  community_report: '\u793e\u533a\u62a5\u544a',
  communityreport: '\u793e\u533a\u62a5\u544a',
  artifact: '\u8865\u5145\u8282\u70b9',
  node: '\u8282\u70b9',
};

type GraphContext = {
  nodesById: Map<string, Module4GraphNode>;
  nodeTypeById: Map<string, string>;
  degreesByNodeId: Map<string, number>;
  neighborsByNodeId: Map<string, Set<string>>;
  edgesByNodeId: Map<string, Module4GraphEdge[]>;
  communityIds: string[];
  documentIds: string[];
  reportIdsByCommunityId: Map<string, string[]>;
  entityIdsByCommunityId: Map<string, string[]>;
  chunkIdsByCommunityId: Map<string, string[]>;
  chunkIdsByEntityId: Map<string, string[]>;
  communityIdByEntityId: Map<string, string>;
};

export type GraphRenderBuildOptions = {
  maxCommunityLevel?: number | null;
  enabledEdgeKinds?: GraphRenderEdge['kind'][];
  collapseCommunityMembersInOverview?: boolean;
  focusPeerCommunityId?: string | null;
  pinnedNodeIds?: string[] | null;
};

const cleanText = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim();

const truncateText = (value: unknown, maxChars = 96) => {
  const normalized = cleanText(value);
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
};

const NOISY_ENTITY_TERMS = [
  'assistant',
  'vision',
  'payload',
  'markdown',
  'worksheet',
  'spreadsheet',
  'table schema',
  'chart schema',
  'table summary',
  'chart summary',
];

const METRIC_HEADER_KEYWORDS = [
  'RATE',
  'GROWTH',
  'BALANCE',
  'TOTAL',
  'RATIO',
  'COUNT',
  'SHARE',
  'INCOME',
  'EXPENDITURE',
  'REVENUE',
  'OUTPUT',
  'USERS',
  'YEAR',
  'ANNUAL',
  'PERCENT',
  'INDICATOR',
  'INDEX',
];

const looksLikeMetricHeader = (value: string) => {
  if (!value) return false;
  if (/[\u4e00-\u9fff]/.test(value)) return false;
  const normalized = cleanText(value).replace(/[-_]/g, ' ');
  if (normalized.length < 18) return false;
  const tokens = normalized.split(/\s+/).filter(Boolean);
  if (tokens.length < 3) return false;
  const letters = normalized.match(/[A-Za-z]/g) || [];
  if (!letters.length) return false;
  const upper = letters.filter((char) => /[A-Z]/.test(char)).length;
  const upperRatio = upper / Math.max(1, letters.length);
  if (upperRatio < 0.9) return false;
  const upperText = normalized.toUpperCase();
  return METRIC_HEADER_KEYWORDS.some((keyword) => upperText.includes(keyword)) || tokens.length >= 4;
};

const noisyEntityLabel = (value: string) => {
  const normalized = cleanText(value);
  if (!normalized) return true;
  if (normalized.length <= 1) return true;
  if (/^community[\s\-_#]*\d*$/i.test(normalized)) return true;
  if (/^entity[\s\-_#]*\d*$/i.test(normalized)) return true;
  if (/^node[\s\-_#]*\d*$/i.test(normalized)) return true;
  if (/^\d+(?:[\-_/.:]\d+)*$/.test(normalized)) return true;
  if (/```|<table|<\/table>|\|\s*:?-+:?\s*\|/i.test(normalized)) return true;

  const lowered = normalized.toLowerCase();
  if (NOISY_ENTITY_TERMS.some((term) => lowered.includes(term))) return true;
  if (lowered.startsWith('timestamp ') || lowered.startsWith('model connectivity check')) return true;
  if (lowered.includes('docx_media') || lowered.startsWith('photo:') || lowered.includes('\u5185\u5d4c\u56fe\u50cf')) return true;
  if ((normalized.includes('|') || normalized.includes('\uFF5C')) && /\d.*\d/.test(normalized)) return true;
  if (normalized.length >= 20 && /[\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A/\uFF08\uFF09]/.test(normalized)) return true;
  if (looksLikeMetricHeader(normalized)) return true;

  const letterOrHan = (normalized.match(/[A-Za-z\u4e00-\u9fff]/g) || []).length;
  const symbolCount = (normalized.match(/[^\w\u4e00-\u9fff\s]/g) || []).length;
  if (letterOrHan === 0) return true;
  if (symbolCount / Math.max(1, normalized.length) >= 0.46) return true;
  if (normalized.length >= 64 && /[。！？；]/.test(normalized)) return true;
  return false;
};

const asNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const shortStableId = (value: unknown, maxChars = 8) => {
  const normalized = cleanText(value).replace(/^.*[:/]/, '');
  if (!normalized) return '';
  return normalized.length <= maxChars ? normalized : normalized.slice(-maxChars);
};

const hashColorIndex = (value: string) => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash % COLORS.length;
};

const colorForCluster = (clusterId: string) => (clusterId ? COLORS[hashColorIndex(clusterId)] : FALLBACK_COLOR);

const isTextUnitType = (nodeType: string) => nodeType === TEXT_UNIT_TYPE || nodeType === CHUNK_TYPE;

const isReportType = (nodeType: string) =>
  nodeType === REPORT_TYPE || nodeType === COMMUNITY_REPORT_TYPE || nodeType === 'communityreport';

const typeLabelForNodeType = (nodeType: string) => NODE_TYPE_LABELS[nodeType] || nodeType || NODE_TYPE_LABELS.node;

const normalizeNodeType = (node: Module4GraphNode) =>
  normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');

const normalizeRelationType = (edge: Module4GraphEdge) => normalizeTypeKey(edge.relation_type || edge.relation_label || 'related_to');

const edgeKindForRelation = (relationType: string): GraphRenderEdge['kind'] => {
  if (relationType === REL_IN_COMMUNITY) return 'in_community';
  if (relationType === REL_HAS_REPORT) return 'has_report';
  if (
    relationType === REL_HAS_ENTITY ||
    relationType === REL_HAS_CHUNK ||
    relationType === REL_MENTIONS ||
    relationType === REL_EVIDENCE
  ) {
    return 'evidence';
  }
  if (relationType === REL_RELATED_TO || relationType === 'related') return 'related_to';
  return 'other';
};

const edgeStyleForKind = (kind: GraphRenderEdge['kind']): GraphRenderEdge['styleToken'] => {
  if (kind === 'in_community') return 'membership';
  if (kind === 'has_report') return 'report';
  if (kind === 'evidence') return 'evidence';
  if (kind === 'related_to') return 'primary';
  return 'muted';
};

const nodeKindForType = (nodeType: string): GraphRenderNode['kind'] => {
  if (nodeType === COMMUNITY_TYPE) return 'community';
  if (nodeType === ENTITY_TYPE) return 'entity';
  if (nodeType === DOCUMENT_TYPE) return 'document';
  if (isTextUnitType(nodeType)) return 'text_unit';
  if (nodeType === COVARIATE_TYPE) return 'covariate';
  if (isReportType(nodeType)) return 'report';
  return 'artifact';
};

const nodeRoleForKind = (kind: GraphRenderNode['kind']): GraphRenderNode['role'] => {
  if (kind === 'community' || kind === 'document') return 'hub';
  if (kind === 'report') return 'summary';
  if (kind === 'text_unit' || kind === 'covariate') return 'evidence';
  return 'member';
};

const edgeKindSet = (options?: GraphRenderBuildOptions) =>
  options?.enabledEdgeKinds?.length ? new Set(options.enabledEdgeKinds) : null;

const ensureSet = (map: Map<string, Set<string>>, key: string) => {
  const current = map.get(key) || new Set<string>();
  map.set(key, current);
  return current;
};

const ensureList = <T,>(map: Map<string, T[]>, key: string) => {
  const current = map.get(key) || [];
  map.set(key, current);
  return current;
};

const pushUnique = <T,>(items: T[], value: T) => {
  if (!items.includes(value)) items.push(value);
};

const buildGraphContext = (graph: Module4GraphResponse): GraphContext => {
  const nodesById = new Map<string, Module4GraphNode>();
  const nodeTypeById = new Map<string, string>();
  const degreesByNodeId = new Map<string, number>();
  const neighborsByNodeId = new Map<string, Set<string>>();
  const edgesByNodeId = new Map<string, Module4GraphEdge[]>();
  const communityIds: string[] = [];
  const documentIds: string[] = [];
  const reportIdsByCommunityId = new Map<string, string[]>();
  const entityIdsByCommunityId = new Map<string, string[]>();
  const chunkIdsByCommunityId = new Map<string, string[]>();
  const chunkIdsByEntityId = new Map<string, string[]>();
  const communityIdByEntityId = new Map<string, string>();

  graph.nodes.forEach((node) => {
    const nodeId = cleanText(node.node_id);
    if (!nodeId) return;
    const nodeType = normalizeNodeType(node);
    nodesById.set(nodeId, node);
    nodeTypeById.set(nodeId, nodeType);
    degreesByNodeId.set(nodeId, 0);
    if (nodeType === COMMUNITY_TYPE) communityIds.push(nodeId);
    if (nodeType === DOCUMENT_TYPE) documentIds.push(nodeId);
  });

  graph.edges.forEach((edge) => {
    const source = cleanText(edge.source_node_id);
    const target = cleanText(edge.target_node_id);
    if (!source || !target || !nodesById.has(source) || !nodesById.has(target)) return;

    degreesByNodeId.set(source, (degreesByNodeId.get(source) || 0) + 1);
    degreesByNodeId.set(target, (degreesByNodeId.get(target) || 0) + 1);
    ensureSet(neighborsByNodeId, source).add(target);
    ensureSet(neighborsByNodeId, target).add(source);
    ensureList(edgesByNodeId, source).push(edge);
    ensureList(edgesByNodeId, target).push(edge);

    const relationType = normalizeRelationType(edge);
    const sourceType = nodeTypeById.get(source) || '';
    const targetType = nodeTypeById.get(target) || '';

    if (relationType === REL_IN_COMMUNITY) {
      if (sourceType === ENTITY_TYPE && targetType === COMMUNITY_TYPE) {
        pushUnique(ensureList(entityIdsByCommunityId, target), source);
        communityIdByEntityId.set(source, target);
      } else if (targetType === ENTITY_TYPE && sourceType === COMMUNITY_TYPE) {
        pushUnique(ensureList(entityIdsByCommunityId, source), target);
        communityIdByEntityId.set(target, source);
      }
    }

    if (relationType === REL_HAS_REPORT) {
      if (sourceType === COMMUNITY_TYPE && isReportType(targetType)) {
        pushUnique(ensureList(reportIdsByCommunityId, source), target);
      } else if (targetType === COMMUNITY_TYPE && isReportType(sourceType)) {
        pushUnique(ensureList(reportIdsByCommunityId, target), source);
      }
    }

    if (sourceType === COMMUNITY_TYPE && isTextUnitType(targetType)) {
      pushUnique(ensureList(chunkIdsByCommunityId, source), target);
    } else if (targetType === COMMUNITY_TYPE && isTextUnitType(sourceType)) {
      pushUnique(ensureList(chunkIdsByCommunityId, target), source);
    }

    if (sourceType === ENTITY_TYPE && isTextUnitType(targetType)) {
      pushUnique(ensureList(chunkIdsByEntityId, source), target);
    } else if (targetType === ENTITY_TYPE && isTextUnitType(sourceType)) {
      pushUnique(ensureList(chunkIdsByEntityId, target), source);
    }
  });

  return {
    nodesById,
    nodeTypeById,
    degreesByNodeId,
    neighborsByNodeId,
    edgesByNodeId,
    communityIds,
    documentIds,
    reportIdsByCommunityId,
    entityIdsByCommunityId,
    chunkIdsByCommunityId,
    chunkIdsByEntityId,
    communityIdByEntityId,
  };
};

const rawNodeLabel = (node: Module4GraphNode, nodeType: string) => {
  const attrs = asRecord(node.attrs);
  return (
    cleanText(node.display_name) ||
    cleanText(attrs.title) ||
    cleanText(attrs.name) ||
    cleanText(attrs.community_title) ||
    cleanText(node.canonical_key) ||
    `${typeLabelForNodeType(nodeType)}:${cleanText(node.node_id)}`
  );
};

const previewTextForNode = (node: Module4GraphNode, nodeType: string) => {
  const attrs = asRecord(node.attrs);
  if (isTextUnitType(nodeType)) {
    return truncateText(attrs.text || node.display_name || attrs.snippet, 160);
  }
  if (isReportType(nodeType)) {
    return truncateText(attrs.summary || attrs.full_content || node.display_name, 160);
  }
  if (nodeType === ENTITY_TYPE) {
    return truncateText(attrs.description || attrs.summary, 160);
  }
  if (nodeType === DOCUMENT_TYPE) {
    return truncateText(attrs.raw_content || attrs.summary, 160);
  }
  if (nodeType === COVARIATE_TYPE) {
    return truncateText(attrs.description || attrs.title || node.display_name, 160);
  }
  return '';
};

const communityDisplayLabel = (communityId: string, context: GraphContext) => {
  const normalized = cleanText(communityId);
  if (!normalized) return '';
  const communityNode = context.nodesById.get(normalized);
  if (!communityNode) return normalized;
  const communityType = context.nodeTypeById.get(normalized) || COMMUNITY_TYPE;
  return rawNodeLabel(communityNode, communityType);
};

const nodeLabel = (node: Module4GraphNode, nodeType: string) => {
  const attrs = asRecord(node.attrs);
  if (isTextUnitType(nodeType)) {
    const textPreview = truncateText(attrs.text || node.display_name || attrs.snippet, 24);
    if (textPreview) return textPreview;
    const humanReadableId = cleanText(attrs.human_readable_id);
    if (humanReadableId) return `\u6587\u672c\u7247\u6bb5 ${humanReadableId}`;
    return '\u6587\u672c\u7247\u6bb5';
  }
  if (isReportType(nodeType)) {
    const communityTitle = cleanText(attrs.community_title);
    if (communityTitle) return `${communityTitle} \u62a5\u544a`;
    return rawNodeLabel(node, nodeType);
  }
  if (nodeType === COVARIATE_TYPE) {
    return cleanText(node.display_name) || cleanText(attrs.title) || `\u534f\u53d8\u91cf ${shortStableId(node.node_id || node.canonical_key)}`;
  }
  return rawNodeLabel(node, nodeType);
};

const nodeImportance = (node: Module4GraphNode, degree: number) => {
  const attrs = asRecord(node.attrs);
  return Math.max(1, asNumber(attrs.importance, 0) || asNumber(attrs.weight, 0) || degree || 1);
};

const toRenderNode = (nodeId: string, context: GraphContext): GraphRenderNode | null => {
  const node = context.nodesById.get(nodeId);
  if (!node) return null;
  const nodeType = context.nodeTypeById.get(nodeId) || 'node';
  const kind = nodeKindForType(nodeType);
  const degree = context.degreesByNodeId.get(nodeId) || 0;
  const importance = nodeImportance(node, degree);
  const clusterId = kind === 'community' ? nodeId : cleanText(asRecord(node.attrs).community_id);
  const communityId = kind === 'entity' ? context.communityIdByEntityId.get(nodeId) || clusterId || null : clusterId || null;
  const communityLevel = asNumber(asRecord(node.attrs).level, 1);
  const resolvedClusterLabel =
    kind === 'community'
      ? rawNodeLabel(node, nodeType)
      : communityDisplayLabel(communityId || clusterId || '', context) || cleanText(asRecord(node.attrs).community_title);
  const previewText = previewTextForNode(node, nodeType);
  const fullLabel = rawNodeLabel(node, nodeType);
  return {
    id: nodeId,
    rawNodeId: node.node_id,
    label: nodeLabel(node, nodeType),
    kind,
    role: nodeRoleForKind(kind),
    communityId,
    communityLevel: Number.isFinite(communityLevel) ? communityLevel : null,
    degree,
    importance,
    size: 40,
    color: colorForCluster(communityId || clusterId || nodeId),
    visibleInOverview: kind !== 'text_unit' && kind !== 'covariate',
    visibleInFocus: kind !== 'text_unit' && kind !== 'covariate',
    visibleInDrilldown: kind !== 'text_unit' && kind !== 'covariate',
    collapsedByDefault: kind === 'text_unit' || kind === 'covariate',
    meta: {
      node_type: nodeType,
      node_type_key: nodeType,
      node_type_label: typeLabelForNodeType(nodeType),
      raw_label: fullLabel,
      cluster_label: resolvedClusterLabel,
      preview_text: previewText,
      attrs: node.attrs || {},
    },
  };
};

const toRenderEdge = (edge: Module4GraphEdge): GraphRenderEdge => {
  const relationType = normalizeRelationType(edge);
  const kind = edgeKindForRelation(relationType);
  const attrs = asRecord(edge.attrs);
  const weight = Math.max(0.25, asNumber(attrs.weight, asNumber(edge.confidence, 1)));
  const strength = Math.max(0.1, asNumber(attrs.strength, weight));
  return {
    id: cleanText(edge.edge_id) || `${cleanText(edge.source_node_id)}:${cleanText(edge.target_node_id)}:${relationType}`,
    rawEdgeId: edge.edge_id,
    source: cleanText(edge.source_node_id),
    target: cleanText(edge.target_node_id),
    kind,
    label: cleanText(edge.relation_label) || relationType || 'related_to',
    weight,
    strength,
    visibleInOverview: kind !== 'other',
    visibleInFocus: true,
    visibleInDrilldown: true,
    styleToken: edgeStyleForKind(kind),
    meta: {
      relation_type: relationType,
      relation_label_zh: cleanText(edge.relation_label) || relationType,
      attrs: edge.attrs || {},
    },
  };
};

const filterNodesByCommunityLevel = (nodes: GraphRenderNode[], options?: GraphRenderBuildOptions) => {
  const maxLevel = options?.maxCommunityLevel;
  if (!Number.isFinite(maxLevel as number)) return nodes;
  return nodes.filter((node) => node.kind !== 'community' || (node.communityLevel || 1) <= (maxLevel as number));
};

const filterEdgesByOptions = (edges: GraphRenderEdge[], options?: GraphRenderBuildOptions) => {
  const allowedKinds = edgeKindSet(options);
  if (!allowedKinds) return edges;
  return edges.filter((edge) => allowedKinds.has(edge.kind));
};

const filterNodesByMode = (nodes: GraphRenderNode[], mode: GraphRenderModel['mode']) => {
  if (mode === 'overview') return nodes.filter((node) => node.visibleInOverview);
  if (mode === 'community-focus') return nodes.filter((node) => node.visibleInFocus);
  return nodes.filter((node) => node.visibleInDrilldown);
};

const sortByEntityPriority = (left: GraphRenderNode, right: GraphRenderNode) => {
  if (right.importance !== left.importance) return right.importance - left.importance;
  if (right.degree !== left.degree) return right.degree - left.degree;
  return left.label.localeCompare(right.label, 'zh-CN');
};

const buildNoisyOverviewEntityIds = (context: GraphContext, pinnedNodeIds: Set<string>) => {
  const blocked = new Set<string>();
  context.nodeTypeById.forEach((nodeType, nodeId) => {
    if (nodeType !== ENTITY_TYPE) return;
    if (pinnedNodeIds.has(nodeId)) return;
    const renderNode = toRenderNode(nodeId, context);
    if (!renderNode) return;
    if (noisyEntityLabel(renderNode.label)) blocked.add(nodeId);
  });
  return blocked;
};

const scoreRelatedEdge = (edge: GraphRenderEdge) =>
  Math.max(0, Number(edge.weight || 0)) * 0.72 + Math.max(0, Number(edge.strength || 0)) * 0.28;

const pruneOverviewRelatedEdges = (edges: GraphRenderEdge[], nodes: GraphRenderNode[]): GraphRenderEdge[] => {
  if (!edges.length) return edges;
  const nodeKindById = new Map(nodes.map((node) => [node.id, node.kind]));
  const entityCount = nodes.filter((node) => node.kind === 'entity').length;
  if (entityCount <= 2) return edges;

  const relatedEdges = edges
    .filter((edge) => {
      if (edge.kind !== 'related_to') return false;
      return nodeKindById.get(edge.source) === 'entity' && nodeKindById.get(edge.target) === 'entity';
    })
    .sort((left, right) => scoreRelatedEdge(right) - scoreRelatedEdge(left));
  const nonRelatedEdges = edges.filter((edge) => edge.kind !== 'related_to');

  const targetRelatedEdgeLimit = Math.min(OVERVIEW_MAX_RELATED_EDGES, Math.max(OVERVIEW_MIN_RELATED_EDGES, entityCount * 2));
  const degreeByNodeId = new Map<string, number>();
  const selectedRelatedEdges: GraphRenderEdge[] = [];
  for (const edge of relatedEdges) {
    if (selectedRelatedEdges.length >= targetRelatedEdgeLimit) break;
    const sourceDegree = degreeByNodeId.get(edge.source) || 0;
    const targetDegree = degreeByNodeId.get(edge.target) || 0;
    const strongEnough = scoreRelatedEdge(edge) >= OVERVIEW_RELATED_EDGE_MIN_SCORE;
    const stillNeedCoverage = selectedRelatedEdges.length < OVERVIEW_MIN_RELATED_EDGES;
    if (!strongEnough && !stillNeedCoverage) continue;
    if (sourceDegree >= OVERVIEW_RELATED_PER_ENTITY_LIMIT || targetDegree >= OVERVIEW_RELATED_PER_ENTITY_LIMIT) continue;
    selectedRelatedEdges.push(edge);
    degreeByNodeId.set(edge.source, sourceDegree + 1);
    degreeByNodeId.set(edge.target, targetDegree + 1);
  }

  return [...nonRelatedEdges, ...selectedRelatedEdges];
};

const buildModelFromNodeIds = (
  graph: Module4GraphResponse,
  context: GraphContext,
  visibleNodeIds: Set<string>,
  mode: GraphRenderModel['mode'],
  options?: GraphRenderBuildOptions
): GraphRenderModel => {
  const levelFilteredNodes = filterNodesByCommunityLevel(
    [...visibleNodeIds]
      .map((nodeId) => toRenderNode(nodeId, context))
      .filter((node): node is GraphRenderNode => Boolean(node)),
    options
  );
  const modeFilteredNodes = filterNodesByMode(levelFilteredNodes, mode);
  const pinnedNodeIdSet = new Set((options?.pinnedNodeIds || []).map((nodeId) => cleanText(nodeId)).filter(Boolean));
  const nodes =
    pinnedNodeIdSet.size === 0
      ? modeFilteredNodes
      : (() => {
          const merged = new Map(modeFilteredNodes.map((node) => [node.id, node]));
          levelFilteredNodes.forEach((node) => {
            if (pinnedNodeIdSet.has(node.id)) merged.set(node.id, node);
          });
          return [...merged.values()];
        })();
  const allowedNodeIds = new Set(nodes.map((node) => node.id));
  const edges = filterEdgesByOptions(
    graph.edges
      .filter((edge) => allowedNodeIds.has(edge.source_node_id) && allowedNodeIds.has(edge.target_node_id))
      .map(toRenderEdge),
    options
  );
  // Keep full relationship fidelity in full overview mode.
  // Only prune related_to edges when user explicitly requests collapsed overview.
  const shouldPruneOverviewEdges = mode === 'overview' && Boolean(options?.collapseCommunityMembersInOverview);
  const stabilizedEdges = shouldPruneOverviewEdges ? pruneOverviewRelatedEdges(edges, nodes) : edges;
  const communities = nodes
    .filter((node) => node.kind === 'community')
    .map(
      (node): GraphRenderCommunity => ({
        id: node.id,
        label: node.label,
        level: Number(node.communityLevel || 1),
        entityCount: (context.entityIdsByCommunityId.get(node.id) || []).length,
        reportNodeId: (context.reportIdsByCommunityId.get(node.id) || [])[0] || null,
        color: node.color,
        importance: node.importance,
      })
    );

  return {
    mode,
    nodes,
    edges: stabilizedEdges,
    communities,
    stats: {
      rawNodeCount: graph.nodes.length,
      rawEdgeCount: graph.edges.length,
      renderedNodeCount: nodes.length,
      renderedEdgeCount: stabilizedEdges.length,
      hiddenEvidenceNodeCount: Math.max(0, graph.nodes.length - nodes.length),
      hiddenEvidenceEdgeCount: Math.max(0, graph.edges.length - stabilizedEdges.length),
    },
  };
};

type CommunityPairAggregate = {
  leftCommunityId: string;
  rightCommunityId: string;
  edgeCount: number;
  totalWeight: number;
  maxWeight: number;
  bridgeEntityIds: Set<string>;
};

const communityImportanceScore = (communityId: string, context: GraphContext) => {
  const entityCount = (context.entityIdsByCommunityId.get(communityId) || []).length;
  const reportCount = (context.reportIdsByCommunityId.get(communityId) || []).length;
  const degree = context.degreesByNodeId.get(communityId) || 0;
  return entityCount * 1.8 + reportCount * 2 + degree * 0.35;
};

const makeCommunityPairKey = (leftCommunityId: string, rightCommunityId: string) =>
  leftCommunityId < rightCommunityId
    ? `${leftCommunityId}::${rightCommunityId}`
    : `${rightCommunityId}::${leftCommunityId}`;

const buildCommunityProjectionOverviewModel = (
  graph: Module4GraphResponse,
  context: GraphContext,
  options?: GraphRenderBuildOptions
): GraphRenderModel | null => {
  if (!context.communityIds.length) return null;

  const rankedCommunityIds = [...context.communityIds].sort((left, right) => {
    const delta = communityImportanceScore(right, context) - communityImportanceScore(left, context);
    if (delta !== 0) return delta;
    return left.localeCompare(right, 'zh-CN');
  });

  const selectedCommunityIds = rankedCommunityIds.slice(0, OVERVIEW_COMMUNITY_LIMIT);
  const selectedCommunitySet = new Set(selectedCommunityIds);
  const ensureCommunitySelected = (communityId: string) => {
    if (!communityId || !context.nodesById.has(communityId) || selectedCommunitySet.has(communityId)) return;
    selectedCommunitySet.add(communityId);
    selectedCommunityIds.push(communityId);
  };

  const pinnedNodeIds = new Set((options?.pinnedNodeIds || []).map((nodeId) => cleanText(nodeId)).filter(Boolean));
  const blockedEntityIds = buildNoisyOverviewEntityIds(context, pinnedNodeIds);
  pinnedNodeIds.forEach((nodeId) => {
    const nodeType = context.nodeTypeById.get(nodeId) || '';
    if (nodeType === COMMUNITY_TYPE) {
      ensureCommunitySelected(nodeId);
      return;
    }
    if (nodeType === ENTITY_TYPE) {
      ensureCommunitySelected(context.communityIdByEntityId.get(nodeId) || '');
      return;
    }
    if (isReportType(nodeType)) {
      for (const [communityId, reportIds] of context.reportIdsByCommunityId.entries()) {
        if (reportIds.includes(nodeId)) {
          ensureCommunitySelected(communityId);
          break;
        }
      }
    }
  });

  const pairAggregates = new Map<string, CommunityPairAggregate>();
  const bridgeScoreByEntityId = new Map<string, number>();
  const bridgePeersByEntityId = new Map<string, Set<string>>();

  graph.edges.forEach((edge) => {
    const relationType = normalizeRelationType(edge);
    if (relationType !== REL_RELATED_TO) return;
    const sourceId = cleanText(edge.source_node_id);
    const targetId = cleanText(edge.target_node_id);
    if (!sourceId || !targetId || sourceId === targetId) return;
    if (blockedEntityIds.has(sourceId) || blockedEntityIds.has(targetId)) return;
    if ((context.nodeTypeById.get(sourceId) || '') !== ENTITY_TYPE) return;
    if ((context.nodeTypeById.get(targetId) || '') !== ENTITY_TYPE) return;

    const sourceCommunityId = context.communityIdByEntityId.get(sourceId) || '';
    const targetCommunityId = context.communityIdByEntityId.get(targetId) || '';
    if (!sourceCommunityId || !targetCommunityId || sourceCommunityId === targetCommunityId) return;
    if (!selectedCommunitySet.has(sourceCommunityId) || !selectedCommunitySet.has(targetCommunityId)) return;

    const pairKey = makeCommunityPairKey(sourceCommunityId, targetCommunityId);
    const existing = pairAggregates.get(pairKey) || {
      leftCommunityId: sourceCommunityId < targetCommunityId ? sourceCommunityId : targetCommunityId,
      rightCommunityId: sourceCommunityId < targetCommunityId ? targetCommunityId : sourceCommunityId,
      edgeCount: 0,
      totalWeight: 0,
      maxWeight: 0,
      bridgeEntityIds: new Set<string>(),
    };
    const weight = Math.max(0.2, asNumber(asRecord(edge.attrs).weight, asNumber(edge.confidence, 0.4)));
    existing.edgeCount += 1;
    existing.totalWeight += weight;
    existing.maxWeight = Math.max(existing.maxWeight, weight);
    existing.bridgeEntityIds.add(sourceId);
    existing.bridgeEntityIds.add(targetId);
    pairAggregates.set(pairKey, existing);

    bridgeScoreByEntityId.set(sourceId, (bridgeScoreByEntityId.get(sourceId) || 0) + weight + 0.3);
    bridgeScoreByEntityId.set(targetId, (bridgeScoreByEntityId.get(targetId) || 0) + weight + 0.3);
    const sourcePeers = bridgePeersByEntityId.get(sourceId) || new Set<string>();
    sourcePeers.add(targetCommunityId);
    bridgePeersByEntityId.set(sourceId, sourcePeers);
    const targetPeers = bridgePeersByEntityId.get(targetId) || new Set<string>();
    targetPeers.add(sourceCommunityId);
    bridgePeersByEntityId.set(targetId, targetPeers);
  });

  const bridgeCandidates = [...bridgeScoreByEntityId.entries()]
    .map(([entityId, score]) => {
      const communityId = context.communityIdByEntityId.get(entityId) || '';
      const peerCount = (bridgePeersByEntityId.get(entityId) || new Set<string>()).size;
      const degree = context.degreesByNodeId.get(entityId) || 0;
      return { entityId, score, communityId, peerCount, degree };
    })
    .filter((item) => item.communityId && selectedCommunitySet.has(item.communityId) && !blockedEntityIds.has(item.entityId))
    .sort((left, right) => {
      if (right.peerCount !== left.peerCount) return right.peerCount - left.peerCount;
      if (right.score !== left.score) return right.score - left.score;
      if (right.degree !== left.degree) return right.degree - left.degree;
      return left.entityId.localeCompare(right.entityId, 'zh-CN');
    });

  const selectedBridgeEntities = new Set<string>();
  const bridgeCountByCommunity = new Map<string, number>();
  bridgeCandidates.forEach((candidate) => {
    if (selectedBridgeEntities.size >= OVERVIEW_BRIDGE_ENTITY_LIMIT) return;
    const currentCount = bridgeCountByCommunity.get(candidate.communityId) || 0;
    if (currentCount >= OVERVIEW_BRIDGE_PER_COMMUNITY_LIMIT) return;
    selectedBridgeEntities.add(candidate.entityId);
    bridgeCountByCommunity.set(candidate.communityId, currentCount + 1);
  });

  pinnedNodeIds.forEach((nodeId) => {
    const nodeType = context.nodeTypeById.get(nodeId) || '';
    if (nodeType !== ENTITY_TYPE) return;
    const communityId = context.communityIdByEntityId.get(nodeId) || '';
    if (!communityId || !selectedCommunitySet.has(communityId)) return;
    selectedBridgeEntities.add(nodeId);
  });

  const selectedCoreEntities = new Set<string>();
  if (!options?.collapseCommunityMembersInOverview) {
    selectedCommunityIds.forEach((communityId) => {
      const members = (context.entityIdsByCommunityId.get(communityId) || [])
        .map((entityId) => toRenderNode(entityId, context))
        .filter((node): node is GraphRenderNode => Boolean(node) && !blockedEntityIds.has(node.id))
        .sort(sortByEntityPriority)
        .slice(0, OVERVIEW_CORE_ENTITY_PER_COMMUNITY);
      members.forEach((node) => selectedCoreEntities.add(node.id));
    });
  }
  pinnedNodeIds.forEach((nodeId) => {
    const nodeType = context.nodeTypeById.get(nodeId) || '';
    if (nodeType !== ENTITY_TYPE) return;
    const communityId = context.communityIdByEntityId.get(nodeId) || '';
    if (!communityId || !selectedCommunitySet.has(communityId)) return;
    selectedCoreEntities.add(nodeId);
  });
  const selectedOverviewEntities = new Set<string>([...selectedBridgeEntities, ...selectedCoreEntities]);

  const reportCommunityById = new Map<string, string>();
  const visibleNodeIds = new Set<string>(selectedCommunityIds);
  selectedCommunityIds.forEach((communityId) => {
    const reportIds = context.reportIdsByCommunityId.get(communityId) || [];
    reportIds.slice(0, OVERVIEW_REPORTS_PER_COMMUNITY_LIMIT).forEach((reportId) => {
      visibleNodeIds.add(reportId);
      reportCommunityById.set(reportId, communityId);
    });
  });
  selectedOverviewEntities.forEach((entityId) => visibleNodeIds.add(entityId));

  let nodes = [...visibleNodeIds]
    .map((nodeId) => toRenderNode(nodeId, context))
    .filter((node): node is GraphRenderNode => Boolean(node))
    .map((node) => {
      if (node.kind === 'community') {
        return { ...node, meta: { ...node.meta, overview_role: 'community_hub' } };
      }
      if (node.kind === 'report') {
        return { ...node, meta: { ...node.meta, overview_role: 'community_report' } };
      }
      if (node.kind === 'entity') {
        return {
          ...node,
          meta: {
            ...node.meta,
            overview_role: selectedBridgeEntities.has(node.id)
              ? 'bridge_entity'
              : selectedCoreEntities.has(node.id)
                ? 'core_entity'
                : 'member_entity',
          },
        };
      }
      return node;
    });

  nodes = filterNodesByCommunityLevel(nodes, options);
  const levelFilteredCommunityIds = new Set(nodes.filter((node) => node.kind === 'community').map((node) => node.id));
  nodes = nodes.filter((node) => {
    if (node.kind === 'community') return true;
    if (node.kind === 'report') {
      const communityId = reportCommunityById.get(node.id) || cleanText(node.communityId || '');
      return communityId ? levelFilteredCommunityIds.has(communityId) : false;
    }
    if (node.kind === 'entity') {
      if (blockedEntityIds.has(node.id) && !pinnedNodeIds.has(node.id)) return false;
      const communityId = context.communityIdByEntityId.get(node.id) || cleanText(node.communityId || '');
      return communityId ? levelFilteredCommunityIds.has(communityId) : false;
    }
    return false;
  });

  const allowedNodeIds = new Set(nodes.map((node) => node.id));
  const edgeMap = new Map<string, GraphRenderEdge>();
  const pushEdge = (edge: GraphRenderEdge) => {
    if (!allowedNodeIds.has(edge.source) || !allowedNodeIds.has(edge.target)) return;
    if (!edgeMap.has(edge.id)) edgeMap.set(edge.id, edge);
  };

  selectedOverviewEntities.forEach((entityId) => {
    const communityId = context.communityIdByEntityId.get(entityId) || '';
    if (!communityId || !allowedNodeIds.has(entityId) || !allowedNodeIds.has(communityId)) return;
    pushEdge({
      id: `overview::membership::${entityId}::${communityId}`,
      source: entityId,
      target: communityId,
      kind: 'in_community',
      label: '\u5f52\u5c5e\u793e\u533a',
      weight: 1,
      strength: 1,
      visibleInOverview: true,
      visibleInFocus: true,
      visibleInDrilldown: true,
      styleToken: 'membership',
      meta: {
        synthetic: true,
        overview_projection: true,
      },
    });
  });

  selectedCommunityIds.forEach((communityId) => {
    const reportIds = context.reportIdsByCommunityId.get(communityId) || [];
    reportIds.slice(0, OVERVIEW_REPORTS_PER_COMMUNITY_LIMIT).forEach((reportId) => {
      if (!allowedNodeIds.has(communityId) || !allowedNodeIds.has(reportId)) return;
      pushEdge({
        id: `overview::report::${communityId}::${reportId}`,
        source: communityId,
        target: reportId,
        kind: 'has_report',
        label: '\u793e\u533a\u62a5\u544a',
        weight: 1,
        strength: 1,
        visibleInOverview: true,
        visibleInFocus: true,
        visibleInDrilldown: true,
        styleToken: 'report',
        meta: {
          synthetic: true,
          overview_projection: true,
        },
      });
    });
  });

  [...pairAggregates.values()]
    .sort((left, right) => {
      if (right.edgeCount !== left.edgeCount) return right.edgeCount - left.edgeCount;
      if (right.totalWeight !== left.totalWeight) return right.totalWeight - left.totalWeight;
      return left.leftCommunityId.localeCompare(right.leftCommunityId, 'zh-CN');
    })
    .slice(0, OVERVIEW_AGGREGATED_EDGE_LIMIT)
    .forEach((aggregate) => {
      if (!allowedNodeIds.has(aggregate.leftCommunityId) || !allowedNodeIds.has(aggregate.rightCommunityId)) return;
      const meanWeight = aggregate.totalWeight / Math.max(1, aggregate.edgeCount);
      const bridgeEntityNames = [...aggregate.bridgeEntityIds]
        .map((entityId) => toRenderNode(entityId, context)?.label || '')
        .filter(Boolean)
        .slice(0, 6);
      pushEdge({
        id: `overview::aggregate::${aggregate.leftCommunityId}::${aggregate.rightCommunityId}`,
        source: aggregate.leftCommunityId,
        target: aggregate.rightCommunityId,
        kind: 'related_to',
        label: '\u8de8\u793e\u533a\u5173\u8054',
        weight: clamp(meanWeight * 2, 0.6, 6),
        strength: clamp(Math.log10(aggregate.edgeCount + 1), 0.25, 1),
        visibleInOverview: true,
        visibleInFocus: true,
        visibleInDrilldown: true,
        styleToken: 'primary',
        meta: {
          synthetic: true,
          overview_projection: true,
          aggregated: true,
          aggregate_count: aggregate.edgeCount,
          aggregate_weight: aggregate.totalWeight,
          bridge_entity_ids: [...aggregate.bridgeEntityIds].slice(0, 12),
          bridge_entity_names: bridgeEntityNames,
        },
      });
    });

  const allowedKinds = edgeKindSet(options);
  const edges = [...edgeMap.values()].filter((edge) => !allowedKinds || allowedKinds.has(edge.kind));
  const communities = nodes
    .filter((node) => node.kind === 'community')
    .map(
      (node): GraphRenderCommunity => ({
        id: node.id,
        label: node.label,
        level: Number(node.communityLevel || 1),
        entityCount: (context.entityIdsByCommunityId.get(node.id) || []).length,
        reportNodeId: (context.reportIdsByCommunityId.get(node.id) || [])[0] || null,
        color: node.color,
        importance: node.importance,
      })
    );

  return {
    mode: 'overview',
    nodes,
    edges,
    communities,
    stats: {
      rawNodeCount: graph.nodes.length,
      rawEdgeCount: graph.edges.length,
      renderedNodeCount: nodes.length,
      renderedEdgeCount: edges.length,
      hiddenEvidenceNodeCount: Math.max(0, graph.nodes.length - nodes.length),
      hiddenEvidenceEdgeCount: Math.max(0, graph.edges.length - edges.length),
    },
  };
};

const addTopEntitiesForCommunity = (
  communityId: string,
  context: GraphContext,
  target: Set<string>,
  limit = OVERVIEW_PER_COMMUNITY_LIMIT,
  blockedEntityIds: Set<string> = new Set()
) => {
  const entityNodes = (context.entityIdsByCommunityId.get(communityId) || [])
    .map((entityId) => toRenderNode(entityId, context))
    .filter((node): node is GraphRenderNode => Boolean(node) && !blockedEntityIds.has(node.id))
    .sort(sortByEntityPriority)
    .slice(0, limit);
  entityNodes.forEach((node) => target.add(node.id));
};

export const buildGraphRAGOverviewModel = (graph: Module4GraphResponse, options?: GraphRenderBuildOptions): GraphRenderModel => {
  const context = buildGraphContext(graph);
  // Projection mode is intentionally opt-in via collapse switch.
  // Default overview should preserve as many real nodes/edges as possible.
  if (options?.collapseCommunityMembersInOverview) {
    const projectedOverview = buildCommunityProjectionOverviewModel(graph, context, options);
    if (projectedOverview && projectedOverview.nodes.length > 0) {
      return projectedOverview;
    }
  }
  const pinnedNodeIdSet = new Set((options?.pinnedNodeIds || []).map((nodeId) => cleanText(nodeId)).filter(Boolean));
  const blockedEntityIds = buildNoisyOverviewEntityIds(context, pinnedNodeIdSet);

  const visibleNodeIds = new Set<string>();

  context.communityIds.forEach((communityId) => visibleNodeIds.add(communityId));

  if (context.communityIds.length === 0) {
    // No community anchors: keep all non-evidence nodes by default.
    context.nodeTypeById.forEach((nodeType, nodeId) => {
      if (isTextUnitType(nodeType) || nodeType === COVARIATE_TYPE) return;
      if (nodeType === ENTITY_TYPE && blockedEntityIds.has(nodeId)) return;
      visibleNodeIds.add(nodeId);
    });
    return buildModelFromNodeIds(graph, context, visibleNodeIds, 'overview', options);
  }

  if (!options?.collapseCommunityMembersInOverview) {
    // Full overview mode: keep all communities, reports, documents and entities
    // (except clearly noisy placeholder entities).
    context.nodeTypeById.forEach((nodeType, nodeId) => {
      if (isTextUnitType(nodeType) || nodeType === COVARIATE_TYPE) return;
      if (nodeType === ENTITY_TYPE && blockedEntityIds.has(nodeId)) return;
      visibleNodeIds.add(nodeId);
    });
  } else {
    context.communityIds.forEach((communityId) =>
      addTopEntitiesForCommunity(communityId, context, visibleNodeIds, OVERVIEW_PER_COMMUNITY_LIMIT, blockedEntityIds)
    );
  }

  pinnedNodeIdSet.forEach((nodeId) => {
    if (!context.nodesById.has(nodeId)) return;
    visibleNodeIds.add(nodeId);
    const communityId = context.communityIdByEntityId.get(nodeId);
    if (communityId && context.nodesById.has(communityId)) visibleNodeIds.add(communityId);
  });

  return buildModelFromNodeIds(graph, context, visibleNodeIds, 'overview', options);
};

export const buildGraphRAGCommunityFocusModel = (
  graph: Module4GraphResponse,
  communityId: string,
  options?: GraphRenderBuildOptions
): GraphRenderModel => {
  const context = buildGraphContext(graph);
  const rootCommunityId = cleanText(communityId);
  if (!rootCommunityId || !context.nodesById.has(rootCommunityId)) return buildGraphRAGOverviewModel(graph, options);

  const visibleNodeIds = new Set<string>([rootCommunityId]);
  addTopEntitiesForCommunity(rootCommunityId, context, visibleNodeIds, COMMUNITY_FOCUS_ENTITY_LIMIT);

  const reportIds = context.reportIdsByCommunityId.get(rootCommunityId) || [];
  reportIds.slice(0, 2).forEach((reportId) => visibleNodeIds.add(reportId));

  const peerId = cleanText(options?.focusPeerCommunityId || '');
  if (peerId && context.nodesById.has(peerId)) {
    visibleNodeIds.add(peerId);
    addTopEntitiesForCommunity(peerId, context, visibleNodeIds, Math.max(6, Math.floor(COMMUNITY_FOCUS_ENTITY_LIMIT / 2)));
  }

  return buildModelFromNodeIds(graph, context, visibleNodeIds, 'community-focus', options);
};

export const buildGraphRAGEntityDrilldownModel = (
  graph: Module4GraphResponse,
  entityId: string,
  options?: GraphRenderBuildOptions
): GraphRenderModel => {
  const context = buildGraphContext(graph);
  const rootEntityId = cleanText(entityId);
  if (!rootEntityId || !context.nodesById.has(rootEntityId)) return buildGraphRAGOverviewModel(graph, options);

  const visibleNodeIds = new Set<string>([rootEntityId]);
  const neighbors = [...(context.neighborsByNodeId.get(rootEntityId) || new Set<string>())];
  const rankedNeighbors = neighbors
    .map((nodeId) => toRenderNode(nodeId, context))
    .filter((node): node is GraphRenderNode => Boolean(node))
    .sort((left, right) => right.importance - left.importance || right.degree - left.degree);
  rankedNeighbors.slice(0, DRILLDOWN_NEIGHBOR_LIMIT).forEach((node) => visibleNodeIds.add(node.id));

  const communityId = context.communityIdByEntityId.get(rootEntityId) || '';
  if (communityId) {
    visibleNodeIds.add(communityId);
    const reportIds = context.reportIdsByCommunityId.get(communityId) || [];
    reportIds.slice(0, 2).forEach((reportId) => visibleNodeIds.add(reportId));
  }

  return buildModelFromNodeIds(graph, context, visibleNodeIds, 'entity-drilldown', options);
};
