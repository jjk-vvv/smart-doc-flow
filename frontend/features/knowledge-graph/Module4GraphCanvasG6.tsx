import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CanvasEvent, CommonEvent, EdgeEvent, Graph, NodeEvent, type EdgeData, type GraphData, type NodeData } from '@antv/g6';
import type { GraphRenderEdge, GraphRenderModel, GraphRenderNode } from './graphragViewModel';

export type GraphLabelMode = 'compact' | 'full';

type Module4GraphCanvasG6Props = {
  model: GraphRenderModel;
  className?: string;
  selectedNodeId?: string | null;
  selectedEdgeId?: string | null;
  queryHitNodeIds?: string[];
  labelMode?: GraphLabelMode;
  onSelectNode?: (nodeId: string | null) => void;
  onSelectEdge?: (edgeId: string | null) => void;
};

const UNIFORM_NODE_SIZE = 22;
const NODE_COLLISION_RADIUS = 16;
// Keep the graph fully visible after fitView. Forcing zoom-in (>1) can push
// large graphs outside viewport and looks like "flash then disappear".
const MIN_AUTO_FIT_ZOOM = 0.24;
const MAX_AUTO_FIT_ZOOM = 1.0;
const SMALL_GRAPH_NODE_THRESHOLD = 12;
const SMALL_GRAPH_EDGE_THRESHOLD = 16;
const LABEL_COLLISION_GAP = 8;
const GRAPH_DEFAULT_WIDTH = 1280;
const GRAPH_DEFAULT_HEIGHT = 420;
const STABLE_OVERVIEW_NODE_THRESHOLD = 1500;
const STABLE_OVERVIEW_EDGE_THRESHOLD = 4000;
// Keep the graph responsive to narrow canvases inside split layouts. A large
// hard minimum width causes the graph to render off-screen in module4 panels.
const GRAPH_MIN_WIDTH = 360;
const GRAPH_MIN_HEIGHT = 260;
const VISIBLE_NODE_PALETTE = ['#6f42c1', '#0ea5e9', '#f59e0b', '#ef4444', '#10b981', '#3b82f6', '#f97316', '#14b8a6'];

type LabelSide = 'right' | 'left';

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
  model.mode === 'overview' &&
  (model.nodes.length >= STABLE_OVERVIEW_NODE_THRESHOLD || model.edges.length >= STABLE_OVERVIEW_EDGE_THRESHOLD);

const cleanSemanticLabel = (value: string) =>
  String(value || '')
    .replace(/[A-Za-z_]{4,24}$/, '')
    .trim();

const fullNodeLabel = (value: string) => {
  const normalized = cleanSemanticLabel(String(value || ''));
  if (!normalized) return '节点';
  return normalized;
};

const wrapFullLabel = (value: string, lineChars = 10) => {
  const normalized = fullNodeLabel(value);
  if (normalized.length <= lineChars) return normalized;
  const lines: string[] = [];
  for (let index = 0; index < normalized.length; index += lineChars) {
    lines.push(normalized.slice(index, index + lineChars));
  }
  return lines.join('\n');
};

const hashColorIndex = (value: string) => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash % VISIBLE_NODE_PALETTE.length;
};

const hashScalar = (value: string, salt = 0) => {
  let hash = (2166136261 ^ salt) >>> 0;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
};

const parseColorToRgb = (value: string): [number, number, number] | null => {
  const normalized = String(value || '').trim().toLowerCase();
  if (!normalized) return null;

  const hex = normalized.replace('#', '');
  if (/^[0-9a-f]{3}$/i.test(hex)) {
    const r = Number.parseInt(hex[0] + hex[0], 16);
    const g = Number.parseInt(hex[1] + hex[1], 16);
    const b = Number.parseInt(hex[2] + hex[2], 16);
    return [r, g, b];
  }
  if (/^[0-9a-f]{6}$/i.test(hex)) {
    const r = Number.parseInt(hex.slice(0, 2), 16);
    const g = Number.parseInt(hex.slice(2, 4), 16);
    const b = Number.parseInt(hex.slice(4, 6), 16);
    return [r, g, b];
  }
  const rgbMatch = normalized.match(/^rgba?\(([^)]+)\)$/i);
  if (rgbMatch) {
    const [rRaw, gRaw, bRaw] = rgbMatch[1].split(',').map((item) => Number.parseFloat(item.trim()));
    if ([rRaw, gRaw, bRaw].every((item) => Number.isFinite(item))) {
      const clamp = (value: number) => Math.max(0, Math.min(255, Math.round(value)));
      return [clamp(rRaw), clamp(gRaw), clamp(bRaw)];
    }
  }
  return null;
};

const relativeLuminance = (rgb: [number, number, number]) => {
  const channel = (value: number) => {
    const normalized = value / 255;
    return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = rgb;
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
};

const normalizedNodeFill = (rawColor: string, seed: string) => {
  const rgb = parseColorToRgb(rawColor);
  if (!rgb) return VISIBLE_NODE_PALETTE[hashColorIndex(seed)];
  const luminance = relativeLuminance(rgb);
  if (luminance >= 0.85) return VISIBLE_NODE_PALETTE[hashColorIndex(seed)];
  return rawColor;
};

const nodeLabelFill = (fillColor: string) => {
  const rgb = parseColorToRgb(fillColor);
  if (!rgb) return '#ffffff';
  return relativeLuminance(rgb) >= 0.62 ? '#0f172a' : '#ffffff';
};

const aggregatedEdgeLabel = (edge: GraphRenderEdge) => {
  const meta = asRecord(edge.meta);
  const count = Math.max(1, Math.floor(toNumber(meta.aggregate_count, 1)));
  const totalWeight = Number(edge.weight || 0).toFixed(1);
  return `跨社区关联（${count}）权重 ${totalWeight}`;
};

const edgeStyleOf = (edge: GraphRenderEdge, mode: GraphRenderModel['mode']) => {
  const aggregated = isAggregatedEdge(edge);
  const shouldShowAggregateLabel = false;
  const showEdgeLabel = mode !== 'overview' && edge.styleToken !== 'membership';

  if (edge.styleToken === 'membership') {
    return {
      stroke: '#d9e2ee',
      lineWidth: 0.85,
      opacity: 0.34,
      endArrow: false,
      labelText: '',
    };
  }

  if (edge.styleToken === 'report') {
    return {
      stroke: '#d2dbe7',
      lineWidth: 0.85,
      opacity: 0.3,
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
      stroke: '#c7d2e2',
      lineWidth: Math.max(1, Math.min(1.8, 0.9 + edge.weight * 0.03)),
      opacity: 0.28,
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
      stroke: '#d8e0eb',
      lineWidth: 0.8,
      opacity: 0.28,
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
    stroke: '#c9d3e3',
    lineWidth: Math.max(0.8, Math.min(1.4, 0.8 + edge.weight * 0.06)),
    opacity: 0.34,
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

const shouldShowNodeLabel = (node: GraphRenderNode, _model: GraphRenderModel, labelIds: Set<string>) =>
  labelIds.has(node.id);

const labelPriority = (node: GraphRenderNode) => {
  const overviewRole = String(asRecord(node.meta).overview_role || '');
  const roleBoost =
    node.kind === 'community'
      ? 1200
      : node.kind === 'report'
        ? 1000
        : overviewRole === 'bridge_entity'
          ? 920
          : overviewRole === 'core_entity'
            ? 860
            : node.kind === 'entity'
              ? 760
              : 640;
  return roleBoost + node.importance * 12 + node.degree * 8;
};

const labelLayoutMetrics = (node: GraphRenderNode, model: GraphRenderModel) => {
  const overview = model.mode === 'overview';
  const labelFontSize = node.kind === 'community' ? 12 : 11;
  const labelText = overview ? wrapFullLabel(node.label, 9) : fullNodeLabel(node.label);
  const lines = labelText.split('\n').filter(Boolean);
  const lineCount = Math.max(1, lines.length);
  const maxLineLength = lines.reduce((max, line) => Math.max(max, line.length), 0);
  const labelWidth = Math.max(18, Math.round(maxLineLength * labelFontSize * 0.6) + 10);
  const labelHeight = lineCount * labelFontSize + Math.max(0, lineCount - 1) * 2 + 6;
  return { labelText, labelFontSize, labelWidth, labelHeight };
};

const meanX = (positionById: Map<string, { x: number; y: number }>) => {
  if (!positionById.size) return 0;
  let total = 0;
  positionById.forEach((position) => {
    total += position.x;
  });
  return total / positionById.size;
};

const buildLabelSideById = (
  model: GraphRenderModel,
  positionById: Map<string, { x: number; y: number }>,
  centerX = 0
) => {
  const sideById = new Map<string, LabelSide>();
  model.nodes.forEach((node) => {
    const position = positionById.get(node.id);
    if (!position) return;
    const side: LabelSide = position.x >= centerX ? 'right' : 'left';
    sideById.set(node.id, side);
  });
  return sideById;
};

const boxesOverlap = (
  left: { x: number; y: number; width: number; height: number },
  right: { x: number; y: number; width: number; height: number }
) =>
  !(
    left.x + left.width + LABEL_COLLISION_GAP <= right.x ||
    right.x + right.width + LABEL_COLLISION_GAP <= left.x ||
    left.y + left.height + LABEL_COLLISION_GAP <= right.y ||
    right.y + right.height + LABEL_COLLISION_GAP <= left.y
  );

const suppressOverlappedLabels = (
  model: GraphRenderModel,
  candidateIds: Set<string>,
  positionById: Map<string, { x: number; y: number }>,
  labelSideById: Map<string, LabelSide>
) => {
  if (model.mode !== 'overview' || candidateIds.size <= 1) return candidateIds;

  const accepted = new Set<string>();
  const placedBoxes: Array<{ x: number; y: number; width: number; height: number }> = [];
  const orderedNodes = model.nodes
    .filter((node) => candidateIds.has(node.id))
    .sort((left, right) => {
      const delta = labelPriority(right) - labelPriority(left);
      if (delta !== 0) return delta;
      return left.label.localeCompare(right.label, 'zh-CN');
    });

  orderedNodes.forEach((node) => {
    const position = positionById.get(node.id);
    if (!position) {
      accepted.add(node.id);
      return;
    }
    const metrics = labelLayoutMetrics(node, model);
    const side = labelSideById.get(node.id) || 'right';
    const labelAnchorX =
      side === 'right'
        ? position.x + UNIFORM_NODE_SIZE / 2 + 8
        : position.x - UNIFORM_NODE_SIZE / 2 - 8 - metrics.labelWidth;
    const bbox = {
      x: labelAnchorX - 2,
      y: position.y - metrics.labelHeight / 2 - 2,
      width: metrics.labelWidth + 4,
      height: metrics.labelHeight + 4,
    };
    if (placedBoxes.some((existing) => boxesOverlap(existing, bbox))) return;
    accepted.add(node.id);
    placedBoxes.push(bbox);
  });

  return accepted;
};

const buildVisibleLabelIds = (
  model: GraphRenderModel,
  labelMode: GraphLabelMode,
  positionById?: Map<string, { x: number; y: number }>,
  labelSideById: Map<string, LabelSide> = new Map()
) => {
  const ids = new Set<string>();
  if (model.nodes.length <= 24 || labelMode === 'full') {
    model.nodes.forEach((node) => ids.add(node.id));
    if (!positionById) return ids;
    return suppressOverlappedLabels(model, ids, positionById, labelSideById);
  }

  model.nodes.forEach((node) => {
    if (node.kind === 'community' || node.kind === 'document') {
      ids.add(node.id);
    }
  });

  const reportLabelLimit =
    model.mode === 'overview'
      ? model.nodes.length > 320
        ? 4
        : model.nodes.length > 240
          ? 6
          : model.nodes.length > 160
            ? 8
            : model.nodes.length > 100
              ? 10
              : 12
      : 8;
  model.nodes
    .filter((node) => node.kind === 'report')
    .sort((left, right) => labelPriority(right) - labelPriority(left) || left.label.localeCompare(right.label, 'zh-CN'))
    .slice(0, reportLabelLimit)
    .forEach((node) => ids.add(node.id));

  const entityLabelLimit =
    model.mode === 'overview'
      ? model.nodes.length > 360
        ? 10
        : model.nodes.length > 280
          ? 14
          : model.nodes.length > 200
            ? 18
            : model.nodes.length > 140
              ? 24
              : 32
      : 24;
  model.nodes
    .filter((node) => node.kind === 'entity')
    .sort((left, right) => {
      const leftRole = String(asRecord(left.meta).overview_role || '');
      const rightRole = String(asRecord(right.meta).overview_role || '');
      const leftBonus = leftRole === 'bridge_entity' ? 1000 : leftRole === 'core_entity' ? 800 : 0;
      const rightBonus = rightRole === 'bridge_entity' ? 1000 : rightRole === 'core_entity' ? 800 : 0;
      const scoreDelta = rightBonus + right.importance + right.degree - (leftBonus + left.importance + left.degree);
      if (scoreDelta !== 0) return scoreDelta;
      return left.label.localeCompare(right.label, 'zh-CN');
    })
    .slice(0, entityLabelLimit)
    .forEach((node) => ids.add(node.id));

  if (!positionById) return ids;
  return suppressOverlappedLabels(model, ids, positionById, labelSideById);
};

const buildPositionMapFromGraph = (graph: Graph, model: GraphRenderModel) => {
  const positionById = new Map<string, { x: number; y: number }>();
  model.nodes.forEach((node) => {
    try {
      const position = graph.getElementPosition(node.id) as { x?: number; y?: number };
      const x = Number(position?.x);
      const y = Number(position?.y);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        positionById.set(node.id, { x, y });
      }
    } catch {
      // Ignore transient lookup failures while layout is settling.
    }
  });
  return positionById;
};

const buildPostLayoutNodeLabelUpdates = (graph: Graph, model: GraphRenderModel, labelMode: GraphLabelMode) => {
  if (!model.nodes.length) return [];
  const positionById = buildPositionMapFromGraph(graph, model);
  const centerX = meanX(positionById);
  const labelSideById = buildLabelSideById(model, positionById, centerX);
  const visibleLabelIds = buildVisibleLabelIds(model, labelMode, positionById, labelSideById);
  return model.nodes.map((node) => {
    const metrics = labelLayoutMetrics(node, model);
    const side = labelSideById.get(node.id) || 'right';
    return {
      id: node.id,
      style: {
        labelText: visibleLabelIds.has(node.id) ? metrics.labelText : '',
        labelPlacement: (model.mode === 'overview' ? side : 'center') as any,
        labelOffset: model.mode === 'overview' ? 8 : 0,
      },
    };
  });
};

const polarPoint = (centerX: number, centerY: number, radius: number, angle: number) => ({
  x: centerX + Math.cos(angle) * radius,
  y: centerY + Math.sin(angle) * radius,
});

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

const phyllotaxisPoint = (
  index: number,
  spacing: number,
  centerX: number,
  centerY: number,
  angleOffset = -Math.PI / 2
) => {
  const radius = spacing * Math.sqrt(index + 0.65);
  const angle = index * GOLDEN_ANGLE + angleOffset;
  return {
    x: centerX + Math.cos(angle) * radius,
    y: centerY + Math.sin(angle) * radius,
  };
};

const isBridgeOverviewEntity = (node: GraphRenderNode) =>
  node.kind === 'entity' && String(asRecord(node.meta).overview_role || '') === 'bridge_entity';

const relaxNodeOverlaps = ({
  model,
  positions,
  minDistance,
  iterations,
}: {
  model: GraphRenderModel;
  positions: Map<string, { x: number; y: number }>;
  minDistance: number;
  iterations: number;
}) => {
  const relaxed = new Map<string, { x: number; y: number }>();
  positions.forEach((point, id) => {
    relaxed.set(id, { x: Number(point.x || 0), y: Number(point.y || 0) });
  });

  const nodeById = new Map(model.nodes.map((node) => [node.id, node] as const));
  const nodeIds = model.nodes.map((node) => node.id).filter((id) => relaxed.has(id));
  if (nodeIds.length <= 1) return relaxed;

  const anchoredNodeIds = new Set(
    model.nodes
      .filter((node) => node.kind === 'community' || node.kind === 'document')
      .map((node) => node.id)
  );

  for (let pass = 0; pass < iterations; pass += 1) {
    let moved = false;
    for (let leftIndex = 0; leftIndex < nodeIds.length - 1; leftIndex += 1) {
      const leftId = nodeIds[leftIndex];
      const leftPoint = relaxed.get(leftId);
      const leftNode = nodeById.get(leftId);
      if (!leftPoint || !leftNode) continue;
      for (let rightIndex = leftIndex + 1; rightIndex < nodeIds.length; rightIndex += 1) {
        const rightId = nodeIds[rightIndex];
        const rightPoint = relaxed.get(rightId);
        const rightNode = nodeById.get(rightId);
        if (!rightPoint || !rightNode) continue;

        let dx = rightPoint.x - leftPoint.x;
        let dy = rightPoint.y - leftPoint.y;
        let distance = Math.hypot(dx, dy);
        if (distance < 1e-4) {
          dx = hashScalar(`${leftId}:${rightId}`, 191) - 0.5;
          dy = hashScalar(`${rightId}:${leftId}`, 223) - 0.5;
          distance = Math.hypot(dx, dy) || 1;
        }

        const leftCommunity = String(leftNode.communityId || '');
        const rightCommunity = String(rightNode.communityId || '');
        const sameCommunity = Boolean(leftCommunity && rightCommunity && leftCommunity === rightCommunity);
        const touchesCommunityAnchor = leftNode.kind === 'community' || rightNode.kind === 'community';
        const touchesBridge = isBridgeOverviewEntity(leftNode) || isBridgeOverviewEntity(rightNode);

        let requiredDistance = minDistance;
        if (!sameCommunity) requiredDistance += 4;
        if (touchesCommunityAnchor) requiredDistance += 8;
        if (touchesBridge) requiredDistance += 2;

        if (distance >= requiredDistance) continue;
        const overlap = requiredDistance - distance;
        const ux = dx / distance;
        const uy = dy / distance;
        const leftAnchored = anchoredNodeIds.has(leftId);
        const rightAnchored = anchoredNodeIds.has(rightId);
        if (leftAnchored && rightAnchored) continue;

        moved = true;
        if (leftAnchored && !rightAnchored) {
          rightPoint.x += ux * overlap;
          rightPoint.y += uy * overlap;
          continue;
        }
        if (!leftAnchored && rightAnchored) {
          leftPoint.x -= ux * overlap;
          leftPoint.y -= uy * overlap;
          continue;
        }
        const push = overlap / 2;
        leftPoint.x -= ux * push;
        leftPoint.y -= uy * push;
        rightPoint.x += ux * push;
        rightPoint.y += uy * push;
      }
    }

    model.nodes.forEach((node) => {
      if (anchoredNodeIds.has(node.id) || node.kind === 'community') return;
      const point = relaxed.get(node.id);
      if (!point) return;
      const anchorId = String(node.communityId || '');
      if (!anchorId) return;
      const anchorPoint = relaxed.get(anchorId);
      if (!anchorPoint) return;
      const pull = node.kind === 'report' ? 0.08 : 0.05;
      point.x += (anchorPoint.x - point.x) * pull;
      point.y += (anchorPoint.y - point.y) * pull;
    });

    if (!moved) break;
  }

  return relaxed;
};

const buildPresetPositions = (model: GraphRenderModel) => {
  const positions = new Map<string, { x: number; y: number }>();
  const documentNodes = model.nodes.filter((node) => node.kind === 'document');
  const communityNodes = model.nodes.filter((node) => node.kind === 'community');
  const entityNodes = model.nodes.filter((node) => node.kind === 'entity');
  const reportNodes = model.nodes.filter((node) => node.kind === 'report');
  const otherNodes = model.nodes.filter((node) => !['document', 'community', 'entity'].includes(node.kind));

  if (model.mode === 'overview') {
    const compactOverview = isSmallGraphModel(model);
    const stableOverview = usesStableOverviewLayout(model);
    const rootX = 0;
    const rootY = stableOverview ? -170 : -140;
    const communityY = stableOverview ? 34 : 24;

    documentNodes.forEach((node, index) => {
      positions.set(node.id, { x: rootX + index * 120, y: rootY });
    });

    if (communityNodes.length === 0) {
      const rankedEntities = [...entityNodes].sort(
        (left, right) => right.importance - left.importance || right.degree - left.degree
      );
      const centerX = rootX;
      const centerY = stableOverview ? 92 : 68;
      // No community anchors: use concentric rings instead of filled disk.
      // This keeps all nodes visible while preventing a dense "color blob".
      const baseRadius = compactOverview ? 74 : 86;
      const ringStep = compactOverview ? 28 : 32;
      const baseCapacity = compactOverview ? 24 : 30;
      let ringIndex = 0;
      let placedInCurrentRing = 0;
      let currentRingCapacity = baseCapacity;

      rankedEntities.forEach((node) => {
        const slot = placedInCurrentRing;
        const angle =
          -Math.PI / 2 +
          (slot / Math.max(1, currentRingCapacity)) * Math.PI * 2 +
          (hashScalar(node.id, 37) - 0.5) * 0.06;
        const radius = baseRadius + ringIndex * ringStep;
        positions.set(node.id, polarPoint(centerX, centerY, radius, angle));

        placedInCurrentRing += 1;
        if (placedInCurrentRing >= currentRingCapacity) {
          ringIndex += 1;
          placedInCurrentRing = 0;
          currentRingCapacity = baseCapacity + ringIndex * 12;
        }
      });

      const outerRadius = baseRadius + Math.max(1, ringIndex + 1) * ringStep + 30;
      otherNodes.forEach((node, index) => {
        const angle =
          -Math.PI / 2 +
          (index / Math.max(1, otherNodes.length)) * Math.PI * 2 +
          (hashScalar(node.id, 71) - 0.5) * 0.08;
        positions.set(node.id, polarPoint(centerX, centerY, outerRadius, angle));
      });

      return relaxNodeOverlaps({
        model,
        positions,
        minDistance: model.nodes.length >= 200 ? UNIFORM_NODE_SIZE + 5 : UNIFORM_NODE_SIZE + 7,
        iterations: model.nodes.length >= 200 ? 18 : 12,
      });
    }

    const rankedCommunities = [...communityNodes].sort(
      (left, right) => right.importance - left.importance || right.degree - left.degree
    );
    const communitySpacing = compactOverview ? 116 : stableOverview ? 146 : 128;
    rankedCommunities.forEach((node, index) => {
      positions.set(node.id, phyllotaxisPoint(index, communitySpacing, rootX, communityY));
    });

    const bridgeEntities = [...entityNodes]
      .filter((node) => isBridgeOverviewEntity(node))
      .sort((left, right) => right.importance - left.importance || right.degree - left.degree);
    const communityMemberEntities = entityNodes.filter((node) => !isBridgeOverviewEntity(node));

    if (bridgeEntities.length > 0) {
      const bridgeCenterY = stableOverview ? -52 : -36;
      const ringCapacity = compactOverview ? 10 : 14;
      const bridgeRadiusBase = compactOverview ? 84 : stableOverview ? 104 : 92;
      const bridgeRadiusStep = compactOverview ? 20 : 24;
      bridgeEntities.forEach((node, index) => {
        const ring = Math.floor(index / ringCapacity);
        const slot = index % ringCapacity;
        const ringSize = Math.min(ringCapacity, bridgeEntities.length - ring * ringCapacity);
        const angle =
          -Math.PI / 2 + (slot / Math.max(1, ringSize)) * Math.PI * 2 + (hashScalar(node.id, 109) - 0.5) * 0.14;
        const radius = bridgeRadiusBase + ring * bridgeRadiusStep + (hashScalar(node.id, 127) - 0.5) * 8;
        positions.set(node.id, polarPoint(rootX, bridgeCenterY, radius, angle));
      });
    }

    const entitiesByCommunity = new Map<string, GraphRenderNode[]>();
    communityMemberEntities.forEach((node) => {
      const key = String(node.communityId || 'unassigned');
      const current = entitiesByCommunity.get(key) || [];
      current.push(node);
      entitiesByCommunity.set(key, current);
    });

    const reportsByCommunity = new Map<string, GraphRenderNode[]>();
    reportNodes.forEach((node) => {
      const key = String(node.communityId || 'unassigned');
      const current = reportsByCommunity.get(key) || [];
      current.push(node);
      reportsByCommunity.set(key, current);
    });

    rankedCommunities.forEach((communityNode) => {
      const members = (entitiesByCommunity.get(communityNode.id) || []).sort(
        (left, right) => right.importance - left.importance || right.degree - left.degree
      );
      const center = positions.get(communityNode.id) || { x: 0, y: 0 };
      const baseRadius = compactOverview ? 42 : stableOverview ? 60 : 50;
      members.forEach((node, index) => {
        const angle = hashScalar(node.id, 31) * Math.PI * 2;
        const ringScale = Math.sqrt(hashScalar(node.id, 47));
        const rankBoost = Math.max(0, Math.floor(index / 8)) * 12;
        const radius = baseRadius + rankBoost + ringScale * 34;
        positions.set(node.id, polarPoint(center.x, center.y, radius, angle));
      });

      const reports = (reportsByCommunity.get(communityNode.id) || []).sort(
        (left, right) => right.importance - left.importance || right.degree - left.degree
      );
      reports.forEach((node, index) => {
        const spread = reports.length <= 1 ? 0 : (index - (reports.length - 1) / 2) * 0.26;
        const radius = compactOverview ? 52 : 62;
        const angle = -Math.PI / 2 + spread + (hashScalar(node.id, 73) - 0.5) * 0.16;
        positions.set(node.id, polarPoint(center.x, center.y, radius, angle));
      });
    });

    const mappedCommunityIds = new Set(rankedCommunities.map((node) => node.id));
    const unassignedEntities = [...entitiesByCommunity.entries()]
      .filter(([communityId]) => !mappedCommunityIds.has(communityId))
      .flatMap(([, members]) => members)
      .sort((left, right) => right.importance - left.importance || right.degree - left.degree);

    const haloSpacing = compactOverview ? 24 : 30;
    const haloMultiplier = compactOverview ? 2.35 : 2.85;
    unassignedEntities.forEach((node, index) => {
      const base = phyllotaxisPoint(index, haloSpacing, rootX, communityY, Math.PI / 5 + hashScalar(node.id, 91));
      positions.set(node.id, {
        x: base.x * haloMultiplier,
        y: base.y * haloMultiplier,
      });
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

  if (model.mode === 'overview') {
    return relaxNodeOverlaps({
      model,
      positions,
      minDistance: model.nodes.length >= 120 ? UNIFORM_NODE_SIZE + 6 : UNIFORM_NODE_SIZE + 9,
      iterations: model.nodes.length >= 120 ? 16 : 11,
    });
  }

  return positions;
};

const nodeStyleOf = (
  node: GraphRenderNode,
  model: GraphRenderModel,
  labelIds: Set<string>,
  labelSide: LabelSide = 'right'
) => {
  const fillColor = normalizedNodeFill(node.color, node.communityId || node.id);
  const denseGraph = model.nodes.length > 220;
  const overview = model.mode === 'overview';
  const overviewRole = String(asRecord(node.meta).overview_role || '');
  const isCommunity = node.kind === 'community';
  const isReport = node.kind === 'report';
  const isBridgeEntity = overviewRole === 'bridge_entity';
  const lineWidth = isBridgeEntity ? 1.2 : denseGraph ? 0.9 : 0.8;
  const metrics = labelLayoutMetrics(node, model);
  const labelFontSize = isCommunity ? 12 : isReport ? 11 : 11;
  const labelText = shouldShowNodeLabel(node, model, labelIds)
    ? metrics.labelText
    : '';
  return {
    size: UNIFORM_NODE_SIZE,
    r: UNIFORM_NODE_SIZE / 2,
    fill: fillColor,
    fillOpacity: isReport ? 0.96 : 1,
    stroke: fillColor,
    strokeOpacity: 1,
    opacity: 1,
    lineWidth,
    labelText,
    labelFill: overview ? '#334155' : nodeLabelFill(fillColor),
    labelFontSize,
    labelWordWrap: false,
    labelWordWrapWidth: overview ? 0 : 140,
    labelMaxLines: 0,
    labelPlacement: (overview ? labelSide : 'center') as 'right' | 'left' | 'center',
    labelOffset: overview ? 8 : 0,
    labelBackground: false,
    labelBackgroundFill: '#ffffff',
    labelBackgroundOpacity: 0,
    labelBackgroundPadding: overview ? [1, 4] : [0, 0],
  };
};

const buildGraphData = (model: GraphRenderModel, labelMode: GraphLabelMode): GraphData => {
  const presetPositions = buildPresetPositions(model);
  const rawPositionById = new Map<string, { x: number; y: number }>();
  model.nodes.forEach((node, index) => {
    if (!node?.id) return;
    const preset = presetPositions.get(node.id);
    if (preset && Number.isFinite(preset.x) && Number.isFinite(preset.y)) {
      rawPositionById.set(node.id, { x: preset.x, y: preset.y });
      return;
    }
    rawPositionById.set(node.id, phyllotaxisPoint(index, 42, 0, 0));
  });
  const labelSideById = buildLabelSideById(model, rawPositionById, 0);
  const labelIds = buildVisibleLabelIds(model, labelMode, rawPositionById, labelSideById);

  const normalizedPositionById = rawPositionById;

  const nodes: NodeData[] = [];
  const nodeIdSet = new Set<string>();
  for (const node of model.nodes) {
    if (!node || !node.id || nodeIdSet.has(node.id)) continue;
    nodeIdSet.add(node.id);
    nodes.push({
      id: node.id,
      type: 'circle',
      data: {
        ...node,
        size: UNIFORM_NODE_SIZE,
        cluster: node.communityId || node.id,
        nodeSize: UNIFORM_NODE_SIZE,
      },
      style: {
        ...nodeStyleOf(node, model, labelIds, labelSideById.get(node.id) || 'right'),
        x: normalizedPositionById.get(node.id)?.x,
        y: normalizedPositionById.get(node.id)?.y,
      },
    });
  }

  const edges: EdgeData[] = [];
  const edgeIdSet = new Set<string>();
  for (const edge of model.edges) {
    if (!edge || !edge.id || edgeIdSet.has(edge.id)) continue;
    if (!nodeIdSet.has(edge.source) || !nodeIdSet.has(edge.target)) continue;
    edgeIdSet.add(edge.id);
    edges.push({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      data: edge,
      style: edgeStyleOf(edge, model.mode),
    });
  }

  return { nodes, edges };
};


type StaticOverviewProps = {
  model: GraphRenderModel;
  className?: string;
  selectedNodeId?: string | null;
  selectedEdgeId?: string | null;
  queryHitNodeIds?: string[];
  labelMode?: GraphLabelMode;
  onSelectNode?: (nodeId: string | null) => void;
  onSelectEdge?: (edgeId: string | null) => void;
};

const staticNodeRadiusForCount = (nodeCount: number) => {
  if (nodeCount >= 120) return 10;
  if (nodeCount >= 90) return 11;
  if (nodeCount >= 70) return 12;
  if (nodeCount >= 50) return 13;
  if (nodeCount >= 32) return 15;
  return 20;
};

const estimateLabelWidth = (text: string, fontSize: number) => Math.max(22, Math.round(text.length * fontSize * 0.58));

const buildStaticOverviewScene = (model: GraphRenderModel, width: number, height: number, labelMode: GraphLabelMode) => {
  const presetPositions = buildPresetPositions(model);
  const nodeRadius = staticNodeRadiusForCount(model.nodes.length);
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
  const projectedPositionById = new Map(
    rawNodes.map(({ node, x, y }) => [node.id, { x: x * scale + offsetX, y: y * scale + offsetY }])
  );
  const projectedCenterX = width / 2;
  const labelSideById = buildLabelSideById(model, projectedPositionById, projectedCenterX);
  const labelIds = buildVisibleLabelIds(model, labelMode, projectedPositionById, labelSideById);

  const nodes = rawNodes.map(({ node, x, y }) => {
    const fillColor = normalizedNodeFill(node.color, node.communityId || node.id);
    const metrics = labelLayoutMetrics(node, model);
    const labelText = metrics.labelText;
    const labelFontSize = node.kind === 'community' ? 12 : 11;
    return {
      ...node,
      x: x * scale + offsetX,
      y: y * scale + offsetY,
      radius: nodeRadius,
      fillColor,
      labelFill: '#334155',
      labelText,
      labelFontSize,
      labelWidth: estimateLabelWidth(labelText.replace(/\n/g, ''), labelFontSize),
      labelSide: labelSideById.get(node.id) || 'right',
      showLabel: labelIds.has(node.id),
    };
  });

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
  labelMode = 'compact',
  onSelectNode,
  onSelectEdge,
}) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: GRAPH_DEFAULT_WIDTH, height: GRAPH_DEFAULT_HEIGHT });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const hostClassName = `relative h-full w-full min-h-[320px] overflow-hidden ${className || ''}`;

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

  const scene = useMemo(
    () => buildStaticOverviewScene(model, size.width, size.height, labelMode),
    [labelMode, model, size.width, size.height]
  );
  const neighborhoodIndex = useMemo(() => buildNeighborhoodIndex(model.nodes, model.edges), [model.nodes, model.edges]);
  const queryHitNodeSet = useMemo(() => new Set(queryHitNodeIds.map((id) => String(id))), [queryHitNodeIds]);
  const queryFilterEnabled = useMemo(() => hasQueryHitsInModel(model, queryHitNodeSet), [model, queryHitNodeSet]);
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
    <div ref={hostRef} className={hostClassName}>
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
                    ? 0.32
                    : queryFilterEnabled && !(queryHitNodeSet.has(edge.source) || queryHitNodeSet.has(edge.target))
                      ? 0.22
                    : edge.opacity
              }
              strokeWidth={selectedEdgeId === edge.id ? edge.lineWidth + 1.2 : edge.lineWidth}
              onClick={() => {
                onSelectNode?.(null);
                onSelectEdge?.(edge.id);
              }}
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
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId((current) => (current === node.id ? null : current))}
                onClick={() => {
                  onSelectEdge?.(null);
                  onSelectNode?.(node.id);
                }}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  r={node.radius}
                  fill={node.fillColor}
                  fillOpacity={dimmed ? 0.62 : 0.98}
                  stroke={selectedNodeId === node.id || hoveredNodeId === node.id ? '#0f172a' : node.fillColor}
                  strokeWidth={selectedNodeId === node.id || hoveredNodeId === node.id ? 2.6 : 1}
                />
                {node.showLabel ? (
                  <>
                    <rect
                      x={node.labelSide === 'right' ? node.radius + 5 : -(node.radius + 5 + node.labelWidth + 8)}
                      y={-(node.labelFontSize / 2) - 3}
                      width={node.labelWidth + 8}
                      height={node.labelFontSize + 6}
                      rx={4}
                      fill="#ffffff"
                      fillOpacity={0.82}
                      style={{ pointerEvents: 'none' }}
                    />
                    <text
                      x={node.labelSide === 'right' ? node.radius + 9 : -(node.radius + 9)}
                      y={1}
                      textAnchor={node.labelSide === 'right' ? 'start' : 'end'}
                      dominantBaseline="central"
                      fill={node.labelFill}
                      fontSize={node.labelFontSize}
                      fontWeight={600}
                      style={{ pointerEvents: 'none' }}
                    >
                      {node.labelText}
                    </text>
                  </>
                ) : null}
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

const hasQueryHitsInModel = (model: GraphRenderModel, queryHitSet: Set<string>) =>
  model.nodes.some((node) => queryHitSet.has(node.id));

const cameraZoomBoundsForModel = (model: GraphRenderModel) => {
  const deterministicOverview = model.mode === 'overview';
  const denseOverview = deterministicOverview && (model.nodes.length > 120 || model.edges.length > 260);
  const ultraDenseOverview = deterministicOverview && (model.nodes.length > 260 || model.edges.length > 700);
  const minZoom = deterministicOverview
    ? ultraDenseOverview
      ? 0.14
      : denseOverview
        ? 0.2
        : MIN_AUTO_FIT_ZOOM
    : denseOverview
      ? 0.28
      : MIN_AUTO_FIT_ZOOM;
  const maxZoom = deterministicOverview ? 0.95 : denseOverview ? 0.95 : MAX_AUTO_FIT_ZOOM;
  const severeLowZoomThreshold = Math.max(0.06, Math.min(0.12, minZoom * 0.5));
  return {
    deterministicOverview,
    denseOverview,
    ultraDenseOverview,
    minZoom,
    maxZoom,
    severeLowZoomThreshold,
  };
};

const graphDataBoundsOf = (graphData: GraphData) => {
  const nodes = Array.isArray(graphData.nodes) ? graphData.nodes : [];
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let count = 0;

  nodes.forEach((node) => {
    const style = asRecord((node as { style?: unknown }).style);
    const x = Number(style.x);
    const y = Number(style.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
    count += 1;
  });

  if (!count) return null;
  return {
    minX,
    maxX,
    minY,
    maxY,
    spanX: maxX - minX,
    spanY: maxY - minY,
    nodeCount: count,
  };
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

  if (model.mode === 'overview') {
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
      nodeStrength: -360,
      edgeStrength: (datum: any) => {
        const styleToken = String(datum?.data?.styleToken || 'primary');
        if (styleToken === 'membership') return 0.28;
        if (styleToken === 'report') return 0.16;
        if (styleToken === 'evidence') return 0.08;
        return 0.06;
      },
      linkDistance: (datum: any) => {
        const styleToken = String(datum?.data?.styleToken || 'primary');
        const aggregated = Boolean(datum?.data?.meta?.aggregated);
        if (styleToken === 'membership') return 106;
        if (styleToken === 'report') return 128;
        if (styleToken === 'evidence') return 150;
        if (aggregated) return 240;
        return 184;
      },
      clustering: true,
      clusterBy: (node: any) => String(node?.data?.cluster || node?.data?.communityId || node?.id || ''),
      clusterNodeStrength: -16,
      clusterEdgeStrength: 0.12,
      clusterEdgeDistance: 142,
      clusterNodeSize: NODE_COLLISION_RADIUS + 6,
      clusterFociStrength: 0.8,
      iterations: 320,
      manyBody: {
        strength: -360,
        distanceMin: 24,
        distanceMax: 760,
      },
      collide: {
        radius: () => NODE_COLLISION_RADIUS + 6,
        strength: 1,
        iterations: 4,
      },
      link: {
        distance: (datum: any) => {
          const styleToken = String(datum?.data?.styleToken || 'primary');
          const aggregated = Boolean(datum?.data?.meta?.aggregated);
          if (styleToken === 'membership') return 106;
          if (styleToken === 'report') return 128;
          if (styleToken === 'evidence') return 150;
          if (aggregated) return 240;
          return 184;
        },
      },
    };
  }

  if (model.mode === 'community-focus') {
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
      nodeStrength: -65,
      edgeStrength: (datum: any) => {
        const styleToken = String(datum?.data?.styleToken || 'primary');
        if (styleToken === 'membership') return 0.85;
        if (styleToken === 'report') return 0.22;
        if (styleToken === 'evidence') return 0.18;
        return 0.42;
      },
      linkDistance: (datum: any) => {
        const styleToken = String(datum?.data?.styleToken || 'primary');
        if (styleToken === 'membership') return 76;
        if (styleToken === 'report') return 96;
        if (styleToken === 'evidence') return 112;
        return 104;
      },
      clustering: true,
      clusterBy: (node: any) => String(node?.data?.cluster || node?.data?.communityId || node?.id || ''),
      clusterNodeStrength: -12,
      clusterEdgeStrength: 0.2,
      clusterEdgeDistance: 72,
      clusterNodeSize: NODE_COLLISION_RADIUS + 2,
      clusterFociStrength: 0.92,
      iterations: 180,
      manyBody: {
        strength: -72,
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

const Module4GraphCanvasG6Dynamic: React.FC<Module4GraphCanvasG6Props> = ({
  model,
  className,
  selectedNodeId,
  selectedEdgeId,
  queryHitNodeIds = [],
  labelMode = 'compact',
  onSelectNode,
  onSelectEdge,
}) => {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const modelRef = useRef(model);
  const neighborhoodRef = useRef(buildNeighborhoodIndex(model.nodes, model.edges));
  const onSelectNodeRef = useRef(onSelectNode);
  const onSelectEdgeRef = useRef(onSelectEdge);
  const selectedNodeIdRef = useRef<string | null>(selectedNodeId || null);
  const selectedEdgeIdRef = useRef<string | null>(selectedEdgeId || null);
  const queryHitNodeSetRef = useRef<Set<string>>(new Set((queryHitNodeIds || []).map((id) => String(id))));
  const labelModeRef = useRef<GraphLabelMode>(labelMode);
  const hoveredNodeIdRef = useRef<string | null>(null);
  const hoveredEdgeIdRef = useRef<string | null>(null);
  const fallbackRetryRef = useRef(0);
  const [tooltip, setTooltip] = useState({
    visible: false,
    x: 0,
    y: 0,
    title: '',
    subtitle: '',
    detail: '',
  });
  const [dynamicRenderFailed, setDynamicRenderFailed] = useState(false);

  const graphData = useMemo(() => buildGraphData(model, labelMode), [labelMode, model]);
  const graphDataBounds = useMemo(() => graphDataBoundsOf(graphData), [graphData]);
  const neighborhoodIndex = useMemo(() => buildNeighborhoodIndex(model.nodes, model.edges), [model.nodes, model.edges]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const targetWindow = window as Window & { __module4CanvasDebug?: Record<string, unknown> };
    targetWindow.__module4CanvasDebug = {
      mode: model.mode,
      modelNodeCount: model.nodes.length,
      modelEdgeCount: model.edges.length,
      graphDataNodeCount: graphData.nodes?.length || 0,
      graphDataEdgeCount: graphData.edges?.length || 0,
      stableOverviewLayout: usesStableOverviewLayout(model),
      dynamicRenderFailed,
      selectedNodeId: selectedNodeId || null,
      selectedEdgeId: selectedEdgeId || null,
      queryHitNodeCount: queryHitNodeIds.length,
      labelMode,
      graphDataBounds,
      timestamp: new Date().toISOString(),
    };
  }, [
    dynamicRenderFailed,
    graphData.edges,
    graphData.nodes,
    graphDataBounds,
    labelMode,
    model,
    queryHitNodeIds.length,
    selectedEdgeId,
    selectedNodeId,
  ]);

  useEffect(() => {
    // Reset dynamic fallback when graph payload changes.
    setDynamicRenderFailed(false);
    fallbackRetryRef.current = 0;
  }, [graphData]);

  useEffect(() => {
    if (!dynamicRenderFailed) return;
    if (fallbackRetryRef.current >= 2) return;
    const retryDelay = 1200 * (fallbackRetryRef.current + 1);
    const timer = window.setTimeout(() => {
      fallbackRetryRef.current += 1;
      setDynamicRenderFailed(false);
    }, retryDelay);
    return () => window.clearTimeout(timer);
  }, [dynamicRenderFailed]);

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
    selectedNodeIdRef.current = selectedNodeId || null;
  }, [selectedNodeId]);

  useEffect(() => {
    selectedEdgeIdRef.current = selectedEdgeId || null;
  }, [selectedEdgeId]);

  useEffect(() => {
    queryHitNodeSetRef.current = new Set((queryHitNodeIds || []).map((id) => String(id)));
  }, [queryHitNodeIds]);

  useEffect(() => {
    labelModeRef.current = labelMode;
  }, [labelMode]);

  useEffect(() => {
    if (dynamicRenderFailed) return;
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let observer: ResizeObserver | null = null;
    let graph: Graph | null = null;
    let lastWidth = 0;
    let lastHeight = 0;
    let zoomGuardTimer: number | null = null;
    setTooltip((previous) => ({ ...previous, visible: false }));

    const applyPersistentElementState = () => {
      if (!graph) return;
      const stateByElement: Record<string, string[]> = {};
      const currentModel = modelRef.current;
      const currentSelectedNodeId = selectedNodeIdRef.current;
      const currentSelectedEdgeId = selectedEdgeIdRef.current;
      const queryHitSet = queryHitNodeSetRef.current;
      const queryFilterEnabled = hasQueryHitsInModel(currentModel, queryHitSet);

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

    const applyPostLayoutLabelVisibility = async () => {
      if (!graph || !isGraphUsable(graph)) return;
      const currentModel = modelRef.current;
      if (!currentModel.nodes.length) return;
      const updates = buildPostLayoutNodeLabelUpdates(graph, currentModel, labelModeRef.current);
      if (!updates.length) return;
      try {
        graph.updateNodeData(updates);
        await graph.draw();
      } catch (error) {
        console.warn('[module4] post-layout label update skipped', error);
      }
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
      setTooltip((previous) => ({ ...previous, visible: false }));
    };

    const onCanvasClick = () => {
      onSelectNodeRef.current?.(null);
      onSelectEdgeRef.current?.(null);
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

      const stateByElement: Record<string, string[]> = {};
      const neighborhood = neighborhoodRef.current;
      const currentModel = modelRef.current;
      const hoveredNode = currentModel.nodes.find((node) => node.id === hoverId) || null;
      const prioritizeAggregate = Boolean(hoveredNode && hoveredNode.kind === 'community');
      const shouldDimForHover = currentModel.nodes.length <= 220;
      const activeNodes = new Set<string>([hoverId, ...(neighborhood.neighbors.get(hoverId) || new Set<string>())]);
      const activeEdges = neighborhood.edgeIdsByNode.get(hoverId) || new Set<string>();

      currentModel.nodes.forEach((node) => {
        if (activeNodes.has(node.id)) {
          stateByElement[node.id] = node.id === hoverId ? ['hovered', 'active'] : ['active'];
          return;
        }
        stateByElement[node.id] = shouldDimForHover ? ['dimmed'] : [];
      });

      currentModel.edges.forEach((edge) => {
        if (activeEdges.has(edge.id)) {
          const aggregate = isAggregatedEdge(edge);
          stateByElement[edge.id] = prioritizeAggregate && aggregate ? ['aggregate_active'] : ['active'];
          return;
        }
        stateByElement[edge.id] = shouldDimForHover ? ['dimmed'] : [];
      });

      if (hoveredNode) {
        const point = event?.canvas || event?.viewport || { x: 0, y: 0 };
        const meta = asRecord(hoveredNode.meta);
        const fullLabel = cleanSemanticLabel(String(meta.raw_label || hoveredNode.label || '')) || hoveredNode.label;
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
          title: fullLabel,
          subtitle: detailParts.join(' | '),
          detail: String(meta.node_type_key || ''),
        });
      }

      void graph.setElementState(stateByElement, false);
    };

    const onNodeLeave = () => {
      if (!graph) return;
      hoveredNodeIdRef.current = null;
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

      try {
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
              dimmed: { opacity: 0.62 },
              query_hit: { opacity: 1 },
              query_dimmed: { opacity: 0.28 },
            },
          },
          edge: {
            type: 'line',
            state: {
              active: { stroke: '#475569', opacity: 0.96 },
              dimmed: { opacity: 0.34 },
              selected: { stroke: '#0f172a', opacity: 0.96, lineWidth: 2.2 },
              aggregate_active: { stroke: '#475569', opacity: 0.78, lineWidth: 3.2 },
              query_hit: { opacity: 0.88 },
              query_dimmed: { opacity: 0.24 },
            },
          },
          ...(layout ? { layout } : {}),
          behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element'],
        });
      } catch (error) {
        console.warn('[module4] graph init failed, fallback to static overview', error);
        if (!disposed) setDynamicRenderFailed(true);
        return;
      }

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
          // G6 may throw synchronously or reject asynchronously during camera updates
          // while container metrics are still settling, so guard both pathways.
          void Promise.resolve()
            .then(() => graph.resize(nextWidth, nextHeight))
            .then(() => {
              if (!isGraphUsable(graph)) return;
              return Promise.resolve(graph.fitView());
            })
            .then(() => applyPostLayoutLabelVisibility())
            .then(() => applyPersistentElementState())
            .catch((error) => {
              console.warn('[module4] graph resize skipped due to transient G6 state', error);
            });
        }
      });
      observer.observe(host);

      Promise.resolve(graph.render())
        .then(async () => {
          if (disposed || !isGraphUsable(graph)) return;
          const zoomableGraph = graph as Graph & {
            getZoom?: () => number;
            zoomTo?: (ratio: number, animation?: boolean, origin?: { x: number; y: number }) => Promise<void> | void;
          };

          // Post-render camera tuning should never force fallback. Some G6 builds
          // can throw transiently during fit/zoom while data has rendered fine.
          try {
            const stableOverview = usesStableOverviewLayout(modelRef.current);
            if (stableOverview) {
              await Promise.resolve(graph.fitView());
              const currentZoom = typeof zoomableGraph.getZoom === 'function' ? zoomableGraph.getZoom() : 1;
              if (currentZoom < MIN_AUTO_FIT_ZOOM && typeof zoomableGraph.zoomTo === 'function') {
                await Promise.resolve(zoomableGraph.zoomTo?.(MIN_AUTO_FIT_ZOOM, false, { x: width / 2, y: height / 2 }));
              } else if (currentZoom > MAX_AUTO_FIT_ZOOM && typeof zoomableGraph.zoomTo === 'function') {
                await Promise.resolve(zoomableGraph.zoomTo?.(MAX_AUTO_FIT_ZOOM, false, { x: width / 2, y: height / 2 }));
              }
              applyPersistentElementState();
              return;
            }

            const currentModel = modelRef.current;
            const bounds = cameraZoomBoundsForModel(currentModel);
            await Promise.resolve(graph.fitView());
            const currentZoom = typeof zoomableGraph.getZoom === 'function' ? zoomableGraph.getZoom() : 1;
            if (currentZoom < bounds.minZoom && typeof zoomableGraph.zoomTo === 'function') {
              await Promise.resolve(zoomableGraph.zoomTo?.(bounds.minZoom, false, { x: width / 2, y: height / 2 }));
            } else if (currentZoom > bounds.maxZoom && typeof zoomableGraph.zoomTo === 'function') {
              await Promise.resolve(zoomableGraph.zoomTo?.(bounds.maxZoom, false, { x: width / 2, y: height / 2 }));
            }
            if (typeof window !== 'undefined') {
              const targetWindow = window as Window & { __module4CanvasDebug?: Record<string, unknown> };
              targetWindow.__module4CanvasDebug = {
                ...(targetWindow.__module4CanvasDebug || {}),
                camera: {
                  currentZoom,
                  minZoom: bounds.minZoom,
                  maxZoom: bounds.maxZoom,
                  deterministicOverview: bounds.deterministicOverview,
                  denseOverview: bounds.denseOverview,
                  ultraDenseOverview: bounds.ultraDenseOverview,
                  severeLowZoomThreshold: bounds.severeLowZoomThreshold,
                },
              };
            }
          } catch (error) {
            console.warn('[module4] post-render camera adjustment skipped', error);
          }

          // Guard against rare cases where zoom snaps to an extreme low value,
          // making the graph appear as "flash then disappear".
          zoomGuardTimer = window.setInterval(() => {
            if (disposed || !graph || !isGraphUsable(graph)) return;
            const zoomableGraph = graph as Graph & {
              getZoom?: () => number;
              zoomTo?: (ratio: number, animation?: boolean, origin?: { x: number; y: number }) => Promise<void> | void;
            };
            if (typeof zoomableGraph.getZoom !== 'function' || typeof zoomableGraph.zoomTo !== 'function') return;
            const currentZoom = zoomableGraph.getZoom();
            if (!Number.isFinite(currentZoom)) return;
            const currentModel = modelRef.current;
            if (currentModel.mode !== 'overview') return;
            const bounds = cameraZoomBoundsForModel(currentModel);
            if (currentZoom >= bounds.severeLowZoomThreshold) return;

            const hostWidth = Math.max(host.clientWidth || GRAPH_DEFAULT_WIDTH, GRAPH_MIN_WIDTH);
            const hostHeight = Math.max(host.clientHeight || GRAPH_DEFAULT_HEIGHT, GRAPH_MIN_HEIGHT);
            void Promise.resolve(graph.fitView())
              .then(() => Promise.resolve(zoomableGraph.zoomTo?.(bounds.minZoom, false, { x: hostWidth / 2, y: hostHeight / 2 })))
              .then(() => applyPostLayoutLabelVisibility())
              .then(() => applyPersistentElementState())
              .catch((error) => {
                console.warn('[module4] zoom guard recovery skipped', error);
              });
          }, 1200);

          await applyPostLayoutLabelVisibility();
          applyPersistentElementState();
        })
        .catch((error) => {
          console.warn('[module4] graph render failed, fallback to static overview', error);
          if (!disposed) {
            setTooltip((previous) => ({ ...previous, visible: false }));
            setDynamicRenderFailed(true);
          }
        });
    }, 0);

    return () => {
      disposed = true;
      window.clearTimeout(timer);
      if (zoomGuardTimer !== null) window.clearInterval(zoomGuardTimer);
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
  }, [dynamicRenderFailed, graphData]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!isGraphUsable(graph)) return;

    const queryHitSet = new Set((queryHitNodeIds || []).map((id) => String(id)));
    const queryFilterEnabled = hasQueryHitsInModel(model, queryHitSet);
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

  if (dynamicRenderFailed) {
    return (
      <div className="relative h-full w-full">
        <Module4GraphStaticOverview
          model={model}
          className={className}
          selectedNodeId={selectedNodeId}
          selectedEdgeId={selectedEdgeId}
          queryHitNodeIds={queryHitNodeIds}
          onSelectNode={onSelectNode}
          onSelectEdge={onSelectEdge}
        />
        <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-amber-200 bg-amber-50/90 px-2 py-1 text-[11px] text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
          动态布局异常，已自动切换稳定视图
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <div ref={hostRef} className={className ? `${className} min-h-[320px]` : 'h-full w-full min-h-[320px]'} />
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

export const Module4GraphCanvasG6: React.FC<Module4GraphCanvasG6Props> = (props) => {
  if (usesStableOverviewLayout(props.model)) {
    return <Module4GraphStaticOverview {...props} />;
  }
  return <Module4GraphCanvasG6Dynamic {...props} />;
};

