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
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { parseErrorMessage } from '../../shared/api/client';
import { MobileAssistantDialog } from './mobile/MobileAssistantDialog';
import { MobileDocumentPreviewCard } from './mobile/MobileDocumentPreviewCard';
import TraceChartPreview from '../../components/trace/TraceChartPreview';
import headerIllustration from '../../assets/插图1.png';
import bodyIllustration from '../../assets/插图二.png';
import allIcon from '../../assets/文档.png';
import pdfIcon from '../../assets/pdf.png';
import wordIcon from '../../assets/WORD.png';
import excelIcon from '../../assets/xlsx.png';
import txtIcon from '../../assets/txt.png';
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
  const payload = pickBestDataframe(locator.dataframe, locator.table_preview, locator.dataframe_json);
  return payload.headers.length > 0 || payload.rows.length > 0;
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

const QUICK_UPLOAD_ALL_ACCEPT =
  '.pdf,.doc,.docx,.xlsx,.txt,.md';

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
    iconImg: txtIcon, // Using txtIcon for md fallback
    color: 'text-cyan-600',
    activeBg: 'bg-cyan-50 dark:bg-cyan-500/10',
    activeBorder: 'border-cyan-200 dark:border-cyan-500/30',
  },
];

export const MobileDeepReadPage: React.FC = () => {
  const [documents, setDocuments] = useState<ExtractionDocument[]>([]);
  const [activeDocHash, setActiveDocHash] = useState('');
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
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
    setUploadQueue((previous) => previous.filter((item) => item.id !== itemId));
  };

  const clearFinishedUploadQueue = () => {
    setUploadQueue((previous) =>
      previous.filter((item) => item.status === 'queued' || item.status === 'running'),
    );
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
      };
      const status = String(payload.status || '').trim();
      const errors = Array.isArray(payload.errors)
        ? payload.errors.map((item) => String(item || '').trim()).filter(Boolean)
        : [];
      const documents = filterAutoRestorableExtractionDocuments(
        Array.isArray(payload.documents) ? payload.documents : [],
      );
      const terminal = Boolean(payload.terminal)
        || ['completed', 'failed', 'cached', 'cancelled'].includes(status.toLowerCase());
      if (terminal) {
        return {
          status,
          errors,
          documents,
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
      }
      if (parsedDocuments.length === 0) {
        throw new Error('未返回可用解析结果');
      }

      const nextDocuments = mergeDocuments(documentsRef.current, parsedDocuments);
      setDocuments(nextDocuments);
      writeExtractionDocuments(nextDocuments);
      documentsRef.current = nextDocuments;

      setSourceFilesByHash((previous) => {
        const next = { ...previous };
        parsedDocuments.forEach((doc) => {
          if (normalizeFileName(doc.file_name) === normalizeFileName(current.file.name)) {
            next[doc.file_hash] = current.file;
          }
        });
        sourceFilesByHashRef.current = next;
        return next;
      });

      const matchedDoc = parsedDocuments.find(
        (doc) => normalizeFileName(doc.file_name) === normalizeFileName(current.file.name),
      ) || parsedDocuments[0];
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
    if (filteredDocuments.length === 0) {
      if (documents.length === 0) {
        setActiveDocHash('');
      }
      return;
    }
    const exists = filteredDocuments.some((doc) => doc.file_hash === activeDocHash);
    if (!exists) {
      setActiveDocHash(filteredDocuments[0].file_hash);
    }
  }, [filteredDocuments, documents.length, activeDocHash]);

  const activeDoc = useMemo(
    () => documents.find((doc) => doc.file_hash === activeDocHash) ?? null,
    [documents, activeDocHash],
  );
  const activeDocIndex = useMemo(
    () => documents.findIndex((doc) => doc.file_hash === activeDocHash),
    [documents, activeDocHash],
  );
  const activeSourceFile = useMemo(
    () => (activeDoc ? sourceFilesByHash[activeDoc.file_hash] || null : null),
    [activeDoc, sourceFilesByHash],
  );

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
          return {
            key: `${hit.ref_id || hit.object_id || 'chart'}-${index}`,
            title: getTraceChartTitle(chartSpec, String(hit.object_id || `图表 ${index + 1}`).trim()),
            summary: getTraceChartSummary(chartSpec),
            chartSpec,
            pointCount: getTraceChartPointCount(chartSpec),
            page: Number(hit.page || locator.page || 0),
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
    setAssistantOpen(false);
    if (typeof window !== 'undefined') {
      window.requestAnimationFrame(() => {
        document.getElementById('mobile-artifact-detail')?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      });
    }
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

  return (
    <motion.div 
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="-mb-28 flex min-h-[calc(100dvh-4.5rem)] flex-col bg-gradient-to-b from-[#C5F1F3] via-[#E6F7F9] to-[#F2F5F8] font-sans dark:from-slate-900 dark:via-slate-900 dark:to-slate-950"
    >
      <div className="px-4 pt-[max(0rem,env(safe-area-inset-top))]">
        {/* 顶部独立导航区 (分离式设计：主标题与副标题) */}
        {/* 整体上移：将 pt-6 减小为 pt-3，使得页面内容整体向上提升约 12px */}
        <motion.div variants={itemVariants} className="relative flex items-start justify-between px-3 pt-3 overflow-visible">
          {/* 左侧标题区：提升层级，向左微移，确保不被背景插图干扰 */}
          {/* 将文字区域单独通过 translate-y 向下平移 12px，以此来拉近与搜索框的距离，同时绝对不会影响其他任何组件 */}
          <div className="relative z-20 flex flex-col gap-1.5 -ml-1 translate-y-3">
            {/* 主标题放大至 26px */}
            <h1 className="text-[26px] font-bold tracking-tight text-slate-900 dark:text-white">
              AI文档处理
            </h1>
            {/* 副标题放大至 15px，并添加 Impeccable 风格的流光动效 */}
            <p className="text-[15px] bg-gradient-to-r from-slate-500/90 via-slate-700 to-slate-500/90 bg-[length:200%_auto] bg-clip-text text-transparent animate-text-shimmer dark:from-slate-400 dark:via-white dark:to-slate-400">
              智能解析与结构化产物检索
            </p>
          </div>
          
          {/* 方案A: 右侧沉浸式悬浮插图 (Impeccable 设计：底层渲染、半透明融合、允许破局与穿插) */}
          <div className="absolute right-0 top-0 bottom-0 z-0 pointer-events-none w-[220px] overflow-visible">
            {/* 再次微调放大插图：宽度提升到 220px，高度提升到 165px，并将 top 从 -top-12 调整为 -top-11 微微下移 (微调) */}
            <div className="absolute -right-4 -top-11 h-[165px] w-[220px]">
              <img 
                src={headerIllustration} 
                alt="Decorative Illustration" 
                className="absolute inset-0 h-full w-full object-contain object-right-bottom mix-blend-multiply opacity-[0.80] dark:opacity-40 dark:mix-blend-normal"
                aria-hidden="true"
              />
            </div>
          </div>
        </motion.div>

        {/* 核心搜索区域：将上边距从 pt-7 进一步调整为 pt-9，使其及其下方所有内容再次微微下移 */}
        <motion.div variants={itemVariants} className="relative pt-9 mb-5 z-30">
          <div className="flex h-[44px] w-full items-center gap-2.5 rounded-full bg-white px-4 shadow-[0_8px_24px_rgba(0,0,0,0.04)] dark:bg-slate-800 dark:shadow-[0_8px_24px_rgba(0,0,0,0.2)]">
            <Search className="text-slate-400" size={18} />
            <input 
              type="text" 
              placeholder="搜索解析记录..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent text-[14px] text-slate-800 placeholder:text-slate-400 focus:outline-none dark:text-slate-200"
            />
          </div>
        </motion.div>

        {/* Quick Upload Rail */}
        <motion.div variants={itemVariants} className="mb-4">
          <div className="mb-3.5 px-1">
            <h3 className="text-[17px] font-bold text-slate-800 dark:text-slate-100">文件上传</h3>
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
        
        {/* Decorative Body Illustration */}
        <motion.div variants={itemVariants} className="mb-3 mt-0.5 flex w-full justify-center px-2">
          <img 
            src={bodyIllustration} 
            alt="Upload Workspace Illustration" 
            className="h-auto w-full max-w-[288px] object-contain drop-shadow-sm transition-transform duration-500 hover:scale-[1.02] dark:opacity-90 dark:mix-blend-lighten" 
            aria-hidden="true" 
          />
        </motion.div>

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
                return (
                  <div
                    key={item.id}
                    className="flex items-center gap-2 rounded-[12px] border border-slate-200/80 bg-slate-50/70 px-2.5 py-2 dark:border-slate-700 dark:bg-slate-900/30"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] font-medium text-slate-700 dark:text-slate-200">
                        {item.resolvedFileName || item.file.name}
                      </p>
                      <p className="truncate text-[11px] text-slate-500 dark:text-slate-400">
                        {UPLOAD_STATUS_LABELS[item.status]} · {item.message}
                      </p>
                    </div>
                    {canStart && (
                      <button
                        type="button"
                        onClick={() => void startSingleUpload(item.id)}
                        className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-semibold text-blue-600 transition hover:bg-blue-100 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-300"
                      >
                        {item.status === 'queued' ? <Play size={12} /> : <RotateCcw size={12} />}
                        {item.status === 'queued' ? '开始解析' : '重新解析'}
                      </button>
                    )}
                    {item.status === 'running' && (
                      <button
                        type="button"
                        onClick={() => void cancelSingleUpload(item.id)}
                        className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-600 transition hover:bg-rose-100 dark:border-rose-500/40 dark:bg-rose-500/15 dark:text-rose-300"
                      >
                        <X size={12} />
                        取消解析
                      </button>
                    )}
                    {item.status !== 'running' && (
                      <button
                        type="button"
                        onClick={() => removeUploadQueueItem(item.id)}
                        className="inline-flex items-center rounded-full border border-slate-200 bg-white px-1.5 py-1 text-[11px] text-slate-500 transition hover:text-slate-700 dark:border-slate-600 dark:bg-slate-700/60 dark:text-slate-300"
                        aria-label={`移除 ${item.file.name}`}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </div>

      <div className="mt-1.5 flex-1 px-4 pb-28">
        <section className="mb-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-[17px] font-bold text-slate-800 dark:text-slate-100">解析文档列表</h3>
            <button className="inline-flex items-center gap-1 rounded-full bg-slate-200/50 px-3 py-1.5 text-[13px] font-medium text-slate-600 transition hover:bg-slate-300/50 hover:text-slate-800 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200">
              查看全部
            </button>
          </div>
          
          <motion.div variants={itemVariants}>
            {filteredDocuments.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-[26px] bg-white py-14 text-center shadow-[0_8px_32px_rgba(0,0,0,0.03)] dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
                <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-slate-50/80 text-slate-400 dark:bg-slate-800/80 dark:text-slate-500">
                  <FileSearch size={28} strokeWidth={1.5} />
                </div>
                <p className="text-[15px] font-semibold text-slate-700 dark:text-slate-200">暂无解析记录</p>
                <p className="mt-1.5 text-[13px] text-slate-400 dark:text-slate-500">
                  {documents.length > 0 ? "没有找到符合条件的文档" : "请先上传文件并创建解析任务"}
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-[26px] bg-white shadow-[0_8px_32px_rgba(0,0,0,0.03)] dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
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
                
                if (fileName.endsWith('.pdf')) {
                  FileIcon = FileText;
                  iconColors = 'bg-red-50 text-red-500 dark:bg-red-500/10 dark:text-red-400';
                } else if (fileName.endsWith('.doc') || fileName.endsWith('.docx')) {
                  FileIcon = File;
                  iconColors = 'bg-blue-50 text-blue-500 dark:bg-blue-500/10 dark:text-blue-400';
                } else if (fileName.endsWith('.xls') || fileName.endsWith('.xlsx') || fileName.endsWith('.csv')) {
                  FileIcon = FileSpreadsheet;
                  iconColors = 'bg-green-50 text-green-600 dark:bg-green-500/10 dark:text-green-500';
                } else if (fileName.endsWith('.ppt') || fileName.endsWith('.pptx')) {
                  FileIcon = MonitorPlay;
                  iconColors = 'bg-orange-50 text-orange-500 dark:bg-orange-500/10 dark:text-orange-400';
                }

                const relatedQueueItem = uploadQueue.find((item) => {
                  const sameHash = Boolean(item.fileHash) && item.fileHash === doc.file_hash;
                  const sameName =
                    normalizeFileName(item.resolvedFileName || item.file.name)
                    === normalizeFileName(doc.file_name);
                  return sameHash || sameName;
                });

                return (
                  <button
                    key={doc.file_hash}
                    type="button"
                    onClick={() => setActiveDocHash(doc.file_hash)}
                    title={`字段 ${fieldCount} · 待核验 ${reviewCount}`}
                    className={cn(
                      'group relative flex w-full items-center gap-3 border-b border-slate-100 px-4 py-3.5 text-left transition-colors last:border-b-0 hover:bg-slate-50 active:bg-slate-100 dark:border-slate-700/40 dark:hover:bg-slate-700/20',
                      active ? 'bg-blue-50/30 dark:bg-blue-900/10' : ''
                    )}
                  >
                    {/* Active Indicator Line */}
                    {active && (
                      <div className="absolute left-0 top-0 h-full w-[3px] bg-blue-500" />
                    )}
                    
                    {/* Icon */}
                    <div className={cn('flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-[15px]', iconColors)}>
                      <FileIcon size={22} strokeWidth={2} />
                    </div>
                    
                    {/* Text */}
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-[14px] font-semibold text-slate-800 dark:text-slate-100">
                        {doc.file_name}
                      </p>
                      <p className="mt-0.5 truncate text-[12px] text-slate-400 dark:text-slate-500">
                        字段 {fieldCount} · 异常 {errorCount}
                      </p>
                    </div>
                    
                    <div className="flex shrink-0 items-center gap-1">
                      {relatedQueueItem?.status === 'running' ? (
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            void cancelSingleUpload(relatedQueueItem.id);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              event.stopPropagation();
                              void cancelSingleUpload(relatedQueueItem.id);
                            }
                          }}
                          className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-600 transition hover:bg-rose-100 dark:border-rose-500/40 dark:bg-rose-500/15 dark:text-rose-300"
                        >
                          <X size={12} />
                          取消解析
                        </div>
                      ) : (
                        <div
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            void reparseDocument(doc);
                          }}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              event.stopPropagation();
                              void reparseDocument(doc);
                            }
                          }}
                          className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-semibold text-blue-600 transition hover:bg-blue-100 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-300"
                        >
                          <RotateCcw size={12} />
                          重新解析
                        </div>
                      )}
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={(event) => {
                          event.stopPropagation();
                          requestRemoveDocument(doc);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            event.stopPropagation();
                            requestRemoveDocument(doc);
                          }
                        }}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 transition hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-700/60 dark:text-slate-200"
                      >
                        <Trash2 size={12} />
                        移除
                      </div>
                    </div>
                  </button>
                );
              })}
              </div>
            )}
          </motion.div>
        </section>

        <MobileDocumentPreviewCard
          activeDoc={activeDoc}
          preferredBase={apiBaseHint}
          activeSourceFile={activeSourceFile}
        />

        <section id="mobile-artifact-detail">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="truncate text-[17px] font-bold text-slate-800 dark:text-slate-100">
              {activeDoc ? `${activeDoc.file_name} · 产物详情` : '产物详情'}
            </h3>
            <button
              type="button"
              onClick={() => setTraceRefreshNonce((prev) => prev + 1)}
              disabled={!activeDoc || traceLoading}
              className="inline-flex items-center gap-1.5 rounded-full bg-slate-200/50 px-3 py-1.5 text-[13px] font-medium text-slate-600 transition hover:bg-slate-300/50 hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
            >
              {traceLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCcw size={14} />}
              刷新
            </button>
          </div>

          <motion.div variants={itemVariants} className="rounded-[26px] bg-white p-4 shadow-[0_8px_32px_rgba(0,0,0,0.03)] dark:bg-slate-800/60 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
            <div className="mb-5 flex gap-1.5 rounded-[14px] bg-slate-50/80 p-1 ring-1 ring-slate-100/50 dark:bg-slate-900/50 dark:ring-slate-700/50">
              {[
              { id: 'fields' as const, label: '字段', icon: LayoutList },
              { id: 'tables' as const, label: '表格', icon: Table2 },
              { id: 'charts' as const, label: '图表', icon: BarChart3 },
              { id: 'images' as const, label: '图片', icon: ImageIcon },
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
                  <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">暂无字段产物</p>
                  <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">该文档未解析出字段信息</p>
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
                  <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">暂无表格产物</p>
                  <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">该文档未解析出表格信息</p>
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
                          <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '表格'}</p>
                          <div className="mt-1 flex items-center gap-2">
                            {item.page > 0 && <span className="rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">第 {item.page} 页</span>}
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
                            下载数据
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => downloadDataframeAsCsv(item.dataframe, `${baseName}-${item.title || 'table'}.csv`)}
                            disabled={item.dataframe.rows.length === 0 && item.dataframe.headers.length === 0}
                            className="inline-flex w-fit items-center gap-1.5 rounded-[10px] bg-emerald-50/80 border border-emerald-100 px-3 py-1.5 text-[12px] font-semibold text-emerald-600 transition hover:bg-emerald-100/80 hover:border-emerald-200 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-400 dark:hover:bg-emerald-500/20"
                          >
                            <Download size={14} />
                            下载数据
                          </button>
                        )}
                        {item.artifactUrl && (
                          <button
                            type="button"
                            onClick={() => handleDownloadRemote(item.artifactUrl, `${baseName}-${item.title || 'table'}-screenshot.png`)}
                            className="inline-flex w-fit items-center gap-1.5 rounded-[10px] bg-slate-50 border border-slate-200/60 px-3 py-1.5 text-[12px] font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-800 dark:bg-slate-800/80 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-700"
                          >
                            <ImageIcon size={14} />
                            下载原图
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
                                        {header || `列 ${idx + 1}`}
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
                            <span>共 {item.dataframe.rowCount} 行 / {item.dataframe.colCount} 列</span>
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
                                {expanded ? '收起' : '展开完整表格'}
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
                <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">暂无图表产物</p>
                <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">该文档未解析出图表信息</p>
              </div>
            ) : (
              chartItems.map((item) => (
                <article key={item.key} className="overflow-hidden rounded-[20px] bg-white border border-slate-100 shadow-[0_2px_10px_rgba(0,0,0,0.02)] transition-colors hover:border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/40 dark:hover:border-slate-600">
                  <div className="p-4">
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '图表'}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-2">
                          {item.page > 0 && <span className="rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">第 {item.page} 页</span>}
                          {item.pointCount > 0 && <span className="rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">{item.pointCount} 个点</span>}
                        </div>
                      </div>
                    </div>

                    {item.summary && (
                      <p className="mb-3 text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">{item.summary}</p>
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
                <p className="text-[14px] font-semibold text-slate-700 dark:text-slate-200">暂无图片产物</p>
                <p className="mt-1 text-[12px] text-slate-400 dark:text-slate-500">该文档未解析出图片信息</p>
              </div>
            ) : (
              imageItems.map((item) => {
                const baseName = toFileBaseName(activeDoc?.file_name || 'document');
                return (
                  <article key={item.key} className="overflow-hidden rounded-[20px] bg-white border border-slate-100 shadow-[0_2px_10px_rgba(0,0,0,0.02)] transition-colors hover:border-slate-200 dark:bg-slate-800/40 dark:border-slate-700/40 dark:hover:border-slate-600">
                    <div className="p-4">
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <p className="text-[15px] font-semibold text-slate-800 dark:text-slate-100">{item.title || '图片'}</p>
                          {item.page > 0 && <span className="mt-1 inline-block rounded-md bg-slate-100/80 border border-slate-200/60 px-2 py-0.5 text-[11px] font-bold text-slate-500 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-400">第 {item.page} 页</span>}
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
                          下载图片
                        </button>
                      )}
                    </div>
                    {item.artifactUrl ? (
                      <div className="bg-slate-50/50 px-4 py-6 border-t border-slate-100 dark:bg-slate-900/50 dark:border-slate-800">
                        <img
                          src={item.artifactUrl}
                          alt={item.title || '图片截图'}
                          className="mx-auto max-h-[240px] rounded-[12px] object-contain shadow-sm border border-slate-200/60 dark:border-slate-700"
                          loading="lazy"
                        />
                      </div>
                    ) : (
                      <p className="bg-slate-50/50 px-4 py-12 border-t border-slate-100 text-center text-[13px] text-slate-500 dark:bg-slate-900/50 dark:border-slate-800 dark:text-slate-500">
                        暂无图片资源
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
      </div>

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

      <button
        type="button"
        onClick={() => setAssistantOpen(true)}
        className={cn(
          'fixed bottom-[calc(env(safe-area-inset-bottom)+5.4rem)] right-4 z-40 flex h-14 w-14 items-center justify-center rounded-full shadow-[0_12px_28px_rgba(15,23,42,0.22)] transition-all active:scale-[0.92] dark:shadow-[0_12px_28px_rgba(2,6,23,0.4)]',
          activeDoc
            ? 'bg-slate-900 text-white hover:bg-black dark:bg-slate-100 dark:text-slate-900'
            : 'bg-slate-700 text-white hover:bg-slate-800 dark:bg-slate-200 dark:text-slate-900',
        )}
        aria-label="打开智能助手"
      >
        <Bot size={24} strokeWidth={2} />
      </button>

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
