import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  AlertCircle,
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
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCw,
  RefreshCcw,
  Maximize,
  X,
  Search,
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

const MODULE2_PANE_LAYOUT_STORAGE_KEY = 'module2_workbench_pane_layout_v6';
const LEFT_PANE_MIN_WIDTH = 220;
const LEFT_PANE_DEFAULT_WIDTH = 236;
const LEFT_PANE_MAX_WIDTH = 380;
const RIGHT_PANE_MIN_WIDTH = 300;
const RIGHT_PANE_DEFAULT_WIDTH = 332;
const RIGHT_PANE_MAX_WIDTH = 520;
const CENTER_PANE_SAFE_WIDTH = 320;
const PANE_DIVIDER_WIDTH = 6;

type WorkbenchPaneLayout = {
  leftWidth: number;
  rightWidth: number;
};

type PaneResizeSide = 'left' | 'right';
type SmartUnitTabId = 'results' | 'assistant';

const clampNumber = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const sanitizePaneWidth = (
  value: unknown,
  fallback: number,
  min: number,
  max: number,
): number => {
  const raw = Number(value);
  return Number.isFinite(raw) ? clampNumber(Math.round(raw), min, max) : fallback;
};

const getDefaultWorkbenchPaneLayout = (viewportWidth: number): WorkbenchPaneLayout => {
  if (viewportWidth >= 1800) {
    return {
      leftWidth: LEFT_PANE_DEFAULT_WIDTH,
      rightWidth: RIGHT_PANE_DEFAULT_WIDTH,
    };
  }

  if (viewportWidth >= 1500) {
    return {
      leftWidth: 228,
      rightWidth: 320,
    };
  }

  return {
    leftWidth: LEFT_PANE_MIN_WIDTH,
    rightWidth: 312,
  };
};

const readWorkbenchPaneLayout = (): WorkbenchPaneLayout => {
  const defaultLayout = typeof window === 'undefined'
    ? {
        leftWidth: LEFT_PANE_DEFAULT_WIDTH,
        rightWidth: RIGHT_PANE_DEFAULT_WIDTH,
      }
    : getDefaultWorkbenchPaneLayout(window.innerWidth);

  if (typeof window === 'undefined') {
    return defaultLayout;
  }

  try {
    const raw = window.localStorage.getItem(MODULE2_PANE_LAYOUT_STORAGE_KEY);
    if (!raw) {
      return defaultLayout;
    }
    const parsed = JSON.parse(raw) as Partial<WorkbenchPaneLayout>;
    return {
      leftWidth: sanitizePaneWidth(parsed.leftWidth, defaultLayout.leftWidth, LEFT_PANE_MIN_WIDTH, LEFT_PANE_MAX_WIDTH),
      rightWidth: sanitizePaneWidth(parsed.rightWidth, defaultLayout.rightWidth, RIGHT_PANE_MIN_WIDTH, RIGHT_PANE_MAX_WIDTH),
    };
  } catch {
    return defaultLayout;
  }
};

const clampWorkbenchPaneLayout = (
  layout: WorkbenchPaneLayout,
  containerWidth: number,
  showLeftPane: boolean,
): WorkbenchPaneLayout => {
  const nextLeftWidth = sanitizePaneWidth(layout.leftWidth, LEFT_PANE_DEFAULT_WIDTH, LEFT_PANE_MIN_WIDTH, LEFT_PANE_MAX_WIDTH);
  const nextRightWidth = sanitizePaneWidth(layout.rightWidth, RIGHT_PANE_DEFAULT_WIDTH, RIGHT_PANE_MIN_WIDTH, RIGHT_PANE_MAX_WIDTH);

  if (!Number.isFinite(containerWidth) || containerWidth <= 0) {
    return {
      leftWidth: nextLeftWidth,
      rightWidth: nextRightWidth,
    };
  }

  const dividerWidth = showLeftPane ? PANE_DIVIDER_WIDTH * 2 : PANE_DIVIDER_WIDTH;
  let resolvedRightWidth = nextRightWidth;
  let resolvedLeftWidth = nextLeftWidth;

  if (showLeftPane) {
    const maxRight = Math.min(
      RIGHT_PANE_MAX_WIDTH,
      Math.max(RIGHT_PANE_MIN_WIDTH, containerWidth - resolvedLeftWidth - dividerWidth - CENTER_PANE_SAFE_WIDTH),
    );
    resolvedRightWidth = clampNumber(resolvedRightWidth, RIGHT_PANE_MIN_WIDTH, maxRight);

    const maxLeft = Math.min(
      LEFT_PANE_MAX_WIDTH,
      Math.max(LEFT_PANE_MIN_WIDTH, containerWidth - resolvedRightWidth - dividerWidth - CENTER_PANE_SAFE_WIDTH),
    );
    resolvedLeftWidth = clampNumber(resolvedLeftWidth, LEFT_PANE_MIN_WIDTH, maxLeft);

    const refinedMaxRight = Math.min(
      RIGHT_PANE_MAX_WIDTH,
      Math.max(RIGHT_PANE_MIN_WIDTH, containerWidth - resolvedLeftWidth - dividerWidth - CENTER_PANE_SAFE_WIDTH),
    );
    resolvedRightWidth = clampNumber(resolvedRightWidth, RIGHT_PANE_MIN_WIDTH, refinedMaxRight);
  } else {
    const maxRight = Math.min(
      RIGHT_PANE_MAX_WIDTH,
      Math.max(RIGHT_PANE_MIN_WIDTH, containerWidth - dividerWidth - CENTER_PANE_SAFE_WIDTH),
    );
    resolvedRightWidth = clampNumber(resolvedRightWidth, RIGHT_PANE_MIN_WIDTH, maxRight);
  }

  return {
    leftWidth: resolvedLeftWidth,
    rightWidth: resolvedRightWidth,
  };
};

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

const isDocumentResultLike = (value: unknown): value is DocumentResult => {
  if (!value || typeof value !== 'object') return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.file_name === 'string'
    && typeof obj.file_hash === 'string'
    && typeof obj.track === 'string'
    && typeof obj.cached === 'boolean'
    && Array.isArray(obj.errors)
    && !!obj.result
    && typeof obj.result === 'object'
  );
};

const getSessionPersistedDocuments = (session: WorkbenchSessionSnapshot | null): DocumentResult[] => {
  const job = session?.extractionJob as (PersistedExtractionJob & { documents?: unknown }) | null | undefined;
  if (!job || !Array.isArray(job.documents)) return [];
  return job.documents.filter(isDocumentResultLike);
};

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
  lock_quality?: string;
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

type AssistantToolEvent = {
  tool_name: string;
  status: string;
  message: string;
  detail: string;
  human_label: string;
};

const isInternalAssistantWarning = (warningRaw: unknown): boolean => {
  const warning = String(warningRaw || '').trim();
  if (!warning) return false;
  return (
    warning.startsWith('assistant_provider_fallback:') ||
    warning.startsWith('assistant_context_fallback:')
  );
};

const filterAssistantWarnings = (warningsRaw: unknown): string[] => {
  if (!Array.isArray(warningsRaw)) return [];
  return warningsRaw
    .map((item) => String(item || '').trim())
    .filter((item) => item && !isInternalAssistantWarning(item));
};

const mergeShortAssistantBridgeParagraphs = (text: string): string => {
  const paragraphs = String(text || '')
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (paragraphs.length < 2) return paragraphs.join('\n\n');

  const bridgeParagraphRe =
    /^(先看|先说|先把|再看|再说|再把|最后|最后再|整体看|整体来说|单看|先看当前|再看整体|比较稳的|还要再核的|先看文档里能确认的部分|再看通用经验|最后说需要联网再核的部分|文档里能确认的部分|通用经验|需要联网再核的部分|当前这条记录|整份文档|当前聚焦对象能确认什么|整份文档大致讲了什么|哪些信息比较稳定，哪些还需要谨慎校对|关于文档内证据|关于通用经验|关于是否需要联网查证)[^。！？!?]{0,20}[。！？!?：]?$/;

  const merged: string[] = [];
  for (let index = 0; index < paragraphs.length; index += 1) {
    const current = paragraphs[index];
    const normalized = current.replace(/\s+/g, '');
    const next = paragraphs[index + 1];
    if (next && normalized.length <= 26 && bridgeParagraphRe.test(normalized)) {
      const prefix = /[。！？!?：:]$/.test(current) ? current : `${current}。`;
      merged.push(`${prefix}${next}`);
      index += 1;
      continue;
    }
    merged.push(current);
  }
  return merged.join('\n\n');
};

const normalizeAssistantDisplayText = (textRaw: unknown): string => (
  mergeShortAssistantBridgeParagraphs(
    String(textRaw || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .replace(/\u200b/g, '')
      .replace(/\u0000/g, '')
      .replace(/\ufeff/g, '')
      .replace(/[\u00a0\u3000\u2002\u2003\u2009\u202f\u205f]/g, ' ')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n[ \t]+/g, '\n')
      .split('\n')
      .map((line) => line.trim())
      .join('\n')
      .replace(/[ \t]{2,}/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/\n\n(?=[-*•]\s)/g, '\n')
      .trim()
  )
);

const humanizeAssistantLockType = (lockTypeRaw: string): string => {
  const lockType = String(lockTypeRaw || '').trim().toLowerCase();
  if (!lockType) return '未锁定';
  if (lockType === 'table_row') return '表格行';
  if (lockType === 'table_region') return '表格区域';
  if (lockType === 'figure') return '图像 / 图表';
  if (lockType === 'ocr_fact_group') return 'OCR 事实组';
  if (lockType === 'field') return '字段';
  return lockTypeRaw || '未锁定';
};

const humanizeAssistantLockQuality = (lockQualityRaw: string): string => {
  const lockQuality = String(lockQualityRaw || '').trim().toLowerCase();
  if (!lockQuality) return '';
  if (lockQuality === 'stable_lock') return '稳定锁定';
  if (lockQuality === 'weak_lock') return '弱锁定';
  if (lockQuality === 'no_lock') return '未形成稳定锁定';
  return lockQualityRaw;
};

const humanizeAssistantFocusScope = (focusScopeRaw: string): string => {
  const focusScope = String(focusScopeRaw || '').trim().toLowerCase();
  if (!focusScope) return '';
  if (focusScope === 'table_row') return '表格行绑定';
  if (focusScope === 'ocr_fact_group') return 'OCR 事实组绑定';
  if (focusScope === 'unresolved_table_row') return '未稳定表格行';
  if (focusScope === 'context') return '普通上下文';
  return focusScopeRaw;
};

const humanizeAssistantActionType = (actionTypeRaw: string): string => {
  const actionType = String(actionTypeRaw || '').trim().toLowerCase();
  if (!actionType) return '';
  if (actionType === 'sql_preview') return 'SQL 预览';
  if (actionType === 'save_preview') return '入库预览';
  return actionTypeRaw;
};

const humanizeAssistantOperationType = (operationTypeRaw: string): string => {
  const operationType = String(operationTypeRaw || '').trim().toLowerCase();
  if (!operationType) return '';
  if (operationType === 'select') return '查询';
  if (operationType === 'insert') return '写入';
  if (operationType === 'update') return '更新';
  if (operationType === 'delete') return '删除';
  return operationTypeRaw;
};

const humanizeAssistantToolEvent = (event: {
  tool_name?: unknown;
  status?: unknown;
  message?: unknown;
  detail?: unknown;
}): string => {
  const toolName = String(event.tool_name || '').trim().toLowerCase();
  const status = String(event.status || '').trim().toLowerCase();

  if (toolName === 'restore_assistant_context' || toolName === 'load_extraction_payload') {
    return '正在读取当前文档上下文';
  }
  if (toolName === 'locate_table_cells') {
    return status === 'clarify' ? '正在核对目标表格行，仍需进一步确认' : '正在核对目标表格行';
  }
  if (toolName === 'match_fields') {
    return status === 'empty' ? '正在检查相关字段，但当前还没有稳定命中' : '正在匹配相关字段';
  }
  if (toolName === 'summarize_document_context') {
    return '正在整理文档重点';
  }
  if (toolName === 'prepare_knowledge_context') {
    return '正在整理与你问题相关的文档背景';
  }
  if (toolName === 'prepare_web_research_context') {
    return status === 'fallback' ? '当前无法给出实时联网结果，正在切换为保守回答' : '正在整理外部信息问题的回答范围';
  }
  if (toolName === 'read_figures' || toolName === 'inspect_figure') {
    return '正在核对图片和图表信息';
  }
  if (toolName === 'build_turn_artifacts') {
    return '正在整理本轮回答所需的上下文';
  }
  if (toolName === 'assistant_model_stream') {
    return status === 'fallback' ? '正在切换到保守回答模式' : '正在生成回答';
  }

  const message = String(event.message || '').trim();
  if (message) return message;
  if (status === 'fallback') return '正在切换到保守回答模式';
  return '正在处理你的问题';
};

const summarizeAssistantRowPreview = (candidate: Record<string, unknown>): string => {
  const rowPreview = Array.isArray(candidate.row_preview) ? candidate.row_preview as Array<unknown> : [];
  return rowPreview
    .flatMap((row) => {
      if (!row || typeof row !== 'object') return [];
      const cells = Array.isArray((row as Record<string, unknown>).cells)
        ? (row as Record<string, unknown>).cells as Array<unknown>
        : [];
      return cells
        .filter((cell) => cell && typeof cell === 'object')
        .slice(0, 4)
        .map((cell) => {
          const item = cell as Record<string, unknown>;
          const header = String(item.header || item.label || '列').trim();
          const text = String(item.text || item.value || '').trim();
          return text ? `${header}=${text}` : '';
        })
        .filter(Boolean);
    })
    .slice(0, 4)
    .join(' | ');
};

const summarizeAssistantFactPreview = (item: Record<string, unknown>): string => {
  const kind = String(item.kind || '').trim().toLowerCase();
  if (kind === 'field') {
    const label = String(item.label || '字段').trim();
    const value = String(item.value || '').trim();
    const page = Number(item.page || 0);
    const refId = String(item.ref_id || '').trim();
    const bits = [
      value ? `${label}: ${value}` : label,
      page > 0 ? `第 ${page} 页` : '',
      refId ? `ref_id=${refId}` : '',
    ].filter(Boolean);
    return bits.join(' · ');
  }
  if (kind === 'table') {
    const tableId = String(item.table_id || '表格').trim();
    const headers = Array.isArray(item.headers)
      ? (item.headers as Array<unknown>).map((header) => String(header || '').trim()).filter(Boolean)
      : [];
    const rowPreview = Array.isArray(item.row_preview) ? item.row_preview as Array<unknown> : [];
    const firstRow = rowPreview[0] && typeof rowPreview[0] === 'object'
      ? rowPreview[0] as Record<string, unknown>
      : null;
    const cells = Array.isArray(firstRow?.cells) ? firstRow.cells as Array<unknown> : [];
    const previewText = cells
      .filter((cell) => cell && typeof cell === 'object')
      .slice(0, 3)
      .map((cell) => {
        const current = cell as Record<string, unknown>;
        const header = String(current.header || '列').trim();
        const text = String(current.text || '').trim();
        return text ? `${header}=${text}` : '';
      })
      .filter(Boolean)
      .join(' | ');
    const bits = [
      tableId,
      headers.length > 0 ? `表头: ${headers.slice(0, 3).join('、')}` : '',
      previewText,
    ].filter(Boolean);
    return bits.join(' · ');
  }
  return String(item.label || item.kind || '').trim();
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
  toolEvents?: AssistantToolEvent[];
  status?: 'streaming' | 'done' | 'error';
  payload?: Record<string, unknown>;
};

type AssistantCompanionState = {
  citations: AssistantCitation[];
  actionPreview: AssistantActionPreview | null;
  toolEvents: AssistantToolEvent[];
};

const EMPTY_ASSISTANT_COMPANION_STATE: AssistantCompanionState = {
  citations: [],
  actionPreview: null,
  toolEvents: [],
};

const isRenderableAssistantDialogMessage = (msg: AssistantDialogMessage): boolean => {
  const messageType = String(msg.messageType || '').trim();
  return messageType !== 'tool_status' && messageType !== 'action_preview' && messageType !== 'system_notice';
};

const DEFAULT_SCHEMA = {
  auto_infer: true,
  prefer_llm: true,
  max_auto_fields: 8,
};

const ASSISTANT_SESSION_STORAGE_KEY = 'module2_assistant_session_map_v1';
const GENERIC_ASSISTANT_SESSION_KEY = '__module2_no_file__';

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

const toAssistantPayloadRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? value as Record<string, unknown> : {};

const toAssistantCitations = (value: unknown): AssistantCitation[] =>
  Array.isArray(value) ? value as AssistantCitation[] : [];

const toAssistantActionPreview = (value: unknown): AssistantActionPreview | null =>
  value && typeof value === 'object' && Object.keys(value as Record<string, unknown>).length > 0
    ? value as AssistantActionPreview
    : null;

const toAssistantToolEvents = (value: unknown): AssistantToolEvent[] =>
  Array.isArray(value) ? value as AssistantToolEvent[] : [];

const toAssistantObjectLock = (value: unknown): AssistantObjectLock | null =>
  value && typeof value === 'object' && Object.keys(value as Record<string, unknown>).length > 0
    ? value as AssistantObjectLock
    : null;

const toAssistantCompanionState = (payloadRaw: unknown): AssistantCompanionState => {
  const payload = toAssistantPayloadRecord(payloadRaw);
  return {
    citations: toAssistantCitations(payload.citations),
    actionPreview: toAssistantActionPreview(payload.action_preview),
    toolEvents: toAssistantToolEvents(payload.tool_events),
  };
};

const findLatestAssistantPayload = (messages: AssistantSessionMessagePayload[]): Record<string, unknown> => {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const current = messages[index];
    if (String(current.role || '').trim().toLowerCase() === 'assistant') {
      return toAssistantPayloadRecord(current.payload);
    }
  }
  return {};
};

const toAssistantVisibleWarnings = (payloadRaw: unknown): string[] => {
  const payload = toAssistantPayloadRecord(payloadRaw);
  const userVisible = payload.user_visible_warnings;
  return filterAssistantWarnings(Array.isArray(userVisible) ? userVisible : payload.warnings);
};

const mergeAssistantFinalAnswer = (currentContent: string, finalContent: string): string => {
  const current = normalizeAssistantDisplayText(currentContent);
  const final = normalizeAssistantDisplayText(finalContent);
  if (!final) return current;
  const currentTrimmed = current.trimEnd();
  if (!currentTrimmed) return final;
  if (final === currentTrimmed) return currentTrimmed;
  if (final.startsWith(currentTrimmed)) {
    return `${currentTrimmed}${final.slice(currentTrimmed.length)}`;
  }
  const maxOverlap = Math.min(currentTrimmed.length, final.length, 120);
  for (let size = maxOverlap; size > 0; size -= 1) {
    if (currentTrimmed.endsWith(final.slice(0, size))) {
      return `${currentTrimmed}${final.slice(size)}`;
    }
  }
  return final;
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
  activeDocFileHash: string,
  officePreviewMap: Record<string, OfficePreviewState>,
  extractionJob: ExtractionJobState | null,
  artifactMap: Record<string, { artifactUrl?: string; artifactPath?: string }>,
  fallbackSelectedFiles: PersistedWorkbenchFile[] = [],
): WorkbenchSessionSnapshot => ({
  version: 1,
  activeDocIndex,
  activeDocFileHash: String(activeDocFileHash || '').trim(),
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

const isMissingExtractionJobMessage = (messageRaw: unknown): boolean => {
  const message = String(messageRaw || '').trim().toLowerCase();
  if (!message) return false;
  return (
    message.includes('not found')
    || message.includes('job not found')
    || message.includes('extraction job not found')
    || message.includes('状态码 404')
    || message.includes('404')
  );
};

const normalizeExtractionJobId = (value: unknown): string => {
  const jobId = String(value || '').trim();
  return /^extract_job_[A-Za-z0-9]+$/.test(jobId) ? jobId : '';
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

type TraceDataframePayload = {
  headers: string[];
  rows: string[][];
  rowCount: number;
  colCount: number;
};

const toTraceDataframePayload = (value: unknown): TraceDataframePayload => {
  const obj = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
  const headers = Array.isArray(obj.headers)
    ? obj.headers.map((item) => String(item ?? '').trim()).filter(Boolean)
    : [];
  const rows = Array.isArray(obj.rows)
    ? obj.rows
        .map((row) => (Array.isArray(row) ? row.map((cell) => String(cell ?? '').trim()) : []))
        .filter((row) => row.some((cell) => cell.length > 0))
    : [];
  const rowCountRaw = Number(obj.row_count ?? rows.length);
  const colCountRaw = Number(
    obj.col_count ?? Math.max(headers.length, ...rows.map((row) => row.length), 0)
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

const TRACE_SOURCE_LABELS: Record<string, string> = {
  pdf_mineru: 'PDF MinerU',
  pdf_roi_crop: 'PDF 页面裁剪',
  gemini_vision: 'Gemini Vision',
  gemini_vision_figure: 'Gemini Vision 图表解析',
  gemini_vision_table: 'Gemini Vision 表格解析',
  table_structured: '结构化表格抽取',
  model: 'Gemini Vision 数据恢复',
  key_values: 'Gemini Vision 关键值恢复',
  text_blocks: 'Gemini Vision 文本恢复',
  docx_chart_xml_merge: 'DOCX 图表结构合并',
};

const toTraceSourceLabel = (value: unknown): string => {
  const key = String(value ?? '').trim().toLowerCase();
  if (!key) return '';
  return TRACE_SOURCE_LABELS[key] || String(value ?? '').trim();
};

export const DeepReadWorkbench: React.FC<{ isSidebarCollapsed?: boolean }> = ({ isSidebarCollapsed = false }) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [schemaText] = useState<string>(JSON.stringify(DEFAULT_SCHEMA, null, 2));
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
  const [expandedTraceCardKey, setExpandedTraceCardKey] = useState('');
  const [assistantStatus, setAssistantStatus] = useState<'idle' | 'confirmed' | 'rolled_back'>('idle');
  const [assistantMessage, setAssistantMessage] = useState("等待生成可执行建议。");
  const [assistantInput, setAssistantInput] = useState('');
  const [assistantQueryLoading, setAssistantQueryLoading] = useState(false);
  const [assistantAnswer, setAssistantAnswer] = useState('');
  const [assistantWarnings, setAssistantWarnings] = useState<string[]>([]);
  const [assistantDialog, setAssistantDialog] = useState<AssistantDialogMessage[]>([]);
  const [assistantSessionId, setAssistantSessionId] = useState('');
  const [assistantCurrentLock, setAssistantCurrentLock] = useState<AssistantObjectLock | null>(null);
  const [assistantCompanionOpen, setAssistantCompanionOpen] = useState(false);
  const [assistantCompanionCitations, setAssistantCompanionCitations] = useState<AssistantCitation[]>([]);
  const [assistantCompanionActionPreview, setAssistantCompanionActionPreview] = useState<AssistantActionPreview | null>(null);
  const [assistantRuntimeEvents, setAssistantRuntimeEvents] = useState<AssistantToolEvent[]>([]);
  const [smartUnitTab, setSmartUnitTab] = useState<SmartUnitTabId>('results');
  const [assistantTabUnread, setAssistantTabUnread] = useState(false);
  const [resultsTabUnread, setResultsTabUnread] = useState(false);
  const [showAssistantHelp, setShowAssistantHelp] = useState(false);
  const [isPreviewFocused, setIsPreviewFocused] = useState(false);
  const [isUploaderDragOver, setIsUploaderDragOver] = useState(false);
  const [resultSearchQuery, setResultSearchQuery] = useState('');
  const [paneLayout, setPaneLayout] = useState<WorkbenchPaneLayout>(() => readWorkbenchPaneLayout());
  const [paneResizeSide, setPaneResizeSide] = useState<PaneResizeSide | null>(null);
  const [workbenchViewportWidth, setWorkbenchViewportWidth] = useState(0);
  const prefersReducedMotion = useReducedMotion();
  
  // Viewport Controls
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [activeTraceKey, setActiveTraceKey] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const assistantInputRef = useRef<HTMLTextAreaElement>(null);
  const textPreviewRef = useRef<HTMLDivElement>(null);
  const assistantDialogRef = useRef<HTMLDivElement>(null);
  const workbenchViewportRef = useRef<HTMLDivElement>(null);
  const documentsRef = useRef<DocumentResult[]>([]);
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
  const paneResizeFrameRef = useRef<number | null>(null);
  const paneResizeLatestXRef = useRef<number | null>(null);
  const paneResizeStartRef = useRef<{
    clientX: number;
    leftWidth: number;
    rightWidth: number;
    side: PaneResizeSide;
  } | null>(null);

  useEffect(() => () => {
    clearSpreadsheetPreviewWarmupQueue();
  }, []);

  useEffect(() => {
    documentsRef.current = documents;
  }, [documents]);

  const activeDoc = documents[activeDocIndex] || null;
  const activeAssistantSessionKey = String(activeDoc?.file_hash || '').trim() || GENERIC_ASSISTANT_SESSION_KEY;
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

  useEffect(() => {
    const target = workbenchViewportRef.current;
    if (!target || typeof ResizeObserver === 'undefined') return;

    const updateWidth = () => {
      setWorkbenchViewportWidth(Math.max(0, Math.floor(target.clientWidth)));
    };

    updateWidth();
    const observer = new ResizeObserver(() => updateWidth());
    observer.observe(target);

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!workbenchViewportWidth) return;
    setPaneLayout((prev) => {
      const next = clampWorkbenchPaneLayout(prev, workbenchViewportWidth, showLeftPanel);
      return prev.leftWidth === next.leftWidth && prev.rightWidth === next.rightWidth ? prev : next;
    });
  }, [showLeftPanel, workbenchViewportWidth]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(MODULE2_PANE_LAYOUT_STORAGE_KEY, JSON.stringify(paneLayout));
  }, [paneLayout]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const frame = window.requestAnimationFrame(() => {
      window.dispatchEvent(new Event('resize'));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [paneLayout.leftWidth, paneLayout.rightWidth, showLeftPanel]);

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
    const payload = toAssistantPayloadRecord(message.payload);
    const messageTypeRaw = String(message.message_type || '').trim();
    const normalizedType: AssistantDialogMessage['messageType'] =
      messageTypeRaw === 'tool_status' || messageTypeRaw === 'action_preview' || messageTypeRaw === 'system_notice'
        ? messageTypeRaw
        : role === 'user'
          ? 'user_message'
          : 'assistant_text';
    return {
      id: String(message.message_id || `assistant-${Date.now()}`),
      role,
      content: String(message.content || ''),
      messageType: normalizedType,
      status: 'done',
      payload,
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

  const resetAssistantCompanionState = (keepLock = false) => {
    setAssistantCompanionOpen(false);
    setAssistantCompanionCitations([]);
    setAssistantCompanionActionPreview(null);
    setAssistantRuntimeEvents([]);
    if (!keepLock) {
      setAssistantCurrentLock(null);
    }
  };

  const applyAssistantCompanionState = (
    nextState: AssistantCompanionState,
    options?: {
      open?: boolean;
    }
  ) => {
    setAssistantCompanionCitations(nextState.citations);
    setAssistantCompanionActionPreview(nextState.actionPreview);
    setAssistantRuntimeEvents(nextState.toolEvents);
    if (typeof options?.open === 'boolean') {
      setAssistantCompanionOpen(options.open);
    } else if (nextState.actionPreview) {
      setAssistantCompanionOpen(true);
    }
  };

  const renderableAssistantDialog = useMemo(
    () => assistantDialog.filter((msg) => isRenderableAssistantDialogMessage(msg)),
    [assistantDialog],
  );
  const latestRenderableAssistantMessageId = useMemo(() => {
    for (let index = renderableAssistantDialog.length - 1; index >= 0; index -= 1) {
      const current = renderableAssistantDialog[index];
      if (current.role === 'assistant' && current.messageType === 'assistant_text') {
        return current.id;
      }
    }
    return '';
  }, [renderableAssistantDialog]);

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
    const sessionDocuments = cached.length === 0 ? getSessionPersistedDocuments(session) : [];
    const restoredDocuments = cached.length > 0 ? cached : sessionDocuments;
    if (restoredDocuments.length > 0) {
      setDocuments(restoredDocuments);
      if (cached.length > 0) {
        setInfoMessage(`已加载 ${restoredDocuments.length} 条本地缓存抽取结果。`);
      } else {
        writeExtractionDocuments(restoredDocuments);
        setInfoMessage(`已从工作台会话恢复 ${restoredDocuments.length} 条抽取结果。`);
      }
    }
    if (!session) {
      persistedSelectedFilesRef.current = [];
      setSessionRestorePending(false);
      setSessionHydrated(true);
      return () => {
        active = false;
      };
    }

    const persistedJob =
      session.extractionJob && normalizeExtractionJobId(session.extractionJob.job_id)
        ? session.extractionJob
        : null;
    setActiveDocIndex(Math.max(0, Number(session.activeDocIndex || 0)));
    setOfficePreviewMap(session.officePreviewMap || {});
    setExtractionJob(persistedJob);
    setIsProcessing(Boolean(persistedJob && !persistedJob.terminal));
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
      || documents.length > 0
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
      String(activeDoc?.file_hash || ''),
      officePreviewMap,
      extractionJob,
      selectedFileArtifacts,
      persistedSelectedFilesRef.current,
    );
    persistedSelectedFilesRef.current = snapshot.selectedFiles;
    writeWorkbenchSession(snapshot);
  }, [activeDoc?.file_hash, activeDocIndex, documents.length, extractionJob, officePreviewMap, selectedFileArtifacts, selectedFiles, sessionHydrated, sessionRestorePending]);

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

  useEffect(() => {
    if (!expandedTraceCardKey) return;
    const exists = traceHits.some((hit, idx) => toTraceHitKey(hit, idx) === expandedTraceCardKey);
    if (!exists) {
      setExpandedTraceCardKey('');
    }
  }, [expandedTraceCardKey, traceHits]);

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
        throw new Error('原文定位失败');
      }
      const payload = (await response.json()) as TraceLocateResponse;
      if (seq !== traceRequestSeqRef.current) return;
      const hits = Array.isArray(payload.hits) ? payload.hits : [];
      setTraceHits(hits.length > 0 ? hits : toTraceHits(doc, fieldKey));
    } catch (error) {
      if (seq !== traceRequestSeqRef.current) return;
      setTraceHits(toTraceHits(doc, fieldKey));
      setTraceError(error instanceof Error ? error.message : '原文定位失败');
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
      setExpandedTraceCardKey('');
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
    resetAssistantCompanionState();
    setOfficePreviewMap({});
    setActiveTraceKey('');
    setExpandedTraceCardKey('');
    const fileHash = activeAssistantSessionKey;
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
              document: activeDoc || undefined,
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
        const nextLock =
          toAssistantObjectLock(payload.current_object_lock)
          ?? toAssistantObjectLock(findLatestAssistantPayload(payload.messages).current_object_lock);
        setAssistantCurrentLock(nextLock);
        if (Array.isArray(payload.messages) && payload.messages.length > 0) {
          const nextDialog = payload.messages.map(toAssistantDialogMessage).filter(isRenderableAssistantDialogMessage);
          const latestPayload = findLatestAssistantPayload(payload.messages);
          const latestCompanion = toAssistantCompanionState(latestPayload);
          setAssistantDialog(nextDialog);
          setAssistantWarnings(toAssistantVisibleWarnings(latestPayload));
          applyAssistantCompanionState(latestCompanion, { open: Boolean(latestCompanion.actionPreview) });
        } else {
          setAssistantDialog([]);
          setAssistantWarnings([]);
          resetAssistantCompanionState(true);
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
  }, [activeAssistantSessionKey]);

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
  const resultSectionCountText = resultCountText || (activeDoc ? '等待结果' : '暂无结果');
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
  const hasTraceTypeStats = Object.values(traceTypeStats).some((count) => count > 0);
  const traceSectionCountText = `${traceHits.length} 条`;
  const traceSectionHint = traceHits.length > 0
    ? '字段、表格与图片定位路径'
    : activeDoc
      ? '等待生成原文定位信息'
      : '抽取完成后在此查看定位结果';

  const assistantActivityKey = useMemo(
    () =>
      JSON.stringify({
        summary: activeSummaryText,
        summaryLoading: activeSummaryLoading,
        dialogCount: renderableAssistantDialog.length,
        lastDialogId: renderableAssistantDialog[renderableAssistantDialog.length - 1]?.id ?? '',
        assistantAnswer,
        assistantWarnings: assistantWarnings.join('|'),
        assistantMessage,
        assistantQueryLoading,
        assistantStatus,
      }),
    [
      activeSummaryText,
      activeSummaryLoading,
      renderableAssistantDialog,
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
      renderableAssistantDialog.length > 0 ||
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
    renderableAssistantDialog.length,
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

  const applyExtractionDocuments = (
    docs: DocumentResult[],
    options?: {
      partial?: boolean;
    },
  ) => {
    const partial = Boolean(options?.partial);
    const previousActiveHash = String(activeDoc?.file_hash || '').trim();
    const previousActiveName = String(activeDoc?.file_name || '').trim().toLowerCase();
    const previousDocCount = documents.length;
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

    let nextActiveIndex = 0;
    if (partial && documentsWithPreview.length > 0) {
      const matchedIndex = documentsWithPreview.findIndex((doc) => {
        const nextHash = String(doc.file_hash || '').trim();
        if (previousActiveHash && nextHash === previousActiveHash) return true;
        const nextName = String(doc.file_name || '').trim().toLowerCase();
        return Boolean(previousActiveName) && nextName === previousActiveName;
      });
      if (matchedIndex >= 0) {
        nextActiveIndex = matchedIndex;
      } else {
        nextActiveIndex = Math.max(0, Math.min(activeDocIndex, documentsWithPreview.length - 1));
      }
    }

    setDocuments(documentsWithPreview);
    writeExtractionDocuments(documentsWithPreview);
    setActiveDocIndex(nextActiveIndex);
    if (!partial || nextActiveIndex !== activeDocIndex) {
      setPdfViewportPage(1);
      setPdfScrollRequest(createPdfScrollRequest(1));
    }
    if (documentsWithPreview.length > 0) {
      const nextActiveDoc = documentsWithPreview[nextActiveIndex] || documentsWithPreview[0];
      const nextActiveHash = String(nextActiveDoc?.file_hash || '').trim();
      if (!partial || previousDocCount === 0 || nextActiveHash !== previousActiveHash) {
        void requestSummary(nextActiveDoc);
      }
    }

    const firstErrorDoc = documentsWithPreview.find((doc) => doc.errors && doc.errors.length > 0);
    if (firstErrorDoc) {
      setErrorMessage(firstErrorDoc.errors.join(' | '));
      return;
    }

    if (partial) {
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
    const normalizedJobId = normalizeExtractionJobId(jobId);
    if (!normalizedJobId) {
      extractionJobPollRef.current = '';
      extractionJobApiBaseRef.current = '';
      setExtractionJob(null);
      setIsProcessing(false);
      setActiveSummaryLoading(false);
      setErrorMessage('抽取任务标识无效，当前任务状态已清理，请重新发起解析。');
      return;
    }
    extractionJobPollRef.current = normalizedJobId;
    const pollIntervalMs = 1200;
    const pollTimeoutMs = 45 * 60 * 1000;
    const startedAt = Date.now();
    while (Date.now() - startedAt < pollTimeoutMs) {
      if (extractionJobPollRef.current !== normalizedJobId) return;
      try {
        const fetchResult = await fetchExtractWithFallback(
          `/extract/jobs/status/${encodeURIComponent(normalizedJobId)}?include_documents=true`,
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

        if (!payload.terminal && Array.isArray(payload.documents) && payload.documents.length > 0) {
          applyExtractionDocuments(payload.documents, { partial: true });
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
        if (extractionJobPollRef.current !== normalizedJobId) return;
        const message =
          error instanceof Error && String(error.message || '').trim()
            ? String(error.message || '').trim()
            : '抽取进度同步失败';
        if (isMissingExtractionJobMessage(message)) {
          extractionJobPollRef.current = '';
          extractionJobApiBaseRef.current = '';
          setExtractionJob(null);
          setIsProcessing(false);
          setActiveSummaryLoading(false);
          if (documentsRef.current.length > 0) {
            setErrorMessage('');
            setInfoMessage('历史抽取任务状态已从后端释放，当前页面已保留最近一次解析结果。');
          } else {
            setErrorMessage(`${message}，当前任务状态已清理，请重新发起解析。`);
            setInfoMessage('检测到历史抽取任务已失效，界面已恢复为可重新发起解析的状态。');
          }
          return;
        }
        setInfoMessage('正在同步最新解析进度...');
      }
      await new Promise((resolve) => window.setTimeout(resolve, pollIntervalMs));
    }
    if (extractionJobPollRef.current === normalizedJobId) {
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
    setExpandedTraceCardKey('');
    setAssistantStatus('idle');
    setAssistantMessage("等待生成可执行建议。");
    setAssistantInput('');
    setAssistantAnswer('');
    setAssistantWarnings([]);
    setAssistantQueryLoading(false);
    setAssistantDialog([]);
    resetAssistantCompanionState();
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
    const normalizedRemovedName = removed.name.trim().toLowerCase();
    const removingParsedResult = documents.some(
      (doc) => String(doc.file_name || '').trim().toLowerCase() === normalizedRemovedName,
    );
    const confirmMessage = selectedFiles.length <= 1
      ? '移除最后一份文件会清空当前页面的解析结果，是否继续？'
      : removingParsedResult
        ? `移除 ${removed.name} 会同步移除它的解析结果，是否继续？`
        : '';
    if (confirmMessage && typeof window !== 'undefined' && !window.confirm(confirmMessage)) {
      return;
    }

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
    resetAssistantCompanionState();
    traceRequestSeqRef.current += 1;
    setTraceHits([]);
    setTraceError('');
    setTraceLoading(false);
    setActiveTraceKey('');
    setExpandedTraceCardKey('');

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
          '',
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
    anchor.download = `非结构化文档分析_抽取结果_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
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
          const keyPoints = Array.isArray(payload.key_points)
            ? payload.key_points.map((item) => String(item || '').trim()).filter(Boolean)
            : [];
          const header = String(payload.header || '').trim();
          const value = String(payload.value || '').trim();
          const rowLabel = String(payload.row_label || '').trim();
          const evidenceLead = citation.citation_type === 'table'
            ? rowLabel
              ? `当前记录：${rowLabel}`
              : '来自当前表格记录'
            : citation.citation_type === 'figure'
              ? '来自当前图表对象'
              : '来自当前字段结果';
          const summaryBits = [
            evidenceLead,
            header ? `列: ${header}` : '',
            '点击可定位原文',
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
    const previewStatus = String(payload.preview_status || 'ready').trim().toLowerCase();
    const lockQuality = String(payload.lock_quality || '').trim();
    const focusScope = String(payload.focus_scope || '').trim();
    const focusReason = String(payload.focus_reason || '').trim();
    const clarificationQuestion = String(payload.clarification_question || '').trim();
    const operationType = String(payload.operation_type || '').trim();
    const targetTable = String(payload.target_table || '').trim();
    const tableStatus = String(payload.target_table_status || '').trim().toLowerCase();
    const sqlReady = Boolean(payload.sql_ready);
    const sqlPreviewText = String(payload.sql_preview_text || '').trim();
    const affectedScope = String(payload.affected_scope || '').trim();
    const missingRequirements = Array.isArray(payload.missing_requirements)
      ? payload.missing_requirements.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const confirmationChecklist = Array.isArray(payload.confirmation_checklist)
      ? payload.confirmation_checklist.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    const evidenceBasis = payload.evidence_basis && typeof payload.evidence_basis === 'object'
      ? payload.evidence_basis as Record<string, unknown>
      : null;
    const identifierFields = Array.isArray(evidenceBasis?.identifier_fields)
      ? evidenceBasis?.identifier_fields.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>
      : [];
    const factItems = Array.isArray(payload.fact_items)
      ? payload.fact_items.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>
      : [];
    const focusLock = payload.focus_lock && typeof payload.focus_lock === 'object'
      ? payload.focus_lock as AssistantObjectLock
      : null;
    const candidateRows = Array.isArray(payload.candidate_rows)
      ? payload.candidate_rows.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>
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
              类型：{humanizeAssistantActionType(preview.action_type)}
            </span>
          )}
          {operationType && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              操作：{humanizeAssistantOperationType(operationType)}
            </span>
          )}
          {preview.target && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              目标：{preview.target}
            </span>
          )}
          <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
            状态：{previewStatus === 'blocked' ? '已阻塞' : '可继续确认'}
          </span>
          {lockQuality && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              锁定强度：{humanizeAssistantLockQuality(lockQuality)}
            </span>
          )}
          {focusScope && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              绑定范围：{humanizeAssistantFocusScope(focusScope)}
            </span>
          )}
          {matchedFields.length > 0 && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              字段：{matchedFields.slice(0, 4).join('、')}
            </span>
          )}
          {targetTable && (
            <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
              目标表：{targetTable}
            </span>
          )}
          <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
            SQL：{sqlReady ? '已生成预览' : '仍待补充'}
          </span>
        </div>
        {targetTable && (
          <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            目标表校验：
            {tableStatus === 'whitelisted'
              ? ` ${targetTable} 已在白名单内。`
              : ` ${targetTable} 目前还不在白名单内，正式执行前还需要补齐表级校验。`}
          </div>
        )}
        {focusLock && (
          <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            当前绑定对象：{humanizeAssistantLockType(String(focusLock.lock_type || ''))}
            {focusLock.label ? ` · ${focusLock.label}` : ''}
            {focusLock.page ? ` · 第 ${focusLock.page} 页` : ''}
          </div>
        )}
        {affectedScope && (
          <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            影响范围：{affectedScope}
          </div>
        )}
        {identifierFields.length > 0 && (
          <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            <div className="font-semibold text-slate-800 dark:text-slate-100">当前用于定位记录的条件</div>
            <div className="mt-1 space-y-1">
              {identifierFields.slice(0, 3).map((item, index) => {
                const label = String(item.label || '字段').trim();
                const value = String(item.value || '').trim();
                const refId = String(item.ref_id || '').trim();
                return (
                  <div key={`assistant-preview-identifier-${index}`}>
                    {label}={value || '空值'}
                    {refId ? ` · ref_id=${refId}` : ''}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {sqlPreviewText && (
          <div className="mt-2 rounded-xl border border-slate-200/80 bg-slate-950 px-3 py-2 text-[10px] leading-relaxed text-slate-100 dark:border-slate-700">
            <div className="mb-1 font-semibold text-slate-200">SQL 预览</div>
            <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-relaxed text-slate-100">
              {sqlPreviewText}
            </pre>
          </div>
        )}
        {!sqlPreviewText && missingRequirements.length > 0 && (
          <div className="mt-2 rounded-xl border border-dashed border-amber-300/80 bg-white/70 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-amber-800/70 dark:bg-slate-950/30 dark:text-slate-300">
            还不能形成最终 SQL，主要还缺少：
            <div className="mt-1 space-y-1">
              {missingRequirements.slice(0, 4).map((item, index) => (
                <div key={`assistant-preview-missing-${index}`}>- {item}</div>
              ))}
            </div>
          </div>
        )}
        {confirmationChecklist.length > 0 && (
          <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            <div className="font-semibold text-slate-800 dark:text-slate-100">确认清单</div>
            <div className="mt-1 space-y-1">
              {confirmationChecklist.slice(0, 4).map((item, index) => (
                <div key={`assistant-preview-check-${index}`}>- {item}</div>
              ))}
            </div>
          </div>
        )}
        {previewStatus === 'blocked' && (
          <div className="mt-2 space-y-2">
            <div className="rounded-xl border border-dashed border-amber-300/80 bg-white/70 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-amber-800/70 dark:bg-slate-950/30 dark:text-slate-300">
              当前候选数：{candidateRows.length}。请先确认目标记录后再继续生成可执行预览。
              {focusReason ? ` 当前阻塞原因：${focusReason}。` : ''}
              {clarificationQuestion ? ` ${clarificationQuestion}` : ''}
            </div>
            {candidateRows.length > 0 && (
              <div className="space-y-1.5">
                {candidateRows.slice(0, 3).map((candidate, index) => {
                  const rank = Number(candidate.rank || index + 1);
                  const tableId = String(candidate.table_id || '表格').trim();
                  const rowLabel = String(candidate.row_label || '').trim();
                  const matchedTerms = Array.isArray(candidate.matched_anchor_terms)
                    ? candidate.matched_anchor_terms.map((item) => String(item || '').trim()).filter(Boolean)
                    : [];
                  const nearTerms = Array.isArray(candidate.near_anchor_terms)
                    ? candidate.near_anchor_terms.map((item) => String(item || '').trim()).filter(Boolean)
                    : [];
                  const missingTerms = Array.isArray(candidate.missing_anchor_terms)
                    ? candidate.missing_anchor_terms.map((item) => String(item || '').trim()).filter(Boolean)
                    : [];
                  const previewText = summarizeAssistantRowPreview(candidate);
                  return (
                    <div
                      key={`assistant-preview-candidate-${rank}-${tableId}-${index}`}
                      className="rounded-xl border border-white/80 bg-white/85 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300"
                    >
                      <div className="font-semibold text-slate-800 dark:text-slate-100">
                        候选 {rank} · {tableId}
                        {candidate.row_index ? ` · 表内第 ${candidate.row_index} 行` : ''}
                        {candidate.page ? ` · 第 ${candidate.page} 页` : ''}
                      </div>
                      {rowLabel && (
                        <div className="mt-1">行标签：{rowLabel}</div>
                      )}
                      {previewText && (
                        <div className="mt-1">行预览：{previewText}</div>
                      )}
                      {matchedTerms.length > 0 && (
                        <div className="mt-1">已命中锚点：{matchedTerms.join('、')}</div>
                      )}
                      {nearTerms.length > 0 && (
                        <div className="mt-1">近似锚点：{nearTerms.join('、')}</div>
                      )}
                      {missingTerms.length > 0 && (
                        <div className="mt-1 text-amber-700 dark:text-amber-300">缺失锚点：{missingTerms.join('、')}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
        {focusScope === 'ocr_fact_group' && factItems.length > 0 && (
          <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-700 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            <div className="font-semibold text-slate-800 dark:text-slate-100">当前基于 OCR 事实组生成预览</div>
            <div className="mt-1 space-y-1">
              {factItems.slice(0, 4).map((item, index) => (
                <div key={`assistant-preview-fact-${index}`}>
                  {summarizeAssistantFactPreview(item)}
                </div>
              ))}
            </div>
          </div>
        )}
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
    const progressLabel = String(msg.payload?.progress_label || '').trim();
    const isLatestAssistantText =
      isAssistant &&
      msg.messageType === 'assistant_text' &&
      msg.id === latestRenderableAssistantMessageId;
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
            <div data-testid={isLatestAssistantText ? 'module2-assistant-answer' : undefined}>
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
            {msg.status === 'streaming' && isAssistant && progressLabel && (
              <div className="mt-2 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">
                {progressLabel}
              </div>
            )}
            {msg.status === 'streaming' && isAssistant && contentText && (
              <div className="mt-2 text-[10px] text-slate-400 dark:text-slate-500">
                正在继续生成回答...
              </div>
            )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderAssistantLockBanner = (compact = false) => {
    if (!assistantCurrentLock) return null;
    const rowIndex = Number(assistantCurrentLock.row_index || 0);
    const sourceRowIndex = Number(assistantCurrentLock.source_row_index || 0);
    const lockQuality = String(assistantCurrentLock.lock_quality || '').trim();
    const meta = assistantCurrentLock.metadata && typeof assistantCurrentLock.metadata === 'object'
      ? assistantCurrentLock.metadata
      : {};
    const header = String(meta.header || '').trim();
    const recognitionTier = String(meta.recognition_tier || '').trim();
    const snippet = String(meta.snippet || '').trim();
    const factPreview = Array.isArray(meta.fact_preview)
      ? meta.fact_preview.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>
      : [];
    const bits = [
      `类型: ${humanizeAssistantLockType(String(assistantCurrentLock.lock_type || ''))}`,
      assistantCurrentLock.page ? `第 ${assistantCurrentLock.page} 页` : '',
      rowIndex > 0 ? `表内第 ${rowIndex} 行` : '',
      sourceRowIndex > 0 ? `原始第 ${sourceRowIndex} 行` : '',
      header ? `当前列: ${header}` : '',
      lockQuality ? `锁定强度: ${humanizeAssistantLockQuality(lockQuality)}` : '',
      recognitionTier ? `识别层级: ${recognitionTier}` : '',
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
        {snippet && (
          <div className="mt-2 rounded-xl bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-blue-900/90 ring-1 ring-inset ring-blue-200/70 dark:bg-slate-950/30 dark:text-blue-100/90 dark:ring-blue-900/60">
            当前摘要：{snippet}
          </div>
        )}
        {String(assistantCurrentLock.lock_type || '').trim().toLowerCase() === 'ocr_fact_group' && factPreview.length > 0 && (
          <div className="mt-2 rounded-xl bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-blue-900/90 ring-1 ring-inset ring-blue-200/70 dark:bg-slate-950/30 dark:text-blue-100/90 dark:ring-blue-900/60">
            <div className="font-semibold">已锁定的 OCR 事实</div>
            <div className="mt-1 space-y-1">
              {factPreview.slice(0, 4).map((item, index) => (
                <div key={`assistant-lock-fact-${index}`}>
                  {summarizeAssistantFactPreview(item)}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderAssistantCompanionPanel = (compact = false) => {
    const hasSummary = activeSummaryLoading || Boolean(activeSummaryText.trim());
    const hasCompanionContent = (
      hasSummary
      || assistantWarnings.length > 0
      || Boolean(assistantCurrentLock)
      || assistantCompanionCitations.length > 0
      || Boolean(assistantCompanionActionPreview)
      || assistantRuntimeEvents.length > 0
    );
    if (!hasCompanionContent) return null;

    const badges = [
      hasSummary ? '摘要' : '',
      assistantCompanionCitations.length > 0 ? `${assistantCompanionCitations.length} 条依据` : '',
      assistantCompanionActionPreview ? '操作预览' : '',
      assistantWarnings.length > 0 ? `${assistantWarnings.length} 条提示` : '',
      assistantRuntimeEvents.length > 0 ? '处理记录' : '',
    ].filter(Boolean);

    return (
      <div className={cn(
        "border-t border-slate-200/70 bg-slate-50/70 px-3 py-2.5 dark:border-slate-800/70 dark:bg-slate-950/20",
        compact && "px-2.5 py-2"
      )}>
        <button
          type="button"
          onClick={() => setAssistantCompanionOpen((prev) => !prev)}
          className={cn(
            "flex w-full items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white/80 px-3 py-2 text-left shadow-sm transition-colors hover:border-blue-200 hover:bg-white dark:border-slate-800/80 dark:bg-slate-900/80 dark:hover:border-blue-900/60",
            compact && "rounded-xl px-2.5 py-2"
          )}
          aria-expanded={assistantCompanionOpen}
          aria-controls={compact ? 'module2-assistant-companion-compact' : 'module2-assistant-companion'}
        >
          <div className="min-w-0">
            <div className="text-[11px] font-semibold text-slate-700 dark:text-slate-200">
              文档摘要与辅助信息
            </div>
            <div className="mt-0.5 truncate text-[10px] text-slate-500 dark:text-slate-400">
              {badges.length > 0 ? badges.join(' · ') : '查看当前回答的辅助信息'}
            </div>
          </div>
          <ChevronRight
            size={14}
            className={cn(
              "shrink-0 text-slate-400 transition-transform dark:text-slate-500",
              assistantCompanionOpen && "rotate-90 text-blue-500 dark:text-blue-400"
            )}
          />
        </button>

        {assistantCompanionOpen && (
          <div
            id={compact ? 'module2-assistant-companion-compact' : 'module2-assistant-companion'}
            className={cn("mt-2.5 space-y-2.5", compact && "mt-2 space-y-2")}
          >
            {hasSummary && (
              <div className="rounded-[18px] border border-slate-200/70 bg-white/75 px-3.5 py-2.5 text-xs leading-relaxed text-slate-600 shadow-[inset_0_1px_0_rgba(255,255,255,0.68)] dark:border-slate-800/70 dark:bg-slate-950/35 dark:text-slate-300">
                <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-blue-600 dark:text-blue-400">
                  <Sparkles size={12} />
                  文档摘要
                </div>
                <div data-testid="module2-summary-text" className="whitespace-pre-wrap break-words font-medium text-slate-700 dark:text-slate-200">
                  {activeSummaryLoading ? (
                    <span className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
                      <Loader2 size={12} className="animate-spin" />
                      正在生成文档摘要...
                    </span>
                  ) : (
                    activeSummaryText
                  )}
                </div>
              </div>
            )}

            {assistantWarnings.length > 0 && (
              <div className="rounded-[16px] border border-amber-200 bg-amber-50/70 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em]">
                  <AlertCircle size={12} />
                  当前提示
                </div>
                <div className="leading-relaxed">{assistantWarnings.join('；')}</div>
              </div>
            )}

            {assistantCurrentLock && (
              <div>
                <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                  当前上下文
                </div>
                {renderAssistantLockBanner(compact)}
              </div>
            )}

            {assistantCompanionCitations.length > 0 && (
              <div>
                <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                  回答依据
                </div>
                {renderAssistantCitations(assistantCompanionCitations, compact)}
              </div>
            )}

            {assistantCompanionActionPreview && (
              <div>
                <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                  操作预览
                </div>
                {renderAssistantActionPreview(assistantCompanionActionPreview, compact)}
              </div>
            )}

            {assistantRuntimeEvents.length > 0 && (
              <div className="rounded-[16px] border border-slate-200/80 bg-white/75 px-3 py-2 text-[11px] text-slate-600 dark:border-slate-800/80 dark:bg-slate-900/75 dark:text-slate-300">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                  最近处理记录
                </div>
                <div className="space-y-1">
                  {assistantRuntimeEvents.slice(-4).map((event, index) => (
                    <div key={`${event.tool_name}-${event.status}-${index}`} className="flex items-start gap-2">
                      <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500/70" />
                      <span className="leading-relaxed">
                        {event.human_label || event.message || event.tool_name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
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
      status: 'streaming',
      payload: {},
    };
    setAssistantDialog((prev) => [...prev, userDialogMsg, pendingAssistantMsg]);
    setAssistantQueryLoading(true);
    setAssistantWarnings([]);
    resetAssistantCompanionState(true);
    setAssistantAnswer('');
    setAssistantInput('');

    const controller = new AbortController();
    assistantAbortRef.current = controller;
    const fileHash = activeAssistantSessionKey;
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
            document: activeDoc || undefined,
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
          const toolEvent: AssistantToolEvent = {
            tool_name: String(parsed.tool_name || '').trim(),
            status: String(parsed.status || '').trim(),
            message: String(parsed.message || '').trim(),
            detail: String(parsed.detail || '').trim(),
            human_label: humanizeAssistantToolEvent(parsed),
          };
          setAssistantRuntimeEvents((prev) => [...prev, toolEvent].slice(-8));
          return;
        }

        if (normalizedEvent === 'citation_bundle') {
          const citations = toAssistantCitations(parsed.citations);
          const nextLock = toAssistantObjectLock(parsed.current_object_lock);
          setAssistantCompanionCitations(citations);
          syncAssistantEvidence(citations, nextLock);
          return;
        }

        if (normalizedEvent === 'action_preview') {
          const preview = toAssistantActionPreview(parsed);
          setAssistantCompanionActionPreview(preview);
          if (preview) {
            setAssistantCompanionOpen(true);
          }
          return;
        }

        if (normalizedEvent === 'assistant_delta') {
          const deltaText = String(parsed.text || '');
          updateAssistantDialogMessage(streamMessageId, (current) => ({
            ...current,
            content: normalizeAssistantDisplayText(`${current.content || ''}${deltaText}`),
            status: 'streaming',
            payload: {
              ...(current.payload || {}),
              progress_label: '',
            },
          }));
          return;
        }

        if (normalizedEvent === 'assistant_done') {
          const citations = toAssistantCitations(parsed.citations);
          const actionPreview = toAssistantActionPreview(parsed.action_preview);
          const nextLock = toAssistantObjectLock(parsed.current_object_lock);
          const nextAnswer = normalizeAssistantDisplayText(parsed.answer || '') || '助手已完成处理。';
          const nextWarnings = filterAssistantWarnings(parsed.warnings);
          setAssistantAnswer(nextAnswer);
          setAssistantMessage(nextAnswer);
          setAssistantWarnings(nextWarnings);
          setAssistantCompanionCitations(citations);
          setAssistantCompanionActionPreview(actionPreview);
          if (actionPreview) {
            setAssistantCompanionOpen(true);
          }
          updateAssistantDialogMessage(streamMessageId, (current) => ({
            ...current,
            content: mergeAssistantFinalAnswer(String(current.content || ''), nextAnswer),
            messageType: 'assistant_text',
            status: 'done',
            payload: {
              route: parsed.route,
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

  const resetPaneWidth = (side: PaneResizeSide) => {
    setPaneLayout((prev) =>
      clampWorkbenchPaneLayout(
        {
          ...prev,
          leftWidth: side === 'left' ? LEFT_PANE_DEFAULT_WIDTH : prev.leftWidth,
          rightWidth: side === 'right' ? RIGHT_PANE_DEFAULT_WIDTH : prev.rightWidth,
        },
        workbenchViewportWidth,
        showLeftPanel,
      ),
    );
  };

  const startPaneResize = (side: PaneResizeSide, event: React.PointerEvent<HTMLButtonElement>) => {
    if (side === 'left' && !showLeftPanel) return;

    event.preventDefault();
    event.stopPropagation();

    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    setPaneResizeSide(side);
    paneResizeStartRef.current = {
      clientX: event.clientX,
      leftWidth: paneLayout.leftWidth,
      rightWidth: paneLayout.rightWidth,
      side,
    };

    const applyResize = () => {
      paneResizeFrameRef.current = null;
      if (!paneResizeStartRef.current || paneResizeLatestXRef.current == null) return;

      const start = paneResizeStartRef.current;
      const deltaX = paneResizeLatestXRef.current - start.clientX;
      const nextLayout = clampWorkbenchPaneLayout(
        {
          leftWidth: start.side === 'left' ? start.leftWidth + deltaX : start.leftWidth,
          rightWidth: start.side === 'right' ? start.rightWidth - deltaX : start.rightWidth,
        },
        workbenchViewportWidth,
        showLeftPanel,
      );

      setPaneLayout((prev) =>
        prev.leftWidth === nextLayout.leftWidth && prev.rightWidth === nextLayout.rightWidth ? prev : nextLayout,
      );
    };

    const scheduleResize = () => {
      if (paneResizeFrameRef.current != null) return;
      paneResizeFrameRef.current = window.requestAnimationFrame(applyResize);
    };

    const handleMove = (moveEvent: PointerEvent) => {
      if (!paneResizeStartRef.current) return;
      paneResizeLatestXRef.current = moveEvent.clientX;
      scheduleResize();
    };

    const handleUp = (upEvent: PointerEvent) => {
      paneResizeStartRef.current = null;
      paneResizeLatestXRef.current = null;
      setPaneResizeSide(null);
      if (paneResizeFrameRef.current != null) {
        window.cancelAnimationFrame(paneResizeFrameRef.current);
        paneResizeFrameRef.current = null;
      }
      if (target.hasPointerCapture(upEvent.pointerId)) {
        target.releasePointerCapture(upEvent.pointerId);
      }
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
      window.removeEventListener('pointercancel', handleUp);
    };

    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    window.addEventListener('pointercancel', handleUp);
  };

  const workbenchGridStyle = showLeftPanel
    ? {
        gridTemplateColumns: `${paneLayout.leftWidth}px ${PANE_DIVIDER_WIDTH}px minmax(0,1fr) ${PANE_DIVIDER_WIDTH}px ${paneLayout.rightWidth}px`,
      }
    : {
        gridTemplateColumns: `minmax(0,1fr) ${PANE_DIVIDER_WIDTH}px ${paneLayout.rightWidth}px`,
      };
  const pendingExtractionCount = selectedFiles.length;
  const showBatchExtractAction = pendingExtractionCount > 0;
  const extractionOverallPercent = clampProgressPercent(extractionJob?.progress?.progress_ratio || 0);
  const batchExtractLabel = isProcessing
    ? `正在提取（${extractionOverallPercent}%）`
    : pendingExtractionCount > 1
      ? `开始批量提取（${pendingExtractionCount}）`
      : '开始提取';
  const smartUnitTabTransition = prefersReducedMotion
    ? { duration: 0 }
    : {
        type: 'spring' as const,
        stiffness: 310,
        damping: 31,
        mass: 0.9,
      };
  const smartUnitPanelTransition = prefersReducedMotion
    ? { duration: 0 }
    : {
        duration: 0.34,
        ease: [0.22, 1, 0.36, 1] as const,
      };
  const useCompactWorkbenchChrome = workbenchViewportWidth >= 1500;
  const useDenseWorkbenchChrome = workbenchViewportWidth >= 1800;
  const smartUnitActivePanelState = { opacity: 1, x: 0, y: 0, scale: 1 };
  const smartUnitLeftHiddenPanelState = prefersReducedMotion
    ? { opacity: 0, x: 0, y: 0, scale: 1 }
    : { opacity: 0, x: -8, y: 1, scale: 0.997 };
  const smartUnitRightHiddenPanelState = prefersReducedMotion
    ? { opacity: 0, x: 0, y: 0, scale: 1 }
    : { opacity: 0, x: 8, y: 1, scale: 0.997 };
  const showTraceOverlay = false;
  const previewControlsDisabled = !hasPreviewContent;
  const previewFocusButtonTitle = '聚焦预览并隐藏文档列表';
  const restoreFolderButtonTitle = '展开文档列表并退出聚焦预览';
  const filePipelineStats = useMemo(() => {
    let completed = 0;
    let failed = 0;
    let processing = 0;
    let queued = 0;

    selectedFiles.forEach((file, index) => {
      const jobFile = pickExtractionJobFileState(extractionJob, file, index);
      const doc = documents[index];

      if (jobFile) {
        const status = String(jobFile.status || '').trim().toLowerCase();
        if (status === 'completed') {
          completed += 1;
          return;
        }
        if (status === 'failed') {
          failed += 1;
          return;
        }
        if (status === 'queued') {
          queued += 1;
          return;
        }
        processing += 1;
        return;
      }

      if (doc) {
        if ((doc.errors?.length ?? 0) > 0) {
          failed += 1;
        } else {
          completed += 1;
        }
        return;
      }

      queued += 1;
    });

    return {
      total: selectedFiles.length,
      completed,
      failed,
      processing,
      queued,
    };
  }, [documents, extractionJob, selectedFiles]);
  const activeIssueCount = (activeDoc?.soft_warnings?.length ?? 0) + (activeDoc?.errors?.length ?? 0);
  const previewStageModeLabel = activeRenderExt === 'pdf'
    ? 'PDF 证据视图'
    : activeRenderExt === 'xlsx'
      ? '表格工作表'
      : IMAGE_EXTENSIONS.has(activeRenderExt)
        ? '图像原稿'
        : ['txt', 'md'].includes(activeRenderExt)
          ? '文本视图'
          : activeRenderExt
            ? `${activeRenderExt.toUpperCase()} 预览`
            : '等待文档';
  const moduleStatusMeta = useMemo(() => {
    if (assistantQueryLoading) {
      return {
        label: '助手处理中',
        detail: '正在结合当前文档上下文组织回答',
        tone: 'blue' as const,
      };
    }
    if (traceLoading) {
      return {
        label: '定位同步中',
        detail: '正在更新原文证据与定位锚点',
        tone: 'blue' as const,
      };
    }
    if (activeSummaryLoading) {
      return {
        label: '摘要更新中',
        detail: '正在提炼当前文档的核心信息',
        tone: 'blue' as const,
      };
    }
    if (isProcessing) {
      return {
        label: '提取进行中',
        detail: extractionOverallPercent > 0 ? `整体进度 ${extractionOverallPercent}%` : '系统正在解析文档结构',
        tone: 'blue' as const,
      };
    }
    if (activeIssueCount > 0) {
      return {
        label: '待人工复核',
        detail: `${activeIssueCount} 条异常或软告警需要确认`,
        tone: 'amber' as const,
      };
    }
    if (documents.length > 0) {
      return {
        label: '分析就绪',
        detail: `${fieldItems.length} 个字段、${traceHits.length} 条原文定位已可联动查看`,
        tone: 'emerald' as const,
      };
    }
    if (selectedFiles.length > 0) {
      return {
        label: '等待启动',
        detail: `已载入 ${selectedFiles.length} 份文档，随时可以开始提取`,
        tone: 'slate' as const,
      };
    }
    return {
      label: '准备就绪',
      detail: '导入文档后即可开始结构化分析',
      tone: 'slate' as const,
    };
  }, [
    activeIssueCount,
    activeSummaryLoading,
    assistantQueryLoading,
    documents.length,
    extractionOverallPercent,
    fieldItems.length,
    isProcessing,
    selectedFiles.length,
    traceHits.length,
    traceLoading,
  ]);
  const moduleStatusToneClass = cn(
    'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset',
    moduleStatusMeta.tone === 'blue' && 'bg-blue-50/90 text-blue-700 ring-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30',
    moduleStatusMeta.tone === 'emerald' && 'bg-emerald-50/90 text-emerald-700 ring-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30',
    moduleStatusMeta.tone === 'amber' && 'bg-amber-50/90 text-amber-700 ring-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30',
    moduleStatusMeta.tone === 'slate' && 'bg-slate-100/90 text-slate-600 ring-slate-500/10 dark:bg-slate-800/90 dark:text-slate-300 dark:ring-slate-700'
  );
  const queueCardValue = filePipelineStats.total > 0 ? `${filePipelineStats.total} 份文档` : '空队列';
  const queueCardHint = filePipelineStats.total > 0
    ? `完成 ${filePipelineStats.completed} · 处理中 ${filePipelineStats.processing} · 失败 ${filePipelineStats.failed}`
    : '上传文档后自动进入当前批次';
  const currentDocCardValue = activeDoc || activeSourceFile ? activeDisplayName : '等待载入';
  const currentDocCardHint = activeDoc
    ? `${previewStageModeLabel} · ${activeDoc.cached ? '已缓存结果' : '实时预览'}`
    : previewStageModeLabel;
  const resultCardValue = fieldItems.length > 0 ? `${fieldItems.length} 个字段` : documents.length > 0 ? '等待字段生成' : '未开始';
  const hasImportedFiles = selectedFiles.length > 0 || documents.length > 0 || Boolean(activeSourceFile);
  const resultCardHint = traceHits.length > 0
    ? `定位 ${traceHits.length} 条 · 平均置信度 ${avgConfidence}%`
    : activeSummaryText
      ? '摘要已同步，可继续核验'
      : '等待抽取与定位结果';
  const focusCardValue = smartUnitTab === 'assistant' ? '助手协同' : '结果核验';
  const focusCardHint = activeIssueCount > 0
    ? `${activeIssueCount} 条提示待确认`
    : assistantQueryLoading
      ? '助手正在处理中'
      : activeSummaryLoading
        ? '摘要同步中'
        : infoMessage;
  const smartUnitTabs: Array<{ id: SmartUnitTabId; label: string; unread: boolean }> = [
    { id: 'results', label: '提取结果', unread: resultsTabUnread },
    { id: 'assistant', label: '智能助手', unread: assistantTabUnread },
  ];
  const assistantPanel = (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-transparent">
      <div className="border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,250,252,0.8))] px-3 py-2 dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.44),rgba(15,23,42,0.22))]">
        <div className="flex items-center justify-between gap-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-[10px] bg-white/88 text-blue-600 ring-1 ring-slate-200/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] dark:bg-slate-900/88 dark:text-blue-300 dark:ring-slate-700/80">
              <Sparkles size={13} className="text-blue-600 dark:text-blue-400" />
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-[11.5px] font-semibold tracking-[0.01em] text-slate-700 dark:text-slate-200">
                智能助手
              </h3>
              <p className="mt-0.5 text-[8.5px] leading-[1.35] text-slate-400 dark:text-slate-500">
                面向当前文档的提问、摘要与修正协同
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowAssistantHelp(true)}
            className="inline-flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-blue-600 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-blue-400"
            aria-label="查看助手功能说明"
          >
            <HelpCircle size={13} />
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div ref={assistantDialogRef} data-testid="module2-assistant-dialog" className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-3.5 py-3 custom-scrollbar">
          {/* Chat History */}
          {renderableAssistantDialog.map((msg) => renderAssistantDialogMessage(msg))}

          {/* Spacer for scrolling */}
          <div className="h-3" />
        </div>

        {renderAssistantCompanionPanel()}

        {/* Input Area */}
        <div className="border-t border-slate-100/50 bg-white/60 px-3 py-3 backdrop-blur-md dark:border-slate-800/50 dark:bg-slate-900/60">
          <div className="relative group">
            <textarea
              ref={assistantInputRef}
              data-testid="module2-assistant-input"
              value={assistantInput}
              onChange={(e) => setAssistantInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (!assistantQueryLoading) {
                    void runAssistantInstruction();
                  }
                }
              }}
              placeholder={activeDoc ? "输入需求，回车发送..." : "可以先问文档处理、抽取方案、表结构设计或 NL2SQL..."}
              className="max-h-24 min-h-[38px] w-full resize-none rounded-[18px] border-none bg-slate-100/80 px-3.5 py-2 pr-10 text-xs leading-relaxed text-slate-700 shadow-inner outline-none transition-all focus:bg-white focus:ring-2 focus:ring-blue-500/20 dark:bg-slate-800/80 dark:text-slate-200 dark:focus:bg-slate-900"
            />
            <button
              type="button"
              data-testid="module2-assistant-send"
              onClick={() => void runAssistantInstruction()}
              disabled={!assistantQueryLoading && !assistantInput.trim()}
              className={cn(
                'absolute bottom-1 right-1 inline-flex h-[26px] w-[26px] items-center justify-center rounded-full transition-all duration-200',
                !assistantQueryLoading && !assistantInput.trim()
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
    <div className="module2-workbench relative flex h-[100dvh] flex-col overflow-hidden bg-slate-100/92 p-0 text-foreground dark:bg-slate-950">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.16),_transparent_60%)] dark:bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.18),_transparent_60%)]" />
        <div className="absolute inset-y-0 right-0 w-1/3 bg-[radial-gradient(circle_at_center,_rgba(16,185,129,0.10),_transparent_65%)] dark:bg-[radial-gradient(circle_at_center,_rgba(16,185,129,0.12),_transparent_65%)]" />
        <div
          className="absolute inset-0 opacity-[0.08] dark:opacity-[0.06]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(15,23,42,0.14) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.14) 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.doc,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg,.bmp,.webp,.tif,.tiff"
        multiple
        className="hidden"
        data-testid="module2-file-input"
        onChange={onSelectFiles}
      />

      <motion.section
        data-testid="module2-top-bar"
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          'relative z-10 mb-0 shrink-0 overflow-hidden border-b border-slate-200/80 bg-white/90 shadow-none ring-0 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/88',
          useDenseWorkbenchChrome
            ? 'px-3 py-1'
            : useCompactWorkbenchChrome
              ? 'px-3 py-1.5'
              : 'px-3.5 py-1.5'
        )}
      >
        <div aria-hidden="true" className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/70 to-transparent dark:via-cyan-400/60" />

        <div className={cn(
          'flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5',
          useDenseWorkbenchChrome && 'gap-x-2 gap-y-1'
        )}>
          <div className="min-w-[210px] flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className={cn(
                'font-bold tracking-[0.02em] text-slate-900 dark:text-slate-50',
                useDenseWorkbenchChrome ? 'text-[14px]' : useCompactWorkbenchChrome ? 'text-[15px]' : 'text-[16px]'
              )}>
                非结构化文档分析
              </h2>
            </div>
            <p className={cn(
              'mt-0.5 text-slate-500 dark:text-slate-400',
              useDenseWorkbenchChrome ? 'text-[8px]' : 'text-[9px]'
            )}>
              支持文档抽取、原文定位与结果核验
            </p>
          </div>

          <div className={cn(
            'flex flex-wrap items-center justify-end gap-1.5',
            useDenseWorkbenchChrome && 'gap-[2px]'
          )}>
            {hasImportedFiles && (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md border border-slate-200/80 bg-white px-2.5 font-semibold text-slate-700 transition-colors duration-200 hover:border-blue-200 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-blue-700 dark:hover:text-blue-300',
                  useDenseWorkbenchChrome ? 'h-[24px] gap-[3px] px-1.5 text-[9px]' : 'h-[28px] text-[10px]'
                )}
              >
                <UploadCloud size={useDenseWorkbenchChrome ? 11 : 13} />
                追加文档
              </button>
            )}
            <button
              type="button"
              onClick={runExtraction}
              data-testid="module2-start-extract"
              disabled={!showBatchExtractAction || isProcessing}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 font-bold transition-colors duration-200',
                useDenseWorkbenchChrome ? 'h-[24px] gap-[3px] px-2 text-[9px]' : 'h-[28px] text-[10px]',
                showBatchExtractAction && !isProcessing
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'cursor-not-allowed bg-slate-200 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
              )}
            >
              {isProcessing ? <Loader2 size={useDenseWorkbenchChrome ? 11 : 13} className="animate-spin" /> : <PlayCircle size={useDenseWorkbenchChrome ? 11 : 13} strokeWidth={2.4} />}
              <span>{showBatchExtractAction ? batchExtractLabel : '等待文档'}</span>
            </button>
            <button
              type="button"
              onClick={exportResults}
              disabled={documents.length === 0}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md border px-2.5 font-semibold transition-colors duration-200',
                useDenseWorkbenchChrome ? 'h-[24px] gap-[3px] px-1.5 text-[9px]' : 'h-[28px] text-[10px]',
                documents.length > 0
                  ? 'border-slate-200/80 bg-white text-slate-700 hover:border-blue-200 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-blue-700 dark:hover:text-blue-300'
                  : 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-600'
              )}
            >
              <Download size={useDenseWorkbenchChrome ? 11 : 13} />
              导出结果
            </button>
            <button
              type="button"
              onClick={clearWorkbenchData}
              data-testid="module2-clear-data"
              disabled={!canClearWorkbenchData || isProcessing}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md border px-2.5 font-semibold transition-colors duration-200',
                useDenseWorkbenchChrome ? 'h-[24px] gap-[3px] px-1.5 text-[9px]' : 'h-[28px] text-[10px]',
                canClearWorkbenchData && !isProcessing
                  ? 'border-red-200 bg-white text-red-600 hover:bg-red-50 hover:border-red-300 dark:border-red-900/60 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-950/30'
                  : 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-600'
              )}
            >
              <Trash2 size={useDenseWorkbenchChrome ? 11 : 13} />
              清空数据
            </button>
          </div>
        </div>
      </motion.section>

      <div ref={workbenchViewportRef} className="relative z-10 min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
        <div
          className={cn(
            'relative grid h-full min-h-0 min-w-[1100px] overflow-hidden rounded-none border-0 bg-white/84 shadow-none ring-0 backdrop-blur-xl dark:bg-slate-900/90',
            !paneResizeSide && 'transition-[grid-template-columns] duration-300 ease-out'
          )}
          style={workbenchGridStyle}
        >
          <div aria-hidden="true" className="pointer-events-none absolute inset-0">
            <div className="absolute inset-x-0 top-0 h-24 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.1),_transparent_72%)] dark:bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.12),_transparent_72%)]" />
            <div className="absolute inset-0 opacity-[0.06] dark:opacity-[0.04]" style={{ backgroundImage: 'linear-gradient(rgba(15,23,42,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(15,23,42,0.1) 1px, transparent 1px)', backgroundSize: '28px 28px' }} />
          </div>
        {showLeftPanel && (
          <div
            id="module2-left-panel"
            data-testid="module2-left-panel"
            className="relative z-10 flex h-full min-h-0 flex-col"
          >
            <div 
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={cn(
                "relative flex flex-1 min-h-[300px] flex-col overflow-hidden border-r border-slate-200/80 bg-[linear-gradient(180deg,rgba(248,250,252,0.86),rgba(255,255,255,0.76))] transition-colors duration-300 dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(15,23,42,0.86))]",
                isUploaderDragOver 
                  ? "bg-blue-50/80 dark:bg-blue-950/20"
                  : ""
              )}
            >
              <div aria-hidden="true" className="absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/70 to-transparent dark:via-cyan-400/60" />
              <div className="border-b border-slate-200/70 bg-white/72 px-3.5 py-2.5 dark:border-slate-800 dark:bg-slate-900/72">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-700 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700">
                        <FolderOpen size={15} />
                      </span>
                      <div className="min-w-0">
                        <h3 className="truncate text-[15px] font-bold text-slate-800 dark:text-slate-100">
                          文档列表
                        </h3>
                        <p className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400">
                          当前批次文件与处理状态
                        </p>
                      </div>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full border border-slate-200/80 bg-slate-50/90 px-2.5 py-1 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300">
                    已导入 {selectedFiles.length || documents.length || 0} 份
                  </span>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50/55 p-0 custom-scrollbar dark:bg-slate-950/20">
                {selectedFiles.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3 border-y border-dashed border-slate-200/80 bg-white/35 py-8 text-center text-slate-400 dark:border-slate-800 dark:bg-slate-900/25">
                    <FolderOpen size={24} className="text-slate-300 dark:text-slate-600" />
                    <div>
                      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">暂无已导入文档</p>
                      <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">请在中央预览区导入文件</p>
                    </div>
                  </div>
                ) : (
                  <div className="divide-y divide-slate-200/70 dark:divide-slate-800/80">
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
                            "group relative flex cursor-pointer items-start gap-3 border-l-2 border-l-transparent bg-transparent px-4 py-3 transition-colors duration-200 hover:bg-white/55 dark:hover:bg-slate-900/35",
                            isActive && "border-l-blue-500 bg-blue-50/60 dark:bg-blue-950/20"
                          )}
                        >
                          <div className="mt-0.5 shrink-0">
                            <FileIcon size={24} className={iconColorClass} strokeWidth={1.5} />
                          </div>
                          
                          <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between gap-2">
                                  <p className={cn("truncate text-sm font-bold text-slate-700 dark:text-slate-200", isActive && "text-slate-900 dark:text-white")}>
                                      {file.name}
                                  </p>
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      removeFile(index);
                                    }}
                                    title={`移除 ${file.name}`}
                                    aria-label={`移除 ${file.name}`}
                                    className="rounded-xl p-1 text-slate-400 opacity-70 transition-all duration-200 hover:bg-red-50 hover:text-red-500 hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-300 dark:hover:bg-red-900/20 dark:focus-visible:ring-red-800"
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

              <div className="border-t border-slate-200/70 bg-white/72 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-800 dark:bg-slate-900/72 dark:text-slate-400">
                {queueCardHint}
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
                  {renderableAssistantDialog.map((msg) => renderAssistantDialogMessage(msg, true))}
                  
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
                          if (!assistantQueryLoading) {
                            void runAssistantInstruction();
                          }
                        }
                      }}
                      placeholder={activeDoc ? "输入需求，回车发送..." : "可以先问文档处理、抽取方案、表结构设计或 NL2SQL..."}
                      className="max-h-24 min-h-[40px] w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 pr-9 text-xs leading-relaxed text-slate-700 outline-none transition-colors focus:border-blue-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-blue-600"
                    />
                    <button
                      type="button"
                      data-testid="module2-assistant-send"
                      onClick={() => void runAssistantInstruction()}
                      disabled={!assistantQueryLoading && !assistantInput.trim()}
                      className={cn(
                        'absolute bottom-1.5 right-1.5 inline-flex h-7 w-7 items-center justify-center rounded-lg transition-colors',
                        !assistantQueryLoading && !assistantInput.trim()
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

      {showLeftPanel && (
        <button
          type="button"
          aria-label="调整文档列表宽度"
          aria-orientation="vertical"
          data-active={paneResizeSide === 'left'}
          onPointerDown={(event) => startPaneResize('left', event)}
          onDoubleClick={() => resetPaneWidth('left')}
          className="module2-pane-handle relative z-20 h-full"
        />
      )}

      {/* CENTER: Workbench Area */}
      <div className="relative z-10 flex h-full min-h-0 flex-col">
        {/* Main Canvas with Floating Toolbar */}
        <div className={cn(
          "relative flex min-h-0 flex-1 flex-col overflow-hidden border-r border-slate-200/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.72),rgba(248,250,252,0.7))] transition-colors duration-300 dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.82))]",
          activeFieldKey || activeTraceKey
            ? "bg-[linear-gradient(180deg,rgba(239,246,255,0.82),rgba(255,255,255,0.7))] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.92),rgba(15,23,42,0.86))]"
            : ""
        )}>
            {/* Dot Grid Background */}
            <div className="pointer-events-none absolute inset-0 opacity-[0.16] dark:opacity-[0.1]" 
                 style={{ backgroundImage: 'radial-gradient(circle, #cbd5e1 1.5px, transparent 1.5px)', backgroundSize: '24px 24px' }}>
            </div>
            <div aria-hidden="true" className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/70 to-transparent dark:via-cyan-400/60" />

            {/* Fixed Header Toolbar */}
            <div className={cn(
              'relative z-20 flex w-full flex-wrap items-center border-b border-slate-200/70 bg-white/70 px-2.5 dark:border-slate-800 dark:bg-slate-900/75',
              useDenseWorkbenchChrome ? 'gap-1.5 py-2 sm:px-2.5' : 'gap-2 py-2.5 sm:px-3'
            )}>
                <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
                     {showLeftPanel && (
                        <button
                          type="button"
                          onClick={() => setIsPreviewFocused(true)}
                          className={cn(
                            'group inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent text-blue-600 transition-all duration-200 active:scale-95 hover:border-slate-200 hover:bg-white hover:text-blue-700 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 dark:text-blue-400 dark:hover:border-slate-700 dark:hover:bg-slate-800',
                            useDenseWorkbenchChrome ? 'h-7 w-7' : 'h-8 w-8'
                          )}
                          title={previewFocusButtonTitle}
                          aria-label={previewFocusButtonTitle}
                          aria-pressed={false}
                          aria-expanded={showLeftPanel}
                          aria-controls="module2-left-panel"
                          data-testid="module2-preview-focus-toggle"
                        >
                          <span className="transition-transform duration-200 ease-out group-hover:scale-105">
                            <Maximize size={useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2.2} />
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
                          className={cn(
                            'ml-1 inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 font-bold text-slate-700 shadow-sm transition-all duration-200 hover:border-blue-200 hover:bg-blue-50/60 hover:text-blue-700 hover:shadow-md active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-blue-700 dark:hover:bg-slate-800 dark:hover:text-blue-300',
                            useDenseWorkbenchChrome ? 'h-7 text-[11px]' : 'h-8 text-xs'
                          )}
                          title={restoreFolderButtonTitle}
                          aria-label={restoreFolderButtonTitle}
                          aria-controls="module2-left-panel"
                          aria-expanded={false}
                          data-testid="module2-restore-left-panel"
                        >
                          <FolderOpen size={useDenseWorkbenchChrome ? 13 : 14} />
                          <span className="hidden sm:inline">文档列表</span>
                        </motion.button>
                      )}

                     {activeDoc || activeSourceFile ? (
                        <div className="min-w-0 flex-1">
                            <span className={cn(
                              'block truncate font-bold text-slate-900 dark:text-slate-100',
                              useDenseWorkbenchChrome ? 'text-[13px]' : 'text-sm'
                            )}>{activeDisplayName}</span>
                            <span className={cn(
                              'mt-0.5 flex min-w-0 items-center gap-1.5 font-bold text-slate-500',
                              useDenseWorkbenchChrome ? 'text-[9px]' : 'text-[10px]'
                            )}>
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
                           <span className={cn('truncate font-bold', useDenseWorkbenchChrome ? 'text-[13px]' : 'text-sm')}>文档预览</span>
                        </div>
                     )}
                </div>

                <div className={cn(
                  'ml-auto flex max-w-full flex-wrap items-center justify-end',
                  useDenseWorkbenchChrome ? 'gap-1.5 sm:gap-2' : 'gap-2 sm:gap-2.5'
                )}>
                  <div className="flex max-w-full flex-wrap items-center justify-end gap-1">
                    <button
                        onClick={handleZoomOut}
                        disabled={previewControlsDisabled}
                        className={cn(
                          useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="缩小"
                        aria-label="缩小预览"
                    >
                      <ZoomOut size={useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2}/>
                    </button>
                    <span className={cn(
                      'shrink-0 text-center font-bold font-mono text-slate-900 dark:text-slate-100',
                      useDenseWorkbenchChrome ? 'w-8 text-[11px]' : 'w-9 text-xs'
                    )}>{Math.round(scale * 100)}%</span>
                    <button
                        onClick={handleZoomIn}
                        disabled={previewControlsDisabled}
                        className={cn(
                          useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="放大"
                        aria-label="放大预览"
                    >
                      <ZoomIn size={useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2}/>
                    </button>
                    <button
                        onClick={handleRotate}
                        disabled={previewControlsDisabled}
                        className={cn(
                          useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors ml-0.5 active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors ml-0.5 active:scale-95 shrink-0',
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="旋转"
                        aria-label="旋转预览"
                    >
                      <RotateCw size={useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2}/>
                    </button>
                    <button
                        onClick={handleResetView}
                        disabled={previewControlsDisabled}
                        className={cn(
                          useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                          previewControlsDisabled
                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                            : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-blue-600"
                        )}
                        title="重置视图"
                        aria-label="重置预览视图"
                    >
                      <RefreshCcw size={useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2}/>
                    </button>

                    {activeRenderExt === 'pdf' && (
                        <>
                            <div className={cn(
                              'w-px shrink-0 bg-slate-200 dark:bg-slate-600',
                              useDenseWorkbenchChrome ? 'mx-1 h-4' : 'mx-1.5 h-5'
                            )} />
                            <div className="flex items-center gap-1 shrink-0">
                                <button
                                    onClick={handlePrevPdfPage}
                                    disabled={currentPdfPage <= 1}
                                    className={cn(
                                        useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                                        currentPdfPage > 1
                                            ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800 dark:text-slate-200"
                                            : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                    )}
                                    title="上一页"
                                >
                                    <ChevronRight size={useDenseWorkbenchChrome ? 14 : 16} className="rotate-180" />
                                </button>
                                <span className={cn(
                                  'shrink-0 text-center font-bold font-mono text-slate-900 dark:text-slate-100',
                                  useDenseWorkbenchChrome ? 'min-w-[46px] text-[11px]' : 'min-w-[52px] text-xs'
                                )}>
                                    {`${currentPdfPage} / ${inferredPdfPageCount}`}
                                </span>
                                <button
                                    onClick={handleNextPdfPage}
                                    disabled={currentPdfPage >= inferredPdfPageCount}
                                    className={cn(
                                        useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                                        currentPdfPage < inferredPdfPageCount
                                            ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800 dark:text-slate-200"
                                            : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                    )}
                                    title="下一页"
                                >
                                    <ChevronRight size={useDenseWorkbenchChrome ? 14 : 16} />
                                </button>
                            </div>
                        </>
                    )}
                  </div>

                  <div className={cn(
                    'flex flex-wrap items-center justify-end border-l border-slate-200/80 dark:border-slate-700/80',
                    useDenseWorkbenchChrome ? 'gap-1 pl-1.5' : 'gap-1.5 pl-2'
                  )}>
                    {showBatchExtractAction && (
                      <span className={cn(
                        'hidden rounded-full bg-blue-50/80 font-bold text-blue-600 ring-1 ring-blue-500/10 sm:inline-flex dark:bg-blue-900/20 dark:text-blue-300 dark:ring-blue-500/20',
                        useDenseWorkbenchChrome ? 'px-2 py-0.5 text-[9px]' : 'px-2.5 py-1 text-[10px]'
                      )}>
                        队列 {pendingExtractionCount} 份
                      </span>
                    )}
                    <span className={cn(
                      'rounded-full bg-slate-100/80 font-bold text-slate-600 ring-1 ring-slate-500/10 dark:bg-slate-800/80 dark:text-slate-300 dark:ring-slate-700',
                      useDenseWorkbenchChrome ? 'px-2 py-0.5 text-[9px]' : 'px-2.5 py-1 text-[10px]'
                    )}>
                      {previewStageModeLabel}
                    </span>
                    {activeDoc && (
                      <span className={cn(
                        'rounded-full bg-white/80 font-bold text-slate-600 ring-1 ring-slate-200/80 dark:bg-slate-900/80 dark:text-slate-300 dark:ring-slate-700',
                        useDenseWorkbenchChrome ? 'px-2 py-0.5 text-[9px]' : 'px-2.5 py-1 text-[10px]'
                      )}>
                        字段 {fieldItems.length}
                      </span>
                    )}
                    {traceHits.length > 0 && (
                      <span className={cn(
                        'rounded-full bg-emerald-50/80 font-bold text-emerald-700 ring-1 ring-emerald-500/10 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20',
                        useDenseWorkbenchChrome ? 'px-2 py-0.5 text-[9px]' : 'px-2.5 py-1 text-[10px]'
                      )}>
                        定位 {traceHits.length}
                      </span>
                    )}
                    {activeIssueCount > 0 && (
                      <span className={cn(
                        'rounded-full bg-amber-50/80 font-bold text-amber-700 ring-1 ring-amber-500/10 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20',
                        useDenseWorkbenchChrome ? 'px-2 py-0.5 text-[9px]' : 'px-2.5 py-1 text-[10px]'
                      )}>
                        提示 {activeIssueCount}
                      </span>
                    )}
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
                                const label = getTraceDisplayKind(hit) === 'table' ? '表格定位' : getTraceDisplayKind(hit) === 'image' ? '图片定位' : '原文定位';
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
            <div className="z-20 flex h-9 items-center justify-between border-t border-slate-200/70 bg-white/75 px-3 text-[10px] text-slate-500 sm:px-4 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400">
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

      <button
        type="button"
        aria-label="调整结果与助手宽度"
        aria-orientation="vertical"
        data-active={paneResizeSide === 'right'}
        onPointerDown={(event) => startPaneResize('right', event)}
        onDoubleClick={() => resetPaneWidth('right')}
        className="module2-pane-handle relative z-20 h-full"
      />

      {/* 右侧：结果面板 */}
      <div className="relative z-10 flex h-full min-h-0 w-full min-w-0 shrink-0 self-stretch flex-col">
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-[linear-gradient(180deg,rgba(248,250,252,0.9),rgba(255,255,255,0.82))] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.94),rgba(15,23,42,0.88))]">
          <div className={cn(
            'border-b border-slate-200/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.97),rgba(248,250,252,0.84))] px-3 pb-0.5 dark:border-slate-800/90 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.97),rgba(15,23,42,0.91))]',
            useDenseWorkbenchChrome ? 'pt-1' : 'pt-1.25'
          )}>
            <div className={cn(
              'flex items-center justify-between',
              useDenseWorkbenchChrome ? 'gap-1.5' : 'gap-2'
            )}>
              <div className="min-w-0 py-0.5">
                <div className={cn('flex items-center', useDenseWorkbenchChrome ? 'gap-1.5' : 'gap-2')}>
                  <span className={cn(
                    'flex items-center justify-center rounded-lg bg-slate-100/90 text-slate-700 ring-1 ring-slate-200/90 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] dark:bg-slate-800/95 dark:text-slate-100 dark:ring-slate-700',
                    useDenseWorkbenchChrome ? 'h-[22px] w-[22px] rounded-[10px]' : 'h-6 w-6'
                  )}>
                    <Bot size={12.5} />
                  </span>
                  <div className="min-w-0">
                    <h3 className={cn(
                      'truncate font-bold text-slate-900 dark:text-slate-50',
                      useDenseWorkbenchChrome ? 'text-[11.5px] leading-4' : 'text-[12px] leading-4'
                    )}>
                      结果与助手
                    </h3>
                    <p className={cn(
                      'mt-0.5 leading-[1.35] text-slate-500 dark:text-slate-400',
                      useDenseWorkbenchChrome ? 'text-[8px]' : 'text-[8.5px]'
                    )}>
                      字段结果、原文定位与智能协同
                    </p>
                  </div>
                </div>
              </div>
              <div className="relative isolate flex shrink-0 items-center self-center">
                <div
                  className={cn(
                    'relative flex items-center gap-0 rounded-[9px] border border-slate-200/80 bg-slate-100/82 p-[1.5px] shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] dark:border-slate-700/80 dark:bg-slate-800/80 dark:shadow-none'
                  )}
                  role="tablist"
                  aria-label="智能处理单元视图切换"
                >
                  {smartUnitTabs.map((tab) => {
                    const isActive = smartUnitTab === tab.id;
                    return (
                      <div key={tab.id} className="relative">
                        {isActive && (
                          <motion.div
                            layoutId="smartUnitTabBlob"
                            className={cn(
                              'pointer-events-none absolute inset-0 rounded-[6px] border border-slate-200/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.99),rgba(255,255,255,0.965))] shadow-[0_2px_8px_rgba(148,163,184,0.1),inset_0_1px_0_rgba(255,255,255,0.82)] dark:border-slate-700/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.99),rgba(15,23,42,0.96))] dark:shadow-[0_2px_10px_rgba(2,6,23,0.18)]'
                            )}
                            transition={smartUnitTabTransition}
                          />
                        )}
                        <button
                          type="button"
                          role="tab"
                          aria-selected={isActive}
                          onClick={() => setSmartUnitTab(tab.id)}
                          className={cn(
                            'relative z-10 inline-flex items-center justify-center font-semibold tracking-[0.01em] whitespace-nowrap outline-none transition-[color,transform] duration-200 ease-out focus-visible:ring-2 focus-visible:ring-blue-500/25',
                            useDenseWorkbenchChrome ? 'h-[21px] min-w-[66px] px-1.5 text-[8.75px]' : 'h-[24px] min-w-[72px] px-2.5 text-[9.5px]',
                            isActive
                              ? 'text-slate-900 dark:text-slate-50'
                              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                          )}
                        >
                          <span className={cn('flex items-center', useDenseWorkbenchChrome ? 'gap-0.5' : 'gap-1')}>
                            {tab.label}
                            {tab.unread && (
                              <span
                                className={cn(
                                  'h-1.5 w-1.5 rounded-full ring-1',
                                  isActive
                                    ? 'bg-blue-500 ring-blue-100 dark:bg-blue-400 dark:ring-blue-950'
                                    : 'bg-slate-400 ring-slate-200 dark:bg-slate-500 dark:ring-slate-800'
                                )}
                                aria-hidden="true"
                              />
                            )}
                          </span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="relative flex-1 min-h-0 overflow-hidden bg-transparent">
              <motion.section
                initial={false}
                animate={
                  smartUnitTab === 'results'
                    ? smartUnitActivePanelState
                    : smartUnitLeftHiddenPanelState
                }
                transition={smartUnitPanelTransition}
                className={cn(
                  'absolute inset-0 min-h-0 p-0 will-change-transform',
                  smartUnitTab === 'results' ? 'z-20 pointer-events-auto' : 'z-10 pointer-events-none'
                )}
                aria-label="抽取结果视图"
                aria-hidden={smartUnitTab !== 'results'}
              >
                <div className="flex h-full min-h-0 flex-col overflow-hidden bg-transparent">
          <div className="border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.93),rgba(248,250,252,0.78))] px-3 py-2 dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.44),rgba(15,23,42,0.22))]">
            <div className="flex items-start justify-between gap-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="flex h-[22px] w-[22px] items-center justify-center rounded-[10px] bg-white/88 text-slate-500 ring-1 ring-slate-200/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] dark:bg-slate-900/88 dark:text-slate-300 dark:ring-slate-700/80">
                    <ScanLine size={13} className="text-slate-400 dark:text-slate-500" />
                  </span>
                  <div className="min-w-0">
                    <h3 className="text-[11.5px] font-semibold tracking-[0.01em] text-slate-700 dark:text-slate-200">
                      抽取结果
                    </h3>
                    <p className="mt-0.5 text-[8.5px] leading-[1.35] text-slate-400 dark:text-slate-500">
                      {activeDoc ? '字段结果与结构化摘要' : '完成抽取后在此查看结构化字段'}
                    </p>
                  </div>
                </div>
              </div>
              <span className="inline-flex h-[22px] shrink-0 items-center rounded-full border border-slate-200/80 bg-white/90 px-2.5 text-[10px] font-semibold text-slate-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] dark:border-slate-700/80 dark:bg-slate-900/88 dark:text-slate-300">
                {resultSectionCountText}
              </span>
            </div>
            {activeDoc && (
              <div className="mt-2 rounded-[14px] border border-slate-200/80 bg-white/74 px-2.5 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] dark:border-slate-800/80 dark:bg-slate-950/20 dark:shadow-none">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[10px] font-medium text-slate-400 dark:text-slate-500">
                      当前文档
                    </p>
                    <p className="mt-1 truncate text-xs font-semibold text-slate-800 dark:text-slate-100">
                      {activeDisplayName}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={moduleStatusToneClass}>
                      <span className={cn(
                        'h-1.5 w-1.5 rounded-full',
                        moduleStatusMeta.tone === 'blue' && 'bg-blue-500',
                        moduleStatusMeta.tone === 'emerald' && 'bg-emerald-500',
                        moduleStatusMeta.tone === 'amber' && 'bg-amber-500',
                        moduleStatusMeta.tone === 'slate' && 'bg-slate-400'
                      )} />
                      {moduleStatusMeta.label}
                    </span>
                    {fieldItems.length > 0 && (
                      <span className="rounded-full bg-slate-100/70 px-2.5 py-1 text-[10px] font-semibold text-slate-600 dark:bg-slate-800/70 dark:text-slate-300">
                        字段 {fieldItems.length}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )}
            {fieldItems.length > 0 && (
              <div className="mt-2 grid grid-cols-2 gap-1.5 text-[10px]">
                <span className="flex items-center justify-center rounded-lg bg-emerald-50/65 px-2 py-1.5 font-semibold text-emerald-700 ring-1 ring-emerald-500/10 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20">
                  平均置信度 {avgConfidence}%
                </span>
                <span className="flex items-center justify-center rounded-lg bg-blue-50/65 px-2 py-1.5 font-semibold text-blue-700 ring-1 ring-blue-500/10 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20">
                  表格 {tableCount} / 图片 {figureCount}
                </span>
              </div>
            )}
            {activeDoc && fieldItems.length > 0 && (
              <div className="mt-2 flex items-center gap-2">
                <div className="relative flex-1 group">
                  <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors group-focus-within:text-blue-500" />
                  <input
                    type="text"
                    value={resultSearchQuery}
                    onChange={(e) => setResultSearchQuery(e.target.value)}
                    className="h-8 w-full rounded-full border-none bg-white/80 pl-9 pr-8 text-xs text-slate-700 placeholder:text-slate-400 ring-1 ring-slate-200/70 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500/20 dark:bg-slate-900/75 dark:text-slate-200 dark:ring-slate-700/70 dark:focus:bg-slate-900"
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
                    'inline-flex h-7 shrink-0 items-center gap-1 rounded-xl border px-2 text-[10.5px] transition-colors',
                    canCopyFilteredResults
                      ? 'border-slate-200 bg-white/80 text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-slate-700 dark:bg-slate-900/75 dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300'
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

          <div data-testid="module2-trace-panel" className="flex min-h-0 max-h-[35%] flex-col overflow-hidden border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(248,250,252,0.94),rgba(241,245,249,0.72))] px-3 py-2 dark:border-slate-800/80 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.3),rgba(15,23,42,0.14))]">
            <div className="flex items-start justify-between gap-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="flex h-[22px] w-[22px] items-center justify-center rounded-[10px] bg-white/88 text-slate-500 ring-1 ring-slate-200/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] dark:bg-slate-900/88 dark:text-slate-300 dark:ring-slate-700/80">
                    <LocateFixed size={13} className={cn('text-slate-400', traceHits.length > 0 && 'text-blue-500 dark:text-blue-400')} />
                  </span>
                  <div className="min-w-0">
                    <h3 className="text-[11.5px] font-semibold tracking-[0.01em] text-slate-700 dark:text-slate-200">
                      原文定位
                    </h3>
                    <p className="mt-0.5 text-[8.5px] leading-[1.35] text-slate-400 dark:text-slate-500">
                      {traceSectionHint}
                    </p>
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-start gap-2 self-start pt-0.5">
                {traceLoading && (
                  <span className="inline-flex h-[22px] items-center gap-1 rounded-full border border-blue-200/80 bg-blue-50/80 px-2.5 text-[10px] font-semibold text-blue-700 dark:border-blue-700/70 dark:bg-blue-900/20 dark:text-blue-300">
                    <Loader2 size={10} className="animate-spin" />
                    同步中
                  </span>
                )}
                <span className="inline-flex h-[22px] items-center rounded-full border border-slate-200/80 bg-white/85 px-2.5 text-[10px] font-semibold text-slate-500 dark:border-slate-700/80 dark:bg-slate-900/85 dark:text-slate-300">
                  {traceSectionCountText}
                </span>
              </div>
            </div>

            {hasTraceTypeStats && (
              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                {traceTypeStats.field > 0 && <span className="inline-flex items-center rounded-full bg-blue-50/80 px-2 py-0.5 font-medium text-blue-600 ring-1 ring-inset ring-blue-500/10 dark:bg-blue-900/20 dark:text-blue-300">字段 {traceTypeStats.field}</span>}
                {traceTypeStats.table > 0 && <span className="inline-flex items-center rounded-full bg-emerald-50/80 px-2 py-0.5 font-medium text-emerald-600 ring-1 ring-inset ring-emerald-500/10 dark:bg-emerald-900/20 dark:text-emerald-300">表格 {traceTypeStats.table}</span>}
                {traceTypeStats.image > 0 && <span className="inline-flex items-center rounded-full bg-amber-50/80 px-2 py-0.5 font-medium text-amber-600 ring-1 ring-inset ring-amber-500/10 dark:bg-amber-900/20 dark:text-amber-300">图片 {traceTypeStats.image}</span>}
                {traceTypeStats.other > 0 && <span className="inline-flex items-center rounded-full bg-slate-100/80 px-2 py-0.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-500/10 dark:bg-slate-700 dark:text-slate-300">其他 {traceTypeStats.other}</span>}
              </div>
            )}

            {traceError && (
              <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[10px] text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
                {traceError}
              </p>
            )}

            {traceHits.length > 0 ? (
              <div className="mt-2 min-h-0 flex-1 overflow-y-auto rounded-[14px] border border-slate-200/70 bg-white/70 pb-0 custom-scrollbar dark:border-slate-800/70 dark:bg-slate-950/18">
                {traceGroups.map((group) => (
                  <div key={`trace-group-${group.key}`} data-testid={`module2-trace-group-${group.key}`} className="mb-3 px-2 pt-2 last:mb-0">
                    <div data-testid="module2-trace-group-label" className="sticky top-0 z-10 mb-1.5 rounded-lg bg-white/95 px-2 py-1 text-[10px] font-bold text-slate-400 backdrop-blur dark:bg-slate-950/95 dark:text-slate-500">
                      {group.label}
                    </div>
                    <div className="space-y-0">
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
                  const tableDataframe = toTraceDataframePayload(locator.dataframe ?? tablePreview);
                  const tableHeaders = tableDataframe.headers;
                  const tableRows = tableDataframe.rows;
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
                  const figureDataframe = toTraceDataframePayload(locator.dataframe);
                  const figureDfHeaders = figureDataframe.headers;
                  const figureDfRows = figureDataframe.rows;
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
                  const canExpandDataframe = displayKind === 'table'
                    ? tableRows.length > 0
                    : objectType === 'figure' && figureDfRows.length > 0;
                  const isTraceExpanded = canExpandDataframe && expandedTraceCardKey === traceKey;
                  const tableHeaderSummary = tableHeaders.slice(0, 4);
                  const figureSummaryBullets = (figureKeyPoints.length > 0 ? figureKeyPoints : figureTextBlocks).slice(0, 3);
                  const artifactSourceLabel = toTraceSourceLabel(locator.artifact_source);
                  const dataframeSourceLabel = toTraceSourceLabel(locator.dataframe_source);
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
                        "group relative w-full border-l-2 border-b border-slate-200/70 border-l-transparent bg-transparent px-3 py-2.5 text-left transition-colors duration-200 dark:border-slate-800/80 hover:bg-white/60 dark:hover:bg-slate-800/35",
                        isActiveTrace && "border-l-blue-500 bg-blue-50/60 dark:bg-blue-950/20",
                        isTraceExpanded && "bg-white/80 dark:bg-slate-900/30"
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
                                <span className="opacity-50">页</span>
                                <span>{Math.round(page)}</span>
                              </span>
                            )}
                        </div>
                        <span className="text-[10px] font-medium text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">{Math.round((Number(hit.confidence || 0) || 0) * 100)}%</span>
                      </div>
                      <p className="line-clamp-2 text-[11px] leading-relaxed text-slate-700 dark:text-slate-200">
                        {snippet || objectId || "定位片段"}
                      </p>
                      {locatorSummary && (
                        <div className="mt-2 flex items-center gap-1.5">
                          <div className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600"></div>
                          <p className="truncate text-[10px] text-slate-500 dark:text-slate-400">
                            {locatorSummary}
                          </p>
                        </div>
                      )}

                      {displayKind === 'table' && tableHeaderSummary.length > 0 && (
                        <div className="mt-2 rounded-md border border-emerald-100/80 bg-emerald-50/55 px-2 py-1.5 dark:border-emerald-900/40 dark:bg-emerald-950/20">
                          <div className="mb-1 text-[10px] font-medium text-emerald-700/80 dark:text-emerald-300/90">
                            摘要
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {tableHeaderSummary.map((header) => (
                              <span
                                key={`${traceKey}-header-${header}`}
                                className="rounded-md bg-white/80 px-1.5 py-0.5 text-[10px] text-emerald-700 ring-1 ring-inset ring-emerald-500/10 dark:bg-emerald-900/20 dark:text-emerald-300"
                              >
                                {header}
                              </span>
                            ))}
                          </div>
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

                      {objectType === 'figure' && figureSummaryBullets.length > 0 && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800">
                          <div className="mb-1 text-[10px] font-medium text-slate-500 dark:text-slate-400">
                            摘要
                          </div>
                          <ul className="space-y-1 text-[10px] leading-relaxed text-slate-600 dark:text-slate-300">
                            {figureSummaryBullets.map((item, itemIdx) => (
                              <li key={`${traceKey}-summary-${itemIdx}`} className="flex items-start gap-1.5">
                                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400/90 dark:bg-amber-300/80"></span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {isTraceExpanded && (artifactSourceLabel || dataframeSourceLabel) && (
                        <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                          {artifactSourceLabel && (
                            <span className="inline-flex items-center rounded-full bg-slate-100/90 px-2 py-0.5 text-slate-600 ring-1 ring-inset ring-slate-400/10 dark:bg-slate-800 dark:text-slate-300">
                              {`截图：${artifactSourceLabel}`}
                            </span>
                          )}
                          {dataframeSourceLabel && (
                            <span className="inline-flex items-center rounded-full bg-blue-50/80 px-2 py-0.5 text-blue-700 ring-1 ring-inset ring-blue-500/10 dark:bg-blue-900/20 dark:text-blue-300">
                              {`数据：${dataframeSourceLabel}`}
                            </span>
                          )}
                        </div>
                      )}

                      {displayKind === 'table' && isTraceExpanded && tableRows.length > 0 && (
                        <div data-testid="module2-trace-table-preview" className="mt-2 rounded-md border border-slate-200 dark:border-slate-700">
                          <div className="border-b border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
                            完整表格
                          </div>
                          <div className="max-h-72 overflow-auto">
                            <table className="min-w-full text-[11px] text-slate-700 dark:text-slate-200">
                              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
                                <tr>
                                  {(tableHeaders.length > 0 ? tableHeaders : tableRows[0]).map((header, hIdx) => (
                                    <th key={`tbl-h-${idx}-${hIdx}`} className="border-b border-r border-slate-200 px-1.5 py-1 text-left font-bold dark:border-slate-700">
                                      {header || `列${hIdx + 1}`}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {tableRows.map((row, rIdx) => (
                                  <tr key={`tbl-r-${idx}-${rIdx}`} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-900 dark:even:bg-slate-800/50">
                                    {(tableHeaders.length > 0 ? tableHeaders : row).map((_, cIdx) => (
                                      <td key={`tbl-c-${idx}-${rIdx}-${cIdx}`} className="max-w-[220px] border-b border-r border-slate-100 px-1.5 py-1 align-top break-words dark:border-slate-800">
                                        {String(row[cIdx] ?? "").trim() || "—"}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {objectType === 'figure' && isTraceExpanded && figureDfRows.length > 0 && (
                        <div data-testid="module2-trace-figure-dataframe" className="mt-2 rounded-md border border-slate-200 dark:border-slate-700">
                          <div className="border-b border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
                            完整图表数据
                          </div>
                          <div className="max-h-72 overflow-auto">
                            <table className="min-w-full text-[10px] text-slate-700 dark:text-slate-200">
                              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
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
                                      <td key={`fig-df-c-${idx}-${rIdx}-${cIdx}`} className="max-w-[180px] border-b border-r border-slate-100 px-1.5 py-1 align-top break-words dark:border-slate-800">
                                        {String(row[cIdx] ?? "").trim() || "—"}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {objectType === 'figure' && isTraceExpanded && (figureTopologyNodes > 0 || figureTopologyEdges > 0) && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {`拓扑节点 ${figureTopologyNodes} · 拓扑连边 ${figureTopologyEdges}`}
                        </div>
                      )}

                      {objectType === 'figure' && isTraceExpanded && figureTextBlocks.length > 0 && (
                        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          {figureTextBlocks.join("；")}
                        </div>
                      )}

                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {canExpandDataframe && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setActiveTraceKey(traceKey);
                              setExpandedTraceCardKey((current) => (current === traceKey ? '' : traceKey));
                            }}
                            className={cn(
                              "inline-flex items-center gap-1 rounded-md border px-1.5 py-1 text-[10px] transition-colors",
                              isTraceExpanded
                                ? "border-emerald-300 bg-emerald-50/80 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300"
                                : "border-slate-200 text-slate-600 hover:border-emerald-300 hover:text-emerald-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-emerald-700 dark:hover:text-emerald-300"
                            )}
                          >
                            <ChevronRight
                              size={11}
                              className={cn("transition-transform duration-200", isTraceExpanded && "rotate-90")}
                            />
                            {isTraceExpanded ? '收起完整表' : '展开完整表'}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                              void writeClipboard(snippet || objectId || "", "已复制定位片段。");
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
              <div className="mt-2 rounded-[14px] border border-dashed border-slate-200/80 bg-white/50 px-3 py-2.5 dark:border-slate-800/80 dark:bg-slate-950/16">
                <p className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                  {activeDoc ? '暂无相关定位信息' : '尚未生成定位结果'}
                </p>
                <p className="mt-1 text-[10px] text-slate-400 dark:text-slate-500">
                  {traceSectionHint}
                </p>
              </div>
            )}
          </div>

          <div className="flex-1 min-h-0 space-y-0 overflow-y-auto custom-scrollbar bg-transparent px-3.5 pb-2.5">
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
                  "group relative cursor-pointer border-l-2 border-b border-slate-200/70 border-l-transparent px-3 py-3 transition-colors duration-200 dark:border-slate-800/80",
                  activeFieldKey === item.key
                    ? "border-l-blue-500 bg-blue-50/55 dark:bg-blue-950/20"
                    : "hover:bg-white/60 dark:hover:bg-slate-800/35"
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
                        页 {item.pageNumber}
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
              </motion.section>
              <motion.section
                initial={false}
                animate={
                  smartUnitTab === 'assistant'
                    ? smartUnitActivePanelState
                    : smartUnitRightHiddenPanelState
                }
                transition={smartUnitPanelTransition}
                className={cn(
                  'absolute inset-0 min-h-0 p-0 will-change-transform',
                  smartUnitTab === 'assistant' ? 'z-20 pointer-events-auto' : 'z-10 pointer-events-none'
                )}
                aria-label="任务助手视图"
                aria-hidden={smartUnitTab !== 'assistant'}
              >
                {assistantPanel}
              </motion.section>
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
                  <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">多模态原文定位</h4>
                  <p>点击提取结果中的字段，系统会自动定位到文档原文位置。支持文字、表格、印章及图片的精准定位。</p>
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

