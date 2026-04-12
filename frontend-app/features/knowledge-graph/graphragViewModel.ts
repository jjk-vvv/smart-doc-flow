export type GraphRenderMode = 'overview' | 'community-focus' | 'entity-drilldown';

export type GraphRenderNodeKind =
  | 'entity'
  | 'community'
  | 'report'
  | 'document'
  | 'text_unit'
  | 'artifact'
  | 'covariate';

export type GraphRenderNodeRole = 'hub' | 'member' | 'summary' | 'evidence';

export type GraphRenderEdgeKind = 'related_to' | 'in_community' | 'has_report' | 'evidence' | 'other';

export type GraphRenderEdgeStyleToken = 'primary' | 'membership' | 'report' | 'evidence' | 'muted';

export type GraphRenderNode = {
  id: string;
  rawNodeId: string;
  label: string;
  kind: GraphRenderNodeKind;
  role: GraphRenderNodeRole;
  communityId?: string | null;
  communityLevel?: number | null;
  degree: number;
  importance: number;
  size: number;
  color: string;
  visibleInOverview: boolean;
  visibleInFocus: boolean;
  visibleInDrilldown: boolean;
  collapsedByDefault: boolean;
  meta: Record<string, unknown>;
};

export type GraphRenderEdge = {
  id: string;
  rawEdgeId?: string;
  source: string;
  target: string;
  kind: GraphRenderEdgeKind;
  label: string;
  weight: number;
  strength: number;
  visibleInOverview: boolean;
  visibleInFocus: boolean;
  visibleInDrilldown: boolean;
  styleToken: GraphRenderEdgeStyleToken;
  meta: Record<string, unknown>;
};

export type GraphRenderCommunity = {
  id: string;
  label: string;
  level: number;
  entityCount: number;
  reportNodeId?: string | null;
  color: string;
  importance: number;
};

export type GraphRenderModel = {
  mode: GraphRenderMode;
  root?: {
    fileHash?: string;
    communityId?: string;
    entityId?: string;
  };
  nodes: GraphRenderNode[];
  edges: GraphRenderEdge[];
  communities: GraphRenderCommunity[];
  stats: {
    rawNodeCount: number;
    rawEdgeCount: number;
    renderedNodeCount: number;
    renderedEdgeCount: number;
    hiddenEvidenceNodeCount: number;
    hiddenEvidenceEdgeCount: number;
  };
};

