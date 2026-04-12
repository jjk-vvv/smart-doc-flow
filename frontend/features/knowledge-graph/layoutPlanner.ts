import type { Module4GraphEdge, Module4GraphNode } from '../../shared/api/knowledgeGraph';
import { asRecord, buildDegreeMap, clamp, firstText, normalizeTypeKey } from './utils';

export type SemanticZoneKey =
  | 'root'
  | 'context'
  | 'analysis'
  | 'evidence'
  | 'structure'
  | 'alert';

export type SemanticPlacement = {
  zoneKey: SemanticZoneKey;
  x: number;
  y: number;
  anchorX: number;
  anchorY: number;
};

export type SemanticZoneSpec = {
  key: SemanticZoneKey;
  label: string;
  anchorX: number;
  anchorY: number;
  depthStep: number;
  clusterGap: number;
  bandGap: number;
  baseCapacity: number;
  curveLift: number;
  anchorStrengthX: number;
  anchorStrengthY: number;
};

type SemanticClusterKey =
  | 'context-core'
  | 'context-network'
  | 'analysis-claims'
  | 'analysis-observations'
  | 'evidence-tabular'
  | 'evidence-visual'
  | 'structure-schema'
  | 'structure-fragment'
  | 'structure-other'
  | 'alert-priority'
  | 'alert-risk';

type SemanticClusterSpec = {
  key: SemanticClusterKey;
  zoneKey: Exclude<SemanticZoneKey, 'root'>;
  order: number;
  depthBias: number;
  gapScale: number;
  spreadScale: number;
  capacityScale: number;
};

const ROOT_ZONE_SPEC: SemanticZoneSpec = {
  key: 'root',
  label: 'Document Root',
  anchorX: 0,
  anchorY: 0,
  depthStep: 0,
  clusterGap: 0,
  bandGap: 0,
  baseCapacity: 1,
  curveLift: 0,
  anchorStrengthX: 0.16,
  anchorStrengthY: 0.16,
};

export const SEMANTIC_ZONE_SPECS: Record<Exclude<SemanticZoneKey, 'root'>, SemanticZoneSpec> = {
  context: {
    key: 'context',
    label: 'Context',
    anchorX: -292,
    anchorY: -166,
    depthStep: 108,
    clusterGap: 112,
    bandGap: 42,
    baseCapacity: 3,
    curveLift: 18,
    anchorStrengthX: 0.126,
    anchorStrengthY: 0.108,
  },
  analysis: {
    key: 'analysis',
    label: 'Analysis',
    anchorX: 286,
    anchorY: -152,
    depthStep: 104,
    clusterGap: 110,
    bandGap: 40,
    baseCapacity: 3,
    curveLift: 16,
    anchorStrengthX: 0.118,
    anchorStrengthY: 0.106,
  },
  evidence: {
    key: 'evidence',
    label: 'Evidence',
    anchorX: 364,
    anchorY: 120,
    depthStep: 96,
    clusterGap: 102,
    bandGap: 36,
    baseCapacity: 3,
    curveLift: 12,
    anchorStrengthX: 0.108,
    anchorStrengthY: 0.106,
  },
  structure: {
    key: 'structure',
    label: 'Structure',
    anchorX: -248,
    anchorY: 188,
    depthStep: 92,
    clusterGap: 98,
    bandGap: 34,
    baseCapacity: 4,
    curveLift: 10,
    anchorStrengthX: 0.118,
    anchorStrengthY: 0.102,
  },
  alert: {
    key: 'alert',
    label: 'Alerts',
    anchorX: 128,
    anchorY: -314,
    depthStep: 82,
    clusterGap: 86,
    bandGap: 28,
    baseCapacity: 2,
    curveLift: 8,
    anchorStrengthX: 0.138,
    anchorStrengthY: 0.128,
  },
};

const SEMANTIC_CLUSTER_SPECS: Record<SemanticClusterKey, SemanticClusterSpec> = {
  'context-core': {
    key: 'context-core',
    zoneKey: 'context',
    order: 0,
    depthBias: 0.92,
    gapScale: 0.9,
    spreadScale: 0.94,
    capacityScale: 1,
  },
  'context-network': {
    key: 'context-network',
    zoneKey: 'context',
    order: 1,
    depthBias: 1.06,
    gapScale: 1.04,
    spreadScale: 1.04,
    capacityScale: 1.12,
  },
  'analysis-claims': {
    key: 'analysis-claims',
    zoneKey: 'analysis',
    order: 0,
    depthBias: 0.9,
    gapScale: 0.92,
    spreadScale: 0.9,
    capacityScale: 0.98,
  },
  'analysis-observations': {
    key: 'analysis-observations',
    zoneKey: 'analysis',
    order: 1,
    depthBias: 1.04,
    gapScale: 1.02,
    spreadScale: 1.02,
    capacityScale: 1.08,
  },
  'evidence-tabular': {
    key: 'evidence-tabular',
    zoneKey: 'evidence',
    order: 0,
    depthBias: 0.94,
    gapScale: 0.92,
    spreadScale: 0.94,
    capacityScale: 1,
  },
  'evidence-visual': {
    key: 'evidence-visual',
    zoneKey: 'evidence',
    order: 1,
    depthBias: 1.08,
    gapScale: 1.02,
    spreadScale: 1.06,
    capacityScale: 1.08,
  },
  'structure-schema': {
    key: 'structure-schema',
    zoneKey: 'structure',
    order: 0,
    depthBias: 0.92,
    gapScale: 0.92,
    spreadScale: 0.92,
    capacityScale: 1,
  },
  'structure-fragment': {
    key: 'structure-fragment',
    zoneKey: 'structure',
    order: 1,
    depthBias: 1.04,
    gapScale: 1.02,
    spreadScale: 1.08,
    capacityScale: 1.15,
  },
  'structure-other': {
    key: 'structure-other',
    zoneKey: 'structure',
    order: 2,
    depthBias: 1.1,
    gapScale: 1.08,
    spreadScale: 1.12,
    capacityScale: 1.18,
  },
  'alert-priority': {
    key: 'alert-priority',
    zoneKey: 'alert',
    order: 0,
    depthBias: 0.9,
    gapScale: 0.92,
    spreadScale: 0.9,
    capacityScale: 1,
  },
  'alert-risk': {
    key: 'alert-risk',
    zoneKey: 'alert',
    order: 1,
    depthBias: 1.02,
    gapScale: 1,
    spreadScale: 1,
    capacityScale: 1.06,
  },
};

const buildAdjacencyMap = (edges: Module4GraphEdge[]) => {
  const adjacencyMap = new Map<string, Set<string>>();
  edges.forEach((edge) => {
    const sourceNeighbors = adjacencyMap.get(edge.source_node_id) || new Set<string>();
    sourceNeighbors.add(edge.target_node_id);
    adjacencyMap.set(edge.source_node_id, sourceNeighbors);

    const targetNeighbors = adjacencyMap.get(edge.target_node_id) || new Set<string>();
    targetNeighbors.add(edge.source_node_id);
    adjacencyMap.set(edge.target_node_id, targetNeighbors);
  });
  return adjacencyMap;
};

const buildRootDistanceMap = (rootNodeId: string, adjacencyMap: Map<string, Set<string>>) => {
  const distances = new Map<string, number>();
  if (!rootNodeId) return distances;

  const queue: string[] = [rootNodeId];
  distances.set(rootNodeId, 0);

  while (queue.length > 0) {
    const currentId = queue.shift() || '';
    const currentDistance = distances.get(currentId) || 0;
    const neighbors = adjacencyMap.get(currentId) || new Set<string>();
    neighbors.forEach((neighborId) => {
      if (distances.has(neighborId)) return;
      distances.set(neighborId, currentDistance + 1);
      queue.push(neighborId);
    });
  }

  return distances;
};

const zonePriorityOfType = (typeKey: string) => {
  if (typeKey === 'document') return 0;
  if (typeKey === 'business_context') return 1;
  if (typeKey === 'topic') return 2;
  if (typeKey === 'community') return 3;
  if (typeKey === 'entity') return 4;
  if (typeKey === 'claim') return 5;
  if (typeKey === 'observation') return 6;
  if (typeKey === 'business_alert') return 7;
  if (typeKey === 'risk') return 8;
  if (typeKey === 'table') return 9;
  if (typeKey === 'figure' || typeKey === 'image') return 10;
  if (typeKey === 'field') return 11;
  if (typeKey === 'chunk') return 12;
  return 13;
};

const displayLabelOf = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  return String(
    firstText(node.display_name, attrs.title, attrs.name, node.canonical_key, node.node_id) || node.node_id,
  ).trim();
};

const pickRootNodeId = (nodes: Module4GraphNode[], degreeMap: Map<string, number>) => {
  const documentNode = nodes.find((node) => normalizeTypeKey(node.node_type) === 'document');
  if (documentNode) return documentNode.node_id;

  return [...nodes]
    .sort((left, right) => {
      const degreeDiff = (degreeMap.get(right.node_id) || 0) - (degreeMap.get(left.node_id) || 0);
      if (degreeDiff !== 0) return degreeDiff;
      const typeDiff =
        zonePriorityOfType(normalizeTypeKey(left.node_type)) -
        zonePriorityOfType(normalizeTypeKey(right.node_type));
      if (typeDiff !== 0) return typeDiff;
      return displayLabelOf(left).localeCompare(displayLabelOf(right), 'zh-CN');
    })[0]?.node_id;
};

export const semanticZoneOfNode = (node: Module4GraphNode, rootNodeId = ''): SemanticZoneKey => {
  const typeKey = normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
  if (node.node_id === rootNodeId || typeKey === 'document') return 'root';
  if (typeKey === 'business_alert' || typeKey === 'risk') return 'alert';
  if (typeKey === 'table' || typeKey === 'figure' || typeKey === 'image') return 'evidence';
  if (typeKey === 'claim' || typeKey === 'observation') return 'analysis';
  if (typeKey === 'business_context' || typeKey === 'topic' || typeKey === 'community' || typeKey === 'entity') {
    return 'context';
  }
  return 'structure';
};

const semanticClusterOfNode = (node: Module4GraphNode, rootNodeId = ''): SemanticClusterKey => {
  const typeKey = normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
  const zoneKey = semanticZoneOfNode(node, rootNodeId);

  if (zoneKey === 'context') {
    if (typeKey === 'business_context' || typeKey === 'topic') return 'context-core';
    return 'context-network';
  }

  if (zoneKey === 'analysis') {
    return typeKey === 'claim' ? 'analysis-claims' : 'analysis-observations';
  }

  if (zoneKey === 'evidence') {
    return typeKey === 'table' ? 'evidence-tabular' : 'evidence-visual';
  }

  if (zoneKey === 'alert') {
    return typeKey === 'business_alert' ? 'alert-priority' : 'alert-risk';
  }

  if (typeKey === 'field') return 'structure-schema';
  if (typeKey === 'chunk') return 'structure-fragment';
  return 'structure-other';
};

const zoneRankScore = (node: Module4GraphNode, zoneKey: SemanticZoneKey, degree: number) => {
  const typeKey = normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
  const confidence = clamp(Number(node.confidence || 0.55), 0, 1);
  const zoneBias =
    zoneKey === 'alert'
      ? typeKey === 'business_alert'
        ? 18
        : 14
      : zoneKey === 'evidence'
        ? typeKey === 'table'
          ? 13
          : 11
        : zoneKey === 'analysis'
          ? typeKey === 'claim'
            ? 13
            : 11
          : zoneKey === 'context'
            ? typeKey === 'business_context'
              ? 14
              : typeKey === 'topic'
                ? 12
                : 10
            : typeKey === 'field'
              ? 10
              : 7;
  return degree * 8.6 + confidence * 5.5 + zoneBias;
};

const zoneCapacityForBand = (
  zone: SemanticZoneSpec,
  bandIndex: number,
  capacityScale: number,
) => Math.max(2, Math.round((zone.baseCapacity + bandIndex) * capacityScale));

const anchorPointOfZone = (zone: SemanticZoneSpec) => ({
  x: zone.anchorX,
  y: zone.anchorY,
});

const branchBasisOf = (anchor: { x: number; y: number }) => {
  const distance = Math.max(1, Math.hypot(anchor.x, anchor.y));
  const radialX = anchor.x / distance;
  const radialY = anchor.y / distance;
  return {
    radialX,
    radialY,
    tangentX: -radialY,
    tangentY: radialX,
  };
};

const preferredBranchDepth = (rootDistance: number, fallback: number) =>
  Math.max(0, Math.min(3.2, (Number.isFinite(rootDistance) ? rootDistance : fallback) - 1));

export const zoneStrengthOf = (zoneKey: SemanticZoneKey) => {
  if (zoneKey === 'root') {
    return {
      x: ROOT_ZONE_SPEC.anchorStrengthX,
      y: ROOT_ZONE_SPEC.anchorStrengthY,
    };
  }
  const spec = SEMANTIC_ZONE_SPECS[zoneKey];
  return {
    x: spec.anchorStrengthX,
    y: spec.anchorStrengthY,
  };
};

export const buildSemanticSectorPositions = (
  nodes: Module4GraphNode[],
  edges: Module4GraphEdge[],
): Map<string, SemanticPlacement> => {
  const placements = new Map<string, SemanticPlacement>();
  if (nodes.length === 0) return placements;

  const degreeMap = buildDegreeMap(nodes, edges);
  const adjacencyMap = buildAdjacencyMap(edges);
  const rootNodeId = pickRootNodeId(nodes, degreeMap) || nodes[0]?.node_id || '';
  const rootDistanceMap = buildRootDistanceMap(rootNodeId, adjacencyMap);

  placements.set(rootNodeId, {
    zoneKey: 'root',
    x: 0,
    y: 0,
    anchorX: 0,
    anchorY: 0,
  });

  const zoneBuckets = new Map<Exclude<SemanticZoneKey, 'root'>, Map<SemanticClusterKey, Module4GraphNode[]>>();
  (Object.keys(SEMANTIC_ZONE_SPECS) as Array<Exclude<SemanticZoneKey, 'root'>>).forEach((key) => {
    zoneBuckets.set(key, new Map<SemanticClusterKey, Module4GraphNode[]>());
  });

  nodes.forEach((node) => {
    if (node.node_id === rootNodeId) return;
    const zoneKey = semanticZoneOfNode(node, rootNodeId);
    if (zoneKey === 'root') return;
    const clusterKey = semanticClusterOfNode(node, rootNodeId);
    const zoneBucket = zoneBuckets.get(zoneKey) || new Map<SemanticClusterKey, Module4GraphNode[]>();
    const clusterBucket = zoneBucket.get(clusterKey) || [];
    clusterBucket.push(node);
    zoneBucket.set(clusterKey, clusterBucket);
    zoneBuckets.set(zoneKey, zoneBucket);
  });

  (Object.entries(SEMANTIC_ZONE_SPECS) as Array<[Exclude<SemanticZoneKey, 'root'>, SemanticZoneSpec]>).forEach(
    ([zoneKey, zone]) => {
      const clusterBuckets = zoneBuckets.get(zoneKey) || new Map<SemanticClusterKey, Module4GraphNode[]>();
      const activeClusters = [...clusterBuckets.entries()]
        .filter(([, bucket]) => bucket.length > 0)
        .sort(
          ([leftKey], [rightKey]) =>
            SEMANTIC_CLUSTER_SPECS[leftKey].order - SEMANTIC_CLUSTER_SPECS[rightKey].order,
        );
      if (!activeClusters.length) return;

      const anchor = anchorPointOfZone(zone);
      const basis = branchBasisOf(anchor);
      const midClusterIndex = (activeClusters.length - 1) / 2;

      activeClusters.forEach(([clusterKey, bucket], clusterIndex) => {
        const clusterSpec = SEMANTIC_CLUSTER_SPECS[clusterKey];
        const clusterBandOffset = (clusterIndex - midClusterIndex) * zone.clusterGap * clusterSpec.gapScale;
        const sortedBucket = [...bucket].sort((left, right) => {
          const leftDegree = degreeMap.get(left.node_id) || 0;
          const rightDegree = degreeMap.get(right.node_id) || 0;
          const leftDepth = rootDistanceMap.get(left.node_id) ?? Number.POSITIVE_INFINITY;
          const rightDepth = rootDistanceMap.get(right.node_id) ?? Number.POSITIVE_INFINITY;
          if (leftDepth !== rightDepth) return leftDepth - rightDepth;

          const leftScore = zoneRankScore(left, zoneKey, leftDegree);
          const rightScore = zoneRankScore(right, zoneKey, rightDegree);
          if (rightScore !== leftScore) return rightScore - leftScore;

          const typeDiff =
            zonePriorityOfType(normalizeTypeKey(left.node_type || left.type_label || left.category)) -
            zonePriorityOfType(normalizeTypeKey(right.node_type || right.type_label || right.category));
          if (typeDiff !== 0) return typeDiff;
          return displayLabelOf(left).localeCompare(displayLabelOf(right), 'zh-CN');
        });

        let consumed = 0;
        let bandIndex = 0;

        while (consumed < sortedBucket.length) {
          const bandCapacity = zoneCapacityForBand(zone, bandIndex, clusterSpec.capacityScale);
          const bandNodes = sortedBucket.slice(consumed, consumed + bandCapacity);
          const bandMid = (bandNodes.length - 1) / 2;

          bandNodes.forEach((node, itemIndex) => {
            const degree = degreeMap.get(node.node_id) || 0;
            const rootDistance = rootDistanceMap.get(node.node_id) ?? bandIndex + 1;
            const depthBias = preferredBranchDepth(rootDistance, bandIndex + 1);
            const depthDistance =
              bandIndex * zone.depthStep +
              depthBias * zone.depthStep * 0.28 +
              (clusterSpec.depthBias - 1) * zone.depthStep * 0.7;
            const lateralOffset = clusterBandOffset + (itemIndex - bandMid) * zone.bandGap * clusterSpec.spreadScale;
            const curveOffset = Math.sign(lateralOffset || 1) * Math.min(Math.abs(lateralOffset) * 0.16, zone.curveLift);
            const priorityDrift = clamp((zoneRankScore(node, zoneKey, degree) - 12) * 0.22, -8, 14);

            const x =
              anchor.x +
              basis.radialX * (depthDistance + priorityDrift * 0.4 + Math.abs(curveOffset) * 0.12) +
              basis.tangentX * lateralOffset;
            const y =
              anchor.y +
              basis.radialY * (depthDistance + priorityDrift * 0.4 + Math.abs(curveOffset) * 0.12) +
              basis.tangentY * lateralOffset +
              basis.radialY * curveOffset * 0.32;

            placements.set(node.node_id, {
              zoneKey,
              x,
              y,
              anchorX: anchor.x,
              anchorY: anchor.y,
            });
          });

          consumed += bandNodes.length;
          bandIndex += 1;
        }
      });
    },
  );

  nodes.forEach((node) => {
    if (placements.has(node.node_id)) return;
    placements.set(node.node_id, {
      zoneKey: 'structure',
      x: -220,
      y: 224,
      anchorX: -220,
      anchorY: 224,
    });
  });

  return placements;
};
