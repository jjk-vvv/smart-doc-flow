import type { Module4GraphEdge, Module4GraphNode } from '../../shared/api/knowledgeGraph';
import { GRAPH_ZONE_COLORS } from './renderTheme';
import { normalizeTypeKey } from './utils';

export type LegendNodeItem = {
  key: string;
  label: string;
  shape: 'circle' | 'panel' | 'diamond';
  color: string;
  description: string;
};

export type LegendEdgeItem = {
  key: string;
  label: string;
  color: string;
  style: 'primary-flow' | 'secondary' | 'support' | 'folded';
  description: string;
};

const NODE_LEGEND_LIBRARY: Record<string, LegendNodeItem> = {
  document: {
    key: 'document',
    label: '核心文档',
    shape: 'circle',
    color: GRAPH_ZONE_COLORS.root,
    description: '当前激活的文档节点，是知识图谱的主入口。',
  },
  semantic: {
    key: 'semantic',
    label: '语义节点',
    shape: 'circle',
    color: GRAPH_ZONE_COLORS.context,
    description: '包含实体、主题、结论、观察等核心语义信息。',
  },
  evidence: {
    key: 'evidence',
    label: '证据节点',
    shape: 'panel',
    color: GRAPH_ZONE_COLORS.evidence,
    description: '承载表格、图像、图表、片段等证据内容的节点。',
  },
  alert: {
    key: 'alert',
    label: '风险预警节点',
    shape: 'diamond',
    color: GRAPH_ZONE_COLORS.alert,
    description: '表示需要重点关注或处置的风险与预警信息。',
  },
  structure: {
    key: 'structure',
    label: '结构节点',
    shape: 'panel',
    color: GRAPH_ZONE_COLORS.structure,
    description: '用于组织抽取结构的辅助节点，如字段与分块。',
  },
};

const EDGE_LEGEND_LIBRARY: Record<string, LegendEdgeItem> = {
  primary: {
    key: 'primary',
    label: '主链路',
    color: GRAPH_ZONE_COLORS.root,
    style: 'primary-flow',
    description: '默认展示的主干关系路径。',
  },
  secondary: {
    key: 'secondary',
    label: '次级关系',
    color: GRAPH_ZONE_COLORS.structure,
    style: 'secondary',
    description: '节点之间的补充语义关系。',
  },
  support: {
    key: 'support',
    label: '证据支撑',
    color: GRAPH_ZONE_COLORS.evidence,
    style: 'support',
    description: '连接推理节点与证据节点的支撑关系。',
  },
  folded: {
    key: 'folded',
    label: '折叠关系计数',
    color: '#0F172A',
    style: 'folded',
    description: '角标数字表示尚未展开的关系数量。',
  },
};

const includeLegend = (present: Set<string>, candidates: string[]) => candidates.some((key) => present.has(key));

export const buildLegendNodeItems = (nodes: Module4GraphNode[]) => {
  const presentTypes = new Set(nodes.map((node) => normalizeTypeKey(node.node_type || node.type_label || node.category)));
  const items: LegendNodeItem[] = [];

  if (presentTypes.has('document')) items.push(NODE_LEGEND_LIBRARY.document);
  if (includeLegend(presentTypes, ['business_context', 'topic', 'community', 'community_report', 'entity', 'claim', 'observation'])) {
    items.push(NODE_LEGEND_LIBRARY.semantic);
  }
  if (includeLegend(presentTypes, ['table', 'figure', 'image'])) {
    items.push(NODE_LEGEND_LIBRARY.evidence);
  }
  if (includeLegend(presentTypes, ['business_alert', 'risk'])) {
    items.push(NODE_LEGEND_LIBRARY.alert);
  }
  if (includeLegend(presentTypes, ['field', 'chunk'])) {
    items.push(NODE_LEGEND_LIBRARY.structure);
  }

  return items;
};

export const buildLegendEdgeItems = (edges: Module4GraphEdge[]) => {
  const hasBaseEdges = edges.some((edge) => edge.isBaseEdge);
  const hasSupportEdges = edges.some((edge) => {
    const relationKey = normalizeTypeKey(edge.relation_type || edge.relation_label);
    return relationKey.includes('support') || relationKey.includes('evidence');
  });

  const items: LegendEdgeItem[] = [];
  if (hasBaseEdges) items.push(EDGE_LEGEND_LIBRARY.primary);
  items.push(EDGE_LEGEND_LIBRARY.secondary);
  if (hasSupportEdges) items.push(EDGE_LEGEND_LIBRARY.support);
  items.push(EDGE_LEGEND_LIBRARY.folded);
  return items;
};
