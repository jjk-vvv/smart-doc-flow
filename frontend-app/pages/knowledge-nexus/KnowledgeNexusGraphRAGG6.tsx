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
  fetchModule4Graph,
  fetchModule4GraphFiles,
  searchModule4GraphRag,
  type Module4GraphFileItem,
  type Module4GraphRagQueryMode,
  type Module4GraphRagQueryResponse,
  type Module4GraphResponse,
} from '../../shared/api/knowledgeGraph';
import { Module4GraphCanvasG6 } from '../../features/knowledge-graph/Module4GraphCanvasG6';
import {
  buildGraphRAGCommunityFocusModel,
  buildGraphRAGEntityDrilldownModel,
  buildGraphRAGOverviewModel,
  type GraphRenderBuildOptions,
} from '../../features/knowledge-graph/graphragRenderAdapter';
import type { GraphRenderEdge, GraphRenderMode, GraphRenderNode } from '../../features/knowledge-graph/graphragViewModel';
import { getActiveExtractionFileHash } from '../../features/knowledge-graph/utils';

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
  { value: 'drift', label: 'DRIFT 检索', description: '先锚定主题再扩展关系路径。' },
  { value: 'basic', label: '基础检索', description: '使用轻量上下文快速返回答案。' },
];

const cleanText = (value: unknown) => String(value || '').replace(/\s+/g, ' ').trim();

const displayFileName = (item: Module4GraphFileItem) => String(item.file_name || item.file_hash || '未命名文件').trim();

const isReadyFile = (item: Module4GraphFileItem) => String(item.status || '').toLowerCase() === 'ready';

const graphBuildModeOf = (item: Module4GraphFileItem) =>
  String(((item.metadata || {}) as Record<string, unknown>).graph_build_mode || '').trim().toLowerCase();

const importModeOf = (item: Module4GraphFileItem) => {
  const metadata = (item.metadata || {}) as Record<string, unknown>;
  const importSummary = (metadata.import_summary || {}) as Record<string, unknown>;
  return String(importSummary.mode || '').trim().toLowerCase();
};

const isFinalGraphRAGFile = (item: Module4GraphFileItem) => {
  const buildMode = graphBuildModeOf(item);
  const importMode = importModeOf(item);
  return buildMode === 'graphrag' || importMode === 'final' || importMode === 'full';
};

const isGraphRAGFile = (item: Module4GraphFileItem) => {
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
    const key = cleanText(item.file_name || item.file_hash || '').toLowerCase() || item.file_hash;
    if (!deduped.has(key)) deduped.set(key, item);
  });
  return [...deduped.values()];
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
  const [graphData, setGraphData] = useState<Module4GraphResponse>(EMPTY_GRAPH);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
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
  const [collapseCommunityMembers, setCollapseCommunityMembers] = useState(false);
  const [queryText, setQueryText] = useState('');
  const [queryMode, setQueryMode] = useState<Module4GraphRagQueryMode>('local');
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryError, setQueryError] = useState('');
  const [queryResult, setQueryResult] = useState<Module4GraphRagQueryResponse | null>(null);
  const [queryFocusIndex, setQueryFocusIndex] = useState(0);
  const [isFileDropdownOpen, setIsFileDropdownOpen] = useState(false);
  const fileDropdownRef = useRef<HTMLDivElement>(null);
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

  const graphRAGFiles = useMemo(
    () => dedupePreferredGraphFiles(graphFiles.filter((item) => isReadyFile(item) && isGraphRAGFile(item))),
    [graphFiles]
  );
  const finalGraphRAGFiles = useMemo(() => graphRAGFiles.filter(isFinalGraphRAGFile), [graphRAGFiles]);
  const visibleFiles = useMemo(
    () =>
      finalGraphRAGFiles.length
        ? finalGraphRAGFiles
        : graphRAGFiles.length
          ? graphRAGFiles
          : dedupePreferredGraphFiles(graphFiles.filter(isReadyFile)),
    [finalGraphRAGFiles, graphFiles, graphRAGFiles]
  );

  const clearQueryResult = useCallback(() => {
    setQueryResult(null);
    setQueryFocusIndex(0);
  }, []);

  const loadGraph = useCallback(
    async (hash: string) => {
      const loadSeq = beginGraphLoad();
      setLoading(true);
      setError('');
      try {
        const nextGraph = hash
          ? await fetchModule4FileGraph(hash, { limitNodes: 1200, limitEdges: 2400 })
          : await fetchModule4Graph({ limitNodes: 1200, limitEdges: 2400 });
        if (!isCurrentGraphLoad(loadSeq)) return;

        startTransition(() => {
          setGraphData(nextGraph);
          setRenderMode('overview');
          setFocusedCommunityId(null);
          setFocusPeerCommunityId(null);
          setDrilldownEntityId(null);
          setSelectedNodeId(null);
          setSelectedEdgeId(null);
          setHoveredNodeId(null);
          setHoveredEdgeId(null);
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
      setHoveredNodeId(null);
      setHoveredEdgeId(null);
      clearQueryResult();
      void loadGraph(nextFileHash);
      setIsFileDropdownOpen(false);
    },
    [clearQueryResult, loadGraph]
  );

  const selectedFile = useMemo(
    () => visibleFiles.find((item) => item.file_hash === selectedFileHash) || null,
    [selectedFileHash, visibleFiles]
  );

  const buildOptions = useMemo<GraphRenderBuildOptions>(
    () => ({
      maxCommunityLevel,
      enabledEdgeKinds,
      collapseCommunityMembersInOverview: collapseCommunityMembers,
      focusPeerCommunityId: renderMode === 'community-focus' ? focusPeerCommunityId : null,
    }),
    [collapseCommunityMembers, enabledEdgeKinds, focusPeerCommunityId, maxCommunityLevel, renderMode]
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

  const activeNodeId = selectedNodeId || hoveredNodeId;
  const activeEdgeId = activeNodeId ? null : selectedEdgeId || hoveredEdgeId;

  const selectedNode = useMemo<GraphRenderNode | null>(() => {
    if (!activeNodeId) return null;
    return renderModel.nodes.find((node) => node.id === activeNodeId) || null;
  }, [activeNodeId, renderModel.nodes]);

  const selectedEdge = useMemo(() => {
    if (!activeEdgeId) return null;
    return renderModel.edges.find((edge) => edge.id === activeEdgeId) || null;
  }, [activeEdgeId, renderModel.edges]);

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
  const selectedNodePreview = cleanText(selectedNodeMeta?.preview_text || '');

  const selectedEdgeMeta = useMemo(
    () => (selectedEdge ? ((selectedEdge.meta || {}) as Record<string, unknown>) : null),
    [selectedEdge]
  );
  const hasPinnedSelection = Boolean(selectedNodeId || selectedEdgeId);
  const shouldShowDetailsPanel = Boolean(selectedNode || selectedEdge);

  const evidenceNodeCount = useMemo(
    () => renderModel.nodes.filter((node) => node.role === 'evidence').length,
    [renderModel.nodes]
  );

  const aggregatedEdgeCount = useMemo(
    () => renderModel.edges.filter((edge) => Boolean((edge.meta || {}).aggregated)).length,
    [renderModel.edges]
  );

  const modeText = useMemo(() => formatTypeName(renderMode), [renderMode]);
  const renderNodeIdSet = useMemo(() => new Set(renderModel.nodes.map((node) => node.id)), [renderModel.nodes]);
  const queryLinkedNodeIdsInView = useMemo(
    () =>
      (queryResult?.linked_node_ids || []).filter((nodeId) => {
        const normalized = cleanText(nodeId);
        return normalized ? renderNodeIdSet.has(normalized) : false;
      }),
    [queryResult?.linked_node_ids, renderNodeIdSet]
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

  const switchToOverview = useCallback(() => {
    setRenderMode('overview');
    setFocusedCommunityId(null);
    setFocusPeerCommunityId(null);
    setDrilldownEntityId(null);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setHoveredNodeId(null);
    setHoveredEdgeId(null);
  }, []);

  const enterCommunityFocus = useCallback((communityId: string, peerId?: string | null) => {
    setRenderMode('community-focus');
    setFocusedCommunityId(communityId);
    setFocusPeerCommunityId(peerId || null);
    setDrilldownEntityId(null);
    setSelectedEdgeId(null);
    setSelectedNodeId(communityId);
    setHoveredNodeId(null);
    setHoveredEdgeId(null);
  }, []);

  const enterEntityDrilldown = useCallback((entityId: string, communityId?: string | null) => {
    setRenderMode('entity-drilldown');
    setDrilldownEntityId(entityId);
    setFocusedCommunityId(communityId || null);
    setFocusPeerCommunityId(null);
    setSelectedEdgeId(null);
    setSelectedNodeId(entityId);
    setHoveredNodeId(null);
    setHoveredEdgeId(null);
  }, []);

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

    setQueryLoading(true);
    setQueryError('');
    try {
      const response = await searchModule4GraphRag({
        fileHash: selectedFileHash,
        query: trimmedQuery,
        mode: queryMode,
        communityLevel: maxCommunityLevel ?? 2,
      });
      startTransition(() => {
        setQueryResult(response);
        setQueryFocusIndex(0);

        const firstLinkedNodeId = (response.linked_node_ids || []).find((nodeId) => renderNodeIdSet.has(String(nodeId)));
        if (firstLinkedNodeId) {
          setSelectedNodeId(String(firstLinkedNodeId));
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
  }, [maxCommunityLevel, queryMode, queryText, renderNodeIdSet, selectedFileHash]);

  const focusQueryLinkedNode = useCallback(
    (offset: number) => {
      const total = queryLinkedNodeIdsInView.length;
      if (!total) return;
      setQueryFocusIndex((previous) => {
        const base = Number.isFinite(previous) ? previous : 0;
        const next = ((base + offset) % total + total) % total;
        const nextNodeId = queryLinkedNodeIdsInView[next];
        if (nextNodeId) {
          setSelectedNodeId(nextNodeId);
          setSelectedEdgeId(null);
        }
        return next;
      });
    },
    [queryLinkedNodeIdsInView]
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

      const readyGraphRAGFiles = dedupePreferredGraphFiles(files.filter((item) => isReadyFile(item) && isGraphRAGFile(item)));
      const readyFinalGraphRAGFiles = readyGraphRAGFiles.filter(isFinalGraphRAGFile);
      const readyFiles = readyFinalGraphRAGFiles.length
        ? readyFinalGraphRAGFiles
        : readyGraphRAGFiles.length
          ? readyGraphRAGFiles
          : dedupePreferredGraphFiles(files.filter(isReadyFile));
      const activeFileHash = getActiveExtractionFileHash();
      const fallbackHash = readyFiles[0]?.file_hash || '';
      const currentFileHash = selectedFileHashRef.current;
      const preferredHash =
        (currentFileHash && readyFiles.some((item) => item.file_hash === currentFileHash) && currentFileHash) ||
        (activeFileHash && readyFiles.some((item) => item.file_hash === activeFileHash) && activeFileHash) ||
        fallbackHash;

      setSelectedFileHash(preferredHash);
      const nextGraph = preferredHash
        ? await fetchModule4FileGraph(preferredHash, { limitNodes: 1200, limitEdges: 2400 })
        : await fetchModule4Graph({ limitNodes: 1200, limitEdges: 2400 });
      if (!isCurrentGraphLoad(loadSeq)) return;

      setGraphData(nextGraph);
      setRenderMode('overview');
      setFocusedCommunityId(null);
      setFocusPeerCommunityId(null);
      setDrilldownEntityId(null);
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
      setHoveredNodeId(null);
      setHoveredEdgeId(null);
      setQueryResult(null);
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
  const totalLinkedNodeCount = queryResult?.linked_node_ids?.length || 0;
  const hiddenLinkedNodeCount = Math.max(0, totalLinkedNodeCount - queryLinkedNodeIdsInView.length);
  const focusedQueryNodeId = queryLinkedNodeIdsInView[queryFocusIndex] || '';

  return (
    <section className="module4-workbench relative flex h-[100dvh] w-full flex-col overflow-hidden bg-[#F8FAFC] p-0 font-sans text-module2-text-primary dark:bg-slate-950">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        {/* Impeccable Ambient Background Glow */}
        <div className="pointer-events-none absolute inset-0 opacity-[0.5] mix-blend-multiply dark:opacity-[0.15] dark:mix-blend-normal bg-[radial-gradient(circle_at_1px_1px,_rgba(15,23,42,0.06)_1px,_transparent_0)] dark:bg-[radial-gradient(circle_at_1px_1px,_rgba(255,255,255,0.06)_1px,_transparent_0)] bg-[length:24px_24px]" />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[600px] bg-[radial-gradient(ellipse_100%_100%_at_top_center,_var(--tw-gradient-stops))] from-cyan-100/60 via-cyan-50/20 to-transparent dark:from-cyan-900/20 dark:via-cyan-950/5" />
        <div className="pointer-events-none absolute -left-[20%] top-[-10%] h-[400px] w-[600px] rounded-full bg-cyan-200/20 blur-[80px] dark:bg-cyan-900/20" />
        <div className="pointer-events-none absolute -right-[20%] top-[10%] h-[300px] w-[500px] rounded-full bg-sky-200/20 blur-[80px] dark:bg-sky-900/10" />
        <div className="pointer-events-none absolute bottom-[-10%] left-[20%] h-[400px] w-[500px] rounded-full bg-blue-200/10 blur-[100px] dark:bg-blue-900/10" />
      </div>
      {/* 顶部紧凑控制栏 */}
      <header className="relative z-10 flex shrink-0 items-center justify-between bg-[#fbfcfd]/90 pl-4 pr-6 py-1.5 backdrop-blur-xl border-b border-slate-200/40 shadow-[0_2px_12px_rgba(0,0,0,0.03)] dark:bg-slate-950/95 dark:border-white/5 dark:shadow-[0_4px_16px_rgba(0,0,0,0.4)]">
        <div className="flex flex-1 min-w-0 items-center gap-3">
          <div className="flex shrink-0 items-center -ml-5 translate-y-[2px]">
            <img 
                src={module4Svg} 
                alt="Knowledge Graph" 
                className="h-[32px] w-auto origin-left scale-[3.0] translate-y-1 object-contain transition-all duration-300 mr-[110px]" 
            />
            <div className="flex shrink-0 items-center space-x-[1px] font-['Microsoft_YaHei'] text-[20px] font-bold tracking-widest -ml-0.5 translate-y-[2px] whitespace-nowrap">
                <span className="text-[#334155] dark:text-slate-200">全域</span>
                <span className="text-[#3b82f6] dark:text-blue-400">知识图谱</span>
            </div>
          </div>
          
          <div className="flex flex-1 min-w-0 items-center justify-end gap-2 ml-4">
            <div className="relative shrink min-w-0" ref={fileDropdownRef}>
              <button
                type="button"
                onClick={() => setIsFileDropdownOpen(!isFileDropdownOpen)}
                className="flex h-[28px] w-full max-w-[300px] shrink cursor-pointer items-center justify-between gap-2 rounded-md border border-slate-200 bg-white/80 px-2.5 text-[12px] text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] outline-none transition-colors hover:border-slate-300 hover:bg-white focus:border-blue-500 focus:bg-white focus:ring-1 focus:ring-blue-500/20 dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:border-slate-600"
              >
                <div className="flex items-center gap-2 truncate">
                  {selectedFile ? (
                    <>
                      <img src={getFileIcon(selectedFile.file_name)} alt="icon" className="h-3.5 w-3.5 shrink-0 object-contain" />
                      <span className="truncate">{displayFileName(selectedFile)}</span>
                    </>
                  ) : (
                    <>
                      <Network size={14} className="shrink-0 text-slate-500 dark:text-slate-400" />
                      <span className="truncate">租户总图</span>
                    </>
                  )}
                </div>
                <ChevronDown size={14} className="shrink-0 text-slate-400" />
              </button>
              
              {isFileDropdownOpen && (
                <div className="absolute right-0 top-full mt-1 w-max min-w-[240px] max-w-[400px] overflow-hidden rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-800 z-50">
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
                  {visibleFiles.map((item) => (
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
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loading}
              className="inline-flex shrink-0 h-[28px] items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 text-[12px] font-medium text-slate-700 shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:bg-slate-50 hover:border-slate-300 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {loading ? '刷新中' : '刷新'}
            </button>
          </div>
        </div>
      </header>

      {/* 主体工作区 */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* 左侧控制栏：检索与视图控制 */}
        <aside className="flex w-80 shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white/95 backdrop-blur-md dark:border-white/5 dark:bg-slate-950/95">
          <div className="flex h-11 shrink-0 items-center px-4 pt-2">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">图谱检索</h2>
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
                
                {queryLinkedNodes.length > 0 && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-[10px] text-slate-500">
                      <span>命中节点 ({queryLinkedNodeIdsInView.length}/{totalLinkedNodeCount})</span>
                      <div className="flex gap-1">
                        <button onClick={() => focusQueryLinkedNode(-1)} className="hover:text-slate-700 dark:hover:text-slate-300">上一个</button>
                        <button onClick={() => focusQueryLinkedNode(1)} className="hover:text-slate-700 dark:hover:text-slate-300">下一个</button>
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

              <div className="h-px w-full bg-slate-100 dark:bg-slate-800/60" />

              <div>
                <label className="mb-2.5 block text-[10px] font-medium text-slate-500 dark:text-slate-400">关系筛选</label>
                <div className="space-y-3">
                  {EDGE_KIND_OPTIONS.map((option) => {
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
          ) : renderModel.nodes.length === 0 ? (
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
              model={renderModel}
              selectedNodeId={selectedNodeId}
              queryHitNodeIds={queryLinkedNodeIdsInView}
              onSelectNode={(nodeId) => {
                setSelectedNodeId(nodeId);
                setHoveredNodeId(nodeId);
                if (!nodeId) setHoveredEdgeId(null);
                if (nodeId) setSelectedEdgeId(null);
              }}
              selectedEdgeId={selectedEdgeId}
              onSelectEdge={(edgeId) => {
                setSelectedEdgeId(edgeId);
                setHoveredEdgeId(edgeId);
                if (!edgeId) setHoveredNodeId(null);
                if (edgeId) setSelectedNodeId(null);
              }}
              onHoverNode={(nodeId) => {
                setHoveredNodeId(nodeId);
                if (nodeId) setHoveredEdgeId(null);
              }}
              onHoverEdge={(edgeId) => {
                setHoveredEdgeId(edgeId);
                if (edgeId) setHoveredNodeId(null);
              }}
              className="h-full w-full outline-none"
            />
          )}
        </main>

        {/* 右侧详情面板 */}
        {shouldShowDetailsPanel && (
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {hasPinnedSelection ? '当前选中' : '悬停预览'}
              </h2>
              <div className="flex items-center gap-2">
                {renderMode !== 'overview' && (
                  <button
                    type="button"
                    onClick={switchToOverview}
                    className="rounded border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                  >
                    返回总览
                  </button>
                )}
              </div>
            </div>

            {selectedNode ? (
              <div className="mt-4 space-y-3 text-xs">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
                  <div className="text-[10px] text-slate-500 dark:text-slate-400">节点名称</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedNode.label}</div>
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
                      onClick={() => enterCommunityFocus(selectedNode.id)}
                      className="rounded border border-violet-200 bg-violet-50 px-2.5 py-1 text-[11px] font-medium text-violet-700 hover:bg-violet-100 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300"
                    >
                      进入社区聚焦
                    </button>
                  )}
                  {selectedNode.kind === 'entity' && (
                    <button
                      type="button"
                      onClick={() => enterEntityDrilldown(selectedNode.id, selectedNode.communityId || null)}
                      className="rounded border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-medium text-sky-700 hover:bg-sky-100 dark:border-sky-700 dark:bg-sky-950/30 dark:text-sky-300"
                    >
                      进入实体钻取
                    </button>
                  )}
                  {selectedNode.communityId && selectedNode.kind !== 'community' && (
                    <button
                      type="button"
                      onClick={() => enterCommunityFocus(String(selectedNode.communityId))}
                      className="rounded border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    >
                      查看所属社区
                    </button>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">类型</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">
                      {formatTypeName(selectedNodeMeta?.node_type_label || selectedNodeMeta?.node_type_key || selectedNode.kind)}
                    </div>
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">角色</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">{formatTypeName(selectedNode.role)}</div>
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">连接度</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">{selectedNode.degree}</div>
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">所属簇</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">{selectedClusterLabel}</div>
                  </div>
                </div>

                {renderMode === 'community-focus' && selectedCommunity && (
                  <div className="mt-2 rounded border border-violet-200 bg-violet-50/70 p-3 dark:border-violet-800/70 dark:bg-violet-950/30">
                    <div className="text-[10px] text-violet-700 dark:text-violet-300">社区聚焦</div>
                    <div className="mt-1 text-[11px] text-slate-700 dark:text-slate-200">
                      成员数量：{selectedCommunity.entityCount} | 层级：{selectedCommunity.level}
                    </div>
                  </div>
                )}
                {renderMode === 'entity-drilldown' && (
                  <div className="mt-2 rounded border border-sky-200 bg-sky-50/70 p-3 dark:border-sky-800/70 dark:bg-sky-950/30">
                    <div className="text-[10px] text-sky-700 dark:text-sky-300">实体钻取</div>
                    <div className="mt-1 text-[11px] text-slate-700 dark:text-slate-200">证据节点：{evidenceNodeCount}</div>
                  </div>
                )}
              </div>
            ) : selectedEdge ? (
              <div className="mt-4 space-y-3 text-xs">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
                  <div className="text-[10px] text-slate-500 dark:text-slate-400">关系标签</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedEdge.label}</div>
                </div>

                {Boolean((selectedEdge.meta || {}).aggregated) && renderMode === 'overview' && (
                  <button
                    type="button"
                    onClick={() => enterCommunityFocus(selectedEdge.source, selectedEdge.target)}
                    className="rounded border border-violet-200 bg-violet-50 px-2.5 py-1 text-[11px] font-medium text-violet-700 hover:bg-violet-100 dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300"
                  >
                    进入关联社区聚焦
                  </button>
                )}

                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">关系类型</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">{formatTypeName(selectedEdge.kind)}</div>
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">权重</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">{selectedEdge.weight.toFixed(2)}</div>
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">置信度</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">{selectedEdge.strength.toFixed(2)}</div>
                  </div>
                  <div className="rounded border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-900/50">
                    <div className="text-[10px] text-slate-500">聚合关系</div>
                    <div className="mt-1 font-medium text-slate-700 dark:text-slate-200">
                      {Boolean((selectedEdge.meta || {}).aggregated) ? '是' : '否'}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-6 text-center text-[11px] text-slate-500 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-400">
                点击画布节点或关系进行高亮。
                <br />如需进入聚焦/钻取模式，请在选中节点后点击操作按钮。
              </div>
            )}

            <div className="mt-6 border-t border-slate-100 pt-4 dark:border-slate-800">
              <h3 className="text-[11px] font-semibold text-slate-700 dark:text-slate-200">渲染统计</h3>
              <div className="mt-2 grid grid-cols-2 gap-y-2 text-[10px] text-slate-600 dark:text-slate-400">
                <div>原始节点: {renderModel.stats.rawNodeCount}</div>
                <div>原始边: {renderModel.stats.rawEdgeCount}</div>
                <div>可见节点: {renderModel.stats.renderedNodeCount}</div>
                <div>可见边: {renderModel.stats.renderedEdgeCount}</div>
                <div>当前模式: {modeText}</div>
                <div>证据节点: {evidenceNodeCount}</div>
              </div>
            </div>
          </aside>
        )}
      </div>
    </section>
  );
};
