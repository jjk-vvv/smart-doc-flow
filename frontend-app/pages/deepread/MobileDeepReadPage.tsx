import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  BarChart3,
  Bot,
  Download,
  ExternalLink,
  FileSearch,
  ImageIcon,
  LayoutList,
  Loader2,
  RefreshCcw,
  Table2,
  Trash2,
  Search,
  FileText,
  FileSpreadsheet,
  MonitorPlay,
  File,
  Play,
  RotateCcw,
  UploadCloud,
  X,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { parseErrorMessage } from '../../shared/api/client';
import { MobileAssistantDialog } from './mobile/MobileAssistantDialog';
import { MobileDocumentPreviewCard } from './mobile/MobileDocumentPreviewCard';
import TraceChartPreview from '../../components/trace/TraceChartPreview';
import headerIllustration from '../../assets/插图1.png';
import bodyIllustration from '../../assets/插图三.png';
import allIcon from '../../assets/文档.png';
import pdfIcon from '../../assets/pdf.png';
import wordIcon from '../../assets/WORD.png';
import excelIcon from '../../assets/xlsx.png';
import txtIcon from '../../assets/txt.png';
import mdIcon from '../../assets/md.png';
import aiAssistantIcon from '../../assets/模块二智能助手图标.png';
import {
  requestExtractionJobCancelFile,
  requestExtractionJobCreateWithRetry,
  requestExtractionJobStatus,
  requestTraceLocate,
  resolveExtractBase,
  resolveExtractArtifactUrlFromTraceHit,
  resolveExtractTableDownloadUrlFromTraceHit,
} from '../../shared/api/extraction';
import {
  countExtractionDocumentFields,
  filterAutoRestorableExtractionDocuments,
  readExtractionDocuments,
  subscribeExtractionUpdates,
  type ExtractionDocument,
  type TraceHit,
  writeExtractionDocuments,
} from '../../shared/state/extractionDocuments';
import type { AssistantCitation } from './assistant/types';
import {
  getTraceChartPointCount,
  getTraceChartSpec,
  getTraceChartSummary,
  getTraceChartTitle,
} from '../../shared/trace/chartSpec';

type ArtifactTab = 'fields' | 'tables' | 'charts' | 'images';
type TraceKind = 'field' | 'table' | 'chart' | 'image' | 'other';
type QuickUploadShortcutId = 'all' | 'pdf' | 'word' | 'excel' | 'txt' | 'md';

type QuickUploadShortcut = {
  id: QuickUploadShortcutId;
  label: string;
  hint: string;
  accept: string;
  icon?: LucideIcon;
  iconImg?: string;
  color: string;
  activeBg: string;
  activeBorder: string;
};

type DataframePayload = {
  headers: string[];
  rows: string[][];
  rowCount: number;
  colCount: number;
};

type UploadTaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

type UploadQueueItem = {
  id: string;
  file: File;
  status: UploadTaskStatus;
  message: string;
  jobId?: string;
  fileHash?: string;
  resolvedFileName?: string;
};

type ExtractionJobFilePayload = {
  file_name?: string;
  file_hash?: string;
  artifact_file_id?: string | null;
  artifact_by_file_url?: string | null;
  artifact_url?: string | null;
};

const isObjectRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

const toDisplayValue = (value: unknown): string => {
  if (value == null) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? '').trim()).filter(Boolean).join(' / ');
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));

const parseMaybeJson = (value: unknown): unknown => {
  if (typeof value !== 'string') return value;
  const text = value.trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return value;
  }
};

const getHitLocator = (hit: TraceHit): Record<string, unknown> => {
  if (!isObjectRecord(hit.locator)) return {};
  return hit.locator;
};

const toDataframePayload = (value: unknown): DataframePayload => {
  const source = parseMaybeJson(value);
  const payload = isObjectRecord(source) ? source : {};
  const headers = Array.isArray(payload.headers)
    ? payload.headers.map((item) => String(item ?? '').trim())
    : [];
  const rows = Array.isArray(payload.rows)
    ? payload.rows.map((row) =>
        Array.isArray(row) ? row.map((cell) => String(cell ?? '').trim()) : [],
      )
    : [];
  const rowCountRaw = Number(payload.row_count ?? rows.length);
  const colCountRaw = Number(
    payload.col_count ?? Math.max(headers.length, ...rows.map((row) => row.length), 0),
  );
  return {
    headers,
    rows,
    rowCount: Number.isFinite(rowCountRaw) && rowCountRaw > 0 ? Math.round(rowCountRaw) : rows.length,
    colCount: Number.isFinite(colCountRaw) && colCountRaw > 0
      ? Math.round(colCountRaw)
      : Math.max(headers.length, ...rows.map((row) => row.length), 0),
  };
};

const pickBestDataframe = (...values: unknown[]): DataframePayload => {
  const scored = values.map((value) => {
    const payload = toDataframePayload(value);
    const nonEmptyCount = payload.rows.reduce(
      (acc, row) => acc + row.filter((cell) => cell.trim().length > 0).length,
      0,
    );
    const score = payload.rows.length * 10000 + payload.headers.length * 100 + nonEmptyCount;
    return { payload, score };
  });
  scored.sort((a, b) => b.score - a.score);
  return scored[0]?.payload ?? { headers: [], rows: [], rowCount: 0, colCount: 0 };
};

const isTableLikeFigureTrace = (hit: TraceHit): boolean => {
  const locator = getHitLocator(hit);
  const figureType = String(locator.figure_type || '').trim().toLowerCase();
  if (figureType === 'table' || figureType === 'spreadsheet') return true;
  const contentModes = Array.isArray(locator.content_modes)
    ? locator.content_modes.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : [];
  const payload = pickBestDataframe(locator.dataframe, locator.table_preview, locator.dataframe_json);
  const hasDataframe = payload.headers.length > 0 || payload.rows.length > 0;
  return hasDataframe && !contentModes.includes('visual') && !contentModes.includes('topology');
};

const getTraceKind = (hit: TraceHit): TraceKind => {
  const objectType = String(hit.object_type || '').trim().toLowerCase();
  if (objectType === 'field') return 'field';
  if (objectType === 'table') return 'table';
  if (objectType === 'chart') return 'chart';
  if (objectType === 'figure' || objectType === 'image') {
    return isTableLikeFigureTrace(hit) ? 'table' : 'image';
  }
  return 'other';
};

const toImageCaption = (hit: TraceHit): string => {
  const locator = getHitLocator(hit);
  const caption = String(locator.caption || '').trim();
  if (caption) return caption;
  const keyPoints = Array.isArray(locator.key_points)
    ? locator.key_points.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  if (keyPoints.length > 0) return keyPoints.join(' / ');
  const snippet = String(hit.snippet || '').trim();
  return snippet || '暂无图片说明';
};

const triggerBlobDownload = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

const toCsvRow = (cells: string[]): string =>
  cells.map((cell) => `"${String(cell || '').replace(/"/g, '""')}"`).join(',');

const downloadDataframeAsCsv = (payload: DataframePayload, filename: string) => {
  const lines: string[] = [];
  if (payload.headers.length > 0) lines.push(toCsvRow(payload.headers));
  payload.rows.forEach((row) => lines.push(toCsvRow(row)));
  const csv = `\uFEFF${lines.join('\n')}`;
  triggerBlobDownload(new Blob([csv], { type: 'text/csv;charset=utf-8;' }), filename);
};

const toFileBaseName = (value: string): string => {
  const text = String(value || '').trim();
  if (!text) return 'document';
  const safe = text.replace(/[<>:"/\\|?*\u0000-\u001F]+/g, '_');
  const dotIdx = safe.lastIndexOf('.');
  return dotIdx > 0 ? safe.slice(0, dotIdx) : safe;
};

const normalizeFileName = (value: string): string => String(value || '').trim().toLowerCase();

const getFileExtension = (value: string): string => {
  const normalized = normalizeFileName(value);
  const dotIdx = normalized.lastIndexOf('.');
  return dotIdx >= 0 ? normalized.slice(dotIdx + 1) : '';
};

const mergeDocuments = (
  previousDocs: ExtractionDocument[],
  incomingDocs: ExtractionDocument[],
): ExtractionDocument[] => {
  const previous = Array.isArray(previousDocs) ? previousDocs : [];
  const incoming = Array.isArray(incomingDocs) ? incomingDocs : [];
  if (incoming.length === 0) return previous;
  const map = new Map<string, ExtractionDocument>();
  previous.forEach((doc) => map.set(String(doc.file_hash || ''), doc));
  incoming.forEach((doc) => map.set(String(doc.file_hash || ''), doc));
  return Array.from(map.values());
};

const normalizeExtractionJobFiles = (value: unknown): ExtractionJobFilePayload[] => {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => isObjectRecord(item))
    .map((item) => ({
      file_name: String(item.file_name || '').trim() || undefined,
      file_hash: String(item.file_hash || '').trim() || undefined,
      artifact_file_id: String(item.artifact_file_id || '').trim() || null,
      artifact_by_file_url: String(item.artifact_by_file_url || '').trim() || null,
      artifact_url: String(item.artifact_url || '').trim() || null,
    }));
};

const findJobFileForDocument = (
  document: ExtractionDocument,
  files: ExtractionJobFilePayload[],
): ExtractionJobFilePayload | null => {
  const targetHash = String(document.file_hash || '').trim();
  const targetName = normalizeFileName(document.file_name);
  if (targetHash) {
    const byHash = files.find((item) => String(item.file_hash || '').trim() === targetHash);
    if (byHash) return byHash;
  }
  if (targetName) {
    const byName = files.find((item) => normalizeFileName(String(item.file_name || '')) === targetName);
    if (byName) return byName;
  }
  return null;
};

const attachSourceArtifactDiagnostics = (
  document: ExtractionDocument,
  filePayload: ExtractionJobFilePayload | null,
): ExtractionDocument => {
  if (!filePayload) return document;
  const artifactByFileUrl = String(filePayload.artifact_by_file_url || '').trim();
  const artifactFileId = String(filePayload.artifact_file_id || '').trim();
  const artifactUrl = String(filePayload.artifact_url || '').trim();
  if (!artifactByFileUrl && !artifactFileId && !artifactUrl) {
    return document;
  }
  const diagnostics = isObjectRecord(document.diagnostics) ? { ...document.diagnostics } : {};
  if (artifactByFileUrl) diagnostics.source_artifact_by_file_url = artifactByFileUrl;
  if (artifactFileId) diagnostics.source_artifact_file_id = artifactFileId;
  if (artifactUrl) diagnostics.source_artifact_url = artifactUrl;
  return {
    ...document,
    diagnostics,
  };
};

const QUICK_UPLOAD_ALL_ACCEPT =
  '.pdf,.doc,.docx,.xlsx,.txt,.md';

const QUEUE_PREVIEW_HASH_PREFIX = 'queue-preview:';

const toQueuePreviewHash = (itemId: string): string =>
  `${QUEUE_PREVIEW_HASH_PREFIX}${String(itemId || '').trim()}`;

const getQueuePreviewItemId = (hash: string): string => {
  const normalized = String(hash || '').trim();
  if (!normalized.startsWith(QUEUE_PREVIEW_HASH_PREFIX)) return '';
  return normalized.slice(QUEUE_PREVIEW_HASH_PREFIX.length);
};

const QUICK_UPLOAD_SCHEMA = JSON.stringify({
  auto_infer: true,
  prefer_llm: true,
  max_auto_fields: 20,
});

const POLL_INTERVAL_MS = 900;
const POLL_TIMEOUT_MS = 12 * 60 * 1000;
const SUPPORTED_UPLOAD_EXTENSIONS = new Set(['pdf', 'doc', 'docx', 'xlsx', 'txt', 'md']);

const UPLOAD_STATUS_LABELS: Record<UploadTaskStatus, string> = {
  queued: '待确认',
  running: '解析中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

const QUICK_UPLOAD_SHORTCUTS: QuickUploadShortcut[] = [
  {
    id: 'all',
    label: '全部',
    hint: '支持所有',
    accept: QUICK_UPLOAD_ALL_ACCEPT,
    iconImg: allIcon,
    color: 'text-slate-600',
    activeBg: 'bg-slate-100 dark:bg-slate-500/10',
    activeBorder: 'border-slate-300 dark:border-slate-500/30',
  },
  {
    id: 'pdf',
    label: 'PDF',
    hint: '扫描/原生',
    accept: '.pdf',
    iconImg: pdfIcon,
    color: 'text-red-500',
    activeBg: 'bg-red-50 dark:bg-red-500/10',
    activeBorder: 'border-red-200 dark:border-red-500/30',
  },
  {
    id: 'word',
    label: 'Word',
    hint: 'doc/docx',
    accept: '.doc,.docx',
    iconImg: wordIcon,
    color: 'text-blue-500',
    activeBg: 'bg-blue-50 dark:bg-blue-500/10',
    activeBorder: 'border-blue-200 dark:border-blue-500/30',
  },
  {
    id: 'excel',
    label: 'Excel',
    hint: '数据表格',
    accept: '.xlsx',
    iconImg: excelIcon,
    color: 'text-green-600',
    activeBg: 'bg-green-50 dark:bg-green-500/10',
    activeBorder: 'border-green-200 dark:border-green-500/30',
  },
  {
    id: 'txt',
    label: 'TXT',
    hint: '纯文本',
    accept: '.txt',
    iconImg: txtIcon,
    color: 'text-slate-600',
    activeBg: 'bg-slate-100 dark:bg-slate-500/10',
    activeBorder: 'border-slate-200 dark:border-slate-500/30',
  },
  {
    id: 'md',
    label: 'MD',
    hint: 'Markdown',
    accept: '.md',
    iconImg: mdIcon,
    color: 'text-cyan-600',
    activeBg: 'bg-cyan-50 dark:bg-cyan-500/10',
    activeBorder: 'border-cyan-200 dark:border-cyan-500/30',
  },
];

export const MobileDeepReadPage: React.FC = () => {
  const [documents, setDocuments] = useState<ExtractionDocument[]>([]);
  const [activeDocHash, setActiveDocHash] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [artifactOpen, setArtifactOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [stickySearchProgress, setStickySearchProgress] = useState(0);
  const [activeUploadShortcut, setActiveUploadShortcut] = useState<QuickUploadShortcutId>('all');
  const [activeTab, setActiveTab] = useState<ArtifactTab>('fields');
  const [traceHits, setTraceHits] = useState<TraceHit[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState('');
  const [apiBaseHint, setApiBaseHint] = useState(() => resolveExtractBase(''));
  const [downloadMessage, setDownloadMessage] = useState('');
  const [uploadMessage, setUploadMessage] = useState('');
  const [toastMessage, setToastMessage] = useState('');
  const [pendingRemoveDoc, setPendingRemoveDoc] = useState<ExtractionDocument | null>(null);
  const [uploadQueue, setUploadQueue] = useState<UploadQueueItem[]>([]);
  const [expandedTableKeys, setExpandedTableKeys] = useState<string[]>([]);
  const [traceRefreshNonce, setTraceRefreshNonce] = useState(0);
  const hasSanitizedInitialDocumentsRef = useRef(false);
  const quickUploadInputRef = useRef<HTMLInputElement>(null);
  const heroSearchInputRef = useRef<HTMLInputElement>(null);
  const stickySearchInputRef = useRef<HTMLInputElement>(null);
  const heroSearchAnchorRef = useRef<HTMLDivElement>(null);
  const stickySearchShellRef = useRef<HTMLDivElement>(null);
  const heroSearchInitialTopRef = useRef<number | null>(null);
  const cancelledUploadIdsRef = useRef<Set<string>>(new Set());
  const uploadQueueRef = useRef<UploadQueueItem[]>([]);
  const documentsRef = useRef<ExtractionDocument[]>([]);
  const sourceFilesByHashRef = useRef<Record<string, File>>({});
  const [sourceFilesByHash, setSourceFilesByHash] = useState<Record<string, File>>({});

  useEffect(() => {
    const sync = () => {
      const docs = readExtractionDocuments();
      if (!hasSanitizedInitialDocumentsRef.current) {
        hasSanitizedInitialDocumentsRef.current = true;
        const safeDocs = filterAutoRestorableExtractionDocuments(docs);
        if (safeDocs.length !== docs.length) {
          writeExtractionDocuments(safeDocs);
        }
        setDocuments(safeDocs);
        return;
      }
      setDocuments(docs);
    };
    sync();
    return subscribeExtractionUpdates(sync);
  }, []);

  useEffect(() => {
    documentsRef.current = documents;
  }, [documents]);

  useEffect(() => {
    sourceFilesByHashRef.current = sourceFilesByHash;
  }, [sourceFilesByHash]);

  useEffect(() => {
    uploadQueueRef.current = uploadQueue;
  }, [uploadQueue]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    let frameId = 0;
    const viewport = window.visualViewport;

    const measureStickySearchProgress = () => {
      frameId = 0;
      const anchor = heroSearchAnchorRef.current;
      const stickyShell = stickySearchShellRef.current;
      if (!anchor || !stickyShell) {
        setStickySearchProgress(0);
        return;
      }

      const anchorRect = anchor.getBoundingClientRect();
      const stickyRect = stickyShell.getBoundingClientRect();

      if (window.scrollY <= 4 || heroSearchInitialTopRef.current == null) {
        heroSearchInitialTopRef.current = anchorRect.top;
      }

      const initialTop = heroSearchInitialTopRef.current ?? anchorRect.top;
      const targetTop = stickyRect.top + 8;
      const travelDistance = Math.max(78, initialTop - targetTop);
      const nextProgress = clamp01((initialTop - anchorRect.top) / travelDistance);

      setStickySearchProgress((previous) =>
        Math.abs(previous - nextProgress) < 0.01 ? previous : nextProgress,
      );
    };

    const scheduleMeasure = () => {
      if (frameId !== 0) return;
      frameId = window.requestAnimationFrame(measureStickySearchProgress);
    };

    scheduleMeasure();
    window.addEventListener('scroll', scheduleMeasure, { passive: true });
    window.addEventListener('resize', scheduleMeasure);
    viewport?.addEventListener('resize', scheduleMeasure);
    viewport?.addEventListener('scroll', scheduleMeasure);

    return () => {
      window.removeEventListener('scroll', scheduleMeasure);
      window.removeEventListener('resize', scheduleMeasure);
      viewport?.removeEventListener('resize', scheduleMeasure);
      viewport?.removeEventListener('scroll', scheduleMeasure);
      if (frameId !== 0) {
        window.cancelAnimationFrame(frameId);
      }
    };
  }, []);

  useEffect(() => {
    if (stickySearchProgress < 0.68) return;
    if (typeof document === 'undefined') return;
    if (document.activeElement === heroSearchInputRef.current) {
      heroSearchInputRef.current?.blur();
    }
  }, [stickySearchProgress]);

  useEffect(() => {
    const message = String(uploadMessage || '').trim();
    if (!message) return undefined;
    setToastMessage(message);
    const timer = window.setTimeout(() => {
      setToastMessage('');
    }, 2200);
    return () => window.clearTimeout(timer);
  }, [uploadMessage]);

  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      const fileName = (doc.file_name || '').toLowerCase();
      const query = searchQuery.trim().toLowerCase();
      return !query || fileName.includes(query);
    });
  }, [documents, searchQuery]);

  const handleQuickUploadShortcut = (shortcut: QuickUploadShortcut) => {
    setActiveUploadShortcut(shortcut.id);
    const input = quickUploadInputRef.current;
    if (!input) return;
    input.value = '';
    input.accept = shortcut.accept;
    input.click();
  };

  const updateUploadQueueItem = (
    itemId: string,
    updater: (current: UploadQueueItem) => UploadQueueItem,
  ) => {
    setUploadQueue((previous) =>
      previous.map((item) => (item.id === itemId ? updater(item) : item)),
    );
  };

  const removeUploadQueueItem = (itemId: string) => {
    cancelledUploadIdsRef.current.delete(itemId);
    setUploadQueue((previous) => {
      const nextQueue = previous.filter((item) => item.id !== itemId);
      setActiveDocHash((currentHash) => {
        const activeQueueItemId = getQueuePreviewItemId(currentHash);
        if (!activeQueueItemId || activeQueueItemId !== itemId) return currentHash;
        if (nextQueue.length > 0) return toQueuePreviewHash(nextQueue[0].id);
        return documentsRef.current[0]?.file_hash || '';
      });
      return nextQueue;
    });
  };

  const clearFinishedUploadQueue = () => {
    setUploadQueue((previous) => {
      const nextQueue = previous.filter((item) => item.status === 'queued' || item.status === 'running');
      setActiveDocHash((currentHash) => {
        const activeQueueItemId = getQueuePreviewItemId(currentHash);
        if (!activeQueueItemId) return currentHash;
        const stillExists = nextQueue.some((item) => item.id === activeQueueItemId);
        if (stillExists) return currentHash;
        if (nextQueue.length > 0) return toQueuePreviewHash(nextQueue[0].id);
        return documentsRef.current[0]?.file_hash || '';
      });
      return nextQueue;
    });
  };

  const enqueueFilesForConfirmation = (files: File[]) => {
    const supported = files.filter((file) =>
      SUPPORTED_UPLOAD_EXTENSIONS.has(getFileExtension(file.name)),
    );
    if (supported.length === 0) {
      setUploadMessage('仅支持 PDF / Word / Excel / TXT / MD 文件');
      return;
    }
    const queuedItems: UploadQueueItem[] = supported.map((file) => ({
      id: `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      file,
      status: 'queued',
      message: '等待确认，点击开始解析',
    }));
    setUploadQueue((previous) => [...queuedItems, ...previous]);
    if (queuedItems.length > 0) {
      setActiveDocHash(toQueuePreviewHash(queuedItems[0].id));
    }
    setUploadMessage(`已加入 ${queuedItems.length} 个文件，请逐个点击“开始解析”`);
  };

  const pollExtractionJobTerminal = async (
    jobId: string,
    preferredBase: string,
    itemId: string,
  ): Promise<{
    status: string;
    errors: string[];
    documents: ExtractionDocument[];
    files: ExtractionJobFilePayload[];
    usedBase: string;
  }> => {
    let usedBase = preferredBase;
    const startedAt = Date.now();
    while (Date.now() - startedAt <= POLL_TIMEOUT_MS) {
      if (cancelledUploadIdsRef.current.has(itemId)) {
        throw new Error('upload_item_cancelled');
      }
      const statusResult = await requestExtractionJobStatus(jobId, usedBase, true);
      if (statusResult.usedBase) {
        usedBase = statusResult.usedBase;
        setApiBaseHint(statusResult.usedBase);
      }
      if (!statusResult.response.ok) {
        throw new Error(await parseErrorMessage(statusResult.response));
      }
      const payload = (await statusResult.response.json()) as {
        status?: string;
        terminal?: boolean;
        errors?: string[];
        documents?: ExtractionDocument[];
        files?: ExtractionJobFilePayload[];
      };
      const status = String(payload.status || '').trim();
      const errors = Array.isArray(payload.errors)
        ? payload.errors.map((item) => String(item || '').trim()).filter(Boolean)
        : [];
      const documents = filterAutoRestorableExtractionDocuments(
        Array.isArray(payload.documents) ? payload.documents : [],
      );
      const files = normalizeExtractionJobFiles(payload.files);
      const terminal = Boolean(payload.terminal)
        || ['completed', 'failed', 'cached', 'cancelled'].includes(status.toLowerCase());
      if (terminal) {
        return {
          status,
          errors,
          documents,
          files,
          usedBase,
        };
      }
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, POLL_INTERVAL_MS);
      });
    }
    throw new Error('job_terminal_timeout');
  };

  const startSingleUpload = async (itemId: string) => {
    const current = uploadQueueRef.current.find((item) => item.id === itemId);
    if (!current || current.status === 'running') return;

    cancelledUploadIdsRef.current.delete(itemId);
    updateUploadQueueItem(itemId, (item) => ({
      ...item,
      status: 'running',
      message: '正在创建解析任务',
    }));
    setUploadMessage(`正在解析 ${current.file.name}...`);
    setDownloadMessage('');
    setTraceError('');

    try {
      const createResult = await requestExtractionJobCreateWithRetry(
        [current.file],
        QUICK_UPLOAD_SCHEMA,
        2,
        apiBaseHint,
      );
      if (createResult.usedBase) {
        setApiBaseHint(createResult.usedBase);
      }
      if (!createResult.response.ok) {
        throw new Error(await parseErrorMessage(createResult.response));
      }

      const createPayload = (await createResult.response.json()) as {
        job_id?: string;
        status?: string;
        terminal?: boolean;
        errors?: string[];
        documents?: ExtractionDocument[];
        files?: ExtractionJobFilePayload[];
      };
      const jobId = String(createPayload.job_id || '').trim();
      if (!jobId) {
        throw new Error('create_payload_missing_job_id');
      }

      updateUploadQueueItem(itemId, (item) => ({
        ...item,
        jobId,
        status: 'running',
        message: '任务已创建，正在等待完成',
      }));

      let parsedDocuments = filterAutoRestorableExtractionDocuments(
        Array.isArray(createPayload.documents) ? createPayload.documents : [],
      );
      let parsedJobFiles = normalizeExtractionJobFiles(createPayload.files);
      if (parsedDocuments.length === 0) {
        const terminalState = await pollExtractionJobTerminal(
          jobId,
          createResult.usedBase || apiBaseHint,
          itemId,
        );
        if (terminalState.status.toLowerCase() !== 'completed' && terminalState.errors.length > 0) {
          throw new Error(terminalState.errors[0]);
        }
        parsedDocuments = terminalState.documents;
        if (terminalState.files.length > 0) {
          parsedJobFiles = terminalState.files;
        }
      }
      if (parsedDocuments.length === 0) {
        throw new Error('未返回可用解析结果');
      }

      const parsedDocumentsWithSource = parsedDocuments.map((document) =>
        attachSourceArtifactDiagnostics(
          document,
          findJobFileForDocument(document, parsedJobFiles),
        ),
      );
      const nextDocuments = mergeDocuments(documentsRef.current, parsedDocumentsWithSource);
      setDocuments(nextDocuments);
      writeExtractionDocuments(nextDocuments);
      documentsRef.current = nextDocuments;

      const matchedDoc = parsedDocumentsWithSource.find(
        (doc) => normalizeFileName(doc.file_name) === normalizeFileName(current.file.name),
      ) || parsedDocumentsWithSource[0];

      setSourceFilesByHash((previous) => {
        const next = { ...previous };
        if (matchedDoc?.file_hash) {
          next[matchedDoc.file_hash] = current.file;
        } else {
          parsedDocumentsWithSource.forEach((doc) => {
            if (normalizeFileName(doc.file_name) === normalizeFileName(current.file.name)) {
              next[doc.file_hash] = current.file;
            }
          });
        }
        sourceFilesByHashRef.current = next;
        return next;
      });
      if (matchedDoc?.file_hash) {
        setActiveDocHash(matchedDoc.file_hash);
      }

      updateUploadQueueItem(itemId, (item) => ({
        ...item,
        status: 'completed',
        fileHash: String(matchedDoc?.file_hash || '').trim(),
        resolvedFileName: String(matchedDoc?.file_name || item.file.name).trim(),
        message: '解析完成',
      }));
      setUploadMessage(`解析完成：${current.file.name}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '文件解析失败，请稍后重试';
      if (message === 'upload_item_cancelled') {
        updateUploadQueueItem(itemId, (item) => ({
          ...item,
          status: 'cancelled',
          message: '解析已取消',
        }));
        setUploadMessage(`已取消：${current.file.name}`);
        return;
      }
      updateUploadQueueItem(itemId, (item) => ({
        ...item,
        status: 'failed',
        message,
      }));
      setUploadMessage(`解析失败：${current.file.name}`);
    }
  };

  const cancelSingleUpload = async (itemId: string) => {
    const current = uploadQueueRef.current.find((item) => item.id === itemId);
    if (!current) return;
    cancelledUploadIdsRef.current.add(itemId);

    if (current.status === 'queued') {
      updateUploadQueueItem(itemId, (item) => ({
        ...item,
        status: 'cancelled',
        message: '已取消（未开始）',
      }));
      setUploadMessage(`已取消：${current.file.name}`);
      return;
    }
    if (current.status !== 'running') return;

    updateUploadQueueItem(itemId, (item) => ({
      ...item,
      status: 'cancelled',
      message: '正在取消...',
    }));

    if (current.jobId) {
      try {
        const cancelResult = await requestExtractionJobCancelFile(
          current.jobId,
          String(current.fileHash || '').trim(),
          String(current.resolvedFileName || current.file.name).trim(),
          apiBaseHint,
        );
        if (cancelResult.usedBase) {
          setApiBaseHint(cancelResult.usedBase);
        }
      } catch {
        // keep local cancelled state
      }
    }

    updateUploadQueueItem(itemId, (item) => ({
      ...item,
      status: 'cancelled',
      message: '解析已取消',
    }));
    setUploadMessage(`已取消：${current.file.name}`);
  };

  const isQueueItemMatchedToDocument = (
    item: UploadQueueItem,
    document: ExtractionDocument,
  ): boolean => {
    const docHash = String(document.file_hash || '').trim();
    const itemHash = String(item.fileHash || '').trim();
    if (docHash && itemHash && docHash === itemHash) return true;
    const docName = normalizeFileName(document.file_name);
    const itemName = normalizeFileName(item.resolvedFileName || item.file.name);
    return Boolean(docName) && docName === itemName;
  };

  const removeDocument = async (document: ExtractionDocument) => {
    const fileName = String(document.file_name || '').trim() || '当前文档';
    const shouldRemove = typeof window === 'undefined'
      ? true
      : true;
    if (!shouldRemove) return;

    const relatedRunningQueueItems = uploadQueueRef.current.filter(
      (item) => isQueueItemMatchedToDocument(item, document) && item.status === 'running',
    );
    for (const queueItem of relatedRunningQueueItems) {
      await cancelSingleUpload(queueItem.id);
    }

    setUploadQueue((previous) =>
      previous.filter((item) => !isQueueItemMatchedToDocument(item, document)),
    );

    const targetHash = String(document.file_hash || '').trim();
    const targetName = normalizeFileName(document.file_name);
    const nextDocuments = documentsRef.current.filter((item) => {
      const sameHash = targetHash && String(item.file_hash || '').trim() === targetHash;
      if (sameHash) return false;
      if (!targetHash) {
        return normalizeFileName(item.file_name) !== targetName;
      }
      return true;
    });
    setDocuments(nextDocuments);
    writeExtractionDocuments(nextDocuments);
    documentsRef.current = nextDocuments;

    setSourceFilesByHash((previous) => {
      if (!targetHash) return previous;
      if (!(targetHash in previous)) return previous;
      const next = { ...previous };
      delete next[targetHash];
      sourceFilesByHashRef.current = next;
      return next;
    });

    if (targetHash && activeDocHash === targetHash) {
      setActiveDocHash(nextDocuments[0]?.file_hash || '');
    }
    setUploadMessage(`已移除：${fileName}`);
  };

  const performDocumentRemoval = async (document: ExtractionDocument) => {
    const fileName = String(document.file_name || '').trim() || '当前文档';

    const relatedRunningQueueItems = uploadQueueRef.current.filter(
      (item) => isQueueItemMatchedToDocument(item, document) && item.status === 'running',
    );
    for (const queueItem of relatedRunningQueueItems) {
      await cancelSingleUpload(queueItem.id);
    }

    setUploadQueue((previous) =>
      previous.filter((item) => !isQueueItemMatchedToDocument(item, document)),
    );

    const targetHash = String(document.file_hash || '').trim();
    const targetName = normalizeFileName(document.file_name);
    const nextDocuments = documentsRef.current.filter((item) => {
      const sameHash = targetHash && String(item.file_hash || '').trim() === targetHash;
      if (sameHash) return false;
      if (!targetHash) {
        return normalizeFileName(item.file_name) !== targetName;
      }
      return true;
    });
    setDocuments(nextDocuments);
    writeExtractionDocuments(nextDocuments);
    documentsRef.current = nextDocuments;

    setSourceFilesByHash((previous) => {
      if (!targetHash) return previous;
      if (!(targetHash in previous)) return previous;
      const next = { ...previous };
      delete next[targetHash];
      sourceFilesByHashRef.current = next;
      return next;
    });

    if (targetHash && activeDocHash === targetHash) {
      setActiveDocHash(nextDocuments[0]?.file_hash || '');
    }
    setUploadMessage(`已移除：${fileName}`);
  };

  const requestRemoveDocument = (document: ExtractionDocument) => {
    setPendingRemoveDoc(document);
  };

  const confirmRemoveDocument = async () => {
    const target = pendingRemoveDoc;
    if (!target) return;
    setPendingRemoveDoc(null);
    await performDocumentRemoval(target);
  };

  const cancelRemoveDocument = () => {
    setPendingRemoveDoc(null);
  };

  const reparseDocument = async (document: ExtractionDocument) => {
    const sourceFile = sourceFilesByHashRef.current[String(document.file_hash || '').trim()];
    if (!sourceFile) {
      setUploadMessage(`无法重解析 ${document.file_name}：缺少本地源文件，请重新上传`);
      return;
    }
    const queueId = `reparse-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const queuedItem: UploadQueueItem = {
      id: queueId,
      file: sourceFile,
      status: 'queued',
      message: '等待重新解析',
      fileHash: String(document.file_hash || '').trim(),
      resolvedFileName: String(document.file_name || sourceFile.name).trim(),
    };
    setUploadQueue((previous) => [queuedItem, ...previous]);
    setActiveDocHash(toQueuePreviewHash(queueId));
    setUploadMessage(`开始重新解析：${document.file_name}`);
    await startSingleUpload(queueId);
  };

  const handleQuickUploadChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []) as File[];
    event.target.value = '';
    if (files.length === 0) return;
    enqueueFilesForConfirmation(files);
  };

  useEffect(() => {
    const activeQueueItemId = getQueuePreviewItemId(activeDocHash);
    if (activeQueueItemId) {
      const queueExists = uploadQueue.some((item) => item.id === activeQueueItemId);
      if (queueExists) return;
    }

    if (filteredDocuments.length === 0) {
      if (documents.length === 0) {
        if (uploadQueue.length > 0) {
          setActiveDocHash(toQueuePreviewHash(uploadQueue[0].id));
        } else {
          setActiveDocHash('');
        }
      }
      return;
    }
    const exists = filteredDocuments.some((doc) => doc.file_hash === activeDocHash);
    if (!exists) {
      setActiveDocHash(filteredDocuments[0].file_hash);
    }
  }, [filteredDocuments, documents.length, activeDocHash, uploadQueue]);

  const activeDoc = useMemo(
    () => documents.find((doc) => doc.file_hash === activeDocHash) ?? null,
    [documents, activeDocHash],
  );
  const activeQueuePreviewItem = useMemo(() => {
    const queueItemId = getQueuePreviewItemId(activeDocHash);
    if (!queueItemId) return null;
    return uploadQueue.find((item) => item.id === queueItemId) ?? null;
  }, [activeDocHash, uploadQueue]);
  const previewDoc = useMemo<ExtractionDocument | null>(() => {
    if (activeDoc) return activeDoc;
    if (!activeQueuePreviewItem) return null;
    const queueFileName = String(
      activeQueuePreviewItem.resolvedFileName || activeQueuePreviewItem.file?.name || '',
    ).trim();
    const previewFileName = queueFileName || 'untitled';
    return {
      file_name: previewFileName,
      file_hash: toQueuePreviewHash(activeQueuePreviewItem.id),
      track: 'upload_queue',
      cached: true,
      result: {},
      errors: [],
      soft_warnings: [],
      diagnostics: {
        queue_item_id: activeQueuePreviewItem.id,
        queue_status: activeQueuePreviewItem.status,
        queue_message: activeQueuePreviewItem.message,
        source_file_name: previewFileName,
        source_file_size: Number(activeQueuePreviewItem.file?.size || 0),
        source_file_type: String(activeQueuePreviewItem.file?.type || ''),
      },
    };
  }, [activeDoc, activeQueuePreviewItem]);
  const activeDocIndex = useMemo(
    () => documents.findIndex((doc) => doc.file_hash === activeDocHash),
    [documents, activeDocHash],
  );
  const activeSourceFile = useMemo(
    () => (activeDoc
      ? sourceFilesByHash[activeDoc.file_hash] || null
      : activeQueuePreviewItem?.file || null),
    [activeDoc, activeQueuePreviewItem, sourceFilesByHash],
  );

  useEffect(() => {
    if (previewOpen && !previewDoc) {
      setPreviewOpen(false);
    }
  }, [previewDoc, previewOpen]);

  useEffect(() => {
    if (artifactOpen && !activeDoc) {
      setArtifactOpen(false);
    }
  }, [activeDoc, artifactOpen]);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const shouldLockPage = previewOpen || artifactOpen;
    const previousOverflow = document.body.style.overflow;
    if (shouldLockPage) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [artifactOpen, previewOpen]);

  const fieldEntries = useMemo(() => {
    if (!activeDoc) return [];
    return Object.entries(activeDoc.result || {})
      .map(([fieldName, entity]) => ({
        fieldName,
        value: toDisplayValue(entity?.value),
      }))
      .filter((item) => item.value.length > 0);
  }, [activeDoc]);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      if (!activeDoc) {
        setTraceHits([]);
        setTraceError('');
        setTraceLoading(false);
        return;
      }
      setTraceLoading(true);
      setTraceError('');
      setExpandedTableKeys([]);
      setDownloadMessage('');
      try {
        const result = await requestTraceLocate(
          {
            document: activeDoc,
            top_k: 80,
          },
          apiBaseHint,
        );
        if (!alive) return;
        const { response, usedBase } = result;
        if (usedBase) setApiBaseHint(usedBase);
        if (!response.ok) {
          throw new Error(await parseErrorMessage(response));
        }
        const payload = (await response.json()) as { hits?: TraceHit[] };
        const hits = Array.isArray(payload.hits) ? payload.hits : [];
        setTraceHits(hits.length > 0 ? hits : Array.isArray(activeDoc.trace_hits) ? activeDoc.trace_hits : []);
      } catch (error) {
        if (!alive) return;
        setTraceHits(Array.isArray(activeDoc.trace_hits) ? activeDoc.trace_hits : []);
        setTraceError(error instanceof Error ? error.message : '产物定位失败');
      } finally {
        if (alive) setTraceLoading(false);
      }
    };
    void run();
    return () => {
      alive = false;
    };
  }, [activeDoc, apiBaseHint, traceRefreshNonce]);

  const tableItems = useMemo(
    () =>
      traceHits
        .map((hit, index) => ({ hit, index }))
        .filter(({ hit }) => getTraceKind(hit) === 'table')
        .map(({ hit, index }) => {
          const locator = getHitLocator(hit);
          const dataframe = pickBestDataframe(locator.dataframe, locator.table_preview, locator.dataframe_json);
          return {
            key: `${hit.ref_id || hit.object_id || 'table'}-${index}`,
            title: String(locator.title || hit.object_id || `表格 ${index + 1}`).trim(),
            summary: String(locator.summary || hit.snippet || '').trim(),
            artifactUrl: resolveExtractArtifactUrlFromTraceHit(hit, apiBaseHint),
            tableDownloadUrl: resolveExtractTableDownloadUrlFromTraceHit(hit, apiBaseHint),
            dataframe,
            page: Number(hit.page || locator.page || 0),
          };
        }),
    [traceHits, apiBaseHint],
  );

  const imageItems = useMemo(
    () =>
      traceHits
        .map((hit, index) => ({ hit, index }))
        .filter(({ hit }) => getTraceKind(hit) === 'image')
        .map(({ hit, index }) => {
          const locator = getHitLocator(hit);
          return {
            key: `${hit.ref_id || hit.object_id || 'image'}-${index}`,
            title: String(locator.title || hit.object_id || `图片 ${index + 1}`).trim(),
            caption: toImageCaption(hit),
            artifactUrl: resolveExtractArtifactUrlFromTraceHit(hit, apiBaseHint),
            page: Number(hit.page || locator.page || 0),
          };
        }),
    [traceHits, apiBaseHint],
  );

  const chartItems = useMemo(
    () =>
      traceHits
        .map((hit, index) => ({ hit, index }))
        .filter(({ hit }) => getTraceKind(hit) === 'chart')
        .map(({ hit, index }) => {
          const locator = getHitLocator(hit);
          const chartSpec = getTraceChartSpec(locator.chart_spec);
          const yFieldLabels = Array.isArray(chartSpec?.y_fields)
            ? chartSpec.y_fields.map((item) => String(item || '').trim()).filter(Boolean)
            : [];
          const xAxisLabel = String(chartSpec?.x_axis_label || chartSpec?.x_field || '').trim();
          const yAxisLabel = String(chartSpec?.y_axis_label || yFieldLabels.join(' / ')).trim();
          return {
            key: `${hit.ref_id || hit.object_id || 'chart'}-${index}`,
            title: getTraceChartTitle(chartSpec, String(hit.object_id || `图表 ${index + 1}`).trim()),
            summary: getTraceChartSummary(chartSpec),
            chartSpec,
            pointCount: getTraceChartPointCount(chartSpec),
            page: Number(hit.page || locator.page || 0),
            xAxisLabel,
            yAxisLabel,
          };
        }),
    [traceHits],
  );

  const handleDownloadRemote = async (url: string, filename: string) => {
    if (!url) return;
    setDownloadMessage('');
    try {
      const response = await fetch(url, { credentials: 'include' });
      if (!response.ok) {
        throw new Error(await parseErrorMessage(response));
      }
      const blob = await response.blob();
      triggerBlobDownload(blob, filename);
    } catch (error) {
      setDownloadMessage(error instanceof Error ? error.message : '下载失败，请稍后重试');
    }
  };

  const openQueuePreview = (itemId: string) => {
    setActiveDocHash(toQueuePreviewHash(itemId));
    setArtifactOpen(false);
    setPreviewOpen(true);
  };

  const openDocumentPreview = (document: ExtractionDocument) => {
    setActiveDocHash(String(document.file_hash || '').trim());
    setArtifactOpen(false);
    setPreviewOpen(true);
  };

  const openDocumentArtifacts = (document: ExtractionDocument, tab: ArtifactTab = 'fields') => {
    setActiveDocHash(String(document.file_hash || '').trim());
    setActiveTab(tab);
    setPreviewOpen(false);
    setArtifactOpen(true);
  };

  const handleAssistantCitationSelect = (citation: AssistantCitation) => {
    const figureType = String((citation.payload as Record<string, unknown> | undefined)?.figure_type || '')
      .trim()
      .toLowerCase();
    if (citation.citation_type === 'table') {
      setActiveTab('tables');
    } else if (citation.citation_type === 'figure' && figureType === 'chart') {
      setActiveTab('charts');
    } else if (citation.citation_type === 'figure') {
      setActiveTab('images');
    } else {
      setActiveTab('fields');
    }
    if (activeDoc) {
      setPreviewOpen(false);
      setArtifactOpen(true);
    }
    setAssistantOpen(false);
  };

  const renderArtifactDetailPanel = () => {
    if (!activeDoc) return null;

    const baseName = toFileBaseName(activeDoc.file_name || 'document');
    const tabDefs = [
      { id: 'fields' as const, label: '字段', icon: LayoutList },
      { id: 'tables' as const, label: '表格', icon: Table2 },
      { id: 'charts' as const, label: '图表', icon: BarChart3 },
      { id: 'images' as const, label: '图片', icon: ImageIcon },
    ];

    return (
      <section id="mobile-artifact-detail" className="flex flex-col min-h-full">
        <div className="flex-1 rounded-[24px] bg-white p-3 shadow-[0_8px_32px_rgba(0,0,0,0.03)] dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <div className="sticky top-0 z-10 -mx-1 mb-4 flex items-center gap-2 bg-white/95 py-1 backdrop-blur-md dark:bg-slate-800/95">
            <div className="flex flex-1 gap-1.5 rounded-[14px] bg-slate-50/80 p-1 ring-1 ring-slate-100/50 dark:bg-slate-900/50 dark:ring-slate-700/50">
              {tabDefs.map((tab) => {
                const Icon = tab.icon;
                const active = tab.id === activeTab;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={cn(
                      'flex flex-1 items-center justify-center gap-1.5 rounded-[12px] py-2 text-[13px] font-semibold transition-all',
                      active
                        ? 'bg-white text-slate-800 shadow-[0_2px_10px_rgba(0,0,0,0.04)] dark:bg-slate-700 dark:text-white'
                        : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200',
                    )}
                  >
                    <Icon size={15} strokeWidth={active ? 2.5 : 2} />
                    {tab.label}
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => setTraceRefreshNonce((prev) => prev + 1)}
              disabled={traceLoading}
              className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[14px] bg-slate-50/80 text-slate-500 ring-1 ring-slate-100/50 transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-900/50 dark:text-slate-400 dark:ring-slate-700/50"
              aria-label="刷新产物"
            >
              {traceLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCcw size={16} />}
            </button>
          </div>

          {traceError && (
            <div className="mb-4 flex items-center gap-2 rounded-[16px] bg-rose-50 px-4 py-3 text-[14px] text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">
              <AlertTriangle size={18} strokeWidth={2.5} className="shrink-0" />
              {traceError}
            </div>
          )}
          {downloadMessage && (
            <div className="mb-4 flex items-center gap-2 rounded-[16px] bg-rose-50 px-4 py-3 text-[14px] text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">
              <AlertTriangle size={18} strokeWidth={2.5} className="shrink-0" />
              {downloadMessage}
            </div>
          )}

          {activeTab === 'fields' && (
            <div className="space-y-2">
              {fieldEntries.length === 0 ? (
                <div className="py-14 text-center text-[13px] text-slate-500 dark:text-slate-400">暂无字段产物</div>
              ) : (
                fieldEntries.map((item) => (
                  <article key={item.fieldName} className="rounded-[16px] border border-slate-100 bg-white px-3.5 py-2.5 shadow-[0_2px_8px_rgba(0,0,0,0.02)] dark:border-slate-700/40 dark:bg-slate-800/40">
                    <p className="text-[12px] font-medium text-slate-500 dark:text-slate-400">{item.fieldName}</p>
                    <p className="mt-0.5 whitespace-pre-wrap break-words text-[14px] font-semibold text-slate-900 dark:text-slate-100">{item.value}</p>
                  </article>
                ))
              )}
            </div>
          )}

          {activeTab === 'tables' && (
            <div className="space-y-3">
              {tableItems.length === 0 ? (
                <div className="py-14 text-center text-[13px] text-slate-500 dark:text-slate-400">暂无表格产物</div>
              ) : (
                tableItems.map((item) => {
                  const expanded = expandedTableKeys.includes(item.key);
                  const previewRows = expanded ? item.dataframe.rows : item.dataframe.rows.slice(0, 8);
                  const hasDataframe = item.dataframe.headers.length > 0 || item.dataframe.rows.length > 0;
                  return (
                    <article key={item.key} className="overflow-hidden rounded-[16px] border border-slate-100 bg-white shadow-[0_2px_8px_rgba(0,0,0,0.02)] dark:border-slate-700/40 dark:bg-slate-800/40">
                      <div className="p-3.5">
                        <div className="mb-2 flex items-start justify-between gap-3">
                          <div className="flex-1">
                            <p className="text-[14px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '表格'}</p>
                            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[12px] text-slate-500 dark:text-slate-400">
                              <span>{item.dataframe.rowCount} 行 / {item.dataframe.colCount} 列</span>
                              {item.page > 0 && (
                                <span className="inline-flex items-center rounded-md border border-slate-200/60 bg-slate-100/80 px-2 py-0.5 text-[11px] font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                                  第 {item.page} 页
                                </span>
                              )}
                            </div>
                          </div>
                          {item.tableDownloadUrl && (
                            <button
                              type="button"
                              onClick={() => handleDownloadRemote(item.tableDownloadUrl, `${baseName}-${item.title || 'table'}.csv`)}
                              className="inline-flex h-7 items-center gap-1 rounded-full border border-emerald-100 bg-emerald-50 px-3 text-[12px] font-semibold text-emerald-600 transition active:scale-95 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400"
                            >
                              <Download size={12} />
                              下载
                            </button>
                          )}
                        </div>

                        {item.summary && (
                          <p className="mb-2 text-[12px] leading-relaxed text-slate-500 dark:text-slate-400">
                            {item.summary}
                          </p>
                        )}

                        <div className="mb-2 flex flex-wrap gap-2">
                          {!item.tableDownloadUrl && (
                            <button
                              type="button"
                              onClick={() => downloadDataframeAsCsv(item.dataframe, `${baseName}-${item.title || 'table'}.csv`)}
                              disabled={!hasDataframe}
                              className="inline-flex h-7 items-center gap-1 rounded-full border border-emerald-100 bg-emerald-50 px-3 text-[12px] font-semibold text-emerald-600 transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400"
                            >
                              <Download size={12} />
                              下载CSV
                            </button>
                          )}
                          {item.artifactUrl && (
                            <button
                              type="button"
                              onClick={() => handleDownloadRemote(item.artifactUrl, `${baseName}-${item.title || 'table'}-screenshot.png`)}
                              className="inline-flex h-7 items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-3 text-[12px] font-semibold text-slate-600 transition active:scale-95 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300"
                            >
                              <ImageIcon size={12} />
                              图像
                            </button>
                          )}
                        </div>

                        {hasDataframe && (
                          <div className="overflow-hidden rounded-[12px] border border-slate-200/70 bg-slate-50/50 dark:border-slate-700/60 dark:bg-slate-900/30">
                            <div className="overflow-x-auto">
                              <table className="min-w-full text-[12px]">
                                {item.dataframe.headers.length > 0 && (
                                  <thead>
                                    <tr className="bg-slate-100/60 dark:bg-slate-800/60">
                                      {item.dataframe.headers.map((header, idx) => (
                                        <th
                                          key={`${item.key}-header-${idx}`}
                                          className="whitespace-nowrap border-b border-slate-200/60 px-3 py-2 text-left font-semibold text-slate-700 dark:border-slate-700/60 dark:text-slate-200"
                                        >
                                          {header || `列 ${idx + 1}`}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                )}
                                <tbody>
                                  {previewRows.map((row, rowIdx) => (
                                    <tr
                                      key={`${item.key}-row-${rowIdx}`}
                                      className="border-b border-slate-100/60 last:border-0 dark:border-slate-800/60"
                                    >
                                      {row.map((cell, cellIdx) => (
                                        <td
                                          key={`${item.key}-cell-${rowIdx}-${cellIdx}`}
                                          className="whitespace-nowrap px-3 py-2 text-slate-600 dark:text-slate-300"
                                        >
                                          {cell}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            <div className="flex items-center justify-between border-t border-slate-200/60 bg-slate-100/40 px-3 py-2 text-[11px] text-slate-500 dark:border-slate-700/60 dark:bg-slate-800/40 dark:text-slate-400">
                              <span>DataFrame: {item.dataframe.rowCount} x {item.dataframe.colCount}</span>
                              {item.dataframe.rows.length > 8 && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setExpandedTableKeys((prev) =>
                                      prev.includes(item.key)
                                        ? prev.filter((key) => key !== item.key)
                                        : [...prev, item.key],
                                    )
                                  }
                                  className="font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                                >
                                  {expanded ? '收起' : '展开'}
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          )}

          {activeTab === 'charts' && (
            <div className="space-y-3">
              {chartItems.length === 0 ? (
                <div className="py-14 text-center text-[13px] text-slate-500 dark:text-slate-400">暂无图表产物</div>
              ) : (
                chartItems.map((item) => (
                  <article key={item.key} className="overflow-hidden rounded-[16px] border border-slate-100 bg-white shadow-[0_2px_8px_rgba(0,0,0,0.02)] dark:border-slate-700/40 dark:bg-slate-800/40">
                    <div className="p-3.5">
                      <p className="text-[14px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '图表'}</p>
                      {item.summary && <p className="mt-2 text-[12px] leading-relaxed text-slate-500 dark:text-slate-400"><span className="font-medium text-slate-700 dark:text-slate-200">趋势解读：</span>{item.summary}</p>}
                      <div className="mt-2">
                        <TraceChartPreview spec={item.chartSpec} compact />
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>
          )}

          {activeTab === 'images' && (
            <div className="space-y-3">
              {imageItems.length === 0 ? (
                <div className="py-14 text-center text-[13px] text-slate-500 dark:text-slate-400">暂无图片产物</div>
              ) : (
                imageItems.map((item) => (
                  <article key={item.key} className="overflow-hidden rounded-[16px] border border-slate-100 bg-white shadow-[0_2px_8px_rgba(0,0,0,0.02)] dark:border-slate-700/40 dark:bg-slate-800/40">
                    <div className="p-3.5">
                      <div className="mb-2 flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <p className="text-[14px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '图片'}</p>
                          {item.page > 0 && (
                            <span className="mt-1 inline-flex items-center rounded-md border border-slate-200/60 bg-slate-100/80 px-2 py-0.5 text-[11px] font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                              第 {item.page} 页
                            </span>
                          )}
                        </div>
                        {item.artifactUrl && (
                          <button
                            type="button"
                            onClick={() => handleDownloadRemote(item.artifactUrl, `${baseName}-${item.title || 'image'}.png`)}
                            className="inline-flex h-7 items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-3 text-[12px] font-semibold text-slate-600 transition active:scale-95 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300"
                          >
                            <Download size={12} />
                            下载
                          </button>
                        )}
                      </div>
                      {item.caption && (
                        <p className="mb-2 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-slate-500 dark:text-slate-400">
                          {item.caption}
                        </p>
                      )}
                    </div>
                    {item.artifactUrl ? (
                      <div className="border-t border-slate-100 bg-slate-50/50 px-3.5 py-3 dark:border-slate-700/50 dark:bg-slate-900/30">
                        <img
                          src={item.artifactUrl}
                          alt={item.title || 'image-artifact'}
                          className="mx-auto max-h-[260px] w-full rounded-[10px] border border-slate-200/70 object-contain dark:border-slate-700/70"
                          loading="lazy"
                        />
                      </div>
                    ) : (
                      <div className="border-t border-slate-100 bg-slate-50/50 px-3.5 py-8 text-center text-[12px] text-slate-500 dark:border-slate-700/50 dark:bg-slate-900/30 dark:text-slate-400">
                        无可预览图像
                      </div>
                    )}
                  </article>
                ))
              )}
            </div>
          )}
        </div>
      </section>
    );
    /*
    return (
      <section id="mobile-artifact-detail">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="truncate text-[17px] font-bold text-slate-800 dark:text-slate-100">
            {activeDoc ? `${activeDoc.file_name} 路 浜х墿璇︽儏` : '浜х墿璇︽儏'}
          </h3>
          <button
            type="button"
            onClick={() => setTraceRefreshNonce((prev) => prev + 1)}
            disabled={!activeDoc || traceLoading}
            className="inline-flex items-center gap-1.5 rounded-full bg-slate-200/50 px-3 py-1.5 text-[13px] font-medium text-slate-600 transition hover:bg-slate-300/50 hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
          >
            {traceLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
            鍒锋柊
          </button>
        </div>

        <motion.div variants={itemVariants} className="rounded-[26px] bg-white p-4 shadow-[0_8px_32px_rgba(0,0,0,0.03)] dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
          <div className="mb-5 flex gap-1.5 rounded-[14px] bg-slate-50/80 p-1 ring-1 ring-slate-100/50 dark:bg-slate-900/50 dark:ring-slate-700/50">
            {[
              { id: 'fields' as const, label: '瀛楁', icon: LayoutList },
              { id: 'tables' as const, label: '琛ㄦ牸', icon: Table2 },
              { id: 'charts' as const, label: '鍥捐〃', icon: BarChart3 },
              { id: 'images' as const, label: '鍥剧墖', icon: ImageIcon },
            ].map((tab) => {
              const Icon = tab.icon;
              const active = tab.id === activeTab;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex flex-1 items-center justify-center gap-1.5 rounded-[12px] py-2 text-[13px] font-semibold transition-all',
                    active
                      ? 'bg-white text-slate-800 shadow-[0_2px_10px_rgba(0,0,0,0.04)] dark:bg-slate-700 dark:text-white'
                      : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200',
                  )}
                >
                  <Icon size={15} strokeWidth={active ? 2.5 : 2} />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {traceError && (
            <div className="mb-4 flex items-center gap-2 rounded-[16px] bg-rose-50 px-4 py-3 text-[14px] text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">
              <AlertTriangle size={18} strokeWidth={2.5} className="shrink-0" />
              {traceError}
            </div>
          )}
          {downloadMessage && (
            <div className="mb-4 flex items-center gap-2 rounded-[16px] bg-rose-50 px-4 py-3 text-[14px] text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">
              <AlertTriangle size={18} strokeWidth={2.5} className="shrink-0" />
              {downloadMessage}
            </div>
          )}

          {activeTab === 'fields' && (
            <div className="space-y-3">
              {fieldEntries.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-50 text-slate-400 dark:bg-slate-800/80 dark:text-slate-500">
                    <LayoutList size={24} strokeWidth={1.5} />
                  </div>
                  <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">鏆傛棤瀛楁浜х墿</p>
                  <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">璇ユ枃妗ｆ湭瑙ｆ瀽鍑哄瓧娈典俊鎭?/p>
                </div>
              ) : (
                fieldEntries.map((item) => (
                  <article key={item.fieldName} className="rounded-[20px] bg-white border border-slate-100 shadow-[0_2px_10px_rgba(0,0,0,0.02)] px-4 py-4 transition-colors hover:border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/40 dark:hover:border-slate-600">
                    <p className="text-[13px] font-medium text-slate-500 dark:text-slate-400">{item.fieldName}</p>
                    <p className="mt-1 whitespace-pre-wrap break-words text-[15px] font-medium text-slate-800 dark:text-slate-100">
                      {item.value}
                    </p>
                  </article>
                ))
              )}
            </div>
          )}

          {activeTab === 'tables' && (
            <div className="space-y-4">
              {tableItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-50 text-slate-400 dark:bg-slate-800/80 dark:text-slate-500">
                    <Table2 size={24} strokeWidth={1.5} />
                  </div>
                  <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">鏆傛棤琛ㄦ牸浜х墿</p>
                  <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">璇ユ枃妗ｆ湭瑙ｆ瀽鍑鸿〃鏍间俊鎭?/p>
                </div>
              ) : (
                tableItems.map((item) => {
                  const expanded = expandedTableKeys.includes(item.key);
                  const previewRows = expanded ? item.dataframe.rows : item.dataframe.rows.slice(0, 8);
                  const baseName = toFileBaseName(activeDoc?.file_name || 'document');
                  return (
                    <article key={item.key} className="overflow-hidden rounded-[20px] bg-white border border-slate-100 shadow-[0_2px_10px_rgba(0,0,0,0.02)] transition-colors hover:border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/40 dark:hover:border-slate-600">
                      <div className="p-4">
                        <div className="mb-3 flex items-start justify-between gap-3">
                          <div className="flex-1">
                            <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '琛ㄦ牸'}</p>
                            <div className="mt-1 flex items-center gap-2">
                              {item.page > 0 && <span className="rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">绗?{item.page} 椤?/span>}
                            </div>
                          </div>
                          {item.artifactUrl && (
                            <a
                              href={item.artifactUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-50 text-slate-600 shadow-[0_2px_8px_rgba(0,0,0,0.04)] transition-colors hover:bg-slate-100 hover:text-slate-900 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600 dark:hover:text-white"
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                        </div>

                        {item.summary && (
                          <p className="mb-3 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">{item.summary}</p>
                        )}

                        <div className="mb-4 flex flex-wrap gap-2">
                          {item.tableDownloadUrl ? (
                            <button
                              type="button"
                              onClick={() => handleDownloadRemote(item.tableDownloadUrl, `${baseName}-${item.title || 'table'}.csv`)}
                              className="inline-flex w-fit items-center gap-1.5 rounded-[10px] bg-emerald-50/80 border border-emerald-100 px-3 py-1.5 text-[12px] font-semibold text-emerald-600 transition hover:bg-emerald-100/80 hover:border-emerald-200 dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-400 dark:hover:bg-emerald-500/20"
                            >
                              <Download size={14} />
                              涓嬭浇鏁版嵁
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => downloadDataframeAsCsv(item.dataframe, `${baseName}-${item.title || 'table'}.csv`)}
                              disabled={item.dataframe.rows.length === 0 && item.dataframe.headers.length === 0}
                              className="inline-flex w-fit items-center gap-1.5 rounded-[10px] bg-emerald-50/80 border border-emerald-100 px-3 py-1.5 text-[12px] font-semibold text-emerald-600 transition hover:bg-emerald-100/80 hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-400 dark:hover:bg-emerald-500/20"
                            >
                              <Download size={14} />
                              涓嬭浇鏁版嵁
                            </button>
                          )}
                          {item.artifactUrl && (
                            <button
                              type="button"
                              onClick={() => handleDownloadRemote(item.artifactUrl, `${baseName}-${item.title || 'table'}-screenshot.png`)}
                              className="inline-flex w-fit items-center gap-1.5 rounded-[10px] bg-slate-50 border border-slate-200/60 px-3 py-1.5 text-[12px] font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-800 dark:bg-slate-800/80 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-700"
                            >
                              <ImageIcon size={14} />
                              涓嬭浇鍘熷浘
                            </button>
                          )}
                        </div>

                        {(item.dataframe.headers.length > 0 || item.dataframe.rows.length > 0) && (
                          <div className="overflow-hidden rounded-[16px] border border-slate-200/60 bg-slate-50/50 dark:border-slate-700/60 dark:bg-slate-900/40">
                            <div className="overflow-x-auto">
                              <table className="min-w-full text-[13px]">
                                {item.dataframe.headers.length > 0 && (
                                  <thead>
                                    <tr className="bg-slate-100/50 dark:bg-slate-800/50">
                                      {item.dataframe.headers.map((header, idx) => (
                                        <th key={`${item.key}-h-${idx}`} className="whitespace-nowrap border-b border-slate-200/60 px-4 py-2.5 text-left font-semibold text-slate-800 dark:border-slate-700/60 dark:text-slate-200">
                                          {header || `鍒?${idx + 1}`}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                )}
                                <tbody>
                                  {previewRows.map((row, rowIdx) => (
                                    <tr key={`${item.key}-r-${rowIdx}`} className="border-b border-slate-100/60 last:border-0 hover:bg-slate-100/30 dark:border-slate-800/60 dark:hover:bg-slate-800/30">
                                      {row.map((cell, cellIdx) => (
                                        <td key={`${item.key}-c-${rowIdx}-${cellIdx}`} className="whitespace-nowrap px-4 py-2 text-slate-600 dark:text-slate-400">
                                          {cell}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            <div className="flex items-center justify-between border-t border-slate-200/60 bg-slate-100/50 px-4 py-2.5 text-[12px] text-slate-500 dark:border-slate-700/60 dark:bg-slate-800/50 dark:text-slate-400">
                              <span>鍏?{item.dataframe.rowCount} 琛?/ {item.dataframe.colCount} 鍒?/span>
                              {item.dataframe.rows.length > 8 && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    setExpandedTableKeys((prev) =>
                                      prev.includes(item.key)
                                        ? prev.filter((key) => key !== item.key)
                                        : [...prev, item.key],
                                    )
                                  }
                                  className="font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                                >
                                  {expanded ? '鏀惰捣' : '灞曞紑瀹屾暣琛ㄦ牸'}
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          )}

          {activeTab === 'charts' && (
            <div className="space-y-4">
              {chartItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-50 text-slate-400 dark:bg-slate-800/80 dark:text-slate-500">
                    <BarChart3 size={24} strokeWidth={1.5} />
                  </div>
                  <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">鏆傛棤鍥捐〃浜х墿</p>
                  <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">璇ユ枃妗ｆ湭瑙ｆ瀽鍑哄浘琛ㄤ俊鎭?/p>
                </div>
              ) : (
                chartItems.map((item) => (
                  <article key={item.key} className="overflow-hidden rounded-[20px] bg-white border border-slate-100 shadow-[0_2px_10px_rgba(0,0,0,0.02)] transition-colors hover:border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/40 dark:hover:border-slate-600">
                    <div className="p-4">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '鍥捐〃'}</p>
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            {item.page > 0 && <span className="rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">绗?{item.page} 椤?/span>}
                            {item.pointCount > 0 && <span className="rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">{item.pointCount} 涓偣</span>}
                          </div>
                        </div>
                      </div>

                      {(item.xAxisLabel || item.yAxisLabel) && (
                        <div className="mb-3 rounded-[12px] border border-slate-200/70 bg-slate-50/70 px-3 py-2 dark:border-slate-700/70 dark:bg-slate-900/40">
                          {item.xAxisLabel && (
                            <p className="text-[12px] leading-5 text-slate-600 dark:text-slate-300">
                              X杞达細{item.xAxisLabel}
                            </p>
                          )}
                          {item.yAxisLabel && (
                            <p className="text-[12px] leading-5 text-slate-600 dark:text-slate-300">
                              Y杞达細{item.yAxisLabel}
                            </p>
                          )}
                        </div>
                      )}

                      {item.summary && (
                        <p className="mb-3 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
                          <span className="mr-1 font-semibold text-slate-700 dark:text-slate-200">瓒嬪娍瑙ｈ锛?/span>
                          {item.summary}
                        </p>
                      )}

                      <TraceChartPreview spec={item.chartSpec} compact />
                    </div>
                  </article>
                ))
              )}
            </div>
          )}

          {activeTab === 'images' && (
            <div className="space-y-4">
              {imageItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-50 text-slate-400 dark:bg-slate-800/80 dark:text-slate-500">
                    <ImageIcon size={24} strokeWidth={1.5} />
                  </div>
                  <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">鏆傛棤鍥剧墖浜х墿</p>
                  <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">璇ユ枃妗ｆ湭瑙ｆ瀽鍑哄浘鐗囦俊鎭?/p>
                </div>
              ) : (
                imageItems.map((item) => {
                  const baseName = toFileBaseName(activeDoc?.file_name || 'document');
                  return (
                    <article key={item.key} className="overflow-hidden rounded-[20px] bg-white border border-slate-100 shadow-[0_2px_10px_rgba(0,0,0,0.02)] transition-colors hover:border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/40 dark:hover:border-slate-600">
                      <div className="p-4">
                        <div className="mb-2 flex items-start justify-between gap-3">
                          <div className="flex-1">
                            <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '鍥剧墖'}</p>
                            {item.page > 0 && <span className="mt-1 inline-block rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">绗?{item.page} 椤?/span>}
                          </div>
                          {item.artifactUrl && (
                            <a
                              href={item.artifactUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-50 text-slate-600 shadow-[0_2px_8px_rgba(0,0,0,0.04)] transition-colors hover:bg-slate-100 hover:text-slate-900 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600 dark:hover:text-white"
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                        </div>

                        {item.caption && (
                          <p className="mb-3 whitespace-pre-wrap break-words text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
                            {item.caption}
                          </p>
                        )}

                        {item.artifactUrl && (
                          <button
                            type="button"
                            onClick={() => handleDownloadRemote(item.artifactUrl, `${baseName}-${item.title || 'image'}.png`)}
                            className="mb-4 inline-flex w-fit items-center gap-1.5 rounded-[10px] bg-slate-50 border border-slate-200/60 px-3 py-1.5 text-[12px] font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-800 dark:bg-slate-800/80 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-700"
                          >
                            <Download size={14} />
                            涓嬭浇鍥剧墖
                          </button>
                        )}
                      </div>
                      {item.artifactUrl ? (
                        <div className="bg-slate-50/50 px-4 py-6 border-t border-slate-100 dark:bg-slate-900/50 dark:border-slate-800">
                          <img
                            src={item.artifactUrl}
                            alt={item.title || '鍥剧墖鎴浘'}
                            className="mx-auto max-h-[240px] rounded-[12px] object-contain shadow-sm border border-slate-200/60 dark:border-slate-700"
                            loading="lazy"
                          />
                        </div>
                      ) : (
                        <p className="bg-slate-50/50 px-4 py-12 border-t border-slate-100 text-center text-[13px] text-slate-500 dark:bg-slate-900/50 dark:border-slate-800 dark:text-slate-500">
                          鏆傛棤鍥剧墖璧勬簮
                        </p>
                      )}
                    </article>
                  );
                })
              )}
            </div>
          )}
        </motion.div>
      </section>
    );
    */
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 15, scale: 0.95 },
    show: { opacity: 1, y: 0, scale: 1, transition: { type: 'spring' as const, stiffness: 300, damping: 24 } }
  };

  const cardVariants = {
    hidden: { opacity: 0, y: 80 },
    show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 260, damping: 26 } }
  };

  const stickySearchLayerOpacity = clamp01(stickySearchProgress * 1.1);
  const stickySearchShellOpacity = clamp01((stickySearchProgress - 0.08) / 0.72);
  const heroSearchOpacity = clamp01(1 - stickySearchProgress * 1.05);
  const heroSearchScale = 1 - stickySearchProgress * 0.06;
  const heroSearchYOffset = -stickySearchProgress * 22;
  const heroSearchBlur = stickySearchProgress * 4;
  const stickySearchYOffset = (1 - stickySearchShellOpacity) * -16;
  const stickySearchScale = 0.97 + stickySearchShellOpacity * 0.03;
  const heroSearchDisabled = stickySearchShellOpacity > 0.62;
  const stickySearchEnabled = stickySearchShellOpacity > 0.2;

  return (
    <motion.div 
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="flex h-[100dvh] flex-col bg-gradient-to-b from-[#C5F1F3] via-[#E6F7F9] to-[#F2F5F8] font-sans overflow-hidden dark:from-slate-900 dark:via-slate-900 dark:to-slate-950"
    >
      {/* Impeccable 级悬浮搜索背景 (全宽毛玻璃，无生硬边缘，无尴尬留白) */}
      <motion.div
        aria-hidden="true"
        className="pointer-events-none fixed inset-x-0 top-0 z-[58] border-b border-slate-200/40 bg-[#fbfcfd]/90 pb-3 pt-[max(12px,env(safe-area-inset-top))] shadow-[0_2px_12px_rgba(0,0,0,0.03)] backdrop-blur-xl dark:border-white/5 dark:bg-[#0B1120]/95 dark:shadow-none"
        style={{ opacity: stickySearchLayerOpacity }}
      >
        <div className="h-[46px]" /> {/* 占位撑开高度与搜索框一致 */}
      </motion.div>

      {/* 悬浮搜索框主体 (完全融入毛玻璃背景，放弃生硬的大白块包裹) */}
      <div
        ref={stickySearchShellRef}
        className="pointer-events-none fixed inset-x-0 top-0 z-[65] px-4 pt-[max(12px,env(safe-area-inset-top))]"
      >
        <motion.div
          style={{
            opacity: stickySearchShellOpacity,
            y: stickySearchYOffset,
            scale: stickySearchScale,
            pointerEvents: stickySearchEnabled ? 'auto' : 'none',
          }}
          className="mx-auto w-full"
        >
          <div className="flex h-[46px] w-full items-center gap-3 rounded-full bg-slate-100/60 px-5 ring-1 ring-slate-200/60 transition-all focus-within:bg-white focus-within:shadow-sm focus-within:ring-slate-300 dark:bg-white/[0.04] dark:ring-white/[0.05] dark:focus-within:bg-[#1A1D24] dark:focus-within:ring-white/10">
            <Search className="text-slate-400 dark:text-slate-500" size={18} />
            <input
              ref={stickySearchInputRef}
              type="text"
              aria-label="搜索解析记录"
              placeholder="搜索解析记录..."
              value={searchQuery}
              disabled={!stickySearchEnabled}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="min-w-0 flex-1 bg-transparent text-[15px] font-medium text-slate-800 placeholder:text-slate-400 focus:outline-none disabled:cursor-default dark:text-slate-200 dark:placeholder:text-slate-500"
            />
          </div>
        </motion.div>
      </div>

      <div className="px-4 pt-[max(0rem,env(safe-area-inset-top))] flex-1 flex flex-col min-h-0">
        {/* 顶部独立导航区 (分离式设计：主标题与副标题) */}
        {/* 整体上移：将 pt-6 减小为 pt-3，使得页面内容整体向上提升约 12px */}
        <motion.div variants={itemVariants} className="relative z-40 flex items-start justify-between px-3 pt-2 overflow-visible pointer-events-auto">
          {/* 左侧标题区：通过 -ml-2 抵消部分 px-3，配合下方标题的 px-1，统一向右微调 4px；向下微调 8px 靠近搜索框 */}
          <div className="relative z-50 flex flex-col gap-1 -ml-2 translate-y-3">
            <div className="flex items-center gap-2.5">
              {/* 主标题缩小至 22px */}
              <h1 className="text-[22px] font-bold tracking-tight text-slate-900 dark:text-white">
                AI信息提取
              </h1>
              {/* 智能助手小组件 */}
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setAssistantOpen(true);
                }}
                className="relative z-50 pointer-events-auto cursor-pointer flex items-center justify-center transition-transform active:scale-[0.92]"
                aria-label="打开智能助手"
              >
                {/* 底部白色动态光晕层：加入 pulse 动画效果，使其像呼吸一样闪烁 */}
                <div className="absolute top-1/2 left-1/2 z-0 h-[24px] w-[24px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/90 blur-[6px] dark:bg-white/40 animate-pulse" aria-hidden="true" />
                {/* 右上角小星光点缀 */}
                <Sparkles 
                  size={12} 
                  className="absolute -right-1.5 -top-1.5 z-20 text-amber-400 animate-pulse dark:text-amber-300 drop-shadow-[0_0_2px_rgba(251,191,36,0.8)]" 
                  aria-hidden="true" 
                />
                {/* 图标主体：设置 relative z-10 确保完全覆盖在光晕之上 */}
                <img src={aiAssistantIcon} alt="AI 助手" className="relative z-10 h-[28px] w-[28px] object-contain drop-shadow-sm" />
              </button>
            </div>
            {/* 副标题缩小至 13px */}
            <p className="text-[13px] bg-gradient-to-r from-slate-500/90 via-slate-700 to-slate-500/90 bg-[length:200%_auto] bg-clip-text text-transparent animate-text-shimmer dark:from-slate-400 dark:via-white dark:to-slate-400">
              智能解析与结构化产物检索
            </p>
          </div>
          
          {/* 右侧沉浸式悬浮插图：移除透明度遮罩，展示原图 */}
          <div className="absolute right-0 top-0 bottom-0 z-0 pointer-events-none w-[160px] overflow-visible">
            <div className="absolute -right-1 -top-7 h-[120px] w-[160px]">
              <img 
                src={headerIllustration} 
                alt="Decorative Illustration" 
                className="absolute inset-0 h-full w-full object-contain object-right-bottom mix-blend-multiply dark:opacity-80 dark:mix-blend-normal"
                aria-hidden="true"
              />
            </div>
          </div>
        </motion.div>

        {/* 核心搜索区域：大幅缩减上边距，让出首屏空间 */}
        <div ref={heroSearchAnchorRef} className="pointer-events-none h-0" aria-hidden="true" />
        <motion.div
          variants={itemVariants}
          className="relative mb-4 pt-6 z-30"
          style={{
            opacity: heroSearchOpacity,
            y: heroSearchYOffset,
            scale: heroSearchScale,
            filter: `blur(${heroSearchBlur.toFixed(2)}px)`,
          }}
        >
          <div className="flex h-[46px] w-full items-center gap-3 rounded-full bg-white/96 px-5 shadow-[0_8px_24px_rgba(0,0,0,0.04)] ring-1 ring-white/50 dark:bg-slate-800 dark:shadow-[0_8px_24px_rgba(0,0,0,0.2)] dark:ring-slate-700/50">
            <Search className="text-slate-400" size={18} />
            <input
              ref={heroSearchInputRef}
              type="text"
              aria-label="搜索解析记录"
              placeholder="搜索解析记录..." 
              value={searchQuery}
              disabled={heroSearchDisabled}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent text-[15px] text-slate-800 placeholder:text-slate-400 focus:outline-none disabled:cursor-default dark:text-slate-200"
            />
          </div>
        </motion.div>

        {/* Quick Upload Rail */}
        <motion.div variants={itemVariants} className="mb-2">
          <div className="mb-2 px-1">
            <h3 className="text-[15px] font-bold text-slate-800 dark:text-slate-100">文件上传</h3>
          </div>

          <div className="-mx-1 flex snap-x snap-mandatory gap-2.5 overflow-x-auto px-1 pb-1 scrollbar-hide [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
            {QUICK_UPLOAD_SHORTCUTS.map((shortcut) => {
              const isActive = activeUploadShortcut === shortcut.id;
              const Icon = shortcut.icon;
              return (
                <button
                  key={shortcut.id}
                  type="button"
                  onClick={() => handleQuickUploadShortcut(shortcut)}
                  className="group flex min-w-[74px] snap-start shrink-0 flex-col items-center gap-2.5 rounded-[16px] bg-transparent px-1 py-1 text-center transition-transform active:scale-[0.97]"
                >
                  <div
                    className={cn(
                      'flex h-[56px] w-[56px] items-center justify-center rounded-[18px] border shadow-[0_4px_12px_rgba(15,23,42,0.04)] transition-all dark:shadow-[0_4px_12px_rgba(2,6,23,0.16)]',
                      isActive
                        ? cn(shortcut.activeBg, shortcut.activeBorder, 'shadow-[0_8px_16px_rgba(59,130,246,0.08)]')
                        : 'border-white/80 bg-white/92 dark:border-slate-700/60 dark:bg-slate-800/95',
                    )}
                  >
                    {shortcut.iconImg ? (
                      <img
                        src={shortcut.iconImg}
                        alt={shortcut.label}
                        className="h-[32px] w-[32px] object-contain transition-transform group-hover:scale-110"
                      />
                    ) : Icon ? (
                      <Icon
                        size={22}
                        className={cn('transition-transform group-hover:scale-110', shortcut.color)}
                        strokeWidth={2.1}
                      />
                    ) : null}
                  </div>
                  <p
                    className={cn(
                      'text-[12px] font-semibold tracking-tight',
                      isActive ? 'text-slate-900 dark:text-white' : 'text-slate-700 dark:text-slate-300',
                    )}
                  >
                    {shortcut.label}
                  </p>
                </button>
              );
            })}
          </div>

          <input
            ref={quickUploadInputRef}
            type="file"
            multiple
            accept={QUICK_UPLOAD_ALL_ACCEPT}
            aria-label="手机端快捷上传文件"
            className="hidden"
            onChange={handleQuickUploadChange}
          />
        </motion.div>

        {uploadQueue.length > 0 && (
          <motion.div
            variants={itemVariants}
            className="mt-2 rounded-[16px] border border-slate-200 bg-white/90 p-3 shadow-[0_8px_20px_rgba(0,0,0,0.03)] dark:border-slate-700 dark:bg-slate-800/80"
          >
            <div className="mb-2.5 flex items-center justify-between gap-2">
              <p className="text-[13px] font-semibold text-slate-700 dark:text-slate-200">
                单文件解析队列
              </p>
              <button
                type="button"
                onClick={clearFinishedUploadQueue}
                className="text-[12px] font-medium text-slate-500 transition hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
              >
                清理已结束
              </button>
            </div>
            <div className="space-y-2">
              {uploadQueue.map((item) => {
                const canStart = item.status === 'queued' || item.status === 'failed' || item.status === 'cancelled' || item.status === 'completed';
                const queuePreviewHash = toQueuePreviewHash(item.id);
                const queueActive = activeDocHash === queuePreviewHash;
                return (
                  <div
                    key={item.id}
                    className={cn(
                      'flex items-center gap-2 rounded-[12px] border px-2.5 py-2 transition-colors',
                      queueActive
                        ? 'border-blue-300 bg-blue-50/80 dark:border-blue-500/70 dark:bg-blue-500/15'
                        : 'border-slate-200/80 bg-slate-50/70 dark:border-slate-700 dark:bg-slate-900/30',
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] font-medium text-slate-700 dark:text-slate-200">
                        {item.resolvedFileName || item.file.name}
                      </p>
                      <p className="truncate text-[11px] text-slate-500 dark:text-slate-400">
                        {UPLOAD_STATUS_LABELS[item.status]} · {item.message}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => openQueuePreview(item.id)}
                      className="inline-flex h-[28px] items-center gap-1.5 rounded-[10px] bg-white px-2.5 text-[12px] font-medium text-slate-600 shadow-sm transition-colors active:bg-slate-50 dark:bg-white/[0.04] dark:text-slate-300 dark:active:bg-white/[0.08] dark:shadow-none"
                    >
                      <MonitorPlay size={13} />
                      预览
                    </button>
                    {canStart && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          void startSingleUpload(item.id);
                        }}
                        className="inline-flex h-[28px] items-center gap-1.5 rounded-[10px] bg-blue-50 px-2.5 text-[12px] font-medium text-blue-600 transition-colors active:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-400 dark:active:bg-blue-500/20"
                      >
                        {item.status === 'queued' ? <Play size={13} /> : <RotateCcw size={13} />}
                        {item.status === 'queued' ? '开始解析' : '重试'}
                      </button>
                    )}
                    {item.status === 'running' && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          void cancelSingleUpload(item.id);
                        }}
                        className="inline-flex h-[28px] items-center gap-1.5 rounded-[10px] bg-rose-50 px-2.5 text-[12px] font-medium text-rose-600 transition-colors active:bg-rose-100 dark:bg-rose-500/10 dark:text-rose-400 dark:active:bg-rose-500/20"
                      >
                        <X size={13} />
                        取消
                      </button>
                    )}
                    {item.status !== 'running' && (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          removeUploadQueueItem(item.id);
                        }}
                        className="inline-flex h-[28px] w-[28px] shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-400 transition-colors active:bg-slate-100 active:text-red-500 dark:bg-white/[0.04] dark:text-slate-500 dark:active:bg-white/[0.08] dark:active:text-red-400"
                        aria-label={`移除 ${item.file.name}`}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}

        <motion.section variants={cardVariants} className="relative z-20 flex-1 flex flex-col min-h-0">
          <div className="-mx-4 rounded-t-[32px] bg-white pt-6 shadow-[0_-4px_24px_rgba(0,0,0,0.02)] dark:bg-slate-900/95 dark:shadow-[0_-4px_24px_rgba(0,0,0,0.2)] flex-1 flex flex-col min-h-0">
            <div className="mb-4 flex items-center justify-between px-6 shrink-0">
              <h3 className="text-[16px] font-bold text-slate-800 dark:text-slate-100">解析文档列表</h3>
            </div>
            
            <div className="relative z-10 px-6 flex-1 overflow-y-auto pb-[calc(env(safe-area-inset-bottom)+70px)]">
              {filteredDocuments.length === 0 ? (
                <div className="mt-2 flex w-full flex-col items-center justify-center rounded-[24px] border-2 border-dashed border-slate-200/60 bg-slate-50/50 py-14 text-center dark:border-slate-700/60 dark:bg-slate-800/20">
                  <div className="mb-4 flex h-[60px] w-[60px] items-center justify-center rounded-[18px] bg-white shadow-[0_8px_30px_rgba(6,182,212,0.15)] ring-1 ring-slate-100 dark:bg-slate-800 dark:shadow-[0_8px_30px_rgba(6,182,212,0.08)] dark:ring-slate-700">
                    <FileSearch size={28} className="text-cyan-500 dark:text-cyan-400" strokeWidth={1.5} />
                  </div>
                  <p className="text-[15px] font-bold text-slate-700 dark:text-slate-200">暂无解析记录</p>
                  <p className="mt-1.5 max-w-[200px] text-[13px] leading-relaxed text-slate-400 dark:text-slate-500">
                    {documents.length > 0 ? "没有找到符合条件的文档" : "请先上传文件并创建解析任务"}
                  </p>
                </div>
              ) : (
              <div className="flex flex-col gap-3">
                {filteredDocuments.map((doc) => {
                const active = doc.file_hash === activeDocHash;
                const errorCount = Array.isArray(doc.errors) ? doc.errors.length : 0;
                const warningCount = new Set(
                  (Array.isArray(doc.soft_warnings) ? doc.soft_warnings : [])
                    .map((item) => String(item || '').trim().toLowerCase())
                    .filter(Boolean),
                ).size;
                const fieldCount = countExtractionDocumentFields(doc);
                const reviewCount = errorCount + warningCount;

                const fileName = (doc.file_name || '').toLowerCase();
                let FileIcon = FileText;
                let iconColors = 'bg-slate-50 text-slate-500 dark:bg-slate-800 dark:text-slate-400';
                let fileImgSrc: string | undefined = txtIcon;
                
                if (fileName.endsWith('.pdf')) {
                  FileIcon = FileText;
                  iconColors = 'bg-red-50 text-red-500 dark:bg-red-500/10 dark:text-red-400';
                  fileImgSrc = pdfIcon;
                } else if (fileName.endsWith('.doc') || fileName.endsWith('.docx')) {
                  FileIcon = File;
                  iconColors = 'bg-blue-50 text-blue-500 dark:bg-blue-500/10 dark:text-blue-400';
                  fileImgSrc = wordIcon;
                } else if (fileName.endsWith('.xls') || fileName.endsWith('.xlsx') || fileName.endsWith('.csv')) {
                  FileIcon = FileSpreadsheet;
                  iconColors = 'bg-green-50 text-green-600 dark:bg-green-500/10 dark:text-green-500';
                  fileImgSrc = excelIcon;
                } else if (fileName.endsWith('.ppt') || fileName.endsWith('.pptx')) {
                  FileIcon = MonitorPlay;
                  iconColors = 'bg-orange-50 text-orange-500 dark:bg-orange-500/10 dark:text-orange-400';
                  fileImgSrc = undefined;
                } else if (fileName.endsWith('.md')) {
                  FileIcon = FileText;
                  iconColors = 'bg-cyan-50 text-cyan-600 dark:bg-cyan-500/10 dark:text-cyan-500';
                  fileImgSrc = mdIcon;
                }

                const relatedQueueItem = uploadQueue.find((item) => {
                  const sameHash = Boolean(item.fileHash) && item.fileHash === doc.file_hash;
                  const sameName =
                    normalizeFileName(item.resolvedFileName || item.file.name)
                    === normalizeFileName(doc.file_name);
                  return sameHash || sameName;
                });

                return (
                  <article
                    key={doc.file_hash}
                    title={`字段 ${fieldCount} · 待核验 ${reviewCount}`}
                    className={cn(
                      'group relative flex w-full flex-col gap-3 rounded-[16px] p-3 text-left transition-colors active:bg-slate-50 dark:active:bg-white/[0.05]',
                      active 
                        ? 'bg-blue-50/40 shadow-[0_4px_20px_rgba(59,130,246,0.06)] dark:bg-blue-500/5 dark:shadow-none' 
                        : 'bg-white shadow-[0_2px_12px_rgba(0,0,0,0.02)] dark:bg-white/[0.03] dark:shadow-none dark:ring-1 dark:ring-white/[0.05]'
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <div className={cn('flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-[12px]', iconColors)}>
                        {fileImgSrc ? (
                          <img src={fileImgSrc} alt={fileName} className="h-5 w-5 object-contain drop-shadow-sm" />
                        ) : (
                          <FileIcon size={20} strokeWidth={2} />
                        )}
                      </div>

                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[14px] font-semibold text-slate-800 dark:text-slate-100">
                          {doc.file_name}
                        </p>
                        <div className="mt-1 flex items-center gap-2 text-[12px] text-slate-400 dark:text-slate-500">
                          <span className="flex items-center gap-1 rounded-md bg-slate-50 px-1.5 py-0.5 dark:bg-white/[0.04]">字段 {fieldCount}</span>
                          <span className={cn('flex items-center gap-1 rounded-md px-1.5 py-0.5', errorCount > 0 ? 'bg-red-50 text-red-500 dark:bg-red-500/10 dark:text-red-400' : 'bg-slate-50 dark:bg-white/[0.04]')}>异常 {errorCount}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex w-full flex-wrap items-center gap-2 pt-1 border-t border-slate-50 dark:border-white/[0.02]">
                      <button
                        type="button"
                        onClick={() => openDocumentPreview(doc)}
                        className="inline-flex h-[28px] flex-1 items-center justify-center gap-1.5 rounded-[10px] bg-slate-50 px-2 text-[12px] font-medium text-slate-600 transition-colors active:bg-slate-100 dark:bg-white/[0.04] dark:text-slate-300 dark:active:bg-white/[0.08]"
                      >
                        <MonitorPlay size={13} />
                        预览
                      </button>
                      <button
                        type="button"
                        onClick={() => openDocumentArtifacts(doc)}
                        className="inline-flex h-[28px] flex-1 items-center justify-center gap-1.5 rounded-[10px] bg-slate-50 px-2 text-[12px] font-medium text-slate-600 transition-colors active:bg-slate-100 dark:bg-white/[0.04] dark:text-slate-300 dark:active:bg-white/[0.08]"
                      >
                        <LayoutList size={13} />
                        产物
                      </button>
                      {relatedQueueItem?.status === 'running' ? (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            void cancelSingleUpload(relatedQueueItem.id);
                          }}
                          className="inline-flex h-[28px] flex-1 items-center justify-center gap-1.5 rounded-[10px] bg-rose-50/80 px-2 text-[12px] font-medium text-rose-600 transition-colors active:bg-rose-100 dark:bg-rose-500/10 dark:text-rose-400 dark:active:bg-rose-500/20"
                        >
                          <X size={13} />
                          取消
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            void reparseDocument(doc);
                          }}
                          className="inline-flex h-[28px] flex-1 items-center justify-center gap-1.5 rounded-[10px] bg-slate-50 px-2 text-[12px] font-medium text-slate-600 transition-colors active:bg-slate-100 dark:bg-white/[0.04] dark:text-slate-300 dark:active:bg-white/[0.08]"
                        >
                          <RotateCcw size={13} />
                          重试
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          requestRemoveDocument(doc);
                        }}
                        className="inline-flex h-[28px] w-[28px] shrink-0 items-center justify-center rounded-[10px] bg-red-50/50 text-red-400 transition-colors active:bg-red-100 active:text-red-600 dark:bg-red-500/10 dark:text-red-400/80 dark:active:bg-red-500/30"
                        aria-label="移除"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </article>
                );
              })}
              </div>
            )}
          </div>
          </div>
        </motion.section>

        {/* Deprecated banner removed: keep single-path upload flow */}
        {/*
        <motion.button
          variants={itemVariants}
          onClick={() => handleQuickUploadShortcut(QUICK_UPLOAD_SHORTCUTS[0])}
          data-testid="mobile-upload-workspace-entry"
          className="flex w-full items-center justify-between rounded-[22px] bg-[#0A2E36] px-4 py-3.5 text-left shadow-xl transition-transform active:scale-[0.98] dark:bg-slate-800"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-[40px] w-[40px] items-center justify-center rounded-[13px] bg-white/10">
              <FileSearch size={20} className="text-white" strokeWidth={2} />
            </div>
            <div>
              <h3 className="text-[16px] font-semibold text-white tracking-wide">上传后手动开始解析</h3>
              <p className="mt-0.5 text-[12px] text-slate-300/80">上传仅入队，不会自动解析；请按文件逐个确认</p>
            </div>
          </div>
        </motion.button>
        */}

        
      </div>

      {previewOpen && previewDoc && (
        <div className="fixed inset-0 z-[72] bg-white dark:bg-slate-950 overflow-hidden">
          <div className="flex h-14 items-center justify-between border-b border-slate-200/70 bg-white/92 px-4 pt-[max(0px,env(safe-area-inset-top))] shadow-[0_6px_18px_rgba(15,23,42,0.06)] backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/92 dark:shadow-none">
            <div className="flex-1 min-w-0 pr-4">
              <p className="text-[17px] font-bold text-slate-900 dark:text-slate-100">文件预览</p>
            </div>
            <div className="flex items-center gap-2">
              {activeDoc && (
                <button
                  type="button"
                  onClick={() => {
                    setPreviewOpen(false);
                    setArtifactOpen(true);
                  }}
                  className="inline-flex h-8 items-center gap-1.5 rounded-full bg-slate-900 px-3.5 text-[13px] font-medium text-white shadow-[0_2px_8px_rgba(15,23,42,0.12)] transition active:scale-95 dark:bg-slate-100 dark:text-slate-900"
                >
                  <LayoutList size={14} />
                  产物
                </button>
              )}
              <button
                type="button"
                onClick={() => setPreviewOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-100/80 text-slate-500 transition active:scale-95 dark:bg-slate-800/80 dark:text-slate-400"
                aria-label="关闭预览"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="flex h-[calc(100dvh-3.5rem)] w-full flex-col overflow-hidden pb-[calc(env(safe-area-inset-bottom))]">
            <MobileDocumentPreviewCard
              activeDoc={previewDoc}
              preferredBase={apiBaseHint}
              activeSourceFile={activeSourceFile}
            />
          </div>
        </div>
      )}

      {artifactOpen && activeDoc && (
        <div className="fixed inset-0 z-[73] bg-[#f4fbfd] dark:bg-slate-950">
          <div className="flex h-14 items-center justify-between border-b border-slate-200/70 bg-white/92 px-4 pt-[max(0px,env(safe-area-inset-top))] shadow-[0_6px_18px_rgba(15,23,42,0.06)] backdrop-blur-xl dark:border-slate-800 dark:bg-slate-950/92 dark:shadow-none">
            <div className="flex-1 min-w-0 pr-4">
              <p className="text-[17px] font-bold text-slate-900 dark:text-slate-100">解析产物</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setArtifactOpen(false);
                  setPreviewOpen(true);
                }}
                className="inline-flex h-8 items-center gap-1.5 rounded-full bg-slate-900 px-3.5 text-[13px] font-medium text-white shadow-[0_2px_8px_rgba(15,23,42,0.12)] transition active:scale-95 dark:bg-slate-100 dark:text-slate-900"
              >
                <MonitorPlay size={14} />
                预览
              </button>
              <button
                type="button"
                onClick={() => setArtifactOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-100/80 text-slate-500 transition active:scale-95 dark:bg-slate-800/80 dark:text-slate-400"
                aria-label="关闭产物详情"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="h-[calc(100dvh-3.5rem)] overflow-y-auto px-2 pb-[calc(env(safe-area-inset-bottom)+1.5rem)] pt-2">
            {renderArtifactDetailPanel()}
          </div>
        </div>
      )}

      {pendingRemoveDoc && (
        <div className="fixed inset-0 z-[70] flex items-end bg-black/40 p-4 backdrop-blur-[1px]">
          <div className="w-full rounded-[20px] border border-slate-200 bg-white p-4 shadow-[0_20px_40px_rgba(15,23,42,0.2)] dark:border-slate-700 dark:bg-slate-900">
            <p className="text-[16px] font-semibold text-slate-900 dark:text-slate-100">
              移除文件
            </p>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-600 dark:text-slate-300">
              确认移除 <span className="font-medium text-slate-800 dark:text-slate-100">{pendingRemoveDoc.file_name}</span> 吗？
              如果该文件正在解析，会先取消任务再移除。
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={cancelRemoveDocument}
                className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-3 py-2 text-[13px] font-semibold text-slate-600 transition hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void confirmRemoveDocument()}
                className="inline-flex items-center justify-center rounded-xl bg-rose-600 px-3 py-2 text-[13px] font-semibold text-white transition hover:bg-rose-700"
              >
                确认移除
              </button>
            </div>
          </div>
        </div>
      )}

      {toastMessage && (
        <div className="pointer-events-none fixed bottom-[calc(env(safe-area-inset-bottom)+5.8rem)] left-1/2 z-[75] -translate-x-1/2">
          <div className="max-w-[88vw] rounded-full bg-slate-900/92 px-4 py-2 text-[12px] font-medium text-white shadow-[0_12px_24px_rgba(15,23,42,0.28)] dark:bg-slate-700/95">
            {toastMessage}
          </div>
        </div>
      )}

      <MobileAssistantDialog
        open={assistantOpen}
        activeDoc={activeDoc}
        activeDocIndex={activeDocIndex >= 0 ? activeDocIndex : 0}
        documents={documents}
        traceHits={traceHits}
        preferredBase={apiBaseHint}
        onPreferredBaseChange={setApiBaseHint}
        onClose={() => setAssistantOpen(false)}
        onSelectCitation={handleAssistantCitationSelect}
      />
    </motion.div>
  );
};
