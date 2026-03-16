import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertCircle,
  Braces,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  PlayCircle,
  ScanLine,
  Trash2,
  UploadCloud,
  File,
  Settings,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCw,
  RefreshCcw,
  Maximize,
  X,
  Search,
  Plus,
  LocateFixed,
  Bot,
  Sparkles,
  Send,
  HelpCircle,
  FolderOpen,
  FileSpreadsheet,
  FileImage
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import {
  readExtractionDocuments,
  clearExtractionDocuments,
  writeExtractionDocuments,
  type ExtractionDocument,
  type ExtractionEntity,
  type TraceHit,
} from '../lib/extractionStore';
import {
  clearWorkbenchSession,
  readWorkbenchSession,
  writeWorkbenchSession,
  type PersistedExtractionJob,
  type PersistedExtractionJobFile,
  type PersistedWorkbenchFile,
  type WorkbenchSessionSnapshot,
} from '../lib/workbenchSession';
import { LuckysheetPreview, clearLuckysheetPreviewCache, warmLuckysheetPreview } from './LuckysheetPreview';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const stringifyAsciiSafeJson = (value: unknown): string =>
  JSON.stringify(value).replace(/[\u0080-\uFFFF]/g, (char) =>
    `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`
  );

type PdfScrollRequest = {
  page: number;
  nonce: number;
};

const createPdfScrollRequest = (page: number): PdfScrollRequest => ({
  page,
  nonce: Date.now() + Math.random(),
});

type PdfCanvasPreviewProps = {
  src: string;
  scale: number;
  rotation: number;
  scrollRequest?: PdfScrollRequest | null;
  onPageCount?: (count: number) => void;
  onVisiblePageChange?: (page: number) => void;
};

const PdfCanvasPreview: React.FC<PdfCanvasPreviewProps> = ({
  src,
  scale,
  rotation,
  scrollRequest,
  onPageCount,
  onVisiblePageChange,
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const stackRef = useRef<HTMLDivElement>(null);
  const docRef = useRef<any>(null);
  const pageCanvasRefs = useRef<Array<HTMLCanvasElement | null>>([]);
  const pageWrapperRefs = useRef<Array<HTMLDivElement | null>>([]);
  const frameRef = useRef<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [docReadyTick, setDocReadyTick] = useState(0);
  const [pageCount, setPageCount] = useState(0);
  const [stackWidth, setStackWidth] = useState(0);

  const syncVisiblePage = () => {
    const container = scrollRef.current;
    if (!container) return;

    const pageNodes = pageWrapperRefs.current.filter(Boolean) as HTMLDivElement[];
    if (pageNodes.length === 0) return;

    const containerRect = container.getBoundingClientRect();
    const targetLine = containerRect.top + Math.min(container.clientHeight * 0.32, 240);

    let bestPage = 1;
    let bestDistance = Number.POSITIVE_INFINITY;

    pageNodes.forEach((node, index) => {
      const rect = node.getBoundingClientRect();
      const anchor = rect.top + Math.min(rect.height * 0.2, 180);
      const distance = Math.abs(anchor - targetLine);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestPage = index + 1;
      }
    });

    onVisiblePageChange?.(bestPage);
  };

  const scheduleVisiblePageSync = () => {
    if (typeof window === 'undefined') return;
    if (frameRef.current != null) {
      window.cancelAnimationFrame(frameRef.current);
    }
    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null;
      syncVisiblePage();
    });
  };

  useEffect(() => {
    const target = stackRef.current;
    if (!target || typeof ResizeObserver === 'undefined') return;

    const updateWidth = () => {
      setStackWidth(Math.max(0, Math.floor(target.clientWidth)));
    };

    updateWidth();
    const observer = new ResizeObserver(() => updateWidth());
    observer.observe(target);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: any = null;

    const load = async () => {
      setLoading(true);
      setError('');
      setPageCount(0);
      try {
        const pdfjsLib: any = await import('pdfjs-dist');
        if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
          pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
            'pdfjs-dist/build/pdf.worker.min.mjs',
            import.meta.url
          ).toString();
        }
        loadingTask = pdfjsLib.getDocument({
          url: src,
          withCredentials: false,
        });
        const doc = await loadingTask.promise;
        if (cancelled) {
          try {
            await doc.destroy();
          } catch {
            // ignore
          }
          return;
        }
        docRef.current = doc;
        const pages = Math.max(1, Number(doc.numPages || 1));
        setPageCount(pages);
        onPageCount?.(pages);
        setDocReadyTick((prev) => prev + 1);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'PDF 预览加载失败');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          scheduleVisiblePageSync();
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
      try {
        loadingTask?.destroy?.();
      } catch {
        // ignore
      }
      const doc = docRef.current;
      docRef.current = null;
      try {
        doc?.destroy?.();
      } catch {
        // ignore
      }
    };
  }, [onPageCount, src]);

  useEffect(() => {
    pageCanvasRefs.current = pageCanvasRefs.current.slice(0, pageCount);
    pageWrapperRefs.current = pageWrapperRefs.current.slice(0, pageCount);
  }, [pageCount]);

  useEffect(() => {
    let cancelled = false;
    const renderTasks: any[] = [];

    const render = async () => {
      const doc = docRef.current;
      if (!doc || pageCount === 0 || stackWidth <= 0) return;
      try {
        setLoading(true);
        setError('');
        const safeRotation = Number(rotation) || 0;
        const safeScale = Math.max(0.5, scale);
        const pixelRatio = window.devicePixelRatio || 1;

        for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
          if (cancelled) return;
          const canvas = pageCanvasRefs.current[pageNumber - 1];
          if (!canvas) continue;
          const pdfPage = await doc.getPage(pageNumber);
          if (cancelled) return;
          const baseViewport = pdfPage.getViewport({
            scale: 1,
            rotation: safeRotation,
          });
          const fitScale = stackWidth > 0 ? stackWidth / Math.max(1, baseViewport.width) : 1;
          const viewport = pdfPage.getViewport({
            scale: Math.max(0.35, fitScale * safeScale),
            rotation: safeRotation,
          });
          const context = canvas.getContext('2d');
          if (!context) {
          setError('无法初始化 PDF 预览画布');
          return;
        }

        canvas.width = Math.max(1, Math.floor(viewport.width * pixelRatio));
        canvas.height = Math.max(1, Math.floor(viewport.height * pixelRatio));
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        context.setTransform(1, 0, 0, 1, 0, 0);
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);

        const renderTask = pdfPage.render({
          canvasContext: context,
          viewport,
        });
        renderTasks.push(renderTask);
        await renderTask.promise;
        scheduleVisiblePageSync();
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'PDF 预览渲染失败');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void render();

    return () => {
      cancelled = true;
      try {
        renderTasks.forEach((task) => task?.cancel?.());
      } catch {
        // ignore
      }
    };
  }, [docReadyTick, pageCount, rotation, scale, src, stackWidth]);

  useEffect(() => {
    if (!scrollRequest?.page || pageCount === 0 || typeof window === 'undefined') return;

    const targetPage = Math.min(Math.max(1, Math.round(scrollRequest.page)), pageCount);
    const targetNode = pageWrapperRefs.current[targetPage - 1];
    const container = scrollRef.current;
    if (!targetNode || !container) return;

    const raf = window.requestAnimationFrame(() => {
      if (targetPage === 1) {
        container.scrollTo({ top: 0, behavior: 'auto' });
      } else {
        targetNode.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
      scheduleVisiblePageSync();
    });

    return () => window.cancelAnimationFrame(raf);
  }, [pageCount, scrollRequest?.nonce, scrollRequest?.page, src]);

  useEffect(() => {
    scheduleVisiblePageSync();
  }, [pageCount]);

  useEffect(() => {
    return () => {
      if (frameRef.current != null && typeof window !== 'undefined') {
        window.cancelAnimationFrame(frameRef.current);
      }
    };
  }, []);

  return (
    <div className="absolute inset-0 overflow-hidden bg-slate-50/70 dark:bg-slate-900/60">
      <div
        ref={scrollRef}
        onScroll={scheduleVisiblePageSync}
        className="absolute inset-0 overflow-y-auto overflow-x-hidden p-3 sm:p-4"
      >
        <div
          ref={stackRef}
          className="mx-auto flex w-full max-w-[980px] flex-col gap-4"
        >
          {Array.from({ length: pageCount }, (_, index) => index + 1).map((pageNumber) => (
            <div
              key={`${src}-${pageNumber}`}
              ref={(node) => {
                pageWrapperRefs.current[pageNumber - 1] = node;
              }}
              data-page-number={pageNumber}
              className="overflow-hidden rounded-[18px] border border-slate-200/80 bg-white shadow-[0_12px_36px_rgba(15,23,42,0.08)] dark:border-slate-700 dark:bg-slate-900"
            >
              <canvas
                ref={(node) => {
                  pageCanvasRefs.current[pageNumber - 1] = node;
                }}
                className="mx-auto block h-auto max-w-full bg-white dark:bg-slate-900"
              />
            </div>
          ))}
        </div>
      </div>
      {loading && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/30 dark:bg-slate-900/30">
          <div className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white/90 px-3 py-1.5 text-xs text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-300">
            <Loader2 size={14} className="animate-spin" />
            正在加载文档预览...
          </div>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-white/80 p-4 text-center dark:bg-slate-900/80">
          <p className="max-w-[420px] text-xs text-slate-600 dark:text-slate-300">{error}</p>
          <a
            href={src}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
          >
            <ExternalLink size={12} />
            在新窗口打开文档
          </a>
        </div>
      )}
    </div>
  );
};

type DocumentResult = ExtractionDocument;

type ExtractResponse = {
  documents: DocumentResult[];
};

type SummarizeResponse = {
  summary: string;
};

type TraceLocateResponse = {
  hit_count: number;
  truncated: boolean;
  hits: TraceHit[];
};

type TraceDisplayKind = 'field' | 'table' | 'image' | 'other';

type AssistantQueryResponse = {
  ok: boolean;
  answer: string;
  summary_used: string;
  matched_fields: Array<{
    field_name: string;
    label: string;
    value: unknown;
    confidence: number;
    source_ref_id?: string | null;
    page?: number | null;
    bbox?: number[];
  }>;
  matched_trace_hits: TraceHit[];
  persisted: boolean;
  persisted_rows: number;
  warnings: string[];
};

type AssistantCitation = {
  citation_type: string;
  title: string;
  page?: number | null;
  ref_id?: string | null;
  object_id: string;
  snippet: string;
  payload: Record<string, unknown>;
};

type AssistantObjectLock = {
  lock_type: string;
  object_id: string;
  label: string;
  page?: number | null;
  ref_id?: string | null;
  table_id?: string | null;
  row_index?: number | null;
  source_row_index?: number | null;
  metadata?: Record<string, unknown>;
};

type AssistantActionPreview = {
  action_id: string;
  action_type: string;
  title: string;
  description: string;
  target: string;
  requires_confirmation: boolean;
  payload: Record<string, unknown>;
};

type AssistantSessionMessagePayload = {
  message_id: string;
  role: string;
  message_type: string;
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type AssistantSessionResponse = {
  session_id: string;
  summary_used: string;
  current_object_lock?: AssistantObjectLock | null;
  messages: AssistantSessionMessagePayload[];
};

type FieldItem = {
  key: string;
  label: string;
  valueText: string;
  confidence: number;
  refId?: string | null;
  bbox: number[];
  pageNumber: number | null;
};

type AssistantDialogMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  messageType?: 'user_message' | 'assistant_text' | 'tool_status' | 'action_preview' | 'system_notice';
  citations?: AssistantCitation[];
  actionPreview?: AssistantActionPreview | null;
  status?: 'streaming' | 'done' | 'error';
  payload?: Record<string, unknown>;
};

const DEFAULT_SCHEMA = {
  auto_infer: true,
  prefer_llm: true,
  max_auto_fields: 8,
};

const ASSISTANT_SESSION_STORAGE_KEY = 'module2_assistant_session_map_v1';

const readAssistantSessionMap = (): Record<string, string> => {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(ASSISTANT_SESSION_STORAGE_KEY) || '{}';
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed as Record<string, string> : {};
  } catch {
    return {};
  }
};

const writeAssistantSessionMap = (value: Record<string, string>) => {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(ASSISTANT_SESSION_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // ignore
  }
};



type OfficePreviewState = {
  status: 'idle' | 'queued' | 'running' | 'completed' | 'failed';
  jobId?: string;
  pdfUrl?: string;
  error?: string;
};

type ExtractionJobFileState = PersistedExtractionJobFile;

type ExtractionJobState = PersistedExtractionJob;

const ALLOWED_EXTENSIONS = new Set(['pdf', 'doc', 'docx', 'xlsx', 'txt', 'md', 'png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff']);
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff']);

const isAllowedFile = (file: File) => {
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  return ALLOWED_EXTENSIONS.has(ext);
};

const fileExt = (name: string) => name.split('.').pop()?.toLowerCase() || '';
const fileIdentityKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;
const toPersistedWorkbenchFile = (file: File, patch?: Partial<PersistedWorkbenchFile>): PersistedWorkbenchFile => ({
  key: fileIdentityKey(file),
  name: file.name,
  size: file.size,
  lastModified: file.lastModified,
  ext: fileExt(file.name),
  artifactUrl: patch?.artifactUrl,
  artifactPath: patch?.artifactPath,
});

const toArtifactRouteFromPath = (artifactPathRaw: string): string => {
  const normalized = String(artifactPathRaw || '').trim().replace(/\\/g, '/');
  if (!normalized) return '';
  if (normalized.startsWith('/extract/')) return normalized;
  const encoded = normalized
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  return encoded ? `/extract/artifact/${encoded}` : '';
};

const toRelativeExtractPath = (rawUrl: string): string => {
  const value = String(rawUrl || '').trim();
  if (!value) return '';
  if (value.startsWith('/extract/')) return value;
  if (!/^https?:\/\//i.test(value)) return '';
  try {
    const parsed = new URL(value);
    return parsed.pathname.startsWith('/extract/')
      ? `${parsed.pathname}${parsed.search || ''}${parsed.hash || ''}`
      : '';
  } catch {
    return '';
  }
};

const hydrateFileFromArtifact = async (item: PersistedWorkbenchFile): Promise<File | null> => {
  const artifactUrl = String(item.artifactUrl || '').trim();
  const artifactPath = String(item.artifactPath || '').trim();
  if (!artifactUrl && !artifactPath) return null;
  const relativeUrl = toRelativeExtractPath(artifactUrl);
  const routeFromPath = toArtifactRouteFromPath(artifactPath);
  const candidates = Array.from(
    new Set(
      [
        relativeUrl,
        routeFromPath,
        artifactUrl,
        routeFromPath ? toAbsoluteExtractUrl(routeFromPath, '') : '',
        /^https?:\/\//i.test(artifactUrl) ? artifactUrl : toAbsoluteExtractUrl(artifactUrl, ''),
      ].filter(Boolean),
    ),
  );
  let response: Response | null = null;
  for (const candidate of candidates) {
    try {
      const fetched = await fetch(candidate);
      if (fetched.ok) {
        response = fetched;
        break;
      }
    } catch {
      continue;
    }
  }
  if (!response) {
    throw new Error(`无法恢复文件预览：${item.name}`);
  }
  const blob = await response.blob();
  const FileCtor = typeof window !== 'undefined' && typeof window.File === 'function'
    ? window.File
    : globalThis.File;
  if (typeof FileCtor !== 'function') {
    throw new Error('当前环境不支持文件恢复');
  }
  return new FileCtor([blob], item.name, {
    type: blob.type || 'application/octet-stream',
    lastModified: Number(item.lastModified || Date.now()),
  });
};

const toSessionSnapshot = (
  selectedFiles: File[],
  activeDocIndex: number,
  officePreviewMap: Record<string, OfficePreviewState>,
  extractionJob: ExtractionJobState | null,
  artifactMap: Record<string, { artifactUrl?: string; artifactPath?: string }>,
  fallbackSelectedFiles: PersistedWorkbenchFile[] = [],
): WorkbenchSessionSnapshot => ({
  version: 1,
  activeDocIndex,
  selectedFiles: selectedFiles.length > 0
    ? selectedFiles.map((file) => toPersistedWorkbenchFile(file, artifactMap[fileIdentityKey(file)]))
    : fallbackSelectedFiles.map((item) => ({
        ...item,
        artifactUrl: artifactMap[item.key]?.artifactUrl ?? item.artifactUrl,
        artifactPath: artifactMap[item.key]?.artifactPath ?? item.artifactPath,
      })),
  officePreviewMap,
  extractionJob,
});

const clampProgressPercent = (ratio: number) =>
  Math.max(0, Math.min(100, Math.round(Math.max(0, Math.min(1, Number(ratio || 0))) * 100)));

let spreadsheetWarmupIdleHandle: number | null = null;
const spreadsheetWarmupQueue: File[] = [];
const spreadsheetWarmupKeys = new Set<string>();

const runSpreadsheetWarmupQueue = () => {
  spreadsheetWarmupIdleHandle = null;
  const nextFile = spreadsheetWarmupQueue.shift();
  if (!nextFile) return;

  const key = fileIdentityKey(nextFile);
  spreadsheetWarmupKeys.delete(key);

  void warmLuckysheetPreview(nextFile)
    .catch(() => undefined)
    .finally(() => {
      if (spreadsheetWarmupQueue.length === 0) return;
      const win = window as Window & {
        requestIdleCallback?: (callback: IdleRequestCallback, options?: IdleRequestOptions) => number;
      };
      if (typeof win.requestIdleCallback === 'function') {
        spreadsheetWarmupIdleHandle = win.requestIdleCallback(() => runSpreadsheetWarmupQueue(), { timeout: 1200 });
        return;
      }
      spreadsheetWarmupIdleHandle = window.setTimeout(() => runSpreadsheetWarmupQueue(), 180);
    });
};

const clearSpreadsheetPreviewWarmupQueue = () => {
  spreadsheetWarmupQueue.length = 0;
  spreadsheetWarmupKeys.clear();
  if (spreadsheetWarmupIdleHandle == null || typeof window === 'undefined') return;
  const win = window as Window & {
    cancelIdleCallback?: (handle: number) => void;
  };
  if (typeof win.cancelIdleCallback === 'function') {
    win.cancelIdleCallback(spreadsheetWarmupIdleHandle);
  } else {
    window.clearTimeout(spreadsheetWarmupIdleHandle);
  }
  spreadsheetWarmupIdleHandle = null;
};

const scheduleSpreadsheetPreviewWarmup = (file: File) => {
  if (typeof window === 'undefined' || fileExt(file.name) !== 'xlsx') return;
  const key = fileIdentityKey(file);
  if (spreadsheetWarmupKeys.has(key)) return;

  spreadsheetWarmupKeys.add(key);
  spreadsheetWarmupQueue.push(file);
  if (spreadsheetWarmupIdleHandle != null) return;

  const win = window as Window & {
    requestIdleCallback?: (callback: IdleRequestCallback, options?: IdleRequestOptions) => number;
  };
  if (typeof win.requestIdleCallback === 'function') {
    spreadsheetWarmupIdleHandle = win.requestIdleCallback(() => runSpreadsheetWarmupQueue(), { timeout: 1200 });
    return;
  }
  spreadsheetWarmupIdleHandle = window.setTimeout(() => runSpreadsheetWarmupQueue(), 180);
};

const previewFileNameFromKey = (key: string): string => {
  const raw = String(key || '');
  const idx = raw.indexOf(':');
  return (idx >= 0 ? raw.slice(0, idx) : raw).trim().toLowerCase();
};

const pickOfficePreviewByFileName = (
  fileName: string,
  previewMap: Record<string, OfficePreviewState>,
): OfficePreviewState | null => {
  const target = String(fileName || '').trim().toLowerCase();
  if (!target) return null;

  let fallback: OfficePreviewState | null = null;
  for (const [key, state] of Object.entries(previewMap || {})) {
    if (!state) continue;
    if (previewFileNameFromKey(key) !== target) continue;
    if (!fallback) fallback = state;
    if (state.status === 'completed' && String(state.pdfUrl || '').trim()) {
      return state;
    }
  }
  return fallback;
};

const pickExtractionJobFileState = (
  extractionJob: ExtractionJobState | null,
  file: File,
  index: number,
): ExtractionJobFileState | null => {
  if (!extractionJob || !Array.isArray(extractionJob.files) || extractionJob.files.length === 0) return null;
  const normalizedName = String(file.name || '').trim().toLowerCase();
  const byIndex = extractionJob.files[index] || null;
  if (byIndex && String(byIndex.file_name || '').trim().toLowerCase() === normalizedName) {
    return byIndex;
  }
  const matched = extractionJob.files.filter(
    (item) => String(item.file_name || '').trim().toLowerCase() === normalizedName,
  );
  if (matched.length === 1) return matched[0];
  if (byIndex) return byIndex;
  return matched[0] || null;
};

type ExtractFetchResult = {
  response: Response;
  usedBase: string;
};

const getViteExtractBase = (): string => {
  try {
    const envObj = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
    return String(envObj?.VITE_MODULE2_API_BASE || envObj?.VITE_EXTRACT_API_BASE || '').trim();
  } catch {
    return '';
  }
};

const trimTrailingSlash = (value: string) => String(value || '').replace(/\/+$/, '');

const normalizeExtractBase = (raw: string): string => {
  const base = trimTrailingSlash(String(raw || '').trim());
  if (!base) return '';
  return base.endsWith('/extract') ? base.slice(0, -8) : base;
};

const getLocalStorageExtractBase = (): string => {
  if (typeof window === 'undefined') return '';
  try {
    return String(window.localStorage.getItem('module2_api_base_override') || '').trim();
  } catch {
    return '';
  }
};

const buildExtractBaseCandidates = (preferredBase = ''): string[] => {
  const out: string[] = [];
  const push = (raw: string) => {
    const base = normalizeExtractBase(raw);
    if (!base) return;
    if (!out.includes(base)) out.push(base);
  };

  push(preferredBase);
  push(getViteExtractBase());
  push(getLocalStorageExtractBase());

  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    const port = window.location.port;
    if (hostname) {
      if (port !== '8000') push(`${protocol}//${hostname}:8000`);
      push(`${protocol}//127.0.0.1:8000`);
      push(`${protocol}//localhost:8000`);
    }
  }

  return out;
};

const joinExtractUrl = (base: string, path: string): string => {
  const normalizedPath = String(path || '').startsWith('/') ? String(path || '') : `/${String(path || '')}`;
  const normalizedBase = normalizeExtractBase(base);
  return normalizedBase ? `${normalizedBase}${normalizedPath}` : normalizedPath;
};

const resolveExtractBase = (preferredBase = ''): string => {
  const normalizedPreferred = normalizeExtractBase(preferredBase);
  if (normalizedPreferred) return normalizedPreferred;
  const candidates = buildExtractBaseCandidates(preferredBase);
  return candidates[0] || '';
};

const toAbsoluteExtractUrl = (rawUrl: string, base: string): string => {
  const value = String(rawUrl || '').trim();
  if (!value) return '';
  if (/^https?:\/\//i.test(value)) return value;
  if (!value.startsWith('/')) return value;
  const normalizedBase = resolveExtractBase(base);
  return normalizedBase ? `${normalizedBase}${value}` : value;
};

const parseFetchErrorMessage = (error: unknown): string => {
  if (!(error instanceof Error)) return '文档预览转换失败';
  const msg = String(error.message || '').trim();
  if (!msg) return '文档预览转换失败';
  const lowered = msg.toLowerCase();
  if (lowered.includes('failed to fetch') || lowered.includes('networkerror') || lowered.includes('load failed')) {
    return '无法连接文档解析后端，请确认后端服务已启动（默认 8000 端口）或检查后端地址配置。';
  }
  return msg;
};

const readResponseErrorMessage = async (response: Response): Promise<string> => {
  let text = '';
  try {
    text = await response.text();
  } catch {
    text = '';
  }
  const trimmed = String(text || '').trim();
  if (!trimmed) return `状态码 ${response.status}`;
  try {
    const parsed = JSON.parse(trimmed);
    const detail = parsed?.detail || parsed?.message || parsed?.error;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
  } catch {
    // non-json payload
  }
  return trimmed.length > 1800 ? `${trimmed.slice(0, 1800)}...` : trimmed;
};

const fetchExtractWithFallback = async (
  path: string,
  init?: RequestInit,
  preferredBase = '',
): Promise<ExtractFetchResult> => {
  const tried: string[] = [];
  let lastError = '';
  const configuredCandidates = [
    normalizeExtractBase(preferredBase),
    normalizeExtractBase(getViteExtractBase()),
    normalizeExtractBase(getLocalStorageExtractBase()),
  ].filter(Boolean);
  const candidates =
    configuredCandidates.length > 0
      ? [...buildExtractBaseCandidates(preferredBase), '']
      : ['', ...buildExtractBaseCandidates(preferredBase)];

  for (const base of candidates) {
    if (tried.includes(base)) continue;
    tried.push(base);
    const url = joinExtractUrl(base, path);
    try {
      const response = await fetch(url, init);
      if (response.ok) {
        return { response, usedBase: base };
      }

      const msg = await readResponseErrorMessage(response);
      const retryable = response.status >= 500 || response.status === 404;
      if (!retryable) {
        throw new Error(msg);
      }
      lastError = msg || `状态码 ${response.status}`;
    } catch (error) {
      lastError = parseFetchErrorMessage(error);
    }
  }

  throw new Error(lastError || '文档解析后端请求失败。');
};

const toPageNumber = (bbox: number[]) => {
  if (bbox.length !== 5) return null;
  const page = Number(bbox[0]);
  if (!Number.isFinite(page) || page < 1) return null;
  return Math.round(page);
};

const toPercentBox = (bbox: number[]) => {
  if (bbox.length !== 5) {
    return { x: 0, y: 0, w: 0, h: 0 };
  }

  const [, x, y, w, h] = bbox;
  // Heuristic normalization for different coordinate systems
  const maxVal = Math.max(x + w, y + h);

  if (maxVal <= 1.5) {
    // Normalized 0-1 coordinates
    return {
      x: x * 100,
      y: y * 100,
      w: w * 100,
      h: h * 100,
    };
  }

  if (maxVal <= 100) {
    // Already percent?
    return { x, y, w, h };
  }

  // A4 standard points (approx)
  return {
    x: (x / 595) * 100,
    y: (y / 842) * 100,
    w: (w / 595) * 100,
    h: (h / 842) * 100,
  };
};

const hasMeaningfulBox = (bbox: number[]) => {
  if (!Array.isArray(bbox) || bbox.length !== 5) return false;
  const [, x, y, w, h] = bbox.map((n) => Number(n));
  if (![x, y, w, h].every((n) => Number.isFinite(n))) return false;
  if (w <= 0 || h <= 0) return false;
  // Avoid fake full-page placeholders: [1, 0, 0, 1, 1]
  if (x <= 0.0001 && y <= 0.0001 && w >= 0.995 && h >= 0.995) return false;
  return true;
};

const toFieldLabel = (name: string) =>
  (
    {
      contract_amount: '合同金额',
      start_date: '开始日期',
      end_date: '结束日期',
      tax_rate: '税率',
      region: '地区',
      invoice_number: '发票号码',
      invoice_date: '开票日期',
      buyer_name: '购买方名称',
      seller_name: '销售方名称',
      total_amount: '合计金额',
    } as Record<string, string>
  )[name] || name;

const toTraceHits = (doc: DocumentResult | null, fieldKey?: string | null): TraceHit[] => {
  if (!doc || !Array.isArray(doc.trace_hits)) return [];
  const key = (fieldKey || '').trim().toLowerCase();
  const out = doc.trace_hits.filter((hit) => {
    if (!hit || typeof hit !== 'object') return false;
    const objectType = String(hit.object_type || '');
    if (!objectType) return false;
    if (!key) return true;
    const objectId = String(hit.object_id || '').toLowerCase();
    const snippet = String(hit.snippet || '').toLowerCase();
    return objectId === key || snippet.includes(`${key}:`);
  });
  return out.sort((a, b) => Number(b.confidence || 0) - Number(a.confidence || 0));
};

const getTraceLocator = (hit: TraceHit): Record<string, unknown> =>
  hit.locator && typeof hit.locator === 'object' ? (hit.locator as Record<string, unknown>) : {};

const isTableLikeFigureTrace = (hit: TraceHit): boolean => {
  const locator = getTraceLocator(hit);
  const figureType = String(locator.figure_type || '').trim().toLowerCase();
  if (figureType === 'table' || figureType === 'spreadsheet') return true;

  const contentModes = Array.isArray(locator.content_modes)
    ? locator.content_modes.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean)
    : [];

  const dataframe = locator.dataframe && typeof locator.dataframe === 'object'
    ? (locator.dataframe as Record<string, unknown>)
    : {};
  const hasHeaders = Array.isArray(dataframe.headers)
    && dataframe.headers.some((cell) => String(cell || '').trim().length > 0);
  const hasRows = Array.isArray(dataframe.rows)
    && dataframe.rows.some(
      (row) => Array.isArray(row) && row.some((cell) => String(cell || '').trim().length > 0)
    );

  return (hasHeaders || hasRows) && !contentModes.includes('visual') && !contentModes.includes('topology');
};

const getTraceDisplayKind = (hit: TraceHit): TraceDisplayKind => {
  const objectType = String(hit.object_type || '').trim().toLowerCase();
  if (objectType === 'field') return 'field';
  if (objectType === 'table') return 'table';
  if (objectType === 'figure') return isTableLikeFigureTrace(hit) ? 'table' : 'image';
  return 'other';
};

const getTraceDisplayLabel = (hit: TraceHit): string => {
  const kind = getTraceDisplayKind(hit);
  if (kind === 'field') return '字段';
  if (kind === 'table') return '表格';
  if (kind === 'image') return '图片';
  return '其他';
};

const toTraceHitKey = (hit: TraceHit, idx: number) =>
  `${String(hit.object_type || 'trace')}:${String(hit.object_id || '')}:${String(hit.ref_id || '')}:${idx}`;

const toTracePage = (hit: TraceHit): number => {
  const pageRaw = Number(hit.page || 0);
  if (Number.isFinite(pageRaw) && pageRaw > 0) return Math.round(pageRaw);
  const bbox = Array.isArray(hit.bbox) ? hit.bbox : [];
  if (bbox.length === 5) {
    const p = Number(bbox[0] || 0);
    if (Number.isFinite(p) && p > 0) return Math.round(p);
  }
  const locator = (hit.locator || {}) as Record<string, unknown>;
  const locatorPage = Number(locator.page || 0);
  return Number.isFinite(locatorPage) && locatorPage > 0 ? Math.round(locatorPage) : 0;
};

const resolveArtifactUrl = (hit: TraceHit): string => {
  const direct = String(hit.artifact_url || '').trim();
  if (direct) return direct;
  const pathRaw = String(hit.artifact_path || '').trim();
  if (!pathRaw) return '';
  const normalized = pathRaw.replace(/\\/g, '/');
  const encoded = normalized
    .split('/')
    .filter(Boolean)
    .map((seg) => encodeURIComponent(seg))
    .join('/');
  return encoded ? `/extract/artifact/${encoded}` : '';
};

export const DeepReadWorkbench: React.FC<{ isSidebarCollapsed?: boolean }> = ({ isSidebarCollapsed = false }) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [schemaText, setSchemaText] = useState<string>(JSON.stringify(DEFAULT_SCHEMA, null, 2));
  const [documents, setDocuments] = useState<DocumentResult[]>([]);
  const [activeDocIndex, setActiveDocIndex] = useState(0);
  const [activeFieldKey, setActiveFieldKey] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [extractionJob, setExtractionJob] = useState<ExtractionJobState | null>(null);
  const [selectedFileArtifacts, setSelectedFileArtifacts] = useState<Record<string, { artifactUrl?: string; artifactPath?: string }>>({});
  const [sessionHydrated, setSessionHydrated] = useState(false);
  const [sessionRestorePending, setSessionRestorePending] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [infoMessage, setInfoMessage] = useState("每批最多上传 5 个文件。");
  const [activeSummaryText, setActiveSummaryText] = useState('');
  const [activeSummaryLoading, setActiveSummaryLoading] = useState(false);
  const [summaryDocName, setSummaryDocName] = useState('');
  const [traceHits, setTraceHits] = useState<TraceHit[]>([]);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState('');
  const [assistantStatus, setAssistantStatus] = useState<'idle' | 'confirmed' | 'rolled_back'>('idle');
  const [assistantMessage, setAssistantMessage] = useState("等待生成可执行建议。");
  const [assistantInput, setAssistantInput] = useState('');
  const [assistantQueryLoading, setAssistantQueryLoading] = useState(false);
  const [assistantAnswer, setAssistantAnswer] = useState('');
  const [assistantWarnings, setAssistantWarnings] = useState<string[]>([]);
  const [assistantDialog, setAssistantDialog] = useState<AssistantDialogMessage[]>([]);
  const [assistantSessionId, setAssistantSessionId] = useState('');
  const [assistantCurrentLock, setAssistantCurrentLock] = useState<AssistantObjectLock | null>(null);
  const [smartUnitTab, setSmartUnitTab] = useState<'results' | 'assistant'>('results');
  const [assistantTabUnread, setAssistantTabUnread] = useState(false);
  const [resultsTabUnread, setResultsTabUnread] = useState(false);
  const [showAssistantHelp, setShowAssistantHelp] = useState(false);
  const [showSchema, setShowSchema] = useState(false); // UI Toggle
  const [isPreviewFocused, setIsPreviewFocused] = useState(false);
  const [isUploaderDragOver, setIsUploaderDragOver] = useState(false);
  const [resultSearchQuery, setResultSearchQuery] = useState('');
  
  // Viewport Controls
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [activeTraceKey, setActiveTraceKey] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const assistantInputRef = useRef<HTMLTextAreaElement>(null);
  const textPreviewRef = useRef<HTMLDivElement>(null);
  const assistantDialogRef = useRef<HTMLDivElement>(null);
  const summaryRequestSeqRef = useRef(0);
  const traceRequestSeqRef = useRef(0);
  const officePreviewPollRef = useRef<Record<string, string>>({});
  const officePreviewApiBaseRef = useRef<Record<string, string>>({});
  const extractionJobPollRef = useRef<string>('');
  const extractionJobApiBaseRef = useRef<string>('');
  const persistedSelectedFilesRef = useRef<PersistedWorkbenchFile[]>([]);
  const assistantAbortRef = useRef<AbortController | null>(null);
  const assistantActivityRef = useRef('');
  const resultsActivityRef = useRef('');

  useEffect(() => () => {
    clearSpreadsheetPreviewWarmupQueue();
  }, []);

  const activeDoc = documents[activeDocIndex] || null;
  const activeSourceFile = useMemo(() => {
    // Priority 1: Match activeDoc if it exists
    if (activeDoc && selectedFiles.length > 0) {
      const targetName = String(activeDoc.file_name || '').trim().toLowerCase();
      const nameMatched = targetName
        ? selectedFiles.filter((file) => file.name.toLowerCase() === targetName)
        : [];
      if (nameMatched.length === 1) return nameMatched[0];
      const byIndex = selectedFiles[activeDocIndex] || null;
      if (nameMatched.length > 1) {
        if (byIndex && byIndex.name.toLowerCase() === targetName) return byIndex;
        return nameMatched[0] || byIndex;
      }
      const exact = selectedFiles.find((file) => file.name === activeDoc.file_name);
      if (exact) return exact;
      if (byIndex && fileExt(byIndex.name) === fileExt(activeDoc.file_name)) return byIndex;

      return byIndex;
    }

    // Priority 2: Fallback to selectedFiles based on index (Pre-extraction preview)
    if (!activeDoc && selectedFiles.length > 0) {
      return selectedFiles[activeDocIndex] || selectedFiles[0];
    }

    return null;
  }, [activeDoc, activeDocIndex, selectedFiles]);
  const activeExt = activeSourceFile ? fileExt(activeSourceFile.name) : (activeDoc ? fileExt(activeDoc.file_name) : '');
  const activeDisplayName = activeDoc?.file_name || activeSourceFile?.name || '当前文档';
  const activeSelectionCount = Math.max(documents.length, selectedFiles.length);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string>('');
  const [officePreviewMap, setOfficePreviewMap] = useState<Record<string, OfficePreviewState>>({});
  const [pdfViewportPage, setPdfViewportPage] = useState(1);
  const [pdfScrollRequest, setPdfScrollRequest] = useState<PdfScrollRequest | null>(null);
  const [pdfPreviewPageCount, setPdfPreviewPageCount] = useState(1);
  const assistantActionable = useMemo(
    () => Boolean(activeDoc && (((activeDoc.errors?.length || 0) > 0) || ((activeDoc.soft_warnings?.length || 0) > 0))),
    [activeDoc]
  );
  const showLeftPanel = !isPreviewFocused;
  const activeOfficePreview = useMemo(() => {
    const fileNameHint = String(activeSourceFile?.name || activeDoc?.file_name || '').trim();
    if (!fileNameHint) return null;

    const byIdentity = activeSourceFile ? (officePreviewMap[fileIdentityKey(activeSourceFile)] || null) : null;
    const byName = pickOfficePreviewByFileName(fileNameHint, officePreviewMap);

    // Prefer a completed preview with url whenever available.
    if (byIdentity && byIdentity.status === 'completed' && String(byIdentity.pdfUrl || '').trim()) {
      return byIdentity;
    }
    if (byName && byName.status === 'completed' && String(byName.pdfUrl || '').trim()) {
      return byName;
    }
    return byIdentity || byName || null;
  }, [activeDoc?.file_name, activeSourceFile, officePreviewMap]);
  const activeDocPreviewPdfUrl = useMemo(() => {
    const val = String(
      activeDoc?.diagnostics?.office_pdf_preview_url
      || activeDoc?.diagnostics?.pdf_preview_url
      || ''
    ).trim();
    return val || '';
  }, [activeDoc?.diagnostics]);
  const activeConvertedPdfUrl = useMemo(() => {
    const fromUpload = String(activeOfficePreview?.pdfUrl || '').trim();
    if (fromUpload) return fromUpload;
    return activeDocPreviewPdfUrl;
  }, [activeOfficePreview?.pdfUrl, activeDocPreviewPdfUrl]);
  const activeRenderExt = useMemo(() => {
    if ((activeExt === 'doc' || activeExt === 'docx') && activeConvertedPdfUrl) return 'pdf';
    return activeExt;
  }, [activeExt, activeConvertedPdfUrl]);
  const activePreviewIdentity = useMemo(() => {
    if (activeDoc?.file_hash) return `doc:${activeDoc.file_hash}`;
    if (activeSourceFile) return `upload:${fileIdentityKey(activeSourceFile)}`;
    if (activeDoc?.file_name) return `name:${activeDoc.file_name}`;
    if (previewUrl) return `preview:${previewUrl}`;
    return '';
  }, [activeDoc?.file_hash, activeDoc?.file_name, activeSourceFile, previewUrl]);
  const hasPreviewContent = Boolean(activeSourceFile || previewUrl);
  const canClearWorkbenchData = useMemo(
    () =>
      Boolean(
        selectedFiles.length > 0
        || documents.length > 0
        || previewUrl
        || previewText
        || activeSummaryText
        || traceHits.length > 0
        || assistantDialog.length > 0
        || assistantInput
        || assistantAnswer
        || resultSearchQuery
        || Object.keys(officePreviewMap).length > 0
      ),
    [
      activeSummaryText,
      assistantAnswer,
      assistantDialog.length,
      assistantInput,
      documents.length,
      officePreviewMap,
      previewText,
      previewUrl,
      resultSearchQuery,
      selectedFiles.length,
      traceHits.length,
    ]
  );
  const recentUserInstructions = useMemo(() => {
    const pool = assistantDialog
      .filter((msg) => msg.role === 'user')
      .map((msg) => msg.content.trim())
      .filter(Boolean)
      .reverse();
    return Array.from(new Set(pool)).slice(0, 6);
  }, [assistantDialog]);

  const persistAssistantSessionForFile = (fileHash: string, sessionId: string) => {
    const fileKey = String(fileHash || '').trim();
    const sessionKey = String(sessionId || '').trim();
    if (!fileKey || !sessionKey) return;
    const current = readAssistantSessionMap();
    current[fileKey] = sessionKey;
    writeAssistantSessionMap(current);
  };

  const clearAssistantSessionForFile = (fileHash: string) => {
    const fileKey = String(fileHash || '').trim();
    if (!fileKey) return;
    const current = readAssistantSessionMap();
    if (!(fileKey in current)) return;
    delete current[fileKey];
    writeAssistantSessionMap(current);
  };

  const toAssistantDialogMessage = (message: AssistantSessionMessagePayload): AssistantDialogMessage => {
    const role = String(message.role || '').trim().toLowerCase() === 'user' ? 'user' : 'assistant';
    const payload = message.payload && typeof message.payload === 'object' ? message.payload : {};
    const messageTypeRaw = String(message.message_type || '').trim();
    const normalizedType: AssistantDialogMessage['messageType'] =
      messageTypeRaw === 'tool_status' || messageTypeRaw === 'action_preview' || messageTypeRaw === 'system_notice'
        ? messageTypeRaw
        : role === 'user'
          ? 'user_message'
          : 'assistant_text';
    const citations = Array.isArray((payload as Record<string, unknown>).citations)
      ? ((payload as Record<string, unknown>).citations as AssistantCitation[])
      : [];
    const actionPreviewRaw = (payload as Record<string, unknown>).action_preview;
    const actionPreview = actionPreviewRaw && typeof actionPreviewRaw === 'object'
      ? actionPreviewRaw as AssistantActionPreview
      : null;
    return {
      id: String(message.message_id || `assistant-${Date.now()}`),
      role,
      content: String(message.content || ''),
      messageType: normalizedType,
      citations,
      actionPreview,
      status: 'done',
      payload: payload as Record<string, unknown>,
    };
  };

  const updateAssistantDialogMessage = (
    messageId: string,
    updater: (current: AssistantDialogMessage) => AssistantDialogMessage
  ) => {
    const targetId = String(messageId || '').trim();
    if (!targetId) return;
    setAssistantDialog((prev) =>
      prev.map((item) => (item.id === targetId ? updater(item) : item))
    );
  };

  const applyAssistantInstruction = (instruction: string) => {
    const text = String(instruction || '').trim();
    if (!text) return;
    setAssistantInput(text);
    requestAnimationFrame(() => {
      assistantInputRef.current?.focus();
      const len = text.length;
      assistantInputRef.current?.setSelectionRange(len, len);
    });
  };

  useEffect(() => {
    return () => {
      officePreviewPollRef.current = {};
      officePreviewApiBaseRef.current = {};
      extractionJobPollRef.current = '';
      extractionJobApiBaseRef.current = '';
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key.toLowerCase() !== 'o') return;
      event.preventDefault();
      fileInputRef.current?.click();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    let active = true;
    const cached = readExtractionDocuments();
    const session = readWorkbenchSession();
    if (cached.length > 0) {
      setDocuments(cached);
      setInfoMessage(`已加载 ${cached.length} 条本地缓存抽取结果。`);
    }
    if (!session) {
      persistedSelectedFilesRef.current = [];
      setSessionRestorePending(false);
      setSessionHydrated(true);
      return () => {
        active = false;
      };
    }

    setActiveDocIndex(Math.max(0, Number(session.activeDocIndex || 0)));
    setOfficePreviewMap(session.officePreviewMap || {});
    setExtractionJob(session.extractionJob || null);
    setIsProcessing(Boolean(session.extractionJob && !session.extractionJob.terminal));
    persistedSelectedFilesRef.current = Array.isArray(session.selectedFiles) ? session.selectedFiles : [];
    const artifactMap = Object.fromEntries(
      (session.selectedFiles || []).map((item) => [
        item.key,
        {
          artifactUrl: item.artifactUrl,
          artifactPath: item.artifactPath,
        },
      ]),
    );
    setSelectedFileArtifacts(artifactMap);

    const restorable = (session.selectedFiles || []).filter((item) =>
      String(item.artifactUrl || item.artifactPath || '').trim()
    );
    if (restorable.length === 0) {
      setSessionRestorePending(false);
      setSessionHydrated(true);
      return () => {
        active = false;
      };
    }

    setSessionRestorePending(true);
    setInfoMessage(`正在恢复 ${restorable.length} 份文件预览与任务状态...`);
    Promise.all(
      restorable.map(async (item) => {
        try {
          return await hydrateFileFromArtifact(item);
        } catch {
          return null;
        }
      }),
    ).then((restored) => {
      if (!active) return;
      const files = restored.filter(Boolean) as File[];
      if (files.length > 0) {
        setSelectedFiles(files);
        setInfoMessage(`已恢复 ${files.length} 份文件预览与任务状态。`);
      }
    }).finally(() => {
      if (!active) return;
      setSessionRestorePending(false);
      setSessionHydrated(true);
    });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (activeSelectionCount === 0) {
      if (activeDocIndex !== 0) {
        setActiveDocIndex(0);
      }
      return;
    }
    if (activeDocIndex > activeSelectionCount - 1) {
      setActiveDocIndex(activeSelectionCount - 1);
    }
  }, [activeDocIndex, activeSelectionCount]);

  useEffect(() => {
    if (!sessionHydrated || sessionRestorePending) return;
    const hasSessionState =
      selectedFiles.length > 0
      || Object.keys(officePreviewMap).length > 0
      || Boolean(extractionJob);
    if (!hasSessionState) {
      persistedSelectedFilesRef.current = [];
      clearWorkbenchSession();
      return;
    }
    const snapshot = toSessionSnapshot(
      selectedFiles,
      activeDocIndex,
      officePreviewMap,
      extractionJob,
      selectedFileArtifacts,
      persistedSelectedFilesRef.current,
    );
    persistedSelectedFilesRef.current = snapshot.selectedFiles;
    writeWorkbenchSession(snapshot);
  }, [activeDocIndex, extractionJob, officePreviewMap, selectedFileArtifacts, selectedFiles, sessionHydrated, sessionRestorePending]);

  useEffect(() => {
    setPdfViewportPage(1);
    if (activeRenderExt === 'pdf' && activePreviewIdentity) {
      setPdfScrollRequest(createPdfScrollRequest(1));
      return;
    }
    setPdfScrollRequest(null);
  }, [activePreviewIdentity, activeRenderExt]);

  useEffect(() => {
    if (!activeSourceFile) {
      if (activeConvertedPdfUrl && (activeExt === 'doc' || activeExt === 'docx')) {
        setPreviewUrl(activeConvertedPdfUrl);
      } else if (activeExt === 'pdf' && activeDocPreviewPdfUrl) {
        setPreviewUrl(activeDocPreviewPdfUrl);
      } else {
        setPreviewUrl(null);
      }
      return;
    }
    if ((activeExt === 'doc' || activeExt === 'docx') && activeConvertedPdfUrl) {
      setPreviewUrl(activeConvertedPdfUrl);
      return;
    }
    const url = URL.createObjectURL(activeSourceFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [activeSourceFile, activeExt, activeConvertedPdfUrl, activeDocPreviewPdfUrl]);

  useEffect(() => {
    if (activeRenderExt !== 'pdf') {
      setPdfPreviewPageCount(1);
      return;
    }
    setPdfPreviewPageCount(1);
  }, [activeRenderExt, previewUrl]);

  useEffect(() => {
    let cancelled = false;
    if (!activeSourceFile) {
      setPreviewText('');
      return () => {
        cancelled = true;
      };
    }

    if (['txt', 'md'].includes(activeExt)) {
      activeSourceFile.text().then((text) => {
        if (cancelled) return;
        const maxChars = 12000;
        setPreviewText(text.length > maxChars ? `${text.slice(0, maxChars)}\n\n...[内容已截断]` : text);
      });
      return () => {
        cancelled = true;
      };
    }

    setPreviewText('');
    return () => {
      cancelled = true;
    };
  }, [activeSourceFile, activeExt]);

  const activeTraceHit = useMemo(() => {
    if (!activeTraceKey) return null;
    const idx = traceHits.findIndex((hit, i) => toTraceHitKey(hit, i) === activeTraceKey);
    if (idx < 0) return null;
    return traceHits[idx];
  }, [activeTraceKey, traceHits]);

  const previewHighlight = useMemo(() => {
    if (!['txt', 'md'].includes(activeExt)) return null;
    const sourceText = previewText || '';
    if (!sourceText) return null;
    const rawSnippet = String(activeTraceHit?.snippet || '').split('|')[0].trim();
    const fieldEntity = activeDoc && activeFieldKey ? activeDoc.result?.[activeFieldKey] : null;
    const fieldFallback = fieldEntity?.value == null ? '' : String(fieldEntity.value);
    let keyword = rawSnippet || fieldFallback;
    keyword = keyword.replace(/^[^:：]{1,30}[:：]\s*/, '').trim();
    if (keyword.length < 2) return null;
    if (keyword.length > 64) keyword = keyword.slice(0, 64);

    const lowerText = sourceText.toLowerCase();
    const lowerKeyword = keyword.toLowerCase();
    const start = lowerText.indexOf(lowerKeyword);
    if (start < 0) return null;
    return {
      before: sourceText.slice(0, start),
      hit: sourceText.slice(start, start + keyword.length),
      after: sourceText.slice(start + keyword.length),
    };
  }, [activeExt, previewText, activeTraceHit, activeFieldKey, activeDoc]);

  const xlsxLocatorHint = useMemo(() => {
    if (activeRenderExt !== 'xlsx') return null;
    const locator = (activeTraceHit?.locator ?? {}) as Record<string, unknown>;
    return {
      sheet_index: Number(locator.sheet_index || 0),
      row_index: Number(locator.row_index || 0),
      col_index: Number(locator.col_index || 0),
      sheet_name: String(locator.sheet_name || ''),
    };
  }, [activeRenderExt, activeTraceHit]);

  useEffect(() => {
    if (!previewHighlight || !textPreviewRef.current) return;
    const mark = textPreviewRef.current.querySelector('mark[data-preview-highlight="true"]');
    if (!mark) return;
    mark.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [previewHighlight]);

  useEffect(() => {
    setResultSearchQuery('');
  }, [activeDoc?.file_hash]);

  useEffect(() => {
    const panel = assistantDialogRef.current;
    if (!panel) return;
    panel.scrollTop = panel.scrollHeight;
  }, [assistantDialog, assistantQueryLoading]);

  useEffect(() => {
    if (activeSourceFile) {
      setIsUploaderDragOver(false);
    }
  }, [activeSourceFile]);

  const requestSummary = async (doc: DocumentResult) => {
    if (!doc) return;
    const seq = ++summaryRequestSeqRef.current;
    setSummaryDocName(doc.file_name);
    setActiveSummaryLoading(true);
    try {
      const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
      const fetchResult = await fetchExtractWithFallback(
        '/extract/summarize',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_name: doc.file_name,
            result: doc.result,
            diagnostics: doc.diagnostics ?? {},
            errors: doc.errors ?? [],
            soft_warnings: doc.soft_warnings ?? [],
            trace_hits: doc.trace_hits ?? [],
            max_chars: 520,
          }),
        },
        preferredBase,
      );
      extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
      const response = fetchResult.response;
      if (!response.ok) {
        throw new Error('摘要生成失败');
      }
      const payload = (await response.json()) as SummarizeResponse;
      if (seq !== summaryRequestSeqRef.current) return;
      setActiveSummaryText((payload.summary || "").trim() || "暂无摘要。");
    } catch (error) {
      if (seq !== summaryRequestSeqRef.current) return;
      const fallback = String(doc.errors?.[0] ?? '').trim();
      setActiveSummaryText(fallback || "暂时无法生成摘要，请稍后重试。");
    } finally {
      if (seq === summaryRequestSeqRef.current) {
        setActiveSummaryLoading(false);
      }
    }
  };

  const requestTraceHits = async (doc: DocumentResult, fieldKey?: string | null) => {
    if (!doc) return;
    const seq = ++traceRequestSeqRef.current;
    setTraceLoading(true);
    setTraceError('');
    try {
      const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
      const fetchResult = await fetchExtractWithFallback(
        '/extract/trace/locate',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            document: doc,
            field_name: fieldKey || undefined,
            top_k: 40,
          }),
        },
        preferredBase,
      );
      extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
      const response = fetchResult.response;
      if (!response.ok) {
        throw new Error('溯源定位失败');
      }
      const payload = (await response.json()) as TraceLocateResponse;
      if (seq !== traceRequestSeqRef.current) return;
      const hits = Array.isArray(payload.hits) ? payload.hits : [];
      setTraceHits(hits.length > 0 ? hits : toTraceHits(doc, fieldKey));
    } catch (error) {
      if (seq !== traceRequestSeqRef.current) return;
      setTraceHits(toTraceHits(doc, fieldKey));
      setTraceError(error instanceof Error ? error.message : '溯源定位失败');
    } finally {
      if (seq === traceRequestSeqRef.current) {
        setTraceLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!activeDoc) {
      setSummaryDocName('');
      setActiveSummaryText('');
      setActiveSummaryLoading(false);
      return;
    }
    void requestSummary(activeDoc);
  }, [activeDoc?.file_hash]);

  useEffect(() => {
    if (!activeDoc) {
      setTraceHits([]);
      setTraceError('');
      setTraceLoading(false);
      setActiveTraceKey('');
      return;
    }
    if (Array.isArray(activeDoc.trace_hits) && activeDoc.trace_hits.length > 0) {
      setTraceHits(toTraceHits(activeDoc, activeFieldKey));
      setTraceError('');
      setTraceLoading(false);
      return;
    }
    void requestTraceHits(activeDoc, activeFieldKey);
  }, [activeDoc?.file_hash, activeFieldKey]);

  useEffect(() => {
    if (!activeDoc) {
      setAssistantStatus('idle');
      setAssistantMessage("等待生成可执行建议。");
      return;
    }
    if (assistantActionable) {
      setAssistantStatus('idle');
      setAssistantMessage("检测到异常或软告警，请确认是否接受当前结果，或执行回滚后重试。");
    } else {
      setAssistantStatus('idle');
      setAssistantMessage("当前批次无需执行变更，结果可直接使用。");
    }
  }, [activeDoc?.file_hash, assistantActionable]);

  useEffect(() => {
    assistantAbortRef.current?.abort();
    assistantAbortRef.current = null;
    setAssistantInput('');
    setAssistantAnswer('');
    setAssistantWarnings([]);
    setAssistantDialog([]);
    setAssistantQueryLoading(false);
    setAssistantSessionId('');
    setAssistantCurrentLock(null);
    setOfficePreviewMap({});
    setActiveTraceKey('');
    const fileHash = String(activeDoc?.file_hash || '').trim();
    if (!activeDoc || !fileHash) {
      return;
    }
    const storedSessionId = String(readAssistantSessionMap()[fileHash] || '').trim();
    if (!storedSessionId) {
      return;
    }
    let cancelled = false;
    const hydrateSession = async () => {
      try {
        const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
        const fetchResult = await fetchExtractWithFallback(
          '/extract/assistant/session',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              document: activeDoc,
              summary: activeSummaryText,
              session_id: storedSessionId,
            }),
          },
          preferredBase,
        );
        extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
        const response = fetchResult.response;
        if (!response.ok) {
          throw new Error('助手会话恢复失败');
        }
        const payload = (await response.json()) as AssistantSessionResponse;
        if (cancelled) return;
        setAssistantSessionId(String(payload.session_id || '').trim());
        setAssistantCurrentLock(payload.current_object_lock ?? null);
        if (Array.isArray(payload.messages) && payload.messages.length > 0) {
          setAssistantDialog(payload.messages.map(toAssistantDialogMessage));
        }
      } catch {
        if (cancelled) return;
        clearAssistantSessionForFile(fileHash);
      }
    };
    void hydrateSession();
    return () => {
      cancelled = true;
    };
  }, [activeDoc?.file_hash]);

  const fieldItems = useMemo<FieldItem[]>(() => {
    if (!activeDoc) return [];

    const entries = Object.entries(activeDoc.result) as Array<[string, ExtractionEntity]>;
    const meaningful = entries.filter(([, entity]) => {
      if (!entity) return false;
      const value = entity.value;
      if (value == null) return false;
      const text = String(value).trim();
      if (!text || text.toLowerCase() === 'null') return false;
      const conf = Number(entity.confidence ?? 0);
      return Number.isFinite(conf) && conf >= 0.2;
    });

    return meaningful.map(([fieldName, entity]) => ({
      bbox: Array.isArray(entity.bbox) ? entity.bbox : [],
      key: fieldName,
      label: toFieldLabel(fieldName),
      valueText: String(entity.value),
      confidence: entity.confidence ?? 0,
      refId: entity.source_ref_id,
      pageNumber: toPageNumber(Array.isArray(entity.bbox) ? entity.bbox : []),
    }));
  }, [activeDoc]);
  const filteredFieldItems = useMemo(() => {
    const q = resultSearchQuery.trim().toLowerCase();
    if (!q) return fieldItems;
    return fieldItems.filter((item) => {
      const key = String(item.key || '').toLowerCase();
      const label = String(item.label || '').toLowerCase();
      const value = String(item.valueText || '').toLowerCase();
      return key.includes(q) || label.includes(q) || value.includes(q);
    });
  }, [fieldItems, resultSearchQuery]);
  const hasResultSearch = resultSearchQuery.trim().length > 0;
  const resultCountText = useMemo(() => {
    if (fieldItems.length === 0) return '';
    if (!hasResultSearch) return `${fieldItems.length} 个字段`;
    return `${filteredFieldItems.length} / ${fieldItems.length} 个字段`;
  }, [fieldItems.length, filteredFieldItems.length, hasResultSearch]);
  const canCopyFilteredResults = filteredFieldItems.length > 0;
  const filteredResultsClipboardText = useMemo(
    () =>
      filteredFieldItems
        .map((item, idx) => `${idx + 1}. ${item.label} (${item.key})\n${item.valueText}`)
        .join('\n\n'),
    [filteredFieldItems]
  );

  const inferredPdfPageCount = useMemo(() => {
    if (activeRenderExt !== 'pdf') return 1;
    const maxByRefs = fieldItems.reduce((maxPage, item) => {
      if (item.pageNumber == null) return maxPage;
      return Math.max(maxPage, item.pageNumber);
    }, 1);
    const maxByTrace = traceHits.reduce((maxPage, hit) => {
      const page = Number(hit.page || 0);
      if (!Number.isFinite(page) || page < 1) return maxPage;
      return Math.max(maxPage, Math.round(page));
    }, 1);
    return Math.max(1, maxByRefs, maxByTrace, pdfPreviewPageCount);
  }, [activeRenderExt, fieldItems, pdfPreviewPageCount, traceHits]);

  const currentPdfPage = Math.min(Math.max(pdfViewportPage, 1), inferredPdfPageCount);

  useEffect(() => {
    if (activeRenderExt !== 'pdf') return;
    if (pdfViewportPage !== currentPdfPage) {
      setPdfViewportPage(currentPdfPage);
    }
  }, [activeRenderExt, currentPdfPage, pdfViewportPage]);

  const overlayItems = useMemo(() => {
    const drawable = activeRenderExt === 'pdf' || IMAGE_EXTENSIONS.has(activeRenderExt);
    if (!drawable) return [];
    if (activeRenderExt !== 'pdf') {
      return fieldItems.filter((item) => hasMeaningfulBox(item.bbox));
    }
    return fieldItems.filter(
      (item) => hasMeaningfulBox(item.bbox) && item.pageNumber === currentPdfPage
    );
  }, [activeRenderExt, currentPdfPage, fieldItems]);

  const overlayTraceItems = useMemo(() => {
    const drawable = activeRenderExt === 'pdf' || IMAGE_EXTENSIONS.has(activeRenderExt);
    if (!drawable) return [];
    const filtered = traceHits.filter((hit) => {
      const bbox = Array.isArray(hit.bbox) ? hit.bbox : [];
      if (!hasMeaningfulBox(bbox)) return false;
      if (String(hit.object_type || '').toLowerCase() === 'field') return false;
      if (activeRenderExt !== 'pdf') return true;
      const page = Number(hit.page || bbox[0] || 0);
      return Number.isFinite(page) && Math.round(page) === currentPdfPage;
    });
    return filtered.slice(0, 24);
  }, [traceHits, activeRenderExt, currentPdfPage]);

  const avgConfidence = useMemo(() => {
    if (fieldItems.length === 0) return 0;
    const total = fieldItems.reduce((acc, item) => acc + item.confidence, 0);
    return Math.round((total / fieldItems.length) * 100);
  }, [fieldItems]);

  const traceTypeStats = useMemo(() => {
    const stats = {
      field: 0,
      table: 0,
      image: 0,
      other: 0,
    };

    traceHits.forEach((hit) => {
      const typ = getTraceDisplayKind(hit);
      if (typ === 'field') {
        stats.field += 1;
      } else if (typ === 'table') {
        stats.table += 1;
      } else if (typ === 'image') {
        stats.image += 1;
      } else {
        stats.other += 1;
      }
    });

    return stats;
  }, [traceHits]);

  const assistantActivityKey = useMemo(
    () =>
      JSON.stringify({
        summary: activeSummaryText,
        summaryLoading: activeSummaryLoading,
        dialogCount: assistantDialog.length,
        lastDialogId: assistantDialog[assistantDialog.length - 1]?.id ?? '',
        assistantAnswer,
        assistantWarnings: assistantWarnings.join('|'),
        assistantMessage,
        assistantQueryLoading,
        assistantStatus,
      }),
    [
      activeSummaryText,
      activeSummaryLoading,
      assistantDialog,
      assistantAnswer,
      assistantWarnings,
      assistantMessage,
      assistantQueryLoading,
      assistantStatus,
    ]
  );
  const resultsActivityKey = useMemo(
    () =>
      JSON.stringify({
        activeDocHash: activeDoc?.file_hash ?? '',
        documentCount: documents.length,
        fieldCount: fieldItems.length,
        traceCount: traceHits.length,
        errorMessage,
        softWarningCount: activeDoc?.soft_warnings?.length ?? 0,
      }),
    [activeDoc?.file_hash, activeDoc?.soft_warnings?.length, documents.length, errorMessage, fieldItems.length, traceHits.length]
  );

  useEffect(() => {
    if (smartUnitTab === 'assistant' && assistantTabUnread) {
      setAssistantTabUnread(false);
    }
    if (smartUnitTab === 'results' && resultsTabUnread) {
      setResultsTabUnread(false);
    }
  }, [assistantTabUnread, resultsTabUnread, smartUnitTab]);

  useEffect(() => {
    const hasAssistantActivity =
      activeSummaryLoading ||
      assistantQueryLoading ||
      Boolean(activeSummaryText.trim()) ||
      assistantDialog.length > 0 ||
      assistantWarnings.length > 0 ||
      Boolean(assistantAnswer.trim());
    if (!hasAssistantActivity) {
      assistantActivityRef.current = assistantActivityKey;
      return;
    }
    if (
      assistantActivityRef.current &&
      assistantActivityRef.current !== assistantActivityKey &&
      smartUnitTab !== 'assistant'
    ) {
      setAssistantTabUnread(true);
    }
    assistantActivityRef.current = assistantActivityKey;
  }, [
    activeSummaryLoading,
    activeSummaryText,
    assistantActivityKey,
    assistantAnswer,
    assistantDialog.length,
    assistantQueryLoading,
    assistantWarnings.length,
    smartUnitTab,
  ]);

  useEffect(() => {
    const hasResultActivity =
      Boolean(activeDoc) ||
      documents.length > 0 ||
      fieldItems.length > 0 ||
      traceHits.length > 0 ||
      Boolean(errorMessage.trim());
    if (!hasResultActivity) {
      resultsActivityRef.current = resultsActivityKey;
      return;
    }
    if (
      resultsActivityRef.current &&
      resultsActivityRef.current !== resultsActivityKey &&
      smartUnitTab !== 'results'
    ) {
      setResultsTabUnread(true);
    }
    resultsActivityRef.current = resultsActivityKey;
  }, [activeDoc, documents.length, errorMessage, fieldItems.length, resultsActivityKey, smartUnitTab, traceHits.length]);

  const traceGroups = useMemo(() => {
    const grouped = {
      field: [] as Array<{ hit: TraceHit; idx: number }>,
      table: [] as Array<{ hit: TraceHit; idx: number }>,
      image: [] as Array<{ hit: TraceHit; idx: number }>,
      other: [] as Array<{ hit: TraceHit; idx: number }>,
    };
    traceHits.forEach((hit, idx) => {
      const typ = getTraceDisplayKind(hit);
      if (typ === "field") {
        grouped.field.push({ hit, idx });
      } else if (typ === "table") {
        grouped.table.push({ hit, idx });
      } else if (typ === "image") {
        grouped.image.push({ hit, idx });
      } else {
        grouped.other.push({ hit, idx });
      }
    });
    return [
      { key: "field", label: "字段", items: grouped.field },
      { key: "table", label: "表格", items: grouped.table },
      { key: "image", label: "图片", items: grouped.image },
      { key: "other", label: "其他", items: grouped.other },
    ].filter((group) => group.items.length > 0);
  }, [traceHits]);

  const tableCount = useMemo(() => {
    const raw = Number(activeDoc?.diagnostics?.table_count ?? 0);
    return Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0;
  }, [activeDoc?.diagnostics?.table_count]);

  const figureCount = useMemo(() => {
    const raw = Number(activeDoc?.diagnostics?.figure_count ?? 0);
    return Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0;
  }, [activeDoc?.diagnostics?.figure_count]);

  const pollOfficePreview = async (key: string, jobId: string, preferredBase = '') => {
    const maxPoll = 150;
    let resolvedBase = preferredBase;
    for (let i = 0; i < maxPoll; i += 1) {
      if (officePreviewPollRef.current[key] !== jobId) return;
      await new Promise((resolve) => setTimeout(resolve, 1200));
      let response: Response | null = null;
      try {
        const fetchResult = await fetchExtractWithFallback(
          `/extract/preview/office/status/${encodeURIComponent(jobId)}`,
          undefined,
          resolvedBase,
        );
        response = fetchResult.response;
        resolvedBase = fetchResult.usedBase || resolvedBase;
        officePreviewApiBaseRef.current[key] = resolvedBase;
      } catch {
        continue;
      }
      if (!response || !response.ok) continue;
      const payload = await response.json();
      const status = String(payload.status || '').toLowerCase();
      if (status === 'completed') {
        const pdfUrl = toAbsoluteExtractUrl(String(payload.artifact_url || '').trim(), resolvedBase);
        setOfficePreviewMap((prev) => ({
          ...prev,
          [key]: {
            status: 'completed',
            jobId,
            pdfUrl,
          },
        }));
        officePreviewApiBaseRef.current[key] = resolvedBase;
        delete officePreviewPollRef.current[key];
        return;
      }
      if (status === 'failed') {
        setOfficePreviewMap((prev) => ({
          ...prev,
          [key]: {
            status: 'failed',
            jobId,
            error: String(payload.error || '文档预览转换失败'),
          },
        }));
        delete officePreviewApiBaseRef.current[key];
        delete officePreviewPollRef.current[key];
        return;
      }
      setOfficePreviewMap((prev) => ({
        ...prev,
        [key]: {
          ...(prev[key] || { status: 'queued' as const }),
          status: status === 'running' ? 'running' : 'queued',
          jobId,
        },
      }));
    }
    if (officePreviewPollRef.current[key] !== jobId) return;
    setOfficePreviewMap((prev) => ({
      ...prev,
      [key]: {
        ...(prev[key] || { status: 'queued' as const }),
        status: 'failed',
        jobId,
        error: '文档预览转换超时',
      },
    }));
    delete officePreviewApiBaseRef.current[key];
    delete officePreviewPollRef.current[key];
  };

  const ensureOfficePreview = async (file: File) => {
    const ext = fileExt(file.name);
    if (ext !== 'doc' && ext !== 'docx') return;
    const key = fileIdentityKey(file);
    if (officePreviewPollRef.current[key]) return;
    const current = officePreviewMap[key];
    if (current && (current.status === 'running' || current.status === 'queued' || current.status === 'completed')) {
      return;
    }
    setOfficePreviewMap((prev) => ({
      ...prev,
      [key]: { status: 'queued' },
    }));
    try {
      const formData = new FormData();
      formData.append('file', file);
      const fetchResult = await fetchExtractWithFallback(
        '/extract/preview/office/start',
        {
          method: 'POST',
          body: formData,
        },
        officePreviewApiBaseRef.current[key] || '',
      );
      const response = fetchResult.response;
      const usedBase = fetchResult.usedBase || '';
      const payload = await response.json();
      const status = String(payload.status || '').toLowerCase();
      const jobId = String(payload.job_id || '').trim();
      const pdfUrl = toAbsoluteExtractUrl(String(payload.artifact_url || '').trim(), usedBase);
      if (status === 'completed' && pdfUrl) {
        setOfficePreviewMap((prev) => ({
          ...prev,
          [key]: {
            status: 'completed',
            jobId,
            pdfUrl,
          },
        }));
        officePreviewApiBaseRef.current[key] = usedBase;
        delete officePreviewPollRef.current[key];
        return;
      }
      if (!jobId) {
        throw new Error('文档预览任务创建失败');
      }
      officePreviewPollRef.current[key] = jobId;
      officePreviewApiBaseRef.current[key] = usedBase;
      setOfficePreviewMap((prev) => ({
        ...prev,
        [key]: {
          status: status === 'running' ? 'running' : 'queued',
          jobId,
        },
      }));
      void pollOfficePreview(key, jobId, usedBase);
    } catch (error) {
      delete officePreviewPollRef.current[key];
      delete officePreviewApiBaseRef.current[key];
      setOfficePreviewMap((prev) => ({
        ...prev,
        [key]: {
          status: 'failed',
          error: parseFetchErrorMessage(error),
        },
      }));
    }
  };

  const applyExtractionDocuments = (docs: DocumentResult[]) => {
    const documentsWithPreview = docs.map((doc) => {
      const ext = fileExt(String(doc.file_name || ''));
      if (ext !== 'doc' && ext !== 'docx') return doc;

      const diagnostics =
        doc.diagnostics && typeof doc.diagnostics === 'object'
          ? (doc.diagnostics as Record<string, unknown>)
          : {};
      const existingPreviewUrl = String(diagnostics.office_pdf_preview_url || '').trim();
      if (existingPreviewUrl) return doc;

      const matchedPreview = pickOfficePreviewByFileName(doc.file_name, officePreviewMap);
      const previewUrl = String(matchedPreview?.pdfUrl || '').trim();
      if (!previewUrl) return doc;

      return {
        ...doc,
        diagnostics: {
          ...diagnostics,
          office_pdf_preview_url: previewUrl,
        },
      };
    });

    setDocuments(documentsWithPreview);
    writeExtractionDocuments(documentsWithPreview);
    setActiveDocIndex(0);
    setPdfViewportPage(1);
    setPdfScrollRequest(createPdfScrollRequest(1));
    if (documentsWithPreview.length > 0) {
      void requestSummary(documentsWithPreview[0]);
    }

    const firstErrorDoc = documentsWithPreview.find((doc) => doc.errors && doc.errors.length > 0);
    if (firstErrorDoc) {
      setErrorMessage(firstErrorDoc.errors.join(' | '));
      return;
    }

    const cacheHits = documentsWithPreview.filter((doc) => doc.cached).length;
    const totalTables = documentsWithPreview.reduce((acc, doc) => {
      const raw = doc.diagnostics?.table_count;
      const val = typeof raw === 'number' ? raw : Number(raw ?? 0);
      return acc + (Number.isFinite(val) ? val : 0);
    }, 0);
    const totalFigures = documentsWithPreview.reduce((acc, doc) => {
      const raw = doc.diagnostics?.figure_count;
      const val = typeof raw === 'number' ? raw : Number(raw ?? 0);
      return acc + (Number.isFinite(val) ? val : 0);
    }, 0);
    const sourceSet = new Set<string>();
    const figureSourceSet = new Set<string>();
    documentsWithPreview.forEach((doc) => {
      const srcRaw = doc.diagnostics?.table_sources;
      if (!srcRaw || typeof srcRaw !== 'object') return;
      Object.keys(srcRaw as Record<string, unknown>).forEach((key) => sourceSet.add(key));
      const figRaw = doc.diagnostics?.figure_sources;
      if (figRaw && typeof figRaw === 'object') {
        Object.keys(figRaw as Record<string, unknown>).forEach((key) => figureSourceSet.add(key));
      }
    });
    const sourceText = sourceSet.size > 0 ? Array.from(sourceSet).slice(0, 3).join(', ') : '未知';
    const figureSourceText = figureSourceSet.size > 0 ? Array.from(figureSourceSet).slice(0, 3).join(', ') : '未知';
    const softWarningCount = documentsWithPreview.reduce((acc, doc) => acc + (doc.soft_warnings?.length ?? 0), 0);
    const autoSchemaDocs = documentsWithPreview.reduce((acc, doc) => {
      const mode = String(doc.diagnostics?.schema_mode || '');
      return acc + (mode === 'auto' ? 1 : 0);
    }, 0);
    setInfoMessage(
      `已完成 ${documentsWithPreview.length} 份文档抽取，缓存命中 ${cacheHits} 份，智能字段识别 ${autoSchemaDocs} 份，识别表格 ${totalTables} 张（来源: ${sourceText}），识别图像 ${totalFigures} 张（来源: ${figureSourceText}），软告警 ${softWarningCount} 条。`
    );
  };

  const pollExtractionJob = async (jobId: string, preferredBase = '') => {
    extractionJobPollRef.current = jobId;
    const pollIntervalMs = 1200;
    const pollTimeoutMs = 45 * 60 * 1000;
    const startedAt = Date.now();
    while (Date.now() - startedAt < pollTimeoutMs) {
      if (extractionJobPollRef.current !== jobId) return;
      try {
        const fetchResult = await fetchExtractWithFallback(
          `/extract/jobs/status/${encodeURIComponent(jobId)}?include_documents=true`,
          undefined,
          preferredBase || extractionJobApiBaseRef.current || '',
        );
        const usedBase = fetchResult.usedBase || preferredBase || '';
        extractionJobApiBaseRef.current = usedBase;
        const payload = (await fetchResult.response.json()) as ExtractionJobState & {
          progress: ExtractionJobState['progress'];
          terminal: boolean;
          documents?: DocumentResult[];
        };
        setExtractionJob(payload);
        setIsProcessing(!payload.terminal);

        const progress = payload.progress;
        const currentName = String(progress?.current_file_name || '').trim();
        const currentStage = String(progress?.current_stage || '').trim();
        const currentPercent = Math.max(0, Math.min(100, Math.round(Number(progress?.progress_ratio || 0) * 100)));
        if (!payload.terminal) {
          setInfoMessage(
            currentName
              ? `正在处理 ${currentName} · ${currentStage || 'running'} · ${currentPercent}%`
              : `正在处理文档 · ${currentPercent}%`
          );
        }

        if (payload.terminal) {
          extractionJobPollRef.current = '';
          if (Array.isArray(payload.documents) && payload.documents.length > 0) {
            applyExtractionDocuments(payload.documents);
          } else if (Array.isArray(payload.errors) && payload.errors.length > 0) {
            setErrorMessage(payload.errors.join(' | '));
          } else {
            setInfoMessage('抽取任务已结束，暂无可展示结果。');
          }
          return;
        }
      } catch (error) {
        if (extractionJobPollRef.current !== jobId) return;
        const message =
          error instanceof Error && String(error.message || '').trim()
            ? String(error.message || '').trim()
            : '抽取进度同步失败';
        if (message.toLowerCase().includes('not found')) {
          extractionJobPollRef.current = '';
          setErrorMessage(message);
          setIsProcessing(false);
          return;
        }
        setInfoMessage('正在同步最新解析进度...');
      }
      await new Promise((resolve) => window.setTimeout(resolve, pollIntervalMs));
    }
    if (extractionJobPollRef.current === jobId) {
      setErrorMessage('抽取进度轮询超时，请稍后重试或检查后端日志。');
      extractionJobPollRef.current = '';
      setIsProcessing(false);
    }
  };

  useEffect(() => {
    if (!extractionJob || extractionJob.terminal) return;
    if (extractionJobPollRef.current === extractionJob.job_id) return;
    void pollExtractionJob(extractionJob.job_id, extractionJobApiBaseRef.current || '');
  }, [extractionJob?.job_id, extractionJob?.terminal]);

  useEffect(() => {
    Object.entries(officePreviewMap as Record<string, OfficePreviewState>).forEach(([key, state]) => {
      if (!state?.jobId) return;
      if (state.status !== 'queued' && state.status !== 'running') return;
      if (officePreviewPollRef.current[key] === state.jobId) return;
      officePreviewPollRef.current[key] = state.jobId;
      void pollOfficePreview(key, state.jobId, officePreviewApiBaseRef.current[key] || '');
    });
  }, [officePreviewMap]);

  const mergeSelectedFiles = (incomingRaw: File[]) => {
    const incoming = incomingRaw.filter(isAllowedFile);
    const rejectedCount = incomingRaw.length - incoming.length;
    if (incoming.length === 0) {
      if (rejectedCount > 0) {
        setInfoMessage("未添加任何文件，仅支持常见文档与图片格式。");
      }
      return;
    }

    const byIdentity = new Map<string, File>();
    [...selectedFiles, ...incoming].forEach((file) => {
      byIdentity.set(fileIdentityKey(file), file);
    });
    const merged = Array.from(byIdentity.values());
    const limited = merged.slice(0, 5);
    setSelectedFiles(limited);
    if (merged.length > 5) {
      setInfoMessage("批处理上限为 5 个文件，超出部分已忽略。");
    } else if (rejectedCount > 0) {
      setInfoMessage(`已忽略 ${rejectedCount} 个不支持的文件，仅支持常见文档与图片格式。`);
    } else {
      setInfoMessage(`已选择 ${limited.length} 个文件，可开始提取。`);
    }
    const selectedKeySet = new Set(limited.map((file) => fileIdentityKey(file)));
    incoming.forEach((file) => {
      if (!selectedKeySet.has(fileIdentityKey(file))) return;
      void ensureOfficePreview(file);
      scheduleSpreadsheetPreviewWarmup(file);
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsUploaderDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsUploaderDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsUploaderDragOver(false);
    const files = Array.from(e.dataTransfer.files) as File[];
    if (files.length > 0) {
      mergeSelectedFiles(files);
    }
  };

  const onSelectFiles = (event: React.ChangeEvent<HTMLInputElement>) => {
    const incomingRaw = Array.from(event.target.files ?? []) as File[];
    mergeSelectedFiles(incomingRaw);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const resetWorkbenchState = (message: string) => {
    officePreviewPollRef.current = {};
    officePreviewApiBaseRef.current = {};
    extractionJobPollRef.current = '';
    extractionJobApiBaseRef.current = '';
    persistedSelectedFilesRef.current = [];
    clearSpreadsheetPreviewWarmupQueue();
    clearLuckysheetPreviewCache();
    setOfficePreviewMap({});
    setExtractionJob(null);
    setSelectedFileArtifacts({});
    setSessionRestorePending(false);
    setDocuments([]);
    setActiveDocIndex(0);
    setActiveFieldKey(null);
    setPreviewUrl(null);
    setPreviewText('');
    setPdfViewportPage(1);
    setPdfScrollRequest(null);
    setPdfPreviewPageCount(1);
    setErrorMessage('');
    setInfoMessage(message);
    setScale(1);
    setRotation(0);
    summaryRequestSeqRef.current += 1;
    traceRequestSeqRef.current += 1;
    setSummaryDocName('');
    setActiveSummaryText('');
    setActiveSummaryLoading(false);
    setTraceHits([]);
    setTraceError('');
    setTraceLoading(false);
    setActiveTraceKey('');
    setAssistantStatus('idle');
    setAssistantMessage("等待生成可执行建议。");
    setAssistantInput('');
    setAssistantAnswer('');
    setAssistantWarnings([]);
    setAssistantQueryLoading(false);
    setAssistantDialog([]);
    setSmartUnitTab('results');
    setAssistantTabUnread(false);
    setResultsTabUnread(false);
    setShowAssistantHelp(false);
    setIsPreviewFocused(false);
    setIsUploaderDragOver(false);
    setResultSearchQuery('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    clearExtractionDocuments();
    clearWorkbenchSession();
  };

  const clearWorkbenchData = () => {
    if (!canClearWorkbenchData) return;
    setSelectedFiles([]);
    resetWorkbenchState('已清空当前页面数据与本地缓存。');
  };

  const removeFile = (index: number) => {
    const removed = selectedFiles[index];
    if (!removed) return;

    if (selectedFiles.length <= 1) {
      setSelectedFiles([]);
      resetWorkbenchState("文件队列已清空。");
      return;
    }

    const key = fileIdentityKey(removed);
    delete officePreviewPollRef.current[key];
    delete officePreviewApiBaseRef.current[key];
    setSelectedFileArtifacts((prev) => {
      if (!(key in prev)) return prev;
      const copied = { ...prev };
      delete copied[key];
      return copied;
    });
    setOfficePreviewMap((map) => {
      if (!(key in map)) return map;
      const copied = { ...map };
      delete copied[key];
      return copied;
    });

    const nextFiles = selectedFiles.filter((_, i) => i !== index);
    setSelectedFiles(nextFiles);
    setDocuments((prev) => {
      if (!Array.isArray(prev) || prev.length === 0) return prev;
      let nextDocs: DocumentResult[] = prev;
      if (index >= 0 && index < prev.length) {
        nextDocs = prev.filter((_, i) => i !== index);
      } else {
        const removedName = removed.name.trim().toLowerCase();
        nextDocs = prev.filter((doc) => String(doc.file_name || '').trim().toLowerCase() !== removedName);
      }
      writeExtractionDocuments(nextDocs);
      return nextDocs;
    });
    if (activeDocIndex >= nextFiles.length) {
      setActiveDocIndex(Math.max(0, nextFiles.length - 1));
    }
    setActiveFieldKey(null);
    setInfoMessage(`已移除 ${removed.name}`);
  };

  const clearAllFiles = () => {
    setSelectedFiles([]);
    resetWorkbenchState('文件队列已清空。');
  };

  const runExtraction = async () => {
    if (selectedFiles.length === 0) {
      setErrorMessage("请至少上传一个文件。");
      return;
    }

    let schemaObj: unknown;
    try {
      schemaObj = JSON.parse(schemaText);
    } catch (error) {
      setErrorMessage(error instanceof Error ? `规则模板格式错误：${error.message}` : "规则模板格式错误。");
      return;
    }

    setErrorMessage('');
    setActiveFieldKey(null);
    setIsProcessing(true);
    setDocuments([]);
    clearExtractionDocuments();
    setExtractionJob(null);
    extractionJobPollRef.current = '';
    extractionJobApiBaseRef.current = '';
    setSelectedFileArtifacts({});
    setActiveDocIndex(0);
    setInfoMessage(`正在提交 ${selectedFiles.length} 个文件的抽取任务...`);
    setActiveSummaryLoading(true);
    setActiveSummaryText('已收到抽取任务，正在生成智能摘要...');
    setSummaryDocName(selectedFiles.length === 1 ? selectedFiles[0].name : '当前批次');
    setAssistantMessage("任务已提交，解析与摘要正在同步执行。");
    setAssistantAnswer('');
    setAssistantWarnings([]);
    traceRequestSeqRef.current += 1;
    setTraceHits([]);
    setTraceError('');
    setTraceLoading(false);
    setActiveTraceKey('');

    try {
      const requestJobCreateWithRetry = async (attempts: number) => {
        let lastError: unknown = null;
        for (let i = 1; i <= attempts; i += 1) {
          const formData = new FormData();
          selectedFiles.forEach((file) => formData.append('files', file));
          formData.append('schema', stringifyAsciiSafeJson(schemaObj));
          try {
            return await fetchExtractWithFallback('/extract/jobs/create', {
              method: 'POST',
              body: formData,
            });
          } catch (error) {
            lastError = error;
            if (i < attempts) {
              setInfoMessage(`网络抖动，正在重试抽取请求（${i}/${attempts - 1}）...`);
              await new Promise((resolve) => setTimeout(resolve, 600 * i));
              continue;
            }
          }
        }
        throw lastError instanceof Error ? lastError : new Error('抽取请求失败');
      };

      const fetchResult = await requestJobCreateWithRetry(2);
      const response = fetchResult.response;
      const usedBase = fetchResult.usedBase || '';
      extractionJobApiBaseRef.current = usedBase;

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || '抽取请求失败');
      }

      const payload = await response.json() as ExtractionJobState & { documents?: DocumentResult[] };
      if (!payload || !payload.job_id) {
        throw new Error('后端未返回有效的抽取任务。');
      }

      const normalizedFiles = Array.isArray(payload.files)
        ? payload.files.map((item) => ({
            ...item,
            artifact_url: toAbsoluteExtractUrl(String(item.artifact_url || '').trim(), usedBase) || item.artifact_url,
          }))
        : [];
      const normalizedJob: ExtractionJobState = {
        ...payload,
        files: normalizedFiles,
        errors: Array.isArray(payload.errors) ? payload.errors : [],
      };
      const nextArtifactMap = selectedFiles.reduce<Record<string, { artifactUrl?: string; artifactPath?: string }>>(
        (acc, file, index) => {
          const item = normalizedFiles[index];
          acc[fileIdentityKey(file)] = {
            artifactUrl: String(item?.artifact_url || '').trim() || undefined,
            artifactPath: String(item?.artifact_path || '').trim() || undefined,
          };
          return acc;
        },
        {},
      );

      setSelectedFileArtifacts(nextArtifactMap);
      setExtractionJob(normalizedJob);
      setIsProcessing(!normalizedJob.terminal);
      writeWorkbenchSession(
        toSessionSnapshot(
          selectedFiles,
          0,
          officePreviewMap,
          normalizedJob,
          nextArtifactMap,
        ),
      );

      const currentPercent = clampProgressPercent(normalizedJob.progress?.progress_ratio || 0);
      const currentFileName = String(normalizedJob.progress?.current_file_name || '').trim();
      setInfoMessage(
        currentFileName
          ? `已提交任务，正在处理 ${currentFileName} · ${currentPercent}%`
          : `已提交任务，等待后端开始解析 · ${currentPercent}%`
      );

      if (normalizedJob.terminal) {
        if (Array.isArray(payload.documents) && payload.documents.length > 0) {
          applyExtractionDocuments(payload.documents);
        } else if (normalizedJob.errors.length > 0) {
          setErrorMessage(normalizedJob.errors.join(' | '));
        }
      } else {
        void pollExtractionJob(normalizedJob.job_id, usedBase);
      }
    } catch (error) {
      console.error(error);
      setErrorMessage(error instanceof Error ? error.message : '抽取失败');
      setActiveSummaryLoading(false);
      setActiveSummaryText("抽取失败，无法生成摘要。");
      setIsProcessing(false);
    }
  };

  const exportResults = () => {
    if (documents.length === 0) return;

    const blob = new Blob([JSON.stringify({ documents }, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `模块二抽取结果_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleZoomIn = () => setScale((prev) => Math.min(prev + 0.1, 2.5));
  const handleZoomOut = () => setScale((prev) => Math.max(prev - 0.1, 0.5));
  const handleRotate = () => setRotation((prev) => (prev + 90) % 360);
  const jumpToPdfPage = (page: number | null | undefined) => {
    if (activeRenderExt !== 'pdf') return;
    const rawPage = Number(page || 0);
    if (!Number.isFinite(rawPage) || rawPage < 1) return;
    const safePage = Math.min(Math.max(1, Math.round(rawPage)), inferredPdfPageCount);
    setPdfViewportPage(safePage);
    setPdfScrollRequest(createPdfScrollRequest(safePage));
  };
  const handlePrevPdfPage = () => {
    jumpToPdfPage(currentPdfPage - 1);
    setActiveFieldKey(null);
  };
  const handleNextPdfPage = () => {
    jumpToPdfPage(currentPdfPage + 1);
    setActiveFieldKey(null);
  };
  const handleResetView = () => {
    setScale(1);
    setRotation(0);
  };

  const writeClipboard = async (text: string, successHint: string) => {
    const payload = String(text || '').trim();
    if (!payload) return;
    try {
      await navigator.clipboard.writeText(payload);
      setInfoMessage(successHint);
      return;
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = payload;
      textarea.setAttribute('readonly', 'true');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setInfoMessage(successHint);
    }
  };

  const tablePreviewToTsv = (headers: string[], rows: string[][]) => {
    const lines: string[] = [];
    if (headers.length > 0) {
      lines.push(headers.join('\t'));
    }
    rows.forEach((row) => lines.push(row.join('\t')));
    return lines.join('\n');
  };

  const handleAssistantConfirm = () => {
    if (!assistantActionable) {
      setAssistantStatus('confirmed');
      setAssistantMessage("已确认：当前无需执行操作。");
      return;
    }
    setAssistantStatus('confirmed');
    setAssistantMessage("已确认保留当前抽取结果。");
  };
  const handleAssistantRollback = () => {
    if (!assistantActionable) {
      setAssistantStatus('rolled_back');
      setAssistantMessage("回滚请求已忽略：当前无可回滚项。");
      return;
    }
    setAssistantStatus('rolled_back');
    setActiveFieldKey(null);
    setTraceHits(toTraceHits(activeDoc, null));
    setAssistantMessage("已执行回滚：定位高亮已重置，你可以重新选择字段或重新抽取。");
  };

  const syncAssistantEvidence = (
    citations: AssistantCitation[],
    nextLock?: AssistantObjectLock | null,
  ) => {
    const normalizedCitations = Array.isArray(citations) ? citations : [];
    const effectiveLock = nextLock === undefined ? assistantCurrentLock : nextLock;
    if (nextLock !== undefined) {
      setAssistantCurrentLock(nextLock);
    }
    if (!activeDoc) return;

    const docHits = Array.isArray(activeDoc.trace_hits) ? activeDoc.trace_hits : [];
    const matched = new Map<string, TraceHit>();
    normalizedCitations.forEach((citation) => {
      const objectType =
        citation.citation_type === 'field'
          ? 'field'
          : citation.citation_type === 'table'
            ? 'table'
            : citation.citation_type === 'figure'
              ? 'figure'
              : '';
      const refId = String(citation.ref_id || '').trim();
      const objectId = String(citation.object_id || '').trim().toLowerCase();
      const exactHits = docHits.filter((hit) => {
        const hitObjectType = String(hit.object_type || '').trim().toLowerCase();
        const hitObjectId = String(hit.object_id || '').trim().toLowerCase();
        const hitRefId = String(hit.ref_id || '').trim();
        if (refId && hitRefId === refId) return true;
        if (!objectId) return false;
        if (hitObjectId !== objectId) return false;
        return !objectType || hitObjectType === objectType;
      });
      if (exactHits.length > 0) {
        exactHits.forEach((hit, idx) => {
          matched.set(toTraceHitKey(hit, idx), hit);
        });
        return;
      }
      const payload = citation.payload && typeof citation.payload === 'object'
        ? citation.payload
        : {};
      const synthetic: TraceHit = {
        file_name: activeDoc.file_name,
        file_hash: activeDoc.file_hash,
        object_type: objectType || 'other',
        object_id: String(citation.object_id || ''),
        ref_id: refId || undefined,
        page: citation.page ?? undefined,
        snippet: String(citation.snippet || citation.title || '').trim(),
        confidence: 0.99,
        locator: payload,
        artifact_url: typeof payload.artifact_url === 'string' ? payload.artifact_url : undefined,
        artifact_path: typeof payload.artifact_path === 'string' ? payload.artifact_path : undefined,
      };
      matched.set(toTraceHitKey(synthetic, matched.size), synthetic);
    });

    if (matched.size > 0) {
      setTraceHits(Array.from(matched.values()));
    } else if (effectiveLock?.table_id) {
      const lockedHits = docHits.filter(
        (hit) =>
          String(hit.object_type || '').trim().toLowerCase() === 'table'
          && String(hit.object_id || '').trim().toLowerCase() === String(effectiveLock.table_id || '').trim().toLowerCase()
      );
      if (lockedHits.length > 0) {
        setTraceHits(lockedHits);
      }
    }

    const firstFieldCitation = normalizedCitations.find((item) => item.citation_type === 'field');
    if (firstFieldCitation?.object_id) {
      setActiveFieldKey(String(firstFieldCitation.object_id).trim() || null);
    } else if (effectiveLock?.lock_type === 'table_row') {
      setActiveFieldKey(null);
    }

    const targetPage = Number(
      effectiveLock?.page
      ?? normalizedCitations.find((item) => Number(item.page || 0) > 0)?.page
      ?? 0
    );
    if (activeRenderExt === 'pdf' && Number.isFinite(targetPage) && targetPage > 0) {
      jumpToPdfPage(targetPage);
    }
  };

  const renderAssistantCitations = (citations?: AssistantCitation[] | null, compact = false) => {
    if (!Array.isArray(citations) || citations.length === 0) return null;
    return (
      <div className={cn("mt-2.5 space-y-2", compact && "mt-2 space-y-1.5")}>
        {citations.slice(0, compact ? 3 : 5).map((citation, idx) => {
          const payload = citation.payload && typeof citation.payload === 'object'
            ? citation.payload
            : {};
          const rowIndex = Number(payload.row_index || 0);
          const sourceRowIndex = Number(payload.source_row_index || 0);
          const figureId = String(payload.figure_id || citation.object_id || '').trim();
          const keyPoints = Array.isArray(payload.key_points)
            ? payload.key_points.map((item) => String(item || '').trim()).filter(Boolean)
            : [];
          const header = String(payload.header || '').trim();
          const value = String(payload.value || '').trim();
          const summaryBits = [
            citation.page ? `第 ${citation.page} 页` : '',
            citation.ref_id ? `ref_id: ${citation.ref_id}` : '',
            rowIndex > 0 ? `表内第 ${rowIndex} 行` : '',
            sourceRowIndex > 0 ? `原始第 ${sourceRowIndex} 行` : '',
            header ? `列: ${header}` : '',
            figureId && citation.citation_type === 'figure' ? `figure_id: ${figureId}` : '',
          ].filter(Boolean);
          return (
            <button
              key={`${citation.object_id}:${citation.ref_id || idx}`}
              type="button"
              onClick={() => syncAssistantEvidence([citation])}
              className={cn(
                "w-full rounded-xl border border-slate-200/80 bg-slate-50/80 px-3 py-2 text-left transition-colors hover:border-blue-300 hover:bg-blue-50/70 dark:border-slate-700/80 dark:bg-slate-950/60 dark:hover:border-blue-500/60 dark:hover:bg-slate-900",
                compact && "rounded-lg px-2.5 py-2"
              )}
              title="定位到该引用证据"
            >
              <div className="flex items-start gap-2">
                <div className={cn(
                  "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-white text-slate-500 ring-1 ring-inset ring-slate-200/70 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700/70",
                  compact && "h-5 w-5 rounded-md"
                )}>
                  {citation.citation_type === 'table' ? (
                    <FileSpreadsheet size={compact ? 11 : 12} />
                  ) : citation.citation_type === 'figure' ? (
                    <FileImage size={compact ? 11 : 12} />
                  ) : (
                    <FileText size={compact ? 11 : 12} />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={cn(
                      "text-[11px] font-semibold text-slate-700 dark:text-slate-100",
                      compact && "text-[10px]"
                    )}>
                      {citation.title || citation.object_id || '引用证据'}
                    </span>
                    <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-500 ring-1 ring-inset ring-slate-200/80 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700/80">
                      {citation.citation_type || 'other'}
                    </span>
                  </div>
                  {summaryBits.length > 0 && (
                    <div className="mt-1 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
                      {summaryBits.join(' · ')}
                    </div>
                  )}
                  {value && citation.citation_type === 'table' && (
                    <div className="mt-1 text-[11px] font-medium text-slate-700 dark:text-slate-200">
                      当前值：{value}
                    </div>
                  )}
                  {keyPoints.length > 0 && (
                    <div className="mt-1 text-[10px] leading-relaxed text-slate-600 dark:text-slate-300">
                      要点：{keyPoints.slice(0, 3).join('；')}
                    </div>
                  )}
                  {!!citation.snippet && (
                    <div className="mt-1 line-clamp-3 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
                      {citation.snippet}
                    </div>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    );
  };

  const renderAssistantActionPreview = (preview?: AssistantActionPreview | null, compact = false) => {
    if (!preview) return null;
    const payload = preview.payload && typeof preview.payload === 'object' ? preview.payload : {};
    const matchedFields = Array.isArray(payload.matched_fields)
      ? payload.matched_fields.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    return (
      <div className={cn(
        "mt-2.5 rounded-2xl border border-amber-200/80 bg-amber-50/80 px-3.5 py-3 text-left dark:border-amber-900/70 dark:bg-amber-950/20",
        compact && "mt-2 rounded-xl px-3 py-2.5"
      )}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-slate-900 dark:text-amber-300 dark:ring-amber-900/70">
            动作预览
          </span>
          <span className="text-[10px] text-amber-700/90 dark:text-amber-200/80">
            {preview.requires_confirmation ? '需确认后执行' : '可直接执行'}
          </span>
        </div>
        <div className="mt-2 text-[12px] font-semibold text-slate-800 dark:text-slate-100">
          {preview.title || '数据库动作预览'}
        </div>
        {preview.description && (
          <div className="mt-1 text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
            {preview.description}
          </div>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-slate-600 dark:text-slate-300">
          {preview.action_type && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              类型：{preview.action_type}
            </span>
          )}
          {preview.target && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              目标：{preview.target}
            </span>
          )}
          {matchedFields.length > 0 && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              字段：{matchedFields.slice(0, 4).join('、')}
            </span>
          )}
        </div>
      </div>
    );
  };

  const renderAssistantDialogMessage = (msg: AssistantDialogMessage, compact = false) => {
    const isAssistant = msg.role === 'assistant';
    const detail = String(msg.payload?.detail || '').trim();
    const toolName = String(msg.payload?.tool_name || '').trim();
    const toolStatus = String(msg.payload?.status || '').trim();
    const isToolStatus = msg.messageType === 'tool_status';
    const contentText = String(msg.content || '').trim();
    return (
      <div
        key={msg.id}
        className={cn(
          compact ? "flex gap-2 max-w-[95%]" : "flex gap-3 max-w-[90%]",
          isAssistant ? "mr-auto" : "ml-auto flex-row-reverse"
        )}
      >
        <div className={cn(
          compact
            ? "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
            : "flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-sm ring-1 ring-inset ring-black/5 backdrop-blur-sm",
          isAssistant
            ? compact
              ? "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400"
              : "bg-white/80 text-blue-600 dark:bg-slate-800/80 dark:text-blue-400"
            : compact
              ? "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
              : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
        )}>
          {isAssistant ? <Bot size={compact ? 12 : 16} /> : <div className="text-[10px] font-bold">{compact ? '我' : 'ME'}</div>}
        </div>
        <div className="min-w-0">
          <div className={cn(
            compact
              ? "rounded-2xl px-3 py-2 text-[11px] leading-relaxed shadow-sm break-words whitespace-pre-wrap"
              : "rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm break-words whitespace-pre-wrap ring-1 ring-inset backdrop-blur-md transition-all hover:shadow-md",
            isAssistant
              ? isToolStatus
                ? compact
                  ? "rounded-tl-none border border-amber-200 bg-amber-50/90 text-amber-800 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-100"
                  : "rounded-tl-none bg-amber-50/90 ring-amber-200/70 text-amber-800 dark:bg-amber-950/20 dark:ring-amber-900/60 dark:text-amber-100"
                : compact
                  ? "rounded-tl-none bg-white border border-slate-100 text-slate-700 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200"
                  : "rounded-tl-none bg-white/80 ring-slate-200/50 text-slate-700 dark:bg-slate-900/80 dark:ring-slate-700/50 dark:text-slate-200"
              : compact
                ? "rounded-tr-none bg-blue-600 text-white"
                : "rounded-tr-none bg-blue-600 ring-blue-600 text-white shadow-blue-500/20 hover:bg-blue-700"
          )}>
            {isToolStatus && (
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[10px] font-semibold">
                <span className="uppercase tracking-wide">工具状态</span>
                {toolName && (
                  <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[9px] text-amber-800 ring-1 ring-inset ring-amber-200 dark:bg-slate-900/80 dark:text-amber-200 dark:ring-amber-900/60">
                    {toolName}
                  </span>
                )}
                {toolStatus && (
                  <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[9px] text-amber-800 ring-1 ring-inset ring-amber-200 dark:bg-slate-900/80 dark:text-amber-200 dark:ring-amber-900/60">
                    {toolStatus}
                  </span>
                )}
              </div>
            )}
            {contentText ? (
              <span>{contentText}</span>
            ) : msg.status === 'streaming' && isAssistant ? (
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.3s]"></span>
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-bounce [animation-delay:-0.15s]"></span>
                <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-bounce"></span>
              </span>
            ) : (
              <span className="text-slate-400 dark:text-slate-500">暂无内容</span>
            )}
            {detail && isToolStatus && (
              <div className="mt-1 text-[10px] leading-relaxed text-amber-700/90 dark:text-amber-100/80">
                {detail}
              </div>
            )}
            {msg.status === 'streaming' && isAssistant && contentText && (
              <div className="mt-2 text-[10px] text-slate-400 dark:text-slate-500">
                正在继续生成回答...
              </div>
            )}
          </div>
          {isAssistant && renderAssistantCitations(msg.citations, compact)}
          {isAssistant && renderAssistantActionPreview(msg.actionPreview, compact)}
        </div>
      </div>
    );
  };

  const renderAssistantLockBanner = (compact = false) => {
    if (!assistantCurrentLock) return null;
    const rowIndex = Number(assistantCurrentLock.row_index || 0);
    const sourceRowIndex = Number(assistantCurrentLock.source_row_index || 0);
    const meta = assistantCurrentLock.metadata && typeof assistantCurrentLock.metadata === 'object'
      ? assistantCurrentLock.metadata
      : {};
    const header = String(meta.header || '').trim();
    const bits = [
      assistantCurrentLock.page ? `第 ${assistantCurrentLock.page} 页` : '',
      rowIndex > 0 ? `表内第 ${rowIndex} 行` : '',
      sourceRowIndex > 0 ? `原始第 ${sourceRowIndex} 行` : '',
      header ? `当前列: ${header}` : '',
    ].filter(Boolean);
    return (
      <div className={cn(
        "rounded-2xl border border-blue-200/70 bg-blue-50/80 px-4 py-3 text-xs text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/20 dark:text-blue-100",
        compact && "rounded-xl px-3 py-2 text-[11px]"
      )}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-blue-700 ring-1 ring-inset ring-blue-200 dark:bg-slate-900 dark:text-blue-300 dark:ring-blue-900/70">
            上下文锁定
          </span>
          <span className="font-semibold">
            {assistantCurrentLock.label || assistantCurrentLock.object_id || '当前对象'}
          </span>
        </div>
        {bits.length > 0 && (
          <div className="mt-1.5 text-[11px] leading-relaxed text-blue-800/90 dark:text-blue-100/80">
            {bits.join(' · ')}
          </div>
        )}
      </div>
    );
  };

  const runAssistantInstruction = async () => {
    if (assistantQueryLoading) {
      assistantAbortRef.current?.abort();
      return;
    }
    const instruction = assistantInput.trim();
    if (!activeDoc) {
      setAssistantWarnings(["当前没有可用文档，请先完成抽取。"]);
      return;
    }
    if (!instruction) {
      setAssistantWarnings(["请输入具体提取需求后再发送。"]);
      return;
    }

    const persistRequested = /(入库|落库|保存|存储|写入数据库|写库)/.test(instruction);
    const webRequested = /(联网|搜索|查一下|最新|最近|政策|法规|新闻|web|google|bing)/i.test(instruction);
    const userDialogMsg: AssistantDialogMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'user',
      content: instruction,
      messageType: 'user_message',
      status: 'done',
    };
    const pendingAssistantId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const pendingAssistantMsg: AssistantDialogMessage = {
      id: pendingAssistantId,
      role: 'assistant',
      content: '',
      messageType: 'assistant_text',
      citations: [],
      actionPreview: null,
      status: 'streaming',
      payload: {},
    };
    setAssistantDialog((prev) => [...prev, userDialogMsg, pendingAssistantMsg]);
    setAssistantQueryLoading(true);
    setAssistantWarnings([]);
    setAssistantAnswer('');
    setAssistantInput('');

    const controller = new AbortController();
    assistantAbortRef.current = controller;
    const fileHash = String(activeDoc.file_hash || '').trim();
    const restoredSessionId = fileHash ? String(readAssistantSessionMap()[fileHash] || '').trim() : '';
    let streamMessageId = pendingAssistantId;

    try {
      const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
      const fetchResult = await fetchExtractWithFallback(
        '/extract/assistant/chat/stream',
        {
          method: 'POST',
          headers: {
            'Accept': 'text/event-stream',
            'Content-Type': 'application/json',
          },
          signal: controller.signal,
          body: JSON.stringify({
            document: activeDoc,
            summary: activeSummaryText,
            user_message: instruction,
            session_id: assistantSessionId || restoredSessionId || undefined,
            persist: persistRequested,
            top_k: 16,
            enable_web_search: webRequested,
            current_object_lock: assistantCurrentLock || undefined,
          }),
        },
        preferredBase,
      );
      extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
      const response = fetchResult.response;
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || '助手处理失败');
      }
      if (!response.body) {
        throw new Error('助手流式响应为空');
      }

      const decoder = new TextDecoder();
      const reader = response.body.getReader();
      let buffer = '';

      const commitSseEvent = (eventName: string, rawData: string) => {
        const normalizedEvent = String(eventName || 'message').trim() || 'message';
        let parsed: Record<string, unknown> = {};
        if (rawData.trim()) {
          try {
            const value = JSON.parse(rawData);
            parsed = value && typeof value === 'object' ? value as Record<string, unknown> : { value };
          } catch {
            parsed = { raw: rawData };
          }
        }

        if (normalizedEvent === 'assistant_start') {
          const nextSessionId = String(parsed.session_id || '').trim();
          const nextAssistantId = String(parsed.assistant_message_id || '').trim();
          if (nextSessionId) {
            setAssistantSessionId(nextSessionId);
            if (fileHash) {
              persistAssistantSessionForFile(fileHash, nextSessionId);
            }
          }
          if (nextAssistantId && nextAssistantId !== streamMessageId) {
            const previousId = streamMessageId;
            streamMessageId = nextAssistantId;
            setAssistantDialog((prev) =>
              prev.map((item) => (item.id === previousId ? { ...item, id: nextAssistantId } : item))
            );
          }
          return;
        }

        if (normalizedEvent === 'tool_status') {
          const toolMessage: AssistantDialogMessage = {
            id: `tool-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            role: 'assistant',
            content: String(parsed.message || '工具已执行').trim(),
            messageType: 'tool_status',
            citations: [],
            actionPreview: null,
            status: 'done',
            payload: {
              tool_name: parsed.tool_name,
              status: parsed.status,
              detail: parsed.detail,
            },
          };
          setAssistantDialog((prev) => [...prev, toolMessage]);
          return;
        }

        if (normalizedEvent === 'citation_bundle') {
          const citations = Array.isArray(parsed.citations)
            ? parsed.citations as AssistantCitation[]
            : [];
          const nextLock = parsed.current_object_lock && typeof parsed.current_object_lock === 'object'
            ? parsed.current_object_lock as AssistantObjectLock
            : null;
          updateAssistantDialogMessage(streamMessageId, (current) => ({
            ...current,
            citations: citations.length > 0 ? citations : current.citations,
            payload: {
              ...(current.payload || {}),
              current_object_lock: nextLock,
            },
          }));
          syncAssistantEvidence(citations, nextLock);
          return;
        }

        if (normalizedEvent === 'action_preview') {
          const preview = parsed && typeof parsed === 'object'
            ? parsed as AssistantActionPreview
            : null;
          updateAssistantDialogMessage(streamMessageId, (current) => ({
            ...current,
            actionPreview: preview,
            payload: {
              ...(current.payload || {}),
              action_preview: preview,
            },
          }));
          return;
        }

        if (normalizedEvent === 'assistant_delta') {
          const deltaText = String(parsed.text || '');
          updateAssistantDialogMessage(streamMessageId, (current) => ({
            ...current,
            content: `${current.content || ''}${deltaText}`,
            status: 'streaming',
          }));
          return;
        }

        if (normalizedEvent === 'assistant_done') {
          const citations = Array.isArray(parsed.citations)
            ? parsed.citations as AssistantCitation[]
            : [];
          const actionPreview = parsed.action_preview && typeof parsed.action_preview === 'object'
            && Object.keys(parsed.action_preview as Record<string, unknown>).length > 0
            ? parsed.action_preview as AssistantActionPreview
            : null;
          const nextLock = parsed.current_object_lock && typeof parsed.current_object_lock === 'object'
            && Object.keys(parsed.current_object_lock as Record<string, unknown>).length > 0
            ? parsed.current_object_lock as AssistantObjectLock
            : null;
          const nextAnswer = String(parsed.answer || '').trim() || '助手已完成处理。';
          setAssistantAnswer(nextAnswer);
          setAssistantMessage(nextAnswer);
          setAssistantWarnings(Array.isArray(parsed.warnings) ? parsed.warnings.map((item) => String(item || '')) : []);
          updateAssistantDialogMessage(streamMessageId, (current) => ({
            ...current,
            content: nextAnswer,
            messageType: 'assistant_text',
            citations: citations.length > 0 ? citations : current.citations,
            actionPreview: actionPreview ?? current.actionPreview ?? null,
            status: 'done',
            payload: {
              ...(current.payload || {}),
              route: parsed.route,
              warnings: parsed.warnings,
              current_object_lock: nextLock,
            },
          }));
          syncAssistantEvidence(citations, nextLock);
          return;
        }

        if (normalizedEvent === 'assistant_error') {
          const message = String(parsed.message || parsed.error || '助手处理失败').trim();
          throw new Error(message);
        }
      };

      const flushBuffer = () => {
        const normalized = buffer.replace(/\r\n/g, '\n');
        const blocks = normalized.split('\n\n');
        buffer = blocks.pop() || '';
        blocks.forEach((block) => {
          const lines = block.split('\n').map((line) => line.trimEnd()).filter(Boolean);
          if (lines.length === 0) return;
          let eventName = 'message';
          const dataLines: string[] = [];
          lines.forEach((line) => {
            if (line.startsWith('event:')) {
              eventName = line.slice(6).trim();
              return;
            }
            if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trim());
            }
          });
          commitSseEvent(eventName, dataLines.join('\n'));
        });
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        flushBuffer();
      }
      buffer += decoder.decode();
      flushBuffer();
      if (buffer.trim()) {
        commitSseEvent('message', buffer.trim());
      }
    } catch (error) {
      if (controller.signal.aborted) {
        setAssistantWarnings(["本次回答已停止。"]);
        setAssistantDialog((prev) =>
          prev.flatMap((item) => {
            if (item.id !== streamMessageId) return [item];
            if (String(item.content || '').trim()) {
              return [{ ...item, status: 'done' }];
            }
            return [];
          })
        );
      } else {
        const message = error instanceof Error ? error.message : '助手处理失败';
        setAssistantWarnings([message]);
        const failedAnswer = "助手处理失败，请检查指令后重试。";
        setAssistantAnswer(failedAnswer);
        setAssistantDialog((prev) => {
          const hasTarget = prev.some((item) => item.id === streamMessageId);
          if (!hasTarget) {
            return [
              ...prev,
              {
                id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                role: 'assistant',
                content: failedAnswer,
                messageType: 'assistant_text',
                status: 'error',
              },
            ];
          }
          return prev.map((item) =>
            item.id === streamMessageId
              ? {
                  ...item,
                  content: String(item.content || '').trim() || failedAnswer,
                  status: 'error',
                }
              : item
          );
        });
      }
    } finally {
      if (assistantAbortRef.current === controller) {
        assistantAbortRef.current = null;
      }
      setAssistantQueryLoading(false);
    }
  };

  const workbenchGridClass = showLeftPanel
    ? "grid h-full flex-1 min-h-0 items-stretch gap-3 grid-cols-[216px_minmax(0,1fr)_336px] grid-rows-[minmax(0,1fr)] transition-[grid-template-columns] duration-300 ease-out"
    : "grid h-full flex-1 min-h-0 items-stretch gap-3 grid-cols-[minmax(0,1fr)_336px] grid-rows-[minmax(0,1fr)] transition-[grid-template-columns] duration-300 ease-out";
  const rightPanelClass = "flex h-full min-h-0 w-full min-w-0 shrink-0 self-stretch flex-col";
  const pendingExtractionCount = selectedFiles.length;
  const showBatchExtractAction = pendingExtractionCount > 0;
  const extractionOverallPercent = clampProgressPercent(extractionJob?.progress?.progress_ratio || 0);
  const batchExtractLabel = isProcessing
    ? `正在提取（${extractionOverallPercent}%）`
    : pendingExtractionCount > 1
      ? `开始批量提取（${pendingExtractionCount}）`
      : '开始提取';
  const smartUnitTrackClass = cn(
    "flex h-full w-[200%] transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] will-change-transform",
    smartUnitTab === 'results' ? "translate-x-0" : "-translate-x-1/2"
  );
  const showTraceOverlay = false;
  const previewControlsDisabled = !hasPreviewContent;
  const previewFocusButtonTitle = '聚焦预览并隐藏全局文件夹';
  const restoreFolderButtonTitle = '展开全局文件夹并退出聚焦预览';
  const assistantPanel = (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-transparent">
      <div className="px-4 py-3 bg-transparent">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-xs font-bold text-slate-600 uppercase tracking-wider dark:text-slate-300">
            <Sparkles size={14} className="text-blue-600 dark:text-blue-400" />
            智能助手
          </h3>
          <button
            onClick={() => setShowAssistantHelp(true)}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-blue-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-blue-400"
            aria-label="查看助手功能说明"
          >
            <HelpCircle size={14} />
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div ref={assistantDialogRef} data-testid="module2-assistant-dialog" className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 custom-scrollbar">
          {/* Summary Section */}
          <div className="rounded-2xl border border-slate-200/50 bg-white/40 px-5 py-4 text-xs leading-relaxed text-slate-600 shadow-sm backdrop-blur-md transition-all hover:bg-white/60 dark:border-slate-800/50 dark:bg-slate-900/40 dark:text-slate-300 dark:hover:bg-slate-900/60">
            <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
              <Sparkles size={14} />
              智能摘要
            </div>
            <p data-testid="module2-summary-text" className="whitespace-pre-wrap break-words font-medium text-slate-700 dark:text-slate-200">
              {activeSummaryLoading ? (
                <span className="flex items-center gap-2 text-slate-500">
                  <Loader2 size={12} className="animate-spin" />
                  正在生成文档摘要...
                </span>
              ) : (
                activeSummaryText || "上传文件并执行抽取后，摘要会自动展示。"
              )}
            </p>
          </div>

          {renderAssistantLockBanner()}

          {/* Chat History */}
          {assistantDialog.map((msg) => renderAssistantDialogMessage(msg))}

          {/* Assistant Answer (Legacy support) */}
          {assistantAnswer && !assistantDialog.some(m => m.content === assistantAnswer) && (
            <div data-testid="module2-assistant-answer" className="rounded-xl border border-blue-200 bg-blue-50/50 px-3 py-2.5 text-[11px] text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
              {assistantAnswer}
            </div>
          )}

          {/* Warnings */}
          {assistantWarnings.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/50 px-3 py-2.5 text-[11px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              {assistantWarnings.join('；')}
            </div>
          )}

          {/* Spacer for scrolling */}
          <div className="h-4" />
        </div>

        {/* Input Area */}
        <div className="border-t border-slate-100/50 bg-white/60 p-4 backdrop-blur-md dark:border-slate-800/50 dark:bg-slate-900/60">
          <div className="relative group">
            <textarea
              ref={assistantInputRef}
              data-testid="module2-assistant-input"
              value={assistantInput}
              onChange={(e) => setAssistantInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (!assistantQueryLoading && activeDoc) {
                    void runAssistantInstruction();
                  }
                }
              }}
              placeholder={activeDoc ? "输入需求，回车发送..." : "请先抽取文档..."}
              className="max-h-24 min-h-[40px] w-full resize-none rounded-2xl border-none bg-slate-100/80 px-4 py-2.5 pr-10 text-xs leading-relaxed text-slate-700 shadow-inner outline-none transition-all focus:bg-white focus:ring-2 focus:ring-blue-500/20 dark:bg-slate-800/80 dark:text-slate-200 dark:focus:bg-slate-900"
            />
            <button
              type="button"
              data-testid="module2-assistant-send"
              onClick={() => void runAssistantInstruction()}
              disabled={!activeDoc || (!assistantQueryLoading && !assistantInput.trim())}
              className={cn(
                'absolute bottom-1.5 right-1.5 inline-flex h-7 w-7 items-center justify-center rounded-full transition-all duration-200',
                !activeDoc || (!assistantQueryLoading && !assistantInput.trim())
                  ? 'cursor-not-allowed bg-slate-200 text-slate-400 dark:bg-slate-700 dark:text-slate-500'
                  : assistantQueryLoading
                    ? 'bg-amber-500 text-white shadow-md shadow-amber-500/30 hover:bg-amber-600 hover:shadow-lg hover:scale-105 active:scale-95'
                    : 'bg-blue-600 text-white shadow-md shadow-blue-500/30 hover:bg-blue-700 hover:shadow-lg hover:scale-105 active:scale-95'
              )}
              title={assistantQueryLoading ? "停止本次回答" : "发送"}
            >
              {assistantQueryLoading ? <X size={12} /> : <Send size={12} className="ml-0.5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  const isPageBased = useMemo(() => {
    return (
      activeRenderExt === 'pdf' ||
      activeExt === 'doc' ||
      activeExt === 'docx' ||
      IMAGE_EXTENSIONS.has(activeExt)
    );
  }, [activeRenderExt, activeExt]);

  return (
    <div className="relative flex h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-100 p-1.5 text-foreground dark:border-slate-700 dark:bg-slate-950">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.doc,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg,.bmp,.webp,.tif,.tiff"
        multiple
        className="hidden"
        data-testid="module2-file-input"
        onChange={onSelectFiles}
      />

      <div className={workbenchGridClass}>
        {showLeftPanel && (
          <div
            id="module2-left-panel"
            data-testid="module2-left-panel"
            className="flex h-full min-h-0 flex-col gap-2"
          >
            <div 
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                "flex flex-1 min-h-[300px] flex-col overflow-hidden rounded-xl border bg-slate-50 shadow-sm transition-colors duration-200 dark:bg-slate-900",
                isUploaderDragOver 
                  ? "border-blue-400 ring-2 ring-blue-200 dark:border-blue-600 dark:ring-blue-800"
                  : "border-slate-200 dark:border-slate-700"
              )}
            >
              <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
                <FolderOpen size={18} className="text-slate-700 dark:text-slate-300" />
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
                  全局文件夹
                </h3>
              </div>

              {selectedFiles.length > 0 && (
                <div className="border-b border-slate-100 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                  >
                    <Plus size={16} />
                    添加新文件
                  </button>
                </div>
              )}

              <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-0 custom-scrollbar dark:bg-slate-950/30">
                {selectedFiles.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center gap-2 py-8 text-center text-slate-400 opacity-60">
                    <FolderOpen size={24} className="text-slate-300 dark:text-slate-600" />
                    <p className="text-xs">请在主视窗上传文件</p>
                  </div>
                ) : (
                  <div className="divide-y divide-slate-100 dark:divide-slate-800">
                    {selectedFiles.map((file, index) => {
                      const isActive = activeSourceFile && fileIdentityKey(activeSourceFile) === fileIdentityKey(file);
                      const ext = file.name.split('.').pop()?.toLowerCase();
                      
                      let FileIcon = File;
                      let iconColorClass = "text-slate-500";
                      
                      if (ext === 'pdf') {
                        FileIcon = FileText;
                        iconColorClass = "text-red-500";
                      } else if (['xls', 'xlsx', 'csv'].includes(ext || '')) {
                        FileIcon = FileSpreadsheet;
                        iconColorClass = "text-emerald-500";
                      } else if (['doc', 'docx'].includes(ext || '')) {
                        FileIcon = FileText;
                        iconColorClass = "text-blue-500";
                      } else if (['jpg', 'jpeg', 'png', 'gif'].includes(ext || '')) {
                        FileIcon = FileImage;
                        iconColorClass = "text-purple-500";
                      }

                      // Status Logic
                      const doc = documents[index];
                      const jobFile = pickExtractionJobFileState(extractionJob, file, index);
                      let statusText = "等待队列...";
                      let statusColor = "text-slate-400";
                      let StatusIndicator = <div className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />;
                      
                      if (jobFile && !extractionJob?.terminal) {
                         const progress = clampProgressPercent(jobFile.progress_ratio);
                         const message = String(jobFile.message || jobFile.stage || '正在解析').trim() || '正在解析';
                         if (jobFile.status === 'failed') {
                             statusText = jobFile.error ? `解析失败：${jobFile.error}` : '解析失败';
                             statusColor = "text-red-500";
                             StatusIndicator = <div className="h-2 w-2 rounded-full bg-red-500" />;
                         } else if (jobFile.status === 'completed') {
                             statusText = jobFile.message || '解析完成';
                             statusColor = "text-emerald-600";
                             StatusIndicator = <div className="h-2 w-2 rounded-full bg-emerald-500" />;
                         } else {
                             statusText = progress > 0 ? `${message} ${progress}%` : message;
                             statusColor = jobFile.status === 'queued' ? "text-slate-400" : "text-slate-500";
                             StatusIndicator = (
                               <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                 <div
                                   className="h-full bg-blue-500 transition-all duration-500"
                                   style={{ width: `${Math.max(progress, jobFile.status === 'queued' ? 8 : 4)}%` }}
                                 />
                               </div>
                             );
                         }
                      } else if (jobFile) {
                         if (jobFile.status === 'failed') {
                             statusText = jobFile.error ? `解析失败：${jobFile.error}` : '解析失败';
                             statusColor = "text-red-500";
                             StatusIndicator = <div className="h-2 w-2 rounded-full bg-red-500" />;
                         } else if (jobFile.status === 'completed') {
                             statusText = jobFile.message || '解析完成';
                             statusColor = "text-emerald-600";
                             StatusIndicator = <div className="h-2 w-2 rounded-full bg-emerald-500" />;
                         }
                      } else if (doc) {
                         if (doc.errors.length > 0) {
                             statusText = "解析异常";
                             statusColor = "text-red-500";
                             StatusIndicator = <div className="h-2 w-2 rounded-full bg-red-500" />;
                         } else {
                             statusText = "解析完成";
                             statusColor = "text-emerald-600";
                             StatusIndicator = <div className="h-2 w-2 rounded-full bg-emerald-500" />;
                         }
                      }

                      return (
                        <div 
                          key={`${file.name}:${index}`}
                          onClick={() => setActiveDocIndex(index)}
                          className={cn(
                            "group relative flex cursor-pointer items-start gap-3 bg-white px-4 py-3 transition-colors hover:bg-slate-50 dark:bg-slate-900 dark:hover:bg-slate-800",
                            isActive && "bg-slate-100 dark:bg-slate-800"
                          )}
                        >
                          {isActive && (
                              <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-600 dark:bg-blue-500" />
                          )}

                          <div className="mt-0.5 shrink-0">
                            <FileIcon size={24} className={iconColorClass} strokeWidth={1.5} />
                          </div>
                          
                          <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between gap-2">
                                  <p className={cn("truncate text-sm font-bold text-slate-700 dark:text-slate-200", isActive && "text-slate-900 dark:text-white")}>
                                      {file.name}
                                  </p>
                                  <button
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      removeFile(index);
                                    }}
                                    className="hidden rounded p-1 text-slate-400 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:block group-hover:opacity-100 dark:hover:bg-red-900/20"
                                  >
                                    <Trash2 size={14} />
                                  </button>
                              </div>
                              
                              <div className="mt-1 flex min-w-0 items-center gap-2">
                                  {StatusIndicator}
                                  <span className={cn("min-w-0 truncate text-[10px] font-medium", statusColor)}>
                                      {statusText}
                                  </span>
                              </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="border-t border-slate-200 p-3 dark:border-slate-700">
                <div className="flex">
                  <button
                    onClick={() => setShowSchema(!showSchema)}
                    className={cn(
                      'flex w-full items-center justify-center rounded-lg border px-2.5 py-2 text-xs font-bold transition-colors',
                      showSchema
                        ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/20 dark:text-blue-300'
                        : 'border-slate-300 bg-white text-slate-700 hover:border-blue-200 hover:text-blue-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-blue-700 dark:hover:text-blue-300'
                    )}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      <Settings size={13} />
                      {showSchema ? '收起规则' : '配置规则'}
                    </span>
                  </button>
                </div>
              </div>
            </div>
            {false && (
            <div className="absolute bottom-2 right-2 z-30 flex h-[36vh] w-[372px] min-h-[280px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white p-3 shadow-xl dark:border-slate-700 dark:bg-slate-900">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-100">
                  <Bot size={16} className="text-blue-500" />
                  沉浸式伴聊助手（智能桥接）
                </h3>
                <button
                  onClick={() => setShowAssistantHelp(true)}
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-blue-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-blue-400"
                  aria-label="查看助手功能说明"
                >
                  <HelpCircle size={14} />
                </button>
              </div>

              <div className="flex min-h-0 flex-1 flex-col">
                <div ref={assistantDialogRef} data-testid="module2-assistant-dialog" className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 custom-scrollbar">
                  {/* Summary Section */}
                  <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-[11px] leading-relaxed text-slate-600 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200">
                    <div className="mb-1 flex items-center gap-1.5 text-[10px] font-bold text-blue-600 dark:text-blue-300">
                      <Sparkles size={11} />
                      智能摘要
                    </div>
                    <p data-testid="module2-summary-text" className="whitespace-pre-wrap break-words">
                      {activeSummaryLoading ? "正在生成文档摘要..." : (activeSummaryText || "上传文件并执行抽取后，摘要会自动展示。")}
                    </p>
                  </div>

                  {renderAssistantLockBanner(true)}

                  {/* Chat History */}
                  {assistantDialog.map((msg) => renderAssistantDialogMessage(msg, true))}

                  {/* Assistant Answer (Legacy support if needed, but better integrated above) */}
                  {assistantAnswer && !assistantDialog.some(m => m.content === assistantAnswer) && (
                     <div data-testid="module2-assistant-answer" className="rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-2 text-[11px] text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
                        {assistantAnswer}
                     </div>
                  )}
                  
                  {/* Warnings */}
                  {assistantWarnings.length > 0 && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                      {assistantWarnings.join('；')}
                    </div>
                  )}

                  {/* Spacer for scrolling */}
                  <div className="h-2" />
                </div>

                {/* Input Area */}
                <div className="border-t border-slate-200 bg-slate-50/50 p-2 dark:border-slate-700 dark:bg-slate-900/50">


                  <div className="relative">
                    <textarea
                      ref={assistantInputRef}
                      data-testid="module2-assistant-input"
                      value={assistantInput}
                      onChange={(e) => setAssistantInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          if (!assistantQueryLoading && activeDoc) {
                            void runAssistantInstruction();
                          }
                        }
                      }}
                      placeholder={activeDoc ? "输入需求，回车发送..." : "请先抽取文档..."}
                      className="max-h-24 min-h-[40px] w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 pr-9 text-xs leading-relaxed text-slate-700 outline-none transition-colors focus:border-blue-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-blue-600"
                    />
                    <button
                      type="button"
                      data-testid="module2-assistant-send"
                      onClick={() => void runAssistantInstruction()}
                      disabled={!activeDoc || (!assistantQueryLoading && !assistantInput.trim())}
                      className={cn(
                        'absolute bottom-1.5 right-1.5 inline-flex h-7 w-7 items-center justify-center rounded-lg transition-colors',
                        !activeDoc || (!assistantQueryLoading && !assistantInput.trim())
                          ? 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-600'
                          : assistantQueryLoading
                            ? 'bg-amber-500 text-white hover:bg-amber-600'
                            : 'bg-blue-600 text-white hover:bg-blue-700'
                      )}
                      title={assistantQueryLoading ? "停止本次回答" : "发送"}
                    >
                      {assistantQueryLoading ? <X size={12} /> : <Send size={12} />}
                    </button>
                  </div>
                </div>
              </div>
            </div>)}
          </div>
        )}


      {/* CENTER: Workbench Area */}
      <div className="relative flex h-full min-h-0 flex-col gap-2">
        {/* Schema Editor Overlay */}
        {showSchema && (
            <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[90%] max-w-2xl z-50 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl shadow-2xl rounded-2xl animate-in slide-in-from-top-4 fade-in duration-200 flex flex-col max-h-[500px] border border-slate-200 dark:border-slate-700 overflow-hidden ring-1 ring-slate-900/5">
                    <div className="p-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/50">
                    <h3 className="text-xs font-bold font-['Microsoft_YaHei'] flex items-center gap-2 text-slate-700 dark:text-slate-200">
                        <Braces size={14} className="text-blue-500" /> 规则模板配置
                    </h3>
                    <div className="flex gap-2">
                            <button onClick={() => setSchemaText(JSON.stringify(DEFAULT_SCHEMA, null, 2))} className="text-[10px] text-blue-500 hover:underline px-2 font-medium">恢复智能规则</button>
                            <button onClick={() => setShowSchema(false)} className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors text-slate-500"><X size={14}/></button>
                    </div>
                    </div>
                    <textarea
                    value={schemaText}
                    onChange={(e) => setSchemaText(e.target.value)}
                    className="flex-1 w-full bg-transparent p-4 font-mono text-xs outline-none resize-none text-slate-700 dark:text-slate-300 placeholder:text-slate-400"
                    spellCheck={false}
                />
            </div>
        )}

        {/* Main Canvas with Floating Toolbar */}
        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
            {/* Dot Grid Background */}
            <div className="absolute inset-0 opacity-0 pointer-events-none -z-10" 
                 style={{ backgroundImage: 'radial-gradient(circle, #cbd5e1 1.5px, transparent 1.5px)', backgroundSize: '24px 24px' }}>
            </div>

            {/* Fixed Header Toolbar */}
            <div className="relative z-20 flex w-full items-center gap-2 border-b border-slate-200 bg-slate-50 px-2.5 py-2 sm:px-3 dark:border-slate-700 dark:bg-slate-900">
                <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
                     {showLeftPanel && (
                        <button
                          type="button"
                          onClick={() => setIsPreviewFocused(true)}
                          className="group inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-transparent text-blue-600 transition-all duration-200 active:scale-95 hover:border-slate-200 hover:bg-white hover:text-blue-700 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 dark:text-blue-400 dark:hover:border-slate-700 dark:hover:bg-slate-800"
                          title={previewFocusButtonTitle}
                          aria-label={previewFocusButtonTitle}
                          aria-pressed={false}
                          aria-expanded={showLeftPanel}
                          aria-controls="module2-left-panel"
                          data-testid="module2-preview-focus-toggle"
                        >
                          <span className="transition-transform duration-200 ease-out group-hover:scale-105">
                            <Maximize size={16} strokeWidth={2.2} />
                          </span>
                        </button>
                      )}

                     {!showLeftPanel && (
                        <motion.button
                          type="button"
                          layout
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ duration: 0.18, ease: 'easeOut' }}
                          onClick={() => setIsPreviewFocused(false)}
                          className="ml-1 inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 shadow-sm transition-all duration-200 hover:border-blue-200 hover:bg-blue-50/60 hover:text-blue-700 hover:shadow-md active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-blue-700 dark:hover:bg-slate-800 dark:hover:text-blue-300"
                          title={restoreFolderButtonTitle}
                          aria-label={restoreFolderButtonTitle}
                          aria-controls="module2-left-panel"
                          aria-expanded={false}
                          data-testid="module2-restore-left-panel"
                        >
                          <FolderOpen size={14} />
                          <span className="hidden sm:inline">全局文件夹</span>
                        </motion.button>
                      )}

                     {activeDoc || activeSourceFile ? (
                        <div className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-bold font-['Microsoft_YaHei'] text-slate-900 dark:text-slate-100">{activeDisplayName}</span>
                            <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[10px] font-bold font-['Microsoft_YaHei'] text-slate-500">
                                {activeDoc ? (
                                    <>
                                        <span className={cn("h-2 w-2 rounded-full shrink-0", activeDoc.cached ? "bg-emerald-500" : "bg-amber-500")} />
                                        <span className="truncate">{activeDoc.cached ? "已缓存" : "实时预览"}</span>
                                    </>
                                ) : (
                                    <>
                                        <span className="h-2 w-2 rounded-full shrink-0 bg-blue-500" />
                                        <span className="truncate">待提取</span>
                                    </>
                                )}
                            </span>
                        </div>
                     ) : (
                         <div className="flex min-w-0 items-center gap-2 text-slate-900 dark:text-slate-100">
                           <span className="truncate text-sm font-bold font-['Microsoft_YaHei']">
                               {isSidebarCollapsed ? "预览视窗" : "文档预览"}
                           </span>
                        </div>
                     )}
                </div>

                <div className="ml-auto flex min-w-0 items-center gap-2 sm:gap-2.5">
                  <div className="flex items-center gap-1">
                    <button
                        onClick={handleZoomOut}
                        disabled={previewControlsDisabled}
                        className={cn(
                          "p-1.5 rounded-lg transition-colors active:scale-95 shrink-0",
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="缩小"
                        aria-label="缩小预览"
                    >
                      <ZoomOut size={16} strokeWidth={2}/>
                    </button>
                    <span className="w-9 shrink-0 text-center text-xs font-bold font-mono text-slate-900 dark:text-slate-100">{Math.round(scale * 100)}%</span>
                    <button
                        onClick={handleZoomIn}
                        disabled={previewControlsDisabled}
                        className={cn(
                          "p-1.5 rounded-lg transition-colors active:scale-95 shrink-0",
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="放大"
                        aria-label="放大预览"
                    >
                      <ZoomIn size={16} strokeWidth={2}/>
                    </button>
                    <button
                        onClick={handleRotate}
                        disabled={previewControlsDisabled}
                        className={cn(
                          "p-1.5 rounded-lg transition-colors ml-0.5 active:scale-95 shrink-0",
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="旋转"
                        aria-label="旋转预览"
                    >
                      <RotateCw size={16} strokeWidth={2}/>
                    </button>
                    <button
                        onClick={handleResetView}
                        disabled={previewControlsDisabled}
                        className={cn(
                          "p-1.5 rounded-lg transition-colors active:scale-95 shrink-0",
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="重置视图"
                        aria-label="重置预览视图"
                    >
                      <RefreshCcw size={16} strokeWidth={2}/>
                    </button>

                    {activeRenderExt === 'pdf' && (
                        <>
                            <div className="mx-1.5 h-5 w-px shrink-0 bg-slate-200 dark:bg-slate-600" />
                            <div className="flex items-center gap-1 shrink-0">
                                <button
                                    onClick={handlePrevPdfPage}
                                    disabled={currentPdfPage <= 1}
                                    className={cn(
                                        "p-1.5 rounded-lg transition-colors active:scale-95 shrink-0",
                                        currentPdfPage > 1
                                            ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800 dark:text-slate-200"
                                            : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                    )}
                                    title="上一页"
                                >
                                    <ChevronRight size={16} className="rotate-180" />
                                </button>
                                <span className="min-w-[52px] shrink-0 text-center text-xs font-bold font-mono text-slate-900 dark:text-slate-100">
                                    {`${currentPdfPage} / ${inferredPdfPageCount}`}
                                </span>
                                <button
                                    onClick={handleNextPdfPage}
                                    disabled={currentPdfPage >= inferredPdfPageCount}
                                    className={cn(
                                        "p-1.5 rounded-lg transition-colors active:scale-95 shrink-0",
                                        currentPdfPage < inferredPdfPageCount
                                            ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800 dark:text-slate-200"
                                            : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                    )}
                                    title="下一页"
                                >
                                    <ChevronRight size={16} />
                                </button>
                            </div>
                        </>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 border-l border-slate-200/80 pl-2 dark:border-slate-700/80">
                    {showBatchExtractAction && (
                      <span className="hidden rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-blue-600 sm:inline-flex dark:bg-blue-900/30 dark:text-blue-300">
                        待处理 {pendingExtractionCount} 份
                      </span>
                    )}
                    {showBatchExtractAction && (
                        <button
                            onClick={runExtraction}
                            data-testid="module2-start-extract"
                            disabled={isProcessing}
                            className={cn(
                                "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold font-['Microsoft_YaHei'] transition-all shadow-sm active:scale-95 shrink-0 whitespace-nowrap sm:px-3",
                                isProcessing
                                ? "bg-slate-100 text-slate-400 cursor-not-allowed dark:bg-slate-800 dark:text-slate-600"
                                : "bg-blue-600 text-white hover:bg-blue-700 hover:shadow-blue-500/25"
                            )}
                        >
                            {isProcessing ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} strokeWidth={2.5} />}
                            <span>{batchExtractLabel}</span>
                        </button>
                    )}
                    {documents.length > 0 && (
                        <button
                            onClick={exportResults}
                            disabled={documents.length === 0}
                            className={cn(
                                "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold font-['Microsoft_YaHei'] transition-all shadow-sm active:scale-95 shrink-0 whitespace-nowrap sm:px-3",
                                documents.length > 0
                                ? "bg-slate-100 text-slate-700 hover:bg-slate-200 hover:text-blue-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                                : "opacity-50 bg-slate-50 text-slate-400 cursor-not-allowed dark:bg-slate-900 dark:text-slate-600"
                            )}
                        >
                            <Download size={14} strokeWidth={2.5} />
                            <span>导出结果</span>
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={clearWorkbenchData}
                        data-testid="module2-clear-data"
                        disabled={!canClearWorkbenchData || isProcessing}
                        aria-label="清空当前页面数据"
                        title="一键清空当前页面数据与本地缓存"
                        className={cn(
                            "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-bold font-['Microsoft_YaHei'] transition-all shadow-sm active:scale-95 shrink-0 whitespace-nowrap sm:px-3",
                            canClearWorkbenchData && !isProcessing
                              ? "border border-red-200 bg-white text-red-600 hover:bg-red-50 hover:border-red-300 dark:border-red-900/60 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-950/30"
                              : "cursor-not-allowed border border-slate-200 bg-slate-50 text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-600"
                        )}
                    >
                        <Trash2 size={14} strokeWidth={2.2} />
                        <span>清空数据</span>
                    </button>
                  </div>
                </div>
            </div>

            <div className="relative z-10 flex flex-1 items-center justify-center overflow-auto p-1.5 sm:p-3 lg:p-4 custom-scrollbar">
                 {selectedFiles.length === 0 ? (
                    <div
                     data-testid="module2-center-uploader"
                     onClick={() => fileInputRef.current?.click()}
                     onDragEnter={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsUploaderDragOver(true);
                    }}
                     onDragOver={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsUploaderDragOver(true);
                    }}
                    onDragLeave={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsUploaderDragOver(false);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setIsUploaderDragOver(false);
                      const dropped = Array.from(e.dataTransfer?.files ?? []) as File[];
                      mergeSelectedFiles(dropped);
                    }}
                    className={cn(
                      "group relative flex h-full w-full select-none cursor-pointer flex-col items-center justify-center overflow-hidden rounded-3xl border-2 border-dashed bg-slate-50/50 transition-all duration-300",
                      isUploaderDragOver
                        ? "border-blue-500 bg-blue-50/70 shadow-lg shadow-blue-500/15 dark:border-blue-400 dark:bg-blue-900/20"
                        : "border-slate-300 hover:border-blue-400 hover:bg-blue-50/50 hover:shadow-lg hover:shadow-blue-500/5 dark:border-slate-700 dark:bg-slate-900/30 dark:hover:border-blue-500/50 dark:hover:bg-blue-900/10"
                    )}
                  >
                     {/* Creative Background Elements */}
                     <div className="absolute inset-0 opacity-0 transition-opacity duration-700 group-hover:opacity-100 pointer-events-none">
                        <div className="absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full bg-blue-100/30 blur-[100px] dark:bg-[#7E92B5]/10" />
                     </div>
 
                     {/* Main 3D Container */}
                     <div className="relative z-10 mb-8 h-32 w-32 perspective-[1000px] pointer-events-none">
                        {/* Floating Card System */}
                        <div className="relative h-full w-full transition-transform duration-500 group-hover:scale-110">
                            
                            {/* Bottom Card - Data Layer */}
                            <div className="absolute inset-0 rounded-2xl border border-slate-200 bg-white/80 shadow-sm transition-all duration-500 ease-out group-hover:-translate-y-4 group-hover:-translate-x-6 group-hover:-rotate-12 dark:border-slate-700 dark:bg-slate-800/80 flex flex-col p-3 gap-2 opacity-60">
                                <div className="h-1.5 w-2/3 rounded-full bg-slate-200 dark:bg-slate-600"/>
                                <div className="h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-600"/>
                                <div className="h-1.5 w-4/5 rounded-full bg-slate-200 dark:bg-slate-600"/>
                            </div>
 
                            {/* Middle Card - Structure Layer */}
                            <div className="absolute inset-0 rounded-2xl border border-slate-200 bg-white/90 shadow-md transition-all duration-500 ease-out group-hover:-translate-y-8 group-hover:translate-x-6 group-hover:rotate-12 dark:border-slate-700 dark:bg-slate-800/90 flex items-center justify-center opacity-80">
                                <div className="h-12 w-16 rounded border border-dashed border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700/50 flex items-center justify-center">
                                    <ScanLine size={16} className="text-slate-400 dark:text-slate-500" />
                                </div>
                            </div>
 
                            {/* Top Card - Action Layer */}
                            <div className="absolute inset-0 flex items-center justify-center rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 shadow-xl transition-all duration-500 cubic-bezier(0.34, 1.56, 0.64, 1) group-hover:-translate-y-12 group-hover:scale-110 group-hover:shadow-blue-200/50 dark:border-slate-600 dark:from-slate-800 dark:to-slate-900 z-20">
                                <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm border border-slate-100 text-blue-400 transition-all duration-500 group-hover:bg-blue-500 group-hover:text-white group-hover:border-blue-500 group-hover:rotate-0 dark:bg-slate-800 dark:border-slate-700 dark:text-[#8DA3C1]">
                                    <UploadCloud size={28} className="transition-all duration-500 group-hover:scale-110" />
                                    {/* Ripple Effect Ring */}
                                    <div className="absolute inset-0 rounded-2xl border-2 border-blue-200 opacity-0 transition-all duration-700 group-hover:animate-ping group-hover:opacity-100"/>
                                </div>
                            </div>
 
                            {/* Shadow Base */}
                            <div className="absolute -bottom-6 left-1/2 h-4 w-24 -translate-x-1/2 rounded-[100%] bg-slate-400/20 blur-xl transition-all duration-500 group-hover:w-32 group-hover:bg-blue-200/40 dark:bg-black/40 scale-x-150" />
                        </div>
                     </div>
                     
                     {/* Text Content */}
                    <div className="relative z-10 text-center transition-transform duration-500 group-hover:translate-y-2">
                       <h3 className="mb-2 text-lg font-bold text-slate-900 transition-colors group-hover:text-blue-700 dark:text-slate-100 dark:group-hover:text-[#8DA3C1]">
                           点击或拖拽上传文档
                       </h3>
                       <p className="text-xs text-slate-600 transition-colors group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-300 mb-3 font-medium">
                           支持便携文档、文字文档、电子表格、图片等多种格式
                       </p>
                       <span className="inline-flex items-center gap-1.5 rounded-full bg-white border border-slate-200 px-3 py-1 text-[10px] font-bold text-slate-600 transition-all duration-300 group-hover:bg-blue-50 group-hover:text-blue-600 group-hover:border-blue-200 group-hover:shadow-sm dark:bg-slate-800 dark:text-slate-400 dark:group-hover:bg-[#1E293B]/50 dark:group-hover:text-[#8DA3C1]">
                           <Sparkles size={10} />
                           智能深度解析 & 溯源定位
                       </span>
                    </div>
                   </div>
                ) : (
                   <div
                        className={cn(
                          "relative w-full origin-center transition-all duration-300 ease-out will-change-transform",
                          activeRenderExt === 'pdf'
                            ? "h-full max-w-[1140px]"
                          : isPageBased 
                            ? "max-w-[940px] shadow-2xl dark:shadow-black/50" 
                            : "h-full min-h-0 flex flex-col"
                        )}
                        style={activeRenderExt === 'pdf'
                          ? undefined
                          : {
                              transform: `scale(${scale}) rotate(${rotation}deg)`,
                              transition: isProcessing ? 'none' : 'transform 0.3s ease-out',
                            }}
                    >
                         <div className={cn(
                           "relative w-full overflow-hidden bg-white dark:bg-[#1a1b26]",
                           activeRenderExt === 'pdf'
                             ? "h-full rounded-[20px] ring-1 ring-slate-200/60 shadow-2xl dark:ring-white/10"
                             : isPageBased 
                             ? "aspect-[595/842] ring-1 ring-slate-200/50 shadow-2xl dark:ring-white/10" 
                             : "flex-1 rounded-xl ring-1 ring-slate-200/50 shadow-sm dark:ring-white/10"
                         )}>
                            {activeRenderExt === 'pdf' && previewUrl ? (
                              <PdfCanvasPreview
                                key={`${activePreviewIdentity}:${previewUrl}`}
                                src={previewUrl}
                                scale={scale}
                                rotation={rotation}
                                scrollRequest={pdfScrollRequest}
                                onPageCount={setPdfPreviewPageCount}
                                onVisiblePageChange={setPdfViewportPage}
                              />
                            ) : (activeExt === 'doc' || activeExt === 'docx') ? (
                              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-50/70 p-6 text-center dark:bg-slate-900/60">
                                <div className="rounded-xl border border-slate-200 bg-white/90 px-4 py-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                                  {activeOfficePreview?.status === 'failed'
                                    ? (activeOfficePreview.error || '文档预览转换失败，请先执行抽取或重新上传。')
                                    : (activeOfficePreview?.status === 'completed'
                                      ? '文档已转换完成，正在加载预览...'
                                      : '后端正在将文档异步转换为预览，请稍候...')}
                                </div>
                                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                  支持文字文档，转换完成后自动切换为预览。
                                </p>
                              </div>
                            ) : IMAGE_EXTENSIONS.has(activeExt) && previewUrl ? (
                              <div className="absolute inset-0 flex items-center justify-center bg-slate-50/70 dark:bg-slate-900/60 p-6">
                                <img
                                  src={previewUrl}
                                  alt={activeDisplayName}
                                  className="max-h-full max-w-full object-contain rounded-md shadow-sm"
                                />
                              </div>
                            ) : activeRenderExt === 'xlsx' ? (
                              <div className="absolute inset-0 min-h-0 overflow-hidden bg-slate-50/70 p-0.5 dark:bg-slate-900/60 sm:p-1">
                                <LuckysheetPreview
                                  file={activeSourceFile}
                                  locator={xlsxLocatorHint}
                                  className="h-full min-h-0 rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
                                />
                              </div>
                            ) : ['txt', 'md'].includes(activeRenderExt) ? (
                              <div ref={textPreviewRef} className="absolute inset-0 p-6 overflow-auto bg-slate-50/70 dark:bg-slate-900/60">
                                <pre className="text-[10px] leading-5 whitespace-pre-wrap break-words font-mono text-slate-700 dark:text-slate-200">
                                  {previewHighlight ? (
                                    <>
                                      {previewHighlight.before}
                                      <mark data-preview-highlight="true" className="rounded bg-amber-200/80 px-0.5 text-slate-900 dark:bg-amber-400/40 dark:text-slate-100">
                                        {previewHighlight.hit}
                                      </mark>
                                      {previewHighlight.after}
                                    </>
                                  ) : (
                                    previewText || '文本预览加载中...'
                                  )}
                                </pre>
                              </div>
                            ) : (
                              <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8 bg-slate-50/70 dark:bg-slate-900/50">
                                <div className="w-14 h-14 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center mb-4 text-slate-500">
                                  <FileText size={26} />
                                </div>
                                <h4 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-2">{activeDisplayName}</h4>
                                <p className="text-[11px] text-slate-500 dark:text-slate-400 max-w-[320px] leading-relaxed">
                                  {activeSourceFile
                                    ? "当前格式暂不支持浏览器内预览，已保留抽取定位层与字段明细。"
                                    : "未找到本地原始文件（可能为缓存结果），仅展示字段定位层与抽取结果。"}
                                </p>
                              </div>
                            )}



                            {/* Bounding Boxes (hidden by default for cleaner trace view) */}
                              {showTraceOverlay && overlayItems.map((item) => {
                               const box = toPercentBox(item.bbox);
                               const isActive = activeFieldKey === item.key;
                               return (
                                 <div
                                   key={item.key}
                                   style={{
                                     left: `${box.x}%`,
                                     top: `${box.y}%`,
                                     width: `${box.w}%`,
                                     height: `${box.h}%`,
                                   }}
                                   onMouseEnter={() => setActiveFieldKey(item.key)}
                                   onMouseLeave={() => setActiveFieldKey(null)}
                                   className={cn(
                                     'absolute border-2 rounded-[2px] cursor-pointer transition-all duration-200 z-10',
                                     isActive
                                       ? 'border-blue-500 bg-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.5)] z-30 scale-[1.05]'
                                       : 'border-blue-400/30 bg-blue-400/5 hover:border-blue-500/80 hover:bg-blue-500/10'
                                   )}
                                 >
                                     {/* Floating Label on Hover */}
                                     <div className={cn(
                                         "absolute -top-10 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] px-2.5 py-1.5 rounded-md shadow-xl whitespace-nowrap pointer-events-none transition-all transform",
                                         isActive ? "opacity-100 translate-y-0 scale-100" : "opacity-0 translate-y-2 scale-95"
                                      )}>
                                          <div className="font-bold">
                                            {item.label}
                                            {item.pageNumber ? `（第${item.pageNumber}页）` : ''}
                                          </div>
                                          <div className="text-slate-500 dark:text-slate-400 text-[9px] font-medium">{Math.floor(item.confidence * 100)}% 置信度</div>
                                          <div className="absolute bottom-[-4px] left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-900 rotate-45"></div>
                                      </div>
                                  </div>
                                );
                              })}

                              {showTraceOverlay && overlayTraceItems.map((hit, idx) => {
                                const rawBox = Array.isArray(hit.bbox) ? hit.bbox : [];
                                const typ = hit.object_type;
                                const box = toPercentBox(rawBox);
                                const label = getTraceDisplayKind(hit) === 'table' ? '表格溯源' : getTraceDisplayKind(hit) === 'image' ? '图片溯源' : '溯源';
                                const traceKey = toTraceHitKey(hit, idx);
                                const isTraceActive = traceKey === activeTraceKey;
                                return (
                                  <div
                                    key={`trace-${traceKey}`}
                                    style={{
                                      left: `${box.x}%`,
                                      top: `${box.y}%`,
                                      width: `${box.w}%`,
                                      height: `${box.h}%`,
                                    }}
                                    className={cn(
                                      'absolute border border-dashed rounded-sm z-[9] pointer-events-none transition-all',
                                      typ === 'figure' ? 'border-amber-500/80 bg-amber-400/10' : 'border-emerald-500/80 bg-emerald-400/10',
                                      isTraceActive && 'ring-2 ring-blue-500/70 border-blue-500 bg-blue-500/10'
                                    )}
                                  >
                                    <div className="absolute -top-5 left-0 px-1.5 py-0.5 rounded bg-slate-900/90 text-white text-[9px] whitespace-nowrap">
                                      {label}
                                    </div>
                                  </div>
                                );
                              })}
                         </div>
                    </div>
                 )}
            </div>
            
            {/* Context Bar */}
            <div className="z-20 flex h-8 items-center justify-between border-t border-slate-200 bg-slate-50 px-3 text-[10px] text-slate-500 sm:px-4 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                <div className="flex min-w-0 items-center gap-2 sm:gap-4">
                     <span data-testid="module2-info-message" className="truncate">{infoMessage}</span>
                </div>
                {activeDoc && (
                    <div className="hidden font-mono opacity-50 sm:block">
                        引用编号: {activeDoc.file_hash.substring(0, 8)}...
                    </div>
                )}
            </div>
        </div>


      </div>

      {/* 右侧：结果面板 */}
      <div className={rightPanelClass}>
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden rounded-2xl border border-white/20 bg-white/90 shadow-2xl shadow-slate-300/30 backdrop-blur-xl ring-1 ring-slate-200/80 dark:bg-slate-900/90 dark:shadow-slate-900/50 dark:border-white/10 dark:ring-0">
          <div className="border-b border-slate-200/60 bg-slate-50/50 px-4 py-2 dark:border-white/10 dark:bg-slate-800/50">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h3 className="flex items-center gap-2 text-lg font-bold text-slate-800 dark:text-slate-100">
                  <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500 via-cyan-500 to-emerald-500 text-white shadow-lg shadow-cyan-500/25">
                    <Bot size={20} />
                  </span>
                  智能处理单元
                </h3>
              </div>
              <div className="relative isolate">
                <svg className="absolute h-0 w-0" aria-hidden="true">
                  <defs>
                    <filter id="gooey-tabs">
                      <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
                      <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 18 -7" result="goo" />
                      <feComposite in="SourceGraphic" in2="goo" operator="atop" />
                    </filter>
                  </defs>
                </svg>
                
                <div
                  className="inline-flex h-8 shrink-0 items-center rounded-full bg-slate-100/80 p-1 dark:bg-slate-800/80"
                  role="tablist"
                  aria-label="智能处理单元视图切换"
                >
                  <div 
                    className="absolute inset-0 z-0 flex items-center p-1" 
                    style={{ filter: 'url(#gooey-tabs)' }}
                    aria-hidden="true"
                  >
                    {[
                      { id: 'results', label: '结果', unread: resultsTabUnread },
                      { id: 'assistant', label: '助手', unread: assistantTabUnread }
                    ].map((tab) => {
                      const isActive = smartUnitTab === tab.id;
                      return (
                        <div key={tab.id} className="relative flex h-6 items-center justify-center px-3">
                          <span className="invisible text-xs font-bold whitespace-nowrap opacity-0 flex items-center gap-1.5">
                            {tab.label}
                            {tab.unread && <span className="h-1.5 w-1.5" />}
                          </span>
                          {isActive && (
                            <motion.div
                              layoutId="smartUnitTabBlob"
                              className="absolute inset-0 rounded-full bg-white dark:bg-slate-900"
                              transition={{ type: "spring", stiffness: 300, damping: 25 }}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <div className="relative z-10 flex items-center">
                    {[
                      { id: 'results', label: '结果', unread: resultsTabUnread },
                      { id: 'assistant', label: '助手', unread: assistantTabUnread }
                    ].map((tab) => {
                      const isActive = smartUnitTab === tab.id;
                      return (
                        <button
                          key={tab.id}
                          type="button"
                          role="tab"
                          aria-selected={isActive}
                          onClick={() => setSmartUnitTab(tab.id as any)}
                          className={cn(
                            'relative inline-flex h-6 items-center justify-center rounded-full px-3 text-xs font-bold transition-colors duration-200 ease-out whitespace-nowrap',
                            isActive
                              ? 'text-blue-600 dark:text-blue-400'
                              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                          )}
                        >
                          <span className="flex items-center gap-1.5">
                            {tab.label}
                            {tab.unread && (
                              <span className="h-1.5 w-1.5 rounded-full bg-red-500 ring-1 ring-white dark:ring-slate-900" aria-hidden="true" />
                            )}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-hidden bg-transparent">
            <div className={smartUnitTrackClass}>
              <section className="h-full w-1/2 min-w-0 p-0" aria-label="抽取结果视图">
                <div className="flex h-full min-h-0 flex-col overflow-hidden bg-transparent">
          <div className="px-4 py-3 bg-transparent">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-xs font-medium text-slate-500 uppercase tracking-wider dark:text-slate-400">
                <ScanLine size={14} className="text-slate-400 dark:text-slate-500" />
                抽取结果
              </h3>
              <span className="rounded-full bg-slate-100/50 px-2 py-0.5 text-[10px] font-bold text-slate-500 backdrop-blur-sm dark:bg-slate-800/50 dark:text-slate-400">{resultCountText}</span>
            </div>
            {fieldItems.length > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-2 text-[10px]">
                <span className="flex items-center justify-center rounded-lg bg-emerald-50/50 px-2 py-1.5 font-bold text-emerald-700 backdrop-blur-sm ring-1 ring-emerald-500/10 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20">
                  平均置信度 {avgConfidence}%
                </span>
                <span className="flex items-center justify-center rounded-lg bg-blue-50/50 px-2 py-1.5 font-bold text-blue-700 backdrop-blur-sm ring-1 ring-blue-500/10 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20">
                  表格 {tableCount} / 图片 {figureCount}
                </span>
              </div>
            )}
            {activeDoc && fieldItems.length > 0 && (
              <div className="mt-3 flex items-center gap-2">
                <div className="relative flex-1 group">
                  <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-blue-500" />
                  <input
                    type="text"
                    value={resultSearchQuery}
                    onChange={(e) => setResultSearchQuery(e.target.value)}
                    className="h-8 w-full rounded-full border-none bg-slate-100/80 pl-9 pr-8 text-xs text-slate-700 placeholder:text-slate-400 ring-1 ring-slate-200/50 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500/20 dark:bg-slate-800/50 dark:text-slate-200 dark:ring-slate-700/50 dark:focus:bg-slate-800"
                    placeholder="搜索字段..."
                    aria-label="搜索抽取结果"
                  />
                  {hasResultSearch && (
                    <button
                      type="button"
                      onClick={() => setResultSearchQuery('')}
                      className="absolute right-1 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      aria-label="清空抽取结果搜索"
                    >
                      <X size={12} />
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() =>
                    void writeClipboard(
                      filteredResultsClipboardText,
                      hasResultSearch
                        ? `已复制 ${filteredFieldItems.length} 条筛选结果。`
                        : `已复制 ${filteredFieldItems.length} 条抽取结果。`
                    )
                  }
                  disabled={!canCopyFilteredResults}
                  className={cn(
                    'inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border px-2 text-[11px] transition-colors',
                    canCopyFilteredResults
                      ? 'border-slate-200 text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300'
                      : 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500'
                  )}
                  aria-label="复制当前结果列表"
                >
                  <Copy size={12} />
                  复制全部
                </button>
              </div>
            )}
          </div>

          <div data-testid="module2-trace-panel" className="flex min-h-0 max-h-[42%] flex-col overflow-hidden rounded-xl border border-slate-200/50 bg-white/40 px-4 pt-2 pb-3 shadow-sm backdrop-blur-md dark:border-slate-800/50 dark:bg-slate-900/40">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-medium text-slate-500 uppercase tracking-wider dark:text-slate-400">
                <LocateFixed size={14} className={cn("text-slate-400", traceHits.length > 0 && "text-blue-500 dark:text-blue-400")} />
                溯源定位
              </div>
            </div>

            {(traceTypeStats.field > 0 || traceTypeStats.table > 0 || traceTypeStats.image > 0 || traceTypeStats.other > 0) && (
              <div className="mb-2 flex flex-wrap gap-1.5 text-[10px]">
                {traceTypeStats.field > 0 && <span className="inline-flex items-center rounded-full bg-blue-50/80 px-2 py-0.5 font-medium text-blue-600 ring-1 ring-inset ring-blue-500/10 dark:bg-blue-900/20 dark:text-blue-300">字段 {traceTypeStats.field}</span>}
                {traceTypeStats.table > 0 && <span className="inline-flex items-center rounded-full bg-emerald-50/80 px-2 py-0.5 font-medium text-emerald-600 ring-1 ring-inset ring-emerald-500/10 dark:bg-emerald-900/20 dark:text-emerald-300">表格 {traceTypeStats.table}</span>}
                {traceTypeStats.image > 0 && <span className="inline-flex items-center rounded-full bg-amber-50/80 px-2 py-0.5 font-medium text-amber-600 ring-1 ring-inset ring-amber-500/10 dark:bg-amber-900/20 dark:text-amber-300">图片 {traceTypeStats.image}</span>}
                {traceTypeStats.other > 0 && <span className="inline-flex items-center rounded-full bg-slate-100/80 px-2 py-0.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-500/10 dark:bg-slate-700 dark:text-slate-300">其他 {traceTypeStats.other}</span>}
              </div>
            )}

            {traceError && (
              <p className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-[10px] text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
                {traceError}
              </p>
            )}

            {traceHits.length > 0 ? (
              <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2 custom-scrollbar">
                {traceGroups.map((group) => (
                  <div key={`trace-group-${group.key}`} data-testid={`module2-trace-group-${group.key}`} className="mb-3 last:mb-0">
                    <div data-testid="module2-trace-group-label" className="sticky top-0 z-10 mb-1.5 bg-slate-50/95 px-2 py-1 text-[10px] font-bold text-slate-400 backdrop-blur dark:bg-slate-900/95 dark:text-slate-500">
                      {group.label}
                    </div>
                    <div className="space-y-1.5 px-1">
                {group.items.map(({ hit, idx }) => {
                  const objectType = String(hit.object_type || "field").toLowerCase();
                  const displayKind = getTraceDisplayKind(hit);
                  const objectLabel = getTraceDisplayLabel(hit);
                  const objectId = String(hit.object_id || "");
                  const page = toTracePage(hit);
                  const snippet = String(hit.snippet || "");
                  const traceKey = toTraceHitKey(hit, idx);
                  const isActiveTrace = activeTraceKey === traceKey;
                  const artifactUrl = resolveArtifactUrl(hit);
                  const locator = (hit.locator ?? {}) as Record<string, unknown>;
                  const tablePreview = (locator.table_preview ?? {}) as Record<string, unknown>;
                  const tableHeaders = Array.isArray(tablePreview.headers)
                    ? tablePreview.headers.map((x) => String(x ?? ''))
                    : [];
                  const tableRows = Array.isArray(tablePreview.rows)
                    ? tablePreview.rows.map((row) =>
                        Array.isArray(row) ? row.map((cell) => String(cell ?? '')) : []
                      )
                    : [];
                  const figureKeyPoints = Array.isArray(locator.key_points)
                    ? locator.key_points.map((x) => String(x ?? '')).filter(Boolean).slice(0, 3)
                    : [];
                  const figureModesRaw = Array.isArray(locator.content_modes)
                    ? locator.content_modes.map((x) => String(x ?? '').trim().toLowerCase()).filter(Boolean)
                    : [];
                  const figureModes = figureModesRaw.slice(0, 4);
                  const modeLabelMap: Record<string, string> = {
                    dataframe: '数据表',
                    topology: '拓扑',
                    text: '文本',
                    visual: '视觉',
                  };
                  const figureDataframe = (locator.dataframe ?? {}) as Record<string, unknown>;
                  const figureDfHeaders = Array.isArray(figureDataframe.headers)
                    ? figureDataframe.headers.map((x) => String(x ?? '')).filter(Boolean).slice(0, 8)
                    : [];
                  const figureDfRows = Array.isArray(figureDataframe.rows)
                    ? figureDataframe.rows
                        .map((row) => (Array.isArray(row) ? row.map((cell) => String(cell ?? '')) : []))
                        .filter((row) => row.length > 0)
                        .slice(0, 3)
                    : [];
                  const figureTopology = (locator.topology ?? {}) as Record<string, unknown>;
                  const figureTopologyNodes = Array.isArray(figureTopology.nodes) ? figureTopology.nodes.length : 0;
                  const figureTopologyEdges = Array.isArray(figureTopology.edges) ? figureTopology.edges.length : 0;
                  const figureTextBlocks = Array.isArray(locator.text_blocks)
                    ? locator.text_blocks.map((x) => String(x ?? '').trim()).filter(Boolean).slice(0, 3)
                    : [];
                  const locatorHints: string[] = [];
                  const sheetName = String(locator.sheet_name || '').trim();
                  if (sheetName) locatorHints.push(`工作表：${sheetName}`);
                  const tableRow = Number(locator.row_index || 0);
                  if (Number.isFinite(tableRow) && tableRow > 0) locatorHints.push(`行：${Math.round(tableRow)}`);
                  const tableCol = Number(locator.col_index || 0);
                  if (Number.isFinite(tableCol) && tableCol > 0) locatorHints.push(`列：${Math.round(tableCol)}`);
                  const paragraphIndex = Number(locator.paragraph_index || 0);
                  if (Number.isFinite(paragraphIndex) && paragraphIndex > 0) locatorHints.push(`段落：${Math.round(paragraphIndex)}`);
                  const chunkIndex = Number(locator.chunk_index || 0);
                  if (Number.isFinite(chunkIndex) && chunkIndex > 0) locatorHints.push(`片段：${Math.round(chunkIndex)}`);
                  const lineStart = Number(locator.line_start || 0);
                  const lineEnd = Number(locator.line_end || 0);
                  if (Number.isFinite(lineStart) && lineStart > 0) {
                    const rangeText = Number.isFinite(lineEnd) && lineEnd >= lineStart
                      ? `${Math.round(lineStart)}-${Math.round(lineEnd)}`
                      : `${Math.round(lineStart)}`;
                    locatorHints.push(`行号：${rangeText}`);
                  }
                  const locatorSummary = locatorHints.join(' 路 ');
                  return (
                    <div
                      key={`trace-list-${traceKey}`}
                      data-testid="module2-trace-card"
                      onClick={() => {
                        setActiveTraceKey(traceKey);
                        if (objectType === "field" && objectId) {
                          setActiveFieldKey(objectId);
                        }
                        if (activeRenderExt === "pdf" && Number.isFinite(page) && page > 0) {
                          jumpToPdfPage(page);
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key !== 'Enter' && e.key !== ' ') return;
                        e.preventDefault();
                        setActiveTraceKey(traceKey);
                        if (objectType === "field" && objectId) {
                          setActiveFieldKey(objectId);
                        }
                        if (activeRenderExt === "pdf" && Number.isFinite(page) && page > 0) {
                          jumpToPdfPage(page);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      className={cn(
                        "group relative w-full rounded-xl border border-transparent bg-white/60 px-3 py-2.5 text-left transition-all hover:bg-white hover:shadow-md hover:shadow-slate-200/50 hover:ring-1 hover:ring-slate-200/50 dark:bg-slate-800/40 dark:hover:bg-slate-800 dark:hover:ring-slate-700",
                        isActiveTrace && "bg-blue-50 ring-1 ring-blue-200 dark:bg-blue-900/30 dark:ring-blue-800"
                      )}
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                           <span className={cn(
                             "flex h-5 items-center justify-center rounded-md px-1.5 text-[10px] font-bold uppercase tracking-wider",
                             displayKind === 'field' ? "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300" :
                             displayKind === 'table' ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300" :
                             displayKind === 'image' ? "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300" :
                             "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                           )}>
                             {objectLabel}
                           </span>
                           {activeRenderExt === 'pdf' && page > 0 && (
                             <span className="flex items-center gap-0.5 text-[10px] font-medium text-slate-400">
                               <span className="opacity-50">Page</span>
                               <span>{Math.round(page)}</span>
                             </span>
                           )}
                        </div>
                        <span className="text-[10px] font-medium text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">{Math.round((Number(hit.confidence || 0) || 0) * 100)}%</span>
                      </div>
                      <p className="line-clamp-2 text-[11px] leading-relaxed text-slate-700 dark:text-slate-200">
                        {snippet || objectId || "溯源片段"}
                      </p>
                      {locatorSummary && (
                        <div className="mt-2 flex items-center gap-1.5">
                          <div className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600"></div>
                          <p className="truncate text-[10px] text-slate-500 dark:text-slate-400">
                            {locatorSummary}
                          </p>
                        </div>
                      )}

                      {objectType === 'figure' && figureModes.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {figureModes.map((mode) => (
                            <span
                              key={`${traceKey}-mode-${mode}`}
                              className="rounded-md bg-amber-50/50 px-1.5 py-0.5 text-[10px] text-amber-700/80 ring-1 ring-inset ring-amber-600/10 dark:bg-amber-900/20 dark:text-amber-300"
                            >
                              {modeLabelMap[mode] || mode}
                            </span>
                          ))}
                        </div>
                      )}

                      {artifactUrl && (
                        <div className="mt-2 overflow-hidden rounded-md border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
                          <a href={artifactUrl} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                            <img
                              data-testid="module2-trace-artifact-image"
                              src={artifactUrl}
                              alt={`${objectLabel}-preview-${idx + 1}`}
                              className="h-40 w-full object-contain bg-white p-1 dark:bg-slate-900 sm:h-56"
                              loading="lazy"
                            />
                          </a>
                        </div>
                      )}

                      {displayKind === 'table' && tableRows.length > 0 && (
                        <div data-testid="module2-trace-table-preview" className="mt-2 overflow-x-auto rounded-md border border-slate-200 dark:border-slate-700">
                          <table className="min-w-full text-[11px] text-slate-700 dark:text-slate-200">
                            <thead className="bg-slate-100 dark:bg-slate-800">
                              <tr>
                                {(tableHeaders.length > 0 ? tableHeaders : tableRows[0]).map((header, hIdx) => (
                                  <th key={`tbl-h-${idx}-${hIdx}`} className="border-b border-r border-slate-200 px-1.5 py-1 text-left font-bold dark:border-slate-700">
                                    {header || `列${hIdx + 1}`}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {tableRows.slice(0, 3).map((row, rIdx) => (
                                <tr key={`tbl-r-${idx}-${rIdx}`} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800/50">
                                  {(tableHeaders.length > 0 ? tableHeaders : row).map((_, cIdx) => (
                                    <td key={`tbl-c-${idx}-${rIdx}-${cIdx}`} className="max-w-[180px] border-b border-r border-slate-100 px-1.5 py-1 align-top break-words dark:border-slate-800">
                                      {String(row[cIdx] ?? "").trim() || "—"}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {objectType === 'figure' && figureKeyPoints.length > 0 && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {figureKeyPoints.join("；")}
                        </div>
                      )}

                      {objectType === 'figure' && figureDfRows.length > 0 && (
                        <div data-testid="module2-trace-figure-dataframe" className="mt-2 overflow-x-auto rounded-md border border-slate-200 dark:border-slate-700">
                          <table className="min-w-full text-[10px] text-slate-700 dark:text-slate-200">
                            <thead className="bg-slate-100 dark:bg-slate-800">
                              <tr>
                                {(figureDfHeaders.length > 0 ? figureDfHeaders : figureDfRows[0]).map((header, hIdx) => (
                                  <th key={`fig-df-h-${idx}-${hIdx}`} className="border-b border-r border-slate-200 px-1.5 py-1 text-left font-bold dark:border-slate-700">
                                    {header || `列${hIdx + 1}`}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {figureDfRows.map((row, rIdx) => (
                                <tr key={`fig-df-r-${idx}-${rIdx}`} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800/50">
                                  {(figureDfHeaders.length > 0 ? figureDfHeaders : row).map((_, cIdx) => (
                                    <td key={`fig-df-c-${idx}-${rIdx}-${cIdx}`} className="max-w-[160px] border-b border-r border-slate-100 px-1.5 py-1 align-top break-words dark:border-slate-800">
                                      {String(row[cIdx] ?? "").trim() || "—"}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {objectType === 'figure' && (figureTopologyNodes > 0 || figureTopologyEdges > 0) && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {`拓扑节点 ${figureTopologyNodes} · 拓扑连边 ${figureTopologyEdges}`}
                        </div>
                      )}

                      {objectType === 'figure' && figureTextBlocks.length > 0 && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {figureTextBlocks.join("；")}
                        </div>
                      )}

                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            void writeClipboard(snippet || objectId || "", "已复制溯源片段。");
                          }}
                          className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                        >
                          <Copy size={11} />
                          复制片段
                        </button>
                        {displayKind === 'table' && tableRows.length > 0 && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void writeClipboard(
                                tablePreviewToTsv(
                                  tableHeaders.length > 0 ? tableHeaders : tableRows[0],
                                  tableRows
                                ),
                                "已复制表格内容（制表符分隔格式）。"
                              );
                            }}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                          >
                            <Copy size={11} />
                            复制表格
                          </button>
                        )}
                        {artifactUrl && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              void writeClipboard(artifactUrl, "已复制截图链接。");
                            }}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                          >
                            <Copy size={11} />
                            {"复制链接"}
                          </button>
                        )}
                        {artifactUrl && (
                          <a
                            href={artifactUrl}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-1 text-[10px] text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
                          >
                            <ExternalLink size={11} />
                            查看截图
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-slate-400 dark:text-slate-500">暂无相关溯源信息</p>
            )}
          </div>

          <div className="flex-1 min-h-0 space-y-2 overflow-y-auto custom-scrollbar bg-transparent px-4 pb-4">
            {errorMessage && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-600 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                <div className="flex items-start gap-2">
                  <AlertCircle size={14} className="mt-0.5 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              </div>
            )}

            {!activeDoc && !errorMessage && (
              <div className="flex h-full flex-col items-center justify-center text-center select-none">
                <ScanLine size={32} strokeWidth={1} className="mb-2 opacity-20 text-slate-400 dark:text-slate-500" />
                <p className="text-xs text-slate-400 dark:text-slate-500">暂无抽取结果</p>
              </div>
            )}

            {activeDoc && activeDoc.errors.length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                {activeDoc.errors.map((e, i) => (
                  <div key={i} className="flex gap-2">
                    <AlertCircle size={12} className="mt-0.5 shrink-0" />
                    <span>{e}</span>
                  </div>
                ))}
              </div>
            )}

            {activeDoc && (activeDoc.soft_warnings?.length ?? 0) > 0 && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-xs text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
                {(activeDoc.soft_warnings ?? []).slice(0, 4).map((warn, i) => (
                  <div key={i} className="flex gap-2">
                    <AlertCircle size={12} className="mt-0.5 shrink-0" />
                    <span>{warn}</span>
                  </div>
                ))}
              </div>
            )}

            {activeDoc && fieldItems.length === 0 && !errorMessage && (
              <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-slate-200 bg-slate-50/30 p-8 text-center backdrop-blur-sm dark:border-slate-800 dark:bg-slate-900/30">
                <div className="rounded-full bg-slate-100 p-3 ring-1 ring-slate-200 dark:bg-slate-800 dark:ring-slate-700">
                  <FileText size={24} className="text-slate-400 dark:text-slate-500" />
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-600 dark:text-slate-300">暂无结构化字段</p>
                  <p className="mt-1 text-[10px] text-slate-400 dark:text-slate-500">请检查文档内容或调整提取规则</p>
                </div>
              </div>
            )}

            {activeDoc && fieldItems.length > 0 && filteredFieldItems.length === 0 && !errorMessage && (
              <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
                 <Search size={20} className="text-slate-300 dark:text-slate-600" />
                 <p className="text-xs text-slate-500 dark:text-slate-400">未找到匹配 "{resultSearchQuery}" 的字段</p>
                 <button 
                   onClick={() => setResultSearchQuery('')}
                   className="text-[10px] text-blue-500 hover:underline"
                 >
                   清除搜索
                 </button>
              </div>
            )}

            {filteredFieldItems.map((item) => (
              <div
                key={item.key}
                onClick={() => {
                  setActiveFieldKey(item.key);
                  const hitIndex = traceHits.findIndex(
                    (hit) =>
                      String(hit.object_type || '').toLowerCase() === 'field' &&
                      String(hit.object_id || '').toLowerCase() === item.key.toLowerCase()
                  );
                  if (hitIndex >= 0) {
                    const hit = traceHits[hitIndex];
                    setActiveTraceKey(toTraceHitKey(hit, hitIndex));
                  }
                  if (activeRenderExt === "pdf" && item.pageNumber) {
                    jumpToPdfPage(item.pageNumber);
                  }
                }}
                onMouseEnter={() => setActiveFieldKey(item.key)}
                onMouseLeave={() => setActiveFieldKey(null)}
                className={cn(
                  "group relative cursor-pointer rounded-xl border p-3 transition-all duration-300",
                  activeFieldKey === item.key
                    ? "border-blue-500/50 bg-blue-50/40 shadow-md ring-1 ring-blue-500/20 backdrop-blur-md dark:bg-blue-900/30 dark:ring-blue-500/30"
                    : "border-slate-200/50 bg-white/40 hover:-translate-y-0.5 hover:border-blue-200 hover:bg-white/60 hover:shadow-lg hover:shadow-slate-200/40 backdrop-blur-sm dark:border-slate-800/50 dark:bg-slate-900/40 dark:hover:border-blue-800 dark:hover:bg-slate-800/60 dark:hover:shadow-none"
                )}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className={cn(
                    "text-[10px] font-bold uppercase tracking-wider transition-colors",
                    activeFieldKey === item.key ? "text-blue-600 dark:text-blue-400" : "text-slate-500 group-hover:text-blue-500 dark:text-slate-400 dark:group-hover:text-blue-400"
                  )}>
                    {item.label}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {activeRenderExt === "pdf" && item.pageNumber && (
                      <span className="flex items-center gap-0.5 rounded-md bg-slate-100/50 px-1.5 py-0.5 text-[9px] font-medium text-slate-500 dark:bg-slate-800/50 dark:text-slate-400">
                        P{item.pageNumber}
                      </span>
                    )}
                    <span
                      className={cn(
                        "flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] font-bold shadow-sm ring-1 ring-inset backdrop-blur-sm",
                        item.confidence > 0.8
                          ? "bg-emerald-50/50 text-emerald-600 ring-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/30"
                          : "bg-amber-50/50 text-amber-600 ring-amber-500/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/30"
                      )}
                    >
                      {item.confidence > 0.8 ? <CheckCircle2 size={8} /> : <AlertCircle size={8} />}
                      {Math.floor(item.confidence * 100)}%
                    </span>
                  </div>
                </div>

                <div className="break-all rounded-lg bg-slate-50/50 px-2.5 py-2 font-mono text-sm leading-relaxed text-slate-700 ring-1 ring-inset ring-slate-200/50 transition-colors group-hover:bg-white/80 group-hover:ring-blue-100 dark:bg-slate-950/30 dark:text-slate-300 dark:ring-slate-800 dark:group-hover:bg-slate-950/50 dark:group-hover:ring-blue-900/30">
                  {item.valueText}
                </div>
              </div>
            ))}
          </div>
                </div>
              </section>
              <section className="h-full w-1/2 min-w-0 p-2" aria-label="任务助手视图">
                {assistantPanel}
              </section>
            </div>
          </div>
        </div>
      </div>
    </div>
      {showAssistantHelp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in zoom-in-95 duration-200">
          <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-700">
            <div className="flex items-center justify-between border-b border-slate-100 p-4 dark:border-slate-800">
              <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                <Bot className="text-blue-500" size={20} />
                信息提取助手功能说明
              </h3>
              <button 
                onClick={() => setShowAssistantHelp(false)}
                className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300 transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            <div className="p-6 space-y-4 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              <div className="flex gap-3">
                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 font-bold">1</div>
                <div>
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">智能解析与提取</h4>
                  <p>上传文档后，助手会自动分析文档结构，你可以直接查看右侧提取结果，或在下方对话框输入指令（如“提取发票金额”）进行定向提取。</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400 font-bold">2</div>
                <div>
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">多模态溯源定位</h4>
                  <p>点击提取结果中的字段，系统会自动定位到文档原文位置。支持文字、表格、印章及图片的精准溯源。</p>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400 font-bold">3</div>
                <div>
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">交互式结果修正</h4>
                  <p>如果对结果不满意，可直接告诉助手“金额不对，应该是示例值”，助手会根据反馈进行修正并重新定位。</p>
                </div>
              </div>
            </div>
            <div className="bg-slate-50 p-4 text-center dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-800">
              <button 
                onClick={() => setShowAssistantHelp(false)}
                className="px-6 py-2 rounded-xl bg-blue-600 text-white font-bold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-500/20 text-sm"
              >
                开始使用
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

