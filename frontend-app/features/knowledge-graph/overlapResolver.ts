import { clamp } from './utils';

export type OverlapLayoutNode = {
  id: string;
  x: number;
  y: number;
  radius: number;
  anchorX: number;
  anchorY: number;
  zoneKey: string;
  fixed?: boolean;
  isRoot?: boolean;
};

type ResolveOverlapOptions = {
  iterations?: number;
  intraZoneGap?: number;
  interZoneGap?: number;
};

type WorkingNode = OverlapLayoutNode & {
  baseX: number;
  baseY: number;
};

const applyPairwiseSeparation = (
  left: WorkingNode,
  right: WorkingNode,
  intraZoneGap: number,
  interZoneGap: number
) => {
  const deltaX = right.x - left.x;
  const deltaY = right.y - left.y;
  const distance = Math.max(0.001, Math.hypot(deltaX, deltaY));
  const sameZone = left.zoneKey === right.zoneKey;
  const padding = sameZone ? intraZoneGap : interZoneGap;
  const minimumDistance = left.radius + right.radius + padding;
  if (distance >= minimumDistance) return;

  const overlap = minimumDistance - distance;
  const pushX = (deltaX / distance) * overlap;
  const pushY = (deltaY / distance) * overlap;

  if (left.fixed && right.fixed) return;
  if (left.fixed) {
    right.x += pushX;
    right.y += pushY;
    return;
  }
  if (right.fixed) {
    left.x -= pushX;
    left.y -= pushY;
    return;
  }

  left.x -= pushX * 0.5;
  left.y -= pushY * 0.5;
  right.x += pushX * 0.5;
  right.y += pushY * 0.5;
};

const applyAnchorRelaxation = (node: WorkingNode, iterationProgress: number) => {
  if (node.fixed || node.isRoot) return;

  const anchorPull = 0.028 + iterationProgress * 0.02;
  const basePull = 0.072 - iterationProgress * 0.022;
  node.x += (node.anchorX - node.x) * anchorPull;
  node.y += (node.anchorY - node.y) * anchorPull;
  node.x += (node.baseX - node.x) * basePull;
  node.y += (node.baseY - node.y) * basePull;

  const maxOffsetX = Math.max(72, Math.abs(node.anchorX - node.baseX) * 1.18 + 92);
  const maxOffsetY = Math.max(64, Math.abs(node.anchorY - node.baseY) * 1.18 + 86);
  node.x = clamp(node.x, node.anchorX - maxOffsetX, node.anchorX + maxOffsetX);
  node.y = clamp(node.y, node.anchorY - maxOffsetY, node.anchorY + maxOffsetY);
};

export const resolveGraphNodeOverlaps = (
  nodes: OverlapLayoutNode[],
  options: ResolveOverlapOptions = {}
) => {
  const iterations = Math.max(12, options.iterations ?? 28);
  const intraZoneGap = Math.max(8, options.intraZoneGap ?? 14);
  const interZoneGap = Math.max(6, options.interZoneGap ?? 10);
  const workingNodes: WorkingNode[] = nodes.map((node) => ({
    ...node,
    baseX: node.x,
    baseY: node.y,
  }));

  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const progress = iteration / Math.max(1, iterations - 1);

    for (let leftIndex = 0; leftIndex < workingNodes.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < workingNodes.length; rightIndex += 1) {
        applyPairwiseSeparation(
          workingNodes[leftIndex],
          workingNodes[rightIndex],
          intraZoneGap,
          interZoneGap
        );
      }
    }

    workingNodes.forEach((node) => applyAnchorRelaxation(node, progress));
  }

  return new Map(
    workingNodes.map((node) => [
      node.id,
      {
        x: node.x,
        y: node.y,
      },
    ])
  );
};
