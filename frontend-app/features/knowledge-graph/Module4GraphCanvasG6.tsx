import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CanvasEvent, CommonEvent, EdgeEvent, Graph, NodeEvent, type EdgeData, type GraphData, type NodeData } from '@antv/g6';
import type { GraphRenderEdge, GraphRenderModel, GraphRenderNode } from './graphragViewModel';

type Module4GraphCanvasG6Props = {
  model: GraphRenderModel;
  className?: string;
  selectedNodeId?: string | null;
  selectedEdgeId?: string | null;
  queryHitNodeIds?: string[];
  onSelectNode?: (nodeId: string | null) => void;
  onSelectEdge?: (edgeId: string | null) => void;
  onHoverNode?: (nodeId: string | null) => void;
  onHoverEdge?: (edgeId: string | null) => void;
};

const UNIFORM_NODE_SIZE = 40;
const NODE_COLLISION_RADIUS = 28;
const MIN_AUTO_FIT_ZOOM = 0.25;
const MAX_AUTO_FIT_ZOOM = 1.08;
const SMALL_GRAPH_NODE_THRESHOLD = 12;
const SMALL_GRAPH_EDGE_THRESHOLD = 16;
const STABLE_OVERVIEW_NODE_THRESHOLD = 140;
const GRAPH_DEFAULT_WIDTH = 1280;
const GRAPH_DEFAULT_HEIGHT = 420;
const GRAPH_MIN_WIDTH = 360;
const GRAPH_MIN_HEIGHT = 300;

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const toNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const isAggregatedEdge = (edge: GraphRenderEdge) => Boolean(asRecord(edge.meta).aggregated);

const isSmallGraphModel = (model: GraphRenderModel) =>
  model.mode === 'overview' &&
  model.nodes.length > 0 &&
  model.nodes.length <= SMALL_GRAPH_NODE_THRESHOLD &&
  model.edges.length <= SMALL_GRAPH_EDGE_THRESHOLD;

const usesStableOverviewLayout = (model: GraphRenderModel) =>
  model.mode === 'overview' && model.nodes.length > 0 && model.nodes.length <= STABLE_OVERVIEW_NODE_THRESHOLD;

const cleanSemanticLabel = (value: string) =>
  String(value || '')
    .replace(/[A-Za-z_]{4,24}$/, '')
    .trim();

const compactNodeLabel = (value: string) => {
  const normalized = cleanSemanticLabel(String(value || ''));
  if (!normalized) return '节点';
  if (normalized.length <= 7) return normalized;
  return `${normalized.slice(0, 6)}...`;
};

const aggregatedEdgeLabel = (edge: GraphRenderEdge) => {
  const meta = asRecord(edge.meta);
  const count = Math.max(1, Math.floor(toNumber(meta.aggregate_count, 1)));
  const totalWeight = Number(edge.weight || 0).toFixed(1);
  return `跨社区关联（${count}）权重 ${totalWeight}`;
};

const edgeStyleOf = (edge: GraphRenderEdge, mode: GraphRenderModel['mode']) => {
  const aggregated = isAggregatedEdge(edge);
  const shouldShowAggregateLabel = aggregated && mode === 'overview';
  const showEdgeLabel = mode !== 'overview' && edge.styleToken !== 'membership';

  if (edge.styleToken === 'membership') {
    return {
      stroke: '#c7d3e3',
      lineWidth: 1.2,
      opacity: 0.56,
      endArrow: false,
      labelText: '',
    };
  }

  if (edge.styleToken === 'report') {
    return {
      stroke: '#b3c0d1',
      lineWidth: 1.1,
      opacity: 0.5,
      endArrow: false,
      lineDash: [4, 4],
      labelText: showEdgeLabel ? edge.label : '',
      labelAutoRotate: true,
      labelFill: '#64748b',
      labelFontSize: 10,
      labelBackground: true,
      labelBackgroundFill: '#ffffff',
      labelBackgroundOpacity: 0.92,
      labelBackgroundPadding: [2, 4],
    };
  }

  if (aggregated) {
    return {
      stroke: '#97a7bd',
      lineWidth: Math.max(1.8, Math.min(3.6, 1.2 + edge.weight * 0.05)),
      opacity: 0.56,
      endArrow: false,
      lineDash: [5, 4],
      labelText: shouldShowAggregateLabel ? aggregatedEdgeLabel(edge) : '',
      labelAutoRotate: true,
      labelFill: '#475569',
      labelFontSize: 10,
      labelBackground: true,
      labelBackgroundFill: '#f8fafc',
      labelBackgroundOpacity: 0.95,
      labelBackgroundPadding: [2, 5],
    };
  }

  if (edge.styleToken === 'evidence') {
    return {
      stroke: '#aebccc',
      lineWidth: 1.15,
      opacity: 0.54,
      endArrow: true,
      labelText: showEdgeLabel ? edge.label : '',
      labelAutoRotate: true,
      labelFill: '#64748b',
      labelFontSize: 10,
      labelBackground: true,
      labelBackgroundFill: '#ffffff',
      labelBackgroundOpacity: 0.9,
      labelBackgroundPadding: [2, 4],
    };
  }

  return {
    stroke: '#9cadc4',
    lineWidth: Math.max(1.2, Math.min(2.2, 1 + edge.weight * 0.12)),
    opacity: 0.58,
    endArrow: true,
    labelText: showEdgeLabel ? edge.label : '',
    labelAutoRotate: true,
    labelFill: '#64748b',
    labelFontSize: 10,
    labelBackground: true,
    labelBackgroundFill: '#ffffff',
    labelBackgroundOpacity: 0.92,
    labelBackgroundPadding: [2, 4],
  };
};

const shouldShowNodeLabel = (node: GraphRenderNode, model: GraphRenderModel, labelIds: Set<string>) =>
  labelIds.has(node.id) || model.nodes.length <= 12;

const buildVisibleLabelIds = (model: GraphRenderModel) => {
  const ids = new Set<string>();

  if (model.nodes.length <= 18) {
    model.nodes.forEach((node) => ids.add(node.id));
    return ids;
  }

  model.nodes.forEach((node) => {
    if (node.kind === 'community' || node.kind === 'document') {
      ids.add(node.id);
    }
  });

  model.nodes
    .filter((node) => node.kind === 'entity')
    .sort((left, right) => right.degree - left.degree || right.importance - left.importance)
    .slice(0, model.mode === 'overview' ? 24 : 32)
    .forEach((node) => ids.add(node.id));

  return ids;
};

const polarPoint = (centerX: number, centerY: number, radius: number, angle: number) => ({
  x: centerX + Math.cos(angle) * radius,
  y: centerY + Math.sin(angle) * radius,
});

const buildPresetPositions = (model: GraphRenderModel) => {
  const positions = new Map<string, { x: number; y: number }>();
  const documentNodes = model.nodes.filter((node) => node.kind === 'document');
  const communityNodes = model.nodes.filter((node) => node.kind === 'community');
  const entityNodes = model.nodes.filter((node) => node.kind === 'entity');
  const otherNodes = model.nodes.filter((node) => !['document', 'community', 'entity'].includes(node.kind));

  if (model.mode === 'overview') {
    const compactOverview = isSmallGraphModel(model);
    const stableOverview = usesStableOverviewLayout(model);
    const rootX = 0;
    const rootY = stableOverview ? -220 : -180;
    const communitySpacing = compactOverview ? 260 : stableOverview ? 340 : 280;
    const communityStartX = -((Math.max(communityNodes.length, 1) - 1) * communitySpacing) / 2;
    const communityY = stableOverview ? 20 : 0;

    documentNodes.forEach((node, index) => {
      positions.set(node.id, { x: rootX + index * 120, y: rootY });
    });

    communityNodes.forEach((node, index) => {
      positions.set(node.id, {
        x: communityStartX + index * communitySpacing,
        y: communityY,
      });
    });

    const entitiesByCommunity = new Map<string, GraphRenderNode[]>();
    entityNodes.forEach((node) => {
      const key = String(node.communityId || 'unassigned');
      const current = entitiesByCommunity.get(key) || [];
      current.push(node);
      entitiesByCommunity.set(key, current);
    });

    communityNodes.forEach((communityNode) => {
      const members = (entitiesByCommunity.get(communityNode.id) || []).sort(
        (left, right) => right.importance - left.importance || right.degree - left.degree
      );
      const center = positions.get(communityNode.id) || { x: 0, y: 0 };
      members.forEach((node, index) => {
        const ringIndex = Math.floor(index / 8);
        const slotIndex = index % 8;
        const ringSize = Math.min(8, members.length - ringIndex * 8);
        const startAngle = Math.PI * 0.18;
        const endAngle = Math.PI * 0.82;
        const ratio = ringSize <= 1 ? 0.5 : slotIndex / Math.max(1, ringSize - 1);
        const angle = startAngle + (endAngle - startAngle) * ratio;
        const radius = (compactOverview ? 118 : stableOverview ? 128 : 108) + ringIndex * (compactOverview ? 52 : stableOverview ? 64 : 56);
        positions.set(node.id, polarPoint(center.x, center.y, radius, angle));
      });
    });

    const mappedCommunityIds = new Set(communityNodes.map((node) => node.id));
    const unassignedEntities = [...entitiesByCommunity.entries()]
      .filter(([communityId]) => !mappedCommunityIds.has(communityId) && communityId !== 'unassigned')
      .flatMap(([, members]) => members)
      .sort((left, right) => right.importance - left.importance || right.degree - left.degree);
    unassignedEntities.forEach((node, index) => {
      const angle = Math.PI * 0.1 + (index / Math.max(1, unassignedEntities.length)) * Math.PI * 0.8;
      positions.set(
        node.id,
        polarPoint(rootX, communityY + (stableOverview ? 250 : 210), (compactOverview ? 220 : stableOverview ? 260 : 190) + Math.floor(index / 10) * 44, angle)
      );
    });
  } else if (model.mode === 'community-focus') {
    const rootCommunity = communityNodes[0] || null;
    if (rootCommunity) positions.set(rootCommunity.id, { x: 0, y: -10 });

    entityNodes.forEach((node, index) => {
      const ringIndex = Math.floor(index / 12);
      const slotIndex = index % 12;
      const ringSize = Math.min(12, entityNodes.length - ringIndex * 12);
      const angle = -Math.PI / 2 + (slotIndex / Math.max(1, ringSize)) * Math.PI * 2;
      const radius = 110 + ringIndex * 54;
      positions.set(node.id, polarPoint(0, 0, radius, angle));
    });

    otherNodes.forEach((node, index) => {
      positions.set(node.id, polarPoint(0, 0, 250 + Math.floor(index / 8) * 40, (index % 8) / 8 * Math.PI * 2));
    });
  }

  return positions;
};

const nodeStyleOf = (node: GraphRenderNode, model: GraphRenderModel, labelIds: Set<string>) => ({
  size: UNIFORM_NODE_SIZE,
  r: UNIFORM_NODE_SIZE / 2,
  fill: node.color,
  fillOpacity: 1,
  stroke: node.color,
  strokeOpacity: 1,
  opacity: 1,
  lineWidth: 1,
  labelText: shouldShowNodeLabel(node, model, labelIds) ? compactNodeLabel(node.label) : '',
  labelFill: '#ffffff',
  labelFontSize: 11,
  labelWordWrap: true,
  labelWordWrapWidth: 56,
  labelMaxLines: 1,
  labelPlacement: 'center' as const,
});

const buildGraphData = (model: GraphRenderModel): GraphData => {
  const labelIds = buildVisibleLabelIds(model);
  const presetPositions = buildPresetPositions(model);
  const nodes: NodeData[] = model.nodes.map((node) => ({
    id: node.id,
    type: 'circle',
    data: {
      ...node,
      size: UNIFORM_NODE_SIZE,
      cluster: node.communityId || node.id,
      nodeSize: UNIFORM_NODE_SIZE,
    },
    style: {
      ...nodeStyleOf(node, model, labelIds),
      x: presetPositions.get(node.id)?.x,
      y: presetPositions.get(node.id)?.y,
    },
  }));

  const edges: EdgeData[] = model.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    data: edge,
    style: edgeStyleOf(edge, model.mode),
  }));

  return { nodes, edges };
};


type StaticOverviewProps = {
  model: GraphRenderModel;
  className?: string;
  selectedNodeId?: string | null;
  selectedEdgeId?: string | null;
  queryHitNodeIds?: string[];
  onSelectNode?: (nodeId: string | null) => void;
  onSelectEdge?: (edgeId: string | null) => void;
  onHoverNode?: (nodeId: string | null) => void;
  onHoverEdge?: (edgeId: string | null) => void;
};

const buildStaticOverviewScene = (model: GraphRenderModel, width: number, height: number) => {
  const presetPositions = buildPresetPositions(model);
  const fallbackX = width / 2;
  const fallbackY = height / 2;
  const rawNodes = model.nodes.map((node) => ({
    node,
    x: presetPositions.get(node.id)?.x ?? fallbackX,
    y: presetPositions.get(node.id)?.y ?? fallbackY,
  }));

  if (!rawNodes.length) return { nodes: [], edges: [] };

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  rawNodes.forEach(({ x, y }) => {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  });

  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  const padding = 72;
  const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY, 1.0);
  const offsetX = (width - spanX * scale) / 2 - minX * scale;
  const verticalAlign = model.mode === 'overview' ? 0.18 : 0.5;
  const offsetY = (height - spanY * scale) * verticalAlign - minY * scale;

  const nodes = rawNodes.map(({ node, x, y }) => ({
    ...node,
    x: x * scale + offsetX,
    y: y * scale + offsetY,
    radius: 20,
    shortLabel: compactNodeLabel(node.label),
  }));

  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const edges = model.edges
    .map((edge) => {
      const source = nodesById.get(edge.source);
      const target = nodesById.get(edge.target);
      if (!source || !target) return null;
      const style = edgeStyleOf(edge, model.mode);
      return {
        ...edge,
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
        stroke: String(style.stroke || '#94a3b8'),
        opacity: Number(style.opacity ?? 0.72),
        lineWidth: Number(style.lineWidth ?? 1.2),
      };
    })
    .filter(Boolean);

  return { nodes, edges };
};

const Module4GraphStaticOverview: React.FC<StaticOverviewProps> = ({
  model,
  className,
  selectedNodeId,
  selectedEdgeId,
  queryHitNodeIds = [],
  onSelectNode,
  onSelectEdge,
  onHoverNode,
  onHoverEdge,
}) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: GRAPH_DEFAULT_WIDTH, height: GRAPH_DEFAULT_HEIGHT });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const sync = () => {
      setSize({
        width: Math.max(GRAPH_MIN_WIDTH, Math.floor(host.clientWidth || GRAPH_DEFAULT_WIDTH)),
        height: Math.max(GRAPH_MIN_HEIGHT, Math.floor(host.clientHeight || GRAPH_DEFAULT_HEIGHT)),
      });
    };
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  const scene = useMemo(() => buildStaticOverviewScene(model, size.width, size.height), [model, size.width, size.height]);
  const neighborhoodIndex = useMemo(() => buildNeighborhoodIndex(model.nodes, model.edges), [model.nodes, model.edges]);
  const queryHitNodeSet = useMemo(() => new Set(queryHitNodeIds.map((id) => String(id))), [queryHitNodeIds]);
  const queryFilterEnabled = queryHitNodeSet.size > 0;
  const activeNodeIds = useMemo(() => {
    const focusId = hoveredNodeId || selectedNodeId || null;
    if (!focusId) return null;
    return new Set<string>([focusId, ...(neighborhoodIndex.neighbors.get(focusId) || new Set<string>())]);
  }, [hoveredNodeId, neighborhoodIndex.neighbors, selectedNodeId]);
  const activeEdgeIds = useMemo(() => {
    const focusId = hoveredNodeId || selectedNodeId || null;
    if (!focusId) return null;
    return new Set<string>([...(neighborhoodIndex.edgeIdsByNode.get(focusId) || new Set<string>())]);
  }, [hoveredNodeId, neighborhoodIndex.edgeIdsByNode, selectedNodeId]);

  return (
    <div ref={hostRef} className={`relative h-full w-full overflow-hidden ${className || ''}`}>
      <svg className="h-full w-full" viewBox={`0 0 ${size.width} ${size.height}`} preserveAspectRatio="xMidYMid meet">
        <g>
          {scene.edges.map((edge) => (
            <line
              key={edge.id}
              x1={edge.x1}
              y1={edge.y1}
              x2={edge.x2}
              y2={edge.y2}
              stroke={edge.stroke}
              strokeOpacity={
                selectedEdgeId && selectedEdgeId !== edge.id
                  ? 0.18
                  : activeEdgeIds && !activeEdgeIds.has(edge.id)
                    ? 0.12
                    : queryFilterEnabled && !(queryHitNodeSet.has(edge.source) || queryHitNodeSet.has(edge.target))
                      ? 0.08
                    : edge.opacity
              }
              strokeWidth={selectedEdgeId === edge.id ? edge.lineWidth + 1.2 : edge.lineWidth}
              onClick={() => {
                onSelectNode?.(null);
                onSelectEdge?.(edge.id);
              }}
              onMouseEnter={() => onHoverEdge?.(edge.id)}
              onMouseLeave={() => onHoverEdge?.(null)}
            />
          ))}
        </g>
        <g>
          {scene.nodes.map((node) => {
            const dimmed = Boolean(
              (activeNodeIds && !activeNodeIds.has(node.id)) || (queryFilterEnabled && !queryHitNodeSet.has(node.id))
            );
            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onMouseEnter={() => {
                  setHoveredNodeId(node.id);
                  onHoverEdge?.(null);
                  onHoverNode?.(node.id);
                }}
                onMouseLeave={() => {
                  setHoveredNodeId((current) => (current === node.id ? null : current));
                  onHoverNode?.(null);
                }}
                onClick={() => {
                  onSelectEdge?.(null);
                  onSelectNode?.(node.id);
                }}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  r={node.radius}
                  fill={node.color}
                  fillOpacity={dimmed ? 0.28 : 0.98}
                  stroke={selectedNodeId === node.id || hoveredNodeId === node.id ? '#0f172a' : node.color}
                  strokeWidth={selectedNodeId === node.id || hoveredNodeId === node.id ? 2.6 : 1}
                />
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="#ffffff"
                  fontSize={node.kind === 'community' ? 12 : 11}
                  fontWeight={600}
                  style={{ pointerEvents: 'none' }}
                >
                  {node.shortLabel}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
};

const buildNeighborhoodIndex = (nodes: GraphRenderNode[], edges: GraphRenderEdge[]) => {
  const neighbors = new Map<string, Set<string>>();
  const edgeIdsByNode = new Map<string, Set<string>>();

  nodes.forEach((node) => {
    neighbors.set(node.id, new Set());
    edgeIdsByNode.set(node.id, new Set());
  });

  edges.forEach((edge) => {
    neighbors.get(edge.source)?.add(edge.target);
    neighbors.get(edge.target)?.add(edge.source);
    edgeIdsByNode.get(edge.source)?.add(edge.id);
    edgeIdsByNode.get(edge.target)?.add(edge.id);
  });

  return { neighbors, edgeIdsByNode };
};

const datumIdOfEvent = (event: any) => {
  const data = event?.target?.__data__;
  if (data?.id) return String(data.id);
  if (event?.target?.context?.element?.id) return String(event.target.context.element.id);
  if (event?.target?.config?.id) return String(event.target.config.id);
  if (event?.target?.attributes?.id) return String(event.target.attributes.id);
  if (event?.target?.id) return String(event.target.id);
  if (event?.item?.id) return String(event.item.id);
  return '';
};

const isGraphUsable = (graph: Graph | null) => {
  if (!graph) return false;
  const candidate = graph as Graph & { destroyed?: boolean };
  return candidate.destroyed !== true;
};

const layoutConfigForModel = (model: GraphRenderModel, width: number, height: number) => {
  if (usesStableOverviewLayout(model)) {
    return null;
  }

  if (model.mode === 'overview' || model.mode === 'community-focus') {
    return {
      type: 'd3-force' as const,
      animation: false,
      preventOverlap: true,
      center: {
        x: width / 2,
        y: height / 2,
        strength: 0.16,
      },
      centerStrength: 0.16,
      nodeStrength: model.mode === 'overview' ? -45 : -65,
      edgeStrength: (datum: any) => {
        const styleToken = String(datum?.data?.styleToken || 'primary');
        if (styleToken === 'membership') return 0.85;
        if (styleToken === 'report') return 0.22;
        if (styleToken === 'evidence') return 0.18;
        return 0.42;
      },
      linkDistance: (datum: any) => {
        const styleToken = String(datum?.data?.styleToken || 'primary');
        if (styleToken === 'membership') return model.mode === 'overview' ? 88 : 76;
        if (styleToken === 'report') return 96;
        if (styleToken === 'evidence') return 112;
        return model.mode === 'overview' ? 126 : 104;
      },
      clustering: true,
      clusterBy: (node: any) => String(node?.data?.cluster || node?.data?.communityId || node?.id || ''),
      clusterNodeStrength: model.mode === 'overview' ? -18 : -12,
      clusterEdgeStrength: 0.2,
      clusterEdgeDistance: model.mode === 'overview' ? 84 : 72,
      clusterNodeSize: NODE_COLLISION_RADIUS + 2,
      clusterFociStrength: model.mode === 'overview' ? 0.96 : 0.92,
      iterations: model.mode === 'overview' ? 220 : 180,
      manyBody: {
        strength: model.mode === 'overview' ? -56 : -72,
        distanceMin: 40,
        distanceMax: 280,
      },
      collide: {
        radius: () => NODE_COLLISION_RADIUS + 2,
        strength: 1,
        iterations: 2,
      },
      link: {
        distance: (datum: any) => {
          const styleToken = String(datum?.data?.styleToken || 'primary');
          if (styleToken === 'membership') return model.mode === 'overview' ? 88 : 76;
          if (styleToken === 'report') return 96;
          if (styleToken === 'evidence') return 112;
          return model.mode === 'overview' ? 126 : 104;
        },
      },
    };
  }

  return {
    type: 'd3-force' as const,
    animation: false,
    preventOverlap: true,
    collideStrength: 1,
    collideIterations: 2,
    center: {
      x: width / 2,
      y: height / 2,
      strength: 0.08,
    },
    centerStrength: 0.08,
    nodeStrength: -205,
    edgeStrength: (datum: any) => {
      const styleToken = String(datum?.data?.styleToken || 'primary');
      if (styleToken === 'membership') return 0.48;
      if (styleToken === 'report') return 0.28;
      if (styleToken === 'evidence') return 0.2;
      return 0.12;
    },
    linkDistance: (datum: any) => {
      const styleToken = String(datum?.data?.styleToken || 'primary');
      if (styleToken === 'membership') return 68;
      if (styleToken === 'report') return 82;
      if (styleToken === 'evidence') return 94;
      return 138;
    },
    clustering: true,
    clusterBy: (node: any) => String(node?.data?.cluster || node?.data?.communityId || node?.id || ''),
    clusterNodeStrength: -8,
    clusterEdgeStrength: 0.08,
    clusterEdgeDistance: 120,
    clusterNodeSize: NODE_COLLISION_RADIUS,
    clusterFociStrength: 0.92,
    iterations: 300,
    manyBody: {
      strength: -235,
      distanceMin: 24,
      distanceMax: 420,
    },
    collide: {
      radius: () => NODE_COLLISION_RADIUS,
      strength: 1,
      iterations: 2,
    },
    link: {
      distance: (datum: any) => {
        const styleToken = String(datum?.data?.styleToken || 'primary');
        if (styleToken === 'membership') return 68;
        if (styleToken === 'report') return 82;
        if (styleToken === 'evidence') return 94;
        return 138;
      },
    },
  };
};

export const Module4GraphCanvasG6: React.FC<Module4GraphCanvasG6Props> = ({
  model,
  className,
  selectedNodeId,
  selectedEdgeId,
  queryHitNodeIds = [],
  onSelectNode,
  onSelectEdge,
  onHoverNode,
  onHoverEdge,
}) => {
  if (usesStableOverviewLayout(model)) {
    return (
      <Module4GraphStaticOverview
        model={model}
        className={className}
        selectedNodeId={selectedNodeId}
        selectedEdgeId={selectedEdgeId}
        queryHitNodeIds={queryHitNodeIds}
        onSelectNode={onSelectNode}
        onSelectEdge={onSelectEdge}
        onHoverNode={onHoverNode}
        onHoverEdge={onHoverEdge}
      />
    );
  }

  const hostRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const modelRef = useRef(model);
  const neighborhoodRef = useRef(buildNeighborhoodIndex(model.nodes, model.edges));
  const onSelectNodeRef = useRef(onSelectNode);
  const onSelectEdgeRef = useRef(onSelectEdge);
  const onHoverNodeRef = useRef(onHoverNode);
  const onHoverEdgeRef = useRef(onHoverEdge);
  const selectedNodeIdRef = useRef<string | null>(selectedNodeId || null);
  const selectedEdgeIdRef = useRef<string | null>(selectedEdgeId || null);
  const queryHitNodeSetRef = useRef<Set<string>>(new Set((queryHitNodeIds || []).map((id) => String(id))));
  const hoveredNodeIdRef = useRef<string | null>(null);
  const hoveredEdgeIdRef = useRef<string | null>(null);
  const [tooltip, setTooltip] = useState({
    visible: false,
    x: 0,
    y: 0,
    title: '',
    subtitle: '',
    detail: '',
  });

  const graphData = useMemo(() => buildGraphData(model), [model]);
  const neighborhoodIndex = useMemo(() => buildNeighborhoodIndex(model.nodes, model.edges), [model.nodes, model.edges]);

  useEffect(() => {
    modelRef.current = model;
    neighborhoodRef.current = neighborhoodIndex;
  }, [model, neighborhoodIndex]);

  useEffect(() => {
    onSelectNodeRef.current = onSelectNode;
  }, [onSelectNode]);

  useEffect(() => {
    onSelectEdgeRef.current = onSelectEdge;
  }, [onSelectEdge]);

  useEffect(() => {
    onHoverNodeRef.current = onHoverNode;
  }, [onHoverNode]);

  useEffect(() => {
    onHoverEdgeRef.current = onHoverEdge;
  }, [onHoverEdge]);

  useEffect(() => {
    selectedNodeIdRef.current = selectedNodeId || null;
  }, [selectedNodeId]);

  useEffect(() => {
    selectedEdgeIdRef.current = selectedEdgeId || null;
  }, [selectedEdgeId]);

  useEffect(() => {
    queryHitNodeSetRef.current = new Set((queryHitNodeIds || []).map((id) => String(id)));
  }, [queryHitNodeIds]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let observer: ResizeObserver | null = null;
    let graph: Graph | null = null;
    let lastWidth = 0;
    let lastHeight = 0;
    setTooltip((previous) => ({ ...previous, visible: false }));

    const applyPersistentElementState = () => {
      if (!graph) return;
      const stateByElement: Record<string, string[]> = {};
      const currentModel = modelRef.current;
      const currentSelectedNodeId = selectedNodeIdRef.current;
      const currentSelectedEdgeId = selectedEdgeIdRef.current;
      const queryHitSet = queryHitNodeSetRef.current;
      const queryFilterEnabled = queryHitSet.size > 0;

      currentModel.nodes.forEach((node) => {
        const states: string[] = [];
        if (queryFilterEnabled) {
          states.push(queryHitSet.has(node.id) ? 'query_hit' : 'query_dimmed');
        }
        if (currentSelectedNodeId === node.id) {
          states.push('selected');
        }
        stateByElement[node.id] = states;
      });

      currentModel.edges.forEach((edge) => {
        const states: string[] = [];
        if (queryFilterEnabled) {
          const relatedToHitNode = queryHitSet.has(edge.source) || queryHitSet.has(edge.target);
          states.push(relatedToHitNode ? 'query_hit' : 'query_dimmed');
        }
        if (currentSelectedEdgeId === edge.id) {
          states.push('selected');
        }
        stateByElement[edge.id] = states;
      });

      void graph.setElementState(stateByElement, false);
    };

    const onNodeClick = (event: any) => {
      const nodeId = datumIdOfEvent(event) || hoveredNodeIdRef.current || '';
      if (!nodeId) return;
      onSelectEdgeRef.current?.(null);
      onSelectNodeRef.current?.(nodeId);
    };

    const onEdgeClick = (event: any) => {
      const edgeId = datumIdOfEvent(event) || hoveredEdgeIdRef.current || '';
      if (!edgeId) return;
      onSelectNodeRef.current?.(null);
      onSelectEdgeRef.current?.(edgeId);
    };

    const onEdgeEnter = (event: any) => {
      const edgeId = datumIdOfEvent(event);
      if (!edgeId) return;
      hoveredEdgeIdRef.current = edgeId;
      onHoverNodeRef.current?.(null);
      onHoverEdgeRef.current?.(edgeId);
      const edge = modelRef.current.edges.find((item) => item.id === edgeId);
      if (!edge) return;
      const point = event?.canvas || event?.viewport || { x: 0, y: 0 };
      const aggregateCount = Number(asRecord(edge.meta).aggregate_count || 0);
      const aggregateText = isAggregatedEdge(edge) ? ` | 聚合数=${aggregateCount}` : '';
      setTooltip({
        visible: true,
        x: Number(point.x || 0),
        y: Number(point.y || 0),
        title: edge.label,
        subtitle: `权重=${edge.weight.toFixed(2)} | 置信度=${edge.strength.toFixed(2)}${aggregateText}`,
        detail: String(asRecord(edge.meta).relation_label_zh || asRecord(edge.meta).relation_type || ''),
      });
    };

    const onEdgeLeave = () => {
      hoveredEdgeIdRef.current = null;
      onHoverEdgeRef.current?.(null);
      setTooltip((previous) => ({ ...previous, visible: false }));
    };

    const onCanvasClick = () => {
      onSelectNodeRef.current?.(null);
      onSelectEdgeRef.current?.(null);
      onHoverNodeRef.current?.(null);
      onHoverEdgeRef.current?.(null);
      setTooltip((previous) => ({ ...previous, visible: false }));
    };

    const onPointerUp = () => {
      if (hoveredNodeIdRef.current) {
        onSelectEdgeRef.current?.(null);
        onSelectNodeRef.current?.(hoveredNodeIdRef.current);
        return;
      }
      if (hoveredEdgeIdRef.current) {
        onSelectNodeRef.current?.(null);
        onSelectEdgeRef.current?.(hoveredEdgeIdRef.current);
      }
    };

    const onNodeEnter = (event: any) => {
      const hoverId = datumIdOfEvent(event);
      if (!hoverId || !graph) return;
      hoveredNodeIdRef.current = hoverId;
      onHoverEdgeRef.current?.(null);
      onHoverNodeRef.current?.(hoverId);

      const stateByElement: Record<string, string[]> = {};
      const neighborhood = neighborhoodRef.current;
      const currentModel = modelRef.current;
      const hoveredNode = currentModel.nodes.find((node) => node.id === hoverId) || null;
      const prioritizeAggregate = Boolean(hoveredNode && hoveredNode.kind === 'community');
      const activeNodes = new Set<string>([hoverId, ...(neighborhood.neighbors.get(hoverId) || new Set<string>())]);
      const activeEdges = neighborhood.edgeIdsByNode.get(hoverId) || new Set<string>();

      currentModel.nodes.forEach((node) => {
        if (activeNodes.has(node.id)) {
          stateByElement[node.id] = node.id === hoverId ? ['hovered', 'active'] : ['active'];
        } else {
          stateByElement[node.id] = ['dimmed'];
        }
      });

      currentModel.edges.forEach((edge) => {
        if (activeEdges.has(edge.id)) {
          const aggregate = isAggregatedEdge(edge);
          stateByElement[edge.id] = prioritizeAggregate && aggregate ? ['aggregate_active'] : ['active'];
        } else {
          stateByElement[edge.id] = ['dimmed'];
        }
      });

      if (hoveredNode) {
        const point = event?.canvas || event?.viewport || { x: 0, y: 0 };
        const meta = asRecord(hoveredNode.meta);
        const typeLabel = String(meta.node_type_label || hoveredNode.kind || '');
        const clusterLabel = cleanSemanticLabel(String(meta.cluster_label || ''));
        const detailParts = [
          typeLabel ? `类型：${typeLabel}` : '',
          `连接度：${hoveredNode.degree}`,
          hoveredNode.kind !== 'community' && clusterLabel ? `归属：${clusterLabel}` : '',
        ].filter(Boolean);
        setTooltip({
          visible: true,
          x: Number(point.x || 0),
          y: Number(point.y || 0),
          title: hoveredNode.label,
          subtitle: detailParts.join(' | '),
          detail: String(meta.node_type_key || ''),
        });
      }

      void graph.setElementState(stateByElement, false);
    };

    const onNodeLeave = () => {
      if (!graph) return;
      hoveredNodeIdRef.current = null;
      onHoverNodeRef.current?.(null);
      setTooltip((previous) => ({ ...previous, visible: false }));
      applyPersistentElementState();
    };

    const timer = window.setTimeout(() => {
      if (disposed) return;

      const width = Math.max(host.clientWidth || GRAPH_DEFAULT_WIDTH, GRAPH_MIN_WIDTH);
      const height = Math.max(host.clientHeight || GRAPH_DEFAULT_HEIGHT, GRAPH_MIN_HEIGHT);
      lastWidth = width;
      lastHeight = height;

      const layout = layoutConfigForModel(modelRef.current, width, height);

      graph = new Graph({
        container: host,
        width,
        height,
        data: graphData,
        node: {
          state: {
            hovered: { halo: true, haloStroke: '#93c5fd', haloLineWidth: 10, haloOpacity: 0.3 },
            active: { stroke: '#0f172a', lineWidth: 1.5 },
            selected: { stroke: '#0f172a', lineWidth: 2.5 },
            dimmed: { opacity: 0.24 },
            query_hit: { opacity: 1 },
            query_dimmed: { opacity: 0.14 },
          },
        },
        edge: {
          type: 'line',
          state: {
            active: { stroke: '#475569', opacity: 0.96 },
            dimmed: { opacity: 0.18 },
            selected: { stroke: '#0f172a', opacity: 0.96, lineWidth: 2.2 },
            aggregate_active: { stroke: '#475569', opacity: 0.78, lineWidth: 3.2 },
            query_hit: { opacity: 0.88 },
            query_dimmed: { opacity: 0.12 },
          },
        },
        ...(layout ? { layout } : {}),
        behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element'],
      });

      graphRef.current = graph;
      graph.on(NodeEvent.CLICK, onNodeClick);
      graph.on(NodeEvent.POINTER_UP, onNodeClick);
      graph.on(EdgeEvent.CLICK, onEdgeClick);
      graph.on(EdgeEvent.POINTER_UP, onEdgeClick);
      graph.on(EdgeEvent.POINTER_ENTER, onEdgeEnter);
      graph.on(EdgeEvent.POINTER_LEAVE, onEdgeLeave);
      graph.on(CanvasEvent.CLICK, onCanvasClick);
      graph.on(CommonEvent.POINTER_UP, onPointerUp);
      graph.on(NodeEvent.POINTER_ENTER, onNodeEnter);
      graph.on(NodeEvent.POINTER_LEAVE, onNodeLeave);

      observer = new ResizeObserver(() => {
        const nextWidth = host.clientWidth;
        const nextHeight = host.clientHeight;
        if (
          nextWidth > 0 &&
          nextHeight > 0 &&
          isGraphUsable(graph) &&
          (Math.abs(nextWidth - lastWidth) > 1 || Math.abs(nextHeight - lastHeight) > 1)
        ) {
          lastWidth = nextWidth;
          lastHeight = nextHeight;
          graph.resize(nextWidth, nextHeight);
        }
      });
      observer.observe(host);

      Promise.resolve(graph.render())
        .then(() => {
          if (!disposed && isGraphUsable(graph)) {
            const zoomableGraph = graph as Graph & {
              getZoom?: () => number;
              zoomTo?: (ratio: number, animation?: boolean, origin?: { x: number; y: number }) => Promise<void> | void;
            };
            const stableOverview = usesStableOverviewLayout(modelRef.current);
            if (stableOverview) {
              const fitResult = graph.fitView();
              const capStableZoom = () => {
                const currentZoom = typeof zoomableGraph.getZoom === 'function' ? zoomableGraph.getZoom() : 1;
                if (currentZoom < 0.88 && typeof zoomableGraph.zoomTo === 'function') {
                  return zoomableGraph.zoomTo?.(0.88, false, { x: width / 2, y: height / 2 });
                }
                if (currentZoom > 1.02 && typeof zoomableGraph.zoomTo === 'function') {
                  return zoomableGraph.zoomTo?.(1.02, false, { x: width / 2, y: height / 2 });
                }
                return undefined;
              };
              return Promise.resolve(fitResult).then(() => {
                applyPersistentElementState();
                return capStableZoom();
              });
            }
            const minZoom = MIN_AUTO_FIT_ZOOM;
            const fitResult = graph.fitView();
            const capZoom = () => {
              const currentZoom = typeof zoomableGraph.getZoom === 'function' ? zoomableGraph.getZoom() : 1;
              if (currentZoom < minZoom && typeof zoomableGraph.zoomTo === 'function') {
                return zoomableGraph.zoomTo?.(minZoom, false, { x: width / 2, y: height / 2 });
              }
              if (currentZoom > MAX_AUTO_FIT_ZOOM && typeof zoomableGraph.zoomTo === 'function') {
                return zoomableGraph.zoomTo?.(MAX_AUTO_FIT_ZOOM, false, { x: width / 2, y: height / 2 });
              }
              return undefined;
            };
            return Promise.resolve(fitResult).then(() => {
              applyPersistentElementState();
              return capZoom();
            });
          }
          return undefined;
        })
        .catch(() => {
          if (!disposed) setTooltip((previous) => ({ ...previous, visible: false }));
        });
    }, 0);

    return () => {
      disposed = true;
      onHoverNodeRef.current?.(null);
      onHoverEdgeRef.current?.(null);
      window.clearTimeout(timer);
      observer?.disconnect();
      graph?.off(NodeEvent.CLICK, onNodeClick);
      graph?.off(NodeEvent.POINTER_UP, onNodeClick);
      graph?.off(EdgeEvent.CLICK, onEdgeClick);
      graph?.off(EdgeEvent.POINTER_UP, onEdgeClick);
      graph?.off(EdgeEvent.POINTER_ENTER, onEdgeEnter);
      graph?.off(EdgeEvent.POINTER_LEAVE, onEdgeLeave);
      graph?.off(CanvasEvent.CLICK, onCanvasClick);
      graph?.off(CommonEvent.POINTER_UP, onPointerUp);
      graph?.off(NodeEvent.POINTER_ENTER, onNodeEnter);
      graph?.off(NodeEvent.POINTER_LEAVE, onNodeLeave);
      if (graphRef.current === graph) graphRef.current = null;
      if (isGraphUsable(graph)) graph.destroy();
    };
  }, [graphData]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!isGraphUsable(graph)) return;

    const queryHitSet = new Set((queryHitNodeIds || []).map((id) => String(id)));
    const queryFilterEnabled = queryHitSet.size > 0;
    const stateByElement: Record<string, string[]> = {};
    model.nodes.forEach((node) => {
      const states: string[] = [];
      if (queryFilterEnabled) states.push(queryHitSet.has(node.id) ? 'query_hit' : 'query_dimmed');
      if (selectedNodeId === node.id) states.push('selected');
      stateByElement[node.id] = states;
    });
    model.edges.forEach((edge) => {
      const states: string[] = [];
      if (queryFilterEnabled) {
        const relatedToHitNode = queryHitSet.has(edge.source) || queryHitSet.has(edge.target);
        states.push(relatedToHitNode ? 'query_hit' : 'query_dimmed');
      }
      if (selectedEdgeId === edge.id) states.push('selected');
      stateByElement[edge.id] = states;
    });
    void graph.setElementState(stateByElement, false);
  }, [model.edges, model.nodes, queryHitNodeIds, selectedEdgeId, selectedNodeId]);

  return (
    <div className="relative h-full w-full">
      <div ref={hostRef} className={className} />
      {tooltip.visible ? (
        <div
          className="pointer-events-none absolute z-20 min-w-[180px] rounded-md border border-slate-200 bg-white/95 px-2 py-1.5 text-[11px] text-slate-700 shadow-md dark:border-slate-700 dark:bg-slate-900/95 dark:text-slate-200"
          style={{ left: tooltip.x + 10, top: tooltip.y + 10 }}
        >
          <div className="font-semibold">{tooltip.title}</div>
          <div className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400">{tooltip.subtitle}</div>
          {tooltip.detail ? <div className="mt-0.5 text-[10px] text-slate-400 dark:text-slate-500">{tooltip.detail}</div> : null}
        </div>
      ) : null}
    </div>
  );
};

