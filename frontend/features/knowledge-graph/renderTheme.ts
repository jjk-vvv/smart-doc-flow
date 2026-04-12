import type { Module4GraphEdge, Module4GraphNode } from '../../shared/api/knowledgeGraph';
import { semanticZoneOfNode } from './layoutPlanner';
import { asRecord, clamp, firstText, normalizeTypeKey } from './utils';

export type GraphNodeVisualSpec = {
  color: string;
  size: number;
  minRadius: number;
  maxRadius: number;
};

export type GraphEdgeEndpoints = {
  source?: Module4GraphNode | null;
  target?: Module4GraphNode | null;
  rootNodeId?: string;
};

export type GraphEdgeVisualPalette = {
  stroke: string;
  glow: string;
  tracer: string;
  tracerWidthBoost: number;
  dash?: string;
  tracerDash: string;
  tracerDuration: string;
};

export const GRAPH_ZONE_COLORS = {
  root: '#1F5A8C',
  context: '#2F7A6E',
  analysis: '#A86D2A',
  evidence: '#2E8B78',
  structure: '#7A8798',
  alert: '#B24A3B',
} as const;

const GRAPH_NODE_COLORS = {
  document: GRAPH_ZONE_COLORS.root,
  business_context: '#2F7A6E',
  topic: '#4E74A4',
  business_alert: GRAPH_ZONE_COLORS.alert,
  claim: '#A86D2A',
  observation: '#7A8440',
  community: '#8A6A2D',
  community_report: '#6C5A8E',
  entity: '#5E7397',
  field: '#6F7C8C',
  risk: GRAPH_ZONE_COLORS.alert,
  table: '#2E8B78',
  figure: '#3E7F96',
  image: '#3E7F96',
  chunk: '#97A4B2',
  fallback: '#758294',
} as const;

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

const hexToRgba = (value: string, alpha: number) => {
  const rgb = hexToRgb(value);
  if (!rgb) return value;
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${clamp(alpha, 0, 1)})`;
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

const typeKeyOf = (node: Module4GraphNode | string) => {
  if (typeof node === 'string') return normalizeTypeKey(node);
  return normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
};

const entitySubtypeColor = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const entityType = normalizeTypeKey(firstText(attrs.entity_type, attrs.object_type));
  if (entityType.includes('geo') || entityType.includes('location')) return '#2F7A6E';
  if (entityType.includes('organization') || entityType.includes('org')) return '#4E74A4';
  if (entityType.includes('person')) return '#B55D68';
  if (entityType.includes('event')) return '#B97A36';
  if (entityType.includes('indicator')) return '#7A8440';
  if (entityType.includes('facility')) return '#3C8A81';
  if (entityType.includes('project')) return '#5877A5';
  if (entityType.includes('material')) return '#92703E';
  return GRAPH_NODE_COLORS.entity;
};

const isRefactorEntityField = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  return normalizeTypeKey(attrs.entity_kind) === 'refactor_extracted_entity';
};

export const zoneToneOfNode = (node: Module4GraphNode, rootNodeId = '') => {
  const zoneKey = semanticZoneOfNode(node, rootNodeId);
  return GRAPH_ZONE_COLORS[zoneKey];
};

export const visualSpecOf = (node: Module4GraphNode): GraphNodeVisualSpec => {
  const key = typeKeyOf(node);

  if (key === 'document') return { color: GRAPH_NODE_COLORS.document, size: 40, minRadius: 17, maxRadius: 23 };
  if (key === 'business_context') return { color: GRAPH_NODE_COLORS.business_context, size: 42, minRadius: 18, maxRadius: 24 };
  if (key === 'topic') return { color: GRAPH_NODE_COLORS.topic, size: 40, minRadius: 17, maxRadius: 23 };
  if (key === 'business_alert') return { color: GRAPH_NODE_COLORS.business_alert, size: 40, minRadius: 17, maxRadius: 24 };
  if (key === 'claim') return { color: GRAPH_NODE_COLORS.claim, size: 38, minRadius: 16, maxRadius: 22 };
  if (key === 'observation') return { color: GRAPH_NODE_COLORS.observation, size: 38, minRadius: 15, maxRadius: 21 };
  if (key === 'entity') return { color: entitySubtypeColor(node), size: 40, minRadius: 16, maxRadius: 22 };
  if (key === 'field') {
    if (isRefactorEntityField(node)) {
      return { color: GRAPH_NODE_COLORS.entity, size: 38, minRadius: 15, maxRadius: 21 };
    }
    return { color: GRAPH_NODE_COLORS.field, size: 34, minRadius: 12, maxRadius: 18 };
  }
  if (key === 'community') return { color: GRAPH_NODE_COLORS.community, size: 42, minRadius: 18, maxRadius: 24 };
  if (key === 'community_report') return { color: GRAPH_NODE_COLORS.community_report, size: 36, minRadius: 13, maxRadius: 19 };
  if (key === 'risk') return { color: GRAPH_NODE_COLORS.risk, size: 38, minRadius: 16, maxRadius: 22 };
  if (key === 'figure' || key === 'image') return { color: GRAPH_NODE_COLORS.figure, size: 34, minRadius: 12, maxRadius: 18 };
  if (key === 'table') return { color: GRAPH_NODE_COLORS.table, size: 36, minRadius: 13, maxRadius: 19 };
  if (key === 'chunk') return { color: GRAPH_NODE_COLORS.chunk, size: 30, minRadius: 10, maxRadius: 16 };
  return { color: GRAPH_NODE_COLORS.fallback, size: 34, minRadius: 12, maxRadius: 18 };
};

const accentNodeOfEdge = (edge: Module4GraphEdge, endpoints?: GraphEdgeEndpoints) => {
  const rootNodeId = String(endpoints?.rootNodeId || '').trim();
  const source = endpoints?.source || null;
  const target = endpoints?.target || null;
  if (!source && !target) return null;

  const sourceZone = source ? semanticZoneOfNode(source, rootNodeId) : 'root';
  const targetZone = target ? semanticZoneOfNode(target, rootNodeId) : 'root';
  if (sourceZone === 'root' && target) return target;
  if (targetZone === 'root' && source) return source;
  return target || source;
};

const fallbackRelationTone = (edge: Module4GraphEdge | string) => {
  const key = normalizeTypeKey(typeof edge === 'string' ? edge : edge.relation_type || edge.relation_label);
  if (key.includes('overview_context')) return '#9FB6C9';
  if (key.includes('context') || key.includes('topic')) return GRAPH_ZONE_COLORS.context;
  if (key.includes('claim') || key.includes('observation')) return GRAPH_ZONE_COLORS.analysis;
  if (key.includes('business_alert') || key.includes('grounded')) return GRAPH_ZONE_COLORS.alert;
  if (key.includes('community')) return '#8A6A2D';
  if (key.includes('report')) return '#6C5A8E';
  if (key.includes('entity')) return '#58719B';
  if (key.includes('field') || key.includes('part')) return GRAPH_ZONE_COLORS.structure;
  if (key.includes('warning') || key.includes('risk')) return GRAPH_ZONE_COLORS.alert;
  if (key.includes('contain')) return '#6E8AA6';
  if (key.includes('evidence') || key.includes('support')) return GRAPH_ZONE_COLORS.evidence;
  return GRAPH_ZONE_COLORS.structure;
};

export const relationToneOf = (edge: Module4GraphEdge | string, endpoints?: GraphEdgeEndpoints) => {
  if (typeof edge === 'string') return fallbackRelationTone(edge);
  if (edge.isBaseEdge) {
    const accentNode = accentNodeOfEdge(edge, endpoints);
    if (accentNode) {
      return zoneToneOfNode(accentNode, String(endpoints?.rootNodeId || '').trim());
    }
  }
  return fallbackRelationTone(edge);
};

export const edgeVisualPaletteOf = (
  edge: Module4GraphEdge,
  endpoints?: GraphEdgeEndpoints,
): GraphEdgeVisualPalette => {
  const relationKey = normalizeTypeKey(edge.relation_type || edge.relation_label);
  const isBaseEdge = Boolean(edge.isBaseEdge);
  const tone = relationToneOf(edge, endpoints);

  if (isBaseEdge) {
    const stroke = mixHexColor(tone, '#f8fbff', 0.06);
    return {
      stroke,
      glow: hexToRgba(stroke, 0.14),
      tracer: 'rgba(255,255,255,0.82)',
      tracerWidthBoost: 0.06,
      dash: undefined,
      tracerDash: '0.16 0.84',
      tracerDuration: '4.6s',
    };
  }

  if (relationKey.includes('evidence') || relationKey.includes('support')) {
    return {
      stroke: GRAPH_ZONE_COLORS.evidence,
      glow: hexToRgba(GRAPH_ZONE_COLORS.evidence, 0.11),
      tracer: 'rgba(230,248,242,0.76)',
      tracerWidthBoost: -0.04,
      dash: '5 5',
      tracerDash: '0.1 0.9',
      tracerDuration: '6.2s',
    };
  }

  if (relationKey.includes('alert') || relationKey.includes('risk') || relationKey.includes('grounded')) {
    return {
      stroke: GRAPH_ZONE_COLORS.alert,
      glow: hexToRgba(GRAPH_ZONE_COLORS.alert, 0.1),
      tracer: 'rgba(252,232,228,0.7)',
      tracerWidthBoost: -0.02,
      dash: '6 6',
      tracerDash: '0.08 0.92',
      tracerDuration: '6.4s',
    };
  }

  if (relationKey.includes('context') || relationKey.includes('claim') || relationKey.includes('observation')) {
    return {
      stroke: tone,
      glow: hexToRgba(tone, 0.1),
      tracer: 'rgba(255,255,255,0.62)',
      tracerWidthBoost: -0.08,
      dash: undefined,
      tracerDash: '0.08 0.92',
      tracerDuration: '6.8s',
    };
  }

  return {
    stroke: mixHexColor(tone, '#dfe7ef', 0.16),
    glow: hexToRgba(tone, 0.08),
    tracer: 'rgba(255,255,255,0.42)',
    tracerWidthBoost: -0.1,
    dash: '3 6',
    tracerDash: '0.06 0.94',
    tracerDuration: '7.2s',
  };
};
