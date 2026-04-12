import type { Module4GraphEdge, Module4GraphNode } from '../../shared/api/knowledgeGraph';
import { normalizeTypeKey, otherNodeIdOfEdge } from './utils';

export type NodeConnectionNarrative = {
  title: string;
  summary: string;
  bullets: string[];
};

const relationLabelOf = (edge: Module4GraphEdge) =>
  normalizeTypeKey(edge.relation_label || edge.relation_type || 'relation');

const viewLabel = (viewMode: 'overview' | 'evidence') =>
  viewMode === 'overview' ? '概览图谱' : '证据图谱';

export const buildNodeConnectionNarrative = ({
  node,
  rootNodeId,
  visibleEdges,
  hiddenEdgeCount,
  nodeMap,
  viewMode,
}: {
  node: Module4GraphNode;
  rootNodeId: string;
  visibleEdges: Module4GraphEdge[];
  hiddenEdgeCount: number;
  nodeMap: Map<string, Module4GraphNode>;
  viewMode: 'overview' | 'evidence';
}): NodeConnectionNarrative => {
  if (node.node_id === rootNodeId) {
    return {
      title: '中心锚点',
      summary:
        '该节点是当前文档图谱的中心锚点，图谱会从这里向外展开语义关系与证据关系。',
      bullets: [
        `当前视图：${viewLabel(viewMode)}`,
        `已展示主关系：${visibleEdges.length} 条`,
        hiddenEdgeCount > 0 ? `尚有折叠关系：${hiddenEdgeCount} 条` : '当前无折叠关系',
      ],
    };
  }

  const visibleBaseEdges = visibleEdges.filter((edge) => edge.isBaseEdge);
  const directRootEdge = visibleBaseEdges.find(
    (edge) => edge.source_node_id === rootNodeId || edge.target_node_id === rootNodeId
  );

  if (directRootEdge) {
    return {
      title: '一级主链路',
      summary:
        '该节点与中心文档直接相连，因此会出现在图谱主骨架中。',
      bullets: [
        `主关系类型：${relationLabelOf(directRootEdge)}`,
        `当前视图：${viewLabel(viewMode)}`,
        hiddenEdgeCount > 0 ? `额外折叠关系：${hiddenEdgeCount} 条` : '无额外折叠关系',
      ],
    };
  }

  const bridgeEdge = visibleBaseEdges[0];
  if (bridgeEdge) {
    const bridgeNode = nodeMap.get(otherNodeIdOfEdge(bridgeEdge, node.node_id));
    const bridgeName = String(bridgeNode?.display_name || bridgeNode?.canonical_key || '关联节点').trim();
    return {
      title: '桥接路径',
      summary: `该节点通过“${bridgeName}”接入中心文档，因此以间接主链路形式展示。`,
      bullets: [
        `桥接关系类型：${relationLabelOf(bridgeEdge)}`,
        `当前视图：${viewLabel(viewMode)}`,
        hiddenEdgeCount > 0 ? `可展开折叠关系：${hiddenEdgeCount} 条` : '无额外折叠关系',
      ],
    };
  }

  return {
    title: '折叠上下文节点',
    summary:
      hiddenEdgeCount > 0
        ? `该节点仍有 ${hiddenEdgeCount} 条关系未在默认视图中展开。`
        : '该节点当前没有可见主关系，通常由筛选条件或邻域范围造成。',
    bullets: [
      `当前视图：${viewLabel(viewMode)}`,
      hiddenEdgeCount > 0 ? `折叠关系：${hiddenEdgeCount} 条` : '折叠关系：0 条',
      '点击该节点可继续展开更多邻域关系与证据路径。',
    ],
  };
};
