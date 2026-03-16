import React, {
  forwardRef,
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  Focus,
  Minus,
  Network,
  Orbit,
  Pin,
  Plus,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  ForceDirectedLayoutType,
  HierarchicalLayoutType,
} from '@neo4j-nvl/base';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force';
import {
  ackModule4Alert,
  fetchModule4Alerts,
  fetchModule4Graph,
  fetchModule4Neighborhood,
  fetchModule4NodeDetail,
  type Module4AlertItem,
  type Module4GraphEdge,
  type Module4GraphNode,
  type Module4GraphResponse,
  type Module4NodeDetailResponse,
} from '../../lib/module4Api';
import {
  readExtractionDocuments,
  subscribeExtractionUpdates,
  type ExtractionDocument,
} from '../../lib/extractionStore';

const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

type FilterState = {
  query: string;
  nodeTypes: string[];
};

type LayoutMode = typeof ForceDirectedLayoutType | typeof HierarchicalLayoutType;

type InspectorState = {
  nodeId: string;
  x: number;
  y: number;
};

type DetailFact = {
  label: string;
  value: string;
};

const TYPE_LABELS: Record<string, string> = {
  document: '文档',
  chunk: '文本片段',
  entity: '实体',
  field: '字段',
  figure: '图像',
  image: '图像',
  table: '表格',
  risk: '风险',
  community: '主题社区',
  covariate: '协变量',
  node: '节点',
};

const RELATION_LABELS: Record<string, string> = {
  contains: '包含',
  related: '关联',
  related_to: '关联',
  links_to: '链接',
  part_of: '属于',
  has_entity: '包含实体',
  has_chunk: '包含片段',
  has_field: '包含字段',
  has_warning: '风险提示',
  has_finding: '包含发现',
  has_evidence: '包含证据',
  in_community: '归属社区',
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

const ARTIFACT_PATTERNS = [
  /^pdf_[a-z0-9_-]+_[ft]\d+$/i,
  /^page_\d+_(figure|table|image|chunk)_\d+$/i,
  /^[a-z0-9_-]+_[ft]\d+$/i,
  /^[0-9a-f]{8}-[0-9a-f-]{27}$/i,
  /^[0-9a-f]{16,}$/i,
];

const GENERIC_ENTITY_NAME_MAP: Record<string, string> = {
  geo: '地理实体',
  indicator: '指标实体',
  facility: '设施实体',
  person: '人物实体',
  event: '事件实体',
  organization: '组织实体',
  org: '组织实体',
  location: '地点实体',
};

const readLocalFallbackFlag = () => {
  const raw = String(import.meta.env.VITE_MODULE4_LOCAL_GRAPH_FALLBACK ?? '')
    .trim()
    .toLowerCase();
  return raw === '' || raw === '1' || raw === 'true' || raw === 'yes';
};

const normalizeText = (value: unknown) => String(value ?? '').replace(/\s+/g, ' ').trim();

const normalizeTypeKey = (value: unknown) =>
  normalizeText(value)
    .replace(/^__|__$/g, '')
    .replace(/\s+/g, '_')
    .toLowerCase() || 'node';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const asRecord = (value: unknown) => (isRecord(value) ? value : {});

const firstText = (...values: unknown[]) => {
  for (const value of values) {
    const text = normalizeText(value);
    if (text) return text;
  }
  return '';
};

const nestedText = (value: unknown, ...path: string[]) => {
  let current: unknown = value;
  for (const key of path) {
    if (!isRecord(current)) return '';
    current = current[key];
  }
  return normalizeText(current);
};

const numberOrNull = (value: unknown) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, max));

const shortText = (value: string, max = 30) => {
  const text = normalizeText(value);
  return text.length > max ? `${text.slice(0, Math.max(0, max - 1))}…` : text;
};

const stripFileExtension = (value: string) => value.replace(/\.(pdf|doc|docx|xls|xlsx|txt|md)$/i, '');

const prettifyToken = (value: string) =>
  normalizeText(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\b[a-z]/g, (char) => char.toUpperCase());

const stripWrappingQuotes = (value: unknown) =>
  normalizeText(value)
    .replace(/^[`"'“”‘’]+/, '')
    .replace(/[`"'“”‘’]+$/, '')
    .trim();

const cleanArtifactText = (value: unknown) =>
  stripWrappingQuotes(value)
    .replace(/^chart:\s*/i, '')
    .replace(/^table:\s*/i, '')
    .replace(/\b(?:pdf|mineru|gemini|vision)[\w-]*_[ft]\d+\b/gi, '')
    .replace(/\bpage_\d+_(?:figure|table|image|chunk)_\d+\b/gi, '')
    .replace(/\((?:pdf|mineru|gemini|vision)[^)]+\)/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim();

const hexToRgb = (value: string) => {
  const hex = value.replace('#', '').trim();
  const normalized =
    hex.length === 3
      ? hex
          .split('')
          .map((char) => `${char}${char}`)
          .join('')
      : hex;
  const parsed = Number.parseInt(normalized, 16);
  if (!Number.isFinite(parsed) || normalized.length !== 6) return null;
  return {
    r: (parsed >> 16) & 255,
    g: (parsed >> 8) & 255,
    b: parsed & 255,
  };
};

const mixHexColor = (left: string, right: string, ratio: number) => {
  const source = hexToRgb(left);
  const target = hexToRgb(right);
  if (!source || !target) return left;
  const weight = clamp(ratio, 0, 1);
  const mix = (from: number, to: number) => Math.round(from + (to - from) * weight);
  return `#${[mix(source.r, target.r), mix(source.g, target.g), mix(source.b, target.b)]
    .map((channel) => channel.toString(16).padStart(2, '0'))
    .join('')}`;
};

const humanizeDocumentName = (value: unknown) => {
  const normalized = stripWrappingQuotes(value)
    .replace(/\.[a-z0-9]+$/i, '')
    .replace(/_hash-[a-z0-9]+$/i, '')
    .replace(/^[0-9]+(?:_[a-z0-9]+){0,3}_/i, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();

  return normalized ? prettifyToken(normalized) : '';
};

const extractSemanticTitle = (value: unknown, fallback = '') => {
  const lines = String(value ?? '')
    .split(/\r?\n+/)
    .map((line) =>
      normalizeText(line)
        .replace(/^\[page\s*\d+\]\s*/i, '')
        .replace(/\/c\d+/gi, '')
        .replace(/\s{2,}/g, ' ')
        .trim()
    )
    .filter(Boolean);

  const contentLines = lines.filter(
    (line) =>
      !/^注释[:：]?$/i.test(line) &&
      !/^notes?[:：]?$/i.test(line) &&
      !/^资料来源[:：]?$/i.test(line) &&
      !/^\[\d+\]/.test(line)
  );

  const titleLike =
    contentLines.find((line) => /\d{4}年.*(公报|报告|白皮书|年鉴|规划|方案|指南|手册|分析)/.test(line)) ||
    contentLines.find((line) => /^[一二三四五六七八九十]+、[\u4e00-\u9fa5A-Za-z0-9（）()《》“”/\-]{2,32}$/.test(line)) ||
    contentLines.find(
      (line) => /^第[一二三四五六七八九十0-9]+[章节篇部分卷][：:\s-]*[\u4e00-\u9fa5A-Za-z0-9（）()《》“”/\-]{2,32}$/.test(line)
    ) ||
    contentLines.find((line) => /^[A-Z]\.\d+\.\s+[A-Z][A-Z\s/&-]{6,}$/i.test(line)) ||
    contentLines.find((line) => /^[A-Z][A-Z\s/&-]{8,}$/.test(line)) ||
    contentLines.find(
      (line) =>
        /[\u4e00-\u9fa5A-Za-z]/.test(line) &&
        line.length >= 6 &&
        !/[=<>]/.test(line) &&
        !/^[0-9\s.,;:%()/-]+$/.test(line) &&
        !/^[0-9.%-]+$/.test(line)
    );

  const cleaned = cleanArtifactText(
    titleLike
      ?.replace(/^[A-Z]\.\d+\.\s*/i, '')
      .replace(/^appendix\s+[a-z]:\s*/i, '')
      .replace(/^chapter\s+\d+[:.]?\s*/i, '') || fallback
  );

  return cleaned ? shortText(cleaned, 42) : '';
};

const looksLikeArtifactName = (value: unknown) => {
  const text = normalizeText(value);
  return text ? ARTIFACT_PATTERNS.some((pattern) => pattern.test(text)) : false;
};

const humanizeWarning = (value: unknown) => {
  const text = normalizeText(value);
  if (!text) return '';
  const [code, ...rest] = text.split(':');
  const titleMap: Record<string, string> = {
    quality_gate_degraded: '质量门控降级',
    field_extract_error: '字段抽取异常',
    table_extract_error: '表格抽取异常',
    parse_error: '解析异常',
    warning: '风险提示',
  };
  const label = titleMap[code] || prettifyToken(code);
  const detail = normalizeText(rest.join(':'));
  return detail ? `${label} · ${detail}` : label;
};

const typeKeyOf = (node: Module4GraphNode | string) => {
  if (typeof node === 'string') return normalizeTypeKey(node);
  return normalizeTypeKey(node.node_type || node.type_label || node.category || 'node');
};

const presentTypeLabel = (node: Module4GraphNode | string) => {
  const key = typeKeyOf(node);
  if (TYPE_LABELS[key]) return TYPE_LABELS[key];
  if (typeof node === 'string') return prettifyToken(key);
  return prettifyToken(firstText(node.type_label, node.category, node.node_type, '节点'));
};

const presentRelationLabel = (edge: Module4GraphEdge) =>
  RELATION_LABELS[normalizeTypeKey(edge.relation_label || edge.relation_type)] ||
  prettifyToken(firstText(edge.relation_label, edge.relation_type, '关联'));

const typePriority = (value: string) => {
  const key = normalizeTypeKey(value);
  if (key === 'community') return 0;
  if (key === 'entity') return 1;
  if (key === 'document') return 2;
  if (key === 'risk') return 3;
  if (key === 'table') return 4;
  if (key === 'figure' || key === 'image') return 5;
  if (key === 'chunk') return 6;
  if (key === 'field') return 7;
  return 8;
};

const visualSpecOf = (node: Module4GraphNode) => {
  const key = typeKeyOf(node);
  const attrs = asRecord(node.attrs);
  const entityType = normalizeTypeKey(firstText(attrs.entity_type, attrs.object_type));

  if (key === 'document') return { color: '#2563EB', size: 72 };
  if (key === 'entity') {
    if (entityType.includes('geo')) return { color: '#0F766E', size: 58 };
    if (entityType.includes('organization')) return { color: '#2563EB', size: 58 };
    if (entityType.includes('person')) return { color: '#E11D48', size: 58 };
    if (entityType.includes('event')) return { color: '#F97316', size: 58 };
    if (entityType.includes('indicator')) return { color: '#7C3AED', size: 58 };
    if (entityType.includes('facility')) return { color: '#0891B2', size: 58 };
    if (entityType.includes('project')) return { color: '#0EA5E9', size: 58 };
    if (entityType.includes('material')) return { color: '#EA580C', size: 58 };
    return { color: '#4F46E5', size: 58 };
  }
  if (key === 'field') return { color: '#4F46E5', size: 56 };
  if (key === 'community') return { color: '#D97706', size: 64 };
  if (key === 'risk') return { color: '#F97316', size: 60 };
  if (key === 'figure' || key === 'image') return { color: '#0EA5E9', size: 56 };
  if (key === 'table') return { color: '#14B8A6', size: 56 };
  if (key === 'chunk') return { color: '#64748B', size: 50 };
  return { color: '#475569', size: 52 };
};

const relationToneOf = (edge: Module4GraphEdge | string) => {
  const key = normalizeTypeKey(typeof edge === 'string' ? edge : edge.relation_type);
  if (key.includes('community')) return '#F59E0B';
  if (key.includes('entity') || key.includes('field')) return '#4F46E5';
  if (key.includes('warning') || key.includes('risk')) return '#F97316';
  if (key.includes('contain') || key.includes('part')) return '#2563EB';
  if (key.includes('evidence')) return '#14B8A6';
  return '#94A3B8';
};

const titleFromSnippet = (snippet: string, typeKey: string) => {
  const cleaned = cleanArtifactText(snippet);
  if (!cleaned) return '';

  if (typeKey === 'figure' || typeKey === 'image') {
    const figureMatch =
      cleaned.match(/(图\s*\d+[^\|]*)/i) ||
      cleaned.match(/(figure\s*\d+[^\|]*)/i) ||
      cleaned.match(/([^|]+)/);
    return cleanArtifactText(figureMatch?.[1] || cleaned);
  }

  if (typeKey === 'table') {
    const titleMatch = cleaned.match(/标题[:：]\s*([^|]+)/);
    if (titleMatch?.[1]) return `表格 · ${cleanArtifactText(titleMatch[1])}`;
    return cleanArtifactText(cleaned.split('|')[0] || cleaned);
  }

  return cleanArtifactText(cleaned.split('|')[0] || cleaned);
};

const fallbackEntityName = (value: unknown, humanReadableId: unknown) => {
  const normalized = normalizeTypeKey(value);
  const label = GENERIC_ENTITY_NAME_MAP[normalized];
  if (!label) return '';
  const suffix = normalizeText(humanReadableId);
  return suffix ? `${label} #${suffix}` : label;
};

const displayNameOfNode = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const context = asRecord(attrs.context);
  const key = typeKeyOf(node);
  const rawDisplay = firstText(node.display_name, node.canonical_key, node.node_id);
  const cleanedDisplay = cleanArtifactText(rawDisplay);

  if (key === 'entity') {
    return firstText(
      GENERIC_ENTITY_NAME_MAP[normalizeTypeKey(cleanedDisplay)] ? '' : cleanedDisplay,
      extractSemanticTitle(attrs.description),
      cleanArtifactText(firstText(attrs.name, attrs.title)),
      fallbackEntityName(cleanedDisplay, attrs.human_readable_id),
      presentTypeLabel(node)
    );
  }

  if (key === 'document') {
    return firstText(
      humanizeDocumentName(attrs.file_name),
      humanizeDocumentName(cleanedDisplay),
      extractSemanticTitle(attrs.raw_content),
      extractSemanticTitle(attrs.text),
      '文档'
    );
  }

  if (key === 'risk') {
    return firstText(humanizeWarning(attrs.warning), cleanedDisplay, '风险提示');
  }

  if (key === 'chunk') {
    return firstText(
      extractSemanticTitle(attrs.text),
      extractSemanticTitle(attrs.raw_content),
      titleFromSnippet(firstText(attrs.snippet, attrs.text, cleanedDisplay), key),
      '文本片段'
    );
  }

  if (!looksLikeArtifactName(rawDisplay) && cleanedDisplay) {
    return cleanedDisplay;
  }

  return firstText(
    extractSemanticTitle(attrs.description),
    cleanArtifactText(nestedText(context, 'caption_hint')),
    titleFromSnippet(firstText(attrs.snippet, nestedText(context, 'caption_hint')), key),
    cleanArtifactText(firstText(attrs.title, attrs.name, attrs.file_name)),
    cleanedDisplay,
    presentTypeLabel(node)
  );
};

const captionOfNode = (node: Module4GraphNode, max = 22) => {
  const base = displayNameOfNode(node);
  const compact = typeKeyOf(node) === 'document' ? stripFileExtension(base) : base;
  const maxLength = typeKeyOf(node) === 'chunk' ? Math.min(max, 16) : max;
  return shortText(compact, maxLength);
};

const summaryOfNode = (node: Module4GraphNode) => {
  const attrs = asRecord(node.attrs);
  const diagnostics = asRecord(attrs.diagnostics);
  const context = asRecord(attrs.context);
  const warning = humanizeWarning(attrs.warning);
  if (warning) return shortText(warning, 180);

  const snippet = cleanArtifactText(
    firstText(
      nestedText(context, 'caption_hint'),
      attrs.snippet,
      nestedText(context, 'nearby_text'),
      extractSemanticTitle(attrs.text),
      extractSemanticTitle(attrs.raw_content)
    )
  );
  if (snippet) return shortText(snippet, 180);

  if (typeKeyOf(node) === 'document') {
    const parts = [
      numberOrNull(diagnostics.figure_count) ? `${diagnostics.figure_count} 张图` : '',
      numberOrNull(diagnostics.table_count) ? `${diagnostics.table_count} 张表` : '',
      numberOrNull(diagnostics.trace_hit_count) ? `${diagnostics.trace_hit_count} 条证据` : '',
      firstText(diagnostics.quality_status) ? `质量 ${diagnostics.quality_status}` : '',
    ].filter(Boolean);
    if (parts.length) return parts.join(' · ');
  }

  return '';
};

const detailFactsOfNode = (node: Module4GraphNode): DetailFact[] => {
  const attrs = asRecord(node.attrs);
  const diagnostics = asRecord(attrs.diagnostics);
  const context = asRecord(attrs.context);
  const facts: DetailFact[] = [];

  const push = (label: string, value: unknown) => {
    const text = normalizeText(value);
    if (!text) return;
    if (facts.some((item) => item.label === label && item.value === text)) return;
    facts.push({ label, value: text });
  };

  push('类型', presentTypeLabel(node));
  push('来源文档', firstText(attrs.source_doc, attrs.file_name, nestedText(context, 'doc_name')));
  if (firstText(attrs.page, nestedText(context, 'page'))) {
    push('页码', `第 ${firstText(attrs.page, nestedText(context, 'page'))} 页`);
  }
  if (node.confidence > 0) push('置信度', `${Math.round(node.confidence * 100)}%`);
  push('对象类型', attrs.object_type);
  if (numberOrNull(diagnostics.figure_count)) push('图像数', diagnostics.figure_count);
  if (numberOrNull(diagnostics.table_count)) push('表格数', diagnostics.table_count);
  push('质量状态', diagnostics.quality_status);
  push('文件哈希', attrs.file_hash);

  return facts.slice(0, 8);
};

const attributeRowsOfNode = (node: Module4GraphNode): DetailFact[] => {
  const attrs = asRecord(node.attrs);
  const context = asRecord(attrs.context);
  const rows: DetailFact[] = [];

  const push = (label: string, value: unknown) => {
    const text = normalizeText(value);
    if (!text) return;
    if (rows.some((item) => item.label === label && item.value === text)) return;
    rows.push({ label, value: shortText(text, 200) });
  };

  push('显示名称', displayNameOfNode(node));
  push('摘要', summaryOfNode(node));
  push('来源片段', cleanArtifactText(firstText(attrs.snippet, nestedText(context, 'caption_hint'))));
  push('告警详情', humanizeWarning(attrs.warning));
  push('原始键', node.canonical_key);
  push('引用 ID', firstText(attrs.source_ref_id, attrs.ref_id));

  return rows.slice(0, 8);
};

const buildStats = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const byNodeType: Record<string, number> = {};
  const byRelationType: Record<string, number> = {};

  nodes.forEach((node) => {
    const key = presentTypeLabel(node);
    byNodeType[key] = (byNodeType[key] || 0) + 1;
  });

  edges.forEach((edge) => {
    const key = presentRelationLabel(edge);
    byRelationType[key] = (byRelationType[key] || 0) + 1;
  });

  return {
    node_count: nodes.length,
    edge_count: edges.length,
    by_node_type: byNodeType,
    by_relation_type: byRelationType,
  };
};

const buildSeedPositions = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const positionMap = new Map<string, NodePositionState>();
  if (!nodes.length) return positionMap;

  const adjacency = new Map<string, Set<string>>();
  nodes.forEach((node) => adjacency.set(node.node_id, new Set()));
  edges.forEach((edge) => {
    adjacency.get(edge.source_node_id)?.add(edge.target_node_id);
    adjacency.get(edge.target_node_id)?.add(edge.source_node_id);
  });

  const rankedNodes = [...nodes].sort((left, right) => {
    const degreeDiff = (adjacency.get(right.node_id)?.size || 0) - (adjacency.get(left.node_id)?.size || 0);
    if (degreeDiff !== 0) return degreeDiff;
    const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
    if (typeDiff !== 0) return typeDiff;
    return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
  });

  const rootId = rankedNodes[0]?.node_id || nodes[0]?.node_id;
  const levels = new Map<string, number>();
  const queue = rootId ? [rootId] : [];
  if (rootId) levels.set(rootId, 0);

  while (queue.length > 0) {
    const currentId = queue.shift() as string;
    const currentLevel = levels.get(currentId) || 0;
    (adjacency.get(currentId) || new Set()).forEach((neighborId) => {
      if (!levels.has(neighborId)) {
        levels.set(neighborId, currentLevel + 1);
        queue.push(neighborId);
      }
    });
  }

  let fallbackLevel = Math.max(0, ...Array.from(levels.values())) + 1;
  nodes.forEach((node) => {
    if (!levels.has(node.node_id)) {
      levels.set(node.node_id, fallbackLevel);
      fallbackLevel += 1;
    }
  });

  const groups = new Map<number, Module4GraphNode[]>();
  nodes.forEach((node) => {
    const level = levels.get(node.node_id) || 0;
    const bucket = groups.get(level) || [];
    bucket.push(node);
    groups.set(level, bucket);
  });

  Array.from(groups.entries())
    .sort((left, right) => left[0] - right[0])
    .forEach(([level, group]) => {
      const ordered = [...group].sort((left, right) => {
        const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
        if (typeDiff !== 0) return typeDiff;
        return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
      });

      const radius = level === 0 ? 0 : 140 + (level - 1) * 120 + Math.max(0, ordered.length - 6) * 8;
      const angleOffset = level * 0.68;
      const yCompression = level === 0 ? 1 : 0.84;

      ordered.forEach((node, index) => {
        const angle =
          ordered.length === 1 ? angleOffset : (Math.PI * 2 * index) / ordered.length + angleOffset;
        positionMap.set(node.node_id, {
          x: radius === 0 ? 0 : Math.cos(angle) * radius,
          y: radius === 0 ? 0 : Math.sin(angle) * radius * yCompression,
        });
      });
    });

  return positionMap;
};

const mergeGraph = (left: Module4GraphResponse, right: Module4GraphResponse): Module4GraphResponse => {
  const nodeMap = new Map<string, Module4GraphNode>();
  const edgeMap = new Map<string, Module4GraphEdge>();

  [...left.nodes, ...right.nodes].forEach((node) => nodeMap.set(node.node_id, node));
  [...left.edges, ...right.edges].forEach((edge) => edgeMap.set(edge.edge_id, edge));

  const nodes = [...nodeMap.values()];
  const edges = [...edgeMap.values()];

  return {
    nodes,
    edges,
    source: right.source || left.source,
    workspace_id: right.workspace_id || left.workspace_id || null,
    stats: buildStats(nodes, edges),
  };
};

const localFallback = (documents: ExtractionDocument[]): Module4GraphResponse => {
  const nodes: Module4GraphNode[] = [];
  const edges: Module4GraphEdge[] = [];

  documents.slice(0, 12).forEach((document, documentIndex) => {
    const documentId = `local-doc-${document.file_hash || documentIndex}`;
    nodes.push({
      node_id: documentId,
      node_type: 'Document',
      canonical_key: document.file_hash || documentId,
      display_name: document.file_name || `文档 ${documentIndex + 1}`,
      confidence: 1,
      type_label: '文档',
      category: '文档',
      attrs: {
        file_name: document.file_name,
        file_hash: document.file_hash,
        track: document.track,
        diagnostics: document.diagnostics || {},
      },
    });

    Object.entries(document.result || {})
      .slice(0, 16)
      .forEach(([fieldName, entity], fieldIndex) => {
        const nodeId = `${documentId}-field-${fieldIndex}`;
        nodes.push({
          node_id: nodeId,
          node_type: 'Field',
          canonical_key: `${document.file_hash || documentId}-${fieldName}`,
          display_name: fieldName,
          confidence: Number(entity?.confidence || 0),
          type_label: '字段',
          category: '字段',
          attrs: {
            source_doc: document.file_name,
            field_name: fieldName,
            value: entity?.value ?? '',
            source_ref_id: entity?.source_ref_id,
          },
        });

        edges.push({
          edge_id: `${documentId}-field-edge-${fieldIndex}`,
          source_node_id: documentId,
          target_node_id: nodeId,
          relation_type: 'HAS_FIELD',
          relation_label: '包含字段',
          direction: 'out',
          confidence: Number(entity?.confidence || 0),
          risk_score: 0,
          attrs: {},
        });
      });

    (document.trace_hits || []).slice(0, 6).forEach((hit, hitIndex) => {
      const nodeId = `${documentId}-trace-${hitIndex}`;
      const objectType = normalizeTypeKey(hit.object_type || 'chunk');
      const nodeType =
        objectType === 'table'
          ? 'Table'
          : objectType === 'figure' || objectType === 'image'
            ? 'Figure'
            : 'Chunk';

      nodes.push({
        node_id: nodeId,
        node_type: nodeType,
        canonical_key: `${document.file_hash || documentId}-${hit.object_id || hitIndex}`,
        display_name: firstText(hit.object_id, hit.object_type, `证据 ${hitIndex + 1}`),
        confidence: Number(hit.confidence || 0.68),
        type_label: presentTypeLabel(nodeType),
        category: presentTypeLabel(nodeType),
        attrs: {
          source_doc: document.file_name,
          object_type: hit.object_type,
          object_id: hit.object_id,
          snippet: hit.snippet,
          page: hit.page,
          artifact_url: hit.artifact_url,
          context: {
            caption_hint: hit.snippet,
            page: hit.page,
          },
        },
      });

      edges.push({
        edge_id: `${documentId}-trace-edge-${hitIndex}`,
        source_node_id: documentId,
        target_node_id: nodeId,
        relation_type: 'HAS_EVIDENCE',
        relation_label: '包含证据',
        direction: 'out',
        confidence: Number(hit.confidence || 0.68),
        risk_score: 0,
        attrs: {},
      });
    });

    (document.errors || []).slice(0, 4).forEach((errorText, errorIndex) => {
      const nodeId = `${documentId}-risk-${errorIndex}`;
      nodes.push({
        node_id: nodeId,
        node_type: 'Risk',
        canonical_key: `${document.file_hash || documentId}-risk-${errorIndex}`,
        display_name: `风险提示 ${errorIndex + 1}`,
        confidence: 0.72,
        type_label: '风险',
        category: '风险',
        attrs: {
          source_doc: document.file_name,
          warning: errorText,
        },
      });

      edges.push({
        edge_id: `${documentId}-warning-edge-${errorIndex}`,
        source_node_id: documentId,
        target_node_id: nodeId,
        relation_type: 'HAS_WARNING',
        relation_label: '风险提示',
        direction: 'out',
        confidence: 0.72,
        risk_score: 0.8,
        attrs: {},
      });
    });
  });

  return {
    nodes,
    edges,
    source: 'local-fallback',
    workspace_id: null,
    stats: buildStats(nodes, edges),
  };
};

const selectionNeighborhoodOf = (graph: Module4GraphResponse, nodeId: string) => {
  if (!nodeId) return null;

  const edges = graph.edges.filter(
    (edge) => edge.source_node_id === nodeId || edge.target_node_id === nodeId
  );
  const nodeIds = new Set<string>([nodeId]);
  const edgeIds = new Set<string>();

  edges.forEach((edge) => {
    nodeIds.add(edge.source_node_id);
    nodeIds.add(edge.target_node_id);
    edgeIds.add(edge.edge_id);
  });

  return { nodeIds, edgeIds };
};

const subgraphForNode = (graph: Module4GraphResponse, nodeId: string): Module4GraphResponse => {
  const neighborhood = selectionNeighborhoodOf(graph, nodeId);
  if (!neighborhood) {
    const nodes = graph.nodes.filter((node) => node.node_id === nodeId);
    return {
      ...EMPTY_GRAPH,
      nodes,
      stats: buildStats(nodes, []),
    };
  }

  const nodes = graph.nodes.filter((node) => neighborhood.nodeIds.has(node.node_id));
  const edges = graph.edges.filter((edge) => neighborhood.edgeIds.has(edge.edge_id));
  return {
    nodes,
    edges,
    source: graph.source,
    workspace_id: graph.workspace_id || null,
    stats: buildStats(nodes, edges),
  };
};

const severityLabel = (value?: string) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'red') return '高风险';
  if (normalized === 'orange') return '中风险';
  if (normalized === 'yellow') return '关注';
  return '未知';
};

const alertStatusLabel = (value?: string) => {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'open') return '待处理';
  if (normalized === 'ack') return '已确认';
  if (normalized === 'resolved') return '已解决';
  if (normalized === 'false_positive') return '误报';
  return '未知';
};

type ForceGraphHandle = {
  fit: (nodeIds?: string[], options?: { animated?: boolean; outOnly?: boolean; maxZoom?: number }) => void;
  getScale: () => number;
  getPan: () => { x: number; y: number };
  setZoom: (zoom: number) => void;
  pinNode: (nodeId: string) => void;
  unPinNode: (nodeIds: string[] | string) => void;
  getNodeScreenPosition: (nodeId: string) => { x: number; y: number } | null;
};

type ForceGraphViewport = {
  x: number;
  y: number;
  zoom: number;
};

type ForceGraphPoint = {
  clientX: number;
  clientY: number;
};

type ForceGraphNodeDatum = SimulationNodeDatum & {
  id: string;
  node: Module4GraphNode;
  label: string;
  radius: number;
  color: string;
  seedX: number;
  seedY: number;
  x: number;
  y: number;
  fx: number | null;
  fy: number | null;
};

type ForceGraphLinkDatum = SimulationLinkDatum<ForceGraphNodeDatum> & {
  id: string;
  edge: Module4GraphEdge;
  label: string;
  color: string;
  width: number;
  source: string | ForceGraphNodeDatum;
  target: string | ForceGraphNodeDatum;
};

type ForceGraphProps = {
  graph: Module4GraphResponse;
  layoutMode: LayoutMode;
  selectedNodeId: string;
  pinnedNodeIds: string[];
  selectionNeighborhood: ReturnType<typeof selectionNeighborhoodOf>;
  onNodeClick: (nodeId: string, point: ForceGraphPoint) => void;
  onNodeDoubleClick: (nodeId: string) => void;
  onCanvasClick: () => void;
  onNodeDragEnd: (nodeId: string, point: ForceGraphPoint) => void;
  className?: string;
};

const splitNodeLabel = (value: string, maxChars = 8, maxLines = 2) => {
  const text = normalizeText(value);
  if (!text) return [''];
  const lines: string[] = [];
  for (let index = 0; index < text.length && lines.length < maxLines; index += maxChars) {
    const slice = text.slice(index, index + maxChars);
    const next = text.slice(index + maxChars);
    lines.push(next && lines.length === maxLines - 1 ? `${slice.slice(0, Math.max(0, maxChars - 1))}…` : slice);
  }
  return lines;
};

const shouldRenderNodeLabel = (
  node: ForceGraphNodeDatum,
  options: {
    graphSize: number;
    zoom: number;
    isSelected: boolean;
    isFocused: boolean;
  }
) => {
  if (options.isSelected) return true;

  const typeKey = typeKeyOf(node.node);
  if (typeKey !== 'chunk') return true;

  const label = normalizeText(node.label);
  if (!label) return false;

  const isVerbose =
    label.length > 16 || /^[[(（【]/.test(label) || /[。；，、,:：|]/.test(label) || /\d{3,}/.test(label);

  if (!isVerbose) return true;
  if (options.isFocused) return true;
  if (options.zoom >= 0.94) return true;
  if (options.graphSize <= 42) return true;
  return false;
};

const buildHierarchyPositions = (nodes: Module4GraphNode[], edges: Module4GraphEdge[]) => {
  const positionMap = new Map<string, { x: number; y: number }>();
  if (!nodes.length) return positionMap;

  const adjacency = new Map<string, Set<string>>();
  nodes.forEach((node) => adjacency.set(node.node_id, new Set()));
  edges.forEach((edge) => {
    adjacency.get(edge.source_node_id)?.add(edge.target_node_id);
    adjacency.get(edge.target_node_id)?.add(edge.source_node_id);
  });

  const rankedNodes = [...nodes].sort((left, right) => {
    const degreeDiff = (adjacency.get(right.node_id)?.size || 0) - (adjacency.get(left.node_id)?.size || 0);
    if (degreeDiff !== 0) return degreeDiff;
    const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
    if (typeDiff !== 0) return typeDiff;
    return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
  });

  const rootId = rankedNodes[0]?.node_id || nodes[0]?.node_id;
  const levels = new Map<string, number>();
  const queue = rootId ? [rootId] : [];
  if (rootId) levels.set(rootId, 0);

  while (queue.length > 0) {
    const currentId = queue.shift() as string;
    const currentLevel = levels.get(currentId) || 0;
    (adjacency.get(currentId) || new Set()).forEach((neighborId) => {
      if (!levels.has(neighborId)) {
        levels.set(neighborId, currentLevel + 1);
        queue.push(neighborId);
      }
    });
  }

  let fallbackLevel = Math.max(0, ...Array.from(levels.values())) + 1;
  nodes.forEach((node) => {
    if (!levels.has(node.node_id)) {
      levels.set(node.node_id, fallbackLevel);
      fallbackLevel += 1;
    }
  });

  const columns = new Map<number, Module4GraphNode[]>();
  nodes.forEach((node) => {
    const level = levels.get(node.node_id) || 0;
    const bucket = columns.get(level) || [];
    bucket.push(node);
    columns.set(level, bucket);
  });

  Array.from(columns.entries())
    .sort((left, right) => left[0] - right[0])
    .forEach(([level, group]) => {
      const ordered = [...group].sort((left, right) => {
        const typeDiff = typePriority(typeKeyOf(left)) - typePriority(typeKeyOf(right));
        if (typeDiff !== 0) return typeDiff;
        return displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN');
      });

      const totalHeight = Math.max(0, (ordered.length - 1) * 136);
      ordered.forEach((node, index) => {
        positionMap.set(node.node_id, {
          x: level * 260,
          y: index * 136 - totalHeight / 2,
        });
      });
    });

  return positionMap;
};

const getLinkEndpoint = (value: string | ForceGraphNodeDatum) =>
  (typeof value === 'string' ? null : value) ?? null;

const Neo4jStyleForceGraph = forwardRef<ForceGraphHandle, ForceGraphProps>(
  (
    {
      graph,
      layoutMode,
      selectedNodeId,
      pinnedNodeIds,
      selectionNeighborhood,
      onNodeClick,
      onNodeDoubleClick,
      onCanvasClick,
      onNodeDragEnd,
      className,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const simulationRef = useRef<Simulation<ForceGraphNodeDatum, ForceGraphLinkDatum> | null>(null);
    const nodesRef = useRef<ForceGraphNodeDatum[]>([]);
    const linksRef = useRef<ForceGraphLinkDatum[]>([]);
    const nodeMapRef = useRef(new Map<string, ForceGraphNodeDatum>());
    const positionCacheRef = useRef(
      new Map<string, { x: number; y: number; fx: number | null; fy: number | null }>()
    );
    const viewportRef = useRef<ForceGraphViewport>({ x: 0, y: 0, zoom: 1 });
    const animationFrameRef = useRef<number | null>(null);
    const viewportAnimationRef = useRef<number | null>(null);
    const suppressClickRef = useRef(false);
    const dragStateRef = useRef<{
      nodeId: string;
      pointerId: number;
      moved: boolean;
    } | null>(null);
    const panStateRef = useRef<{
      pointerId: number;
      startClientX: number;
      startClientY: number;
      originX: number;
      originY: number;
      moved: boolean;
    } | null>(null);

    const [viewport, setViewport] = useState<ForceGraphViewport>({ x: 0, y: 0, zoom: 1 });
    const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
    const [, setTick] = useState(0);

    viewportRef.current = viewport;

    const graphSignature = useMemo(
      () =>
        `${graph.nodes.map((node) => node.node_id).sort().join('|')}::${graph.edges
          .map((edge) => edge.edge_id)
          .sort()
          .join('|')}`,
      [graph.edges, graph.nodes]
    );

    const scheduleRender = useCallback(() => {
      if (typeof window === 'undefined') return;
      if (animationFrameRef.current != null) return;
      animationFrameRef.current = window.requestAnimationFrame(() => {
        animationFrameRef.current = null;
        setTick((current) => current + 1);
      });
    }, []);

    const animateViewport = useCallback(
      (next: ForceGraphViewport, animated = true) => {
        if (typeof window === 'undefined') {
          setViewport(next);
          return;
        }

        if (viewportAnimationRef.current != null) {
          window.cancelAnimationFrame(viewportAnimationRef.current);
          viewportAnimationRef.current = null;
        }

        if (!animated) {
          setViewport(next);
          return;
        }

        const start = viewportRef.current;
        const startTime = performance.now();
        const duration = 220;

        const step = (now: number) => {
          const progress = Math.min(1, (now - startTime) / duration);
          const eased = 1 - (1 - progress) ** 3;
          setViewport({
            x: start.x + (next.x - start.x) * eased,
            y: start.y + (next.y - start.y) * eased,
            zoom: start.zoom + (next.zoom - start.zoom) * eased,
          });
          if (progress < 1) {
            viewportAnimationRef.current = window.requestAnimationFrame(step);
          } else {
            viewportAnimationRef.current = null;
          }
        };

        viewportAnimationRef.current = window.requestAnimationFrame(step);
      },
      []
    );

    const toGraphPoint = useCallback(
      (clientX: number, clientY: number) => {
        const rect = containerRef.current?.getBoundingClientRect();
        const activeViewport = viewportRef.current;
        if (!rect) return { x: 0, y: 0 };
        return {
          x: (clientX - rect.left - activeViewport.x) / activeViewport.zoom,
          y: (clientY - rect.top - activeViewport.y) / activeViewport.zoom,
        };
      },
      []
    );

    const fitNodes = useCallback(
      (nodeIds?: string[], options?: { animated?: boolean; outOnly?: boolean; maxZoom?: number }) => {
        if (!containerSize.width || !containerSize.height) return;
        const activeNodes = nodesRef.current.filter((node) => !nodeIds?.length || nodeIds.includes(node.id));
        if (!activeNodes.length) return;
        const padding = activeNodes.length > 120 ? 28 : activeNodes.length > 64 ? 24 : 20;

        let minX = Number.POSITIVE_INFINITY;
        let minY = Number.POSITIVE_INFINITY;
        let maxX = Number.NEGATIVE_INFINITY;
        let maxY = Number.NEGATIVE_INFINITY;

        activeNodes.forEach((node) => {
          const radius = node.radius + padding;
          const x = Number(node.x || 0);
          const y = Number(node.y || 0);
          minX = Math.min(minX, x - radius);
          maxX = Math.max(maxX, x + radius);
          minY = Math.min(minY, y - radius);
          maxY = Math.max(maxY, y + radius);
        });

        const width = Math.max(1, maxX - minX);
        const height = Math.max(1, maxY - minY);
        const zoomLimit = options?.maxZoom ?? (activeNodes.length === 1 ? 1.14 : 1.04);
        const nextZoom = clamp(
          Math.min(containerSize.width / width, containerSize.height / height) * 0.88,
          0.18,
          zoomLimit
        );
        const currentViewport = viewportRef.current;
        const targetZoom = options?.outOnly ? Math.min(currentViewport.zoom, nextZoom) : nextZoom;
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;

        animateViewport(
          {
            zoom: targetZoom,
            x: containerSize.width / 2 - centerX * targetZoom,
            y: containerSize.height / 2 - centerY * targetZoom,
          },
          options?.animated !== false
        );
      },
      [animateViewport, containerSize.height, containerSize.width]
    );

    useImperativeHandle(
      ref,
      () => ({
        fit: (nodeIds, options) => fitNodes(nodeIds, options),
        getScale: () => viewportRef.current.zoom,
        getPan: () => ({ x: viewportRef.current.x, y: viewportRef.current.y }),
        setZoom: (zoom: number) => {
          const rect = containerRef.current?.getBoundingClientRect();
          if (!rect) return;
          const current = viewportRef.current;
          const worldX = (containerSize.width / 2 - current.x) / current.zoom;
          const worldY = (containerSize.height / 2 - current.y) / current.zoom;
          const nextZoom = clamp(zoom, 0.18, 2.4);
          animateViewport({
            zoom: nextZoom,
            x: containerSize.width / 2 - worldX * nextZoom,
            y: containerSize.height / 2 - worldY * nextZoom,
          });
        },
        pinNode: (nodeId: string) => {
          const node = nodeMapRef.current.get(nodeId);
          if (!node) return;
          node.fx = node.x || 0;
          node.fy = node.y || 0;
          scheduleRender();
        },
        unPinNode: (nodeIds: string[] | string) => {
          const ids = Array.isArray(nodeIds) ? nodeIds : [nodeIds];
          ids.forEach((nodeId) => {
            const node = nodeMapRef.current.get(nodeId);
            if (!node || dragStateRef.current?.nodeId === nodeId) return;
            if (layoutMode === HierarchicalLayoutType) return;
            node.fx = null;
            node.fy = null;
          });
          simulationRef.current?.alpha(0.28).restart();
          scheduleRender();
        },
        getNodeScreenPosition: (nodeId: string) => {
          const node = nodeMapRef.current.get(nodeId);
          if (!node) return null;
          const activeViewport = viewportRef.current;
          return {
            x: activeViewport.x + Number(node.x || 0) * activeViewport.zoom,
            y: activeViewport.y + Number(node.y || 0) * activeViewport.zoom,
          };
        },
      }),
      [animateViewport, containerSize.height, containerSize.width, fitNodes, layoutMode, scheduleRender]
    );

    useEffect(() => {
      const target = containerRef.current;
      if (!target || typeof ResizeObserver === 'undefined') return () => undefined;

      const updateSize = () => {
        setContainerSize({
          width: Math.max(0, target.clientWidth),
          height: Math.max(0, target.clientHeight),
        });
      };

      updateSize();
      const observer = new ResizeObserver(() => updateSize());
      observer.observe(target);
      return () => observer.disconnect();
    }, []);

    useEffect(() => {
      if (!graph.nodes.length) {
        nodesRef.current = [];
        linksRef.current = [];
        nodeMapRef.current = new Map();
        simulationRef.current?.stop();
        simulationRef.current = null;
        return () => undefined;
      }

      const cachedPositions = positionCacheRef.current;
      const seedPositions =
        layoutMode === HierarchicalLayoutType
          ? buildHierarchyPositions(graph.nodes, graph.edges)
          : buildSeedPositions(graph.nodes, graph.edges);
      const pinnedSet = new Set(pinnedNodeIds);

        const nextNodes = graph.nodes.map((node) => {
          const visual = visualSpecOf(node);
          const label = captionOfNode(node, visual.size > 64 ? 24 : 18);
          const cached = cachedPositions.get(node.node_id);
          const seeded = seedPositions.get(node.node_id);
          const x = cached?.x ?? seeded?.x ?? (Math.random() - 0.5) * 360;
          const y = cached?.y ?? seeded?.y ?? (Math.random() - 0.5) * 280;
          const isPinned = pinnedSet.has(node.node_id) || layoutMode === HierarchicalLayoutType;
          return {
            id: node.node_id,
            node,
            label,
            radius: Math.max(24, visual.size * 0.46),
            color: visual.color,
            seedX: seeded?.x ?? x,
            seedY: seeded?.y ?? y,
            x,
            y,
            fx: isPinned ? cached?.fx ?? x : null,
          fy: isPinned ? cached?.fy ?? y : null,
        } satisfies ForceGraphNodeDatum;
      });

      const nextLinks = graph.edges.map((edge) => ({
        id: edge.edge_id,
        edge,
        label: presentRelationLabel(edge),
        color: relationToneOf(edge),
        width: Math.max(1.6, 1.2 + edge.confidence * 2),
        source: edge.source_node_id,
        target: edge.target_node_id,
      })) satisfies ForceGraphLinkDatum[];

      nodesRef.current = nextNodes;
      linksRef.current = nextLinks;
      nodeMapRef.current = new Map(nextNodes.map((node) => [node.id, node]));

      simulationRef.current?.stop();

      if (layoutMode === HierarchicalLayoutType) {
        nextNodes.forEach((node) => {
          const position = seedPositions.get(node.id) || { x: 0, y: 0 };
          node.x = position.x;
          node.y = position.y;
          node.fx = position.x;
          node.fy = position.y;
          cachedPositions.set(node.id, {
            x: position.x,
            y: position.y,
            fx: position.x,
            fy: position.y,
          });
        });
        scheduleRender();
        return () => undefined;
      }

      const simulation = forceSimulation(nextNodes)
        .force(
          'link',
          forceLink<ForceGraphNodeDatum, ForceGraphLinkDatum>(nextLinks)
            .id((node) => node.id)
            .distance((link) => {
              const typeKey = normalizeTypeKey(link.edge.relation_type);
              if (typeKey.includes('community')) return 248;
              if (typeKey.includes('part')) return 168;
              if (typeKey.includes('entity')) return 132;
              if (typeKey.includes('related')) return 148;
              return 138;
            })
            .strength((link) => {
              const typeKey = normalizeTypeKey(link.edge.relation_type);
              if (typeKey.includes('community')) return 0.12;
              if (typeKey.includes('part')) return 0.26;
              if (typeKey.includes('entity')) return 0.2;
              return 0.16;
            })
        )
        .force(
          'charge',
          forceManyBody<ForceGraphNodeDatum>()
            .strength((node) => {
              const typeKey = typeKeyOf(node.node);
              if (typeKey === 'community') return -1240;
              if (typeKey === 'document') return -860;
              if (typeKey === 'chunk') return graph.nodes.length > 180 ? -420 : -500;
              return graph.nodes.length > 180 ? -560 : -680;
            })
            .distanceMax(1100)
        )
        .force('center', forceCenter<ForceGraphNodeDatum>(0, 0))
        .force('seed-x', forceX<ForceGraphNodeDatum>((node) => node.seedX).strength(graph.nodes.length > 180 ? 0.028 : 0.042))
        .force('seed-y', forceY<ForceGraphNodeDatum>((node) => node.seedY).strength(graph.nodes.length > 180 ? 0.028 : 0.042))
        .force(
          'collide',
          forceCollide<ForceGraphNodeDatum>().radius((node) => node.radius + (typeKeyOf(node.node) === 'chunk' ? 16 : 20)).iterations(3)
        )
        .alpha(0.92)
        .alphaDecay(0.032)
        .velocityDecay(0.2)
        .on('tick', () => {
          nextNodes.forEach((node) => {
            cachedPositions.set(node.id, {
              x: Number(node.x || 0),
              y: Number(node.y || 0),
              fx: node.fx ?? null,
              fy: node.fy ?? null,
            });
          });
          scheduleRender();
        });

      simulationRef.current = simulation;
      scheduleRender();

      return () => {
        simulation.stop();
      };
    }, [graph.nodes, graph.edges, graphSignature, layoutMode, pinnedNodeIds, scheduleRender]);

    useEffect(() => {
      const pinnedSet = new Set(pinnedNodeIds);
      nodesRef.current.forEach((node) => {
        const shouldPin = pinnedSet.has(node.id) || layoutMode === HierarchicalLayoutType;
        if (shouldPin) {
          node.fx = node.fx ?? node.x ?? 0;
          node.fy = node.fy ?? node.y ?? 0;
        } else if (dragStateRef.current?.nodeId !== node.id) {
          node.fx = null;
          node.fy = null;
        }
      });

      if (layoutMode === ForceDirectedLayoutType) {
        simulationRef.current?.alpha(0.24).restart();
      }
      scheduleRender();
    }, [layoutMode, pinnedNodeIds, scheduleRender]);

    useEffect(() => {
      const handlePointerMove = (event: PointerEvent) => {
        const activeDrag = dragStateRef.current;
        if (activeDrag) {
          const node = nodeMapRef.current.get(activeDrag.nodeId);
          if (!node) return;

          const nextPoint = toGraphPoint(event.clientX, event.clientY);
          node.fx = nextPoint.x;
          node.fy = nextPoint.y;
          node.x = nextPoint.x;
          node.y = nextPoint.y;
          activeDrag.moved = true;
          suppressClickRef.current = true;
          if (layoutMode === ForceDirectedLayoutType) {
            simulationRef.current?.alphaTarget(0.28).restart();
          }
          scheduleRender();
          return;
        }

        const activePan = panStateRef.current;
        if (activePan) {
          const deltaX = event.clientX - activePan.startClientX;
          const deltaY = event.clientY - activePan.startClientY;
          activePan.moved = activePan.moved || Math.abs(deltaX) > 2 || Math.abs(deltaY) > 2;
          setViewport((current) => ({
            ...current,
            x: activePan.originX + deltaX,
            y: activePan.originY + deltaY,
          }));
        }
      };

      const handlePointerUp = (event: PointerEvent) => {
        const activeDrag = dragStateRef.current;
        if (activeDrag) {
          const node = nodeMapRef.current.get(activeDrag.nodeId);
          if (node) {
            node.fx = node.x ?? 0;
            node.fy = node.y ?? 0;
            if (layoutMode === ForceDirectedLayoutType) {
              simulationRef.current?.alphaTarget(0);
            }
            onNodeDragEnd(activeDrag.nodeId, {
              clientX: event.clientX,
              clientY: event.clientY,
            });
          }
          dragStateRef.current = null;
          window.setTimeout(() => {
            suppressClickRef.current = false;
          }, 120);
        }

        if (panStateRef.current) {
          const wasMoved = panStateRef.current.moved;
          panStateRef.current = null;
          if (wasMoved) {
            window.setTimeout(() => {
              suppressClickRef.current = false;
            }, 80);
          }
        }
      };

      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', handlePointerUp);
      return () => {
        window.removeEventListener('pointermove', handlePointerMove);
        window.removeEventListener('pointerup', handlePointerUp);
      };
    }, [layoutMode, onNodeDragEnd, scheduleRender, toGraphPoint]);

    useEffect(() => {
      return () => {
        if (typeof window === 'undefined') return;
        if (animationFrameRef.current != null) window.cancelAnimationFrame(animationFrameRef.current);
        if (viewportAnimationRef.current != null) window.cancelAnimationFrame(viewportAnimationRef.current);
      };
    }, []);

    const handleWheel = useCallback(
      (event: React.WheelEvent<SVGSVGElement>) => {
        event.preventDefault();
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;

        const current = viewportRef.current;
        const cursorX = event.clientX - rect.left;
        const cursorY = event.clientY - rect.top;
        const worldX = (cursorX - current.x) / current.zoom;
        const worldY = (cursorY - current.y) / current.zoom;
        const nextZoom = clamp(current.zoom * (event.deltaY < 0 ? 1.08 : 0.92), 0.18, 2.4);
        setViewport({
          zoom: nextZoom,
          x: cursorX - worldX * nextZoom,
          y: cursorY - worldY * nextZoom,
        });
      },
      []
    );

    const handleBackdropPointerDown = useCallback((event: React.PointerEvent<SVGSVGElement>) => {
      const target = event.target as Element;
      if (target.closest('[data-force-node="true"]')) return;
      const current = viewportRef.current;
      panStateRef.current = {
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        originX: current.x,
        originY: current.y,
        moved: false,
      };
      suppressClickRef.current = false;
    }, []);

    const handleCanvasPointerUp = useCallback(() => {
      if (panStateRef.current?.moved) {
        suppressClickRef.current = true;
      }
    }, []);

    const renderNodes = nodesRef.current;
    const renderLinks = linksRef.current;

    return (
      <div ref={containerRef} className={cn('absolute inset-0', className)}>
        <svg
          className="absolute inset-0 h-full w-full touch-none select-none"
          onWheel={handleWheel}
          onPointerDown={handleBackdropPointerDown}
          onPointerUp={handleCanvasPointerUp}
          onClick={() => {
            if (suppressClickRef.current) {
              suppressClickRef.current = false;
              return;
            }
            onCanvasClick();
          }}
        >
          <defs>
            <filter id="module4-node-shadow" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="18" stdDeviation="14" floodColor="rgba(15,23,42,0.14)" />
            </filter>
          </defs>
          <rect x="0" y="0" width="100%" height="100%" fill="transparent" />
          <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.zoom})`}>
            {renderLinks.map((link) => {
              const source = getLinkEndpoint(link.source);
              const target = getLinkEndpoint(link.target);
              if (!source || !target) return null;

              const active = selectionNeighborhood ? selectionNeighborhood.edgeIds.has(link.id) : false;
              const dimmed = selectionNeighborhood ? !active : false;
              const midX = ((source.x || 0) + (target.x || 0)) / 2;
              const midY = ((source.y || 0) + (target.y || 0)) / 2;
              const showLabel = active || (graph.nodes.length <= 54 && viewport.zoom >= 0.6);
              const strokeColor = dimmed ? mixHexColor(link.color, '#dbe4f0', 0.58) : link.color;

              return (
                <g key={link.id}>
                  <line
                    x1={source.x || 0}
                    y1={source.y || 0}
                    x2={target.x || 0}
                    y2={target.y || 0}
                    stroke={strokeColor}
                    strokeOpacity={dimmed ? 0.28 : active ? 0.94 : 0.44}
                    strokeWidth={active ? Math.min(4.2, link.width + 0.8) : link.width}
                    strokeLinecap="round"
                  />
                  {showLabel && (
                    <g transform={`translate(${midX} ${midY})`}>
                      <rect
                        x={-34}
                        y={-9}
                        width={68}
                        height={18}
                        rx={9}
                        fill="rgba(255,255,255,0.86)"
                        stroke="rgba(203,213,225,0.9)"
                      />
                      <text
                        textAnchor="middle"
                        dominantBaseline="central"
                        fontSize={9}
                        fontWeight={700}
                        fill={dimmed ? '#94a3b8' : '#334155'}
                      >
                        {shortText(link.label, 10)}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}

            {renderNodes.map((node) => {
              const isSelected = selectedNodeId === node.id;
              const isPinned = pinnedNodeIds.includes(node.id);
              const isFocused = selectionNeighborhood ? selectionNeighborhood.nodeIds.has(node.id) : false;
              const isDimmed = selectionNeighborhood ? !isFocused : false;
              const nodeFill = isDimmed ? mixHexColor(node.color, '#e2e8f0', 0.56) : node.color;
              const shouldShowLabel = shouldRenderNodeLabel(node, {
                graphSize: graph.nodes.length,
                zoom: viewport.zoom,
                isSelected,
                isFocused,
              });
              const labelLines = splitNodeLabel(node.label, node.radius >= 30 ? 8 : 7, 2);
              const isDragging = dragStateRef.current?.nodeId === node.id;

              return (
                <g
                  key={node.id}
                  data-force-node="true"
                  transform={`translate(${node.x || 0} ${node.y || 0})`}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    dragStateRef.current = {
                      nodeId: node.id,
                      pointerId: event.pointerId,
                      moved: false,
                    };
                    suppressClickRef.current = false;
                    node.fx = node.x || 0;
                    node.fy = node.y || 0;
                    scheduleRender();
                  }}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (suppressClickRef.current) {
                      suppressClickRef.current = false;
                      return;
                    }
                    onNodeClick(node.id, {
                      clientX: event.clientX,
                      clientY: event.clientY,
                    });
                  }}
                  onDoubleClick={(event) => {
                    event.stopPropagation();
                    onNodeDoubleClick(node.id);
                  }}
                  style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
                >
                  <circle
                    r={node.radius + (isSelected ? 8 : 4)}
                    fill={isSelected ? 'rgba(15,23,42,0.08)' : 'rgba(255,255,255,0.28)'}
                  />
                  <circle
                    r={node.radius}
                    fill={nodeFill}
                    stroke={isSelected ? '#0f172a' : isPinned ? '#0f172a' : 'rgba(255,255,255,0.92)'}
                    strokeWidth={isSelected ? 3.2 : isPinned ? 2.4 : 1.6}
                    filter="url(#module4-node-shadow)"
                  />
                  <circle
                    r={Math.max(10, node.radius - 6)}
                    fill="none"
                    stroke={isSelected ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.34)'}
                    strokeWidth={1.2}
                  />
                  {shouldShowLabel &&
                    labelLines.map((line, index) => (
                      <text
                        key={`${node.id}-${line}-${index}`}
                        textAnchor="middle"
                        dominantBaseline="central"
                        y={(index - (labelLines.length - 1) / 2) * 12}
                        fontSize={node.radius >= 30 ? 11 : 10}
                        fontWeight={800}
                        fill={isDimmed ? '#475569' : '#f8fafc'}
                        style={{ pointerEvents: 'none' }}
                      >
                        {line}
                      </text>
                    ))}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    );
  }
);

export const KnowledgeNexus: React.FC = () => {
  const allowLocalFallback = useMemo(readLocalFallbackFlag, []);
  const nvlRef = useRef<ForceGraphHandle | null>(null);
  const graphHostRef = useRef<HTMLDivElement | null>(null);
  const sourceRef = useRef('storage');
  const fitPendingRef = useRef(true);

  const [graphData, setGraphData] = useState<Module4GraphResponse>(EMPTY_GRAPH);
  const [alerts, setAlerts] = useState<Module4AlertItem[]>([]);
  const [filters, setFilters] = useState<FilterState>({ query: '', nodeTypes: [] });
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(ForceDirectedLayoutType);
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [detail, setDetail] = useState<Module4NodeDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [ackingAlertId, setAckingAlertId] = useState('');
  const [message, setMessage] = useState('等待模块四图谱加载。');
  const [apiError, setApiError] = useState('');
  const [pinnedNodeIds, setPinnedNodeIds] = useState<string[]>([]);
  const [inspector, setInspector] = useState<InspectorState | null>(null);

  const deferredFilters = useDeferredValue(filters);

  const graphNodeMap = useMemo(
    () => new Map(graphData.nodes.map((node) => [node.node_id, node])),
    [graphData.nodes]
  );

  const nodeTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    graphData.nodes.forEach((node) => {
      const label = presentTypeLabel(node);
      counts[label] = (counts[label] || 0) + 1;
    });
    return counts;
  }, [graphData.nodes]);

  const nodeTypes = useMemo(
    () =>
      Object.keys(nodeTypeCounts).sort((left, right) => {
        const diff = typePriority(normalizeTypeKey(left)) - typePriority(normalizeTypeKey(right));
        return diff !== 0 ? diff : left.localeCompare(right, 'zh-CN');
      }),
    [nodeTypeCounts]
  );

  const fullGraphSignature = useMemo(
    () =>
      `${graphData.nodes.map((node) => node.node_id).sort().join('|')}::${graphData.edges
        .map((edge) => edge.edge_id)
        .sort()
        .join('|')}`,
    [graphData.edges, graphData.nodes]
  );

  const filteredGraph = useMemo(() => {
    const query = normalizeText(deferredFilters.query).toLowerCase();
    const activeTypes = new Set(deferredFilters.nodeTypes.map((item) => normalizeTypeKey(item)));

    const nodes = graphData.nodes.filter((node) => {
      const typeMatch =
        activeTypes.size === 0 ||
        activeTypes.has(typeKeyOf(node)) ||
        activeTypes.has(normalizeTypeKey(presentTypeLabel(node)));
      if (!typeMatch) return false;
      if (!query) return true;

      const haystack = [
        displayNameOfNode(node),
        summaryOfNode(node),
        presentTypeLabel(node),
        normalizeText(asRecord(node.attrs).snippet),
        normalizeText(asRecord(node.attrs).file_name),
      ]
        .join(' ')
        .toLowerCase();

      return haystack.includes(query);
    });

    const nodeIds = new Set(nodes.map((node) => node.node_id));
    const edges = graphData.edges.filter(
      (edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id)
    );

    return {
      nodes,
      edges,
      source: graphData.source,
      workspace_id: graphData.workspace_id || null,
      stats: buildStats(nodes, edges),
    } satisfies Module4GraphResponse;
  }, [deferredFilters, graphData]);

  const graphSignature = useMemo(
    () =>
      `${filteredGraph.nodes.map((node) => node.node_id).sort().join('|')}::${filteredGraph.edges
        .map((edge) => edge.edge_id)
        .sort()
        .join('|')}`,
    [filteredGraph.edges, filteredGraph.nodes]
  );

  const selectedNode = useMemo(
    () => graphNodeMap.get(selectedNodeId) || detail?.node || null,
    [detail?.node, graphNodeMap, selectedNodeId]
  );

  const currentSelectionGraph = useMemo(
    () => (selectedNodeId ? subgraphForNode(graphData, selectedNodeId) : EMPTY_GRAPH),
    [graphData, selectedNodeId]
  );

  const detailGraph = detail?.graph?.nodes.length ? detail.graph : currentSelectionGraph;
  const detailNode = detail?.node || selectedNode;
  const selectionNeighborhood = useMemo(
    () => (selectedNodeId ? selectionNeighborhoodOf(filteredGraph, selectedNodeId) : null),
    [filteredGraph, selectedNodeId]
  );

  const detailEdges = useMemo(() => {
    if (!detailNode) return [];
    return detailGraph.edges.filter(
      (edge) => edge.source_node_id === detailNode.node_id || edge.target_node_id === detailNode.node_id
    );
  }, [detailGraph.edges, detailNode]);

  const detailNeighbors = useMemo(() => {
    if (!detailNode) return [];
    const neighborIds = new Set<string>();
    detailEdges.forEach((edge) => {
      neighborIds.add(edge.source_node_id);
      neighborIds.add(edge.target_node_id);
    });
    neighborIds.delete(detailNode.node_id);

    return detailGraph.nodes
      .filter((node) => neighborIds.has(node.node_id))
      .sort((left, right) => displayNameOfNode(left).localeCompare(displayNameOfNode(right), 'zh-CN'))
      .slice(0, 8);
  }, [detailEdges, detailGraph.nodes, detailNode]);

  const pinnedSet = useMemo(() => new Set(pinnedNodeIds), [pinnedNodeIds]);

  const fitGraph = useCallback(
    (nodeIds?: string[], outOnly = false) => {
      const nvl = nvlRef.current;
      const ids = nodeIds?.length ? nodeIds : filteredGraph.nodes.map((node) => node.node_id);
      if (!nvl || !ids.length) return;

      nvl.fit(ids, {
        animated: true,
        outOnly,
        maxZoom: ids.length === 1 ? 1.14 : 1.04,
      });
    },
    [filteredGraph.nodes]
  );

  const focusNode = useCallback(
    (nodeId: string) => {
      const neighborhood = selectionNeighborhoodOf(graphData, nodeId);
      fitGraph(neighborhood ? [...neighborhood.nodeIds] : [nodeId]);
    },
    [fitGraph, graphData]
  );

  const openInspector = useCallback((nodeId: string, event?: { clientX: number; clientY: number }) => {
    const host = graphHostRef.current;
    let x = 24;
    let y = 24;
    const cardWidth = 348;
    const cardHeight = 520;

    if (host && event) {
      const rect = host.getBoundingClientRect();
      const localX = event.clientX - rect.left;
      const localY = event.clientY - rect.top;
      const preferredX = localX > rect.width * 0.62 ? localX - cardWidth - 22 : localX + 18;
      const preferredY = localY > rect.height * 0.7 ? localY - cardHeight + 40 : localY - 24;
      x = clamp(preferredX, 20, Math.max(20, rect.width - cardWidth));
      y = clamp(preferredY, 20, Math.max(20, rect.height - cardHeight));
    }

    if (host && !event) {
      const rect = host.getBoundingClientRect();
      const point = nvlRef.current?.getNodeScreenPosition(nodeId);
      if (point) {
        const preferredX = point.x > rect.width * 0.62 ? point.x - cardWidth - 22 : point.x + 22;
        const preferredY = point.y > rect.height * 0.7 ? point.y - cardHeight + 40 : point.y - 28;
        x = clamp(preferredX, 20, Math.max(20, rect.width - cardWidth));
        y = clamp(preferredY, 20, Math.max(20, rect.height - cardHeight));
      } else {
        x = clamp(rect.width - cardWidth, 20, Math.max(20, rect.width - cardWidth));
        y = 24;
      }
    }

    setSelectedNodeId(nodeId);
    setInspector({ nodeId, x, y });
  }, []);

  const closeInspector = useCallback(() => {
    setSelectedNodeId('');
    setInspector(null);
    setDetail(null);
  }, []);

  const loadGraph = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!options?.silent) setLoading(true);
      setApiError('');

      const [graphResult, alertResult] = await Promise.allSettled([
        fetchModule4Graph({ limitNodes: 1200, limitEdges: 2400 }),
        fetchModule4Alerts({ status: 'open', pageSize: 8 }),
      ]);

      let nextGraph = EMPTY_GRAPH;
      let nextSource = 'storage';

      if (graphResult.status === 'fulfilled' && graphResult.value.nodes.length > 0) {
        nextGraph = graphResult.value;
        nextSource = 'storage';
        setMessage('点击节点查看详情，双击扩展邻域，拖拽节点可固定位置。');
      } else {
        const localDocs = allowLocalFallback ? readExtractionDocuments() : [];
        if (localDocs.length > 0) {
          nextGraph = localFallback(localDocs);
          nextSource = 'local-fallback';
          setMessage('当前正在使用模块二本地结果兜底展示，等待模块四图谱同步完成。');
        } else {
          setMessage('当前还没有可展示的图谱数据。');
        }
      }

      if (graphResult.status === 'rejected') {
        setApiError(graphResult.reason instanceof Error ? graphResult.reason.message : '图谱加载失败');
      }

      if (alertResult.status === 'fulfilled') {
        setAlerts(alertResult.value.items);
      } else {
        setAlerts([]);
      }

      sourceRef.current = nextSource;
      fitPendingRef.current = true;
      startTransition(() => setGraphData(nextGraph));

      if (!options?.silent) setLoading(false);
    },
    [allowLocalFallback]
  );

  const expandNeighborhood = useCallback(
    async (nodeId = selectedNodeId) => {
      if (!nodeId) return;
      setExpanding(true);
      try {
        const neighborhood = await fetchModule4Neighborhood(nodeId, { depth: 1, limit: 280 });
        sourceRef.current = 'storage';
        fitPendingRef.current = true;
        startTransition(() => {
          setGraphData((current) => mergeGraph(current, neighborhood));
        });
        setDetail({
          node: neighborhood.nodes.find((item) => item.node_id === nodeId) || detailNode || null,
          graph: neighborhood,
        });
        const nodeForMessage =
          neighborhood.nodes.find((item) => item.node_id === nodeId) || detailNode || selectedNode;
        setMessage(
          nodeForMessage
            ? `已扩展节点「${displayNameOfNode(nodeForMessage)}」的邻域。`
            : '已扩展节点邻域。'
        );
        window.setTimeout(() => focusNode(nodeId), 160);
      } catch (error) {
        setApiError(error instanceof Error ? error.message : '扩展邻域失败');
      } finally {
        setExpanding(false);
      }
    },
    [detailNode, focusNode, selectedNode, selectedNodeId]
  );

  const openNodeFromAlert = useCallback(
    async (item: Module4AlertItem) => {
      const nodeId = item.subject_node_id;
      if (!nodeId) return;

      if (!graphNodeMap.has(nodeId)) {
        try {
          const neighborhood = await fetchModule4Neighborhood(nodeId, { depth: 1, limit: 200 });
          sourceRef.current = 'storage';
          fitPendingRef.current = true;
          startTransition(() => {
            setGraphData((current) => mergeGraph(current, neighborhood));
          });
        } catch (error) {
          setApiError(error instanceof Error ? error.message : '无法定位告警节点');
        }
      }

      openInspector(nodeId);
      window.setTimeout(() => focusNode(nodeId), 120);
    },
    [focusNode, graphNodeMap, openInspector]
  );

  const togglePin = useCallback(
    (nodeId = selectedNodeId) => {
      if (!nodeId) return;
      const nvl = nvlRef.current;
      setPinnedNodeIds((current) => {
        const shouldPin = !current.includes(nodeId);
        if (nvl) {
          if (shouldPin) {
            nvl.pinNode(nodeId);
          } else {
            nvl.unPinNode([nodeId]);
          }
        }
        return shouldPin ? [...current, nodeId] : current.filter((item) => item !== nodeId);
      });
    },
    [selectedNodeId]
  );

  const adjustZoom = useCallback(
    (delta: number) => {
      const nvl = nvlRef.current;
      if (!nvl) return;
      const nextZoom = clamp(nvl.getScale() + delta, 0.2, 2.4);
      nvl.setZoom(nextZoom);
    },
    []
  );

  const handleAckAlert = useCallback(async (alertId: string) => {
    setAckingAlertId(alertId);
    try {
      await ackModule4Alert(alertId);
      const next = await fetchModule4Alerts({ status: 'open', pageSize: 8 });
      setAlerts(next.items);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : '确认告警失败');
    } finally {
      setAckingAlertId('');
    }
  }, []);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  useEffect(() => {
    if (!allowLocalFallback) return () => undefined;

    const handleExtractionUpdate = () => {
      const localDocs = readExtractionDocuments();
      if (localDocs.length > 0 && sourceRef.current !== 'storage') {
        startTransition(() => {
          setGraphData(localFallback(localDocs));
        });
      }
      void loadGraph({ silent: true });
    };

    const unsubscribe = subscribeExtractionUpdates(handleExtractionUpdate);
    return unsubscribe;
  }, [allowLocalFallback, loadGraph]);

  useEffect(() => {
    fitPendingRef.current = true;

    const validNodeIds = new Set(graphData.nodes.map((node) => node.node_id));
    setPinnedNodeIds((current) => current.filter((nodeId) => validNodeIds.has(nodeId)));
  }, [fullGraphSignature, graphData.nodes]);

  useEffect(() => {
    if (!selectedNodeId) return;
    if (filteredGraph.nodes.some((node) => node.node_id === selectedNodeId)) return;
    closeInspector();
  }, [closeInspector, filteredGraph.nodes, selectedNodeId]);

  useEffect(() => {
    if (!selectedNodeId) {
      setDetail(null);
      return;
    }

    const fallbackNode = graphNodeMap.get(selectedNodeId) || null;
    const fallbackGraph = subgraphForNode(graphData, selectedNodeId);
    if (fallbackNode) {
      setDetail({ node: fallbackNode, graph: fallbackGraph });
    }

    let cancelled = false;
    void fetchModule4NodeDetail(selectedNodeId, { limit: 180 })
      .then((result) => {
        if (cancelled) return;
        setDetail(result);
      })
      .catch(() => {
        if (cancelled || !fallbackNode) return;
        setDetail({ node: fallbackNode, graph: fallbackGraph });
      });

    return () => {
      cancelled = true;
    };
  }, [graphData, graphNodeMap, selectedNodeId]);

  useEffect(() => {
    if (!filteredGraph.nodes.length || !fitPendingRef.current) return () => undefined;

    const delay = layoutMode === ForceDirectedLayoutType ? 280 : 120;
    const timer = window.setTimeout(() => {
      fitPendingRef.current = false;
      fitGraph(undefined, true);
    }, delay);

    return () => window.clearTimeout(timer);
  }, [filteredGraph.nodes.length, fitGraph, graphSignature, layoutMode]);

  useEffect(() => {
    const nvl = nvlRef.current;
    if (!nvl) return;

    const visibleIds = new Set(filteredGraph.nodes.map((node) => node.node_id));
    const toUnpin = filteredGraph.nodes
      .map((node) => node.node_id)
      .filter((nodeId) => !pinnedSet.has(nodeId));

    if (toUnpin.length) nvl.unPinNode(toUnpin);
    pinnedNodeIds.forEach((nodeId) => {
      if (visibleIds.has(nodeId)) nvl.pinNode(nodeId);
    });
  }, [filteredGraph.nodes, pinnedNodeIds, pinnedSet]);

  const selectedPinned = detailNode ? pinnedSet.has(detailNode.node_id) : false;
  const sourceLabel = sourceRef.current === 'local-fallback' ? '模块二兜底图谱' : '模块四知识图谱';
  const openAlertCount = alerts.filter((item) => item.status === 'open').length;

  const metricCards = [
    {
      label: '节点总数',
      value: String(graphData.stats.node_count || graphData.nodes.length),
      tone: 'from-blue-500/12 to-blue-500/0 text-blue-700 border-blue-200/70',
    },
    {
      label: '关系总数',
      value: String(graphData.stats.edge_count || graphData.edges.length),
      tone: 'from-cyan-500/12 to-cyan-500/0 text-cyan-700 border-cyan-200/70',
    },
    {
      label: '待处理告警',
      value: String(openAlertCount),
      tone: 'from-amber-500/12 to-amber-500/0 text-amber-700 border-amber-200/70',
    },
  ];

  useEffect(() => {
    if (!import.meta.env.DEV || typeof window === 'undefined') return () => undefined;

    const debugApi = {
      openNode: (nodeId: string) => openInspector(nodeId),
      focusNode,
      expandNeighborhood,
      getGraph: () => graphData,
      getSelectedNodeId: () => selectedNodeId,
    };

    (window as Window & { __module4GraphDebug?: typeof debugApi }).__module4GraphDebug = debugApi;

    return () => {
      delete (window as Window & { __module4GraphDebug?: typeof debugApi }).__module4GraphDebug;
    };
  }, [expandNeighborhood, focusNode, graphData, openInspector, selectedNodeId]);

  return (
    <section className="relative h-[calc(100vh-2rem)] overflow-hidden rounded-[30px] border border-slate-200/70 bg-[linear-gradient(135deg,#fffefb_0%,#f7fafc_42%,#eef4ff_100%)] shadow-[0_24px_80px_rgba(15,23,42,0.12)]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.16),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(14,165,233,0.12),transparent_26%),linear-gradient(180deg,rgba(255,255,255,0.62),rgba(255,255,255,0.18))]" />
      <div className="absolute inset-y-0 left-[340px] hidden w-px bg-gradient-to-b from-transparent via-slate-200/70 to-transparent xl:block" />

      <div className="relative flex h-full flex-col xl:flex-row">
        <aside className="w-full shrink-0 border-b border-slate-200/70 bg-white/72 backdrop-blur-xl xl:w-[340px] xl:border-b-0 xl:border-r">
          <div className="flex h-full flex-col">
            <div className="border-b border-slate-200/70 px-6 py-6">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Module 4 / Graph Workbench
                  </div>
                  <h2 className="mt-2 text-[28px] font-semibold tracking-tight text-slate-900">
                    全域知识图谱
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    Neo4j 风格的图谱工作台。单击节点查看详情，双击扩展邻域，拖拽节点后会保持当前位置。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadGraph()}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-slate-200 bg-white/85 text-slate-600 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
                  aria-label="刷新图谱"
                >
                  <RefreshCw size={18} className={cn(loading && 'animate-spin')} />
                </button>
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-[11px] font-medium text-slate-600">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  {sourceLabel}
                </span>
                <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-[11px] font-medium text-slate-600">
                  {layoutMode === ForceDirectedLayoutType ? <Orbit size={12} /> : <Network size={12} />}
                  {layoutMode === ForceDirectedLayoutType ? '力导布局' : '层级布局'}
                </span>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-3">
                {metricCards.map((card) => (
                  <div
                    key={card.label}
                    className={cn('rounded-2xl border bg-gradient-to-br px-3 py-3', card.tone)}
                  >
                    <div className="text-[11px] font-medium text-slate-500">{card.label}</div>
                    <div className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
                      {card.value}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-2xl border border-slate-200 bg-white/80 px-4 py-3 shadow-sm">
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  搜索节点
                </label>
                <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2">
                  <Search size={16} className="text-slate-400" />
                  <input
                    value={filters.query}
                    onChange={(event) =>
                      setFilters((current) => ({ ...current, query: event.target.value }))
                    }
                    placeholder="搜索实体、表格、文档或风险"
                    className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
                  />
                </div>
              </div>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
              <section className="rounded-[24px] border border-slate-200/80 bg-white/75 p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">节点类型</h3>
                    <p className="text-xs text-slate-500">按类型筛选当前图谱</p>
                  </div>
                  {filters.nodeTypes.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setFilters((current) => ({ ...current, nodeTypes: [] }))}
                      className="text-xs font-medium text-blue-600 transition hover:text-blue-700"
                    >
                      清空
                    </button>
                  )}
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {nodeTypes.map((label) => {
                    const active = filters.nodeTypes.includes(label);
                    const count = nodeTypeCounts[label] || 0;
                    const color = visualSpecOf({
                      node_id: label,
                      node_type: normalizeTypeKey(label),
                      canonical_key: label,
                      display_name: label,
                      confidence: 0,
                      attrs: {},
                    }).color;

                    return (
                      <button
                        key={label}
                        type="button"
                        onClick={() =>
                          setFilters((current) => ({
                            ...current,
                            nodeTypes: current.nodeTypes.includes(label)
                              ? current.nodeTypes.filter((item) => item !== label)
                              : [...current.nodeTypes, label],
                          }))
                        }
                        className={cn(
                          'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition',
                          active
                            ? 'border-slate-900 bg-slate-900 text-white shadow-[0_10px_25px_rgba(15,23,42,0.16)]'
                            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
                        )}
                      >
                        <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                        {label}
                        <span
                          className={cn(
                            'rounded-full px-1.5 py-0.5 text-[10px]',
                            active ? 'bg-white/18 text-white' : 'bg-slate-100 text-slate-500'
                          )}
                        >
                          {count}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>

              <section className="rounded-[24px] border border-slate-200/80 bg-white/75 p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">告警队列</h3>
                    <p className="text-xs text-slate-500">点击跳转到对应节点</p>
                  </div>
                  <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
                    {openAlertCount} 条
                  </span>
                </div>

                <div className="mt-4 space-y-3">
                  {alerts.length === 0 && (
                    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 px-4 py-6 text-center text-sm text-slate-500">
                      当前没有待处理告警
                    </div>
                  )}

                  {alerts.map((alert) => (
                    <div
                      key={alert.alert_id}
                      className="rounded-2xl border border-slate-200 bg-white/85 p-3 transition hover:border-slate-300 hover:shadow-sm"
                    >
                      <button
                        type="button"
                        onClick={() => void openNodeFromAlert(alert)}
                        className="w-full text-left"
                      >
                        <div className="flex items-start gap-3">
                          <div
                            className={cn(
                              'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl',
                              alert.severity === 'red'
                                ? 'bg-rose-100 text-rose-600'
                                : alert.severity === 'orange'
                                  ? 'bg-amber-100 text-amber-700'
                                  : 'bg-yellow-100 text-yellow-700'
                            )}
                          >
                            <AlertTriangle size={16} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                                {severityLabel(alert.severity)}
                              </span>
                              <span className="text-[11px] text-slate-400">{alertStatusLabel(alert.status)}</span>
                            </div>
                            <div className="mt-2 text-sm font-semibold text-slate-900">{alert.title}</div>
                            <p className="mt-1 text-xs leading-5 text-slate-500">{alert.summary}</p>
                          </div>
                        </div>
                      </button>

                      <div className="mt-3 flex items-center justify-between gap-3">
                        <div className="text-[11px] text-slate-400">风险分 {Math.round(alert.risk_score)}</div>
                        <button
                          type="button"
                          onClick={() => void handleAckAlert(alert.alert_id)}
                          disabled={ackingAlertId === alert.alert_id}
                          className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium text-slate-600 transition hover:border-blue-300 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {ackingAlertId === alert.alert_id ? '确认中…' : '确认'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-[24px] border border-slate-200/80 bg-white/75 p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-slate-900">使用提示</h3>
                <div className="mt-3 space-y-2 text-sm leading-6 text-slate-600">
                  <p>1. 单击节点后会在图中浮出详情卡，不再固定在右侧。</p>
                  <p>2. 双击节点可增量拉取邻域，让图谱像 Neo4j Browser 一样扩展。</p>
                  <p>3. 拖拽节点后会固定其位置，周围节点会跟随力导向重新平衡。</p>
                </div>
              </section>
            </div>
          </div>
        </aside>

        <div className="relative flex min-h-0 flex-1 flex-col">
          <header className="border-b border-slate-200/70 bg-white/38 px-5 py-4 backdrop-blur-xl">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-[11px] font-medium text-slate-500">
                  <span className="rounded-full border border-slate-200 bg-white/70 px-2.5 py-1">
                    当前渲染 {filteredGraph.nodes.length} 个节点 / {filteredGraph.edges.length} 条关系
                  </span>
                  {apiError && (
                    <span className="rounded-full border border-rose-200 bg-rose-50 px-2.5 py-1 text-rose-600">
                      {apiError}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{message}</p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setLayoutMode((current) =>
                      current === ForceDirectedLayoutType ? HierarchicalLayoutType : ForceDirectedLayoutType
                    )
                  }
                  className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white/85 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-900"
                >
                  {layoutMode === ForceDirectedLayoutType ? <Network size={16} /> : <Orbit size={16} />}
                  {layoutMode === ForceDirectedLayoutType ? '切换层级布局' : '切换力导布局'}
                </button>
                <button
                  type="button"
                  onClick={() => fitGraph(undefined, true)}
                  className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white/85 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-900"
                >
                  <Focus size={16} />
                  自适应视图
                </button>
              </div>
            </div>
          </header>

          <div
            ref={graphHostRef}
            data-testid="module4-graph-host"
            className="relative min-h-0 flex-1 overflow-hidden"
          >
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.72),transparent_48%),radial-gradient(circle_at_20%_20%,rgba(37,99,235,0.08),transparent_30%),radial-gradient(circle_at_80%_80%,rgba(14,165,233,0.08),transparent_26%)]" />
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-white/70 to-transparent" />

            {filteredGraph.nodes.length === 0 ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
                <div className="rounded-[28px] border border-dashed border-slate-300/80 bg-white/70 px-8 py-10 shadow-sm backdrop-blur-sm">
                  <h3 className="text-xl font-semibold tracking-tight text-slate-900">暂无可渲染图谱</h3>
                  <p className="mt-3 max-w-md text-sm leading-6 text-slate-600">
                    当前筛选条件下没有节点。可以清空筛选，或先在模块二上传文档并等待模块四图谱同步。
                  </p>
                </div>
              </div>
            ) : (
              <Neo4jStyleForceGraph
                ref={nvlRef}
                graph={filteredGraph}
                layoutMode={layoutMode}
                selectedNodeId={selectedNodeId}
                pinnedNodeIds={pinnedNodeIds}
                selectionNeighborhood={selectionNeighborhood}
                onNodeClick={(nodeId, point) => {
                  openInspector(nodeId, point);
                }}
                onNodeDoubleClick={(nodeId) => {
                  openInspector(nodeId);
                  void expandNeighborhood(nodeId);
                }}
                onCanvasClick={closeInspector}
                onNodeDragEnd={(nodeId, point) => {
                  setPinnedNodeIds((current) => Array.from(new Set([...current, nodeId])));
                  openInspector(nodeId, point);
                }}
                className="absolute inset-0"
              />
            )}

            <div className="pointer-events-none absolute left-5 bottom-5 rounded-2xl border border-slate-200/80 bg-white/78 px-4 py-3 text-xs leading-6 text-slate-500 shadow-sm backdrop-blur-md">
              单击节点查看详情，双击扩展邻域，拖拽后节点会保持位置。
            </div>

            <div className="absolute bottom-5 right-5 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => adjustZoom(0.1)}
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white/88 text-slate-700 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
                aria-label="放大"
              >
                <Plus size={18} />
              </button>
              <button
                type="button"
                onClick={() => adjustZoom(-0.1)}
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white/88 text-slate-700 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
                aria-label="缩小"
              >
                <Minus size={18} />
              </button>
              <button
                type="button"
                onClick={() => void loadGraph()}
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white/88 text-slate-700 shadow-sm transition hover:border-blue-300 hover:text-blue-700"
                aria-label="刷新"
              >
                <RefreshCw size={18} className={cn(loading && 'animate-spin')} />
              </button>
            </div>

            <AnimatePresence>
              {inspector && detailNode && (
                <motion.div
                  initial={{ opacity: 0, y: 16, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 14, scale: 0.97 }}
                  transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
                  className="pointer-events-none absolute z-20"
                  style={{ left: inspector.x, top: inspector.y }}
                >
                  <div className="pointer-events-auto w-[min(348px,calc(100vw-3rem))] overflow-hidden rounded-[28px] border border-slate-200/80 bg-white/90 shadow-[0_24px_60px_rgba(15,23,42,0.16)] backdrop-blur-xl">
                    <div className="border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.92))] px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-white">
                              {presentTypeLabel(detailNode)}
                            </span>
                            {selectedPinned && (
                              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-[10px] font-semibold text-blue-700">
                                已固定
                              </span>
                            )}
                          </div>
                          <h3 className="mt-3 text-lg font-semibold tracking-tight text-slate-900">
                            {displayNameOfNode(detailNode)}
                          </h3>
                          {summaryOfNode(detailNode) && (
                            <p className="mt-2 text-sm leading-6 text-slate-600">{summaryOfNode(detailNode)}</p>
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={closeInspector}
                          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:text-slate-900"
                          aria-label="关闭详情"
                        >
                          <X size={16} />
                        </button>
                      </div>
                    </div>

                    <div className="custom-scrollbar max-h-[min(62vh,540px)] space-y-4 overflow-y-auto px-4 py-4">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={() => togglePin(detailNode.node_id)}
                          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                        >
                          <Pin size={13} />
                          {selectedPinned ? '取消固定' : '固定节点'}
                        </button>
                        <button
                          type="button"
                          onClick={() => focusNode(detailNode.node_id)}
                          className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                        >
                          <Focus size={13} />
                          聚焦节点
                        </button>
                        <button
                          type="button"
                          onClick={() => void expandNeighborhood(detailNode.node_id)}
                          className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 transition hover:border-blue-300 hover:bg-blue-100"
                        >
                          <Network size={13} />
                          {expanding ? '扩展中…' : '扩展邻域'}
                        </button>
                      </div>

                      {detailFactsOfNode(detailNode).length > 0 && (
                        <div className="grid grid-cols-2 gap-2">
                          {detailFactsOfNode(detailNode).map((fact) => (
                            <div
                              key={`${fact.label}-${fact.value}`}
                              className="rounded-2xl border border-slate-200 bg-slate-50/80 px-3 py-2"
                            >
                              <div className="text-[11px] font-medium text-slate-500">{fact.label}</div>
                              <div className="mt-1 text-sm font-medium text-slate-900">{fact.value}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {detailNeighbors.length > 0 && (
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                            相关节点
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {detailNeighbors.map((neighbor) => (
                              <button
                                key={neighbor.node_id}
                                type="button"
                                onClick={() => {
                                  startTransition(() => {
                                    setGraphData((current) => mergeGraph(current, detailGraph));
                                  });
                                  openInspector(neighbor.node_id);
                                  window.setTimeout(() => focusNode(neighbor.node_id), 120);
                                }}
                                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                              >
                                <span
                                  className="h-2.5 w-2.5 rounded-full"
                                  style={{ backgroundColor: visualSpecOf(neighbor).color }}
                                />
                                {shortText(displayNameOfNode(neighbor), 20)}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {attributeRowsOfNode(detailNode).length > 0 && (
                        <div className="space-y-2">
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                            节点属性
                          </div>
                          {attributeRowsOfNode(detailNode).map((row) => (
                            <div
                              key={`${row.label}-${row.value}`}
                              className="flex items-start justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2"
                            >
                              <div className="text-xs font-medium text-slate-500">{row.label}</div>
                              <div className="max-w-[200px] text-right text-sm text-slate-700">{row.value}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {detailEdges.length > 0 && (
                        <div className="rounded-2xl border border-slate-200 bg-slate-50/70 px-3 py-3">
                          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                            邻接关系
                          </div>
                          <div className="mt-3 space-y-2">
                            {detailEdges.slice(0, 6).map((edge) => (
                              <div
                                key={edge.edge_id}
                                className="flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2 text-xs text-slate-600"
                              >
                                <span>{presentRelationLabel(edge)}</span>
                                <span
                                  className="rounded-full px-2 py-0.5 text-[10px] font-semibold text-slate-500"
                                  style={{ backgroundColor: `${relationToneOf(edge)}20` }}
                                >
                                  {Math.round(edge.confidence * 100)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
};
