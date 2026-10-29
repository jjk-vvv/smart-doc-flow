import React, { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, Network, PanelRightClose, PanelRightOpen, RefreshCw, Search, XCircle } from 'lucide-react';
import module4Svg from '../../assets/knowledge-graph.svg';
import wordIcon from '../../assets/WORD.png';
import pdfIcon from '../../assets/pdf.png';
import txtIcon from '../../assets/txt.png';
import mdIcon from '../../assets/md.png';
import excelIcon from '../../assets/xlsx.png';
import defaultDocIcon from '../../assets/文档.png';
import {
  fetchModule4FileGraph,
  fetchModule4FileNeighborhood,
  fetchModule4Graph,
  fetchModule4GraphFiles,
  fetchModule4NodeDetail,
  searchModule4GraphRag,
  type Module4EvidenceItem,
  type Module4GraphEdge,
  type Module4GraphFileItem,
  type Module4GraphNode,
  type Module4GraphRagQueryMode,
  type Module4GraphRagQueryResponse,
  type Module4GraphResponse,
  type Module4NodeDetailResponse,
} from '../../shared/api/knowledgeGraph';
import { Module4GraphCanvasG6, type GraphLabelMode } from '../../features/knowledge-graph/Module4GraphCanvasG6';
import {
  buildGraphRAGCommunityFocusModel,
  buildGraphRAGEntityDrilldownModel,
  buildGraphRAGOverviewModel,
  type GraphRenderBuildOptions,
} from '../../features/knowledge-graph/graphragRenderAdapter';
import type { GraphRenderEdge, GraphRenderMode, GraphRenderModel, GraphRenderNode } from '../../features/knowledge-graph/graphragViewModel';
import { getActiveExtractionFileHash } from '../../features/knowledge-graph/utils';

const cn = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ');

const getFileIcon = (filename: string) => {
  if (!filename) return defaultDocIcon;
  const lowerName = filename.toLowerCase();
  if (lowerName.endsWith('.txt')) return txtIcon;
  if (lowerName.endsWith('.md')) return mdIcon;
  if (lowerName.endsWith('.pdf')) return pdfIcon;
  if (lowerName.endsWith('.doc') || lowerName.endsWith('.docx')) return wordIcon;
  if (lowerName.endsWith('.xls') || lowerName.endsWith('.xlsx') || lowerName.endsWith('.csv')) return excelIcon;
  return defaultDocIcon;
};

const EMPTY_GRAPH: Module4GraphResponse = {
  nodes: [],
  edges: [],
  source: 'storage',
  workspace_id: null,
  stats: {
    node_count: 0,
    edge_count: 0,
    by_node_type: {},
    by_relation_type: {},
  },
};

const EDGE_KIND_OPTIONS: Array<{ key: GraphRenderEdge['kind']; label: string }> = [
  { key: 'related_to', label: '实体关联' },
  { key: 'in_community', label: '社区归属' },
  { key: 'has_report', label: '社区报告' },
  { key: 'evidence', label: '证据链路' },
];

const TYPE_NAME_MAP: Record<string, string> = {
  overview: '总览模式',
  'community-focus': '社区聚焦',
  'entity-drilldown': '实体钻取',
  community: '社区',
  report: '报告',
  community_report: '社区报告',
  communityreport: '社区报告',
  entity: '实体',
  document: '文档',
  text_unit: '文本片段',
  textunit: '文本片段',
  chunk: '文本片段',
  artifact: '补充节点',
  covariate: '协变量',
  hub: '中心节点',
  member: '成员节点',
  summary: '摘要节点',
  evidence: '证据节点',
  related_to: '实体关联',
  in_community: '社区归属',
  has_report: '报告关系',
  other: '其他关系',
};

const QUERY_MODE_OPTIONS: Array<{ value: Module4GraphRagQueryMode; label: string; description: string }> = [
  { value: 'local', label: '本地检索', description: '优先在相关社区内检索并回答。' },
  { value: 'global', label: '全局检索', description: '跨社区聚合后回答，适合宏观问题。' },
  { value: 'drift', label: 'DRIFT 检索', description: '先锁定主题再扩展关系路径。' },
  { value: 'basic', label: '基础检索', description: '使用轻量上下文快速返回答案。' },
];

const DEFAULT_GRAPH_NODE_TYPES = ['Entity', 'Community', 'CommunityReport'];
const DEFAULT_GRAPH_RELATION_TYPES = ['related_to', 'in_community', 'has_report'];
const LABEL_MODE_OPTIONS: Array<{ key: GraphLabelMode; label: string; description: string }> = [
  {
    key: 'compact',
    label: '简洁标签',
    description: '优先显示社区与关键实体，减少文字重叠',
  },
  {
    key: 'full',
    label: '完整标签',
    description: '尽可能展示全部节点名称，自动做防重叠抑制',
  },
];

const MODULE4_CONTROL_DRAWER_BREAKPOINT = 1360;
const MODULE4_HEADER_DENSE_BREAKPOINT = 1220;
const MODULE4_HEADER_ULTRA_DENSE_BREAKPOINT = 980;
const MODULE4_DETAIL_DENSE_BREAKPOINT = 1280;
const MODULE4_DETAIL_ULTRA_DENSE_BREAKPOINT = 1080;

const DETAIL_PANEL_CARD_SOFT_CLASS =
  'rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900';
const DETAIL_PANEL_CARD_BASE_CLASS =
  'rounded-md border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-950/40';
const DETAIL_PANEL_LABEL_CLASS = 'text-[10px] font-medium text-slate-500 dark:text-slate-400';
const DETAIL_PANEL_VALUE_CLASS = 'mt-1 text-[11px] font-medium text-slate-700 dark:text-slate-200';
const DETAIL_PANEL_SECTION_TITLE_CLASS =
  'text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400';
const DETAIL_PANEL_ACTION_BASE_CLASS =
  'inline-flex h-7 items-center rounded-md border px-2.5 text-[10px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60';
const DETAIL_PANEL_ACTION_NEUTRAL_CLASS =
  `${DETAIL_PANEL_ACTION_BASE_CLASS} border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200`;
const DETAIL_PANEL_ACTION_VIOLET_CLASS =
  `${DETAIL_PANEL_ACTION_BASE_CLASS} border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300`;
const DETAIL_PANEL_ACTION_SKY_CLASS =
  `${DETAIL_PANEL_ACTION_BASE_CLASS} border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100 dark:border-sky-700 dark:bg-sky-950/30 dark:text-sky-300`;

const cleanText = (value: unknown) => String(value || '').replace(/\s+/g, ' ').trim();

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const asNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const publicCaseMetaOf = (item: Module4GraphFileItem) => asRecord(asRecord(item.metadata).public_case);

const isPublicCaseFile = (item: Module4GraphFileItem) =>
  cleanText(asRecord(item.metadata).visibility).toLowerCase() === 'public_case';

const publicCaseSortOrderOf = (item: Module4GraphFileItem) => asNumber(publicCaseMetaOf(item).sort_order, 1000);

const publicCaseCaseIdOf = (item: Module4GraphFileItem) => cleanText(publicCaseMetaOf(item).case_id || item.file_hash);

type LinkedNodeResolutionDiagnostics = {
  candidateCount: number;
  resolvedCount: number;
  unresolvedCount: number;
  unresolvedCandidates: string[];
  resolutionStrategy: string;
  usedFallbackCandidates: boolean;
};

const parseLinkedNodeResolution = (value: unknown): LinkedNodeResolutionDiagnostics => {
  const record = asRecord(value);
  const unresolvedCandidates = Array.isArray(record.unresolved_candidates)
    ? record.unresolved_candidates.map((item) => cleanText(item)).filter(Boolean)
    : [];
  return {
    candidateCount: asNumber(record.candidate_count, 0),
    resolvedCount: asNumber(record.resolved_count, 0),
    unresolvedCount: asNumber(record.unresolved_count, 0),
    unresolvedCandidates,
    resolutionStrategy: cleanText(record.resolution_strategy),
    usedFallbackCandidates: Boolean(record.used_fallback_candidates),
  };
};

const MAX_HIDDEN_QUERY_HIT_EXPAND = 8;
const GRAPH_RENDER_FILE_EXTENSIONS = new Set(['.docx', '.pdf', '.txt', '.md']);

const fileExtensionFromName = (value: unknown) => {
  const normalized = cleanText(value).toLowerCase();
  if (!normalized) return '';
  const match = normalized.match(/(\.[a-z0-9]+)$/i);
  return match ? match[1].toLowerCase() : '';
};

const normalizeFileExtension = (value: unknown) => {
  const normalized = cleanText(value).toLowerCase();
  if (!normalized) return '';
  return normalized.startsWith('.') ? normalized : `.${normalized}`;
};

const resolveGraphRenderableExtension = (item: Module4GraphFileItem) => {
  const directExt = fileExtensionFromName(item.file_name || item.file_hash);
  if (GRAPH_RENDER_FILE_EXTENSIONS.has(directExt)) return directExt;

  const metadata = asRecord(item.metadata);
  const inputSnapshot = asRecord(metadata.input_snapshot);

  const extensionCandidates = [
    inputSnapshot.file_ext,
    inputSnapshot.file_extension,
    inputSnapshot.ext,
    inputSnapshot.suffix,
  ];
  for (const candidate of extensionCandidates) {
    const normalized = normalizeFileExtension(candidate);
    if (GRAPH_RENDER_FILE_EXTENSIONS.has(normalized)) return normalized;
  }

  const filenameCandidates = [
    inputSnapshot.file_name,
    inputSnapshot.original_file_name,
    inputSnapshot.origin_file_name,
    inputSnapshot.source_file_name,
    inputSnapshot.source_name,
  ];
  for (const candidate of filenameCandidates) {
    const inferredExt = fileExtensionFromName(candidate);
    if (GRAPH_RENDER_FILE_EXTENSIONS.has(inferredExt)) return inferredExt;
  }

  return '';
};

const hasRenderableArtifactStatus = (item: Module4GraphFileItem) => {
  const metadata = asRecord(item.metadata);
  const artifactStageStatus = asRecord(metadata.artifact_stage_status);
  if (!Object.keys(artifactStageStatus).length) return true;
  if (artifactStageStatus.full_ready === true) return true;
  const stages = asRecord(artifactStageStatus.stages);
  if (!Object.keys(stages).length) return true;
  return Object.values(stages).every((stage) => asRecord(stage).exists !== false);
};

const normalizeQueryMode = (value: unknown): Module4GraphRagQueryMode | null => {
  const normalized = cleanText(value).toLowerCase();
  if (normalized === 'local' || normalized === 'global' || normalized === 'drift' || normalized === 'basic') {
    return normalized;
  }
  return null;
};

const queryModeLabel = (value: Module4GraphRagQueryMode | null | undefined) =>
  QUERY_MODE_OPTIONS.find((item) => item.value === value)?.label || '未知模式';

type QueryExecutionMeta = {
  requestedMode: Module4GraphRagQueryMode | null;
  effectiveMode: Module4GraphRagQueryMode | null;
  usedFallback: boolean;
  source: string;
};

const buildQueryExecutionMeta = ({
  source,
  requestedMode,
  effectiveMode,
}: {
  source: unknown;
  requestedMode: Module4GraphRagQueryMode | null;
  effectiveMode: Module4GraphRagQueryMode | null;
}): QueryExecutionMeta => {
  const normalizedSource = cleanText(source);
  const fallbackMatch = normalizedSource.match(/^graphrag:query:([a-z_]+):fallback:([a-z_]+)$/i);
  if (fallbackMatch) {
    return {
      requestedMode: normalizeQueryMode(fallbackMatch[1]) || requestedMode,
      effectiveMode: normalizeQueryMode(fallbackMatch[2]) || effectiveMode,
      usedFallback: true,
      source: normalizedSource,
    };
  }

  const directMatch = normalizedSource.match(/^graphrag:query:([a-z_]+)$/i);
  if (directMatch) {
    const sourceMode = normalizeQueryMode(directMatch[1]);
    return {
      requestedMode: sourceMode || requestedMode,
      effectiveMode: effectiveMode || sourceMode,
      usedFallback: false,
      source: normalizedSource,
    };
  }

  const requested = requestedMode;
  const effective = effectiveMode;
  return {
    requestedMode: requested,
    effectiveMode: effective,
    usedFallback: Boolean(requested && effective && requested !== effective),
    source: normalizedSource,
  };
};

const edgeMergeKey = (edge: Module4GraphEdge): string => {
  const edgeId = cleanText(edge.edge_id);
  if (edgeId) return `edge:${edgeId}`;
  return `tuple:${cleanText(edge.source_node_id)}=>${cleanText(edge.target_node_id)}#${cleanText(edge.relation_type)}`;
};

const mergeGraphSnapshots = (base: Module4GraphResponse, patch: Module4GraphResponse): Module4GraphResponse => {
  const nodeMap = new Map<string, Module4GraphNode>();
  const edgeMap = new Map<string, Module4GraphEdge>();

  base.nodes.forEach((node) => nodeMap.set(node.node_id, node));
  patch.nodes.forEach((node) => nodeMap.set(node.node_id, node));

  base.edges.forEach((edge) => edgeMap.set(edgeMergeKey(edge), edge));
  patch.edges.forEach((edge) => edgeMap.set(edgeMergeKey(edge), edge));

  const mergedNodes = [...nodeMap.values()];
  const mergedEdges = [...edgeMap.values()];

  const byNodeType: Record<string, number> = {};
  mergedNodes.forEach((node) => {
    const key = cleanText(node.node_type || 'unknown') || 'unknown';
    byNodeType[key] = (byNodeType[key] || 0) + 1;
  });

  const byRelationType: Record<string, number> = {};
  mergedEdges.forEach((edge) => {
    const key = cleanText(edge.relation_type || 'unknown') || 'unknown';
    byRelationType[key] = (byRelationType[key] || 0) + 1;
  });

  return {
    nodes: mergedNodes,
    edges: mergedEdges,
    source: patch.source || base.source || 'storage',
    workspace_id: patch.workspace_id ?? base.workspace_id ?? null,
    stats: {
      node_count: mergedNodes.length,
      edge_count: mergedEdges.length,
      by_node_type: byNodeType,
      by_relation_type: byRelationType,
    },
  };
};

const displayFileName = (item: Module4GraphFileItem) =>
  cleanText(publicCaseMetaOf(item).display_name || item.file_name || item.file_hash || '未命名文件');

const isReadyFile = (item: Module4GraphFileItem) => String(item.status || '').toLowerCase() === 'ready';

const isGraphRenderableFile = (item: Module4GraphFileItem) => {
  if (!isReadyFile(item)) return false;
  if (!resolveGraphRenderableExtension(item)) return false;
  if (!cleanText(item.active_version_id)) return false;
  if (asNumber(item.node_count, 0) <= 0 || asNumber(item.edge_count, 0) <= 0) return false;
  if (!hasRenderableArtifactStatus(item)) return false;
  if (cleanText(item.last_error)) return false;
  return true;
};

const graphBuildModeOf = (item: Module4GraphFileItem) =>
  String(((item.metadata || {}) as Record<string, unknown>).graph_build_mode || '').trim().toLowerCase();

const importModeOf = (item: Module4GraphFileItem) => {
  const metadata = (item.metadata || {}) as Record<string, unknown>;
  const importSummary = (metadata.import_summary || {}) as Record<string, unknown>;
  return String(importSummary.mode || '').trim().toLowerCase();
};

const isFinalGraphRAGFile = (item: Module4GraphFileItem) => {
  if (!isGraphRenderableFile(item)) return false;
  const buildMode = graphBuildModeOf(item);
  const importMode = importModeOf(item);
  return buildMode === 'graphrag' || importMode === 'final' || importMode === 'full';
};

const isGraphRAGFile = (item: Module4GraphFileItem) => {
  if (!isGraphRenderableFile(item)) return false;
  const buildMode = graphBuildModeOf(item);
  const importMode = importModeOf(item);
  return Boolean(
    item.workspace_id ||
      buildMode === 'graphrag' ||
      buildMode === 'graphrag_partial' ||
      importMode === 'full' ||
      importMode === 'partial'
  );
};

const fileQualityRank = (item: Module4GraphFileItem) => {
  const buildMode = graphBuildModeOf(item);
  const importMode = importModeOf(item);
  if (buildMode === 'graphrag' || importMode === 'final' || importMode === 'full') return 4;
  if (buildMode === 'graphrag_partial' || importMode === 'partial') return 3;
  if (item.workspace_id) return 2;
  return 1;
};

const sortGraphFiles = (items: Module4GraphFileItem[]) =>
  [...items].sort((left, right) => {
    const visibilityDelta = Number(isPublicCaseFile(left)) - Number(isPublicCaseFile(right));
    if (visibilityDelta !== 0) return visibilityDelta;

    if (isPublicCaseFile(left) && isPublicCaseFile(right)) {
      const sortOrderDelta = publicCaseSortOrderOf(left) - publicCaseSortOrderOf(right);
      if (sortOrderDelta !== 0) return sortOrderDelta;
      return displayFileName(left).localeCompare(displayFileName(right), 'zh-CN');
    }

    const rankDelta = fileQualityRank(right) - fileQualityRank(left);
    if (rankDelta !== 0) return rankDelta;

    const rightTime = new Date(String(right.updated_at || right.last_indexed_at || right.created_at || 0)).getTime();
    const leftTime = new Date(String(left.updated_at || left.last_indexed_at || left.created_at || 0)).getTime();
    if (rightTime !== leftTime) return rightTime - leftTime;

    const nodeDelta = Number(right.node_count || 0) - Number(left.node_count || 0);
    if (nodeDelta !== 0) return nodeDelta;

    return displayFileName(left).localeCompare(displayFileName(right), 'zh-CN');
  });

const dedupePreferredGraphFiles = (items: Module4GraphFileItem[]) => {
  const deduped = new Map<string, Module4GraphFileItem>();
  sortGraphFiles(items).forEach((item) => {
    const key = graphFileDedupeKey(item);
    if (!deduped.has(key)) deduped.set(key, item);
  });
  return [...deduped.values()];
};

const graphFileDedupeKey = (item: Module4GraphFileItem) =>
  isPublicCaseFile(item)
    ? `public:${publicCaseCaseIdOf(item)}`
    : `private:${cleanText(item.file_name || item.file_hash || '').toLowerCase() || cleanText(item.file_hash)}`;

type HiddenGraphFileReason = {
  item: Module4GraphFileItem;
  reason: string;
  code: string;
};

const hiddenGraphFileReasonForItem = ({
  item,
  finalGraphRAGAvailable,
  graphRAGAvailable,
  preferredByKey,
}: {
  item: Module4GraphFileItem;
  finalGraphRAGAvailable: boolean;
  graphRAGAvailable: boolean;
  preferredByKey: Map<string, Module4GraphFileItem>;
}): HiddenGraphFileReason => {
  const status = cleanText(item.status).toLowerCase();
  if (!isReadyFile(item)) {
    return {
      item,
      code: 'not_ready',
      reason: `索引未完成（当前状态：${status || 'unknown'}）`,
    };
  }

  const extension = resolveGraphRenderableExtension(item);
  if (!extension) {
    return {
      item,
      code: 'unsupported_extension',
      reason: '文件类型不在图谱渲染范围（仅支持 docx/pdf/txt/md）。',
    };
  }

  const lastError = cleanText(item.last_error);
  if (lastError) {
    return {
      item,
      code: 'build_error',
      reason: `构建失败：${lastError.slice(0, 120)}`,
    };
  }

  if (!cleanText(item.active_version_id)) {
    return {
      item,
      code: 'missing_version',
      reason: '缺少可用图谱版本（active_version_id 为空）',
    };
  }

  if (asNumber(item.node_count, 0) <= 0 || asNumber(item.edge_count, 0) <= 0) {
    return {
      item,
      code: 'empty_graph',
      reason: '图谱节点或边数量为 0',
    };
  }

  if (!hasRenderableArtifactStatus(item)) {
    return {
      item,
      code: 'artifact_incomplete',
      reason: 'GraphRAG 产物不完整，暂不展示',
    };
  }

  if (finalGraphRAGAvailable && isGraphRAGFile(item) && !isFinalGraphRAGFile(item)) {
    return {
      item,
      code: 'prefer_final',
      reason: '已有完整 GraphRAG 构建版本，当前版本被自动降级展示',
    };
  }

  if (graphRAGAvailable && isGraphRenderableFile(item) && !isGraphRAGFile(item)) {
    return {
      item,
      code: 'prefer_graphrag',
      reason: '已存在 GraphRAG 构建结果，优先展示 GraphRAG 文件',
    };
  }

  const preferred = preferredByKey.get(graphFileDedupeKey(item));
  if (preferred && preferred.graph_file_id !== item.graph_file_id) {
    return {
      item,
      code: 'deduped_out',
      reason: '同名文件存在更高质量版本，当前版本已隐藏',
    };
  }

  return {
    item,
    code: 'other_filter',
    reason: '未满足当前展示过滤条件',
  };
};

const formatTypeName = (value: unknown) => {
  const normalized = String(value || '').trim();
  if (!normalized) return '未命名';
  return (
    TYPE_NAME_MAP[normalized] ||
    normalized
      .replace(/_/g, ' ')
      .replace(/\b[a-z]/g, (char) => char.toUpperCase())
      .trim()
  );
};

const describeBuildMode = (item: Module4GraphFileItem | null) => {
  if (!item) return '';
  const buildMode = graphBuildModeOf(item);
  if (buildMode === 'graphrag') return 'GraphRAG 完整构建';
  if (buildMode === 'graphrag_partial') return 'GraphRAG 部分导入';
  return item.workspace_id ? 'GraphRAG 工作区图谱' : '历史图谱';
};

export const KnowledgeNexus: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [graphFiles, setGraphFiles] = useState<Module4GraphFileItem[]>([]);
  const [selectedFileHash, setSelectedFileHash] = useState('');
  const [baselineGraphData, setBaselineGraphData] = useState<Module4GraphResponse>(EMPTY_GRAPH);
  const [queryOverlayGraphData, setQueryOverlayGraphData] = useState<Module4GraphResponse | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [renderMode, setRenderMode] = useState<GraphRenderMode>('overview');
  const [focusedCommunityId, setFocusedCommunityId] = useState<string | null>(null);
  const [focusPeerCommunityId, setFocusPeerCommunityId] = useState<string | null>(null);
  const [drilldownEntityId, setDrilldownEntityId] = useState<string | null>(null);
  const [maxCommunityLevel, setMaxCommunityLevel] = useState<number | null>(null);
  const [enabledEdgeKinds, setEnabledEdgeKinds] = useState<GraphRenderEdge['kind'][]>([
    'related_to',
    'in_community',
    'has_report',
  ]);
  const [labelMode, setLabelMode] = useState<GraphLabelMode>('compact');
  const [collapseCommunityMembers, setCollapseCommunityMembers] = useState(false);
  const [queryText, setQueryText] = useState('');
  const [queryMode, setQueryMode] = useState<Module4GraphRagQueryMode>('local');
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState('');
  const [queryResult, setQueryResult] = useState<Module4GraphRagQueryResponse | null>(null);
  const [lastRequestedQueryMode, setLastRequestedQueryMode] = useState<Module4GraphRagQueryMode | null>(null);
  const [queryFocusIndex, setQueryFocusIndex] = useState(0);
  const [neighborhoodLoading, setNeighborhoodLoading] = useState(false);
  const [expandingHiddenHits, setExpandingHiddenHits] = useState(false);
  const [nodeDetail, setNodeDetail] = useState<Module4NodeDetailResponse | null>(null);
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);
  const [nodeDetailError, setNodeDetailError] = useState('');
  const [isFileDropdownOpen, setIsFileDropdownOpen] = useState(false);
  const [workbenchWidth, setWorkbenchWidth] = useState<number>(() =>
    typeof window !== 'undefined' ? window.innerWidth : 1440
  );
  const [isControlDrawerOpen, setIsControlDrawerOpen] = useState<boolean>(() =>
    typeof window !== 'undefined'
      ? window.innerWidth <= MODULE4_CONTROL_DRAWER_BREAKPOINT
      : false
  );
  const fileDropdownRef = useRef<HTMLDivElement>(null);
  const workbenchRef = useRef<HTMLElement | null>(null);
  const graphLoadSeqRef = useRef(0);
  const selectedFileHashRef = useRef('');

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (fileDropdownRef.current && !fileDropdownRef.current.contains(event.target as Node)) {
        setIsFileDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const beginGraphLoad = useCallback(() => {
    graphLoadSeqRef.current += 1;
    return graphLoadSeqRef.current;
  }, []);

  const isCurrentGraphLoad = useCallback((loadSeq: number) => graphLoadSeqRef.current === loadSeq, []);

  useEffect(() => {
    selectedFileHashRef.current = selectedFileHash;
  }, [selectedFileHash]);

  useEffect(() => {
    const target = workbenchRef.current;

    const syncWidth = () => {
      const nextWidth = Math.round(target?.getBoundingClientRect().width || window.innerWidth || 1440);
      setWorkbenchWidth((prev) => (prev === nextWidth ? prev : nextWidth));
    };

    syncWidth();

    if (typeof ResizeObserver === 'undefined' || !target) {
      window.addEventListener('resize', syncWidth);
      return () => window.removeEventListener('resize', syncWidth);
    }

    const observer = new ResizeObserver(() => syncWidth());
    observer.observe(target);
    window.addEventListener('resize', syncWidth);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', syncWidth);
    };
  }, []);

  const shouldUseControlDrawer = workbenchWidth > 0 && workbenchWidth <= MODULE4_CONTROL_DRAWER_BREAKPOINT;
  const showDockedControlPanel = !shouldUseControlDrawer;
  const showControlDrawer = shouldUseControlDrawer && isControlDrawerOpen;
  const useDenseHeader = workbenchWidth > 0 && workbenchWidth <= MODULE4_HEADER_DENSE_BREAKPOINT;
  const useUltraDenseHeader = workbenchWidth > 0 && workbenchWidth <= MODULE4_HEADER_ULTRA_DENSE_BREAKPOINT;
  const useDenseDetailPanel = workbenchWidth > 0 && workbenchWidth <= MODULE4_DETAIL_DENSE_BREAKPOINT;
  const useUltraDenseDetailPanel = workbenchWidth > 0 && workbenchWidth <= MODULE4_DETAIL_ULTRA_DENSE_BREAKPOINT;

  const closeControlDrawer = useCallback(() => setIsControlDrawerOpen(false), []);
  const toggleControlDrawer = useCallback(() => {
    if (!shouldUseControlDrawer) return;
    setIsControlDrawerOpen((prev) => !prev);
  }, [shouldUseControlDrawer]);

  useEffect(() => {
    if (!shouldUseControlDrawer && isControlDrawerOpen) {
      setIsControlDrawerOpen(false);
    }
  }, [isControlDrawerOpen, shouldUseControlDrawer]);

  const graphRAGFiles = useMemo(
    () => dedupePreferredGraphFiles(graphFiles.filter((item) => isGraphRAGFile(item))),
    [graphFiles]
  );
  const finalGraphRAGFiles = useMemo(() => graphRAGFiles.filter(isFinalGraphRAGFile), [graphRAGFiles]);
  const visibleFiles = useMemo(
    () =>
      finalGraphRAGFiles.length
        ? finalGraphRAGFiles
        : graphRAGFiles.length
          ? graphRAGFiles
          : dedupePreferredGraphFiles(graphFiles.filter(isGraphRenderableFile)),
    [finalGraphRAGFiles, graphFiles, graphRAGFiles]
  );
  const visiblePrivateFiles = useMemo(
    () => visibleFiles.filter((item) => !isPublicCaseFile(item)),
    [visibleFiles]
  );
  const visiblePublicCaseFiles = useMemo(
    () => visibleFiles.filter(isPublicCaseFile),
    [visibleFiles]
  );
  const hiddenGraphFileReasons = useMemo<HiddenGraphFileReason[]>(() => {
    const visibleIdSet = new Set(visibleFiles.map((item) => item.graph_file_id));
    const preferredByKey = new Map<string, Module4GraphFileItem>();
    sortGraphFiles(graphFiles).forEach((item) => {
      const key = graphFileDedupeKey(item);
      if (!preferredByKey.has(key)) preferredByKey.set(key, item);
    });

    return sortGraphFiles(graphFiles)
      .filter((item) => !visibleIdSet.has(item.graph_file_id))
      .map((item) =>
        hiddenGraphFileReasonForItem({
          item,
          finalGraphRAGAvailable: finalGraphRAGFiles.length > 0,
          graphRAGAvailable: graphRAGFiles.length > 0,
          preferredByKey,
        })
      );
  }, [finalGraphRAGFiles.length, graphFiles, graphRAGFiles.length, visibleFiles]);
  const hiddenGraphFileReasonPreview = useMemo(() => hiddenGraphFileReasons.slice(0, 8), [hiddenGraphFileReasons]);

  const clearQueryResult = useCallback(() => {
    setQueryResult(null);
    setLastRequestedQueryMode(null);
    setQueryFocusIndex(0);
    setQueryOverlayGraphData(null);
  }, []);

  const graphData = useMemo<Module4GraphResponse>(() => {
    if (!queryOverlayGraphData) return baselineGraphData;
    return mergeGraphSnapshots(baselineGraphData, queryOverlayGraphData);
  }, [baselineGraphData, queryOverlayGraphData]);

  const loadGraph = useCallback(
    async (hash: string) => {
      const loadSeq = beginGraphLoad();
      setLoading(true);
      setError('');
      try {
        const nextGraph = hash
          ? await fetchModule4FileGraph(hash, {
              nodeTypes: DEFAULT_GRAPH_NODE_TYPES,
              relationTypes: DEFAULT_GRAPH_RELATION_TYPES,
              limitNodes: 1200,
              limitEdges: 2400,
            })
          : await fetchModule4Graph({
              nodeTypes: DEFAULT_GRAPH_NODE_TYPES,
              relationTypes: DEFAULT_GRAPH_RELATION_TYPES,
              limitNodes: 1200,
              limitEdges: 2400,
            });
        if (!isCurrentGraphLoad(loadSeq)) return;

        startTransition(() => {
          setBaselineGraphData(nextGraph);
          setQueryOverlayGraphData(null);
          setRenderMode('overview');
          setFocusedCommunityId(null);
          setFocusPeerCommunityId(null);
          setDrilldownEntityId(null);
          setSelectedNodeId(null);
          setSelectedEdgeId(null);
          setQueryResult(null);
          setQueryError('');
          setQueryFocusIndex(0);
        });
      } catch (loadError) {
        if (!isCurrentGraphLoad(loadSeq)) return;
        const message = loadError instanceof Error ? loadError.message : '加载图谱失败';
        setError(message);
      } finally {
        if (isCurrentGraphLoad(loadSeq)) setLoading(false);
      }
    },
    [beginGraphLoad, isCurrentGraphLoad]
  );

  const handleFileSelect = useCallback(
    (nextFileHash: string) => {
      setSelectedFileHash(nextFileHash);
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
      clearQueryResult();
      void loadGraph(nextFileHash);
      setIsFileDropdownOpen(false);
      if (showControlDrawer) {
        setIsControlDrawerOpen(false);
      }
    },
    [clearQueryResult, loadGraph, showControlDrawer]
  );

  const selectedFile = useMemo(
    () => visibleFiles.find((item) => item.file_hash === selectedFileHash) || null,
    [selectedFileHash, visibleFiles]
  );

  const graphNodeIdByAlias = useMemo(() => {
    const aliasMap = new Map<string, string>();
    graphData.nodes.forEach((node) => {
      const nodeId = cleanText(node.node_id);
      if (!nodeId) return;
      const attrs = ((node.attrs || {}) as Record<string, unknown>) || {};
      const aliases = [
        nodeId,
        cleanText(node.canonical_key),
        cleanText(node.display_name),
        cleanText(attrs.graphrag_id),
        cleanText(attrs.report_id),
        cleanText(attrs.human_readable_id),
        cleanText(attrs.id),
        cleanText(attrs.title),
        cleanText(attrs.name),
      ].filter(Boolean);
      aliases.forEach((alias) => {
        const normalizedAlias = cleanText(alias);
        if (!normalizedAlias) return;
        if (!aliasMap.has(normalizedAlias)) aliasMap.set(normalizedAlias, nodeId);
        const lowerAlias = normalizedAlias.toLowerCase();
        if (!aliasMap.has(lowerAlias)) aliasMap.set(lowerAlias, nodeId);
        if (normalizedAlias.includes('::')) {
          const suffix = cleanText(normalizedAlias.split('::').slice(1).join('::'));
          if (suffix && !aliasMap.has(suffix)) aliasMap.set(suffix, nodeId);
          if (suffix) {
            const lowerSuffix = suffix.toLowerCase();
            if (!aliasMap.has(lowerSuffix)) aliasMap.set(lowerSuffix, nodeId);
          }
        }
      });
    });
    return aliasMap;
  }, [graphData.nodes]);

  const resolveLinkedNodeId = useCallback(
    (value: unknown) => {
      const normalized = cleanText(value);
      if (!normalized) return '';
      if (graphNodeIdByAlias.has(normalized)) return String(graphNodeIdByAlias.get(normalized));
      const lower = normalized.toLowerCase();
      if (graphNodeIdByAlias.has(lower)) return String(graphNodeIdByAlias.get(lower));
      if (normalized.includes('::')) {
        const suffix = cleanText(normalized.split('::').slice(1).join('::'));
        if (suffix && graphNodeIdByAlias.has(suffix)) return String(graphNodeIdByAlias.get(suffix));
        const lowerSuffix = suffix.toLowerCase();
        if (lowerSuffix && graphNodeIdByAlias.has(lowerSuffix)) return String(graphNodeIdByAlias.get(lowerSuffix));
      }
      return normalized;
    },
    [graphNodeIdByAlias]
  );

  const graphNodeTypeById = useMemo(() => {
    const nodeTypeMap = new Map<string, string>();
    graphData.nodes.forEach((node) => {
      const nodeId = cleanText(node.node_id);
      if (!nodeId) return;
      const nodeType = cleanText(node.node_type).toLowerCase();
      if (!nodeType) return;
      nodeTypeMap.set(nodeId, nodeType);
    });
    return nodeTypeMap;
  }, [graphData.nodes]);

  const applyQueryNodeFocusMode = useCallback(
    (nodeId: string | null | undefined) => {
      const normalizedNodeId = cleanText(nodeId);
      if (!normalizedNodeId) {
        setRenderMode('overview');
        setFocusedCommunityId(null);
        setFocusPeerCommunityId(null);
        setDrilldownEntityId(null);
        return;
      }

      const nodeType = graphNodeTypeById.get(normalizedNodeId) || '';
      if (nodeType === 'community') {
        setRenderMode('community-focus');
        setFocusedCommunityId(normalizedNodeId);
        setFocusPeerCommunityId(null);
        setDrilldownEntityId(null);
        return;
      }
      if (nodeType === 'entity') {
        setRenderMode('entity-drilldown');
        setDrilldownEntityId(normalizedNodeId);
        setFocusedCommunityId(null);
        setFocusPeerCommunityId(null);
        return;
      }

      setRenderMode('overview');
      setFocusedCommunityId(null);
      setFocusPeerCommunityId(null);
      setDrilldownEntityId(null);
    },
    [graphNodeTypeById]
  );

  const buildOptions = useMemo<GraphRenderBuildOptions>(
    () => ({
      maxCommunityLevel,
      enabledEdgeKinds,
      collapseCommunityMembersInOverview: collapseCommunityMembers,
      focusPeerCommunityId: renderMode === 'community-focus' ? focusPeerCommunityId : null,
      pinnedNodeIds: (queryResult?.linked_node_ids || [])
        .map((nodeId) => resolveLinkedNodeId(nodeId))
        .filter(Boolean)
        .slice(0, 120),
    }),
    [
      collapseCommunityMembers,
      enabledEdgeKinds,
      focusPeerCommunityId,
      maxCommunityLevel,
      queryResult?.linked_node_ids,
      resolveLinkedNodeId,
      renderMode,
    ]
  );

  const communityLevelOptions = useMemo(() => {
    const levels = graphData.nodes
      .filter((node) => String(node.node_type || '').toLowerCase() === 'community')
      .map((node) => Number((node.attrs || {}).level))
      .filter((level) => Number.isFinite(level));
    return [...new Set(levels)].sort((left, right) => left - right);
  }, [graphData.nodes]);

  const renderModel = useMemo(() => {
    if (renderMode === 'community-focus' && focusedCommunityId) {
      return buildGraphRAGCommunityFocusModel(graphData, focusedCommunityId, buildOptions);
    }
    if (renderMode === 'entity-drilldown' && drilldownEntityId) {
      return buildGraphRAGEntityDrilldownModel(graphData, drilldownEntityId, buildOptions);
    }
    return buildGraphRAGOverviewModel(graphData, buildOptions);
  }, [buildOptions, drilldownEntityId, focusedCommunityId, graphData, renderMode]);

  const lastNonEmptyRenderModelRef = useRef<GraphRenderModel | null>(null);
  useEffect(() => {
    if (renderModel.nodes.length > 0) lastNonEmptyRenderModelRef.current = renderModel;
  }, [renderModel]);

  const displayRenderModel = useMemo(() => {
    if (renderModel.nodes.length > 0) return renderModel;
    const lastModel = lastNonEmptyRenderModelRef.current;
    if (loading && lastModel && lastModel.nodes.length > 0) return lastModel;
    return renderModel;
  }, [loading, renderModel]);

  const selectedNode = useMemo<GraphRenderNode | null>(() => {
    if (!selectedNodeId) return null;
    return renderModel.nodes.find((node) => node.id === selectedNodeId) || null;
  }, [renderModel.nodes, selectedNodeId]);

  const selectedEdge = useMemo(() => {
    if (!selectedEdgeId) return null;
    return renderModel.edges.find((edge) => edge.id === selectedEdgeId) || null;
  }, [renderModel.edges, selectedEdgeId]);
  const shouldShowDetailsPanel = Boolean(selectedNode || selectedEdge || renderMode !== 'overview');

  const selectedCommunity = useMemo(() => {
    const communityId = selectedNode?.kind === 'community' ? selectedNode.id : selectedNode?.communityId || focusedCommunityId;
    if (!communityId) return null;
    return renderModel.communities.find((item) => item.id === communityId) || null;
  }, [focusedCommunityId, renderModel.communities, selectedNode]);

  const peerCommunity = useMemo(() => {
    if (!focusPeerCommunityId) return null;
    return renderModel.communities.find((item) => item.id === focusPeerCommunityId) || null;
  }, [focusPeerCommunityId, renderModel.communities]);

  const selectedNodeMeta = useMemo(
    () => (selectedNode ? ((selectedNode.meta || {}) as Record<string, unknown>) : null),
    [selectedNode]
  );
  const nodeDetailMeta = useMemo(
    () => ((nodeDetail?.node?.attrs || {}) as Record<string, unknown>),
    [nodeDetail?.node?.attrs]
  );
  const selectedNodePreview = cleanText(selectedNodeMeta?.preview_text || nodeDetailMeta?.preview_text || '');

  const selectedEdgeMeta = useMemo(
    () => (selectedEdge ? ((selectedEdge.meta || {}) as Record<string, unknown>) : null),
    [selectedEdge]
  );
  const selectedEdgeEvidenceCount = Number(
    selectedEdgeMeta?.evidence_count ?? selectedEdgeMeta?.evidenceCount ?? selectedEdgeMeta?.evidence_total ?? 0
  );
  const nodeDetailEvidence = useMemo(() => (nodeDetail?.evidence || []) as Module4EvidenceItem[], [nodeDetail?.evidence]);
  const nodeDetailEdgeEvidenceCount = useMemo(
    () =>
      Object.values(nodeDetail?.edge_evidence || {}).reduce(
        (total, items) => total + (Array.isArray(items) ? items.length : 0),
        0
      ),
    [nodeDetail?.edge_evidence]
  );

  const evidenceNodeCount = useMemo(
    () => renderModel.nodes.filter((node) => node.role === 'evidence').length,
    [renderModel.nodes]
  );

  const aggregatedEdgeCount = useMemo(
    () => renderModel.edges.filter((edge) => Boolean((edge.meta || {}).aggregated)).length,
    [renderModel.edges]
  );

  const modeText = useMemo(() => formatTypeName(renderMode), [renderMode]);
  const allGraphNodeIdSet = useMemo(
    () => new Set(graphData.nodes.map((node) => cleanText(node.node_id)).filter(Boolean)),
    [graphData.nodes]
  );
  const renderNodeIdSet = useMemo(() => new Set(renderModel.nodes.map((node) => node.id)), [renderModel.nodes]);
  const queryLinkedNodeResolution = useMemo(
    () => parseLinkedNodeResolution(queryResult?.linked_node_resolution || null),
    [queryResult?.linked_node_resolution]
  );
  const queryLinkedNodeIdsAll = useMemo(
    () => {
      const normalized = (queryResult?.linked_node_ids || [])
        .map((nodeId) => resolveLinkedNodeId(nodeId))
        .filter(Boolean);
      return [...new Set(normalized)] as string[];
    },
    [queryResult?.linked_node_ids, resolveLinkedNodeId]
  );
  const queryLinkedNodeIdsMappable = useMemo(
    () => queryLinkedNodeIdsAll.filter((nodeId) => allGraphNodeIdSet.has(nodeId)),
    [allGraphNodeIdSet, queryLinkedNodeIdsAll]
  );
  const queryLinkedNodeIdsInView = useMemo(
    () => queryLinkedNodeIdsMappable.filter((nodeId) => renderNodeIdSet.has(nodeId)),
    [queryLinkedNodeIdsMappable, renderNodeIdSet]
  );
  const hiddenQueryLinkedNodeIds = useMemo(
    () => queryLinkedNodeIdsMappable.filter((nodeId) => !renderNodeIdSet.has(nodeId)),
    [queryLinkedNodeIdsMappable, renderNodeIdSet]
  );
  const hiddenQueryLinkedNodeIdsExpandable = useMemo(() => {
    if (!hiddenQueryLinkedNodeIds.length) return [] as string[];
    const unresolvedSet = new Set(
      queryLinkedNodeResolution.unresolvedCandidates.map((nodeId) => resolveLinkedNodeId(nodeId)).filter(Boolean)
    );
    return hiddenQueryLinkedNodeIds.filter((nodeId) => !unresolvedSet.has(nodeId));
  }, [hiddenQueryLinkedNodeIds, queryLinkedNodeResolution.unresolvedCandidates, resolveLinkedNodeId]);
  const queryUnresolvedCandidatePreview = useMemo(
    () => queryLinkedNodeResolution.unresolvedCandidates.slice(0, 4),
    [queryLinkedNodeResolution.unresolvedCandidates]
  );
  const queryLinkedNodes = useMemo(
    () =>
      queryLinkedNodeIdsInView
        .map((nodeId) => renderModel.nodes.find((node) => node.id === nodeId) || null)
        .filter((item): item is GraphRenderNode => Boolean(item)),
    [queryLinkedNodeIdsInView, renderModel.nodes]
  );
  const queryContextSummary = useMemo(
    () =>
      Object.entries(queryResult?.context_data || {})
        .map(([name, rows]) => ({ name, count: Array.isArray(rows) ? rows.length : 0 }))
        .filter((item) => item.count > 0)
        .sort((left, right) => right.count - left.count),
    [queryResult?.context_data]
  );
  const edgeKindOptions = useMemo(
    () =>
      EDGE_KIND_OPTIONS.some((item) => item.key === 'other')
        ? EDGE_KIND_OPTIONS
        : [...EDGE_KIND_OPTIONS, { key: 'other' as GraphRenderEdge['kind'], label: '其他关系' }],
    []
  );

  const switchToOverview = useCallback(() => {
    setRenderMode('overview');
    setFocusedCommunityId(null);
    setFocusPeerCommunityId(null);
    setDrilldownEntityId(null);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, []);

  const expandNodeNeighborhood = useCallback(
    async (nodeId: string, depth = 1) => {
      const normalized = cleanText(nodeId);
      if (!selectedFileHash || !normalized) return;

      setNeighborhoodLoading(true);
      try {
        const neighborhood = await fetchModule4FileNeighborhood(selectedFileHash, normalized, {
          depth: Math.max(1, depth),
          relationTypes: DEFAULT_GRAPH_RELATION_TYPES,
          limit: 360,
        });
        startTransition(() => {
          setQueryOverlayGraphData((previous) =>
            previous ? mergeGraphSnapshots(previous, neighborhood) : neighborhood
          );
          setRenderMode('overview');
          setFocusedCommunityId(null);
          setFocusPeerCommunityId(null);
          setDrilldownEntityId(null);
          setSelectedNodeId(normalized);
          setSelectedEdgeId(null);
        });
      } catch (loadError) {
        const message = loadError instanceof Error ? loadError.message : '扩展节点邻域失败';
        setError(message);
      } finally {
        setNeighborhoodLoading(false);
      }
    },
    [selectedFileHash]
  );

  const expandHiddenQueryHits = useCallback(async () => {
    if (!selectedFileHash || hiddenQueryLinkedNodeIdsExpandable.length === 0) return;
    setExpandingHiddenHits(true);
    try {
      let mergedNeighborhood: Module4GraphResponse | null = null;
      for (const nodeId of hiddenQueryLinkedNodeIdsExpandable.slice(0, MAX_HIDDEN_QUERY_HIT_EXPAND)) {
        const neighborhood = await fetchModule4FileNeighborhood(selectedFileHash, nodeId, {
          depth: 1,
          relationTypes: DEFAULT_GRAPH_RELATION_TYPES,
          limit: 260,
        });
        mergedNeighborhood = mergedNeighborhood ? mergeGraphSnapshots(mergedNeighborhood, neighborhood) : neighborhood;
      }
      if (mergedNeighborhood) {
        startTransition(() => {
          setQueryOverlayGraphData((previous) =>
            previous
              ? mergeGraphSnapshots(previous, mergedNeighborhood as Module4GraphResponse)
              : (mergedNeighborhood as Module4GraphResponse)
          );
          const firstHidden = hiddenQueryLinkedNodeIdsExpandable[0];
          if (firstHidden) {
            setSelectedNodeId(firstHidden);
            setSelectedEdgeId(null);
          }
        });
      }
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : '扩展隐藏命中节点失败';
      setQueryError(message);
    } finally {
      setExpandingHiddenHits(false);
    }
  }, [hiddenQueryLinkedNodeIdsExpandable, selectedFileHash]);

  const runGraphQuery = useCallback(async () => {
    const trimmedQuery = cleanText(queryText);
    if (!selectedFileHash) {
      setQueryError('请先选择一个已构建完成的 GraphRAG 文件再执行查询。');
      return;
    }
    if (!trimmedQuery) {
      setQueryError('请输入要检索的问题。');
      return;
    }

    if (showControlDrawer) {
      setIsControlDrawerOpen(false);
    }
    setQueryLoading(true);
    setQueryError('');
    const requestedMode = queryMode;
    try {
      const response = await searchModule4GraphRag({
        fileHash: selectedFileHash,
        query: trimmedQuery,
        mode: requestedMode,
        communityLevel: maxCommunityLevel ?? 2,
      });
      const linkedNodeCandidates = (response.linked_node_ids || [])
        .map((nodeId) => resolveLinkedNodeId(nodeId))
        .filter(Boolean);
      startTransition(() => {
        setQueryResult(response);
        setLastRequestedQueryMode(requestedMode);
        setQueryFocusIndex(0);

        const firstLinkedNodeId = linkedNodeCandidates.find((nodeId) => allGraphNodeIdSet.has(String(nodeId)));
        if (firstLinkedNodeId) {
          const normalizedNodeId = String(firstLinkedNodeId);
          setSelectedNodeId(normalizedNodeId);
          setSelectedEdgeId(null);
        } else {
          setSelectedNodeId(null);
          setSelectedEdgeId(null);
        }
      });
    } catch (queryLoadError) {
      setQueryResult(null);
      const message = queryLoadError instanceof Error ? queryLoadError.message : 'GraphRAG 查询失败';
      setQueryError(message);
    } finally {
      setQueryLoading(false);
    }
  }, [allGraphNodeIdSet, maxCommunityLevel, queryMode, queryText, resolveLinkedNodeId, selectedFileHash, showControlDrawer]);

  const focusQueryLinkedNode = useCallback(
    (offset: number) => {
      const total = queryLinkedNodeIdsInView.length;
      if (!total) return;
      const base = Number.isFinite(queryFocusIndex) ? queryFocusIndex : 0;
      const next = ((base + offset) % total + total) % total;
      const nextNodeId = queryLinkedNodeIdsInView[next];
      if (nextNodeId) {
        setSelectedNodeId(nextNodeId);
        setSelectedEdgeId(null);
      }
      setQueryFocusIndex(next);
    },
    [queryFocusIndex, queryLinkedNodeIdsInView]
  );

  const refresh = useCallback(async () => {
    const loadSeq = beginGraphLoad();
    setLoading(true);
    setError('');
    try {
      const filesResponse = await fetchModule4GraphFiles({ limit: 200 });
      if (!isCurrentGraphLoad(loadSeq)) return;
      const files = filesResponse.items || [];
      setGraphFiles(files);

      const readyGraphRAGFiles = dedupePreferredGraphFiles(files.filter((item) => isGraphRAGFile(item)));
      const readyFinalGraphRAGFiles = readyGraphRAGFiles.filter(isFinalGraphRAGFile);
      const readyFiles = readyFinalGraphRAGFiles.length
        ? readyFinalGraphRAGFiles
        : readyGraphRAGFiles.length
          ? readyGraphRAGFiles
          : dedupePreferredGraphFiles(files.filter(isGraphRenderableFile));
      const privateReadyFiles = readyFiles.filter((item) => !isPublicCaseFile(item));
      const publicReadyFiles = readyFiles.filter(isPublicCaseFile);
      const activeFileHash = getActiveExtractionFileHash();
      const fallbackHash = privateReadyFiles[0]?.file_hash || publicReadyFiles[0]?.file_hash || '';
      const currentFileHash = selectedFileHashRef.current;
      const preferredHash =
        (currentFileHash && readyFiles.some((item) => item.file_hash === currentFileHash) && currentFileHash) ||
        (activeFileHash && readyFiles.some((item) => item.file_hash === activeFileHash) && activeFileHash) ||
        fallbackHash;

      setSelectedFileHash(preferredHash);
      const nextGraph = preferredHash
        ? await fetchModule4FileGraph(preferredHash, {
            nodeTypes: DEFAULT_GRAPH_NODE_TYPES,
            relationTypes: DEFAULT_GRAPH_RELATION_TYPES,
            limitNodes: 1200,
            limitEdges: 2400,
          })
        : await fetchModule4Graph({
            nodeTypes: DEFAULT_GRAPH_NODE_TYPES,
            relationTypes: DEFAULT_GRAPH_RELATION_TYPES,
            limitNodes: 1200,
            limitEdges: 2400,
          });
      if (!isCurrentGraphLoad(loadSeq)) return;

      setBaselineGraphData(nextGraph);
      setQueryOverlayGraphData(null);
      setRenderMode('overview');
      setFocusedCommunityId(null);
      setFocusPeerCommunityId(null);
      setDrilldownEntityId(null);
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
      setQueryResult(null);
      setLastRequestedQueryMode(null);
      setQueryError('');
      setQueryFocusIndex(0);
    } catch (loadError) {
      if (!isCurrentGraphLoad(loadSeq)) return;
      const message = loadError instanceof Error ? loadError.message : '刷新图谱工作台失败';
      setError(message);
    } finally {
      if (isCurrentGraphLoad(loadSeq)) setLoading(false);
    }
  }, [beginGraphLoad, isCurrentGraphLoad]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!queryResult) return;
    if (!queryLinkedNodeIdsInView.length) {
      setQueryFocusIndex(0);
      return;
    }
    setQueryFocusIndex((previous) => {
      if (!Number.isFinite(previous)) return 0;
      if (previous < 0) return 0;
      if (previous >= queryLinkedNodeIdsInView.length) return queryLinkedNodeIdsInView.length - 1;
      return previous;
    });
    if (!selectedNodeId || !queryLinkedNodeIdsInView.includes(selectedNodeId)) {
      setSelectedNodeId(queryLinkedNodeIdsInView[0]);
      setSelectedEdgeId(null);
    }
  }, [queryLinkedNodeIdsInView, queryResult, selectedNodeId]);

  useEffect(() => {
    if (!selectedNodeId) {
      setNodeDetail(null);
      setNodeDetailError('');
      setNodeDetailLoading(false);
      return;
    }

    let cancelled = false;
    setNodeDetailLoading(true);
    setNodeDetailError('');

    void fetchModule4NodeDetail(selectedNodeId, {
      fileHash: selectedFileHash || undefined,
      depth: 1,
      limit: 240,
    })
      .then((response) => {
        if (cancelled) return;
        setNodeDetail(response);
      })
      .catch((detailError) => {
        if (cancelled) return;
        const message = detailError instanceof Error ? detailError.message : '加载节点详情失败';
        setNodeDetail(null);
        setNodeDetailError(message);
      })
      .finally(() => {
        if (!cancelled) setNodeDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedFileHash, selectedNodeId]);

  const selectedClusterLabel = cleanText(selectedNodeMeta?.cluster_label || selectedCommunity?.label || '未归属');
  const showPartialHint = Boolean(selectedFile && graphBuildModeOf(selectedFile) === 'graphrag_partial');
  const selectedFileMetadata = (selectedFile?.metadata || {}) as Record<string, unknown>;
  const inputSnapshot = (selectedFileMetadata.input_snapshot || {}) as Record<string, unknown>;
  const artifactStageStatus = (selectedFileMetadata.artifact_stage_status || {}) as Record<string, unknown>;
  const artifactStages = (artifactStageStatus.stages || {}) as Record<string, { exists?: boolean; path?: string; size_bytes?: number }>;
  const failureMeta = (selectedFileMetadata.failure || {}) as Record<string, unknown>;
  const stageNameMap: Record<string, string> = {
    create_base_text_units: '基础文本切分',
    create_base_extracted_entities: '基础实体抽取',
    create_final_entities: '最终实体汇总',
    create_final_relationships: '最终关系汇总',
    create_final_communities: '社区聚类',
    create_final_community_reports: '社区报告',
    indexing: '索引构建',
    normalizing: '文本归一化',
    importing_graph: '图谱导入',
    validating_runtime: '运行时校验',
    processing_documents: '处理文档',
  };
  const missingArtifactStages = Object.entries(artifactStages).filter(([, value]) => !value?.exists);
  const formatStageLabel = (stageName: string) => stageNameMap[stageName] || stageName;
  const totalLinkedNodeCount = queryLinkedNodeIdsMappable.length;
  const hiddenLinkedNodeRawCount = hiddenQueryLinkedNodeIds.length;
  const hiddenLinkedNodeCount = hiddenQueryLinkedNodeIdsExpandable.length;
  const queryResolutionStrategyLabel = useMemo(() => {
    switch (queryLinkedNodeResolution.resolutionStrategy) {
      case 'storage_first_then_artifact':
        return '存储优先，产物兜底';
      case 'storage_only':
        return '仅存储映射';
      case 'artifact_only':
        return '仅产物映射';
      case 'identity_fallback':
        return '未映射，使用原始候选';
      default:
        return queryLinkedNodeResolution.resolutionStrategy || '未提供';
    }
  }, [queryLinkedNodeResolution.resolutionStrategy]);
  const queryExecutionMeta = useMemo(
    () =>
      buildQueryExecutionMeta({
        source: queryResult?.source,
        requestedMode: lastRequestedQueryMode,
        effectiveMode: queryResult?.mode || null,
      }),
    [lastRequestedQueryMode, queryResult?.mode, queryResult?.source]
  );
  const queryExecutionRequestedLabel = useMemo(
    () => queryModeLabel(queryExecutionMeta.requestedMode),
    [queryExecutionMeta.requestedMode]
  );
  const queryExecutionEffectiveLabel = useMemo(
    () => queryModeLabel(queryExecutionMeta.effectiveMode),
    [queryExecutionMeta.effectiveMode]
  );
  const focusedQueryNodeId = queryLinkedNodeIdsInView[queryFocusIndex] || '';

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const targetWindow = window as Window & { __module4Debug?: Record<string, unknown> };
    targetWindow.__module4Debug = {
      selectedFileHash: selectedFileHash || null,
      selectedFileName: selectedFile ? displayFileName(selectedFile) : '租户总图',
      renderMode,
      focusedCommunityId,
      focusPeerCommunityId,
      drilldownEntityId,
      selectedNodeId,
      selectedEdgeId,
      enabledEdgeKinds,
      collapseCommunityMembers,
      maxCommunityLevel,
      graphDataStats: {
        nodeCount: graphData.nodes.length,
        edgeCount: graphData.edges.length,
        byNodeType: graphData.stats?.by_node_type || {},
        byRelationType: graphData.stats?.by_relation_type || {},
      },
      renderModelStats: {
        nodeCount: renderModel.nodes.length,
        edgeCount: renderModel.edges.length,
        byNodeKind: renderModel.nodes.reduce<Record<string, number>>((acc, node) => {
          const key = String(node.kind || 'unknown');
          acc[key] = (acc[key] || 0) + 1;
          return acc;
        }, {}),
        byEdgeKind: renderModel.edges.reduce<Record<string, number>>((acc, edge) => {
          const key = String(edge.kind || 'unknown');
          acc[key] = (acc[key] || 0) + 1;
          return acc;
        }, {}),
      },
      displayModelStats: {
        nodeCount: displayRenderModel.nodes.length,
        edgeCount: displayRenderModel.edges.length,
      },
      query: {
        hasResult: Boolean(queryResult),
        linkedNodeIdsAll: queryLinkedNodeIdsAll.length,
        linkedNodeIdsInView: queryLinkedNodeIdsInView.length,
        hiddenLinkedNodeIds: hiddenQueryLinkedNodeIds.length,
        focusIndex: queryFocusIndex,
        focusedNodeId: focusedQueryNodeId || null,
      },
      timestamp: new Date().toISOString(),
    };
  }, [
    collapseCommunityMembers,
    drilldownEntityId,
    enabledEdgeKinds,
    focusPeerCommunityId,
    focusedCommunityId,
    focusedQueryNodeId,
    graphData.edges.length,
    graphData.nodes.length,
    graphData.stats?.by_node_type,
    graphData.stats?.by_relation_type,
    displayRenderModel.edges.length,
    displayRenderModel.nodes.length,
    hiddenQueryLinkedNodeIds.length,
    maxCommunityLevel,
    queryFocusIndex,
    queryLinkedNodeIdsAll.length,
    queryLinkedNodeIdsInView.length,
    queryResult,
    renderMode,
    renderModel.edges,
    renderModel.nodes,
    selectedEdgeId,
    selectedFile,
    selectedFileHash,
    selectedNodeId,
  ]);

  const controlButtonLabel = useUltraDenseHeader ? '控制' : '检索/控制';
  const refreshButtonLabel = loading ? '刷新中' : useUltraDenseHeader ? '刷新' : '刷新';
  const headerFileSelectorMaxWidthClass = useUltraDenseHeader
    ? 'max-w-[220px]'
    : useDenseHeader
      ? 'max-w-[260px]'
      : 'max-w-[300px]';
  const headerChromeClass = useUltraDenseHeader
    ? 'pl-3 pr-3 py-1'
    : useDenseHeader
      ? 'pl-4 pr-4 py-1.5'
      : 'pl-4 pr-6 py-1.5';
  const headerGapClass = useUltraDenseHeader ? 'gap-2' : 'gap-3';
  const detailAsideWidthClass = useUltraDenseDetailPanel ? 'w-[17rem]' : useDenseDetailPanel ? 'w-[18rem]' : 'w-80';
  const detailSectionPaddingClass = useUltraDenseDetailPanel ? 'px-3 pb-3' : 'px-4 pb-4';
  const detailHeaderPaddingClass = useUltraDenseDetailPanel ? 'px-3 pt-2' : 'px-4 pt-2';
  const detailCardGapClass = useUltraDenseDetailPanel ? 'space-y-2.5' : 'space-y-3';

  return (
    <section ref={workbenchRef} className="module4-workbench relative flex h-[100dvh] w-full flex-col overflow-hidden bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-module2-primary-bg/40 via-module2-bg to-module2-primary-bg/40 p-0 text-module2-text-primary dark:bg-slate-950">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        {/* Enhanced bright theme background elements for more highlights and depth (Copied from Mod 2) */}
        <div className="absolute -top-[10%] -left-[5%] w-[60%] h-[60%] rounded-full bg-gradient-to-br from-blue-400/20 to-sky-500/20 blur-[100px] dark:from-blue-500/10 dark:to-sky-500/10" />
        <div className="absolute top-[10%] -right-[5%] w-[50%] h-[50%] rounded-full bg-gradient-to-bl from-blue-400/20 to-cyan-500/15 blur-[100px] dark:from-blue-500/10 dark:to-cyan-500/10" />
        <div className="absolute bottom-[0%] left-[10%] w-[50%] h-[50%] rounded-full bg-gradient-to-tr from-sky-400/15 to-cyan-400/15 blur-[100px] dark:from-sky-500/10 dark:to-cyan-500/10" />
        <div className="absolute top-[30%] left-[30%] w-[40%] h-[40%] rounded-full bg-cyan-400/10 blur-[80px] dark:bg-blue-500/10" />
        <div className="absolute -bottom-[10%] right-[10%] w-[40%] h-[40%] rounded-full bg-blue-400/20 blur-[100px] dark:bg-blue-900/10" />
        <div
            className="absolute inset-0 opacity-[0.6] mix-blend-multiply dark:opacity-[0.2] dark:mix-blend-normal bg-[radial-gradient(circle_at_1px_1px,_rgba(15,23,42,0.08)_1px,_transparent_0)] bg-[length:32px_32px]"
        />
      </div>
      {/* 顶部紧凑控制栏*/}
      <header className={cn("relative z-10 flex shrink-0 items-center justify-between bg-[#fbfcfd]/90 backdrop-blur-xl border-b border-slate-200/40 shadow-[0_2px_12px_rgba(0,0,0,0.03)] dark:bg-slate-950/95 dark:border-white/5 dark:shadow-[0_4px_16px_rgba(0,0,0,0.4)]", headerChromeClass)}>
        <div className={cn("flex flex-1 min-w-0 items-center", headerGapClass)}>
          <div className={cn("flex shrink-0 items-center translate-y-[2px]", useUltraDenseHeader ? "-ml-2.5" : "-ml-5")}>
            <img 
                src={module4Svg} 
                alt="Knowledge Graph" 
                className={cn(
                  "w-auto origin-left scale-[3.0] translate-y-1 object-contain transition-all duration-300",
                  useUltraDenseHeader ? "h-[24px] mr-[72px]" : useDenseHeader ? "h-[28px] mr-[96px]" : "h-[32px] mr-[110px]",
                )} 
            />
            <div className={cn(
              "flex shrink-0 items-center space-x-[1px] font-['Microsoft_YaHei'] font-bold tracking-widest -ml-0.5 translate-y-[2px] whitespace-nowrap",
              useUltraDenseHeader ? "text-[15px]" : useDenseHeader ? "text-[18px]" : "text-[20px]",
            )}>
                <span className="text-[#334155] dark:text-slate-200">全域</span>
                <span className="text-[#3b82f6] dark:text-blue-400">知识图谱</span>
            </div>
          </div>
          
          <div className={cn("flex flex-1 min-w-0 items-center justify-end ml-4", useUltraDenseHeader ? "gap-1" : "gap-2")}>
            {shouldUseControlDrawer && (
              <button
                type="button"
                onClick={toggleControlDrawer}
                className={cn(
                  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white/90 text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors hover:bg-slate-50 hover:border-slate-300 active:scale-95 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600",
                  useUltraDenseHeader ? "h-[24px] px-2 text-[11px]" : "h-[28px] px-3 text-[12px]",
                )}
                title={showControlDrawer ? '收起检索/控制' : '打开检索/控制'}
                aria-label={showControlDrawer ? '收起检索/控制' : '打开检索/控制'}
              >
                {showControlDrawer ? <PanelRightClose size={useUltraDenseHeader ? 12 : 14} /> : <PanelRightOpen size={useUltraDenseHeader ? 12 : 14} />}
                <span className={cn(useUltraDenseHeader ? 'hidden md:inline' : 'hidden sm:inline')}>{controlButtonLabel}</span>
              </button>
            )}
            <div className="relative shrink min-w-0" ref={fileDropdownRef}>
              <button
                type="button"
                onClick={() => setIsFileDropdownOpen(!isFileDropdownOpen)}
                className={cn(
                  "flex h-[28px] w-full shrink cursor-pointer items-center justify-between gap-2 rounded-md border border-slate-200 bg-white/80 px-2.5 text-[12px] text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] outline-none transition-colors hover:border-slate-300 hover:bg-white focus:border-blue-500 focus:bg-white focus:ring-1 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-slate-600",
                  useUltraDenseHeader ? "h-[24px] text-[11px]" : "",
                  headerFileSelectorMaxWidthClass,
                )}
              >
                <div className="flex items-center gap-2 truncate">
                  {selectedFile ? (
                    <>
                      <img src={getFileIcon(selectedFile.file_name)} alt="icon" className="h-3.5 w-3.5 shrink-0 object-contain" />
                      <span className="truncate">{displayFileName(selectedFile)}</span>
                      {isPublicCaseFile(selectedFile) ? (
                        <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">
                          案例
                        </span>
                      ) : null}
                    </>
                  ) : (
                    <>
                      <Network size={14} className="shrink-0 text-slate-500 dark:text-slate-400" />
                      <span className="truncate">租户总图</span>
                    </>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {hiddenGraphFileReasons.length > 0 ? (
                    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                      未展示{hiddenGraphFileReasons.length}
                    </span>
                  ) : null}
                  <ChevronDown size={14} className="shrink-0 text-slate-400" />
                </div>
              </button>
              
              {isFileDropdownOpen && (
                <div className="absolute right-0 top-full z-50 mt-1 w-max min-w-[300px] max-w-[480px] overflow-hidden rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800">
                  <button
                    type="button"
                    onClick={() => handleFileSelect('')}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
                      selectedFileHash === ''
                        ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                        : 'text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700/50'
                    }`}
                  >
                    <Network size={14} className="shrink-0 text-slate-500 dark:text-slate-400" />
                    <span className="truncate">租户总图</span>
                  </button>
                  {visiblePrivateFiles.length > 0 ? (
                    <div className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400">
                      我的图谱
                    </div>
                  ) : null}
                  {visiblePrivateFiles.map((item) => (
                    <button
                      key={item.graph_file_id}
                      type="button"
                      onClick={() => handleFileSelect(item.file_hash)}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
                        selectedFileHash === item.file_hash
                          ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                          : 'text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700/50'
                      }`}
                    >
                      <img src={getFileIcon(item.file_name)} alt="icon" className="h-3.5 w-3.5 shrink-0 object-contain" />
                      <span className="truncate">{displayFileName(item)}</span>
                    </button>
                  ))}
                  {visiblePublicCaseFiles.length > 0 ? (
                    <div className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400">
                      案例图谱
                    </div>
                  ) : null}
                  {visiblePublicCaseFiles.map((item) => (
                    <button
                      key={item.graph_file_id}
                      type="button"
                      onClick={() => handleFileSelect(item.file_hash)}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
                        selectedFileHash === item.file_hash
                          ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                          : 'text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700/50'
                      }`}
                    >
                      <img src={getFileIcon(item.file_name)} alt="icon" className="h-3.5 w-3.5 shrink-0 object-contain" />
                      <span className="truncate">{displayFileName(item)}</span>
                      <span className="ml-auto rounded bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">
                        只读
                      </span>
                    </button>
                  ))}

                  <div className="mx-2 my-1 h-px bg-slate-200 dark:bg-slate-700" />
                  <div className="px-3 pb-1 pt-0.5 text-[10px] leading-5 text-slate-500 dark:text-slate-400">
                    支持渲染的文件类型：`docx` / `pdf` / `txt` / `md`。`xls` / `xlsx` / `csv` 不参与知识图谱渲染。                  </div>

                  {hiddenGraphFileReasonPreview.length > 0 ? (
                    <>
                      <div className="px-3 pt-1 text-[10px] font-semibold text-slate-600 dark:text-slate-300">
                        未展示文件及原因
                      </div>
                      <div className="max-h-44 space-y-1 overflow-auto px-2 py-1.5">
                        {hiddenGraphFileReasonPreview.map(({ item, reason, code }) => (
                          <div
                            key={`${item.graph_file_id}:${code}`}
                            className="rounded border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] leading-4 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                          >
                            <div className="truncate font-medium text-slate-700 dark:text-slate-200">{displayFileName(item)}</div>
                            <div className="mt-0.5 text-slate-500 dark:text-slate-400">{reason}</div>
                          </div>
                        ))}
                      </div>
                      {hiddenGraphFileReasons.length > hiddenGraphFileReasonPreview.length ? (
                        <div className="px-3 pb-2 text-[10px] text-slate-500 dark:text-slate-400">
                          仅展示前 {hiddenGraphFileReasonPreview.length} 条，剩余 {hiddenGraphFileReasons.length - hiddenGraphFileReasonPreview.length} 条可通过刷新后查看。                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loading}
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-md border border-slate-200 bg-white font-medium text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:bg-slate-50 hover:border-slate-300 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200",
                useUltraDenseHeader ? "h-[24px] px-2 text-[11px]" : "h-[28px] px-3 text-[12px]",
              )}
            >
              <RefreshCw size={useUltraDenseHeader ? 12 : 14} className={loading ? 'animate-spin' : ''} />
              <span className={cn(useUltraDenseHeader ? 'hidden md:inline' : 'hidden sm:inline')}>{refreshButtonLabel}</span>
            </button>
          </div>
        </div>
      </header>

      {/* 主体工作区*/}
      <div className="relative flex flex-1 overflow-hidden">
        {showControlDrawer && (
          <button
            type="button"
            onClick={closeControlDrawer}
            className="absolute inset-0 z-30 bg-slate-950/16 backdrop-blur-[2px]"
            aria-label="关闭检索与控制抽屉"
          />
        )}
        
        {/* 左侧控制栏：检索与视图控制 */}
        <aside
          className={cn(
            "flex shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white/95 backdrop-blur-md dark:border-white/5 dark:bg-slate-950/95",
            showDockedControlPanel
              ? "relative w-80"
              : showControlDrawer
                ? "absolute inset-y-3 left-3 z-40 w-[min(320px,calc(100%-24px))] rounded-[24px] border border-slate-200/70 shadow-[0_24px_60px_-28px_rgba(15,23,42,0.32)] dark:border-white/[0.08] dark:shadow-[0_28px_72px_-34px_rgba(2,6,23,0.9)]"
                : "hidden",
          )}
        >
            <div className="flex h-11 shrink-0 items-center px-4 pt-2">
              <div className="flex w-full items-center justify-between">
                <h2 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">图谱检索</h2>
                {showControlDrawer && (
                  <button
                    type="button"
                    onClick={closeControlDrawer}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                    title="关闭检索与控制"
                    aria-label="关闭检索与控制"
                  >
                    <XCircle size={16} />
                  </button>
                )}
              </div>
            </div>
          
          <div className="px-4 pb-4">
            <p className="text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
              {QUERY_MODE_OPTIONS.find((item) => item.value === queryMode)?.description}
            </p>
            <div className="mt-3">
              <textarea
                value={queryText}
                onChange={(event) => setQueryText(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                    event.preventDefault();
                    void runGraphQuery();
                  }
                }}
                rows={2}
                placeholder="输入问题，按 Ctrl+Enter 检索..."
                className="w-full resize-none rounded-md border border-slate-200 bg-white px-3 py-2.5 text-[11px] text-slate-700 shadow-sm outline-none transition-all placeholder:text-slate-400 hover:border-slate-300 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 dark:hover:border-slate-600"
              />
            </div>
            <div className="mt-2.5 flex items-center justify-between gap-2.5">
              <select
                value={queryMode}
                onChange={(event) => setQueryMode(event.target.value as Module4GraphRagQueryMode)}
                className="h-8 flex-1 cursor-pointer rounded-md border border-slate-200 bg-white px-2.5 text-[11px] text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] outline-none transition-colors hover:border-slate-300 hover:bg-slate-50 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600"
              >
                {QUERY_MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value} className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100">{option.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void runGraphQuery()}
                disabled={queryLoading || !selectedFileHash}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-blue-600 px-4 text-[11px] font-medium text-white shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-800 dark:disabled:text-slate-600"
              >
                <Search size={12} className={queryLoading ? 'animate-pulse' : ''} />
                  {queryLoading ? '查询中' : '执行查询'}
              </button>
            </div>
            
            {queryError && (
              <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-[11px] text-red-700 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300">
                {queryError}
              </div>
            )}

            {queryResult && (
              <div className="mt-4 border-t border-slate-100 pt-4 dark:border-slate-800">
                  <div className="flex items-center justify-between">
                    <h3 className="text-[11px] font-medium text-slate-700 dark:text-slate-200">检索结果</h3>
                    <button
                      onClick={clearQueryResult}
                      className="text-[10px] text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                    >
                    清空
                  </button>
                </div>
                <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-2.5 dark:border-slate-700 dark:bg-slate-900">
                    <div className="whitespace-pre-wrap break-words text-[11px] leading-5 text-slate-700 dark:text-slate-100">
                      {cleanText(queryResult.answer) || '未返回可展示答案。'}
                    </div>
                </div>

                <div className="mt-2 rounded-md border border-slate-200 bg-white p-2 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
                  <div>请求模式: {queryExecutionRequestedLabel}</div>
                  <div>
                    实际执行: {queryExecutionEffectiveLabel}
                    {queryExecutionMeta.usedFallback ? '（已触发回退）' : '（原生执行）'}
                  </div>
                  <div className="truncate">执行来源: {queryExecutionMeta.source || '未提供'}</div>
                </div>
                
                <div className="mt-2 rounded-md border border-slate-200 bg-white p-2 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
                  <div>
                    结果映射: 已解析{queryLinkedNodeResolution.resolvedCount}/{Math.max(queryLinkedNodeResolution.candidateCount, totalLinkedNodeCount)}
                    {queryLinkedNodeResolution.unresolvedCount > 0
                      ? `，未解析 ${queryLinkedNodeResolution.unresolvedCount}`
                      : '，全部可解析'}
                  </div>
                  <div>
                    映射策略: {queryResolutionStrategyLabel}
                    {queryLinkedNodeResolution.usedFallbackCandidates ? '（命中为空时回退候选）' : ''}
                  </div>
                  {queryUnresolvedCandidatePreview.length > 0 && (
                    <div className="mt-1 truncate text-slate-500 dark:text-slate-400">
                      未解析示例 {queryUnresolvedCandidatePreview.join('、')}
                    </div>
                  )}
                </div>

                {hiddenLinkedNodeRawCount > 0 && (
                  <div className="mt-3 rounded-md border border-amber-200 bg-amber-50/70 p-2.5 dark:border-amber-900/50 dark:bg-amber-950/20">
                    <div className="text-[10px] leading-5 text-amber-700 dark:text-amber-300">
                      {hiddenLinkedNodeCount > 0
                        ? `有 ${hiddenLinkedNodeCount}/${hiddenLinkedNodeRawCount} 个命中节点不在当前视图，可扩展邻域后查看（单次最多 ${MAX_HIDDEN_QUERY_HIT_EXPAND} 个）。`
                        : `有 ${hiddenLinkedNodeRawCount} 个命中节点未映射到当前图谱，暂不可扩展。`}
                    </div>
                    {hiddenLinkedNodeCount > 0 && (
                      <button
                        type="button"
                        onClick={() => void expandHiddenQueryHits()}
                        disabled={expandingHiddenHits || neighborhoodLoading}
                        className="mt-2 inline-flex h-7 items-center rounded-md border border-amber-300 bg-white px-2.5 text-[10px] font-medium text-amber-700 transition-colors hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300 dark:hover:bg-amber-900/40"
                      >
                        {expandingHiddenHits ? '正在扩展命中节点...' : '扩展隐藏命中节点'}
                      </button>
                    )}
                  </div>
                )}

                {queryLinkedNodes.length > 0 && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[10px] text-slate-500">
                      <span>命中节点 ({queryLinkedNodeIdsInView.length}/{totalLinkedNodeCount})</span>
                      <div className="flex gap-1">
                        <button onClick={() => focusQueryLinkedNode(-1)} className="hover:text-slate-700 dark:hover:text-slate-300">上一条</button>
                        <button onClick={() => focusQueryLinkedNode(1)} className="hover:text-slate-700 dark:hover:text-slate-300">下一条</button>
                      </div>
                    </div>
                    <div className="mt-1.5 max-h-32 space-y-1 overflow-auto pr-1">
                      {queryLinkedNodes.slice(0, 24).map((node) => (
                        <button
                          key={node.id}
                          onClick={() => {
                            setSelectedNodeId(node.id);
                            setSelectedEdgeId(null);
                            const nextIndex = queryLinkedNodeIdsInView.findIndex((item) => item === node.id);
                            if (nextIndex >= 0) setQueryFocusIndex(nextIndex);
                          }}
                          className={`w-full truncate rounded border px-2 py-1.5 text-left text-[10px] transition ${
                            focusedQueryNodeId === node.id
                              ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/30 dark:text-blue-300'
                              : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'
                          }`}
                        >
                          {node.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="mx-4 my-2 h-px bg-slate-200/60 dark:bg-slate-800/60" />

          <div className="flex h-11 shrink-0 items-center px-4 pt-2">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">视图控制</h2>
          </div>

          <div className="px-4 pb-4">
            <div className="space-y-5">
              <div>
                <label className="mb-2 block text-[10px] font-medium text-slate-500 dark:text-slate-400">社区层级</label>
                <select
                  value={maxCommunityLevel === null ? 'all' : String(maxCommunityLevel)}
                  onChange={(event) => {
                    const value = event.target.value;
                    setMaxCommunityLevel(value === 'all' ? null : Number(value));
                    setSelectedNodeId(null);
                  }}
                  className="h-8 w-full cursor-pointer rounded-md border border-slate-200 bg-white px-2.5 text-[11px] text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] outline-none transition-colors hover:border-slate-300 hover:bg-slate-50 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600"
                >
                  <option value="all" className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100">全部层级</option>
                  {communityLevelOptions.map((level) => (
                    <option key={level} value={String(level)} className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100">第 {level} 层</option>
                  ))}
                </select>
              </div>

              <label className="flex cursor-pointer items-center gap-2.5">
                <div className="relative inline-flex h-[18px] w-8 items-center rounded-full bg-slate-200 transition-colors dark:bg-slate-700 has-[:checked]:bg-blue-600 dark:has-[:checked]:bg-blue-500">
                  <input
                    type="checkbox"
                    className="peer sr-only"
                    checked={collapseCommunityMembers}
                    onChange={(event) => {
                      setCollapseCommunityMembers(event.target.checked);
                      setSelectedNodeId(null);
                    }}
                  />
                  <span className="inline-block h-3.5 w-3.5 translate-x-[3px] rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-[15px]" />
                </div>
                <span className="text-[11px] font-medium text-slate-700 dark:text-slate-200">折叠社区成员</span>
              </label>

              <div>
                <label className="mb-2 block text-[10px] font-medium text-slate-500 dark:text-slate-400">标签展示</label>
                <select
                  value={labelMode}
                  onChange={(event) => setLabelMode(event.target.value as GraphLabelMode)}
                  className="h-8 w-full cursor-pointer rounded-md border border-slate-200 bg-white px-2.5 text-[11px] text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] outline-none transition-colors hover:border-slate-300 hover:bg-slate-50 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600"
                >
                  {LABEL_MODE_OPTIONS.map((option) => (
                    <option key={option.key} value={option.key} className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100">
                      {option.label}
                    </option>
                  ))}
                </select>
                <p className="mt-1.5 text-[10px] leading-4 text-slate-500 dark:text-slate-400">
                  {LABEL_MODE_OPTIONS.find((option) => option.key === labelMode)?.description}
                </p>
              </div>

              <div className="h-px w-full bg-slate-100 dark:bg-slate-800/60" />

                <div>
                  <label className="mb-2.5 block text-[10px] font-medium text-slate-500 dark:text-slate-400">关系筛选</label>
                  <div className="space-y-3">
                  {edgeKindOptions.map((option) => {
                    const checked = enabledEdgeKinds.includes(option.key);
                    return (
                      <label key={option.key} className="group flex cursor-pointer items-center gap-2.5">
                        <div className={`flex h-3.5 w-3.5 items-center justify-center rounded border transition-colors ${checked ? 'border-blue-600 bg-blue-600 dark:border-blue-500 dark:bg-blue-500' : 'border-slate-300 bg-white group-hover:border-slate-400 dark:border-slate-600 dark:bg-slate-900 dark:group-hover:border-slate-500'}`}>
                          <input
                            type="checkbox"
                            className="peer sr-only"
                            checked={checked}
                            onChange={(event) => {
                              setEnabledEdgeKinds((previous) => {
                                if (event.target.checked) return [...new Set([...previous, option.key])];
                                const next = previous.filter((item) => item !== option.key);
                                return next.length ? next : previous;
                              });
                            }}
                          />
                          {checked && <svg className="h-2.5 w-2.5 text-white" viewBox="0 0 14 14" fill="none"><path d="M3 7.5L5.5 10L11 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                        </div>
                        <span className="text-[11px] text-slate-600 transition-colors group-hover:text-slate-900 dark:text-slate-300 dark:group-hover:text-slate-100">{option.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </aside>

        {/* 中心画布视口 */}
        <main className="relative flex flex-1 flex-col bg-white dark:bg-slate-900/50">
          {error ? (
            <div className="flex h-full w-full items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <span className="rounded-full bg-red-100 p-3 text-red-600 dark:bg-red-900/30 dark:text-red-400">
                  <Network size={24} />
                </span>
                <p className="text-[13px] text-red-600 dark:text-red-400">{error}</p>
              </div>
            </div>
          ) : displayRenderModel.nodes.length === 0 ? (
            <div className="flex h-full w-full items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <span className="rounded-full bg-slate-100 p-3 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                  <Network size={24} />
                </span>
                <p className="text-[13px] text-slate-500 dark:text-slate-400">
                  当前图谱没有可渲染节点。请先选择 GraphRAG 文件，或等待索引完成。
                </p>
              </div>
            </div>
          ) : (
            <Module4GraphCanvasG6
              model={displayRenderModel}
              labelMode={labelMode}
              selectedNodeId={selectedNodeId}
              queryHitNodeIds={queryLinkedNodeIdsInView}
              onSelectNode={(nodeId) => {
                setSelectedNodeId(nodeId);
                if (nodeId) setSelectedEdgeId(null);
              }}
              selectedEdgeId={selectedEdgeId}
              onSelectEdge={(edgeId) => {
                setSelectedEdgeId(edgeId);
                if (edgeId) setSelectedNodeId(null);
              }}
              className="h-full w-full outline-none"
            />
          )}
        </main>

        {/* 右侧详情面板 */}
        {(selectedNode || selectedEdge) && (
          <aside className={cn("flex shrink-0 flex-col overflow-y-auto border-l border-slate-200 bg-white/95 backdrop-blur-md dark:border-white/5 dark:bg-slate-950/95", detailAsideWidthClass)}>
            <div className={cn("flex h-11 shrink-0 items-center justify-between", detailHeaderPaddingClass)}>
              <h2 className={DETAIL_PANEL_SECTION_TITLE_CLASS}>当前选中</h2>
              {renderMode !== 'overview' && (
                <button
                  type="button"
                  onClick={switchToOverview}
                  className={DETAIL_PANEL_ACTION_NEUTRAL_CLASS}
                >
                  返回总览
                </button>
              )}
            </div>

            <div className={detailSectionPaddingClass}>
              {selectedNode ? (
                <div className={cn("text-xs", detailCardGapClass)}>
                  <div className={DETAIL_PANEL_CARD_SOFT_CLASS}>
                    <div className={DETAIL_PANEL_LABEL_CLASS}>节点名称</div>
                    <div className="mt-1 text-[12px] font-semibold leading-5 text-slate-900 dark:text-slate-100">
                      {selectedNode.label}
                    </div>
                    {selectedNodePreview && (
                      <div className="mt-2 whitespace-pre-wrap break-words text-[11px] leading-5 text-slate-600 dark:text-slate-300">
                        {selectedNodePreview}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {selectedNode.kind === 'community' && (
                      <button
                        type="button"
                        onClick={() => void expandNodeNeighborhood(selectedNode.id, 2)}
                        className={DETAIL_PANEL_ACTION_VIOLET_CLASS}
                      >
                        进入社区聚焦
                      </button>
                    )}
                    {selectedNode.kind === 'entity' && (
                      <button
                        type="button"
                        onClick={() => void expandNodeNeighborhood(selectedNode.id, 2)}
                        className={DETAIL_PANEL_ACTION_SKY_CLASS}
                      >
                        进入实体钻取
                      </button>
                    )}
                    {selectedNode.communityId && selectedNode.kind !== 'community' && (
                      <button
                        type="button"
                        onClick={() => void expandNodeNeighborhood(String(selectedNode.communityId), 2)}
                        className={DETAIL_PANEL_ACTION_NEUTRAL_CLASS}
                      >
                        查看所属社区
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>类型</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>
                        {formatTypeName(selectedNodeMeta?.node_type_label || selectedNodeMeta?.node_type_key || selectedNode.kind)}
                      </div>
                    </div>
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>角色</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>{formatTypeName(selectedNode.role)}</div>
                    </div>
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>连接度</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>{selectedNode.degree}</div>
                    </div>
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>所属簇</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>{selectedClusterLabel}</div>
                    </div>
                  </div>

                  <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                    <div className={DETAIL_PANEL_LABEL_CLASS}>节点证据</div>
                    {nodeDetailLoading ? (
                      <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">正在加载证据...</div>
                    ) : nodeDetailError ? (
                      <div className="mt-2 text-[11px] text-amber-600 dark:text-amber-300">{nodeDetailError}</div>
                    ) : nodeDetailEvidence.length > 0 ? (
                      <div className="mt-2 max-h-48 space-y-1.5 overflow-auto pr-1">
                        {nodeDetailEvidence.slice(0, 6).map((evidence) => (
                          <div
                            key={evidence.evidence_id}
                            className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 text-[10px] leading-5 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                            title={cleanText(evidence.snippet)}
                          >
                            {cleanText(evidence.snippet) || '（空证据片段）'}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">暂无可用证据</div>
                    )}
                    {nodeDetailEdgeEvidenceCount > 0 && (
                      <div className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">
                        关联边证据条目 {nodeDetailEdgeEvidenceCount}
                      </div>
                    )}
                  </div>

                  {renderMode === 'community-focus' && selectedCommunity && (
                    <div className="rounded-md border border-violet-200 bg-violet-50/70 p-3 dark:border-violet-800/70 dark:bg-violet-950/30">
                      <div className="text-[10px] font-medium text-violet-700 dark:text-violet-300">社区聚焦</div>
                      <div className="mt-1 text-[11px] leading-5 text-slate-700 dark:text-slate-200">
                        成员数量：{selectedCommunity.entityCount} | 层级：{selectedCommunity.level}
                      </div>
                    </div>
                  )}
                  {renderMode === 'entity-drilldown' && (
                    <div className="rounded-md border border-sky-200 bg-sky-50/70 p-3 dark:border-sky-800/70 dark:bg-sky-950/30">
                      <div className="text-[10px] font-medium text-sky-700 dark:text-sky-300">实体钻取</div>
                      <div className="mt-1 text-[11px] leading-5 text-slate-700 dark:text-slate-200">
                        证据节点：{evidenceNodeCount}
                      </div>
                    </div>
                  )}
                </div>
              ) : selectedEdge ? (
                <div className={cn("text-xs", detailCardGapClass)}>
                  <div className={DETAIL_PANEL_CARD_SOFT_CLASS}>
                    <div className={DETAIL_PANEL_LABEL_CLASS}>关系标签</div>
                    <div className="mt-1 text-[12px] font-semibold leading-5 text-slate-900 dark:text-slate-100">
                      {selectedEdge.label}
                    </div>
                  </div>

                  {Boolean((selectedEdge.meta || {}).aggregated) && renderMode === 'overview' && (
                    <button
                      type="button"
                      onClick={() => {
                        void expandNodeNeighborhood(selectedEdge.source, 2);
                        if (selectedEdge.target !== selectedEdge.source) {
                          void expandNodeNeighborhood(selectedEdge.target, 2);
                        }
                      }}
                      className={DETAIL_PANEL_ACTION_VIOLET_CLASS}
                    >
                      进入关联社区聚焦
                    </button>
                  )}

                  <div className="grid grid-cols-2 gap-2">
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>关系类型</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>{formatTypeName(selectedEdge.kind)}</div>
                    </div>
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>权重</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>{selectedEdge.weight.toFixed(2)}</div>
                    </div>
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>置信度</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>{selectedEdge.strength.toFixed(2)}</div>
                    </div>
                    <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                      <div className={DETAIL_PANEL_LABEL_CLASS}>聚合关系</div>
                      <div className={DETAIL_PANEL_VALUE_CLASS}>
                        {Boolean((selectedEdge.meta || {}).aggregated) ? '是' : '否'}
                      </div>
                    </div>
                  </div>

                  <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                    <div className={DETAIL_PANEL_LABEL_CLASS}>边证据条目</div>
                    <div className={DETAIL_PANEL_VALUE_CLASS}>{selectedEdgeEvidenceCount > 0 ? selectedEdgeEvidenceCount : '暂无'}</div>
                  </div>
                </div>
              ) : (
                <div className={`${DETAIL_PANEL_CARD_SOFT_CLASS} py-6 text-center text-[11px] text-slate-500 dark:text-slate-400`}>
                  点击画布节点或关系进行高亮。
                  <br />如需进入聚焦/钻取模式，请在选中节点后点击操作按钮。
                </div>
              )}
            </div>

            <div className="mx-4 my-2 h-px bg-slate-200/60 dark:bg-slate-800/60" />

            <div className={cn("flex h-11 shrink-0 items-center", detailHeaderPaddingClass)}>
              <h3 className={DETAIL_PANEL_SECTION_TITLE_CLASS}>渲染统计</h3>
            </div>
            <div className={detailSectionPaddingClass}>
              <div className="grid grid-cols-2 gap-2 text-[10px]">
                <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                  <div className={DETAIL_PANEL_LABEL_CLASS}>原始节点</div>
                  <div className={DETAIL_PANEL_VALUE_CLASS}>{renderModel.stats.rawNodeCount}</div>
                </div>
                <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                  <div className={DETAIL_PANEL_LABEL_CLASS}>原始边</div>
                  <div className={DETAIL_PANEL_VALUE_CLASS}>{renderModel.stats.rawEdgeCount}</div>
                </div>
                <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                  <div className={DETAIL_PANEL_LABEL_CLASS}>可见节点</div>
                  <div className={DETAIL_PANEL_VALUE_CLASS}>{renderModel.stats.renderedNodeCount}</div>
                </div>
                <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                  <div className={DETAIL_PANEL_LABEL_CLASS}>可见边</div>
                  <div className={DETAIL_PANEL_VALUE_CLASS}>{renderModel.stats.renderedEdgeCount}</div>
                </div>
                <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                  <div className={DETAIL_PANEL_LABEL_CLASS}>当前模式</div>
                  <div className={DETAIL_PANEL_VALUE_CLASS}>{modeText}</div>
                </div>
                <div className={DETAIL_PANEL_CARD_BASE_CLASS}>
                  <div className={DETAIL_PANEL_LABEL_CLASS}>证据节点</div>
                  <div className={DETAIL_PANEL_VALUE_CLASS}>{evidenceNodeCount}</div>
                </div>
              </div>
            </div>
          </aside>
        )}
      </div>
    </section>
  );
};
