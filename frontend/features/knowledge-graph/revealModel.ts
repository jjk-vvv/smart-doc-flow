import type {
  Module4GraphEdge,
  Module4GraphNode,
  Module4GraphResponse,
} from '../../shared/api/knowledgeGraph';
import { asRecord, buildDegreeMap, normalizeTypeKey, otherNodeIdOfEdge } from './utils';

export type GraphRevealViewMode = 'overview' | 'evidence';

export type GraphRevealModel = {
  layoutGraph: Module4GraphResponse;
  visibleGraph: Module4GraphResponse;
  baseEdgeIds: Set<string>;
  visibleEdgeIds: Set<string>;
  hiddenEdgeCountsByNode: Map<string, number>;
};

type GraphRevealOptions = {
  graph: Module4GraphResponse;
  rootNodeId: string;
  selectedNodeId: string;
  viewMode: GraphRevealViewMode;
};

const buildStats = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const byNodeType: Record<string, number> = {};
  const byRelationType: Record<string, number> = {};

  nodes.forEach((node) => {
    const key = normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
    byNodeType[key] = (byNodeType[key] || 0) + 1;
  });

  edges.forEach((edge) => {
    const key = normalizeTypeKey(edge.relation_label || edge.relation_type || 'relation');
    byRelationType[key] = (byRelationType[key] || 0) + 1;
  });

  return {
    node_count: nodes.length,
    edge_count: edges.length,
    by_node_type: byNodeType,
    by_relation_type: byRelationType,
  };
};

const buildAdjacentEdgeMap = (edges: Module4GraphEdge[]) => {
  const adjacency = new Map<string, Module4GraphEdge[]>();
  edges.forEach((edge) => {
    if (!adjacency.has(edge.source_node_id)) adjacency.set(edge.source_node_id, []);
    adjacency.get(edge.source_node_id)!.push(edge);

    if (!adjacency.has(edge.target_node_id)) adjacency.set(edge.target_node_id, []);
    adjacency.get(edge.target_node_id)!.push(edge);
  });
  return adjacency;
};

const edgePriority = (
  edge: Module4GraphEdge,
  degreeMap: Map<string, number>,
  rootNodeId: string,
  viewMode: GraphRevealViewMode
) => {
  const relationKey = normalizeTypeKey(edge.relation_label || edge.relation_type);
  let score = Number(edge.confidence || 0) * 8;
  score += (degreeMap.get(edge.source_node_id) || 0) * 0.9;
  score += (degreeMap.get(edge.target_node_id) || 0) * 0.9;

  if (edge.source_node_id === rootNodeId || edge.target_node_id === rootNodeId) score += 22;
  if (relationKey === 'overview_context') score += 28;
  if (relationKey.includes('support') || relationKey.includes('evidence')) score += 11;
  if (relationKey.includes('claim') || relationKey.includes('observation')) score += 9;
  if (relationKey.includes('context') || relationKey.includes('topic')) score += 8;
  if (relationKey.includes('alert') || relationKey.includes('grounded')) score += 7;
  if (viewMode === 'evidence' && relationKey.includes('field')) score += 6;
  return score;
};

const pickComponentStartNodes = (
  nodes: Module4GraphNode[],
  edges: Module4GraphEdge[],
  rootNodeId: string
) => {
  const degreeMap = buildDegreeMap(nodes, edges);
  const remaining = [...nodes].sort((left, right) => {
    const rightDegree = degreeMap.get(right.node_id) || 0;
    const leftDegree = degreeMap.get(left.node_id) || 0;
    if (rightDegree !== leftDegree) return rightDegree - leftDegree;
    return String(left.node_id).localeCompare(String(right.node_id), 'zh-CN');
  });

  const orderedStartIds: string[] = [];
  if (rootNodeId && nodes.some((node) => node.node_id === rootNodeId)) {
    orderedStartIds.push(rootNodeId);
  }
  remaining.forEach((node) => {
    if (!orderedStartIds.includes(node.node_id)) {
      orderedStartIds.push(node.node_id);
    }
  });
  return orderedStartIds;
};

const buildBaseEdgeState = ({
  nodes,
  edges,
  rootNodeId,
  viewMode,
}: {
  nodes: Module4GraphNode[];
  edges: Module4GraphEdge[];
  rootNodeId: string;
  viewMode: GraphRevealViewMode;
}) => {
  const degreeMap = buildDegreeMap(nodes, edges);
  const adjacency = buildAdjacentEdgeMap(edges);
  const visited = new Set<string>();
  const baseEdgeIds = new Set<string>();
  const baseEdgeReasons = new Map<string, string>();
  const startIds = pickComponentStartNodes(nodes, edges, rootNodeId);

  startIds.forEach((startId) => {
    if (visited.has(startId)) return;
    const queue: string[] = [startId];
    visited.add(startId);
    let head = 0;

    while (head < queue.length) {
      const currentId = queue[head++];
      const incidentEdges = [...(adjacency.get(currentId) || [])].sort(
        (left, right) => edgePriority(right, degreeMap, rootNodeId, viewMode) - edgePriority(left, degreeMap, rootNodeId, viewMode)
      );

      incidentEdges.forEach((edge) => {
        const nextNodeId = otherNodeIdOfEdge(edge, currentId);
        if (visited.has(nextNodeId)) return;
        visited.add(nextNodeId);
        queue.push(nextNodeId);
        baseEdgeIds.add(edge.edge_id);

        const reason =
          edge.source_node_id === rootNodeId || edge.target_node_id === rootNodeId
            ? 'root-spoke'
            : currentId === startId
              ? 'component-bridge'
              : 'semantic-bridge';
        baseEdgeReasons.set(edge.edge_id, reason);
      });
    }
  });

  if (baseEdgeIds.size === 0 && edges.length > 0) {
    edges.forEach((edge) => {
      baseEdgeIds.add(edge.edge_id);
      baseEdgeReasons.set(edge.edge_id, 'fallback-all');
    });
  }

  return {
    baseEdgeIds,
    baseEdgeReasons,
  };
};

export const buildGraphRevealModel = ({
  graph,
  rootNodeId,
  selectedNodeId,
  viewMode,
}: GraphRevealOptions): GraphRevealModel => {
  const nodes = graph.nodes;
  const { baseEdgeIds, baseEdgeReasons } = buildBaseEdgeState({
    nodes,
    edges: graph.edges,
    rootNodeId,
    viewMode,
  });
  const annotatedEdges = graph.edges.map((edge) => {
    const isBaseEdge = baseEdgeIds.has(edge.edge_id);
    const baseEdgeReason = baseEdgeReasons.get(edge.edge_id) || null;
    return {
      ...edge,
      isBaseEdge,
      baseEdgeReason,
      attrs: {
        ...asRecord(edge.attrs),
        isBaseEdge,
        baseEdgeReason,
      },
    } satisfies Module4GraphEdge;
  });

  const visibleEdgeIds = new Set<string>(baseEdgeIds);
  if (selectedNodeId) {
    annotatedEdges.forEach((edge) => {
      if (edge.isBaseEdge) return;
      if (edge.source_node_id === selectedNodeId || edge.target_node_id === selectedNodeId) {
        visibleEdgeIds.add(edge.edge_id);
      }
    });
  }

  const hiddenEdgeCountsByNode = new Map<string, number>();
  annotatedEdges.forEach((edge) => {
    if (visibleEdgeIds.has(edge.edge_id)) return;
    hiddenEdgeCountsByNode.set(edge.source_node_id, (hiddenEdgeCountsByNode.get(edge.source_node_id) || 0) + 1);
    hiddenEdgeCountsByNode.set(edge.target_node_id, (hiddenEdgeCountsByNode.get(edge.target_node_id) || 0) + 1);
  });

  const layoutEdges = annotatedEdges;
  const visibleEdges = annotatedEdges.filter((edge) => visibleEdgeIds.has(edge.edge_id));

  return {
    layoutGraph: {
      nodes,
      edges: layoutEdges,
      source: graph.source,
      workspace_id: graph.workspace_id || null,
      stats: buildStats(nodes, layoutEdges),
    },
    visibleGraph: {
      nodes,
      edges: visibleEdges,
      source: graph.source,
      workspace_id: graph.workspace_id || null,
      stats: buildStats(nodes, visibleEdges),
    },
    baseEdgeIds,
    visibleEdgeIds,
    hiddenEdgeCountsByNode,
  };
};
