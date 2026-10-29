import type { Module4GraphEdge, Module4GraphNode, Module4GraphResponse } from '../../shared/api/knowledgeGraph';
import { asRecord, normalizeTypeKey } from './utils';
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

const OVERVIEW_ENTITY_LIMIT = 96;
const OVERVIEW_PER_COMMUNITY_LIMIT = 18;
const COMMUNITY_FOCUS_ENTITY_LIMIT = 24;
const COMMUNITY_FOCUS_CHUNK_LIMIT = 16;
const DRILLDOWN_NEIGHBOR_LIMIT = 20;

const NODE_TYPE_LABELS: Record<string, string> = {
  community: '社区',
  entity: '实体',
  document: '文档',
  text_unit: '文本片段',
  textunit: '文本片段',
  chunk: '文本片段',
  covariate: '协变量',
  report: '社区报告',
  community_report: '社区报告',
  communityreport: '社区报告',
  artifact: '补充节点',
  node: '节点',
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
};

const cleanText = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim();
const GENERIC_COMMUNITY_RE = /^\s*community[\s_-]*\d+\s*$/i;
const GENERIC_REPORT_RE = /^\s*report[\s_-]*[a-z0-9-]+\s*$/i;
const HEXISH_RE = /^[0-9a-f][0-9a-f-]{11,}$/i;
const ARTIFACT_ENTITY_PREFIX_RE = /^(?:photo:|table[_-]|figure[_-]|image[_-]|chart[_-]|sheet[_-]|workbook[_-])/i;
const METRIC_ONLY_RE = /^(?:比上年)?(?:增长|下降|提高|增加|减少|增产|减产|上涨|回落)?\s*\d+(?:\.\d+)?\s*(?:%|‰)?$/;
const ZH_UNNAMED_COMMUNITY = '\u672a\u547d\u540d\u793e\u533a';
const ZH_COMMUNITY_REPORT = '\u793e\u533a\u62a5\u544a';
const ZH_EVIDENCE_NODE = '\u5019\u9009\u8bc1\u636e\u8282\u70b9';

const truncateText = (value: unknown, maxChars = 96) => {
  const normalized = cleanText(value);
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
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

const isPlaceholderCommunityTitle = (title: string, communityId: string) => {
  const normalizedTitle = cleanText(title);
  if (!normalizedTitle) return true;
  const lowerTitle = normalizedTitle.toLowerCase();
  const lowerId = cleanText(communityId).toLowerCase();
  const token = lowerId.split('::').pop() || lowerId;
  if (GENERIC_COMMUNITY_RE.test(normalizedTitle)) return true;
  if (lowerTitle === 'community' || lowerTitle === 'community report' || lowerTitle === 'report') return true;
  if (HEXISH_RE.test(lowerTitle)) return true;
  return (lowerTitle === lowerId || lowerTitle === token) && Boolean(token && (HEXISH_RE.test(token) || /^\d+$/.test(token)));
};

const isPlaceholderReportTitle = (title: string, reportId: string) => {
  const normalizedTitle = cleanText(title);
  if (!normalizedTitle) return true;
  const lowerTitle = normalizedTitle.toLowerCase();
  const lowerId = cleanText(reportId).toLowerCase();
  const token = lowerId.split('::').pop() || lowerId;
  if (GENERIC_REPORT_RE.test(normalizedTitle)) return true;
  if (HEXISH_RE.test(lowerTitle)) return true;
  return (lowerTitle === lowerId || lowerTitle === token) && Boolean(token && (HEXISH_RE.test(token) || /^\d+$/.test(token)));
};

const isHardNoiseEntityLabel = (label: string) => {
  const normalized = cleanText(label);
  if (!normalized) return true;
  if (HEXISH_RE.test(normalized)) return true;
  if (METRIC_ONLY_RE.test(normalized)) return true;
  if (ARTIFACT_ENTITY_PREFIX_RE.test(normalized)) return true;
  const lowered = normalized.toLowerCase();
  if (lowered.includes('docx_media') || lowered.includes('table schema') || lowered.includes('chart schema')) return true;
  if (lowered === 'document_title' || lowered === 'model connectivity check') return true;
  return false;
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
  return resolvedNodeLabel(communityNode, communityType);
};

const nodeLabel = (node: Module4GraphNode, nodeType: string) => {
  const attrs = asRecord(node.attrs);
  if (isTextUnitType(nodeType)) {
    const humanReadableId = cleanText(attrs.human_readable_id);
    const stableId = shortStableId(attrs.graphrag_id || node.node_id || node.canonical_key);
    if (humanReadableId) return `文本片段 ${humanReadableId}`;
    if (stableId) return `文本片段 ${stableId}`;
    return '文本片段';
  }
  if (isReportType(nodeType)) {
    const communityTitle = cleanText(attrs.community_title);
    if (communityTitle) return `${communityTitle} 报告`;
    return rawNodeLabel(node, nodeType);
  }
  if (nodeType === COVARIATE_TYPE) {
    return cleanText(node.display_name) || cleanText(attrs.title) || `协变量 ${shortStableId(node.node_id || node.canonical_key)}`;
  }
  return rawNodeLabel(node, nodeType);
};

const resolveCommunityNodeLabel = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const baseLabel = rawNodeLabel(node, COMMUNITY_TYPE);
  const communityId = cleanText(attrs.graphrag_id || node.node_id);
  const communityTitle = cleanText(attrs.community_title);
  if (isPlaceholderCommunityTitle(baseLabel, communityId)) {
    if (communityTitle && !isPlaceholderCommunityTitle(communityTitle, communityId)) return communityTitle;
    return ZH_UNNAMED_COMMUNITY;
  }
  return baseLabel || ZH_UNNAMED_COMMUNITY;
};

const resolveReportNodeLabel = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const baseLabel = rawNodeLabel(node, COMMUNITY_REPORT_TYPE);
  const reportId = cleanText(attrs.report_id || attrs.graphrag_id || node.node_id);
  const communityTitle = cleanText(attrs.community_title);
  if (isPlaceholderReportTitle(baseLabel, reportId)) {
    if (communityTitle) return communityTitle.endsWith('\u62a5\u544a') ? communityTitle : `${communityTitle} \u62a5\u544a`;
    return ZH_COMMUNITY_REPORT;
  }
  if (!baseLabel && communityTitle) return communityTitle.endsWith('\u62a5\u544a') ? communityTitle : `${communityTitle} \u62a5\u544a`;
  return baseLabel || ZH_COMMUNITY_REPORT;
};

const isSuppressedEntityNode = (node: Module4GraphNode, nodeType: string) => {
  if (nodeType !== ENTITY_TYPE) return false;
  const attrs = asRecord(node.attrs);
  const baseLabel = rawNodeLabel(node, nodeType);
  return cleanText(attrs.label_quality).toLowerCase() === 'suppressed' || isHardNoiseEntityLabel(baseLabel);
};

const resolveEntityNodeLabel = (node: Module4GraphNode, nodeType: string) => {
  const attrs = asRecord(node.attrs);
  const baseLabel = rawNodeLabel(node, nodeType);
  if (isSuppressedEntityNode(node, nodeType)) {
    const stableId = shortStableId(attrs.graphrag_id || node.node_id || node.canonical_key);
    return stableId ? `${ZH_EVIDENCE_NODE} ${stableId}` : ZH_EVIDENCE_NODE;
  }
  return baseLabel || ZH_EVIDENCE_NODE;
};

const resolvedNodeLabel = (node: Module4GraphNode, nodeType: string) => {
  if (nodeType === COMMUNITY_TYPE) return resolveCommunityNodeLabel(node);
  if (isReportType(nodeType)) return resolveReportNodeLabel(node);
  if (nodeType === ENTITY_TYPE) return resolveEntityNodeLabel(node, nodeType);
  return nodeLabel(node, nodeType);
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
  const attrs = asRecord(node.attrs);
  const label = resolvedNodeLabel(node, nodeType);
  const suppressedEntity = isSuppressedEntityNode(node, nodeType);
  const degree = context.degreesByNodeId.get(nodeId) || 0;
  const importance = nodeImportance(node, degree);
  const clusterId = kind === 'community' ? nodeId : cleanText(attrs.community_id);
  const communityId = kind === 'entity' ? context.communityIdByEntityId.get(nodeId) || clusterId || null : clusterId || null;
  const communityLevel = asNumber(attrs.level, 1);
  const resolvedClusterLabel =
    kind === 'community'
      ? label
      : communityDisplayLabel(communityId || clusterId || '', context) || cleanText(attrs.community_title);
  const previewText = previewTextForNode(node, nodeType);
  return {
    id: nodeId,
    rawNodeId: node.node_id,
    label,
    kind,
    role: nodeRoleForKind(kind),
    communityId,
    communityLevel: Number.isFinite(communityLevel) ? communityLevel : null,
    degree,
    importance,
    size: 40,
    color: colorForCluster(communityId || clusterId || nodeId),
    visibleInOverview: kind !== 'text_unit' && kind !== 'covariate' && !suppressedEntity,
    visibleInFocus: true,
    visibleInDrilldown: true,
    collapsedByDefault: kind === 'text_unit' || kind === 'covariate' || suppressedEntity,
    meta: {
      node_type: nodeType,
      node_type_key: nodeType,
      node_type_label: typeLabelForNodeType(nodeType),
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

const sortByEntityPriority = (left: GraphRenderNode, right: GraphRenderNode) => {
  if (right.importance !== left.importance) return right.importance - left.importance;
  if (right.degree !== left.degree) return right.degree - left.degree;
  return left.label.localeCompare(right.label, 'zh-CN');
};

const buildModelFromNodeIds = (
  graph: Module4GraphResponse,
  context: GraphContext,
  visibleNodeIds: Set<string>,
  mode: GraphRenderModel['mode'],
  options?: GraphRenderBuildOptions
): GraphRenderModel => {
  const nodes = filterNodesByCommunityLevel(
    [...visibleNodeIds]
      .map((nodeId) => toRenderNode(nodeId, context))
      .filter((node): node is GraphRenderNode => Boolean(node)),
    options
  );
  const allowedNodeIds = new Set(nodes.map((node) => node.id));
  const edges = filterEdgesByOptions(
    graph.edges
      .filter((edge) => allowedNodeIds.has(edge.source_node_id) && allowedNodeIds.has(edge.target_node_id))
      .map(toRenderEdge),
    options
  );
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
  limit = OVERVIEW_PER_COMMUNITY_LIMIT
) => {
  const entityNodes = (context.entityIdsByCommunityId.get(communityId) || [])
    .map((entityId) => toRenderNode(entityId, context))
    .filter((node): node is GraphRenderNode => Boolean(node))
    .sort(sortByEntityPriority)
    .slice(0, limit);
  entityNodes.forEach((node) => target.add(node.id));
};

export const buildGraphRAGOverviewModel = (graph: Module4GraphResponse, options?: GraphRenderBuildOptions): GraphRenderModel => {
  const context = buildGraphContext(graph);
  const visibleNodeIds = new Set<string>();

  context.documentIds.forEach((documentId) => visibleNodeIds.add(documentId));
  context.communityIds.forEach((communityId) => visibleNodeIds.add(communityId));

  if (context.communityIds.length === 0) {
    graph.nodes
      .filter((node) => {
        const nodeType = context.nodeTypeById.get(node.node_id) || '';
        return nodeType === DOCUMENT_TYPE || nodeType === ENTITY_TYPE;
      })
      .slice(0, 48)
      .forEach((node) => visibleNodeIds.add(node.node_id));
    return buildModelFromNodeIds(graph, context, visibleNodeIds, 'overview', options);
  }

  if (!options?.collapseCommunityMembersInOverview) {
    context.communityIds.forEach((communityId) => addTopEntitiesForCommunity(communityId, context, visibleNodeIds));
  }

  // Cap overview entity count to keep global layout stable.
  const overviewEntities = [...visibleNodeIds]
    .map((nodeId) => toRenderNode(nodeId, context))
    .filter((node): node is GraphRenderNode => Boolean(node) && node.kind === 'entity')
    .sort(sortByEntityPriority);
  if (overviewEntities.length > OVERVIEW_ENTITY_LIMIT) {
    const allowed = new Set(overviewEntities.slice(0, OVERVIEW_ENTITY_LIMIT).map((node) => node.id));
    [...visibleNodeIds].forEach((nodeId) => {
      const node = toRenderNode(nodeId, context);
      if (node?.kind === 'entity' && !allowed.has(nodeId)) visibleNodeIds.delete(nodeId);
    });
  }

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

  const chunkIds = context.chunkIdsByCommunityId.get(rootCommunityId) || [];
  chunkIds.slice(0, COMMUNITY_FOCUS_CHUNK_LIMIT).forEach((chunkId) => visibleNodeIds.add(chunkId));

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

  const chunkIds = context.chunkIdsByEntityId.get(rootEntityId) || [];
  chunkIds.slice(0, 8).forEach((chunkId) => visibleNodeIds.add(chunkId));

  return buildModelFromNodeIds(graph, context, visibleNodeIds, 'entity-drilldown', options);
};
