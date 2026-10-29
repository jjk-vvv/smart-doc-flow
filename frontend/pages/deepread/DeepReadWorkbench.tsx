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
  Upload,
  File,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize,
  X,
  Search,
  LocateFixed,
  Bot,
  Sparkles,
  HelpCircle,
  FolderOpen,
  Layout,
  FileSpreadsheet,
  FileImage,
  Plus,
  ArrowUp,
  BarChart3,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import module2Svg from '../../assets/deepread-workbench.svg';
import iconWord from '../../assets/WORD.png';
import iconPdf from '../../assets/pdf.png';
import iconXlsx from '../../assets/xlsx.png';
import iconTxt from '../../assets/txt.png';
import iconDocumentQueue from '../../assets/文档.png';
import iconErnieBot from '../../assets/文心智能体-copy.png';
import iconAssistant from '../../assets/智能助手.png';
import {
  readExtractionDocuments,
  clearExtractionDocuments,
  writeExtractionDocuments,
  countExtractionDocumentFields,
  filterAutoRestorableExtractionDocuments,
  getExtractionDocumentQualityStatus,
  type ExtractionDocument,
  type ExtractionEntity,
  type TraceHit,
  isRetryableExtractionWarning,
  isStaleRetryableExtractionDocument,
} from '../../shared/state/extractionDocuments';
import {
  clearWorkbenchSession,
  readWorkbenchSession,
  writeWorkbenchSession,
  type PersistedExtractionJob,
  type PersistedExtractionJobFile,
  type PersistedWorkbenchFile,
  type WorkbenchSessionSnapshot,
} from '../../shared/state/workbenchSession';
import { consumeModule2DraftFromHomeWorkbench } from '../../shared/state/homeWorkbench';
import { getCurrentUser } from '../../shared/api/auth';
import { fetchModule4GraphFileDetail, fetchModule4JobStatus } from '../../shared/api/knowledgeGraph';
import { LuckysheetPreview, clearLuckysheetPreviewCache } from '../../components/LuckysheetPreview';
import { PdfJsViewer, type PdfViewMode } from '../../components/PdfJsViewer';
import { AssistantActionPreviewCard } from './assistant/AssistantActionPreviewCard';
import { AssistantCitationList } from './assistant/AssistantCitationList';
import { AssistantComposerStatus } from './assistant/AssistantComposerStatus';
import { AssistantCompanionPanel } from './assistant/AssistantCompanionPanel';
import { XlsxTraceChart, type XlsxTraceChartSpec } from '../../components/deepread/XlsxTraceChart';
import { buildAssistantExtraContext } from './assistant/contextBuilder';
import { isRenderableAssistantDialogMessage } from './assistant/helpers';
import { AssistantLockBanner } from './assistant/AssistantLockBanner';
import { AssistantMessageBubble } from './assistant/AssistantMessageBubble';
import {
  GENERIC_ASSISTANT_SESSION_KEY,
  persistAssistantSessionForFile,
  readAssistantSessionMap,
} from './assistant/sessionStore';
import type {
  AssistantActionPreview,
  AssistantCitation,
  AssistantDialogMessage,
  AssistantObjectLock,
  AssistantToolEvent,
} from './assistant/types';
import { useAssistantStream } from './assistant/useAssistantStream';
import { DeepReadWelcomeScreen } from './DeepReadWelcomeScreen';

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
const PANE_DIVIDER_WIDTH = 1;
const MODULE2_LEFT_DRAWER_BREAKPOINT = 1280;
const MODULE2_ASSISTANT_PROTECT_BREAKPOINT = 1366;
const MODULE2_CENTER_SAFE_NARROW_BREAKPOINT = 980;
const CENTER_PANE_NARROW_SAFE_WIDTH = 280;
const TEXT_PREVIEW_LEFT_PANE_WIDE_WIDTH = 208;
const TEXT_PREVIEW_LEFT_PANE_COMPACT_WIDTH = 200;
const TEXT_PREVIEW_RIGHT_PANE_WIDE_WIDTH = 288;
const TEXT_PREVIEW_RIGHT_PANE_COMPACT_WIDTH = 272;

type WorkbenchPaneLayout = {
    leftWidth: number;
    rightWidth: number;
};

type PaneLayoutStage = 'default' | 'text';

type PaneResizeSide = 'left' | 'right';
type SmartUnitTabId = 'results' | 'assistant';

const clampNumber = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const resolveCenterPaneSafeWidth = (containerWidth: number): number => (
    containerWidth > 0 && containerWidth <= MODULE2_CENTER_SAFE_NARROW_BREAKPOINT
        ? CENTER_PANE_NARROW_SAFE_WIDTH
        : CENTER_PANE_SAFE_WIDTH
);

const resolveRightPaneMinWidth = (containerWidth: number): number => (
    containerWidth > 0 && containerWidth <= MODULE2_ASSISTANT_PROTECT_BREAKPOINT
        ? RIGHT_PANE_DEFAULT_WIDTH
        : RIGHT_PANE_MIN_WIDTH
);

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

const getTextPreviewWorkbenchPaneLayout = (viewportWidth: number): WorkbenchPaneLayout => {
    if (viewportWidth >= 1600) {
        return {
            leftWidth: TEXT_PREVIEW_LEFT_PANE_WIDE_WIDTH,
            rightWidth: TEXT_PREVIEW_RIGHT_PANE_WIDE_WIDTH,
        };
    }

    return {
        leftWidth: TEXT_PREVIEW_LEFT_PANE_COMPACT_WIDTH,
        rightWidth: TEXT_PREVIEW_RIGHT_PANE_COMPACT_WIDTH,
    };
};

const resolveWorkbenchPaneLayoutDefaults = (
    viewportWidth: number,
    stage: PaneLayoutStage,
): WorkbenchPaneLayout => (
    stage === 'text'
        ? getTextPreviewWorkbenchPaneLayout(viewportWidth)
        : getDefaultWorkbenchPaneLayout(viewportWidth)
);

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
    const effectiveCenterSafeWidth = resolveCenterPaneSafeWidth(containerWidth);
    const effectiveRightMinWidth = resolveRightPaneMinWidth(containerWidth);
    const nextLeftWidth = sanitizePaneWidth(layout.leftWidth, LEFT_PANE_DEFAULT_WIDTH, LEFT_PANE_MIN_WIDTH, LEFT_PANE_MAX_WIDTH);
    const nextRightWidth = sanitizePaneWidth(layout.rightWidth, RIGHT_PANE_DEFAULT_WIDTH, effectiveRightMinWidth, RIGHT_PANE_MAX_WIDTH);

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
            Math.max(effectiveRightMinWidth, containerWidth - resolvedLeftWidth - dividerWidth - effectiveCenterSafeWidth),
        );
        resolvedRightWidth = clampNumber(resolvedRightWidth, effectiveRightMinWidth, maxRight);

        const maxLeft = Math.min(
            LEFT_PANE_MAX_WIDTH,
            Math.max(LEFT_PANE_MIN_WIDTH, containerWidth - resolvedRightWidth - dividerWidth - effectiveCenterSafeWidth),
        );
        resolvedLeftWidth = clampNumber(resolvedLeftWidth, LEFT_PANE_MIN_WIDTH, maxLeft);

        const refinedMaxRight = Math.min(
            RIGHT_PANE_MAX_WIDTH,
            Math.max(effectiveRightMinWidth, containerWidth - resolvedLeftWidth - dividerWidth - effectiveCenterSafeWidth),
        );
        resolvedRightWidth = clampNumber(resolvedRightWidth, effectiveRightMinWidth, refinedMaxRight);
    } else {
        const maxRight = Math.min(
            RIGHT_PANE_MAX_WIDTH,
            Math.max(effectiveRightMinWidth, containerWidth - dividerWidth - effectiveCenterSafeWidth),
        );
        resolvedRightWidth = clampNumber(resolvedRightWidth, effectiveRightMinWidth, maxRight);
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
        <div className="absolute inset-0 overflow-hidden bg-slate-50/70 dark:bg-transparent">
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
                            className="overflow-hidden rounded-[18px] border border-slate-100/50 bg-white shadow-[0_12px_36px_rgba(15,23,42,0.08)] dark:border-white/[0.05] dark:bg-white/[0.02] dark:shadow-[0_12px_36px_rgba(0,0,0,0.5)]"
                        >
                            <canvas
                                ref={(node) => {
                                    pageCanvasRefs.current[pageNumber - 1] = node;
                                }}
                                className="mx-auto block h-auto max-w-full bg-white dark:bg-transparent"
                            />
                        </div>
                    ))}
                </div>
            </div>
            {loading && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/30 dark:bg-black/20 dark:backdrop-blur-sm">
                    <div className="inline-flex items-center gap-2 rounded-lg border border-slate-100/80 bg-white/90 px-3 py-1.5 text-xs text-slate-600 shadow-soft-sm dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300 dark:backdrop-blur-md">
                        <Loader2 size={14} className="animate-spin" />
                        正在加载文档预览...
                    </div>
                </div>
            )}
            {error && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-white/80 p-4 text-center dark:bg-black/40 dark:backdrop-blur-sm">
                    <p className="max-w-[420px] text-xs text-slate-600 dark:text-slate-300">{error}</p>
                    <a
                        href={src}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 rounded-md border border-slate-100/80 px-2 py-1 text-[11px] tabular-nums text-slate-600 hover:border-blue-300 hover:text-blue-700 dark:border-white/[0.05] dark:text-slate-300 dark:hover:border-blue-700 dark:hover:text-blue-300"
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
    return filterAutoRestorableExtractionDocuments(job.documents.filter(isDocumentResultLike));
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

type TraceDisplayKind = 'field' | 'table' | 'image' | 'chart' | 'other';
type GraphSyncUiState = 'idle' | 'submitting' | 'success' | 'error';

const GRAPH_SYNC_SUPPORTED_EXTENSIONS = new Set(['pdf', 'docx', 'txt', 'md']);
const GRAPH_SYNC_EXCLUDED_EXTENSIONS = new Set(['xlsx', 'xls']);

const formatGraphSyncShortId = (value: unknown, width = 8): string => {
    const normalized = String(value || '').trim();
    if (!normalized) return '';
    return normalized.length <= width ? normalized : normalized.slice(0, width);
};

const formatGraphSyncProgress = (value: unknown): string => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '';
    const normalized = numeric <= 1 ? numeric * 100 : numeric;
    return `${Math.max(0, Math.min(100, normalized)).toFixed(normalized >= 10 ? 0 : 1)}%`;
};

const waitForGraphSyncPoll = (ms: number): Promise<void> =>
    new Promise((resolve) => window.setTimeout(resolve, ms));

const GRAPH_SYNC_DISCOVERY_POLL_MS = 1200;
const GRAPH_SYNC_ACTIVE_POLL_MS = 2000;
const GRAPH_SYNC_DISCOVERY_TIMEOUT_MS = 60_000;
const GRAPH_SYNC_ACTIVE_TIMEOUT_MS = 45 * 60 * 1000;
const GRAPH_SYNC_DISCOVERY_MAX_ATTEMPTS = Math.ceil(GRAPH_SYNC_DISCOVERY_TIMEOUT_MS / GRAPH_SYNC_DISCOVERY_POLL_MS);
const GRAPH_SYNC_ACTIVE_MAX_ATTEMPTS = Math.ceil(GRAPH_SYNC_ACTIVE_TIMEOUT_MS / GRAPH_SYNC_ACTIVE_POLL_MS);

const formatResultSoftWarning = (warningRaw: unknown): string => {
    const warning = String(warningRaw || '').trim();
    if (!warning) return '';
    const warningLower = warning.toLowerCase();

    if (warning.startsWith('auto_result_filter_removed:')) {
        const count = Number(warning.split(':').at(-1) || 0);
        return Number.isFinite(count) && count > 0
            ? `已自动过滤 ${Math.round(count)} 项低价值字段`
            : '已自动过滤部分低价值字段';
    }

    if (warning.startsWith('quality_gate_degraded:low_coverage')) {
        return '结果覆盖度偏低，建议人工复核';
    }

    if (warning.startsWith('quality_gate_degraded:')) {
        return '结果质量存在波动，建议人工复核';
    }

    if (
        warning.startsWith('table_extract_error:rate_limited_retryable')
        || warning.startsWith('field_extract_error:rate_limited_retryable')
        || warning.startsWith('downgraded:rate_limited_retryable')
        || warning.startsWith('upstream_rate_limited_retryable')
        || warning.includes('429')
        || /(?:^|[^0-9])429(?:[^0-9]|$)/i.test(warning)
        || warningLower.includes('rate limit')
        || warningLower.includes('too many requests')
    ) {
        return '上游解析服务限流，本次结果可能不完整';
    }

    if (
        warning.startsWith('table_extract_error:timeout_retryable')
        || warning.startsWith('field_extract_error:timeout_retryable')
        || warning.startsWith('downgraded:timeout_retryable')
        || warning.startsWith('table_extract_timeout')
        || warning.startsWith('field_extract_timeout')
        || warningLower.includes('timeout')
    ) {
        return '上游解析超时，本次结果可能不完整';
    }

    if (
        warning.startsWith('table_extract_error:upstream_retryable')
        || warning.startsWith('field_extract_error:upstream_retryable')
        || warning.startsWith('downgraded:recoverable_upstream')
        || warning.startsWith('upstream_connection_retryable')
        || warningLower.includes('connection error')
    ) {
        return '上游解析暂时异常，本次结果可能不完整';
    }

    if (
        warning.startsWith('table_extract_error:')
        || warning.startsWith('field_extract_error:')
        || warning === 'table_extract_error'
        || warning === 'field_extract_error'
    ) {
        return '表格或字段抽取阶段出现异常，本次结果可能不完整';
    }

    return warning;
};

const normalizeSoftWarningCode = (warningRaw: unknown): string =>
    String(warningRaw || '').trim().toLowerCase();

const getSoftWarningDisplayGroup = (warningRaw: unknown): string => {
    const warning = normalizeSoftWarningCode(warningRaw);
    if (!warning) return '';
    if (warning.startsWith('auto_result_filter_removed:')) return 'auto_result_filter_removed';
    if (warning.startsWith('quality_gate_degraded:low_coverage')) return 'quality_gate_degraded_low_coverage';
    if (warning.startsWith('quality_gate_degraded:')) return 'quality_gate_degraded';
    if (
        warning.startsWith('table_extract_error:rate_limited_retryable')
        || warning.startsWith('field_extract_error:rate_limited_retryable')
        || warning.startsWith('downgraded:rate_limited_retryable')
        || warning.startsWith('upstream_rate_limited_retryable')
        || warning.includes('429')
        || warning.includes('rate limit')
        || warning.includes('too many requests')
    ) {
        return 'retryable_rate_limit';
    }
    if (
        warning.startsWith('table_extract_error:timeout_retryable')
        || warning.startsWith('field_extract_error:timeout_retryable')
        || warning.startsWith('downgraded:timeout_retryable')
        || warning.startsWith('table_extract_timeout')
        || warning.startsWith('field_extract_timeout')
        || warning.includes('timeout')
    ) {
        return 'retryable_timeout';
    }
    if (
        warning.startsWith('table_extract_error:upstream_retryable')
        || warning.startsWith('field_extract_error:upstream_retryable')
        || warning.startsWith('downgraded:recoverable_upstream')
        || warning.startsWith('upstream_connection_retryable')
        || warning.includes('connection error')
    ) {
        return 'retryable_upstream';
    }
    if (
        warning.startsWith('table_extract_error:')
        || warning.startsWith('field_extract_error:')
        || warning === 'table_extract_error'
        || warning === 'field_extract_error'
    ) {
        return 'extract_error';
    }
    return `raw:${warning}`;
};

const shouldSuppressSoftWarningForDisplay = (
    warningRaw: unknown,
    doc?: DocumentResult | null,
): boolean => {
    const warning = normalizeSoftWarningCode(warningRaw);
    if (!warning || warning === 'quality_gate_ok') return true;
    if (warning === 'auto_result_filter_removed:0') return true;
    if (!doc) return false;
    if (warning.startsWith('downgraded:') && isRetryableExtractionWarning(warningRaw)) {
        return true;
    }
    if (warning.startsWith('quality_gate_degraded:') && isStaleRetryableExtractionDocument(doc)) {
        return true;
    }
    return false;
};

const getDisplaySoftWarnings = (doc?: DocumentResult | null): string[] => {
    if (!doc || !Array.isArray(doc.soft_warnings) || doc.soft_warnings.length === 0) return [];
    const labels: string[] = [];
    const seen = new Set<string>();
    doc.soft_warnings.forEach((warning) => {
        if (shouldSuppressSoftWarningForDisplay(warning, doc)) return;
        const label = formatResultSoftWarning(warning);
        if (!label) return;
        const group = getSoftWarningDisplayGroup(warning) || label;
        if (seen.has(group)) return;
        seen.add(group);
        labels.push(label);
    });
    return labels;
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

const DEFAULT_SCHEMA = {
    auto_infer: true,
    prefer_llm: true,
    max_auto_fields: 20,
};

type OfficePreviewState = {
    status: 'idle' | 'queued' | 'running' | 'completed' | 'failed';
    jobId?: string;
    pdfUrl?: string;
    error?: string;
};

type ExtractionJobFileState = PersistedExtractionJobFile;

type ExtractionJobState = PersistedExtractionJob;

type RuntimeExtractionJobFileState = ExtractionJobFileState & {
    __syncedAtMs?: number;
};

type RuntimeExtractionJobState = ExtractionJobState & {
    files: RuntimeExtractionJobFileState[];
    __syncedAtMs?: number;
    documents?: DocumentResult[];
};

type ExtractionJobRunningFileState = NonNullable<
    NonNullable<ExtractionJobState['progress']['running_files']>
>[number];

const isPlainRecord = (value: unknown): value is Record<string, unknown> =>
    !!value && typeof value === 'object' && !Array.isArray(value);

const EXTRACTION_STAGE_LABELS: Record<string, string> = {
    queued: '排队中',
    cached: '恢复缓存',
    preflight: '预检查',
    converting: '转 PDF',
    parsing: '版面解析',
    parsed: '版面就绪',
    extracting: '抽取字段与图表',
    finalizing: '整理结果',
    completed: '已完成',
    failed: '失败',
};

const EXTRACTION_STAGE_PROGRESS_META: Record<string, { ceiling: number; rampMs: number; maxHeadroom: number }> = {
    queued: { ceiling: 0.06, rampMs: 8000, maxHeadroom: 0.06 },
    preflight: { ceiling: 0.12, rampMs: 4000, maxHeadroom: 0.06 },
    converting: { ceiling: 0.28, rampMs: 22000, maxHeadroom: 0.12 },
    parsing: { ceiling: 0.74, rampMs: 90000, maxHeadroom: 0.22 },
    parsed: { ceiling: 0.78, rampMs: 5000, maxHeadroom: 0.08 },
    extracting: { ceiling: 0.93, rampMs: 70000, maxHeadroom: 0.18 },
    finalizing: { ceiling: 0.98, rampMs: 15000, maxHeadroom: 0.08 },
};

const normalizeExtractionStageName = (value: unknown): string =>
    String(value || '').trim().toLowerCase() || 'queued';

const toExtractionStageLabel = (value: unknown): string => {
    const stage = normalizeExtractionStageName(value);
    return EXTRACTION_STAGE_LABELS[stage] || (String(value || '').trim() || '处理中');
};

const ALLOWED_EXTENSIONS = new Set(['pdf', 'doc', 'docx', 'xlsx', 'txt', 'md', 'png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff']);
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff']);

const isAllowedFile = (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    return ALLOWED_EXTENSIONS.has(ext);
};

const fileExt = (name: string) => name.split('.').pop()?.toLowerCase() || '';
const fileIdentityKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;
type SelectedFileArtifactRef = {
    artifactByFileUrl?: string;
    artifactFileId?: string;
    artifactUrl?: string;
    artifactPath?: string;
};

const toPersistedWorkbenchFile = (file: File, patch?: Partial<PersistedWorkbenchFile>): PersistedWorkbenchFile => ({
    key: fileIdentityKey(file),
    name: file.name,
    size: file.size,
    lastModified: file.lastModified,
    ext: fileExt(file.name),
    artifactByFileUrl: patch?.artifactByFileUrl,
    artifactFileId: patch?.artifactFileId,
    artifactUrl: patch?.artifactUrl,
    artifactPath: patch?.artifactPath,
});

const normalizeWorkbenchFileName = (value: unknown): string =>
    String(value || '').trim().toLowerCase();

const buildExtractionJobServerFileKey = (fileHash: unknown, fileName: unknown): string => {
    const normalizedHash = String(fileHash || '').trim();
    const normalizedName = normalizeWorkbenchFileName(fileName);
    if (normalizedHash && normalizedName) {
        return `${normalizedHash}::${normalizedName}`;
    }
    if (normalizedHash) {
        return normalizedHash;
    }
    return normalizedName ? `name::${normalizedName}` : '';
};

const buildSelectedFileNameCounts = (files: File[]): Map<string, number> => {
    const counts = new Map<string, number>();
    files.forEach((file) => {
        const key = normalizeWorkbenchFileName(file.name);
        if (!key) return;
        counts.set(key, (counts.get(key) || 0) + 1);
    });
    return counts;
};

const collectHiddenExtractionJobFiles = (
    job: RuntimeExtractionJobState | null,
    selectedFiles: File[],
    suppressedKeys?: ReadonlySet<string>,
): RuntimeExtractionJobFileState[] => {
    if (!job || !Array.isArray(job.files) || job.files.length === 0) return [];
    const remainingNames = buildSelectedFileNameCounts(selectedFiles);
    const hidden: RuntimeExtractionJobFileState[] = [];
    job.files.forEach((item) => {
        const itemKey = buildExtractionJobServerFileKey(item.file_hash, item.file_name);
        if (itemKey && suppressedKeys?.has(itemKey)) {
            return;
        }
        const nameKey = normalizeWorkbenchFileName(item.file_name);
        const remaining = remainingNames.get(nameKey) || 0;
        if (remaining > 0) {
            remainingNames.set(nameKey, remaining - 1);
            return;
        }
        hidden.push(item);
    });
    return hidden;
};

const filterVisibleRuntimeExtractionJob = (
    job: RuntimeExtractionJobState | null,
    selectedFiles: File[],
    suppressedKeys?: ReadonlySet<string>,
): RuntimeExtractionJobState | null => {
    if (!job || !Array.isArray(job.files) || job.files.length === 0) return job;
    const remainingNames = buildSelectedFileNameCounts(selectedFiles);
    const filteredFiles: RuntimeExtractionJobFileState[] = [];

    job.files.forEach((item) => {
        const itemKey = buildExtractionJobServerFileKey(item.file_hash, item.file_name);
        if (itemKey && suppressedKeys?.has(itemKey)) {
            return;
        }
        const nameKey = normalizeWorkbenchFileName(item.file_name);
        const remaining = remainingNames.get(nameKey) || 0;
        if (selectedFiles.length > 0 && remaining <= 0) {
            return;
        }
        if (selectedFiles.length > 0) {
            remainingNames.set(nameKey, remaining - 1);
        }
        filteredFiles.push(item);
    });

    if ((suppressedKeys?.size || 0) === 0 && filteredFiles.length === job.files.length) {
        return job;
    }

    const filteredRunningFiles: ExtractionJobRunningFileState[] = filteredFiles
        .map((item, index) => ({
            file_index: index + 1,
            file_name: String(item.file_name || '').trim(),
            stage: String(item.stage || 'queued').trim() || 'queued',
            status: String(item.status || 'running').trim() || 'running',
            progress_ratio: Math.max(0, Math.min(1, Number(item.progress_ratio || 0))),
        }))
        .filter((item) => {
            const status = String(item.status || '').trim().toLowerCase();
            return !['queued', 'completed', 'failed', 'cancelled'].includes(status);
        });

    const activeStages = filteredRunningFiles.reduce<Record<string, number>>((acc, item) => {
        const stage = String(item.stage || 'queued').trim() || 'queued';
        acc[stage] = (acc[stage] || 0) + 1;
        return acc;
    }, {});

    const queuedFiles = filteredFiles.reduce((count, item) => (
        String(item.status || '').trim().toLowerCase() === 'queued' ? count + 1 : count
    ), 0);
    const completedFiles = filteredFiles.reduce((count, item) => (
        String(item.status || '').trim().toLowerCase() === 'completed' ? count + 1 : count
    ), 0);
    const failedFiles = filteredFiles.reduce((count, item) => (
        String(item.status || '').trim().toLowerCase() === 'failed' ? count + 1 : count
    ), 0);
    const progressRatio = filteredFiles.length > 0
        ? filteredFiles.reduce((sum, item) => sum + Math.max(0, Math.min(1, Number(item.progress_ratio || 0))), 0) / filteredFiles.length
        : 0;

    const currentRunning = filteredRunningFiles.find(
        (item) => String(item.file_name || '').trim() === String(job.progress?.current_file_name || '').trim(),
    ) || filteredRunningFiles[0] || null;

    let currentFileIndex = 0;
    let currentFileName = '';
    let currentStage = filteredFiles.length > 0
        ? String(filteredFiles[0]?.stage || job.progress?.current_stage || 'queued').trim() || 'queued'
        : (String(job.progress?.current_stage || 'queued').trim() || 'queued');

    if (currentRunning) {
        currentFileIndex = Math.max(1, Number(currentRunning.file_index || 1));
        currentFileName = String(currentRunning.file_name || '').trim();
        currentStage = String(currentRunning.stage || currentStage).trim() || currentStage;
    } else if (filteredFiles.length > 0) {
        const preferredIndex = Math.max(
            0,
            Math.min(filteredFiles.length - 1, Math.max(0, Number(job.progress?.current_file_index || 1) - 1)),
        );
        const preferredFile = filteredFiles[preferredIndex] || filteredFiles[0];
        currentFileIndex = preferredIndex + 1;
        currentFileName = String(preferredFile?.file_name || '').trim();
        currentStage = String(preferredFile?.stage || currentStage).trim() || currentStage;
    }

    return {
        ...job,
        files: filteredFiles,
        progress: {
            ...job.progress,
            total_files: filteredFiles.length,
            completed_files: completedFiles,
            failed_files: failedFiles,
            current_file_index: currentFileIndex,
            current_file_name: currentFileName,
            current_stage: currentStage,
            progress_ratio: progressRatio,
            queued_files: queuedFiles,
            running_files: filteredRunningFiles,
            active_stages: activeStages,
            parallel_workers: filteredRunningFiles.length,
        },
    };
};

const filterVisibleDocumentsForJobFiles = (
    docs: DocumentResult[],
    jobFiles: RuntimeExtractionJobFileState[],
): DocumentResult[] => {
    if (!Array.isArray(docs) || docs.length === 0) return [];
    if (!Array.isArray(jobFiles) || jobFiles.length === 0) return [];

    const remainingByKey = new Map<string, number>();
    const remainingByName = new Map<string, number>();

    jobFiles.forEach((item) => {
        const key = buildExtractionJobServerFileKey(item.file_hash, item.file_name);
        if (key) {
            remainingByKey.set(key, (remainingByKey.get(key) || 0) + 1);
        }
        const nameKey = normalizeWorkbenchFileName(item.file_name);
        if (nameKey) {
            remainingByName.set(nameKey, (remainingByName.get(nameKey) || 0) + 1);
        }
    });

    return docs.filter((doc) => {
        const key = buildExtractionJobServerFileKey(doc.file_hash, doc.file_name);
        const keyCount = key ? (remainingByKey.get(key) || 0) : 0;
        if (key && keyCount > 0) {
            remainingByKey.set(key, keyCount - 1);
            return true;
        }
        const nameKey = normalizeWorkbenchFileName(doc.file_name);
        const nameCount = remainingByName.get(nameKey) || 0;
        if (nameCount <= 0) {
            return false;
        }
        remainingByName.set(nameKey, nameCount - 1);
        return true;
    });
};

const toArtifactRouteFromFileId = (fileIdRaw: unknown): string => {
    const normalized = String(fileIdRaw || '').trim();
    if (!normalized) return '';
    return `/extract/artifact/by-file/${encodeURIComponent(normalized)}`;
};

const isLegacyExtractArtifactRoute = (rawUrl: string): boolean => {
    const value = String(rawUrl || '').trim();
    if (!value) return false;
    try {
        const parsed = /^https?:\/\//i.test(value) ? new URL(value) : new URL(value, 'http://localhost');
        const pathname = String(parsed.pathname || '');
        return pathname.startsWith('/extract/artifact/') && !pathname.startsWith('/extract/artifact/by-file/');
    } catch {
        return value.startsWith('/extract/artifact/') && !value.startsWith('/extract/artifact/by-file/');
    }
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

const normalizeExtractArtifactUrl = (
    rawUrl: string,
    preferredBase = '',
): string => {
    const relative = toRelativeExtractPath(rawUrl);
    if (relative) {
        if (isLegacyExtractArtifactRoute(relative)) return '';
        return relative;
    }
    if (isLegacyExtractArtifactRoute(rawUrl)) return '';
    return toAbsoluteExtractUrl(rawUrl, preferredBase);
};

const resolveByFileArtifactUrl = (
    payload: Record<string, unknown> | null | undefined,
    preferredBase = '',
): string => {
    const byFileRaw = String(payload?.artifact_by_file_url || '').trim();
    if (byFileRaw) {
        const normalized = normalizeExtractArtifactUrl(byFileRaw, preferredBase);
        if (normalized) return normalized;
    }
    const byFileRoute = toArtifactRouteFromFileId(payload?.artifact_file_id);
    if (byFileRoute) {
        const normalized = normalizeExtractArtifactUrl(byFileRoute, preferredBase);
        if (normalized) return normalized;
    }
    return '';
};

const normalizeSelectedFileArtifactRef = (
    ref: Partial<SelectedFileArtifactRef> | null | undefined,
    preferredBase = '',
): SelectedFileArtifactRef => {
    const artifactByFileUrlRaw = String(ref?.artifactByFileUrl || '').trim();
    const artifactUrlRaw = String(ref?.artifactUrl || '').trim();
    return {
        artifactByFileUrl:
            normalizeExtractArtifactUrl(artifactByFileUrlRaw, preferredBase)
            || artifactByFileUrlRaw
            || undefined,
        artifactFileId: String(ref?.artifactFileId || '').trim() || undefined,
        artifactUrl: normalizeExtractArtifactUrl(artifactUrlRaw, preferredBase) || undefined,
        artifactPath: undefined,
    };
};

const hasRestorableArtifactRef = (ref: Partial<SelectedFileArtifactRef> | null | undefined): boolean => {
    const normalized = normalizeSelectedFileArtifactRef(ref);
    return Boolean(
        normalized.artifactByFileUrl
        || normalized.artifactFileId
        || normalized.artifactUrl
        || normalized.artifactPath,
    );
};

// --- Global Cache for Module Switching ---
const fileBlobCache = new Map<string, File>();

const hydrateFileFromArtifact = async (item: PersistedWorkbenchFile): Promise<File | null> => {
    if (item.key && fileBlobCache.has(item.key)) {
        return fileBlobCache.get(item.key)!;
    }
    const artifactByFileUrl = String(item.artifactByFileUrl || '').trim();
    const artifactByFileRoute = toArtifactRouteFromFileId(item.artifactFileId);
    const artifactUrl = String(item.artifactUrl || '').trim();
    if (!artifactByFileUrl && !artifactByFileRoute && !artifactUrl) return null;
    const byFileRelativeUrl = toRelativeExtractPath(artifactByFileUrl);
    const relativeUrl = toRelativeExtractPath(artifactUrl);
    const resolvedBase = resolveExtractBase('');
    const byFileRelativeWithBase = byFileRelativeUrl ? joinExtractUrl(resolvedBase, byFileRelativeUrl) : '';
    const byFileRouteWithBase = artifactByFileRoute ? joinExtractUrl(resolvedBase, artifactByFileRoute) : '';
    const relativeWithBase = relativeUrl ? joinExtractUrl(resolvedBase, relativeUrl) : '';
    const directArtifactUrl = normalizeExtractArtifactUrl(artifactUrl, resolvedBase);
    const candidates = Array.from(
        new Set(
            [
                byFileRelativeUrl,
                artifactByFileRoute,
                relativeUrl,
                directArtifactUrl,
                byFileRelativeWithBase,
                byFileRouteWithBase,
                relativeWithBase,
                /^https?:\/\//i.test(directArtifactUrl) ? directArtifactUrl : toAbsoluteExtractUrl(directArtifactUrl, ''),
            ].filter(Boolean),
        ),
    );
    let response: Response | null = null;
    for (const candidate of candidates) {
        try {
            const fetched = await fetch(candidate, {
                credentials: 'include',
            });
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
    const restoredFile = new FileCtor([blob], item.name, {
        type: blob.type || 'application/octet-stream',
        lastModified: Number(item.lastModified || Date.now()),
    });
    if (item.key) {
        fileBlobCache.set(item.key, restoredFile);
    }
    return restoredFile;
};

const toSessionSnapshot = (
    selectedFiles: File[],
    activeDocIndex: number,
    activeDocFileHash: string,
    smartUnitTab: SmartUnitTabId,
    officePreviewMap: Record<string, OfficePreviewState>,
    extractionJob: ExtractionJobState | null,
    artifactMap: Record<string, SelectedFileArtifactRef>,
    fallbackSelectedFiles: PersistedWorkbenchFile[] = [],
): WorkbenchSessionSnapshot => ({
    version: 1,
    activeDocIndex,
    activeDocFileHash: String(activeDocFileHash || '').trim(),
    smartUnitTab,
    selectedFiles: selectedFiles.length > 0
        ? selectedFiles.map((file) => toPersistedWorkbenchFile(file, artifactMap[fileIdentityKey(file)]))
        : fallbackSelectedFiles.map((item) => {
            const normalized = normalizeSelectedFileArtifactRef({
                artifactByFileUrl: artifactMap[item.key]?.artifactByFileUrl ?? item.artifactByFileUrl,
                artifactFileId: artifactMap[item.key]?.artifactFileId ?? item.artifactFileId,
                artifactUrl: artifactMap[item.key]?.artifactUrl ?? item.artifactUrl,
                artifactPath: artifactMap[item.key]?.artifactPath ?? item.artifactPath,
            });
            return {
                ...item,
                artifactByFileUrl: normalized.artifactByFileUrl,
                artifactFileId: normalized.artifactFileId,
                artifactUrl: normalized.artifactUrl,
                artifactPath: normalized.artifactPath,
            };
        }),
    officePreviewMap,
    extractionJob: toPersistedExtractionJob(extractionJob),
});

const clampProgressPercent = (ratio: number) =>
    Math.max(0, Math.min(100, Math.round(Math.max(0, Math.min(1, Number(ratio || 0))) * 100)));

const formatProgressPercent = (ratio: number, digits = 0): string => {
    const clampedPercent = Math.max(0, Math.min(100, Math.max(0, Math.min(1, Number(ratio || 0))) * 100));
    const precision = Math.max(0, Math.min(2, Math.floor(Number(digits) || 0)));
    if (precision === 0) {
        return `${Math.round(clampedPercent)}%`;
    }
    const factor = 10 ** precision;
    const rounded = Math.round(clampedPercent * factor) / factor;
    const normalized = rounded.toFixed(precision).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1');
    return `${normalized}%`;
};

const estimateExtractionProgressRatio = (
    ratio: number,
    stage: unknown,
    syncedAtMs?: number,
    terminal = false,
    nowMs?: number,
): number => {
    const base = Math.max(0, Math.min(1, Number(ratio || 0)));
    const stageName = normalizeExtractionStageName(stage);
    if (terminal || ['completed', 'failed', 'cached', 'cancelled'].includes(stageName) || !Number.isFinite(syncedAtMs || NaN)) {
        return base;
    }

    const meta = EXTRACTION_STAGE_PROGRESS_META[stageName];
    const ceiling = Math.max(
        base,
        Math.min(
            Number(meta?.ceiling ?? Math.min(0.96, base + 0.12)),
            base + Math.max(0, Number(meta?.maxHeadroom ?? 0.12)),
        ),
    );
    if (ceiling <= base) {
        return base;
    }

    const currentNowMs = Number.isFinite(nowMs || NaN) ? Number(nowMs) : Date.now();
    const elapsed = Math.max(0, currentNowMs - Number(syncedAtMs || 0));
    const rampMs = Math.max(1200, Number(meta?.rampMs ?? 10000));
    const t = Math.min(1, elapsed / rampMs);
    const eased = 1 - (1 - t) ** 3;
    return base + (ceiling - base) * eased;
};

const estimateRuntimeExtractionFileRatio = (
    extractionJob: RuntimeExtractionJobState | null,
    jobFile: RuntimeExtractionJobFileState | null,
    nowMs?: number,
): number => {
    if (!jobFile) return 0;
    const status = String(jobFile.status || '').trim().toLowerCase();
    return estimateExtractionProgressRatio(
        jobFile.progress_ratio,
        jobFile.stage,
        jobFile.__syncedAtMs ?? extractionJob?.__syncedAtMs,
        Boolean(extractionJob?.terminal) || ['completed', 'failed', 'cached', 'cancelled'].includes(status),
        nowMs,
    );
};

const estimateRuntimeExtractionOverallRatio = (
    extractionJob: RuntimeExtractionJobState | null,
    nowMs?: number,
): number => {
    if (!extractionJob) return 0;
    const normalizedNowMs = Number.isFinite(nowMs || NaN) ? Number(nowMs) : Date.now();
    if (Array.isArray(extractionJob.files) && extractionJob.files.length > 0) {
        const totalFiles = Math.max(1, Number(extractionJob.progress?.total_files || extractionJob.files.length || 1));
        const summedRatio = extractionJob.files.reduce(
            (acc, item) => acc + estimateRuntimeExtractionFileRatio(extractionJob, item, normalizedNowMs),
            0,
        );
        return Math.max(0, Math.min(1, summedRatio / totalFiles));
    }
    return estimateExtractionProgressRatio(
        extractionJob.progress?.progress_ratio || 0,
        extractionJob.progress?.current_stage,
        extractionJob.__syncedAtMs,
        Boolean(extractionJob.terminal),
        normalizedNowMs,
    );
};

const getRuntimeRunningExtractionFiles = (
    extractionJob: RuntimeExtractionJobState | null,
): ExtractionJobRunningFileState[] => {
    if (!extractionJob) return [];
    if (Array.isArray(extractionJob.progress?.running_files) && extractionJob.progress.running_files.length > 0) {
        return extractionJob.progress.running_files
            .map((item, index) => ({
                file_index: Math.max(1, Number(item?.file_index || index + 1)),
                file_name: String(item?.file_name || '').trim(),
                stage: String(item?.stage || 'queued').trim() || 'queued',
                status: String(item?.status || 'running').trim() || 'running',
                progress_ratio: Math.max(0, Math.min(1, Number(item?.progress_ratio || 0))),
            }))
            .filter((item) => item.file_name);
    }
    return extractionJob.files
        .map((item, index) => ({
            file_index: index + 1,
            file_name: String(item.file_name || '').trim(),
            stage: String(item.stage || 'queued').trim() || 'queued',
            status: String(item.status || 'running').trim() || 'running',
            progress_ratio: Math.max(0, Math.min(1, Number(item.progress_ratio || 0))),
        }))
        .filter((item) => {
            const status = String(item.status || '').trim().toLowerCase();
            return status !== 'queued' && status !== 'completed' && status !== 'failed' && status !== 'cancelled';
        });
};

const getRuntimeQueuedExtractionFileCount = (
    extractionJob: RuntimeExtractionJobState | null,
): number => {
    if (!extractionJob) return 0;
    const explicit = Number(extractionJob.progress?.queued_files);
    if (Number.isFinite(explicit)) {
        return Math.max(0, Math.floor(explicit));
    }
    return extractionJob.files.reduce((count, item) => (
        String(item.status || '').trim().toLowerCase() === 'queued' ? count + 1 : count
    ), 0);
};

const formatExtractionActiveStageSummary = (
    extractionJob: RuntimeExtractionJobState | null,
): string => {
    if (!extractionJob) return '';
    const stageCounts: Record<string, number> = {};
    if (isPlainRecord(extractionJob.progress?.active_stages)) {
        Object.entries(extractionJob.progress.active_stages).forEach(([stage, rawCount]) => {
            const count = Math.max(0, Math.floor(Number(rawCount || 0)));
            if (count > 0) {
                stageCounts[String(stage || '').trim() || 'queued'] = count;
            }
        });
    } else {
        getRuntimeRunningExtractionFiles(extractionJob).forEach((item) => {
            const stage = String(item.stage || 'queued').trim() || 'queued';
            stageCounts[stage] = (stageCounts[stage] || 0) + 1;
        });
    }
    const items = Object.entries(stageCounts)
        .filter(([, count]) => count > 0)
        .slice(0, 3)
        .map(([stage, count]) => `${toExtractionStageLabel(stage) || stage}×${count}`);
    return items.join('，');
};

const pickCurrentExtractionJobFileState = (
    extractionJob: RuntimeExtractionJobState | null,
): RuntimeExtractionJobFileState | null => {
    if (!extractionJob || !Array.isArray(extractionJob.files) || extractionJob.files.length === 0) {
        return null;
    }
    const currentFileName = String(extractionJob.progress?.current_file_name || '').trim().toLowerCase();
    const currentIndex = Math.max(0, Number(extractionJob.progress?.current_file_index || 0) - 1);
    const byIndex = extractionJob.files[currentIndex] || null;
    if (
        byIndex
        && (
            !currentFileName
            || String(byIndex.file_name || '').trim().toLowerCase() === currentFileName
        )
    ) {
        return byIndex;
    }
    if (currentFileName) {
        const matched = extractionJob.files.find(
            (item) => String(item.file_name || '').trim().toLowerCase() === currentFileName,
        );
        if (matched) {
            return matched;
        }
    }
    return extractionJob.files.find((item) => String(item.status || '').trim().toLowerCase() === 'running')
        || extractionJob.files[0]
        || null;
};

const buildExtractionInfoMessage = (
    extractionJob: RuntimeExtractionJobState | null,
    nowMs?: number,
    submitted = false,
): string => {
    if (!extractionJob) {
        return submitted ? '已提交任务，等待后端开始解析。' : '正在处理文档。';
    }

    const normalizedNowMs = Number.isFinite(nowMs || NaN) ? Number(nowMs) : Date.now();
    const currentFileName = String(extractionJob.progress?.current_file_name || '').trim();
    const currentStageLabel = toExtractionStageLabel(extractionJob.progress?.current_stage);
    const overallRatio = estimateRuntimeExtractionOverallRatio(extractionJob, normalizedNowMs);
    const overallPercentLabel = formatProgressPercent(overallRatio, extractionJob.terminal ? 0 : 1);
    const currentFileState = pickCurrentExtractionJobFileState(extractionJob);
    const currentFileRatio = estimateRuntimeExtractionFileRatio(extractionJob, currentFileState, normalizedNowMs);
    const currentFilePercentLabel = formatProgressPercent(currentFileRatio, extractionJob.terminal ? 0 : 1);
    const totalFiles = Math.max(
        1,
        Number(extractionJob.progress?.total_files || extractionJob.files.length || 1),
    );
    const prefix = submitted ? '已提交任务，正在处理' : '正在处理';
    const completedFiles = Math.max(0, Number(extractionJob.progress?.completed_files || 0));
    const failedFiles = Math.max(0, Number(extractionJob.progress?.failed_files || 0));
    const runningFiles = getRuntimeRunningExtractionFiles(extractionJob);
    const runningCount = runningFiles.length;
    const queuedCount = getRuntimeQueuedExtractionFileCount(extractionJob);
    const stageSummary = formatExtractionActiveStageSummary(extractionJob);

    if (totalFiles > 1) {
        if (runningCount > 0) {
            const runningNames = runningFiles
                .slice(0, 2)
                .map((item) => item.file_name)
                .filter(Boolean)
                .join('、');
            const runningLabel = runningNames
                ? (runningCount > 2 ? `${runningNames} 等 ${runningCount} 个文件` : runningNames)
                : `并行中 ${runningCount} 个文件`;
            const parts = [
                `${prefix} ${runningLabel}`,
                `已完成 ${Math.min(totalFiles, completedFiles + failedFiles)}/${totalFiles}`,
                failedFiles > 0 ? `失败 ${failedFiles}` : '',
                queuedCount > 0 ? `排队 ${queuedCount} 个` : '',
                stageSummary ? `当前阶段 ${stageSummary}` : '',
                `批次 ${overallPercentLabel}`,
            ].filter(Boolean);
            return parts.join(' · ');
        }

        if (currentFileName) {
            return `${prefix} ${currentFileName} · ${currentStageLabel || '处理中'} · 当前文件 ${currentFilePercentLabel} · 批次 ${overallPercentLabel}`;
        }

        if (submitted) {
            return `已提交 ${totalFiles} 个文件，等待后端分配处理槽位 · 批次 ${overallPercentLabel}`;
        }
        return `正在处理 ${totalFiles} 个文件 · 已完成 ${Math.min(totalFiles, completedFiles + failedFiles)}/${totalFiles} · 批次 ${overallPercentLabel}`;
    }

    if (currentFileName) {
        return `${prefix} ${currentFileName} · ${currentStageLabel || '处理中'} · ${currentFilePercentLabel}`;
    }

    return submitted ? `已提交任务，等待后端开始解析 · ${overallPercentLabel}` : `正在处理文档 · ${overallPercentLabel}`;
};

const toPersistedExtractionJob = (job: ExtractionJobState | null): PersistedExtractionJob | null => {
    if (!job) return null;
    return {
        job_id: String(job.job_id || '').trim(),
        status: String(job.status || 'queued').trim() || 'queued',
        terminal: Boolean(job.terminal),
        created_at: Number(job.created_at || 0),
        updated_at: Number(job.updated_at || 0),
        progress: {
            total_files: Math.max(0, Number(job.progress?.total_files || 0)),
            completed_files: Math.max(0, Number(job.progress?.completed_files || 0)),
            failed_files: Math.max(0, Number(job.progress?.failed_files || 0)),
            current_file_index: Math.max(0, Number(job.progress?.current_file_index || 0)),
            current_file_name: String(job.progress?.current_file_name || '').trim(),
            current_stage: String(job.progress?.current_stage || 'queued').trim() || 'queued',
            progress_ratio: Math.max(0, Math.min(1, Number(job.progress?.progress_ratio || 0))),
            queued_files: Math.max(0, Number(job.progress?.queued_files || 0)),
            running_files: Array.isArray(job.progress?.running_files)
                ? job.progress.running_files.map((item, index) => ({
                    file_index: Math.max(1, Number(item?.file_index || index + 1)),
                    file_name: String(item?.file_name || '').trim(),
                    stage: String(item?.stage || 'queued').trim() || 'queued',
                    status: String(item?.status || 'running').trim() || 'running',
                    progress_ratio: Math.max(0, Math.min(1, Number(item?.progress_ratio || 0))),
                }))
                : [],
            active_stages: isPlainRecord(job.progress?.active_stages)
                ? Object.fromEntries(
                    Object.entries(job.progress.active_stages).map(([stage, rawCount]) => [
                        String(stage || '').trim() || 'queued',
                        Math.max(0, Math.floor(Number(rawCount || 0))),
                    ]),
                )
                : {},
            parallel_workers: Math.max(0, Number(job.progress?.parallel_workers || 0)),
        },
        files: Array.isArray(job.files)
            ? job.files.map((item) => ({
                file_name: String(item.file_name || '').trim(),
                file_hash: String(item.file_hash || '').trim(),
                status: String(item.status || 'queued').trim() || 'queued',
                stage: String(item.stage || 'queued').trim() || 'queued',
                progress_ratio: Math.max(0, Math.min(1, Number(item.progress_ratio || 0))),
                message: String(item.message || '').trim(),
                artifact_file_id: item.artifact_file_id ?? null,
                artifact_download_url: item.artifact_download_url ?? null,
                artifact_by_file_url: item.artifact_by_file_url ?? null,
                artifact_path: null,
                artifact_url: item.artifact_url ?? null,
                error: sanitizeExtractUiErrorMessage(item.error),
                track: String(item.track || '').trim(),
                cached: Boolean(item.cached),
            }))
            : [],
        errors: sanitizeExtractUiErrorList(job.errors),
    };
};

const normalizeExtractionJobPayload = (
    payload: ExtractionJobState & { documents?: DocumentResult[] },
    usedBase: string,
    previous?: RuntimeExtractionJobState | null,
): RuntimeExtractionJobState => {
    const syncedAtMs = Date.now();
    const previousByKey = new Map<string, RuntimeExtractionJobFileState>();
    if (previous?.job_id === payload.job_id && Array.isArray(previous.files)) {
        previous.files.forEach((item) => {
            const key = `${String(item.file_hash || '').trim()}::${String(item.file_name || '').trim().toLowerCase()}`;
            previousByKey.set(key, item);
        });
    }

    const normalizedFiles: RuntimeExtractionJobFileState[] = Array.isArray(payload.files)
        ? payload.files.map((item) => {
            const key = `${String(item.file_hash || '').trim()}::${String(item.file_name || '').trim().toLowerCase()}`;
            const previousFile = previousByKey.get(key);
            const nextStage = normalizeExtractionStageName(item.stage);
            const nextStatus = String(item.status || '').trim().toLowerCase();
            let nextRatio = Math.max(0, Math.min(1, Number(item.progress_ratio || 0)));
            if (
                previousFile
                && !payload.terminal
                && !['completed', 'failed'].includes(nextStatus)
                && normalizeExtractionStageName(previousFile.stage) === nextStage
                && String(previousFile.status || '').trim().toLowerCase() === nextStatus
            ) {
                const previousDisplayedRatio = estimateExtractionProgressRatio(
                    Number(previousFile.progress_ratio || 0),
                    previousFile.stage,
                    previousFile.__syncedAtMs,
                    false,
                    syncedAtMs,
                );
                nextRatio = Math.max(
                    nextRatio,
                    Math.max(0, Math.min(1, Number(previousFile.progress_ratio || 0))),
                    Math.max(0, Math.min(1, previousDisplayedRatio)),
                );
            }
            const normalizedByFileUrl = resolveByFileArtifactUrl(item as Record<string, unknown>, usedBase);
            const normalizedArtifactUrl = normalizeExtractArtifactUrl(
                String(item.artifact_url || '').trim(),
                usedBase,
            );
            return {
                ...item,
                progress_ratio: nextRatio,
                artifact_by_file_url: normalizedByFileUrl || String(item.artifact_by_file_url || '').trim() || undefined,
                artifact_download_url: String(item.artifact_download_url || '').trim() || undefined,
                artifact_file_id: String(item.artifact_file_id || '').trim() || undefined,
                artifact_url: normalizedByFileUrl || normalizedArtifactUrl || undefined,
                artifact_path: undefined,
                error: sanitizeExtractUiErrorMessage(item.error),
                __syncedAtMs: syncedAtMs,
            };
        })
        : [];
    const normalizedRunningFiles = Array.isArray(payload.progress?.running_files)
        ? payload.progress.running_files.map((item, index) => ({
            file_index: Math.max(1, Number(item?.file_index || index + 1)),
            file_name: String(item?.file_name || '').trim(),
            stage: String(item?.stage || 'queued').trim() || 'queued',
            status: String(item?.status || 'running').trim() || 'running',
            progress_ratio: Math.max(0, Math.min(1, Number(item?.progress_ratio || 0))),
        }))
        : [];
    const normalizedActiveStages = isPlainRecord(payload.progress?.active_stages)
        ? Object.fromEntries(
            Object.entries(payload.progress.active_stages).map(([stage, rawCount]) => [
                String(stage || '').trim() || 'queued',
                Math.max(0, Math.floor(Number(rawCount || 0))),
            ]),
        )
        : {};

    let overallRatio = Math.max(0, Math.min(1, Number(payload.progress?.progress_ratio || 0)));
    if (
        previous?.job_id === payload.job_id
        && !payload.terminal
        && normalizeExtractionStageName(previous.progress?.current_stage) === normalizeExtractionStageName(payload.progress?.current_stage)
        && String(previous.progress?.current_file_name || '').trim() === String(payload.progress?.current_file_name || '').trim()
    ) {
        const previousDisplayedOverallRatio = estimateExtractionProgressRatio(
            Number(previous.progress?.progress_ratio || 0),
            previous.progress?.current_stage,
            previous.__syncedAtMs,
            false,
            syncedAtMs,
        );
        overallRatio = Math.max(
            overallRatio,
            Math.max(0, Math.min(1, Number(previous.progress?.progress_ratio || 0))),
            Math.max(0, Math.min(1, previousDisplayedOverallRatio)),
        );
    }

    return {
        ...payload,
        progress: {
            total_files: Math.max(0, Number(payload.progress?.total_files || normalizedFiles.length || 0)),
            completed_files: Math.max(0, Number(payload.progress?.completed_files || 0)),
            failed_files: Math.max(0, Number(payload.progress?.failed_files || 0)),
            current_file_index: Math.max(0, Number(payload.progress?.current_file_index || 0)),
            current_file_name: String(payload.progress?.current_file_name || '').trim(),
            current_stage: String(payload.progress?.current_stage || 'queued').trim() || 'queued',
            progress_ratio: overallRatio,
            queued_files: Math.max(0, Number(payload.progress?.queued_files || 0)),
            running_files: normalizedRunningFiles,
            active_stages: normalizedActiveStages,
            parallel_workers: Math.max(
                0,
                Number(payload.progress?.parallel_workers || normalizedRunningFiles.length || 0),
            ),
        },
        files: normalizedFiles,
        errors: sanitizeExtractUiErrorList(payload.errors),
        __syncedAtMs: syncedAtMs,
    };
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
    extractionJob: RuntimeExtractionJobState | null,
    file: File,
    index: number,
): RuntimeExtractionJobFileState | null => {
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
    return matched[0] || null;
};

const pickDocumentResultForFile = (
    docs: DocumentResult[],
    file: File,
    index: number,
): DocumentResult | null => {
    if (!Array.isArray(docs) || docs.length === 0) return null;
    const normalizedName = normalizeWorkbenchFileName(file.name);
    const byIndex = docs[index] || null;
    if (byIndex && normalizeWorkbenchFileName(byIndex.file_name) === normalizedName) {
        return byIndex;
    }
    const matched = docs.filter(
        (item) => normalizeWorkbenchFileName(item.file_name) === normalizedName,
    );
    if (matched.length === 1) return matched[0];
    return (byIndex && normalizeWorkbenchFileName(byIndex.file_name) === normalizedName)
        ? byIndex
        : matched[0] || null;
};

const mergeExtractionDocumentsForSelection = (
    previousDocs: DocumentResult[],
    incomingDocs: DocumentResult[],
    selectedFiles: File[],
): DocumentResult[] => {
    if (!Array.isArray(incomingDocs) || incomingDocs.length === 0) {
        return Array.isArray(previousDocs) ? previousDocs : [];
    }
    if (!Array.isArray(previousDocs) || previousDocs.length === 0) {
        return incomingDocs;
    }

    const previousBuckets = new Map<string, DocumentResult[]>();
    const incomingBuckets = new Map<string, DocumentResult[]>();
    const pushBucket = (
        target: Map<string, DocumentResult[]>,
        doc: DocumentResult,
    ) => {
        const key = normalizeWorkbenchFileName(doc.file_name);
        if (!key) return;
        const current = target.get(key) || [];
        current.push(doc);
        target.set(key, current);
    };

    previousDocs.forEach((doc) => pushBucket(previousBuckets, doc));
    incomingDocs.forEach((doc) => pushBucket(incomingBuckets, doc));

    const ordered: DocumentResult[] = [];
    selectedFiles.forEach((file) => {
        const key = normalizeWorkbenchFileName(file.name);
        if (!key) return;

        const incomingBucket = incomingBuckets.get(key);
        if (incomingBucket && incomingBucket.length > 0) {
            const next = incomingBucket.shift();
            if (next) {
                ordered.push(next);
                return;
            }
        }

        const previousBucket = previousBuckets.get(key);
        if (previousBucket && previousBucket.length > 0) {
            const next = previousBucket.shift();
            if (next) {
                ordered.push(next);
            }
        }
    });

    return ordered;
};

const mergeSelectedFileArtifactsFromJob = (
    previousArtifacts: Record<string, SelectedFileArtifactRef>,
    selectedFiles: File[],
    jobFiles: RuntimeExtractionJobFileState[],
): Record<string, SelectedFileArtifactRef> => {
    const next = { ...(previousArtifacts || {}) };
    if (!Array.isArray(selectedFiles) || selectedFiles.length === 0) {
        return next;
    }
    if (!Array.isArray(jobFiles) || jobFiles.length === 0) {
        return next;
    }

    const jobBuckets = new Map<string, RuntimeExtractionJobFileState[]>();
    jobFiles.forEach((item) => {
        const key = normalizeWorkbenchFileName(item.file_name);
        if (!key) return;
        const current = jobBuckets.get(key) || [];
        current.push(item);
        jobBuckets.set(key, current);
    });

    selectedFiles.forEach((file) => {
        const key = normalizeWorkbenchFileName(file.name);
        if (!key) return;
        const bucket = jobBuckets.get(key);
        if (!bucket || bucket.length === 0) return;
        const item = bucket.shift();
        if (!item) return;
        next[fileIdentityKey(file)] = normalizeSelectedFileArtifactRef({
            artifactByFileUrl: String(item.artifact_by_file_url || '').trim() || undefined,
            artifactFileId: String(item.artifact_file_id || '').trim() || undefined,
            artifactUrl: String(item.artifact_url || '').trim() || undefined,
            artifactPath: undefined,
        });
    });

    return next;
};

const removeDocumentResultForFile = (
    docs: DocumentResult[],
    file: File,
): DocumentResult[] => {
    if (!Array.isArray(docs) || docs.length === 0) return [];
    const targetName = normalizeWorkbenchFileName(file.name);
    if (!targetName) return docs;
    return docs.filter((doc) => normalizeWorkbenchFileName(doc.file_name) !== targetName);
};

const removeDocumentResultsForNames = (
    docs: DocumentResult[],
    fileNames: Iterable<string>,
): DocumentResult[] => {
    if (!Array.isArray(docs) || docs.length === 0) return [];
    const normalizedTargets = new Set(
        Array.from(fileNames)
            .map((item) => normalizeWorkbenchFileName(item))
            .filter(Boolean),
    );
    if (normalizedTargets.size === 0) return docs;
    return docs.filter((doc) => !normalizedTargets.has(normalizeWorkbenchFileName(doc.file_name)));
};

type ExtractFetchResult = {
    response: Response;
    usedBase: string;
};

type ExtractFetchFallbackOptions = {
    retryNotFound?: boolean;
    routeMissRetryAttempts?: number;
};

const DEFAULT_EXTRACT_ROUTE_MISS_RETRY_ATTEMPTS = 2;
const EXTRACT_ROUTE_MISS_RETRY_DELAY_MS = 450;
const BACKEND_FALLBACKS_KEY = 'smart_doc_flow.backend_entry_fallbacks';

const waitForExtractRetry = (ms: number): Promise<void> =>
    new Promise((resolve) => window.setTimeout(resolve, ms));

const getViteExtractBase = (): string => {
    try {
        const envObj = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
        return String(
            envObj?.VITE_MODULE2_API_BASE
            || envObj?.VITE_EXTRACT_API_BASE
            || envObj?.VITE_BACKEND_ENTRY_URL
            || '',
        ).trim();
    } catch {
        return '';
    }
};

const parseExtractBaseCandidates = (raw = ''): string[] =>
    String(raw || '')
        .split(/[,\n;]/)
        .map((item) => String(item || '').trim())
        .filter(Boolean);

const trimTrailingSlash = (value: string) => String(value || '').replace(/\/+$/, '');

const normalizeExtractBase = (raw: string): string => {
    const base = trimTrailingSlash(String(raw || '').trim());
    if (!base) return '';
    return base.endsWith('/extract') ? base.slice(0, -8) : base;
};

const isLoopbackExtractHost = (hostname: string): boolean => {
    const normalized = String(hostname || '').trim().toLowerCase();
    return (
        normalized === 'localhost'
        || normalized === '127.0.0.1'
        || normalized === '0.0.0.0'
        || normalized === '::1'
        || normalized === '[::1]'
        || normalized.endsWith('.localhost')
    );
};

const isElectronExtractRuntime = (): boolean => {
    if (typeof navigator === 'undefined') return false;
    return /electron/i.test(String(navigator.userAgent || ''));
};

const isLocalExtractRuntime = (): boolean => {
    if (typeof window === 'undefined') return false;
    return (
        window.location.protocol === 'file:'
        || isLoopbackExtractHost(window.location.hostname)
        || isElectronExtractRuntime()
    );
};

const isLoopbackExtractBase = (value: string): boolean => {
    try {
        const parsed = new URL(value);
        return isLoopbackExtractHost(parsed.hostname);
    } catch {
        return false;
    }
};

const shouldSkipExtractBaseCandidate = (value: string): boolean => {
    const normalized = normalizeExtractBase(value);
    if (!normalized || !/^https?:\/\//i.test(normalized)) return false;
    return isLocalExtractRuntime() && !isLoopbackExtractBase(normalized);
};

const shouldSkipRelativeExtractCandidate = (): boolean => {
    if (typeof window === 'undefined') return false;
    return isElectronExtractRuntime() && !isLoopbackExtractHost(window.location.hostname);
};

const buildLoopbackGatewayBaseCandidate = (): string => {
    if (typeof window === 'undefined') return '';
    try {
        const hostname = window.location.hostname;
        const port = window.location.port;
        if (isElectronExtractRuntime() && !isLoopbackExtractHost(hostname)) {
            return 'http://127.0.0.1:3001';
        }
        if (!isLoopbackExtractHost(hostname) || port === '3001') return '';

        const url = new URL(window.location.href);
        url.pathname = '';
        url.search = '';
        url.hash = '';
        url.port = '3001';
        return normalizeExtractBase(`${url.protocol}//${url.host}`);
    } catch {
        return '';
    }
};

const getLocalStorageExtractBase = (): string => {
    if (typeof window === 'undefined') return '';
    try {
        return String(window.localStorage.getItem('module2_api_base_override') || '').trim();
    } catch {
        return '';
    }
};

const getViteExtractFallbackBases = (): string[] => {
    try {
        const envObj = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env;
        return parseExtractBaseCandidates(String(envObj?.VITE_BACKEND_ENTRY_URL_FALLBACKS || ''));
    } catch {
        return [];
    }
};

const getLocalStorageBackendFallbackBases = (): string[] => {
    if (typeof window === 'undefined') return [];
    try {
        return parseExtractBaseCandidates(window.localStorage.getItem(BACKEND_FALLBACKS_KEY) || '');
    } catch {
        return [];
    }
};

const hasConfiguredExtractBaseCandidates = (preferredBase = ''): boolean => {
    if (normalizeExtractBase(preferredBase)) return true;
    if (normalizeExtractBase(getLocalStorageExtractBase())) return true;
    if (normalizeExtractBase(getViteExtractBase())) return true;
    if (getViteExtractFallbackBases().some((item) => normalizeExtractBase(item))) return true;
    if (getLocalStorageBackendFallbackBases().some((item) => normalizeExtractBase(item))) return true;
    return false;
};

const shouldPreferRelativeExtractCandidate = (preferredBase = ''): boolean => {
    if (typeof window === 'undefined') return true;
    if (isLocalExtractRuntime()) return true;
    return !hasConfiguredExtractBaseCandidates(preferredBase);
};

const buildExtractBaseCandidates = (preferredBase = ''): string[] => {
    const out: string[] = [];
    const push = (raw: string) => {
        const base = normalizeExtractBase(raw);
        if (!base) return;
        if (shouldSkipExtractBaseCandidate(base)) return;
        if (!out.includes(base)) out.push(base);
    };

    push(preferredBase);
    push(getLocalStorageExtractBase());
    push(getViteExtractBase());
    getViteExtractFallbackBases().forEach((item) => push(item));
    getLocalStorageBackendFallbackBases().forEach((item) => push(item));
    // Only synthesize :3001 for loopback dev servers. Public/frp origins must
    // stay same-origin so browsers do not hit an unreachable cross-port API.
    push(buildLoopbackGatewayBaseCandidate());

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
        return '无法连接文档解析后端，请确认后端服务已启动（默认 3001 端口）或检查后端地址配置。';
    }
    return msg;
};

type ExtractAuthHeaders = Record<string, string>;

let extractAuthHeadersCache: ExtractAuthHeaders | null = null;
let extractAuthHeadersPromise: Promise<ExtractAuthHeaders> | null = null;

const resolveExtractAuthHeaders = async (): Promise<ExtractAuthHeaders> => {
    if (extractAuthHeadersCache) {
        return extractAuthHeadersCache;
    }
    if (extractAuthHeadersPromise) {
        return extractAuthHeadersPromise;
    }

    extractAuthHeadersPromise = (async () => {
        try {
            const payload = await getCurrentUser();
            const user = payload?.user;
            const userId = String(user?.id || '').trim();
            const tenantId = String(user?.tenantId || userId).trim();
            const headers: ExtractAuthHeaders = {};
            if (userId) {
                headers['X-Authenticated-User-Id'] = userId;
            }
            if (tenantId) {
                headers['X-Authenticated-Tenant-Id'] = tenantId;
                headers['X-Tenant-Id'] = tenantId;
            }
            extractAuthHeadersCache = headers;
            return headers;
        } catch {
            extractAuthHeadersCache = {};
            return {};
        } finally {
            extractAuthHeadersPromise = null;
        }
    })();

    return extractAuthHeadersPromise;
};

const withExtractAuthHeaders = async (init?: RequestInit): Promise<RequestInit> => {
    const mergedHeaders = new Headers(init?.headers || undefined);
    const authHeaders = await resolveExtractAuthHeaders();
    Object.entries(authHeaders).forEach(([key, value]) => {
        if (value && !mergedHeaders.has(key)) {
            mergedHeaders.set(key, value);
        }
    });
    return {
        ...(init || {}),
        headers: mergedHeaders,
    };
};

const isMissingExtractionJobMessage = (messageRaw: unknown): boolean => {
    const message = String(messageRaw || '').trim().toLowerCase();
    if (!message) return false;
    if (
        message.includes('没有到达文档解析后端')
        || message.includes('内网穿透')
        || message.includes('frp')
    ) {
        return false;
    }
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

type ResponseErrorInfo = {
    message: string;
    upstreamRouteMiss: boolean;
};

const isHtmlLikeErrorPayload = (value: string): boolean => {
    const normalized = String(value || '').trim().toLowerCase();
    return (
        normalized.startsWith('<!doctype')
        || normalized.startsWith('<html')
        || normalized.includes('<title>not found</title>')
        || normalized.includes('<body>')
    );
};

const isFrpRouteMissPayload = (value: string): boolean => {
    const normalized = String(value || '').toLowerCase();
    return normalized.includes('server is powered by') && normalized.includes('frp');
};

const isExtractHtmlRouteMissResponse = (response: Response, contentType: string, payload: string): boolean => {
    const normalizedType = String(contentType || '').toLowerCase();
    if (!normalizedType.includes('text/html')) return false;
    if (isHtmlLikeErrorPayload(payload)) return true;
    if (response.status === 404 || response.status >= 500) return true;
    return false;
};

const buildExtractRouteMissMessage = (response: Response): string => (
    `模块二请求没有到达文档解析后端（HTTP ${response.status}）。`
    + `请检查桌面端 API 地址、内网穿透或网关路由配置。请求地址：${response.url}`
);

const sanitizeExtractUiErrorMessage = (messageRaw: unknown): string => {
    const message = String(messageRaw || '').trim();
    if (!message) return '';
    if (isFrpRouteMissPayload(message) || isHtmlLikeErrorPayload(message)) {
        return '模块二请求没有到达文档解析后端。请检查桌面端 API 地址、内网穿透或网关路由配置。';
    }
    return message;
};

const sanitizeExtractUiErrorList = (errorsRaw: unknown): string[] => {
    const errors = Array.isArray(errorsRaw) ? errorsRaw : [errorsRaw];
    const messages = errors
        .map((item) => sanitizeExtractUiErrorMessage(item))
        .filter(Boolean);
    return Array.from(new Set(messages));
};

const formatExtractUiErrors = (errorsRaw: unknown): string => {
    return sanitizeExtractUiErrorList(errorsRaw).join(' | ');
};

const readResponseErrorInfo = async (response: Response): Promise<ResponseErrorInfo> => {
    let text = '';
    try {
        text = await response.text();
    } catch {
        text = '';
    }
    const trimmed = String(text || '').trim();
    if (!trimmed) {
        return { message: `状态码 ${response.status}`, upstreamRouteMiss: false };
    }

    const contentType = String(response.headers.get('content-type') || '').toLowerCase();
    if (
        isFrpRouteMissPayload(trimmed)
        || isExtractHtmlRouteMissResponse(response, contentType, trimmed)
        || isHtmlLikeErrorPayload(trimmed)
    ) {
        return {
            message: buildExtractRouteMissMessage(response),
            upstreamRouteMiss: true,
        };
    }

    try {
        const parsed = JSON.parse(trimmed);
        const detail = parsed?.detail || parsed?.message || parsed?.error;
        if (typeof detail === 'string' && detail.trim()) {
            return { message: detail.trim(), upstreamRouteMiss: false };
        }
    } catch {
        // non-json payload
    }
    return {
        message: trimmed.length > 1800 ? `${trimmed.slice(0, 1800)}...` : trimmed,
        upstreamRouteMiss: false,
    };
};

const readResponseErrorMessage = async (response: Response): Promise<string> => {
    const info = await readResponseErrorInfo(response);
    return info.message;
};

const fetchExtractWithFallback = async (
    path: string,
    init?: RequestInit,
    preferredBase = '',
    options?: ExtractFetchFallbackOptions,
): Promise<ExtractFetchResult> => {
    const initWithHeaders = await withExtractAuthHeaders(init);
    const tried: string[] = [];
    let lastError = '';
    const retryNotFound = options?.retryNotFound !== false;
    const routeMissRetryAttempts = Math.max(
        0,
        Number.isFinite(Number(options?.routeMissRetryAttempts))
            ? Number(options?.routeMissRetryAttempts)
            : DEFAULT_EXTRACT_ROUTE_MISS_RETRY_ATTEMPTS,
    );
    const preferredCandidateRaw = normalizeExtractBase(preferredBase);
    const preferredCandidate = shouldSkipExtractBaseCandidate(preferredCandidateRaw) ? '' : preferredCandidateRaw;
    const relativeCandidate = shouldSkipRelativeExtractCandidate() ? null : '';
    const configuredCandidates = buildExtractBaseCandidates(preferredBase);
    const candidateOrder = shouldPreferRelativeExtractCandidate(preferredBase)
        ? [
            ...(preferredCandidate ? [preferredCandidate] : []),
            ...(relativeCandidate === null ? [] : [relativeCandidate]),
            ...configuredCandidates,
        ]
        : [
            ...(preferredCandidate ? [preferredCandidate] : []),
            ...configuredCandidates,
            ...(relativeCandidate === null ? [] : [relativeCandidate]),
        ];
    const candidates = Array.from(
        new Set(
            candidateOrder.filter((item): item is string => typeof item === 'string'),
        ),
    );

    for (const base of candidates) {
        if (tried.includes(base)) continue;
        tried.push(base);
        const url = joinExtractUrl(base, path);
        try {
            for (let routeMissAttempt = 0; routeMissAttempt <= routeMissRetryAttempts; routeMissAttempt += 1) {
                const response = await fetch(url, {
                    credentials: initWithHeaders.credentials ?? 'include',
                    ...initWithHeaders,
                });
                if (response.ok) {
                    return { response, usedBase: base };
                }

                const errorInfo = await readResponseErrorInfo(response);
                const msg = sanitizeExtractUiErrorMessage(errorInfo.message);
                if (errorInfo.upstreamRouteMiss && routeMissAttempt < routeMissRetryAttempts) {
                    lastError = msg || `状态码 ${response.status}`;
                    console.warn('module2 extract route miss, retrying request', {
                        path,
                        url,
                        status: response.status,
                        attempt: routeMissAttempt + 1,
                        maxAttempts: routeMissRetryAttempts,
                    });
                    await waitForExtractRetry(EXTRACT_ROUTE_MISS_RETRY_DELAY_MS * (routeMissAttempt + 1));
                    continue;
                }

                const retryableStatus =
                    response.status >= 500 ||
                    response.status === 401 ||
                    response.status === 403 ||
                    response.status === 410 ||
                    (retryNotFound && response.status === 404);
                const retryable = retryableStatus || errorInfo.upstreamRouteMiss;
                if (!retryable) {
                    throw new Error(msg);
                }
                lastError = msg || `状态码 ${response.status}`;
                break;
            }
        } catch (error) {
            lastError = sanitizeExtractUiErrorMessage(parseFetchErrorMessage(error));
        }
    }

    throw new Error(sanitizeExtractUiErrorMessage(lastError) || '文档解析后端请求失败。');
};

const fetchExtractAtBase = async (
    path: string,
    init?: RequestInit,
    base = '',
): Promise<ExtractFetchResult> => {
    const initWithHeaders = await withExtractAuthHeaders(init);
    const normalizedBase = normalizeExtractBase(base);
    const url = joinExtractUrl(normalizedBase, path);
    const response = await fetch(url, {
        credentials: initWithHeaders.credentials ?? 'include',
        ...initWithHeaders,
    });
    if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response));
    }
    return { response, usedBase: normalizedBase };
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
    if (objectType === 'chart') return 'chart';
    if (objectType === 'figure') return isTableLikeFigureTrace(hit) ? 'table' : 'image';
    return 'other';
};

const getTraceDisplayLabel = (hit: TraceHit): string => {
    const kind = getTraceDisplayKind(hit);
    if (kind === 'field') return '字段';
    if (kind === 'table') return '表格';
    if (kind === 'image') return '图片';
    if (kind === 'chart') return '数据可视化';
    return '其他';
};

const buildTraceGroups = (hits: TraceHit[]) => {
    const grouped = {
        table: [] as Array<{ hit: TraceHit; idx: number }>,
        image: [] as Array<{ hit: TraceHit; idx: number }>,
        chart: [] as Array<{ hit: TraceHit; idx: number }>,
        other: [] as Array<{ hit: TraceHit; idx: number }>,
    };

    hits.forEach((hit, idx) => {
        const kind = getTraceDisplayKind(hit);
        if (kind === 'table') {
            grouped.table.push({ hit, idx });
        } else if (kind === 'image') {
            grouped.image.push({ hit, idx });
        } else if (kind === 'chart') {
            grouped.chart.push({ hit, idx });
        } else {
            grouped.other.push({ hit, idx });
        }
    });

    return [
        { key: 'table', label: '表格', items: grouped.table },
        { key: 'image', label: '图片', items: grouped.image },
        { key: 'chart', label: '数据可视化', items: grouped.chart },
        { key: 'other', label: '其他', items: grouped.other },
    ].filter((group) => group.items.length > 0);
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
    const byFileDirect = String((hit as Record<string, unknown>).artifact_by_file_url || '').trim();
    if (byFileDirect) return normalizeExtractArtifactUrl(byFileDirect, '');
    const fileIdRoute = toArtifactRouteFromFileId((hit as Record<string, unknown>).artifact_file_id);
    if (fileIdRoute) return normalizeExtractArtifactUrl(fileIdRoute, '');
    const direct = String(hit.artifact_url || '').trim();
    if (direct) return normalizeExtractArtifactUrl(direct, '');
    return '';
};

const TRACE_BLOCKED_ARTIFACT_SOURCES = new Set(['pdf_roi_crop']);

const canRenderTraceArtifactImage = (artifactUrl: string, artifactSource: unknown): boolean => {
    if (!String(artifactUrl || '').trim()) return false;
    const sourceKey = String(artifactSource ?? '').trim().toLowerCase();
    return !TRACE_BLOCKED_ARTIFACT_SOURCES.has(sourceKey);
};

const canShowTraceArtifactSource = (artifactSource: unknown): boolean => {
    const sourceKey = String(artifactSource ?? '').trim().toLowerCase();
    return Boolean(sourceKey) && !TRACE_BLOCKED_ARTIFACT_SOURCES.has(sourceKey);
};

const normalizeDocumentArtifactLinks = (doc: DocumentResult, usedBase: string): DocumentResult => {
    const normalizedTraceHits = Array.isArray(doc.trace_hits)
        ? doc.trace_hits.map((hit) => {
            const byFileRaw = String((hit as Record<string, unknown>)?.artifact_by_file_url || '').trim();
            const normalizedArtifactUrl = normalizeExtractArtifactUrl(
                String(hit?.artifact_url || '').trim(),
                usedBase,
            );
            return {
                ...hit,
                artifact_by_file_url:
                    normalizeExtractArtifactUrl(byFileRaw, usedBase)
                    || byFileRaw
                    || undefined,
                artifact_url: normalizedArtifactUrl || undefined,
                artifact_path: undefined,
            };
        })
        : doc.trace_hits;

    const diagnosticsRaw =
        doc.diagnostics && typeof doc.diagnostics === 'object'
            ? (doc.diagnostics as Record<string, unknown>)
            : null;
    const normalizedDiagnostics = diagnosticsRaw
        ? Object.fromEntries(
            Object.entries(diagnosticsRaw).map(([key, value]) => {
                if (!/_url$/i.test(key) || typeof value !== 'string') {
                    return [key, value];
                }
                const normalized = normalizeExtractArtifactUrl(String(value || '').trim(), usedBase);
                return [key, normalized || ''];
            }),
        )
        : doc.diagnostics;

    return {
        ...doc,
        errors: sanitizeExtractUiErrorList(doc.errors),
        soft_warnings: sanitizeExtractUiErrorList(doc.soft_warnings),
        trace_hits: normalizedTraceHits,
        diagnostics: normalizedDiagnostics,
    };
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

const scoreTraceDataframePayload = (payload: TraceDataframePayload): number => {
    const headerCount = payload.headers.length;
    const rowCount = payload.rows.length;
    const colCount = Math.max(payload.colCount, ...payload.rows.map((row) => row.length), headerCount, 0);
    const nonEmptyCellCount = payload.rows.reduce(
        (count, row) => count + row.filter((cell) => String(cell || '').trim().length > 0).length,
        0,
    );
    return (rowCount * 10_000) + (colCount * 100) + (headerCount * 10) + nonEmptyCellCount;
};

const pickBestTraceDataframePayload = (...values: unknown[]): TraceDataframePayload => {
    let bestPayload = toTraceDataframePayload(null);
    let bestScore = -1;

    values.forEach((value) => {
        const candidate = toTraceDataframePayload(value);
        const score = scoreTraceDataframePayload(candidate);
        if (score > bestScore) {
            bestPayload = candidate;
            bestScore = score;
        }
    });

    return bestPayload;
};

const TRACE_SOURCE_LABELS: Record<string, string> = {
    pdf_mineru: 'PDF MinerU',
    pdf_roi_crop: 'PDF 页面裁剪',
    artifact_output: '解析产物图像',
    docx_chart_xml: 'DOCX 图表结构产物',
    docx_media: 'DOCX 媒体产物',
    docx_media_vision: 'DOCX 媒体视觉解析产物',
    vision: 'Vision',
    vision_figure: 'Vision 图表解析',
    vision_table: 'Vision 表格解析',
    table_structured: '结构化表格抽取',
    xlsx_chart_spec: '工作表可视化规格',
    model: 'Vision 数据恢复',
    key_values: 'Vision 关键值恢复',
    text_blocks: 'Vision 文本恢复',
    docx_chart_xml_merge: 'DOCX 图表结构合并',
};

const toTraceSourceLabel = (value: unknown): string => {
    const key = String(value ?? '').trim().toLowerCase();
    if (!key) return '';
    return TRACE_SOURCE_LABELS[key] || String(value ?? '').trim();
};

const toPositiveRoundedInt = (value: unknown): number => {
    const raw = Number(value ?? 0);
    return Number.isFinite(raw) && raw > 0 ? Math.round(raw) : 0;
};

const toRecord = (value: unknown): Record<string, unknown> =>
    isPlainRecord(value) ? value : {};

const toTraceChartSpec = (value: unknown): XlsxTraceChartSpec | null => {
    if (!isPlainRecord(value)) return null;
    const chartType = String(value.chart_type || '').trim().toLowerCase();
    if (!chartType) return null;
    const titleZh = String(value.title_zh || '').trim();
    const title = String(value.title || '').trim();
    const descriptionZh = String(value.description_zh || '').trim();
    const description = String(value.description || '').trim();
    const trendSummaryZh = String(value.trend_summary_zh || '').trim();
    const trendSummary = String(value.trend_summary || '').trim();
    return {
        chart_type: chartType,
        title: titleZh || title,
        title_zh: titleZh,
        description: descriptionZh || description,
        description_zh: descriptionZh,
        trend_summary: trendSummaryZh || trendSummary,
        trend_summary_zh: trendSummaryZh,
        x_field: String(value.x_field || '').trim(),
        y_fields: Array.isArray(value.y_fields)
            ? value.y_fields.map((item) => String(item || '').trim()).filter(Boolean)
            : [],
        x_axis_label: String(value.x_axis_label || '').trim(),
        y_axis_label: String(value.y_axis_label || '').trim(),
        x_values: Array.isArray(value.x_values)
            ? value.x_values.map((item) => String(item || '').trim())
            : [],
        series: Array.isArray(value.series)
            ? value.series
                .map((item) => {
                    if (!isPlainRecord(item)) return null;
                    const name = String(item.name || '').trim();
                    const data = Array.isArray(item.data) ? item.data.map((cell) => Number(cell)).filter((cell) => Number.isFinite(cell)) : [];
                    if (!name || data.length === 0) return null;
                    return { name, data };
                })
                .filter((item): item is { name: string; data: number[] } => !!item)
            : [],
        points: Array.isArray(value.points)
            ? value.points
                .map((item) => {
                    if (!Array.isArray(item) || item.length < 2) return null;
                    const x = Number(item[0]);
                    const y = Number(item[1]);
                    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
                    return [x, y] as [number, number];
                })
                .filter((item): item is [number, number] => !!item)
            : [],
        point_count: Number(value.point_count || 0),
        aggregation: String(value.aggregation || '').trim(),
    };
};

const toPositiveRoundedArrayMax = (value: unknown): number => {
    if (!Array.isArray(value)) return 0;
    return value.reduce((maxValue, item) => Math.max(maxValue, toPositiveRoundedInt(item)), 0);
};

const readDiagnosticPdfPageCount = (diagnosticsRaw: unknown): number => {
    const diagnostics = toRecord(diagnosticsRaw);
    const parseStats = toRecord(diagnostics.parse_stats);
    const visualRuntimeLimits = toRecord(parseStats.visual_runtime_limits || diagnostics.visual_runtime_limits);
    const mineruRun = toRecord(parseStats.mineru_run);

    return Math.max(
        toPositiveRoundedInt(diagnostics.page_count),
        toPositiveRoundedInt(diagnostics.visual_page_count),
        toPositiveRoundedInt(diagnostics.pdf_page_count),
        toPositiveRoundedInt(diagnostics.total_pages),
        toPositiveRoundedInt(parseStats.page_count),
        toPositiveRoundedInt(parseStats.visual_page_count),
        toPositiveRoundedInt(parseStats.visual_probe_pages),
        toPositiveRoundedInt(parseStats.pdf_page_count),
        toPositiveRoundedInt(visualRuntimeLimits.page_count),
        toPositiveRoundedInt(visualRuntimeLimits.total_pages),
        toPositiveRoundedInt(mineruRun.end_page),
        toPositiveRoundedArrayMax(diagnostics.trace_pages),
        toPositiveRoundedArrayMax(diagnostics.figure_pages),
        toPositiveRoundedArrayMax(parseStats.trace_pages),
        toPositiveRoundedArrayMax(parseStats.figure_pages),
    );
};

const XLSX_WORKBOOK_BUILD_MODE_LABELS: Record<string, string> = {
    openpyxl_data_only: 'openpyxl 只读值',
    zip_xml: 'ZIP/XML 直读',
    openpyxl_formula: 'openpyxl 公式回退',
    unavailable: '未获取到完整工作簿',
};

const formatCompactInt = (value: number): string => {
    const safeValue = Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
    return safeValue.toLocaleString('zh-CN');
};

export const DeepReadWorkbench: React.FC<{ isSidebarCollapsed?: boolean }> = ({ isSidebarCollapsed = false }) => {
    const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
    const [schemaText] = useState<string>(JSON.stringify(DEFAULT_SCHEMA, null, 2));
    const [documents, setDocuments] = useState<DocumentResult[]>([]);
    const [activeDocIndex, setActiveDocIndex] = useState(0);
    const [activeFieldKey, setActiveFieldKey] = useState<string | null>(null);
    const [hoveredFieldKey, setHoveredFieldKey] = useState<string | null>(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [extractionJob, setExtractionJob] = useState<RuntimeExtractionJobState | null>(null);
    const [progressNowMs, setProgressNowMs] = useState<number>(() => Date.now());
    const [selectedFileArtifacts, setSelectedFileArtifacts] = useState<Record<string, SelectedFileArtifactRef>>({});
    const [sessionHydrated, setSessionHydrated] = useState(() => {
        if (typeof window === 'undefined') return false;
        const session = readWorkbenchSession();
        if (!session) return true;
        const restorable = (session.selectedFiles || []).filter((item) => hasRestorableArtifactRef(item));
        return restorable.length === 0;
    });
    const [sessionRestorePending, setSessionRestorePending] = useState(() => {
        if (typeof window === 'undefined') return false;
        const session = readWorkbenchSession();
        if (!session) return false;
        const restorable = (session.selectedFiles || []).filter((item) => hasRestorableArtifactRef(item));
        return restorable.length > 0;
    });
    const [errorMessage, setErrorMessage] = useState('');
    const [pendingRemoveFile, setPendingRemoveFile] = useState<{
        index: number;
        fileName: string;
        message: string;
    } | null>(null);
    const [infoMessage, setInfoMessage] = useState("每批最多上传 5 个文件。");
    const [activeSummaryText, setActiveSummaryText] = useState('');
    const [activeSummaryLoading, setActiveSummaryLoading] = useState(false);
    const [isSummaryExpanded, setIsSummaryExpanded] = useState(true);
    const [summaryDocName, setSummaryDocName] = useState('');
    const [graphSyncState, setGraphSyncState] = useState<GraphSyncUiState>('idle');
    const [graphSyncMessage, setGraphSyncMessage] = useState('');
    const [traceHits, setTraceHits] = useState<TraceHit[]>([]);
    const [traceLoading, setTraceLoading] = useState(false);
    const [traceError, setTraceError] = useState('');
    const [tracePanelOpen, setTracePanelOpen] = useState(false);
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
    const [showAssistantHelp, setShowAssistantHelp] = useState(false);
    const [isPreviewFocused, setIsPreviewFocused] = useState(false);
    const [isLeftQueueDrawerOpen, setIsLeftQueueDrawerOpen] = useState(false);
    const [isUploaderDragOver, setIsUploaderDragOver] = useState(false);
    const [resultSearchQuery, setResultSearchQuery] = useState('');
    const [paneLayout, setPaneLayout] = useState<WorkbenchPaneLayout>(() => readWorkbenchPaneLayout());
    const [paneResizeSide, setPaneResizeSide] = useState<PaneResizeSide | null>(null);
    const [workbenchViewportWidth, setWorkbenchViewportWidth] = useState(0);
    const prefersReducedMotion = useReducedMotion();

    // Viewport Controls
    const [scale, setScale] = useState(1);
    const [rotation, setRotation] = useState(0);
    const [pdfViewMode, setPdfViewMode] = useState<PdfViewMode>('fit-width');
    const [activeTraceKey, setActiveTraceKey] = useState('');

    const fileInputRef = useRef<HTMLInputElement>(null);
    const assistantInputRef = useRef<HTMLTextAreaElement>(null);
    const textPreviewRef = useRef<HTMLDivElement>(null);
    const assistantDialogRef = useRef<HTMLDivElement>(null);
    const workbenchViewportRef = useRef<HTMLDivElement>(null);
    const selectedFilesRef = useRef<File[]>([]);
    const documentsRef = useRef<DocumentResult[]>([]);
    const activeDocRef = useRef<DocumentResult | null>(null);
    const activeDocIndexRef = useRef(0);
    const extractionJobStateRef = useRef<RuntimeExtractionJobState | null>(null);
    const suppressedExtractionJobFilesRef = useRef<Record<string, Set<string>>>({});
    const summaryRequestSeqRef = useRef(0);
    const traceRequestSeqRef = useRef(0);
    const graphSyncPollRunIdRef = useRef(0);
    const officePreviewMapRef = useRef<Record<string, OfficePreviewState>>({});
    const officePreviewPollRef = useRef<Record<string, string>>({});
    const officePreviewApiBaseRef = useRef<Record<string, string>>({});
    const extractionJobPollRef = useRef<string>('');
    const extractionJobPollRunIdRef = useRef(0);
    const extractionJobApiBaseRef = useRef<string>('');
    const terminalJobResyncRef = useRef<string>('');
    const restoredSessionJobIdRef = useRef<string>('');
    const persistedSelectedFilesRef = useRef<PersistedWorkbenchFile[]>([]);
    const assistantAbortRef = useRef<AbortController | null>(null);
    const paneResizeFrameRef = useRef<number | null>(null);
    const paneResizeLatestXRef = useRef<number | null>(null);
    const paneResizeStartRef = useRef<{
        clientX: number;
        leftWidth: number;
        rightWidth: number;
        side: PaneResizeSide;
    } | null>(null);
    const paneLayoutStageRef = useRef<PaneLayoutStage | null>(null);
    const standardPaneLayoutRef = useRef<WorkbenchPaneLayout | null>(null);
    const textPaneLayoutRef = useRef<WorkbenchPaneLayout | null>(null);

    useEffect(() => {
        extractionJobStateRef.current = extractionJob;
    }, [extractionJob]);

    useEffect(() => {
        selectedFilesRef.current = selectedFiles;
    }, [selectedFiles]);

    useEffect(() => {
        if (typeof window === 'undefined') return undefined;
        setProgressNowMs(Date.now());
        if (!extractionJob || extractionJob.terminal) {
            return undefined;
        }
        const timer = window.setInterval(() => {
            setProgressNowMs(Date.now());
        }, 120);
        return () => window.clearInterval(timer);
    }, [
        extractionJob?.job_id,
        extractionJob?.terminal,
        extractionJob?.progress?.current_stage,
        extractionJob?.progress?.current_file_name,
    ]);

    useEffect(() => {
        documentsRef.current = documents;
    }, [documents]);

    const getSuppressedExtractionJobFileKeys = (jobId: string): Set<string> => {
        const normalizedJobId = normalizeExtractionJobId(jobId);
        if (!normalizedJobId) {
            return new Set<string>();
        }
        const existing = suppressedExtractionJobFilesRef.current[normalizedJobId];
        if (existing) {
            return existing;
        }
        const created = new Set<string>();
        suppressedExtractionJobFilesRef.current[normalizedJobId] = created;
        return created;
    };

    const requestCancelExtractionJobFile = async (
        jobId: string,
        fileHash: string,
        fileName: string,
        preferredBase = '',
    ): Promise<void> => {
        const normalizedJobId = normalizeExtractionJobId(jobId);
        if (!normalizedJobId || (!String(fileHash || '').trim() && !String(fileName || '').trim())) {
            return;
        }
        const lockedBase = preferredBase || extractionJobApiBaseRef.current || '';
        const fetchResult = await fetchExtractAtBase(
            `/extract/jobs/${encodeURIComponent(normalizedJobId)}/cancel-file`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    file_hash: String(fileHash || '').trim(),
                    file_name: String(fileName || '').trim(),
                }),
            },
            lockedBase,
        );
        extractionJobApiBaseRef.current = fetchResult.usedBase || lockedBase || extractionJobApiBaseRef.current || '';
    };

    const suppressAndCancelJobFile = (
        job: RuntimeExtractionJobState | null,
        file: File,
        index: number,
        preferredBase = '',
    ): string => {
        const normalizedJobId = normalizeExtractionJobId(job?.job_id);
        if (!job || !normalizedJobId || job.terminal) {
            return '';
        }
        const jobFile = pickExtractionJobFileState(job, file, index);
        if (!jobFile) {
            return '';
        }
        const fileKey = buildExtractionJobServerFileKey(jobFile.file_hash, jobFile.file_name);
        if (!fileKey) {
            return '';
        }
        const suppressedKeys = getSuppressedExtractionJobFileKeys(normalizedJobId);
        if (!suppressedKeys.has(fileKey)) {
            suppressedKeys.add(fileKey);
            const status = String(jobFile.status || '').trim().toLowerCase();
            if (!['completed', 'failed', 'cancelled'].includes(status)) {
                void requestCancelExtractionJobFile(
                    normalizedJobId,
                    String(jobFile.file_hash || '').trim(),
                    String(jobFile.file_name || '').trim(),
                    preferredBase || extractionJobApiBaseRef.current || '',
                ).catch((error) => {
                    console.warn('module2 cancel file failed', error);
                });
            }
        }
        return fileKey;
    };

    const reconcileVisibleExtractionJob = (
        job: RuntimeExtractionJobState | null,
        preferredBase = '',
    ): RuntimeExtractionJobState | null => {
        const normalizedJobId = normalizeExtractionJobId(job?.job_id);
        if (!job || !normalizedJobId) {
            return job;
        }
        const suppressedKeys = getSuppressedExtractionJobFileKeys(normalizedJobId);
        const hiddenFiles = collectHiddenExtractionJobFiles(job, selectedFilesRef.current, suppressedKeys);
        hiddenFiles.forEach((item) => {
            const fileKey = buildExtractionJobServerFileKey(item.file_hash, item.file_name);
            if (!fileKey || suppressedKeys.has(fileKey)) {
                return;
            }
            suppressedKeys.add(fileKey);
            const status = String(item.status || '').trim().toLowerCase();
            if (!['completed', 'failed', 'cancelled'].includes(status)) {
                void requestCancelExtractionJobFile(
                    normalizedJobId,
                    String(item.file_hash || '').trim(),
                    String(item.file_name || '').trim(),
                    preferredBase || extractionJobApiBaseRef.current || '',
                ).catch((error) => {
                    console.warn('module2 cancel hidden file failed', error);
                });
            }
        });
        return filterVisibleRuntimeExtractionJob(job, selectedFilesRef.current, suppressedKeys);
    };

    const activeSourceFile = useMemo(() => {
        if (selectedFiles.length > 0) {
            return selectedFiles[activeDocIndex] || selectedFiles[0];
        }

        const fallbackDoc = documents[activeDocIndex] || documents[0] || null;
        if (fallbackDoc) {
            const normalizedName = normalizeWorkbenchFileName(fallbackDoc.file_name);
            return selectedFiles.find((file) => normalizeWorkbenchFileName(file.name) === normalizedName) || null;
        }

        return null;
    }, [activeDocIndex, documents, selectedFiles]);
    const activeSourceFileIndex = useMemo(() => {
        if (!activeSourceFile) return -1;
        const targetKey = fileIdentityKey(activeSourceFile);
        return selectedFiles.findIndex((file) => fileIdentityKey(file) === targetKey);
    }, [activeSourceFile, selectedFiles]);
    const activeDoc = useMemo(
        () => (
            activeSourceFile
                ? pickDocumentResultForFile(
                    documents,
                    activeSourceFile,
                    activeSourceFileIndex >= 0 ? activeSourceFileIndex : activeDocIndex,
                )
                : documents[activeDocIndex] || documents[0] || null
        ),
        [activeDocIndex, activeSourceFile, activeSourceFileIndex, documents],
    );
    useEffect(() => {
        activeDocRef.current = activeDoc;
        activeDocIndexRef.current = activeDocIndex;
    }, [activeDoc, activeDocIndex]);
    const highlightedFieldKey = hoveredFieldKey || activeFieldKey;
    const activeAssistantSessionKey = String(activeDoc?.file_hash || '').trim() || GENERIC_ASSISTANT_SESSION_KEY;
    const activeExtractionJobFile = useMemo(
        () => (
            activeSourceFile
                ? pickExtractionJobFileState(
                    extractionJob,
                    activeSourceFile,
                    activeSourceFileIndex >= 0 ? activeSourceFileIndex : activeDocIndex,
                )
                : null
        ),
        [activeDocIndex, activeSourceFile, activeSourceFileIndex, extractionJob],
    );
    const activeParsedDocument = useMemo(
        () => (
            activeSourceFile
                ? pickDocumentResultForFile(
                    documents,
                    activeSourceFile,
                    activeSourceFileIndex >= 0 ? activeSourceFileIndex : activeDocIndex,
                )
                : activeDoc
        ),
        [activeDoc, activeDocIndex, activeSourceFile, activeSourceFileIndex, documents],
    );
    const activeExtractionJobFileRatio = estimateRuntimeExtractionFileRatio(
        extractionJob,
        activeExtractionJobFile,
        progressNowMs,
    );
    const activeExtractionJobFilePercentLabel = formatProgressPercent(
        activeExtractionJobFileRatio,
        extractionJob?.terminal ? 0 : 1,
    );
    const activeExtractionJobFileStageLabel = toExtractionStageLabel(activeExtractionJobFile?.stage);
    const showActiveExtractionPreviewStatus = Boolean(
        activeExtractionJobFile && (!activeDoc || !extractionJob?.terminal),
    );
    const resolvedInfoMessage = useMemo(() => {
        if (extractionJob && !extractionJob.terminal) {
            const liveMessage = buildExtractionInfoMessage(extractionJob, progressNowMs, false);
            const normalizedInfoMessage = String(infoMessage || '').trim();
            if (
                !normalizedInfoMessage
                || normalizedInfoMessage === '正在同步最新解析进度...'
                || normalizedInfoMessage.startsWith('正在处理')
                || normalizedInfoMessage.startsWith('已提交任务')
            ) {
                return liveMessage;
            }
        }
        return infoMessage;
    }, [extractionJob, infoMessage, progressNowMs]);
    const activeExt = activeSourceFile ? fileExt(activeSourceFile.name) : (activeDoc ? fileExt(activeDoc.file_name) : '');
    const activeDisplayName = activeDoc?.file_name || activeSourceFile?.name || '当前文档';
    const activeSelectionCount = Math.max(documents.length, selectedFiles.length);
    const graphSyncSupported = Boolean(activeDoc && GRAPH_SYNC_SUPPORTED_EXTENSIONS.has(activeExt));
    const graphSyncExcluded = GRAPH_SYNC_EXCLUDED_EXTENSIONS.has(activeExt);
    const graphSyncDisabled = !graphSyncSupported || isProcessing || Boolean(activeDoc?.errors?.length);
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);
    const [previewText, setPreviewText] = useState<string>('');
    const [officePreviewMap, setOfficePreviewMap] = useState<Record<string, OfficePreviewState>>({});
    useEffect(() => {
        officePreviewMapRef.current = officePreviewMap;
    }, [officePreviewMap]);
    const [pdfViewportPage, setPdfViewportPage] = useState(1);
    const [pdfScrollRequest, setPdfScrollRequest] = useState<PdfScrollRequest | null>(null);
    const [pdfPreviewPageCount, setPdfPreviewPageCount] = useState(1);
    const assistantActionable = useMemo(
        () => Boolean(activeDoc && (((activeDoc.errors?.length || 0) > 0) || getDisplaySoftWarnings(activeDoc).length > 0)),
        [activeDoc]
    );
    const shouldUseLeftQueueDrawer = selectedFiles.length > 0
        && workbenchViewportWidth > 0
        && workbenchViewportWidth <= MODULE2_LEFT_DRAWER_BREAKPOINT;
    const showLeftPanel = !isPreviewFocused && !shouldUseLeftQueueDrawer;
    const showLeftQueueDrawer = shouldUseLeftQueueDrawer && isLeftQueueDrawerOpen && selectedFiles.length > 0;
    const isTextPreviewStage = ['txt', 'md'].includes(activeExt);
    const currentPaneLayoutStage: PaneLayoutStage = isTextPreviewStage ? 'text' : 'default';
    const resolvePaneLayoutViewportWidth = () => (
        workbenchViewportWidth > 0
            ? workbenchViewportWidth
            : (typeof window === 'undefined' ? 0 : window.innerWidth)
    );

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
        if (selectedFiles.length === 0) {
            paneLayoutStageRef.current = null;
            return;
        }

        const viewportWidth = resolvePaneLayoutViewportWidth();
        const nextStage = currentPaneLayoutStage;

        if (paneLayoutStageRef.current === null) {
            paneLayoutStageRef.current = nextStage;
            if (nextStage === 'text') {
                const nextLayout = clampWorkbenchPaneLayout(
                    textPaneLayoutRef.current || resolveWorkbenchPaneLayoutDefaults(viewportWidth, 'text'),
                    viewportWidth,
                    showLeftPanel,
                );
                setPaneLayout((prev) => (
                    prev.leftWidth === nextLayout.leftWidth && prev.rightWidth === nextLayout.rightWidth
                        ? prev
                        : nextLayout
                ));
            }
            return;
        }

        if (paneLayoutStageRef.current === nextStage) return;

        if (paneLayoutStageRef.current === 'text') {
            textPaneLayoutRef.current = paneLayout;
        } else {
            standardPaneLayoutRef.current = paneLayout;
        }

        paneLayoutStageRef.current = nextStage;
        const restoredLayout = nextStage === 'text'
            ? (textPaneLayoutRef.current || resolveWorkbenchPaneLayoutDefaults(viewportWidth, 'text'))
            : (standardPaneLayoutRef.current || resolveWorkbenchPaneLayoutDefaults(viewportWidth, 'default'));
        const nextLayout = clampWorkbenchPaneLayout(restoredLayout, viewportWidth, showLeftPanel);
        setPaneLayout((prev) => (
            prev.leftWidth === nextLayout.leftWidth && prev.rightWidth === nextLayout.rightWidth
                ? prev
                : nextLayout
        ));
    }, [
        currentPaneLayoutStage,
        paneLayout,
        selectedFiles.length,
        showLeftPanel,
        workbenchViewportWidth,
    ]);

    useEffect(() => {
        if (selectedFiles.length === 0) return;
        if (currentPaneLayoutStage === 'text') {
            textPaneLayoutRef.current = paneLayout;
            return;
        }
        standardPaneLayoutRef.current = paneLayout;
    }, [
        currentPaneLayoutStage,
        paneLayout.leftWidth,
        paneLayout.rightWidth,
        selectedFiles.length,
    ]);

    useEffect(() => {
        if (!workbenchViewportWidth) return;
        setPaneLayout((prev) => {
            const next = clampWorkbenchPaneLayout(prev, workbenchViewportWidth, showLeftPanel);
            return prev.leftWidth === next.leftWidth && prev.rightWidth === next.rightWidth ? prev : next;
        });
    }, [showLeftPanel, workbenchViewportWidth]);

    useEffect(() => {
        if (selectedFiles.length === 0 && isLeftQueueDrawerOpen) {
            setIsLeftQueueDrawerOpen(false);
            return;
        }
        if (!shouldUseLeftQueueDrawer && isLeftQueueDrawerOpen) {
            setIsLeftQueueDrawerOpen(false);
        }
    }, [isLeftQueueDrawerOpen, selectedFiles.length, shouldUseLeftQueueDrawer]);

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
        const diagnostics = toRecord(activeDoc?.diagnostics);
        const byFileResolved = resolveByFileArtifactUrl(
            {
                artifact_by_file_url: String(
                    diagnostics.office_pdf_preview_by_file_url
                    || diagnostics.pdf_preview_by_file_url
                    || ''
                ).trim(),
                artifact_file_id: String(
                    diagnostics.office_pdf_preview_file_id
                    || diagnostics.pdf_preview_file_id
                    || ''
                ).trim(),
            },
            '',
        );
        if (byFileResolved) return byFileResolved;
        const directRaw = String(
            diagnostics.office_pdf_preview_url
            || diagnostics.pdf_preview_url
            || ''
        ).trim();
        if (!directRaw) return '';
        return normalizeExtractArtifactUrl(directRaw, '') || '';
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
    const xlsxWorkbookOverview = useMemo(() => {
        if (activeRenderExt !== 'xlsx' || !activeDoc) return null;
        const diagnostics = toRecord(activeDoc.diagnostics);
        const buildModeKey = String(diagnostics.xlsx_workbook_build_mode || '').trim().toLowerCase();
        const buildModeLabel = XLSX_WORKBOOK_BUILD_MODE_LABELS[buildModeKey]
            || String(diagnostics.xlsx_workbook_build_mode || '').trim()
            || '未标注';
        const artifactVersion = String(diagnostics.xlsx_sheet_rows_artifact_version || '').trim();
        const workbookManifestUrl = String(diagnostics.xlsx_workbook_manifest_url || '').trim();
        const fieldArtifactUrl = String(diagnostics.field_results_artifact_url || '').trim();
        const fieldArtifactCount = toPositiveRoundedInt(diagnostics.field_results_artifact_count);
        return {
            metrics: [
                {
                    key: 'sheet_count',
                    label: '工作表',
                    value: formatCompactInt(toPositiveRoundedInt(diagnostics.xlsx_source_sheet_count)),
                },
                {
                    key: 'total_rows',
                    label: '总行数',
                    value: formatCompactInt(toPositiveRoundedInt(diagnostics.xlsx_source_total_rows)),
                },
                {
                    key: 'total_cols',
                    label: '总列数',
                    value: formatCompactInt(toPositiveRoundedInt(diagnostics.xlsx_source_total_cols)),
                },
                {
                    key: 'nonempty_rows',
                    label: '非空行',
                    value: formatCompactInt(toPositiveRoundedInt(diagnostics.xlsx_source_total_nonempty_rows)),
                },
                {
                    key: 'nonempty_cells',
                    label: '非空单元格',
                    value: formatCompactInt(toPositiveRoundedInt(diagnostics.xlsx_source_total_nonempty_cells)),
                },
            ],
            buildModeLabel,
            artifactVersion,
            workbookManifestUrl,
            fieldArtifactUrl,
            fieldArtifactCount,
        };
    }, [activeDoc, activeRenderExt]);
    const diagnosticPdfPageCount = useMemo(() => {
        if (activeRenderExt !== 'pdf') return 0;
        return readDiagnosticPdfPageCount(activeDoc?.diagnostics);
    }, [activeDoc?.diagnostics, activeRenderExt]);
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
    const latestStreamingAssistantMessage = useMemo(() => {
        for (let index = renderableAssistantDialog.length - 1; index >= 0; index -= 1) {
            const current = renderableAssistantDialog[index];
            if (
                current.role === 'assistant'
                && current.messageType === 'assistant_text'
                && current.status === 'streaming'
            ) {
                return current;
            }
        }
        return null;
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
            extractionJobPollRunIdRef.current += 1;
            extractionJobApiBaseRef.current = '';
            terminalJobResyncRef.current = '';
            restoredSessionJobIdRef.current = '';
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
        const sanitizedCached = cached.map((doc) => normalizeDocumentArtifactLinks(doc, ''));
        const safeCached = filterAutoRestorableExtractionDocuments(sanitizedCached);
        if (JSON.stringify(safeCached) !== JSON.stringify(cached)) {
            writeExtractionDocuments(safeCached);
        }
        const session = readWorkbenchSession();
        const sessionDocuments = safeCached.length === 0
            ? getSessionPersistedDocuments(session).map((doc) => normalizeDocumentArtifactLinks(doc, ''))
            : [];
        const restoredDocuments = safeCached.length > 0 ? safeCached : sessionDocuments;
        if (restoredDocuments.length > 0) {
            setDocuments(restoredDocuments);
            if (safeCached.length > 0) {
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
        restoredSessionJobIdRef.current = persistedJob ? normalizeExtractionJobId(persistedJob.job_id) : '';
        setActiveDocIndex(Math.max(0, Number(session.activeDocIndex || 0)));
        setSmartUnitTab(session.smartUnitTab === 'assistant' ? 'assistant' : 'results');
        setOfficePreviewMap(session.officePreviewMap || {});
        setExtractionJob(persistedJob);
        setIsProcessing(Boolean(persistedJob && !persistedJob.terminal));
        persistedSelectedFilesRef.current = Array.isArray(session.selectedFiles) ? session.selectedFiles : [];
        const artifactMap = Object.fromEntries(
            (session.selectedFiles || []).map((item) => [
                item.key,
                normalizeSelectedFileArtifactRef({
                    artifactByFileUrl: item.artifactByFileUrl,
                    artifactFileId: item.artifactFileId,
                    artifactUrl: item.artifactUrl,
                    artifactPath: item.artifactPath,
                }),
            ]),
        );
        setSelectedFileArtifacts(artifactMap);

        const restorable = (session.selectedFiles || []).filter((item) => hasRestorableArtifactRef(item));
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
            smartUnitTab,
            officePreviewMap,
            extractionJob,
            selectedFileArtifacts,
            persistedSelectedFilesRef.current,
        );
        persistedSelectedFilesRef.current = snapshot.selectedFiles;
        writeWorkbenchSession(snapshot);
    }, [activeDoc?.file_hash, activeDocIndex, documents.length, extractionJob, officePreviewMap, selectedFileArtifacts, selectedFiles, sessionHydrated, sessionRestorePending, smartUnitTab]);

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
        setPdfPreviewPageCount(Math.max(1, diagnosticPdfPageCount || 1));
    }, [activeRenderExt, diagnosticPdfPageCount, previewUrl]);

    useEffect(() => {
        if (!activePreviewIdentity) return;
        setScale(1);
        setRotation(0);
        setPdfViewMode('fit-width');
        setPdfViewportPage(1);
        setPdfScrollRequest(createPdfScrollRequest(1));
    }, [activePreviewIdentity]);

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

    useEffect(() => {
        if (!tracePanelOpen || !activeFieldKey) return;
        const normalizedFieldKey = String(activeFieldKey || '').trim().toLowerCase();
        const activeExists = activeTraceKey
            && traceHits.some((hit, idx) => toTraceHitKey(hit, idx) === activeTraceKey);
        if (activeExists) return;

        const preferredIndex = traceHits.findIndex(
            (hit) =>
                String(hit.object_type || '').trim().toLowerCase() === 'field'
                && String(hit.object_id || '').trim().toLowerCase() === normalizedFieldKey
        );
        const fallbackIndex = preferredIndex >= 0
            ? preferredIndex
            : traceHits.findIndex((hit) => getTraceDisplayKind(hit) !== 'field');

        if (fallbackIndex >= 0) {
            setActiveTraceKey(toTraceHitKey(traceHits[fallbackIndex], fallbackIndex));
            return;
        }

        setActiveTraceKey('');
    }, [activeFieldKey, activeTraceKey, traceHits, tracePanelOpen]);

    const previewHighlight = useMemo(() => {
        if (!['txt', 'md'].includes(activeExt)) return null;
        const sourceText = previewText || '';
        if (!sourceText) return null;
        const rawSnippet = String(activeTraceHit?.snippet || '').split('|')[0].trim();
        const fieldEntity = activeDoc && highlightedFieldKey ? activeDoc.result?.[highlightedFieldKey] : null;
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
    }, [activeExt, previewText, activeTraceHit, highlightedFieldKey, activeDoc]);

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
        graphSyncPollRunIdRef.current += 1;
        setGraphSyncState('idle');
        setGraphSyncMessage('');
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
            setActiveSummaryText(
                sanitizeExtractUiErrorMessage(payload.summary) || "暂无摘要。",
            );
        } catch (error) {
            if (seq !== summaryRequestSeqRef.current) return;
            const fallback = sanitizeExtractUiErrorMessage(doc.errors?.[0]);
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
        setTracePanelOpen(Boolean(fieldKey));
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

    const syncGraphRetryVisibility = async (
        doc: DocumentResult,
        expectedSourceBatchKey: string,
        previousJobId: string,
        previousBatchId: string,
        runId: number,
    ) => {
        const normalizedSourceBatchKey = String(expectedSourceBatchKey || '').trim();
        let activeJobId = '';
        let activeBatchId = '';
        let activeSourceBatchKey = normalizedSourceBatchKey;

        for (
            let attempt = 0;
            attempt < GRAPH_SYNC_DISCOVERY_MAX_ATTEMPTS + GRAPH_SYNC_ACTIVE_MAX_ATTEMPTS;
            attempt += 1
        ) {
            if (runId !== graphSyncPollRunIdRef.current) return;

            try {
                const detailPayload = await fetchModule4GraphFileDetail(doc.file_hash);
                const item = detailPayload.item;
                const metadata = item.metadata && typeof item.metadata === 'object'
                    ? item.metadata as Record<string, unknown>
                    : {};
                const currentJobId = String(item.current_job_id || activeJobId).trim();
                const graphStatus = String(item.status || '').trim().toLowerCase();
                const batchId = String(metadata.batch_id || activeBatchId).trim();
                const sourceBatchKey = String(metadata.source_batch_key || activeSourceBatchKey).trim();

                const matchedCurrentRetry = (
                    normalizedSourceBatchKey
                        ? sourceBatchKey === normalizedSourceBatchKey
                        : false
                )
                    || (!!batchId && batchId !== previousBatchId)
                    || (!!currentJobId && currentJobId !== previousJobId)
                    || (!!activeJobId && currentJobId === activeJobId);

                if (matchedCurrentRetry) {
                    activeJobId = currentJobId || activeJobId;
                    activeBatchId = batchId || activeBatchId;
                    activeSourceBatchKey = sourceBatchKey || activeSourceBatchKey;

                    let jobStatus = '';
                    let jobProgressLabel = '';
                    if (activeJobId) {
                        const jobPayload = await fetchModule4JobStatus(activeJobId, { statusOnly: true }).catch(() => null);
                        if (jobPayload) {
                            jobStatus = String(jobPayload.status || '').trim().toLowerCase();
                            jobProgressLabel = formatGraphSyncProgress(jobPayload.progress);
                        }
                    }

                    const messageParts = [
                        activeSourceBatchKey
                            ? `\u5df2\u63d0\u4ea4\u77e5\u8bc6\u56fe\u8c31\u6784\u5efa\u8bf7\u6c42\uff0c\u6279\u6b21 ${formatGraphSyncShortId(activeSourceBatchKey)}\u3002`
                            : '\u5df2\u63d0\u4ea4\u77e5\u8bc6\u56fe\u8c31\u6784\u5efa\u8bf7\u6c42\u3002',
                        activeJobId
                            ? `\u6a21\u5757\u56db\u4efb\u52a1 ${formatGraphSyncShortId(activeJobId, 12)}${jobStatus ? ` ${jobStatus}` : ''}${jobProgressLabel ? ` (${jobProgressLabel})` : ''}\u3002`
                            : '',
                        !activeJobId && activeBatchId
                            ? `\u6a21\u5757\u56db\u5df2\u63a5\u6536\u672c\u6b21\u8bf7\u6c42\uff0c\u5165\u56fe\u6279\u6b21 ${formatGraphSyncShortId(activeBatchId, 12)}\u3002`
                            : '',
                        graphStatus === 'ready'
                            ? '\u56fe\u8c31\u5df2\u5b8c\u6210\uff0c\u53ef\u524d\u5f80\u6a21\u5757\u56db\u67e5\u770b\u3002'
                            : graphStatus === 'failed'
                                ? '\u6a21\u5757\u56db\u5df2\u8bb0\u5f55\u5931\u8d25\u4efb\u52a1\uff0c\u8bf7\u524d\u5f80\u6a21\u5757\u56db\u67e5\u770b\u8be6\u60c5\u3002'
                                : '',
                    ].filter(Boolean);
                    /*
                    const messageParts = [
                        `已提交知识图谱构建请求，批次 ${formatGraphSyncShortId(normalizedSourceBatchKey)}。`,
                        currentJobId
                            ? `模块四任务 ${formatGraphSyncShortId(currentJobId, 12)}${jobStatus ? ` ${jobStatus}` : ''}${jobProgressLabel ? ` (${jobProgressLabel})` : ''}。`
                            : '',
                        !currentJobId && batchId
                            ? `模块四已接收本次请求，入图批次 ${formatGraphSyncShortId(batchId, 12)}。`
                            : '',
                        graphStatus === 'ready'
                            ? '图谱已完成，可前往模块四查看。'
                            : graphStatus === 'failed'
                                ? '模块四已记录失败任务，请前往模块四查看详情。'
                                : '',
                    ].filter(Boolean);
                    */
                    setGraphSyncMessage(messageParts.join(' '));

                    if (graphStatus === 'failed' || jobStatus === 'failed' || jobStatus === 'cancelled') {
                        setGraphSyncState('error');
                        return;
                    }

                    if (graphStatus === 'ready') {
                        setGraphSyncState('success');
                        return;
                    }
                }
            } catch {
                // Keep the optimistic submission message while module4 receives the new batch.
            }

            await waitForGraphSyncPoll(activeJobId ? GRAPH_SYNC_ACTIVE_POLL_MS : GRAPH_SYNC_DISCOVERY_POLL_MS);
        }
    };

    const requestGraphSync = async (doc: DocumentResult) => {
        if (!doc || !GRAPH_SYNC_SUPPORTED_EXTENSIONS.has(fileExt(doc.file_name))) {
            return;
        }
        const runId = graphSyncPollRunIdRef.current + 1;
        graphSyncPollRunIdRef.current = runId;
        setGraphSyncState('submitting');
        setGraphSyncMessage('');
        try {
            const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
            const previousDetail = await fetchModule4GraphFileDetail(doc.file_hash).catch(() => null);
            const previousItem = previousDetail?.item;
            const previousMetadata = previousItem?.metadata && typeof previousItem.metadata === 'object'
                ? previousItem.metadata as Record<string, unknown>
                : {};
            const previousJobId = String(previousItem?.current_job_id || '').trim();
            const previousBatchId = String(previousMetadata.batch_id || '').trim();
            const fetchResult = await fetchExtractWithFallback(
                '/extract/graph-sync',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        job_id: normalizeExtractionJobId(extractionJob?.job_id),
                        file_name: doc.file_name,
                        file_hash: doc.file_hash,
                        document: doc,
                    }),
                },
                preferredBase,
            );
            extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
            const response = fetchResult.response;
            if (!response.ok) {
                throw new Error(await readResponseErrorMessage(response));
            }
            const payload = await response.json().catch(() => ({} as Record<string, unknown>));
            const sourceBatchKey = String(payload?.source_batch_key || '').trim();
            setGraphSyncState('success');
            setGraphSyncMessage(
                sourceBatchKey
                    ? `\u5df2\u63d0\u4ea4\u77e5\u8bc6\u56fe\u8c31\u6784\u5efa\u8bf7\u6c42\uff0c\u6279\u6b21 ${formatGraphSyncShortId(sourceBatchKey)}\uff0c\u6b63\u5728\u7b49\u5f85\u6a21\u5757\u56db\u63a5\u6536\u3002`
                    : String(payload?.message || '').trim()
                        || '\u5df2\u63d0\u4ea4\u77e5\u8bc6\u56fe\u8c31\u6784\u5efa\u8bf7\u6c42\uff0c\u6b63\u5728\u7b49\u5f85\u6a21\u5757\u56db\u63a5\u6536\u3002'
            );
            void syncGraphRetryVisibility(doc, sourceBatchKey, previousJobId, previousBatchId, runId);
        } catch (error) {
            setGraphSyncState('error');
            setGraphSyncMessage(
                error instanceof Error
                    ? error.message
                    : '\u77e5\u8bc6\u56fe\u8c31\u6784\u5efa\u63d0\u4ea4\u5931\u8d25'
            );
        }
    };
    /*
    const requestGraphSync = async (doc: DocumentResult) => {
        if (!doc || !GRAPH_SYNC_SUPPORTED_EXTENSIONS.has(fileExt(doc.file_name))) {
            return;
        }
        setGraphSyncState('submitting');
        setGraphSyncMessage('');
        try {
            const preferredBase = extractionJobApiBaseRef.current || resolveExtractBase();
            const fetchResult = await fetchExtractWithFallback(
                '/extract/graph-sync',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        job_id: normalizeExtractionJobId(extractionJob?.job_id),
                        file_name: doc.file_name,
                        file_hash: doc.file_hash,
                        document: doc,
                    }),
                },
                preferredBase,
            );
            extractionJobApiBaseRef.current = fetchResult.usedBase || preferredBase;
            const response = fetchResult.response;
            if (!response.ok) {
                throw new Error(await readResponseErrorMessage(response));
            }
            const payload = await response.json().catch(() => ({} as Record<string, unknown>));
            setGraphSyncState('success');
            setGraphSyncMessage(
                String(payload?.message || '').trim()
                || '已提交知识图谱构建请求，请前往模块四查看进度。'
            );
        } catch (error) {
            setGraphSyncState('error');
            setGraphSyncMessage(error instanceof Error ? error.message : '知识图谱构建提交失败');
        }
    };
    */

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
            setTracePanelOpen(false);
            setActiveTraceKey('');
            setExpandedTraceCardKey('');
            return;
        }
        setTracePanelOpen(Boolean(activeFieldKey));
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
        setHoveredFieldKey(null);
        setActiveFieldKey(null);
        setActiveTraceKey('');
        setExpandedTraceCardKey('');
        const fileHash = activeAssistantSessionKey;
        const storedSessionId = String(readAssistantSessionMap()[fileHash] || '').trim();
        setAssistantSessionId(storedSessionId);
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
    const activeFieldItem = useMemo(
        () =>
            fieldItems.find(
                (item) => String(item.key || '').toLowerCase() === String(activeFieldKey || '').trim().toLowerCase()
            ) || null,
        [activeFieldKey, fieldItems]
    );
    const hasFieldResults = fieldItems.length > 0;
    const shouldShowResultsStateCard = !hasFieldResults;
    const documentTraceHits = useMemo(() => toTraceHits(activeDoc, null), [activeDoc]);
    const xlsxProjectionSummary = useMemo(() => {
        if (activeRenderExt !== 'xlsx' || documentTraceHits.length === 0) return null;

        let truncatedSheetCount = 0;
        let maxProjectedRows = 0;
        let maxProjectedCols = 0;
        let maxSourceRows = 0;
        let maxSourceCols = 0;

        documentTraceHits.forEach((hit) => {
            if (getTraceDisplayKind(hit) !== 'table') return;
            const locator = toRecord(hit.locator);
            const dataframeRaw = toRecord(locator.dataframe);
            const previewRaw = toRecord(locator.table_preview);
            const projectedRows = Math.max(
                toPositiveRoundedInt(dataframeRaw.projected_row_count),
                toPositiveRoundedInt(previewRaw.projected_row_count),
                toPositiveRoundedInt(dataframeRaw.row_count),
                toPositiveRoundedInt(previewRaw.row_count),
            );
            const projectedCols = Math.max(
                toPositiveRoundedInt(dataframeRaw.projected_col_count),
                toPositiveRoundedInt(previewRaw.projected_col_count),
                toPositiveRoundedInt(dataframeRaw.col_count),
                toPositiveRoundedInt(previewRaw.col_count),
            );
            const sourceRows = Math.max(
                toPositiveRoundedInt(dataframeRaw.source_nonempty_row_count),
                toPositiveRoundedInt(previewRaw.source_nonempty_row_count),
            );
            const sourceCols = Math.max(
                toPositiveRoundedInt(dataframeRaw.source_used_col_count),
                toPositiveRoundedInt(previewRaw.source_used_col_count),
            );
            const truncated = Boolean(dataframeRaw.xlsx_projection_truncated)
                || Boolean(previewRaw.xlsx_projection_truncated)
                || (sourceRows > 0 && sourceRows > projectedRows)
                || (sourceCols > 0 && sourceCols > projectedCols);
            if (!truncated) return;

            truncatedSheetCount += 1;
            maxProjectedRows = Math.max(maxProjectedRows, projectedRows);
            maxProjectedCols = Math.max(maxProjectedCols, projectedCols);
            maxSourceRows = Math.max(maxSourceRows, sourceRows);
            maxSourceCols = Math.max(maxSourceCols, sourceCols);
        });

        if (truncatedSheetCount <= 0) return null;
        return {
            truncatedSheetCount,
            maxProjectedRows,
            maxProjectedCols,
            maxSourceRows,
            maxSourceCols,
        };
    }, [activeRenderExt, documentTraceHits]);
    const documentTraceDetailHits = useMemo(
        () => documentTraceHits.filter((hit) => String(hit.object_type || '').toLowerCase() !== 'field'),
        [documentTraceHits]
    );
    const hasDocumentTraceDetailHits = documentTraceDetailHits.length > 0;
    const traceDetailHits = useMemo(
        () => traceHits.filter((hit) => String(hit.object_type || '').toLowerCase() !== 'field'),
        [traceHits]
    );
    const hasTraceDetailHits = traceDetailHits.length > 0;
    const shouldShowTraceDetailPanel = false;
    const shouldShowTraceRootBlock = Boolean(activeDoc) && (filteredFieldItems.length > 0 || hasDocumentTraceDetailHits);
    const canCopyFilteredResults = filteredFieldItems.length > 0;
    const filteredResultsClipboardText = useMemo(
        () =>
            filteredFieldItems
                .map((item, idx) => `${idx + 1}. ${item.label} (${item.key})\n${item.valueText}`)
                .join('\n\n'),
        [filteredFieldItems]
    );
    const assistantExtraContext = useMemo(
        () =>
            buildAssistantExtraContext({
                activeDoc,
                activeDocIndex,
                documents,
                fieldItems,
                traceHits: documentTraceHits,
                activeSummaryText,
                smartUnitTab,
                currentObjectLock: assistantCurrentLock,
            }),
        [activeDoc, activeDocIndex, activeSummaryText, assistantCurrentLock, documentTraceHits, documents, fieldItems, smartUnitTab]
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
        return Math.max(1, diagnosticPdfPageCount, maxByRefs, maxByTrace, pdfPreviewPageCount);
    }, [activeRenderExt, diagnosticPdfPageCount, fieldItems, pdfPreviewPageCount, traceHits]);

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
    const documentTraceHitCount = documentTraceHits.length;

    const traceTypeStats = useMemo(() => {
        const stats: Record<TraceDisplayKind, number> = {
            field: 0,
            table: 0,
            image: 0,
            chart: 0,
            other: 0,
        };

        traceDetailHits.forEach((hit) => {
            const typ = getTraceDisplayKind(hit);
            if (typ === 'field') {
                stats.field += 1;
            } else if (typ === 'table') {
                stats.table += 1;
            } else if (typ === 'image') {
                stats.image += 1;
            } else if (typ === 'chart') {
                stats.chart += 1;
            } else {
                stats.other += 1;
            }
        });

        return stats;
    }, [traceDetailHits]);
    const hasTraceTypeStats = false;
    const traceSectionHint = traceDetailHits.length > 0
        ? '字段、表格、图片与数据可视化证据定位路径'
        : activeDoc
            ? '当前没有额外的表格、图片或数据可视化证据可展示'
            : '抽取完成后在此查看定位结果';
    const tracePanelHintText = activeFieldItem
        ? traceDetailHits.length > 0
            ? `当前聚焦“${activeFieldItem.label}”，点击定位卡片可回跳原文。`
            : `当前字段暂无额外证据卡片，原文定位以预览区高亮为准。`
        : traceSectionHint;

    const traceGroups = useMemo(() => buildTraceGroups(traceDetailHits), [traceDetailHits]);
    const documentTraceGroups = useMemo(() => buildTraceGroups(documentTraceDetailHits), [documentTraceDetailHits]);

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
                    { retryNotFound: false },
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
                const pdfUrl =
                    resolveByFileArtifactUrl(payload, resolvedBase)
                    || normalizeExtractArtifactUrl(
                        String(payload.artifact_url || '').trim(),
                        resolvedBase,
                    );
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
            const pdfUrl =
                resolveByFileArtifactUrl(payload, usedBase)
                || normalizeExtractArtifactUrl(
                    String(payload.artifact_url || '').trim(),
                    usedBase,
                );
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
            apiBase?: string;
        },
    ) => {
        const partial = Boolean(options?.partial);
        const usedBase = String(options?.apiBase || '').trim();
        const currentActiveDoc = activeDocRef.current;
        const currentActiveDocIndex = activeDocIndexRef.current;
        const previousDocuments = documentsRef.current;
        const previousActiveHash = String(currentActiveDoc?.file_hash || '').trim();
        const previousActiveName = String(currentActiveDoc?.file_name || '').trim().toLowerCase();
        const previousDocCount = previousDocuments.length;
        const currentOfficePreviewMap = officePreviewMapRef.current;
        const incomingDocumentsWithPreview = docs.map((doc) => {
            const normalizedDoc = normalizeDocumentArtifactLinks(doc, usedBase);
            const ext = fileExt(String(doc.file_name || ''));
            if (ext !== 'doc' && ext !== 'docx') return normalizedDoc;

            const diagnostics =
                normalizedDoc.diagnostics && typeof normalizedDoc.diagnostics === 'object'
                    ? (normalizedDoc.diagnostics as Record<string, unknown>)
                    : {};
            const existingPreviewUrl = String(diagnostics.office_pdf_preview_url || '').trim();
            if (existingPreviewUrl) return normalizedDoc;

            const matchedPreview = pickOfficePreviewByFileName(normalizedDoc.file_name, currentOfficePreviewMap);
            const previewUrl = String(matchedPreview?.pdfUrl || '').trim();
            if (!previewUrl) return normalizedDoc;

            return {
                ...normalizedDoc,
                diagnostics: {
                    ...diagnostics,
                    office_pdf_preview_url: previewUrl,
                },
            };
        });
        const documentsWithPreview = mergeExtractionDocumentsForSelection(
            previousDocuments,
            incomingDocumentsWithPreview,
            selectedFilesRef.current,
        );
        const nextActiveIndex = Math.max(
            0,
            Math.min(
                currentActiveDocIndex,
                Math.max(0, selectedFilesRef.current.length - 1),
            ),
        );
        const nextActiveFile = selectedFilesRef.current[nextActiveIndex] || null;
        const nextActiveDoc = nextActiveFile
            ? pickDocumentResultForFile(documentsWithPreview, nextActiveFile, nextActiveIndex)
            : documentsWithPreview[0] || null;
        setDocuments(documentsWithPreview);
        writeExtractionDocuments(documentsWithPreview);
        if (nextActiveIndex !== currentActiveDocIndex) {
            setActiveDocIndex(nextActiveIndex);
        }
        if (!partial || nextActiveIndex !== currentActiveDocIndex) {
            setPdfViewportPage(1);
            setPdfScrollRequest(createPdfScrollRequest(1));
        }
        if (nextActiveDoc) {
            const nextActiveHash = String(nextActiveDoc.file_hash || '').trim();
            if (!partial || previousDocCount === 0 || nextActiveHash !== previousActiveHash) {
                void requestSummary(nextActiveDoc);
            }
        }

        const firstErrorDoc = documentsWithPreview.find((doc) => doc.errors && doc.errors.length > 0);
        if (firstErrorDoc) {
            setErrorMessage(formatExtractUiErrors(firstErrorDoc.errors));
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
        const softWarningCount = documentsWithPreview.reduce((acc, doc) => acc + getDisplaySoftWarnings(doc).length, 0);
        const autoSchemaDocs = documentsWithPreview.reduce((acc, doc) => {
            const mode = String(doc.diagnostics?.schema_mode || '');
            return acc + (mode === 'auto' ? 1 : 0);
        }, 0);
        setInfoMessage(
            `已完成 ${documentsWithPreview.length} 份文档抽取，缓存命中 ${cacheHits} 份，智能字段识别 ${autoSchemaDocs} 份，识别表格 ${totalTables} 张（来源: ${sourceText}），识别图像 ${totalFigures} 张（来源: ${figureSourceText}），软告警 ${softWarningCount} 条。`
        );
    };

    const clearFailedExtractionDocuments = (
        jobFiles: RuntimeExtractionJobFileState[],
    ) => {
        const targetNames = new Set<string>();
        jobFiles.forEach((item) => {
            const normalized = normalizeWorkbenchFileName(item.file_name);
            if (normalized) {
                targetNames.add(normalized);
            }
        });
        if (targetNames.size === 0) {
            selectedFilesRef.current.forEach((file) => {
                const normalized = normalizeWorkbenchFileName(file.name);
                if (normalized) {
                    targetNames.add(normalized);
                }
            });
        }
        if (targetNames.size === 0) return;

        const previousDocuments = documentsRef.current;
        const nextDocuments = removeDocumentResultsForNames(previousDocuments, targetNames);
        if (nextDocuments.length === previousDocuments.length) return;

        setDocuments(nextDocuments);
        writeExtractionDocuments(nextDocuments);
        if (activeDocIndexRef.current > Math.max(0, nextDocuments.length - 1)) {
            setActiveDocIndex(Math.max(0, nextDocuments.length - 1));
        }
        setPdfViewportPage(1);
        setPdfScrollRequest(createPdfScrollRequest(1));
    };

    const pollExtractionJob = async (
        jobId: string,
        preferredBase = '',
        options?: { silentMissingJob?: boolean },
    ) => {
        const normalizedJobId = normalizeExtractionJobId(jobId);
        const silentMissingJob = Boolean(options?.silentMissingJob);
        if (!normalizedJobId) {
            extractionJobPollRef.current = '';
            extractionJobApiBaseRef.current = '';
            setExtractionJob(null);
            setIsProcessing(false);
            setActiveSummaryLoading(false);
            setErrorMessage('抽取任务标识无效，当前任务状态已清理，请重新发起解析。');
            return;
        }
        const runId = ++extractionJobPollRunIdRef.current;
        extractionJobPollRef.current = normalizedJobId;
        const pollIntervalMs = 850;
        const pollTimeoutMs = 45 * 60 * 1000;
        const startedAt = Date.now();
        while (Date.now() - startedAt < pollTimeoutMs) {
            if (
                extractionJobPollRef.current !== normalizedJobId
                || extractionJobPollRunIdRef.current !== runId
            ) {
                return;
            }
            try {
                const fetchResult = await fetchExtractWithFallback(
                    `/extract/jobs/status/${encodeURIComponent(normalizedJobId)}?include_documents=false&status_only=true`,
                    undefined,
                    preferredBase || extractionJobApiBaseRef.current || '',
                    { retryNotFound: false },
                );
                const usedBase = fetchResult.usedBase || preferredBase || '';
                extractionJobApiBaseRef.current = usedBase;
                const payload = (await fetchResult.response.json()) as ExtractionJobState & {
                    progress: ExtractionJobState['progress'];
                    terminal: boolean;
                    documents?: DocumentResult[];
                };
                const normalizedJob = normalizeExtractionJobPayload(
                    payload,
                    usedBase,
                    extractionJobPollRef.current === normalizedJobId ? extractionJobStateRef.current : null,
                );
                const visibleJob = reconcileVisibleExtractionJob(normalizedJob, usedBase);
                const visibleDocuments = Array.isArray(payload.documents)
                    ? filterVisibleDocumentsForJobFiles(payload.documents, visibleJob?.files || [])
                    : [];
                setExtractionJob(visibleJob);
                setIsProcessing(!visibleJob?.terminal);

                if (!visibleJob?.terminal) {
                    setInfoMessage(buildExtractionInfoMessage(visibleJob, Date.now(), false));
                }

                if (!visibleJob?.terminal && visibleDocuments.length > 0) {
                    applyExtractionDocuments(visibleDocuments, { partial: true, apiBase: usedBase });
                }

                if (visibleJob?.terminal) {
                    extractionJobPollRef.current = '';
                    let terminalPayload: (ExtractionJobState & {
                        progress: ExtractionJobState['progress'];
                        terminal: boolean;
                        documents?: DocumentResult[];
                    }) = payload;
                    let terminalBase = usedBase;
                    let terminalVisibleJob = visibleJob;
                    let terminalVisibleDocuments = visibleDocuments;

                    try {
                        const terminalFetchResult = await fetchExtractWithFallback(
                            `/extract/jobs/status/${encodeURIComponent(normalizedJobId)}?include_documents=true`,
                            undefined,
                            usedBase || preferredBase || extractionJobApiBaseRef.current || '',
                            { retryNotFound: false },
                        );
                        terminalBase = terminalFetchResult.usedBase || terminalBase;
                        extractionJobApiBaseRef.current = terminalBase;
                        terminalPayload = (await terminalFetchResult.response.json()) as ExtractionJobState & {
                            progress: ExtractionJobState['progress'];
                            terminal: boolean;
                            documents?: DocumentResult[];
                        };

                        const normalizedTerminalJob = normalizeExtractionJobPayload(
                            terminalPayload,
                            terminalBase,
                            extractionJobStateRef.current,
                        );
                        terminalVisibleJob = reconcileVisibleExtractionJob(normalizedTerminalJob, terminalBase);
                        terminalVisibleDocuments = Array.isArray(terminalPayload.documents)
                            ? filterVisibleDocumentsForJobFiles(terminalPayload.documents, terminalVisibleJob?.files || [])
                            : [];
                        setExtractionJob(terminalVisibleJob);
                    } catch (terminalFetchError) {
                        console.warn('module2 terminal documents fetch failed', terminalFetchError);
                    }

                    if (terminalVisibleDocuments.length > 0) {
                        applyExtractionDocuments(terminalVisibleDocuments, { apiBase: terminalBase || usedBase });
                    } else {
                        const terminalStatus = String(
                            terminalVisibleJob?.status || terminalPayload.status || '',
                        ).trim().toLowerCase();
                        const terminalFileFailure = (terminalVisibleJob?.files || []).some((item) => {
                            const status = String(item.status || '').trim().toLowerCase();
                            return status === 'failed' || status === 'cancelled';
                        });
                        if (
                            terminalStatus === 'failed'
                            || terminalFileFailure
                            || (Array.isArray(terminalPayload.errors) && terminalPayload.errors.length > 0)
                        ) {
                            clearFailedExtractionDocuments(terminalVisibleJob?.files || []);
                        }
                        if (Array.isArray(terminalPayload.errors) && terminalPayload.errors.length > 0) {
                            setErrorMessage(formatExtractUiErrors(terminalPayload.errors));
                        } else {
                        setInfoMessage('抽取任务已结束，暂无可展示结果。');
                    }
                    }
                    return;
                }
            } catch (error) {
                if (
                    extractionJobPollRef.current !== normalizedJobId
                    || extractionJobPollRunIdRef.current !== runId
                ) {
                    return;
                }
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
                    if (silentMissingJob) {
                        setErrorMessage('');
                        setInfoMessage(
                            documentsRef.current.length > 0
                                ? '检测到历史任务已过期，已自动忽略旧任务状态并保留最近一次解析结果。'
                                : '检测到历史任务已过期，界面已自动恢复为可重新发起解析的状态。',
                        );
                    } else if (documentsRef.current.length > 0) {
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
        if (
            extractionJobPollRef.current === normalizedJobId
            && extractionJobPollRunIdRef.current === runId
        ) {
            setErrorMessage('抽取进度轮询超时，请稍后重试或检查后端日志。');
            extractionJobPollRef.current = '';
            setIsProcessing(false);
        }
    };

    useEffect(() => {
        if (!extractionJob || extractionJob.terminal) return;
        const normalizedJobId = normalizeExtractionJobId(extractionJob.job_id);
        if (!normalizedJobId) return;
        if (extractionJobPollRef.current === normalizedJobId) return;
        const isRestoredSessionJob = restoredSessionJobIdRef.current === normalizedJobId;
        void pollExtractionJob(
            normalizedJobId,
            extractionJobApiBaseRef.current || '',
            { silentMissingJob: isRestoredSessionJob },
        );
    }, [extractionJob?.job_id, extractionJob?.terminal]);

    useEffect(() => {
        if (!extractionJob || !extractionJob.terminal) return;
        const normalizedJobId = normalizeExtractionJobId(extractionJob.job_id);
        if (!normalizedJobId) return;
        const isRestoredSessionJob = restoredSessionJobIdRef.current === normalizedJobId;
        if (isRestoredSessionJob && documentsRef.current.length > 0) {
            terminalJobResyncRef.current = normalizedJobId;
            return;
        }
        if (terminalJobResyncRef.current === normalizedJobId) return;
        terminalJobResyncRef.current = normalizedJobId;
        void pollExtractionJob(
            normalizedJobId,
            extractionJobApiBaseRef.current || '',
            { silentMissingJob: isRestoredSessionJob },
        );
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
        const currentSelectedFiles = selectedFilesRef.current;
        const existingKeySet = new Set(currentSelectedFiles.map((file) => fileIdentityKey(file)));
        [...currentSelectedFiles, ...incoming].forEach((file) => {
            const key = fileIdentityKey(file);
            byIdentity.set(key, file);
            fileBlobCache.set(key, file); // 存入全局缓存
        });
        const merged = Array.from(byIdentity.values());
        const limited = merged.slice(0, 5);
        const retainedNewFileKeys = new Set(
            limited
                .map((file) => fileIdentityKey(file))
                .filter((key) => !existingKeySet.has(key)),
        );
        setSelectedFiles(limited);
        if (retainedNewFileKeys.size > 0) {
            for (let index = limited.length - 1; index >= 0; index -= 1) {
                if (!retainedNewFileKeys.has(fileIdentityKey(limited[index]))) continue;
                setActiveDocIndex(index);
                break;
            }
        }
        if (merged.length > 5) {
            setInfoMessage("批处理上限为 5 个文件，超出部分已忽略。");
        } else if (rejectedCount > 0) {
            setInfoMessage(`已忽略 ${rejectedCount} 个不支持的文件，仅支持常见文档与图片格式。`);
        } else {
            setInfoMessage(`已选择 ${limited.length} 个文件，可切换到当前文件后单独开始解析。`);
        }
        const selectedKeySet = new Set(limited.map((file) => fileIdentityKey(file)));
        incoming.forEach((file) => {
            if (!selectedKeySet.has(fileIdentityKey(file))) return;
            void ensureOfficePreview(file);
        });
    };

    useEffect(() => {
        void consumeModule2DraftFromHomeWorkbench().then((handoff) => {
            if (!handoff) return;
            if (handoff.itemIds && handoff.itemIds.length > 0) {
              // process HomeWorkbench items ...
            }
            setSmartUnitTab('results');
        });
    }, [mergeSelectedFiles]);

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
        suppressedExtractionJobFilesRef.current = {};
        persistedSelectedFilesRef.current = [];
        clearLuckysheetPreviewCache();
        setOfficePreviewMap({});
        setExtractionJob(null);
        setSelectedFileArtifacts({});
        setSessionRestorePending(false);
        setDocuments([]);
        setSelectedFiles([]);
        fileBlobCache.clear();
        setActiveDocIndex(0);
        setActiveFieldKey(null);
        setHoveredFieldKey(null);
        setPreviewUrl(null);
        setPreviewText('');
        setPdfViewportPage(1);
        setPdfScrollRequest(null);
        setPdfPreviewPageCount(1);
        setErrorMessage('');
        setInfoMessage(message);
        setScale(1);
        setRotation(0);
        setPdfViewMode('fit-width');
        summaryRequestSeqRef.current += 1;
        traceRequestSeqRef.current += 1;
        setSummaryDocName('');
        setActiveSummaryText('');
        setActiveSummaryLoading(false);
        setTraceHits([]);
        setTraceError('');
        setTraceLoading(false);
        setTracePanelOpen(false);
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
        const currentJob = extractionJobStateRef.current;
        selectedFiles.forEach((file, index) => {
            suppressAndCancelJobFile(currentJob, file, index);
        });
        setSelectedFiles([]);
        resetWorkbenchState('已清空当前页面数据与本地缓存。');
    };

    const removeFile = (index: number, forceConfirm = false) => {
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
        if (confirmMessage && !forceConfirm) {
            setPendingRemoveFile({
                index,
                fileName: removed.name,
                message: confirmMessage,
            });
            return;
        }

        const currentJob = extractionJobStateRef.current;
        const nextFiles = selectedFiles.filter((_, i) => i !== index);
        suppressAndCancelJobFile(currentJob, removed, index);

        if (selectedFiles.length <= 1) {
            setSelectedFiles([]);
            resetWorkbenchState("文件队列已清空。");
            return;
        }

        const key = fileIdentityKey(removed);
        fileBlobCache.delete(key);
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

        setSelectedFiles(nextFiles);
        setExtractionJob((prev) => {
            const normalizedJobId = normalizeExtractionJobId(prev?.job_id);
            const suppressedKeys = normalizedJobId
                ? getSuppressedExtractionJobFileKeys(normalizedJobId)
                : undefined;
            return filterVisibleRuntimeExtractionJob(prev, nextFiles, suppressedKeys);
        });
        setDocuments((prev) => {
            if (!Array.isArray(prev) || prev.length === 0) return prev;
            const nextDocs = removeDocumentResultForFile(prev, removed);
            writeExtractionDocuments(nextDocs);
            return nextDocs;
        });
        if (activeDocIndex >= nextFiles.length) {
            setActiveDocIndex(Math.max(0, nextFiles.length - 1));
        }
        setActiveFieldKey(null);
        setInfoMessage(`已移除 ${removed.name}`);
    };

    const confirmRemoveFile = () => {
        if (!pendingRemoveFile) return;
        const targetIndex = pendingRemoveFile.index;
        setPendingRemoveFile(null);
        removeFile(targetIndex, true);
    };

    const cancelRemoveFile = () => {
        setPendingRemoveFile(null);
    };

    const clearAllFiles = () => {
        const currentJob = extractionJobStateRef.current;
        selectedFiles.forEach((file, index) => {
            suppressAndCancelJobFile(currentJob, file, index);
        });
        setSelectedFiles([]);
        resetWorkbenchState('文件队列已清空。');
    };

    const runExtraction = async () => {
        const targetFile = activeSourceFile;
        const targetIndex = activeSourceFileIndex >= 0 ? activeSourceFileIndex : activeDocIndex;
        if (!targetFile) {
            setErrorMessage("请先选择需要解析的文件。");
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
        const previousDocuments = documentsRef.current;
        const nextDocuments = removeDocumentResultForFile(previousDocuments, targetFile);
        if (nextDocuments.length !== previousDocuments.length) {
            setDocuments(nextDocuments);
            writeExtractionDocuments(nextDocuments);
        }
        setActiveFieldKey(null);
        setIsProcessing(true);
        setExtractionJob(null);
        extractionJobPollRef.current = '';
        extractionJobPollRunIdRef.current += 1;
        extractionJobApiBaseRef.current = '';
        terminalJobResyncRef.current = '';
        restoredSessionJobIdRef.current = '';
        suppressedExtractionJobFilesRef.current = {};
        setInfoMessage(`正在提交 ${targetFile.name} 的抽取任务...`);
        setActiveSummaryLoading(true);
        setActiveSummaryText('已收到当前文件的抽取任务，正在生成智能摘要...');
        setSummaryDocName(targetFile.name);
        setAssistantMessage("当前文件任务已提交，解析与摘要正在同步执行。");
        setAssistantAnswer('');
        setAssistantWarnings([]);
        resetAssistantCompanionState();
        traceRequestSeqRef.current += 1;
        setTraceHits([]);
        setTraceError('');
        setTraceLoading(false);
        setTracePanelOpen(false);
        setActiveTraceKey('');
        setExpandedTraceCardKey('');

        try {
            const requestJobCreateWithRetry = async (attempts: number) => {
                let lastError: unknown = null;
                for (let i = 1; i <= attempts; i += 1) {
                    const formData = new FormData();
                    formData.append('files', targetFile);
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
                const message = await readResponseErrorMessage(response);
                throw new Error(message || '抽取请求失败');
            }

            const payload = await response.json() as ExtractionJobState & { documents?: DocumentResult[] };
            if (!payload || !payload.job_id) {
                throw new Error('后端未返回有效的抽取任务。');
            }

            const normalizedJob = normalizeExtractionJobPayload(payload, usedBase, extractionJobStateRef.current);
            const visibleJob = reconcileVisibleExtractionJob(normalizedJob, usedBase);
            const currentVisibleFiles = selectedFilesRef.current.length > 0 ? selectedFilesRef.current : selectedFiles;
            const visibleDocuments = Array.isArray(payload.documents)
                ? filterVisibleDocumentsForJobFiles(payload.documents, visibleJob?.files || [])
                : [];
            const nextArtifactMap = mergeSelectedFileArtifactsFromJob(
                selectedFileArtifacts,
                currentVisibleFiles,
                visibleJob?.files || [],
            );

            setSelectedFileArtifacts(nextArtifactMap);
            setExtractionJob(visibleJob);
            setIsProcessing(!visibleJob?.terminal);
            writeWorkbenchSession(
                toSessionSnapshot(
                    currentVisibleFiles,
                    targetIndex,
                    '',
                    'results',
                    officePreviewMap,
                    visibleJob,
                    nextArtifactMap,
                ),
            );

            setInfoMessage(buildExtractionInfoMessage(visibleJob, Date.now(), true));

            if (visibleJob?.terminal) {
                if (visibleDocuments.length > 0) {
                    applyExtractionDocuments(visibleDocuments, { apiBase: usedBase });
                } else if (visibleJob.errors.length > 0) {
                    clearFailedExtractionDocuments(visibleJob.files || []);
                    setErrorMessage(formatExtractUiErrors(visibleJob.errors));
                }
            } else {
                void pollExtractionJob(visibleJob?.job_id || normalizedJob.job_id, usedBase);
            }
        } catch (error) {
            console.error(error);
            setErrorMessage(sanitizeExtractUiErrorMessage(error instanceof Error ? error.message : '抽取失败') || '抽取失败');
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
    const activateTraceSelection = ({
        traceKey,
        objectType,
        objectId,
        page,
    }: {
        traceKey: string;
        objectType?: string;
        objectId?: string;
        page?: number;
    }) => {
        setActiveTraceKey(traceKey);
        if (String(objectType || '').toLowerCase() === 'field' && objectId) {
            setActiveFieldKey(objectId);
        }
        if (activeRenderExt === 'pdf' && Number.isFinite(page) && Number(page) > 0) {
            jumpToPdfPage(page);
        }
    };
    const handleSelectDocument = (index: number) => {
        if (index === activeDocIndex) return;
        setHoveredFieldKey(null);
        setActiveFieldKey(null);
        setActiveTraceKey('');
        setExpandedTraceCardKey('');
        setPdfViewportPage(1);
        setPdfScrollRequest(createPdfScrollRequest(1));
        setActiveDocIndex(index);
        if (showLeftQueueDrawer) {
            setIsLeftQueueDrawerOpen(false);
        }
    };
    const openLeftQueueDrawer = () => {
        if (!shouldUseLeftQueueDrawer) {
            setIsPreviewFocused(false);
            return;
        }
        setIsLeftQueueDrawerOpen(true);
    };
    const closeLeftQueueDrawer = () => setIsLeftQueueDrawerOpen(false);
    const toggleLeftQueueAccess = () => {
        if (!shouldUseLeftQueueDrawer) {
            setIsPreviewFocused((prev) => !prev);
            return;
        }
        setIsLeftQueueDrawerOpen((prev) => !prev);
    };
    const stopTraceCardAction = (
        event: React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLElement>
    ) => {
        event.stopPropagation();
    };
    const handleTraceCardKeyDown = (
        event: React.KeyboardEvent<HTMLDivElement>,
        options: {
            traceKey: string;
            objectType?: string;
            objectId?: string;
            page?: number;
        }
    ) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        activateTraceSelection(options);
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
        if (activeRenderExt === 'pdf') {
            setPdfViewMode('fit-width');
        }
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

    const clearTraceSelection = () => {
        setTracePanelOpen(false);
        setActiveFieldKey(null);
        setActiveTraceKey('');
        setExpandedTraceCardKey('');
        setHoveredFieldKey(null);
    };

    const handleFieldCardClick = (item: FieldItem) => {
        const normalizedKey = String(item.key || '').trim().toLowerCase();
        const isSameFieldActive =
            tracePanelOpen && String(activeFieldKey || '').trim().toLowerCase() === normalizedKey;

        if (isSameFieldActive) {
            clearTraceSelection();
            return;
        }

        setTracePanelOpen(true);
        setActiveFieldKey(item.key);
        setExpandedTraceCardKey('');

        const hitIndex = traceHits.findIndex(
            (hit) =>
                String(hit.object_type || '').trim().toLowerCase() === 'field'
                && String(hit.object_id || '').trim().toLowerCase() === normalizedKey
        );
        if (hitIndex >= 0) {
            setActiveTraceKey(toTraceHitKey(traceHits[hitIndex], hitIndex));
        } else {
            setActiveTraceKey('');
        }

        if (activeRenderExt === 'pdf' && item.pageNumber) {
            jumpToPdfPage(item.pageNumber);
        }
    };

    const renderTraceEvidenceCard = (hit: TraceHit, idx: number) => {
        const objectType = String(hit.object_type || 'field').toLowerCase();
        const displayKind = getTraceDisplayKind(hit);
        const objectLabel = getTraceDisplayLabel(hit);
        const objectId = String(hit.object_id || '');
        const page = toTracePage(hit);
        const rawSnippet = String(hit.snippet || '');
        let snippet = rawSnippet;
        if (displayKind === 'table') {
            snippet = snippet.replace(/([；;,. ]*)表头[:：].*$/, '');
        }
        let displayTitle = snippet || objectId || '定位片段';
        if (displayKind === 'image' || objectType === 'figure') {
            displayTitle = displayTitle.replace(/^(?:charts?|figures?|images?|图表)[:：\s]*/i, '').replace(/\s*\([^)]+\)$/, '');
        }
        const traceKey = toTraceHitKey(hit, idx);
        const isActiveTrace = activeTraceKey === traceKey;
        const jumpButtonLabel = activeRenderExt === 'pdf' && page > 0
            ? `定位到第 ${Math.round(page)} 页`
            : '聚焦当前证据';
        const artifactUrl = resolveArtifactUrl(hit);
        const locator = (hit.locator ?? {}) as Record<string, unknown>;
        const chartSpec = toTraceChartSpec(locator.chart_spec);
        const tablePreview = toRecord(locator.table_preview);
        const tableDataframeRaw = toRecord(locator.dataframe);
        const tableDataframe = pickBestTraceDataframePayload(tableDataframeRaw, tablePreview);
        const tableHeaders = tableDataframe.headers;
        const tableRows = tableDataframe.rows;
        const tableProjectedRowCount = Math.max(
            tableDataframe.rowCount,
            toPositiveRoundedInt(tableDataframeRaw.projected_row_count),
            toPositiveRoundedInt(tablePreview.projected_row_count),
        );
        const tableProjectedColCount = Math.max(
            tableDataframe.colCount,
            toPositiveRoundedInt(tableDataframeRaw.projected_col_count),
            toPositiveRoundedInt(tablePreview.projected_col_count),
        );
        const tableSourceRowCount = Math.max(
            toPositiveRoundedInt(tableDataframeRaw.source_nonempty_row_count),
            toPositiveRoundedInt(tablePreview.source_nonempty_row_count),
        );
        const tableSourceColCount = Math.max(
            toPositiveRoundedInt(tableDataframeRaw.source_used_col_count),
            toPositiveRoundedInt(tablePreview.source_used_col_count),
        );
        const tableProjectionTruncated = Boolean(tableDataframeRaw.xlsx_projection_truncated)
            || Boolean(tablePreview.xlsx_projection_truncated)
            || (tableSourceRowCount > 0 && tableSourceRowCount > tableProjectedRowCount)
            || (tableSourceColCount > 0 && tableSourceColCount > tableProjectedColCount);
        const figureKeyPoints = Array.isArray(locator.key_points)
            ? locator.key_points.map((value) => String(value ?? '')).filter(Boolean).slice(0, 3)
            : [];
        const figureModesRaw = Array.isArray(locator.content_modes)
            ? locator.content_modes.map((value) => String(value ?? '').trim().toLowerCase()).filter(Boolean)
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
            ? locator.text_blocks.map((value) => String(value ?? '').trim()).filter(Boolean).slice(0, 3)
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
        const locatorSummary = locatorHints.join(' / ');
        const canExpandDataframe = displayKind === 'table'
            ? tableRows.length > 0
            : objectType === 'figure' && figureDfRows.length > 0;
        const isTraceExpanded = canExpandDataframe && expandedTraceCardKey === traceKey;
        const tableHeaderSummary = tableHeaders.slice(0, 4);
        const figureSummaryBullets = (figureKeyPoints.length > 0 ? figureKeyPoints : figureTextBlocks).slice(0, 3);
        const artifactSourceLabel = toTraceSourceLabel(locator.artifact_source);
        const showArtifactImage = canRenderTraceArtifactImage(artifactUrl, locator.artifact_source);
        const showArtifactSource = canShowTraceArtifactSource(locator.artifact_source);

        return (
            <div
                key={`trace-list-${traceKey}`}
                data-testid="module2-trace-card"
                data-trace-kind={displayKind}
                data-trace-active={isActiveTrace ? 'true' : 'false'}
                onClick={() => activateTraceSelection({ traceKey, objectType, objectId, page })}
                className={cn(
                    "group relative w-full rounded-xl border px-3 py-3 text-left shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-all duration-200 mb-2",
                    isActiveTrace
                        ? "border-blue-400 ring-1 ring-blue-400 bg-blue-50/50 dark:border-blue-500/50 dark:ring-blue-500/30 dark:bg-blue-500/10"
                        : "border-slate-200/80 bg-slate-50/50 hover:border-slate-300 hover:bg-white hover:shadow-[0_2px_4px_rgba(0,0,0,0.04)] dark:border-white/[0.05] dark:bg-white/[0.01] dark:hover:border-white/[0.08] dark:hover:bg-white/[0.03]",
                    isTraceExpanded && "bg-white shadow-[0_2px_4px_rgba(0,0,0,0.04)] border-slate-300 dark:bg-white/[0.04] dark:border-white/[0.1]"
                )}
            >
                <div className="mb-1.5 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                        <span className={cn(
                            "flex h-5 items-center justify-center rounded-md px-1.5 text-[10px] tabular-nums font-semibold uppercase tracking-wider",
                            displayKind === 'field' ? "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400" :
                                displayKind === 'table' ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400" :
                                    displayKind === 'chart' ? "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300" :
                                    displayKind === 'image' ? "bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400" :
                                        "bg-slate-100 text-slate-600 dark:bg-white/[0.05] dark:text-slate-400"
                        )}>
                            {objectLabel}
                        </span>
                        {activeRenderExt === 'pdf' && page > 0 && (
                            <span className="flex items-center gap-0.5 text-[10px] tabular-nums font-medium text-slate-400">
                                <span className="opacity-50">页</span>
                                <span>{Math.round(page)}</span>
                            </span>
                        )}
                    </div>
                    <span className="text-[10px] tabular-nums font-medium text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">{Math.round((Number(hit.confidence || 0) || 0) * 100)}%</span>
                </div>
                <div className="flex items-start gap-1.5">
                    <div className={cn(
                        "mt-[1px] flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px]",
                        displayKind === 'table' ? "bg-emerald-50 text-emerald-600 ring-1 ring-inset ring-emerald-100/50 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20" :
                        displayKind === 'chart' ? "bg-cyan-50 text-cyan-700 ring-1 ring-inset ring-cyan-100/50 dark:bg-cyan-500/10 dark:text-cyan-300 dark:ring-cyan-500/20" :
                        displayKind === 'image' ? "bg-amber-50 text-amber-600 ring-1 ring-inset ring-amber-100/50 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20" :
                        displayKind === 'field' ? "bg-blue-50 text-blue-600 ring-1 ring-inset ring-blue-100/50 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20" :
                        "bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-200/50 dark:bg-white/[0.05] dark:text-slate-400 dark:ring-white/[0.1]"
                    )}>
                        {displayKind === 'table' ? <FileSpreadsheet className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                         displayKind === 'chart' ? <Layout className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                         displayKind === 'image' ? <FileImage className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                         displayKind === 'field' ? <FileText className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                         <File className="h-[10px] w-[10px]" strokeWidth={2.5} />}
                    </div>
                    <p className="line-clamp-2 text-[11px] tabular-nums leading-relaxed text-slate-800 dark:text-slate-200">
                        {displayTitle}
                    </p>
                </div>

                {locatorSummary && (
                    <div className="mt-2 flex items-center gap-1.5">
                        <div className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600"></div>
                        <p className="truncate text-[10px] tabular-nums text-slate-500 dark:text-slate-400">
                            {locatorSummary}
                        </p>
                    </div>
                )}

                {displayKind === 'table' && tableProjectionTruncated && (
                    <div className="mt-2 rounded-md bg-slate-50/85 px-2.5 py-2 text-[10px] leading-relaxed text-slate-600 ring-1 ring-inset ring-slate-300/60 dark:bg-white/[0.03] dark:text-slate-300 dark:ring-white/[0.08]">
                        {`Table preview scope: ${formatCompactInt(tableProjectedRowCount)} rows × ${formatCompactInt(tableProjectedColCount)} cols shown; source non-empty scope ${formatCompactInt(tableSourceRowCount)} rows × ${formatCompactInt(tableSourceColCount)} cols.`}
                    </div>
                )}

                {displayKind === 'table' && tableHeaderSummary.length > 0 && (
                    <div className="mt-2.5 rounded-md bg-emerald-50/50 px-2.5 py-2 dark:bg-emerald-500/5">
                        <div className="mb-1.5 text-[10px] tabular-nums font-medium text-emerald-600 dark:text-emerald-400">
                            摘要
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                            {tableHeaderSummary.map((header) => (
                                <span
                                    key={`${traceKey}-header-${header}`}
                                    className="rounded bg-white/60 px-1.5 py-0.5 text-[10px] tabular-nums text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                                >
                                    {header}
                                </span>
                            ))}
                        </div>
                    </div>
                )}

                {displayKind === 'chart' && chartSpec && (
                    <div className="mt-3 rounded-lg border border-cyan-200/70 bg-cyan-50/40 p-2 dark:border-cyan-500/20 dark:bg-cyan-500/5">
                        <XlsxTraceChart spec={chartSpec} className="rounded-md bg-white/70 dark:bg-slate-900/50" />
                        {(() => {
                            const xAxisLabel = String(chartSpec.x_axis_label || chartSpec.x_field || '').trim();
                            const yAxisLabel = String(
                                chartSpec.y_axis_label ||
                                (Array.isArray(chartSpec.y_fields) ? chartSpec.y_fields.filter(Boolean).join(' / ') : '')
                            ).trim();
                            if (!xAxisLabel && !yAxisLabel) return null;
                            return (
                                <div className="mt-2 flex flex-wrap gap-1.5 px-1 text-[10px] tabular-nums text-cyan-700/95 dark:text-cyan-200/95">
                                    {xAxisLabel && (
                                        <span className="inline-flex items-center gap-1 rounded-md bg-white/80 px-2 py-0.5 ring-1 ring-inset ring-cyan-500/20 dark:bg-cyan-500/10 dark:ring-cyan-500/30">
                                            X轴：{xAxisLabel}
                                        </span>
                                    )}
                                    {yAxisLabel && (
                                        <span className="inline-flex items-center gap-1 rounded-md bg-white/80 px-2 py-0.5 ring-1 ring-inset ring-cyan-500/20 dark:bg-cyan-500/10 dark:ring-cyan-500/30">
                                            Y轴：{yAxisLabel}
                                        </span>
                                    )}
                                </div>
                            );
                        })()}
                        {(chartSpec.trend_summary || chartSpec.description) && (
                            <p className="mt-2 px-1 text-[10.5px] leading-relaxed text-cyan-800/90 dark:text-cyan-200/90">
                                {chartSpec.trend_summary || chartSpec.description}
                            </p>
                        )}
                    </div>
                )}

                {objectType === 'figure' && figureModes.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                        {figureModes.map((mode) => (
                            <span
                                key={`${traceKey}-mode-${mode}`}
                                className="rounded-md bg-amber-50/50 px-1.5 py-0.5 text-[10px] tabular-nums text-amber-700/80 ring-1 ring-inset ring-amber-600/10 dark:bg-amber-900/20 dark:text-amber-300"
                            >
                                {modeLabelMap[mode] || mode}
                            </span>
                        ))}
                    </div>
                )}

                {showArtifactImage && (
                    <div className="mt-2.5 space-y-2">
                        <div className="overflow-hidden rounded-lg bg-slate-100/50 dark:bg-white/[0.02]">
                            <button
                                type="button"
                                data-trace-card-action="true"
                                onMouseDown={stopTraceCardAction}
                                onKeyDown={stopTraceCardAction}
                                onClick={(event) => {
                                    stopTraceCardAction(event);
                                    activateTraceSelection({ traceKey, objectType, objectId, page });
                                }}
                                className="block w-full text-left"
                                title={activeRenderExt === 'pdf' && page > 0 ? `定位到第 ${Math.round(page)} 页` : '聚焦当前证据'}
                                aria-label={activeRenderExt === 'pdf' && page > 0 ? `定位到第 ${Math.round(page)} 页` : '聚焦当前证据'}
                            >
                                <img
                                    data-testid="module2-trace-artifact-image"
                                    src={artifactUrl}
                                    alt={`${objectLabel}-preview-${idx + 1}`}
                                    className="h-40 w-full object-contain bg-white/50 p-1.5 dark:bg-transparent sm:h-56"
                                    loading="lazy"
                                />
                            </button>
                        </div>
                        <div className="flex justify-start">
                            <a
                                href={artifactUrl}
                                target="_blank"
                                rel="noreferrer"
                                data-trace-card-action="true"
                                onMouseDown={stopTraceCardAction}
                                onKeyDown={stopTraceCardAction}
                                onClick={stopTraceCardAction}
                                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-2.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-200/80 shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-all hover:bg-slate-50 hover:text-slate-800 active:scale-95 dark:bg-white/[0.02] dark:text-slate-300 dark:ring-white/[0.05] dark:hover:bg-white/[0.04] dark:hover:text-slate-100"
                                style={{ height: '22px', fontSize: '11px' }}
                            >
                                <ExternalLink size={12} />
                                查看截图
                            </a>
                        </div>
                    </div>
                )}

                {objectType === 'figure' && figureSummaryBullets.length > 0 && (
                    <div className="mt-3 rounded-lg bg-[#F8FAFC]/80 px-3 py-2.5 shadow-[inset_0_0_0_1px_rgba(0,0,0,0.03)] dark:bg-white/[0.02] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.05)]">
                        <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-slate-500 dark:text-slate-400">
                            <Sparkles size={10} className="text-blue-500" />
                            关键信息
                        </div>
                        <div className="space-y-2">
                            {figureSummaryBullets.map((bullet, bulletIdx) => (
                                <div
                                    key={`${traceKey}-bullet-${bulletIdx}`}
                                    className="flex items-start gap-2"
                                >
                                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-blue-400 dark:bg-blue-500" />
                                    <p className="text-[11px] leading-relaxed text-slate-700 dark:text-slate-300">
                                        {bullet}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {displayKind === 'table' && tableRows.length > 0 && (
                    <div className="mt-3 overflow-hidden rounded-lg border border-slate-200/60 shadow-[0_1px_3px_rgba(0,0,0,0.02)] dark:border-white/[0.05] dark:bg-white/[0.01]">
                        <div className="flex items-center justify-between border-b border-slate-200/60 bg-[#F8FAFC]/90 px-3 py-2 text-[10px] tabular-nums font-medium text-slate-500 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-400">
                            <span>DataFrame</span>
                        </div>
                        <div className="max-h-72 overflow-auto custom-scrollbar">
                            <table className="min-w-full border-collapse text-[10px] tabular-nums text-slate-700 dark:text-slate-300">
                                <thead className="sticky top-0 z-10 bg-[#F8FAFC]/95 backdrop-blur-md shadow-sm dark:bg-slate-900/80">
                                    <tr>
                                        {(tableHeaders.length > 0 ? tableHeaders : tableRows[0]).map((header, hIdx) => (
                                            <th
                                                key={`table-h-${idx}-${hIdx}`}
                                                className="border-b border-r border-slate-200/60 px-2.5 py-2 text-left font-semibold text-slate-600 last:border-r-0 dark:border-white/[0.05] dark:text-slate-400"
                                            >
                                                {header || `列${hIdx + 1}`}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {tableRows.map((row, rIdx) => (
                                        <tr
                                            key={`table-r-${idx}-${rIdx}`}
                                            className="group transition-colors odd:bg-white even:bg-[#F8FAFC]/60 hover:bg-blue-50/50 dark:odd:bg-transparent dark:even:bg-white/[0.02] dark:hover:bg-white/[0.04]"
                                        >
                                            {(tableHeaders.length > 0 ? tableHeaders : row).map((_, cIdx) => (
                                                <td
                                                    key={`table-c-${idx}-${rIdx}-${cIdx}`}
                                                    className="max-w-[180px] border-b border-r border-slate-100 px-2.5 py-2 align-top break-words last:border-r-0 group-last:border-b-0 dark:border-white/[0.05]"
                                                >
                                                    {String(row[cIdx] ?? '').trim() || <span className="opacity-30">—</span>}
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {displayKind === 'table' && tableRows.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                        <button
                            type="button"
                            data-trace-card-action="true"
                            onMouseDown={stopTraceCardAction}
                            onKeyDown={stopTraceCardAction}
                            onClick={(event) => {
                                stopTraceCardAction(event);
                                void writeClipboard(
                                    tablePreviewToTsv(
                                        tableHeaders.length > 0 ? tableHeaders : tableRows[0],
                                        tableRows
                                    ),
                                    '已复制表格内容'
                                );
                            }}
                            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-2.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-200/80 shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-all hover:bg-slate-50 hover:text-slate-800 active:scale-95 dark:bg-white/[0.02] dark:text-slate-300 dark:ring-white/[0.05] dark:hover:bg-white/[0.04] dark:hover:text-slate-100"
                            style={{ height: '22px', fontSize: '11px' }}
                        >
                            <Copy size={12} />
                            复制表格
                        </button>
                    </div>
                )}
            </div>
        );
    };

    const renderTraceEvidenceContent = ({
        inline = false,
        groups = traceGroups,
        loading = traceLoading,
        error = traceError,
        emptyTitle,
        emptyHint = tracePanelHintText,
        forceGroupLabels = false,
    }: {
        inline?: boolean;
        groups?: ReturnType<typeof buildTraceGroups>;
        loading?: boolean;
        error?: string;
        emptyTitle?: string;
        emptyHint?: string;
        forceGroupLabels?: boolean;
    } = {}) => {
        const showGroupLabels = forceGroupLabels || groups.length > 1;

        return (
            <>
                {loading && (
                    <div className={cn(
                        'flex items-center gap-1.5 rounded-xl border border-blue-200/80 bg-blue-50/80 px-2.5 py-2 text-[10px] tabular-nums font-semibold text-blue-700 dark:border-blue-700/70 dark:bg-blue-900/20 dark:text-blue-300',
                        inline ? 'mb-3' : 'mt-2'
                    )}>
                        <Loader2 size={10} className="animate-spin" />
                        正在同步原文定位…
                    </div>
                )}

                {error && (
                    <p className={cn(
                        'rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[10px] tabular-nums text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300',
                        inline ? 'mb-3' : 'mt-2'
                    )}>
                        {error}
                    </p>
                )}

                {groups.length > 0 ? (
                    <div
                        className={cn(
                            !inline && 'mt-2 rounded-[14px] border border-slate-100/40 bg-white/70 px-2 py-2 dark:border-white/[0.05] dark:bg-white/[0.02]',
                            inline && 'space-y-6'
                        )}
                    >
                        {groups.map((group) => (
                            <div
                                key={`trace-group-${group.key}`}
                                id={inline ? `trace-section-${group.key}` : undefined}
                                data-testid={`module2-trace-group-${group.key}`}
                                className={cn(
                                    !inline && 'last:mb-0', 
                                    inline && 'last:mb-0 scroll-mt-24'
                                )}
                            >
                                {showGroupLabels && (
                                    <div className="mb-3 flex items-center gap-2">
                                        <div
                                            data-testid="module2-trace-group-label"
                                            className={cn(
                                                'px-2 py-0.5 rounded text-[11px] tabular-nums font-bold',
                                                inline
                                                    ? 'text-slate-600 bg-slate-100/80 dark:text-slate-300 dark:bg-white/[0.05]'
                                                    : 'text-slate-600 bg-slate-100/80 dark:text-slate-300 dark:bg-white/[0.05]'
                                            )}
                                        >
                                            {group.label}
                                        </div>
                                        {inline && <div className="h-px flex-1 bg-gradient-to-r from-slate-100 to-transparent dark:from-white/[0.05]"></div>}
                                    </div>
                                )}
                                <div className="space-y-0">
                                    {group.items.map(({ hit, idx }) => renderTraceEvidenceCard(hit, idx))}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : !loading && (
                    <div className={cn(
                        'flex flex-col items-center justify-center rounded-xl border border-slate-200/60 bg-slate-50/50 px-4 py-8 text-center dark:border-white/[0.05] dark:bg-white/[0.02]',
                        inline ? '' : 'mt-2'
                    )}>
                        <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-white/[0.05] dark:text-slate-500">
                            <LocateFixed size={16} />
                        </div>
                        <p className="text-[12px] font-medium text-slate-600 dark:text-slate-300">
                            {emptyTitle || (activeFieldItem ? '当前字段暂无额外证据卡片' : activeDoc ? '暂无相关定位信息' : '尚未生成定位结果')}
                        </p>
                        <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                            {emptyHint}
                        </p>
                    </div>
                )}
            </>
        );
    };

    const renderFieldEvidenceCard = (item: FieldItem) => {
        const isActiveField =
            tracePanelOpen &&
            String(activeFieldKey || '').trim().toLowerCase() === String(item.key || '').trim().toLowerCase();

        return (
            <div
                key={item.key}
                data-testid="module2-field-chip"
                onClick={() => handleFieldCardClick(item)}
                onMouseEnter={() => setHoveredFieldKey(item.key)}
                onMouseLeave={() => setHoveredFieldKey(null)}
                className={cn(
                    "group relative cursor-pointer rounded-xl border p-3 transition-all duration-300 mb-2 shadow-[0_1px_2px_rgba(0,0,0,0.02)]",
                    highlightedFieldKey === item.key
                        ? "border-blue-400 bg-blue-50/60 ring-1 ring-blue-400/50 dark:border-blue-500/50 dark:bg-blue-500/10 dark:ring-blue-500/30"
                        : "border-slate-200/80 bg-white hover:border-slate-300 hover:bg-slate-50/80 hover:shadow-[0_2px_4px_rgba(0,0,0,0.04)] dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:border-white/[0.08] dark:hover:bg-white/[0.04]"
                )}
            >
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                        <div className="mb-1.5 flex items-center gap-2">
                            <span
                                className={cn(
                                    "inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium transition-colors",
                                    highlightedFieldKey === item.key
                                        ? "bg-blue-100/50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400"
                                        : "bg-slate-100/80 text-slate-600 group-hover:bg-slate-200/60 group-hover:text-slate-800 dark:bg-white/[0.04] dark:text-slate-300 dark:group-hover:bg-white/[0.08]"
                                )}
                            >
                                {item.label}
                            </span>
                        </div>
                        <div className="break-words text-[13px] font-medium leading-relaxed text-slate-800 dark:text-slate-200 px-0.5">
                            {item.valueText}
                        </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1.5 mt-0.5">
                        {activeRenderExt === "pdf" && item.pageNumber && (
                            <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium text-slate-500 bg-slate-50/80 ring-1 ring-inset ring-slate-200/80 dark:bg-white/[0.02] dark:ring-white/[0.05] dark:text-slate-400">
                                页 {item.pageNumber}
                            </span>
                        )}
                        <span
                            className={cn(
                                "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-bold ring-1 ring-inset",
                                item.confidence > 0.8
                                    ? "bg-emerald-50/80 ring-emerald-500/20 text-emerald-600 dark:bg-emerald-500/10 dark:ring-emerald-500/20 dark:text-emerald-400"
                                    : "bg-amber-50/80 ring-amber-500/20 text-amber-600 dark:bg-amber-500/10 dark:ring-amber-500/20 dark:text-amber-400"
                            )}
                        >
                            {item.confidence > 0.8 ? <CheckCircle2 size={10} /> : <AlertCircle size={10} />}
                            {Math.floor(item.confidence * 100)}%
                        </span>
                    </div>
                </div>
            </div>
        );
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
        setTracePanelOpen(true);
        setAssistantMessage("已执行回滚：定位高亮已重置，你可以重新选择字段或重新抽取。");
    };

    const syncAssistantEvidence = (
        citations: AssistantCitation[],
        nextLock?: AssistantObjectLock | null,
        options?: { interactive?: boolean },
    ) => {
        const normalizedCitations = Array.isArray(citations) ? citations : [];
        const interactive = Boolean(options?.interactive);
        const effectiveLock = nextLock === undefined ? assistantCurrentLock : nextLock;
        if (nextLock !== undefined) {
            setAssistantCurrentLock(nextLock);
        }
        if (!interactive || !activeDoc) return;

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
                artifact_by_file_url: typeof payload.artifact_by_file_url === 'string' ? payload.artifact_by_file_url : undefined,
                artifact_file_id: typeof payload.artifact_file_id === 'string' ? payload.artifact_file_id : undefined,
                artifact_url: typeof payload.artifact_url === 'string' ? payload.artifact_url : undefined,
                artifact_path: undefined,
            };
            matched.set(toTraceHitKey(synthetic, matched.size), synthetic);
        });

        if (matched.size > 0) {
            setTraceHits(Array.from(matched.values()));
            setTracePanelOpen(true);
        } else if (effectiveLock?.table_id) {
            const lockedHits = docHits.filter(
                (hit) =>
                    String(hit.object_type || '').trim().toLowerCase() === 'table'
                    && String(hit.object_id || '').trim().toLowerCase() === String(effectiveLock.table_id || '').trim().toLowerCase()
            );
            if (lockedHits.length > 0) {
                setTraceHits(lockedHits);
                setTracePanelOpen(true);
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

    const { runAssistantInstruction } = useAssistantStream({
        assistantQueryLoading,
        assistantInput,
        assistantDialog,
        assistantSessionId,
        activeAssistantSessionKey,
        activeDocFileHash: String(activeDoc?.file_hash || '').trim(),
        assistantExtraContext,
        extractionJobApiBaseRef,
        assistantAbortRef,
        fetchExtractWithFallback,
        resolveExtractBase,
        readAssistantSessionMap,
        persistAssistantSessionForFile,
        resetAssistantCompanionState,
        updateAssistantDialogMessage,
        syncAssistantEvidence,
        setAssistantDialog,
        setAssistantQueryLoading,
        setAssistantWarnings,
        setAssistantAnswer,
        setAssistantInput,
        setAssistantMessage,
        setAssistantSessionId,
        setAssistantCompanionCitations,
        setAssistantCompanionActionPreview,
        setAssistantRuntimeEvents,
    });

    const renderAssistantCitations = (citations?: AssistantCitation[] | null, compact = false) => {
        return (
            <AssistantCitationList
                citations={citations}
                compact={compact}
                onSelectCitation={(citation) => {
                    setAssistantCompanionOpen(true);
                    syncAssistantEvidence([citation], undefined, { interactive: true });
                }}
            />
        );
    };

    const renderAssistantActionPreview = (preview?: AssistantActionPreview | null, compact = false) => {
        return <AssistantActionPreviewCard preview={preview} compact={compact} />;
    };

    const renderAssistantDialogMessage = (msg: AssistantDialogMessage, compact = false) => {
        const isLatestAssistantText =
            msg.role === 'assistant' &&
            msg.messageType === 'assistant_text' &&
            msg.id === latestRenderableAssistantMessageId;
        return (
            <AssistantMessageBubble
                key={msg.id}
                message={msg}
                compact={compact}
                isLatestAnswer={isLatestAssistantText}
            />
        );
    };

    const renderAssistantLockBanner = (compact = false) => {
        return <AssistantLockBanner lock={assistantCurrentLock} compact={compact} />;
    };

    const assistantCompanionHasContent = (
        assistantWarnings.length > 0
        || assistantCompanionCitations.length > 0
        || Boolean(assistantCompanionActionPreview)
        || assistantRuntimeEvents.length > 0
    );
    const assistantCompanionSummary = [
        assistantCompanionCitations.length > 0 ? `${assistantCompanionCitations.length} 条依据` : '',
        assistantCompanionActionPreview ? '操作建议' : '',
        assistantWarnings.length > 0 ? `${assistantWarnings.length} 条提示` : '',
        assistantRuntimeEvents.length > 0 ? '本轮进展' : '',
    ].filter(Boolean).join(' · ');

    const renderAssistantCompanionPanel = (compact = false) => {
        if (!assistantCompanionOpen || !assistantCompanionHasContent) {
            return null;
        }
        return (
            <AssistantCompanionPanel
                compact={compact}
                open={assistantCompanionOpen}
                onToggle={() => setAssistantCompanionOpen((prev) => !prev)}
                warnings={assistantWarnings}
                currentLock={assistantCurrentLock}
                citations={assistantCompanionCitations}
                actionPreview={assistantCompanionActionPreview}
                runtimeEvents={assistantRuntimeEvents}
                renderLockBanner={renderAssistantLockBanner}
                renderCitations={renderAssistantCitations}
                renderActionPreview={renderAssistantActionPreview}
            />
        );
    };

    const resetPaneWidth = (side: PaneResizeSide) => {
        const viewportWidth = resolvePaneLayoutViewportWidth();
        const stageDefaults = resolveWorkbenchPaneLayoutDefaults(viewportWidth, currentPaneLayoutStage);
        setPaneLayout((prev) =>
            clampWorkbenchPaneLayout(
                {
                    ...prev,
                    leftWidth: side === 'left' ? stageDefaults.leftWidth : prev.leftWidth,
                    rightWidth: side === 'right' ? stageDefaults.rightWidth : prev.rightWidth,
                },
                viewportWidth,
                showLeftPanel,
            ),
        );
    };

    const startPaneResize = (side: PaneResizeSide, event: React.PointerEvent<HTMLElement>) => {
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

    const effectiveCenterSafeWidth = resolveCenterPaneSafeWidth(workbenchViewportWidth);
    const workbenchGridMinWidth = selectedFiles.length === 0
        ? effectiveCenterSafeWidth
        : (showLeftPanel
            ? paneLayout.leftWidth + paneLayout.rightWidth + (PANE_DIVIDER_WIDTH * 2) + effectiveCenterSafeWidth
            : paneLayout.rightWidth + PANE_DIVIDER_WIDTH + effectiveCenterSafeWidth);
             
    const workbenchGridStyle = selectedFiles.length === 0
        ? {
            gridTemplateColumns: `minmax(0,1fr)`,
            minWidth: `${workbenchGridMinWidth}px`,
          }
        : (showLeftPanel
            ? {
                gridTemplateColumns: `${paneLayout.leftWidth}px ${PANE_DIVIDER_WIDTH}px minmax(0,1fr) ${PANE_DIVIDER_WIDTH}px ${paneLayout.rightWidth}px`,
                minWidth: `${workbenchGridMinWidth}px`,
            }
            : {
                gridTemplateColumns: `minmax(0,1fr) ${PANE_DIVIDER_WIDTH}px ${paneLayout.rightWidth}px`,
                minWidth: `${workbenchGridMinWidth}px`,
            });
    const extractionOverallRatio = estimateRuntimeExtractionOverallRatio(
        extractionJob,
        progressNowMs,
    );
    const extractionOverallPercent = clampProgressPercent(extractionOverallRatio);
    const extractionOverallPercentLabel = formatProgressPercent(
        extractionOverallRatio,
        extractionJob?.terminal ? 0 : 1,
    );
    const extractionTotalFiles = Math.max(
        0,
        Number(extractionJob?.progress?.total_files || selectedFiles.length || 0),
    );
    const canRunActiveExtraction = Boolean(activeSourceFile);
    const activeExtractActionLabel = isProcessing
        ? extractionTotalFiles > 1
            ? `正在解析文件（${extractionOverallPercentLabel}）`
            : `正在解析当前文件（${extractionOverallPercentLabel}）`
        : activeParsedDocument
            ? '重新解析当前文件'
            : '解析当前文件';
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
    // Narrower desktop widths need denser chrome so the right-side smart unit tabs
    // remain inside the visible pane and stay genuinely clickable.
    const useCompactWorkbenchChrome = workbenchViewportWidth > 0 && workbenchViewportWidth <= 1600;
    const useDenseWorkbenchChrome = workbenchViewportWidth > 0 && workbenchViewportWidth <= 1366;
    const useUltraDenseWorkbenchChrome = workbenchViewportWidth > 0 && workbenchViewportWidth <= 1180;
    const smartUnitActivePanelState = { opacity: 1, x: 0, y: 0, scale: 1 };
    const smartUnitLeftHiddenPanelState = prefersReducedMotion
        ? { opacity: 0, x: 0, y: 0, scale: 1 }
        : { opacity: 0, x: -8, y: 1, scale: 0.997 };
    const smartUnitRightHiddenPanelState = prefersReducedMotion
        ? { opacity: 0, x: 0, y: 0, scale: 1 }
        : { opacity: 0, x: 8, y: 1, scale: 0.997 };
    const showTraceOverlay = false;
    const previewControlsDisabled = !hasPreviewContent;
    const previewScaleLabel = activeRenderExt === 'pdf'
        ? (
            scale === 1
                ? (pdfViewMode === 'fit-width' ? '适宽' : pdfViewMode === 'fit-page' ? '整页' : '100%')
                : `${Math.round(scale * 100)}%`
        )
        : `${Math.round(scale * 100)}%`;
    const previewFocusButtonTitle = '聚焦预览并隐藏文档列表';
    const restoreFolderButtonTitle = '展开文档列表并退出聚焦预览';
    const leftQueueAccessButtonTitle = shouldUseLeftQueueDrawer
        ? (showLeftQueueDrawer ? '收起文件/队列' : '打开文件/队列')
        : (showLeftPanel ? '收起文件/队列' : '展开文件/队列');
    const topBarQueueButtonLabel = useUltraDenseWorkbenchChrome ? '文件' : useDenseWorkbenchChrome ? '文件' : '文件/队列';
    const topBarExtractButtonLabel = useUltraDenseWorkbenchChrome
        ? (isProcessing ? '解析中' : activeParsedDocument ? '重解析' : '解析')
        : activeExtractActionLabel;
    const previewToolbarTitle = useUltraDenseWorkbenchChrome ? '预览' : '文档预览';
    const filePipelineStats = useMemo(() => {
        let completed = 0;
        let failed = 0;
        let processing = 0;
        let queued = 0;

        selectedFiles.forEach((file, index) => {
            const jobFile = pickExtractionJobFileState(extractionJob, file, index);
            const doc = pickDocumentResultForFile(documents, file, index);

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
    const activeErrorMessages = useMemo(
        () => sanitizeExtractUiErrorList(activeDoc?.errors ?? []),
        [activeDoc?.errors],
    );
    const activeSoftWarningLabels = useMemo(
        () => getDisplaySoftWarnings(activeDoc),
        [activeDoc],
    );
    const activeIssueCount = activeErrorMessages.length + activeSoftWarningLabels.length;
    const shouldRenderSpreadsheetPreview = activeRenderExt === 'xlsx'
        && !isProcessing
        && (Boolean(activeDoc) || documents.length > 0);
    const isSpreadsheetPreviewStage = activeRenderExt === 'xlsx' && shouldRenderSpreadsheetPreview;
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
                detail: `${fieldItems.length} 个字段、${documentTraceHitCount} 条原文定位已可联动查看`,
                tone: 'emerald' as const,
            };
        }
        if (selectedFiles.length > 0) {
            return {
                label: '等待启动',
                detail: `已载入 ${selectedFiles.length} 份文档，可切换到当前文档后单独开始解析`,
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
        documentTraceHitCount,
        selectedFiles.length,
        traceLoading,
    ]);
    const resultsStateCardMeta = useMemo(() => {
        const firstDocError = sanitizeExtractUiErrorMessage(activeDoc?.errors?.[0]);
        const firstDocWarning = String(activeSoftWarningLabels[0] || '').trim();
        const primaryDocName = activeDoc?.file_name || activeSourceFile?.name || selectedFiles[0]?.name || '';
        const activeDocFieldCount = countExtractionDocumentFields(activeDoc);
        const activeDocQuality = getExtractionDocumentQualityStatus(activeDoc);

        const visibleErrorMessage = sanitizeExtractUiErrorMessage(errorMessage);
        if (visibleErrorMessage) {
            return {
                title: '当前结果需要核验',
                detail: visibleErrorMessage,
                context: primaryDocName ? `当前文档：${primaryDocName}` : '请检查本批次解析状态',
            };
        }

        if (firstDocError) {
            return {
                title: '当前未提取到可展示字段',
                detail: firstDocError,
                context: primaryDocName ? `当前文档：${primaryDocName}` : '请检查文档内容后重试',
            };
        }

        if (isProcessing) {
            return {
                title: '正在解析文档',
                detail: String(moduleStatusMeta.detail || '').trim() || '结果会随解析进度逐步更新。',
                context: primaryDocName
                    ? `当前文档：${primaryDocName}`
                    : selectedFiles.length > 0
                        ? `已载入 ${selectedFiles.length} 份文档`
                        : '结果会在这里集中呈现',
            };
        }

        if (activeDoc && documents.length > 0) {
            if (isStaleRetryableExtractionDocument(activeDoc)) {
                return {
                    title: '检测到上次低质量结果',
                    detail: '该结果曾受限流或超时影响，字段可能不完整，建议重新解析当前文件。',
                    context: primaryDocName ? `当前文档：${primaryDocName}` : '建议重新发起当前文件解析',
                };
            }

            if (!firstDocWarning && activeDocFieldCount > 0) {
                return {
                    title: activeDocQuality === 'degraded' ? '当前结果已生成，建议复核' : '当前结果已生成',
                    detail: activeDocQuality === 'degraded'
                        ? '当前结果已生成，但质量状态为降级，建议结合原文复核。'
                        : '字段结果已经生成，可继续查看证据定位与智能助手解读。',
                    context: primaryDocName ? `当前文档：${primaryDocName}` : '结果将在这里集中呈现',
                };
            }
        }

        if (activeDoc && documents.length > 0) {
            return {
                title: firstDocWarning ? '当前结果需要人工确认' : '当前未提取到可展示字段',
                detail: firstDocWarning || '请检查文档内容，或稍后重新发起解析。',
                context: primaryDocName ? `当前文档：${primaryDocName}` : '结果将在这里集中呈现',
            };
        }

        if (selectedFiles.length > 0) {
            return {
                title: '等待开始解析',
                detail: '已选择文档，请切换到当前文档后单独开始解析。',
                context: primaryDocName ? `当前文档：${primaryDocName}` : `已载入 ${selectedFiles.length} 份文档`,
            };
        }

        return {
            title: '等待结果',
            detail: '请先在中部区域导入文档，结果会在这里集中呈现。',
            context: '支持字段联动定位与后续助手协同分析',
        };
    }, [activeDoc, activeSoftWarningLabels, documents.length, errorMessage, isProcessing, moduleStatusMeta.detail, selectedFiles]);
    const hasImportedFiles = selectedFiles.length > 0 || documents.length > 0 || Boolean(activeSourceFile);
    const smartUnitTabs: Array<{ id: SmartUnitTabId; label: string }> = [
        { id: 'results', label: '提取结果' },
        { id: 'assistant', label: '智能助手' },
    ];
    const assistantPanel = (
        <div className="flex h-full min-h-0 flex-col overflow-hidden bg-white dark:bg-[#0B1120]">
            <div className={cn(
                "bg-white dark:bg-none dark:bg-white/[0.02]",
                useUltraDenseWorkbenchChrome ? "px-3 py-2.5" : "px-4 py-3"
            )}>
                <div className={cn(
                    "flex items-start justify-between",
                    useUltraDenseWorkbenchChrome ? "gap-2" : "gap-2.5"
                )}>
                    <div className={cn("flex min-w-0 items-start", useUltraDenseWorkbenchChrome ? "gap-1" : useDenseWorkbenchChrome ? "gap-1" : "gap-1.5")}>
                        <img src={iconErnieBot} alt="智能助手" className={cn("shrink-0 object-contain", useUltraDenseWorkbenchChrome ? "h-[18px] w-[18px] translate-y-[1px]" : "h-[20px] w-[20px]", useDenseWorkbenchChrome ? "translate-y-[0px]" : "translate-y-[1px]")} />
                        <div className="min-w-0">
                            <h3 className={cn("truncate font-semibold tracking-[0.01em] text-slate-800 dark:text-slate-200", useUltraDenseWorkbenchChrome ? "text-[11.5px]" : useDenseWorkbenchChrome ? "text-[12px]" : "text-[13px]")}>
                                智能助手
                            </h3>
                            {!useUltraDenseWorkbenchChrome && (
                                <p className="mt-0.5 text-[11px] leading-[1.35] text-slate-400 dark:text-slate-500">
                                    面向当前文档的提问、摘要与修正协同
                                </p>
                            )}
                        </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                        {assistantCompanionHasContent && (
                            <button
                                type="button"
                                onClick={() => setAssistantCompanionOpen((prev) => !prev)}
                                className={cn(
                                    "inline-flex items-center gap-1 rounded-full border font-medium transition-all",
                                    useUltraDenseWorkbenchChrome ? "h-[24px] px-2" : "h-[26px] px-2.5 text-[11px]",
                                    assistantCompanionOpen
                                        ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-300"
                                        : "border-slate-200 bg-white text-slate-500 hover:border-blue-200 hover:text-blue-600 dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-slate-400 dark:hover:border-blue-500/30 dark:hover:text-blue-300"
                                )}
                                aria-label="查看辅助信息"
                                title={assistantCompanionSummary || '查看辅助信息'}
                            >
                                <Layout size={12} />
                                {!useUltraDenseWorkbenchChrome && <span>辅助信息</span>}
                                {assistantCompanionCitations.length > 0 && (
                                    <span className="rounded-full bg-white/80 px-1.5 py-0.5 text-[10px] leading-none text-current ring-1 ring-inset ring-current/10 dark:bg-white/[0.08]">
                                        {assistantCompanionCitations.length}
                                    </span>
                                )}
                            </button>
                        )}
                        <button
                        onClick={() => setShowAssistantHelp(true)}
                        className={cn(
                            "inline-flex shrink-0 items-center justify-center rounded-md text-slate-400 transition-all hover:bg-slate-50 hover:text-blue-600 active:scale-95 dark:text-slate-500 dark:hover:bg-white/[0.08] dark:hover:text-blue-400",
                            useUltraDenseWorkbenchChrome ? "h-[22px] w-[22px]" : "h-[24px] w-[24px]"
                        )}
                        aria-label="查看助手功能说明"
                        title="查看助手功能说明"
                    >
                        <HelpCircle size={13} />
                    </button>
                    </div>
                </div>
            </div>

            <div className="flex min-h-0 flex-1 flex-col">
                <div ref={assistantDialogRef} data-testid="module2-assistant-dialog" className={cn(
                    "relative flex min-h-0 flex-1 flex-col overflow-y-auto custom-scrollbar",
                    useUltraDenseWorkbenchChrome ? "px-3 py-3" : "px-4 py-4"
                )}>
                    {renderableAssistantDialog.length === 0 ? (
                        <div className={cn(
                            "flex h-full flex-col items-center justify-center px-4",
                            useUltraDenseWorkbenchChrome ? "pb-8" : "pb-12"
                        )}>
                            <div className={cn(
                                "text-slate-300 dark:text-slate-600/80",
                                useUltraDenseWorkbenchChrome ? "mb-4" : "mb-5"
                            )}>
                                <Sparkles size={useUltraDenseWorkbenchChrome ? 34 : 42} strokeWidth={1.2} />
                            </div>
                            <h2 className={cn(
                                "font-medium tracking-tight text-slate-700 dark:text-slate-300",
                                useUltraDenseWorkbenchChrome ? "text-[16px]" : "text-[18px]"
                            )}>
                                今天我能帮您些什么？
                            </h2>
                        </div>
                    ) : (
                        <div className={cn(
                            "flex flex-col",
                            useUltraDenseWorkbenchChrome ? "space-y-4" : "space-y-5"
                        )}>
                            {renderableAssistantDialog.map((msg) => renderAssistantDialogMessage(msg))}
                            <div className="h-3" />
                        </div>
                    )}
                </div>

                {renderAssistantCompanionPanel()}

                <div className={cn(
                    "relative z-10",
                    useUltraDenseWorkbenchChrome ? "px-3 pb-3.5 pt-1.5" : "px-4 pb-5 pt-2"
                )}>
                    <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-white via-white/95 to-transparent dark:from-[#0B1120] dark:via-[#0B1120]/95" />
                    <div className="relative z-10">
                        <AssistantComposerStatus
                            isLoading={assistantQueryLoading}
                            streamingMessage={latestStreamingAssistantMessage}
                        />
                        <div
                            className="relative flex flex-col rounded-[24px] border-0 bg-white shadow-[0_2px_16px_rgba(0,0,0,0.04)] ring-1 ring-slate-200/50 transition-all focus-within:shadow-[0_8px_30px_rgba(0,0,0,0.08)] focus-within:ring-slate-300 dark:bg-[#1A1D24] dark:ring-white/[0.05] dark:focus-within:shadow-[0_8px_30px_rgba(0,0,0,0.3)] dark:focus-within:ring-white/[0.1]"
                            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                            onDrop={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                const files = Array.from(e.dataTransfer.files) as File[];
                                if (files.length > 0) {
                                    mergeSelectedFiles(files);
                                }
                            }}
                        >
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
                                placeholder="在这里输入您的问题或指令..."
                                className={cn(
                                    "w-full resize-none bg-transparent text-slate-800 placeholder:text-slate-400 outline-none dark:text-slate-200 custom-scrollbar",
                                    useUltraDenseWorkbenchChrome
                                        ? "max-h-[168px] min-h-[46px] px-3.5 pt-3.5 pb-0 text-[14px] leading-relaxed"
                                        : "max-h-[200px] min-h-[52px] px-4 pt-4 pb-0 text-[15px] leading-relaxed"
                                )}
                            />
                            <div className={cn(
                                "flex items-center justify-between pt-1",
                                useUltraDenseWorkbenchChrome ? "px-2.5 pb-2.5" : "px-3 pb-3"
                            )}>
                                <div className="flex items-center gap-1.5">
                                    <button
                                        type="button"
                                        onClick={() => fileInputRef.current?.click()}
                                        className={cn(
                                            "group relative flex items-center justify-center rounded-full text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:text-slate-400 dark:hover:bg-white/[0.1] dark:hover:text-slate-200",
                                            useUltraDenseWorkbenchChrome ? "h-[32px] w-[32px]" : "h-[36px] w-[36px]"
                                        )}
                                        title="上传文档进行分析"
                                        aria-label="上传文档进行分析"
                                    >
                                        <Plus size={useUltraDenseWorkbenchChrome ? 18 : 20} strokeWidth={2} className="transition-transform group-hover:scale-110" />
                                    </button>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        type="button"
                                        data-testid="module2-assistant-send"
                                        onClick={() => void runAssistantInstruction()}
                                        disabled={!assistantQueryLoading && !assistantInput.trim()}
                                        className={cn(
                                            'group relative flex items-center justify-center rounded-full transition-all duration-200',
                                            useUltraDenseWorkbenchChrome ? 'h-[32px] w-[32px]' : 'h-[36px] w-[36px]',
                                            !assistantQueryLoading && !assistantInput.trim()
                                                ? 'cursor-not-allowed bg-[#F3F4F6] text-[#A1A1AA] dark:bg-white/[0.05] dark:text-slate-600'
                                                : assistantQueryLoading
                                                    ? 'bg-slate-800 text-white shadow-sm hover:bg-slate-900 active:scale-95 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100'
                                                    : 'bg-slate-900 text-white shadow-sm hover:bg-black hover:shadow active:scale-95 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100'
                                        )}
                                        title={assistantQueryLoading ? "停止本次回答" : "发送"}
                                        aria-label={assistantQueryLoading ? "停止本次回答" : "发送"}
                                    >
                                        {assistantQueryLoading ? <X size={useUltraDenseWorkbenchChrome ? 15 : 16} /> : <ArrowUp size={useUltraDenseWorkbenchChrome ? 16 : 18} strokeWidth={2.5} className="transition-transform group-hover:-translate-y-0.5" />}
                                    </button>
                                </div>
                            </div>
                        </div>
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
        <div className="module2-workbench relative flex h-[100dvh] flex-col overflow-hidden bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-module2-primary-bg/40 via-module2-bg to-module2-primary-bg/40 p-0 text-module2-text-primary">
            <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
                {/* Enhanced bright theme background elements for more highlights and depth */}
                <div className="absolute -top-[10%] -left-[5%] w-[60%] h-[60%] rounded-full bg-gradient-to-br from-blue-400/20 to-sky-500/20 blur-[100px] dark:from-blue-500/10 dark:to-sky-500/10" />
                <div className="absolute top-[10%] -right-[5%] w-[50%] h-[50%] rounded-full bg-gradient-to-bl from-blue-400/20 to-cyan-500/15 blur-[100px] dark:from-blue-500/10 dark:to-cyan-500/10" />
                <div className="absolute bottom-[0%] left-[10%] w-[50%] h-[50%] rounded-full bg-gradient-to-tr from-sky-400/15 to-cyan-400/15 blur-[100px] dark:from-sky-500/10 dark:to-cyan-500/10" />
                <div className="absolute top-[30%] left-[30%] w-[40%] h-[40%] rounded-full bg-cyan-400/10 blur-[80px] dark:bg-blue-500/10" />
                <div className="absolute -bottom-[10%] right-[10%] w-[40%] h-[40%] rounded-full bg-blue-400/20 blur-[100px] dark:bg-blue-900/10" />
                <div
                    className="absolute inset-0 opacity-[0.6] mix-blend-multiply dark:opacity-[0.2] dark:mix-blend-normal bg-[radial-gradient(circle_at_1px_1px,_rgba(15,23,42,0.08)_1px,_transparent_0)] bg-[length:32px_32px]"
                />
            </div>
            <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx,.xlsx,.txt,.md,.png,.jpg,.jpeg,.bmp,.webp,.tif,.tiff"
                multiple
                aria-label="上传待提取文档"
                title="上传待提取文档"
                className="hidden"
                data-testid="module2-file-input"
                onChange={onSelectFiles}
            />

            {selectedFiles.length > 0 && (
                <motion.section
                    data-testid="module2-top-bar"
                    initial={{ opacity: 0, y: -12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                    className={cn(
                        'relative z-10 shrink-0 bg-[#fbfcfd]/90 backdrop-blur-xl border-b border-slate-200/40 shadow-[0_2px_12px_rgba(0,0,0,0.03)] dark:bg-slate-950/95 dark:border-white/5 dark:shadow-[0_4px_16px_rgba(0,0,0,0.4)]',
                        useUltraDenseWorkbenchChrome
                            ? 'pl-3 pr-0 py-1.5'
                            : useDenseWorkbenchChrome
                            ? 'pl-4 pr-0 py-1.5'
                            : useCompactWorkbenchChrome
                                ? 'pl-4 pr-0 py-2'
                                : 'pl-4 pr-0 py-2.5'
                    )}
                >
                    <div className={cn(
                        'flex flex-wrap items-center justify-between gap-x-4 gap-y-2',
                        useUltraDenseWorkbenchChrome ? 'gap-x-2.5 gap-y-1' : useDenseWorkbenchChrome && 'gap-x-3 gap-y-1'
                    )}>
                        <div className={cn("flex-1", useUltraDenseWorkbenchChrome ? 'min-w-[160px]' : 'min-w-[210px]')}>
                            <div className={cn("flex items-center", useUltraDenseWorkbenchChrome ? '-ml-2.5' : '-ml-5')}>
                                <img 
                                    src={module2Svg} 
                                    alt="非结构化文档分析" 
                                    className={cn(
                                        "w-auto object-contain transition-all duration-300 origin-left scale-[3.0] translate-y-1",
                                        useUltraDenseWorkbenchChrome ? "h-[24px] mr-[70px]" : useDenseWorkbenchChrome ? "h-[28px] mr-[96px]" : "h-[36px] mr-[126px]"
                                    )} 
                                />
                                <div className={cn(
                                    "flex items-center space-x-[1px] font-['Microsoft_YaHei'] font-bold tracking-widest translate-y-1",
                                    useUltraDenseWorkbenchChrome ? "text-[15px] ml-0" : useDenseWorkbenchChrome ? "text-[18px] ml-0.5" : "text-[23px] ml-1"
                                )}>
                                    <span className="text-[#334155] dark:text-slate-200">AI</span>
                                    <span className="text-[#3b82f6] dark:text-blue-400">信息抽取</span>
                                </div>
                            </div>
                        </div>

                        <div 
                            className={cn(
                                'flex flex-nowrap items-center justify-end',
                                !paneResizeSide && 'transition-all duration-300 ease-out',
                                useDenseWorkbenchChrome 
                                    ? 'gap-1.5 pr-4' 
                                    : useCompactWorkbenchChrome
                                        ? 'gap-1.5 pr-5'
                                        : 'gap-2 pr-6'
                            )}
                        >
                            <button
                                type="button"
                                onClick={toggleLeftQueueAccess}
                                className={cn(
                                    'group inline-flex shrink-0 whitespace-nowrap items-center justify-center rounded-full border font-medium transition-all duration-200 active:scale-95',
                                    useUltraDenseWorkbenchChrome ? 'h-[24px] px-2.5 text-[11px]' : useDenseWorkbenchChrome ? 'h-[26px] px-3 text-[12px]' : 'h-[28px] px-3.5 text-[12px]',
                                    (showLeftPanel || showLeftQueueDrawer)
                                        ? 'border-blue-200 bg-blue-50 text-blue-700 shadow-sm hover:bg-blue-100 dark:border-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300 dark:hover:bg-blue-500/20'
                                        : 'border-slate-200/80 bg-white text-slate-600 shadow-[0_1px_2px_rgba(0,0,0,0.04)] hover:bg-slate-50 hover:text-slate-800 hover:border-slate-300 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300 dark:hover:bg-white/[0.1] dark:hover:text-slate-100'
                                )}
                                title={
                                    shouldUseLeftQueueDrawer
                                        ? (showLeftQueueDrawer ? '收起文件/队列' : '打开文件/队列')
                                        : (showLeftPanel ? '收起文件/队列' : '展开文件/队列')
                                }
                                aria-label={
                                    shouldUseLeftQueueDrawer
                                        ? (showLeftQueueDrawer ? '收起文件/队列' : '打开文件/队列')
                                        : (showLeftPanel ? '收起文件/队列' : '展开文件/队列')
                                }
                            >
                                <div className="flex items-center gap-1.5">
                                    <FolderOpen size={13} className="transition-transform duration-200 group-hover:scale-110" />
                                    <span>{topBarQueueButtonLabel}</span>
                                </div>
                            </button>
                            <button
                                type="button"
                                onClick={runExtraction}
                                data-testid="module2-start-extract"
                                disabled={!canRunActiveExtraction || isProcessing}
                                className={cn(
                                    'group inline-flex shrink-0 whitespace-nowrap items-center justify-center rounded-full font-medium transition-all duration-200 active:scale-95 ring-1 ring-transparent',
                                    useUltraDenseWorkbenchChrome ? 'h-[24px] px-2.5 text-[11px]' : useDenseWorkbenchChrome ? 'h-[26px] px-3 text-[12px]' : 'h-[28px] px-4 text-[12px]',
                                    canRunActiveExtraction && !isProcessing
                                        ? 'bg-blue-600 text-white shadow-sm hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500'
                                        : 'cursor-not-allowed bg-slate-100 text-slate-400 shadow-none dark:bg-white/[0.05] dark:text-slate-500'
                                )}
                            >
                                <div className="flex items-center gap-1.5">
                                    {isProcessing ? <Loader2 size={13} className="animate-spin" /> : <PlayCircle size={13} className="transition-transform duration-200 group-hover:scale-110" />}
                                    <span>{topBarExtractButtonLabel}</span>
                                </div>
                            </button>
                            {documents.length > 0 && (
                                <button
                                    type="button"
                                    onClick={exportResults}
                                    className={cn(
                                        'group inline-flex shrink-0 whitespace-nowrap items-center justify-center rounded-full border border-slate-200/80 bg-white font-medium text-slate-600 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-all hover:bg-slate-50 hover:text-slate-800 hover:border-slate-300 active:scale-95 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300 dark:hover:bg-white/[0.1] dark:hover:text-slate-100',
                                        useUltraDenseWorkbenchChrome ? 'h-[24px] px-2.5 text-[11px]' : useDenseWorkbenchChrome ? 'h-[26px] px-3 text-[12px]' : 'h-[28px] px-3.5 text-[12px]'
                                    )}
                                >
                                    <div className="flex items-center gap-1.5">
                                        <Download size={13} className="opacity-70 transition-transform duration-200 group-hover:scale-110" />
                                        {!useUltraDenseWorkbenchChrome && <span>导出</span>}
                                    </div>
                                </button>
                            )}
                            {canClearWorkbenchData && (
                                <button
                                    type="button"
                                    onClick={clearWorkbenchData}
                                    data-testid="module2-clear-data"
                                    disabled={isProcessing}
                                    className={cn(
                                        'group inline-flex shrink-0 whitespace-nowrap items-center justify-center rounded-full font-medium transition-all duration-300 ease-spring-gentle',
                                        useUltraDenseWorkbenchChrome ? 'h-[24px] px-2 text-[11px]' : useDenseWorkbenchChrome ? 'h-[26px] px-2 text-[12px]' : 'h-[28px] px-2.5 text-[12px]',
                                        !isProcessing
                                            ? 'text-slate-500 hover:bg-red-50 hover:text-red-600 active:scale-95 dark:text-slate-400 dark:hover:bg-red-500/10 dark:hover:text-red-400'
                                            : 'cursor-not-allowed text-slate-300 dark:text-slate-600'
                                    )}
                                >
                                    <div className="flex items-center gap-1.5">
                                        <Trash2 size={13} className="opacity-80 transition-transform duration-200 group-hover:scale-110" />
                                        {!useUltraDenseWorkbenchChrome && <span>清空</span>}
                                    </div>
                                </button>
                            )}
                        </div>
                    </div>
                </motion.section>
            )}

            <div ref={workbenchViewportRef} className="relative z-10 min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
                <div
                    className={cn(
                        'relative grid h-full min-h-0 overflow-hidden rounded-none border-0 bg-transparent shadow-none ring-0',
                        !paneResizeSide && 'transition-[grid-template-columns] duration-300 ease-out'
                    )}
                    style={workbenchGridStyle}
                >
                    {showLeftQueueDrawer && (
                        <button
                            type="button"
                            onClick={closeLeftQueueDrawer}
                            className="absolute inset-0 z-30 bg-slate-950/16 backdrop-blur-[2px]"
                            aria-label="关闭文件队列抽屉"
                        />
                    )}

                    {(showLeftPanel || showLeftQueueDrawer) && selectedFiles.length > 0 && (
                        <div
                            id="module2-left-panel"
                            data-testid="module2-left-panel"
                            className={cn(
                                "z-40 flex min-h-0 flex-col",
                                showLeftQueueDrawer
                                    ? "absolute inset-y-3 left-3 w-[min(360px,calc(100%-24px))] overflow-hidden rounded-[24px] border border-slate-200/70 bg-white shadow-[0_24px_60px_-28px_rgba(15,23,42,0.32)] dark:border-white/[0.08] dark:bg-slate-950 dark:shadow-[0_28px_72px_-34px_rgba(2,6,23,0.9)]"
                                    : "relative h-full"
                            )}
                        >
                            <div
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                className={cn(
                                    "relative flex flex-1 min-h-[300px] flex-col overflow-hidden bg-white shadow-[1px_0_10px_rgba(0,0,0,0.02)] transition-colors duration-200 dark:bg-white/[0.02] backdrop-blur-xl dark:border-r dark:border-white/[0.05]",
                                    isUploaderDragOver
                                        ? "bg-blue-50/60 ring-2 ring-inset ring-blue-400/50 dark:bg-blue-900/20 dark:ring-blue-500/50"
                                        : ""
                                )}
                            >
                                <div className={cn(
                                    "relative z-20 flex items-center w-full px-4 bg-white/80 backdrop-blur-md border-b border-slate-200/60 shadow-[0_4px_12px_rgba(0,0,0,0.05)] transition-colors duration-200 dark:bg-white/[0.02] dark:border-b dark:border-white/[0.05] dark:shadow-[0_4px_12px_rgba(0,0,0,0.2)]",
                                    useDenseWorkbenchChrome ? "h-[40px]" : "h-[48px]"
                                )}>
                                    <div className="flex w-full items-center justify-between gap-3">
                                        <div className="flex min-w-0 items-center gap-1">
                                            <img src={iconDocumentQueue} alt="文档队列" className="h-[18px] w-[18px] object-contain" />
                                            <h3 className={cn(
                                                "truncate font-semibold tracking-tight text-slate-800 dark:text-slate-200",
                                                useDenseWorkbenchChrome ? "text-xs" : "text-sm"
                                            )}>
                                                文档队列
                                            </h3>
                                        </div>
                                        {showLeftQueueDrawer && (
                                            <button
                                                type="button"
                                                onClick={closeLeftQueueDrawer}
                                                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:text-slate-400 dark:hover:bg-white/[0.08] dark:hover:text-slate-200"
                                                title="关闭文件队列"
                                                aria-label="关闭文件队列"
                                            >
                                                <X size={16} />
                                            </button>
                                        )}
                                    </div>
                                </div>

                                <div className="min-h-0 flex-1 overflow-y-auto bg-transparent p-3 custom-scrollbar">
                                    {selectedFiles.length === 0 ? (
                                        <div className="flex h-full flex-col items-center justify-center gap-2.5 text-center">
                                            <div className="flex h-10 w-10 items-center justify-center rounded-[10px] bg-white/50 border border-slate-200/60 shadow-[0_1px_3px_rgba(0,0,0,0.02)] dark:bg-white/[0.02] dark:border-white/5 dark:shadow-none">
                                                <FolderOpen size={16} className="text-slate-400 dark:text-slate-500" strokeWidth={1.5} />
                                            </div>
                                            <div>
                                                <p className="text-[12px] font-medium tracking-tight text-slate-600 dark:text-slate-300">暂无文档队列</p>
                                                <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">拖拽文件或点击上方按钮添加</p>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="flex flex-col gap-1">
                                            {selectedFiles.map((file, index) => {
                                                const isActive = activeSourceFile && fileIdentityKey(activeSourceFile) === fileIdentityKey(file);
                                                const ext = file.name.split('.').pop()?.toLowerCase();

                                                let FileIcon = File;
                                                let iconColorClass = "text-slate-500";
                                                let customIconSrc = null;

                                                if (ext === 'pdf') {
                                                    customIconSrc = iconPdf;
                                                } else if (['xls', 'xlsx', 'csv'].includes(ext || '')) {
                                                    customIconSrc = iconXlsx;
                                                } else if (['doc', 'docx'].includes(ext || '')) {
                                                    customIconSrc = iconWord;
                                                } else if (['txt', 'md'].includes(ext || '')) {
                                                    customIconSrc = iconTxt;
                                                } else if (['jpg', 'jpeg', 'png', 'gif'].includes(ext || '')) {
                                                    FileIcon = FileImage;
                                                    iconColorClass = "text-purple-500";
                                                }

                                                // Status Logic
                                                const doc = pickDocumentResultForFile(documents, file, index);
                                                const jobFile = pickExtractionJobFileState(extractionJob, file, index);
                                                let statusText = "等待队列...";
                                                let statusColor = "text-slate-400";
                                                let StatusIndicator = <div className="h-2 w-2 rounded-full bg-slate-300 dark:bg-slate-600" />;

                                                if (jobFile && !extractionJob?.terminal) {
                                                    const estimatedProgressRatio = estimateRuntimeExtractionFileRatio(
                                                        extractionJob,
                                                        jobFile,
                                                        progressNowMs,
                                                    );
                                                    const progress = clampProgressPercent(estimatedProgressRatio);
                                                    const progressLabel = formatProgressPercent(estimatedProgressRatio, 1);
                                                    const progressWidth = Math.max(
                                                        estimatedProgressRatio * 100,
                                                        jobFile.status === 'queued' ? 8 : 4,
                                                    );
                                                    const message = String(jobFile.message || toExtractionStageLabel(jobFile.stage) || '正在解析').trim() || '正在解析';
                                                    if (jobFile.status === 'failed') {
                                                        statusText = jobFile.error ? `解析失败：${jobFile.error}` : '解析失败';
                                                        statusColor = "text-red-500";
                                                        StatusIndicator = <div className="h-2 w-2 rounded-full bg-red-500" />;
                                                    } else if (jobFile.status === 'completed') {
                                                        statusText = jobFile.message || '解析完成';
                                                        statusColor = "text-emerald-600";
                                                        StatusIndicator = <div className="h-2 w-2 rounded-full bg-emerald-500" />;
                                                    } else {
                                                        statusText = progress > 0 ? `${message} ${progressLabel}` : message;
                                                        statusColor = jobFile.status === 'queued' ? "text-slate-400" : "text-slate-500";
                                                        StatusIndicator = (
                                                            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-white/[0.1]">
                                                                <div
                                                                    className="h-full bg-gradient-to-r from-sky-500 via-blue-500 to-cyan-400 transition-[width] duration-700 ease-out"
                                                                    style={{ width: `${progressWidth}%` }}
                                                                />
                                                            </div>
                                                        );
                                                    }
                                                } else if (jobFile) {
                                                    if (jobFile.status === 'failed') {
                                                        const visibleJobFileError = sanitizeExtractUiErrorMessage(jobFile.error);
                                                        statusText = visibleJobFileError ? `解析失败：${visibleJobFileError}` : '解析失败';
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
                                                        data-testid="module2-document-switcher-button"
                                                        onClick={() => handleSelectDocument(index)}
                                                        onKeyDown={(event) => {
                                                            if (event.key !== 'Enter' && event.key !== ' ') return;
                                                            event.preventDefault();
                                                            handleSelectDocument(index);
                                                        }}
                                                        role="button"
                                                        tabIndex={0}
                                                        aria-current={isActive ? "true" : "false"}
                                                        aria-label={`${file.name}，${statusText}${isActive ? '，当前已选中' : ''}`}
                                                        className={cn(
                                                            "group relative mx-2 mb-1 flex cursor-pointer items-start gap-3 rounded-[10px] px-3 py-2.5 transition-all duration-200 ease-out active:scale-[0.98]",
                                                            isActive
                                                                ? "bg-blue-50/80 shadow-[0_1px_3px_rgba(0,0,0,0.02)] dark:bg-blue-500/10 dark:shadow-none"
                                                                : "bg-transparent hover:bg-slate-50 dark:hover:bg-white/[0.02]"
                                                        )}
                                                    >
                                                        <div className={cn(
                                                            "mt-0.5 shrink-0 transition-transform duration-200",
                                                            isActive && "scale-105"
                                                        )}>
                                                            {customIconSrc ? (
                                                                <img src={customIconSrc} alt={ext} className="h-5 w-5 object-contain" />
                                                            ) : (
                                                                <FileIcon size={20} className={iconColorClass} strokeWidth={isActive ? 2 : 1.5} />
                                                            )}
                                                        </div>

                                                        <div className="min-w-0 flex-1">
                                                            <div className="flex items-center justify-between gap-2">
                                                                <p className={cn("truncate text-[13px] font-medium transition-colors duration-200", isActive ? "text-slate-900 font-semibold dark:text-slate-100" : "text-slate-600 dark:text-slate-400")}>
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
                                                                    className="rounded-md p-1 text-slate-500/90 opacity-100 transition-all duration-200 hover:bg-slate-200/60 hover:text-slate-700 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-200"
                                                                >
                                                                    <Trash2 size={13} />
                                                                </button>
                                                            </div>

                                                            <div className="mt-1 flex min-w-0 items-center gap-2">
                                                                {StatusIndicator}
                                                                <span className={cn("min-w-0 truncate text-[10px] tabular-nums font-medium", statusColor)}>
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

                                {/* Upload / Append Document Button */}
                                <div className="mt-auto border-t border-slate-100/50 bg-slate-50/50 px-5 py-4 dark:border-white/[0.02] dark:bg-white/[0.01]">
                                    <button
                                        type="button"
                                        onClick={() => fileInputRef.current?.click()}
                                        className="group flex w-full items-center justify-center gap-2 rounded-xl bg-slate-200/50 py-3 text-[13px] font-semibold text-blue-700 shadow-[0_1px_2px_rgba(0,0,0,0.02)] ring-1 ring-slate-200/50 transition-all duration-200 hover:bg-slate-200/80 hover:text-blue-800 hover:shadow-sm active:scale-[0.98] dark:bg-white/[0.04] dark:text-blue-400 dark:ring-white/5 dark:hover:bg-white/[0.08] dark:hover:text-blue-300"
                                    >
                                        <Upload size={16} className="transition-transform duration-200 group-hover:-translate-y-0.5" strokeWidth={2.5} />
                                        <span>上传文档</span>
                                    </button>
                                </div>
                            </div>
                            {false && (
                                <div className="absolute bottom-2 right-2 z-30 flex h-[36vh] w-[372px] min-h-[280px] flex-col overflow-hidden rounded-xl border border-slate-100/80 bg-white p-3 shadow-soft-xl dark:border-white/[0.05] dark:bg-white/[0.02] backdrop-blur-xl">
                                    <div className="mb-2 flex items-center justify-between">
                                        <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-100">
                                            <Bot size={16} className="text-blue-500" />
                                            沉浸式伴聊助手（智能桥接）
                                        </h3>
                                        <button
                                            onClick={() => setShowAssistantHelp(true)}
                                            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-blue-600 dark:text-slate-500 dark:hover:bg-white/[0.05] dark:hover:text-blue-400"
                                            aria-label="查看助手功能说明"
                                        >
                                            <HelpCircle size={14} />
                                        </button>
                                    </div>

                                    <div className="flex min-h-0 flex-1 flex-col">
                                        <div ref={assistantDialogRef} data-testid="module2-assistant-dialog" className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 custom-scrollbar">
                                            {/* Summary Section */}
                                            <div className="rounded-xl border border-slate-100/80 bg-slate-50/80 px-3 py-2 text-[11px] tabular-nums leading-relaxed text-slate-600 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-200">
                                                <div className="mb-1 flex items-center gap-1.5 text-[10px] tabular-nums font-bold text-blue-600 dark:text-blue-300">
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
                                                <div className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] tabular-nums text-amber-700 dark:border-amber-800/50 dark:bg-amber-900/10 dark:text-amber-300">
                                                    {assistantWarnings.join('；')}
                                                </div>
                                            )}

                                            {/* Spacer for scrolling */}
                                            <div className="h-2" />
                                        </div>

                                        {/* Input Area */}
                                        <div className="border-t border-slate-100/80 bg-slate-50/50 p-3 dark:border-white/[0.05] dark:bg-white/[0.02]">
                                            <AssistantComposerStatus
                                                isLoading={assistantQueryLoading}
                                                streamingMessage={latestStreamingAssistantMessage}
                                            />

                                            <div
                                                className="relative flex flex-col rounded-[24px] border-0 bg-white shadow-[0_2px_16px_rgba(0,0,0,0.04)] ring-1 ring-slate-200/50 transition-all focus-within:shadow-[0_8px_30px_rgba(0,0,0,0.08)] focus-within:ring-slate-300 dark:bg-[#1A1D24] dark:ring-white/[0.05] dark:focus-within:shadow-[0_8px_30px_rgba(0,0,0,0.3)] dark:focus-within:ring-white/[0.1]"
                                                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                                                onDrop={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                    const files = Array.from(e.dataTransfer.files) as File[];
                                                    if (files.length > 0) {
                                                        mergeSelectedFiles(files);
                                                    }
                                                }}
                                            >
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
                                                    placeholder="在这里输入您的问题或指令..."
                                                    className="max-h-[160px] min-h-[52px] w-full resize-none bg-transparent px-4 pt-4 pb-0 text-[14px] leading-relaxed text-slate-800 placeholder:text-slate-400 outline-none dark:text-slate-200 custom-scrollbar"
                                                />
                                                <div className="flex items-center justify-between px-3 pb-3 pt-1">
                                                    <div className="flex items-center gap-1.5">
                                                        <button
                                                            type="button"
                                                            onClick={() => fileInputRef.current?.click()}
                                                            className="group relative flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition-all hover:bg-slate-100 hover:text-slate-700 active:scale-95 dark:text-slate-400 dark:hover:bg-white/[0.1] dark:hover:text-slate-200"
                                                            title="上传文档进行分析"
                                                            aria-label="上传文档进行分析"
                                                        >
                                                            <Plus size={18} strokeWidth={2} className="transition-transform group-hover:scale-110" />
                                                        </button>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            type="button"
                                                            data-testid="module2-assistant-send"
                                                            onClick={() => void runAssistantInstruction()}
                                                            disabled={!assistantQueryLoading && !assistantInput.trim()}
                                                            className={cn(
                                                                'group relative flex h-8 w-8 items-center justify-center rounded-full transition-all duration-200',
                                                                !assistantQueryLoading && !assistantInput.trim()
                                                                    ? 'cursor-not-allowed bg-[#F3F4F6] text-[#A1A1AA] dark:bg-white/[0.05] dark:text-slate-600'
                                                                    : assistantQueryLoading
                                                                        ? 'bg-slate-800 text-white shadow-sm hover:bg-slate-900 active:scale-95 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100'
                                                                        : 'bg-slate-900 text-white shadow-sm hover:bg-black hover:shadow active:scale-95 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100'
                                                            )}
                                                            title={assistantQueryLoading ? "停止本次回答" : "发送"}
                                                            aria-label={assistantQueryLoading ? "停止本次回答" : "发送"}
                                                        >
                                                            {assistantQueryLoading ? <X size={14} /> : <ArrowUp size={15} strokeWidth={2.5} className="transition-transform group-hover:-translate-y-0.5" />}
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>)}
                        </div>
                    )}

                    {showLeftPanel && selectedFiles.length > 0 && (
                        <div
                            role="separator"
                            aria-label="调整文档列表宽度"
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
                            "relative flex min-h-0 flex-1 flex-col overflow-hidden bg-slate-50 transition-all duration-300 dark:bg-slate-950 dark:shadow-none",
                            isTextPreviewStage
                                ? "bg-[linear-gradient(180deg,rgba(247,250,255,0.98),rgba(239,246,255,0.94))] dark:bg-[linear-gradient(180deg,rgba(247,250,255,0.98),rgba(239,246,255,0.94))]"
                                : "",
                            highlightedFieldKey || activeTraceKey
                                ? "bg-[linear-gradient(180deg,rgba(239,246,255,0.95),rgba(224,231,255,0.9))] dark:bg-[linear-gradient(180deg,rgba(2,6,23,0.92),rgba(2,6,23,0.86))]"
                                : ""
                        )}>
                            {/* Dot Grid Background */}
                            <div className={cn(
                                "pointer-events-none absolute inset-0 bg-[radial-gradient(circle,_#60a5fa_1px,_transparent_1px)] bg-[length:24px_24px]",
                                isTextPreviewStage
                                    ? "opacity-[0.18] dark:opacity-[0.18]"
                                    : "opacity-[0.35] dark:opacity-[0.04]"
                            )}>
                            </div>
                            <div aria-hidden="true" className="absolute inset-x-10 top-0 h-[2px] bg-gradient-to-r from-transparent via-blue-500/50 to-transparent dark:via-cyan-400/60 shadow-[0_0_10px_rgba(59,130,246,0.5)]" />

                            {/* Fixed Header Toolbar */}
                            {selectedFiles.length > 0 && (
                                <div className={cn(
                                    'relative z-20 flex w-full flex-nowrap items-center px-4 bg-white/80 backdrop-blur-md border-b border-slate-200/60 shadow-[0_2px_8px_rgba(0,0,0,0.03)] transition-colors duration-200 dark:bg-slate-950/80 dark:border-b dark:border-white/[0.05] dark:shadow-[0_2px_8px_rgba(0,0,0,0.15)]',
                                    useUltraDenseWorkbenchChrome ? 'gap-1 h-[36px] px-3' : useDenseWorkbenchChrome ? 'gap-1.5 h-[40px]' : 'gap-2 h-[48px]'
                                )}>
                                <div className={cn("flex min-w-0 items-center overflow-hidden", useUltraDenseWorkbenchChrome ? 'gap-1' : 'gap-1.5')}>
                                    {showLeftPanel && !shouldUseLeftQueueDrawer && (
                                        <button
                                            type="button"
                                            onClick={() => setIsPreviewFocused(true)}
                                            className={cn(
                                                'group inline-flex shrink-0 items-center justify-center rounded-lg border border-transparent text-blue-600 transition-all duration-300 ease-spring-gentle active:scale-95 hover:border-slate-100/80 hover:bg-white hover:text-blue-700 hover:shadow-soft-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 dark:text-blue-400 dark:hover:border-white/[0.1] dark:hover:bg-white/[0.08]',
                                                useUltraDenseWorkbenchChrome ? 'h-6 w-6' : useDenseWorkbenchChrome ? 'h-7 w-7' : 'h-8 w-8'
                                            )}
                                            title={previewFocusButtonTitle}
                                            aria-label={previewFocusButtonTitle}
                                            aria-controls="module2-left-panel"
                                            data-testid="module2-preview-focus-toggle"
                                        >
                                            <span className="transition-transform duration-200 ease-out group-hover:scale-105">
                                                <Maximize size={useUltraDenseWorkbenchChrome ? 13 : useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2.2} />
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
                                            onClick={() => {
                                                if (shouldUseLeftQueueDrawer) {
                                                    toggleLeftQueueAccess();
                                                    return;
                                                }
                                                setIsPreviewFocused(false);
                                            }}
                                            className={cn(
                                                'ml-1 inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-100/80 bg-white px-3 font-bold text-slate-800 shadow-soft-sm transition-all duration-300 ease-spring-gentle hover:border-blue-200 hover:bg-blue-50/60 hover:text-blue-700 hover:shadow-soft-md active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-200 dark:hover:border-blue-700 dark:hover:bg-white/[0.08] dark:hover:text-blue-300',
                                                useUltraDenseWorkbenchChrome ? 'ml-0 h-6 px-2 text-[10px] tabular-nums' : useDenseWorkbenchChrome ? 'h-7 text-[11px] tabular-nums' : 'h-8 text-xs'
                                            )}
                                            title={shouldUseLeftQueueDrawer ? leftQueueAccessButtonTitle : restoreFolderButtonTitle}
                                            aria-label={shouldUseLeftQueueDrawer ? leftQueueAccessButtonTitle : restoreFolderButtonTitle}
                                            aria-controls="module2-left-panel"
                                            data-testid="module2-restore-left-panel"
                                        >
                                            <FolderOpen size={useUltraDenseWorkbenchChrome ? 12 : useDenseWorkbenchChrome ? 13 : 14} />
                                            {!useUltraDenseWorkbenchChrome && <span className="hidden sm:inline">{shouldUseLeftQueueDrawer ? '文件/队列' : '文档列表'}</span>}
                                        </motion.button>
                                    )}

                                    <div className={cn("flex min-w-0 items-center text-slate-900 dark:text-slate-100", useUltraDenseWorkbenchChrome ? 'gap-1' : 'gap-2')}>
                                        <span className={cn('truncate font-bold', useUltraDenseWorkbenchChrome ? 'text-[12px]' : useDenseWorkbenchChrome ? 'text-[13px]' : 'text-sm')}>{previewToolbarTitle}</span>
                                    </div>
                                </div>

                                <div className={cn(
                                    'ml-auto flex max-w-full flex-wrap items-center justify-end',
                                    useUltraDenseWorkbenchChrome ? 'gap-1 sm:gap-1.5' : useDenseWorkbenchChrome ? 'gap-1.5 sm:gap-2' : 'gap-2 sm:gap-2.5'
                                )}>
                                    <div className={cn("flex max-w-full flex-nowrap items-center justify-end", useUltraDenseWorkbenchChrome ? 'gap-0' : 'gap-0.5 sm:gap-1')}>
                                        <button
                                            onClick={handleZoomOut}
                                            disabled={previewControlsDisabled}
                                            className={cn(
                                                useUltraDenseWorkbenchChrome ? 'p-1 rounded-lg transition-colors active:scale-95 shrink-0' : useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                                                previewControlsDisabled
                                                    ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                                                    : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/[0.08] hover:text-blue-600"
                                            )}
                                            title="缩小"
                                        >
                                            <ZoomOut size={useUltraDenseWorkbenchChrome ? 13 : useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2} />
                                        </button>
                                        <span className={cn(
                                            'shrink-0 text-center font-medium text-slate-700 dark:text-slate-300',
                                            useUltraDenseWorkbenchChrome ? 'w-8 text-[10px] tabular-nums' : useDenseWorkbenchChrome ? 'w-9 text-[11px] tabular-nums' : 'w-10 text-xs'
                                        )}>{previewScaleLabel}</span>
                                        <button
                                            onClick={handleZoomIn}
                                            disabled={previewControlsDisabled}
                                            className={cn(
                                                useUltraDenseWorkbenchChrome ? 'p-1 rounded-lg transition-colors active:scale-95 shrink-0' : useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                                                previewControlsDisabled
                                                    ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                                                    : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/[0.08] hover:text-blue-600"
                                            )}
                                            title="放大"
                                        >
                                            <ZoomIn size={useUltraDenseWorkbenchChrome ? 13 : useDenseWorkbenchChrome ? 14 : 16} strokeWidth={2} />
                                        </button>

                                        {activeRenderExt === 'pdf' && (
                                            <>
                                                <div className={cn(
                                                    'w-px shrink-0 bg-slate-200/80 dark:bg-white/[0.1]',
                                                    useUltraDenseWorkbenchChrome ? 'mx-1 h-3' : useDenseWorkbenchChrome ? 'mx-1.5 h-3.5' : 'mx-2 h-4'
                                                )} />
                                                <div className={cn("flex items-center shrink-0", useUltraDenseWorkbenchChrome ? 'gap-0' : 'gap-0.5')}>
                                                    <button
                                                        onClick={handlePrevPdfPage}
                                                        disabled={currentPdfPage <= 1}
                                                        className={cn(
                                                            useUltraDenseWorkbenchChrome ? 'p-1 rounded-lg transition-colors active:scale-95 shrink-0' : useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                                                            currentPdfPage > 1
                                                                ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-white/[0.08] dark:text-slate-300"
                                                                : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                                        )}
                                                        title="上一页"
                                                    >
                                                        <ChevronRight size={useUltraDenseWorkbenchChrome ? 13 : useDenseWorkbenchChrome ? 14 : 16} className="rotate-180" />
                                                    </button>
                                                    <span className={cn(
                                                        'shrink-0 text-center font-medium text-slate-700 dark:text-slate-300',
                                                        useUltraDenseWorkbenchChrome ? 'min-w-[30px] text-[10px] tabular-nums' : useDenseWorkbenchChrome ? 'min-w-[36px] text-[11px] tabular-nums' : 'min-w-[42px] text-xs'
                                                    )} data-testid="module2-preview-page-indicator">
                                                        {`${currentPdfPage} / ${inferredPdfPageCount}`}
                                                    </span>
                                                    <button
                                                        onClick={handleNextPdfPage}
                                                        disabled={currentPdfPage >= inferredPdfPageCount}
                                                        className={cn(
                                                            useUltraDenseWorkbenchChrome ? 'p-1 rounded-lg transition-colors active:scale-95 shrink-0' : useDenseWorkbenchChrome ? 'p-1.25 rounded-lg transition-colors active:scale-95 shrink-0' : 'p-1.5 rounded-lg transition-colors active:scale-95 shrink-0',
                                                            currentPdfPage < inferredPdfPageCount
                                                                ? "text-slate-700 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-white/[0.08] dark:text-slate-300"
                                                                : "text-slate-300 dark:text-slate-600 cursor-not-allowed"
                                                        )}
                                                        title="下一页"
                                                    >
                                                        <ChevronRight size={useUltraDenseWorkbenchChrome ? 13 : useDenseWorkbenchChrome ? 14 : 16} />
                                                    </button>
                                                </div>

                                                <div className={cn(
                                                    'w-px shrink-0 bg-slate-200/80 dark:bg-white/[0.1]',
                                                    useUltraDenseWorkbenchChrome ? 'mx-1 h-3' : useDenseWorkbenchChrome ? 'mx-1.5 h-3.5' : 'mx-2 h-4'
                                                )} />
                                                
                                                <button
                                                    onClick={() => {
                                                        setPdfViewMode(pdfViewMode === 'fit-width' ? 'fit-page' : pdfViewMode === 'fit-page' ? 'actual' : 'fit-width');
                                                        setScale(1);
                                                    }}
                                                    disabled={previewControlsDisabled}
                                                    className={cn(
                                                        'flex items-center justify-center gap-1 font-medium transition-colors active:scale-95 shrink-0',
                                                        useUltraDenseWorkbenchChrome ? 'px-1.5 py-1 rounded-lg text-[10px]' : useDenseWorkbenchChrome ? 'px-2 py-1.25 rounded-lg text-[11px]' : 'px-2.5 py-1.5 rounded-lg text-xs',
                                                        previewControlsDisabled
                                                            ? "cursor-not-allowed text-slate-300 dark:text-slate-600"
                                                            : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/[0.08] hover:text-blue-600"
                                                    )}
                                                    title="切换布局"
                                                >
                                                    <Layout size={useUltraDenseWorkbenchChrome ? 12 : useDenseWorkbenchChrome ? 13 : 14} />
                                                    {!useUltraDenseWorkbenchChrome && <span>布局</span>}
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </div>
                            </div>
                            )}

                            <div className={cn(
                                "relative z-10 flex flex-1 custom-scrollbar",
                                selectedFiles.length === 0
                                    ? "min-h-0 overflow-hidden p-0 items-stretch justify-stretch bg-white dark:bg-transparent"
                                    : activeRenderExt === 'pdf'
                                        ? "min-h-0 overflow-hidden p-0 items-stretch justify-stretch"
                                        : isSpreadsheetPreviewStage
                                            ? "min-h-0 overflow-hidden p-0 items-stretch justify-stretch"
                                        : isTextPreviewStage
                                            ? "min-h-0 overflow-hidden p-0 items-stretch justify-stretch"
                                        : "items-center justify-center overflow-auto p-8 sm:p-12 lg:p-16"
                            )}>
                                {selectedFiles.length === 0 && sessionHydrated && !sessionRestorePending ? (
                                    <DeepReadWelcomeScreen
                                        onUploadClick={() => fileInputRef.current?.click()}
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
                                        isUploaderDragOver={isUploaderDragOver}
                                    />
                                ) : selectedFiles.length === 0 ? (
                                    <div className="flex h-full w-full items-center justify-center">
                                        <Loader2 className="h-8 w-8 animate-spin text-blue-500 opacity-50" />
                                        <span className="ml-3 text-sm text-slate-500">正在恢复工作区...</span>
                                    </div>
                                ) : (
                                    <div
                                        className={cn(
                                            "relative w-full origin-center transition-all duration-300 ease-out will-change-transform",
                                            activeRenderExt === 'pdf'
                                                ? "h-full w-full"
                                                : isSpreadsheetPreviewStage
                                                    ? "h-full w-full min-h-0"
                                                : isTextPreviewStage
                                                    ? "h-full w-full min-h-0"
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
                                            "relative w-full overflow-hidden bg-white dark:bg-transparent",
                                            activeRenderExt === 'pdf'
                                                ? "h-full rounded-none ring-0 shadow-none"
                                                : isSpreadsheetPreviewStage
                                                    ? "h-full rounded-none ring-0 shadow-none"
                                                : isTextPreviewStage
                                                    ? "h-full rounded-none ring-0 shadow-none bg-transparent"
                                                : isPageBased
                                                    ? "aspect-[595/842] ring-1 ring-slate-200/50 shadow-2xl dark:ring-white/10"
                                                    : "flex-1 rounded-xl ring-1 ring-slate-200/50 shadow-soft-sm dark:ring-white/10"
                                        )}>
                                            {activeRenderExt === 'pdf' && previewUrl ? (
                                                <PdfJsViewer
                                                    key={`${activePreviewIdentity}:${previewUrl}`}
                                                    src={previewUrl}
                                                    scale={scale}
                                                    rotation={rotation}
                                                    viewMode={pdfViewMode}
                                                    scrollRequest={pdfScrollRequest}
                                                    onPageCount={setPdfPreviewPageCount}
                                                    onVisiblePageChange={setPdfViewportPage}
                                                />
                                            ) : (activeExt === 'doc' || activeExt === 'docx') ? (
                                                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-50/70 p-6 text-center dark:bg-white/[0.05]">
                                                    <div className="rounded-xl border border-slate-100/80 bg-white/90 px-4 py-3 text-xs text-slate-600 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-300">
                                                        {activeOfficePreview?.status === 'failed'
                                                            ? (activeOfficePreview.error || '文档预览转换失败，请先执行抽取或重新上传。')
                                                            : (activeOfficePreview?.status === 'completed'
                                                                ? '文档已转换完成，正在加载预览...'
                                                                : '后端正在将文档异步转换为预览，请稍候...')}
                                                    </div>
                                                    <p className="text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
                                                        支持文字文档，转换完成后自动切换为预览。
                                                    </p>
                                                </div>
                                            ) : IMAGE_EXTENSIONS.has(activeExt) && previewUrl ? (
                                                <div className="absolute inset-0 flex items-center justify-center bg-slate-50/70 dark:bg-white/[0.05] p-6">
                                                    <img
                                                        src={previewUrl}
                                                        alt={activeDisplayName}
                                                        className="max-h-full max-w-full object-contain rounded-md shadow-soft-sm"
                                                    />
                                                </div>
                                            ) : activeRenderExt === 'xlsx' ? (
                                                shouldRenderSpreadsheetPreview ? (
                                                    <div className="absolute inset-0 min-h-0 overflow-hidden bg-slate-50/45 p-0 dark:bg-transparent">
                                                        <LuckysheetPreview
                                                            file={activeSourceFile}
                                                            locator={xlsxLocatorHint}
                                                            className="h-full min-h-0 rounded-none border-0 bg-white dark:bg-transparent"
                                                        />
                                                    </div>
                                                ) : (
                                                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-slate-50/70 p-6 text-center dark:bg-white/[0.05]">
                                                        <div className="rounded-xl border border-slate-100/80 bg-white/90 px-4 py-3 text-xs text-slate-600 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-300">
                                                            {isProcessing
                                                                ? '电子表格预览将在抽取完成后自动加载，当前优先保障字段提取与结果回填。'
                                                                : '电子表格预览即将加载，请稍候。'}
                                                        </div>
                                                        <p className="text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
                                                            {isProcessing
                                                                ? '这样可以避免大表格预览阻塞工作台状态更新。'
                                                                : '抽取结果已经就绪，正在准备表格视图。'}
                                                        </p>
                                                    </div>
                                                )
                                            ) : ['txt', 'md'].includes(activeRenderExt) ? (
                                                <div
                                                    ref={textPreviewRef}
                                                    className="absolute inset-0 overflow-auto bg-[linear-gradient(180deg,rgba(247,250,255,0.94),rgba(239,246,255,0.88))] px-1.5 py-2 dark:bg-[linear-gradient(180deg,rgba(247,250,255,0.96),rgba(239,246,255,0.9))] sm:px-2.5 sm:py-3 lg:px-3 lg:py-4"
                                                >
                                                    <div className="flex min-h-full w-full">
                                                        <div className="w-full rounded-[24px] border border-sky-100/85 bg-white/97 px-4 py-4 shadow-[0_20px_48px_rgba(148,163,184,0.14)] ring-1 ring-white/70 backdrop-blur-sm dark:border-sky-100/80 dark:bg-white/95 dark:ring-white/80 sm:px-5 sm:py-5 lg:px-6 lg:py-6">
                                                            <pre className="w-full whitespace-pre-wrap break-words font-sans text-[14px] font-medium leading-[1.95] tracking-[0.01em] text-slate-800 dark:text-slate-800 sm:text-[15px] lg:text-[15.5px] lg:leading-[2.02] xl:text-[16px]">
                                                        {previewHighlight ? (
                                                            <>
                                                                {previewHighlight.before}
                                                                <mark data-preview-highlight="true" className="rounded-md bg-amber-200/90 px-1 py-0.5 text-slate-900 shadow-[0_0_0_1px_rgba(251,191,36,0.22)]">
                                                                    {previewHighlight.hit}
                                                                </mark>
                                                                {previewHighlight.after}
                                                            </>
                                                        ) : (
                                                            previewText || '文本预览加载中...'
                                                        )}
                                                            </pre>
                                                        </div>
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-8 bg-slate-50/70 dark:bg-white/[0.05]">
                                                    <div className="w-14 h-14 rounded-2xl bg-white dark:bg-white/[0.05] border border-slate-100/80 dark:border-white/[0.05] flex items-center justify-center mb-4 text-slate-500">
                                                        <img src={iconDocumentQueue} alt="Document" className="h-7 w-7 object-contain opacity-60 drop-shadow-sm" />
                                                    </div>
                                                    <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200 mb-2">{activeDisplayName}</h4>
                                                    <p className="text-[11px] tabular-nums text-slate-500 dark:text-slate-400 max-w-[320px] leading-relaxed">
                                                        {activeSourceFile
                                                            ? "当前格式暂不支持浏览器内预览，已保留抽取定位层与字段明细。"
                                                            : "未找到本地原始文件（可能为缓存结果），仅展示字段定位层与抽取结果。"}
                                                    </p>
                                                </div>
                                            )}

                                            {/* Bounding Boxes (hidden by default for cleaner trace view) */}
                                            {showTraceOverlay && overlayItems.map((item) => {
                                                const box = toPercentBox(item.bbox);
                                                const isActive = highlightedFieldKey === item.key;
                                                return (
                                                    <div
                                                        key={item.key}
                                                        style={{
                                                            left: `${box.x}%`,
                                                            top: `${box.y}%`,
                                                            width: `${box.w}%`,
                                                            height: `${box.h}%`,
                                                        }}
                                                        onMouseEnter={() => setHoveredFieldKey(item.key)}
                                                        onMouseLeave={() => setHoveredFieldKey(null)}
                                                        className={cn(
                                                            'absolute border-2 rounded-[2px] cursor-pointer transition-all duration-300 ease-spring-gentle z-10',
                                                            isActive
                                                                ? 'border-blue-500 bg-blue-500/20 shadow-[0_0_20px_rgba(59,130,246,0.5)] z-30 scale-[1.05]'
                                                                : 'border-blue-400/30 bg-blue-400/5 hover:border-blue-500/80 hover:bg-blue-500/10'
                                                        )}
                                                    >
                                                        {/* Floating Label on Hover */}
                                                        <div className={cn(
                                                            "absolute -top-10 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] tabular-nums px-2.5 py-1.5 rounded-md shadow-soft-xl whitespace-nowrap pointer-events-none transition-all transform",
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
                                                const label = getTraceDisplayKind(hit) === 'table'
                                                    ? '表格定位'
                                                    : getTraceDisplayKind(hit) === 'image'
                                                        ? '图片定位'
                                                        : getTraceDisplayKind(hit) === 'chart'
                                                            ? '图表定位'
                                                            : '原文定位';
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
                        </div>

                    </div>

                    {selectedFiles.length > 0 && (
                        <div
                            role="separator"
                            aria-label="调整结果与助手宽度"
                            data-active={paneResizeSide === 'right'}
                            onPointerDown={(event) => startPaneResize('right', event)}
                            onDoubleClick={() => resetPaneWidth('right')}
                            className="module2-pane-handle relative z-20 h-full"
                        />
                    )}

                    {/* 右侧：结果面板 */}
                    {selectedFiles.length > 0 && (
                    <div className="relative z-10 flex h-full min-h-0 w-full min-w-0 shrink-0 self-stretch flex-col bg-[#F8FAFC]/80 dark:bg-white/[0.02] backdrop-blur-xl dark:border-l dark:border-white/[0.05] transition-colors duration-200">
                        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                            <div className={cn(
                                'relative z-30 flex items-center w-full px-4 bg-white/90 backdrop-blur-md border-b border-slate-200/50 transition-colors duration-200 dark:bg-white/[0.02] dark:border-white/[0.05]',
                                useDenseWorkbenchChrome ? 'h-[40px]' : 'h-[48px]'
                            )}>
                                <div className={cn(
                                    'flex w-full items-center justify-between',
                                    useDenseWorkbenchChrome ? 'gap-1.5' : 'gap-2'
                                )}>
                                    <div className="min-w-0">
                                        <div className={cn('flex items-start', useDenseWorkbenchChrome ? 'gap-1' : 'gap-1.5')}>
                                            <img src={iconAssistant} alt="结果与助手" className={cn("h-[20px] w-[20px] shrink-0 object-contain", useDenseWorkbenchChrome ? "translate-y-[0px]" : "translate-y-[1px]")} />
                                            <div className="min-w-0">
                                                <h3 className={cn(
                                                    'truncate font-semibold tracking-tight text-slate-800 dark:text-slate-200',
                                                    useDenseWorkbenchChrome ? 'text-[12px]' : 'text-[13px]'
                                                )}>
                                                    结果与助手
                                                </h3>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="relative isolate flex shrink-0 items-center self-center">
                                        <div
                                            className={cn(
                                                'relative flex items-center gap-0.5 rounded-full bg-slate-100/50 p-0.5 dark:bg-white/[0.03]'
                                            )}
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
                                                                    'pointer-events-none absolute inset-0 rounded-full bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)] ring-1 ring-slate-200/50 dark:border-white/[0.05] dark:bg-white/[0.08] dark:ring-transparent'
                                                                )}
                                                                transition={smartUnitTabTransition}
                                                            />
                                                        )}
                                                        <button
                                                            type="button"
                                                            data-testid={`module2-smart-tab-${tab.id}`}
                                                            onClick={() => setSmartUnitTab(tab.id)}
                                                            aria-label={`${tab.label}${isActive ? '，当前已选中' : ''}`}
                                                            className={cn(
                                                                'relative z-10 inline-flex items-center justify-center tracking-wide whitespace-nowrap outline-none transition-[color,transform] duration-200 ease-out focus-visible:ring-2 focus-visible:ring-blue-500/25',
                                                                useDenseWorkbenchChrome ? 'h-[24px] px-3 text-[11px]' : 'h-[28px] px-3.5 text-[12px]',
                                                                isActive
                                                                    ? 'font-semibold text-slate-800 dark:text-slate-100'
                                                                    : 'font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300'
                                                            )}
                                                        >
                                                            <span className="flex items-center gap-1.5">
                                                                {tab.label}
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
                                        <div className="shrink-0 border-b border-slate-200/50 bg-slate-50/50 px-4 py-3.5 dark:border-white/[0.05] dark:bg-white/[0.02]">
                                            {shouldShowResultsStateCard ? (
                                                <div className="flex flex-col gap-3">
                                                    <div className="flex items-start gap-3">
                                                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-blue-50/80 text-blue-600 ring-1 ring-inset ring-blue-500/10 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20">
                                                            {isProcessing ? <Loader2 size={16} className="animate-spin text-blue-500" /> : <ScanLine size={16} />}
                                                        </div>
                                                        <div className="min-w-0 flex-1">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <h3 className="text-[13px] font-semibold tracking-wide text-slate-800 dark:text-slate-100">
                                                                    {resultsStateCardMeta.title}
                                                                </h3>
                                                            </div>
                                                            <p className="mt-1.5 text-[11.5px] font-medium text-slate-600 dark:text-slate-400">
                                                                {resultsStateCardMeta.detail}
                                                            </p>
                                                            <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                                                                {resultsStateCardMeta.context}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="flex flex-col gap-3">
                                                    <div className="flex flex-wrap items-center justify-between gap-2.5">
                                                        <div className="min-w-0 flex-1">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <p className="truncate text-[13.5px] font-bold tracking-wide text-slate-800 dark:text-slate-100">
                                                                    {activeDisplayName}
                                                                </p>
                                                                {activeIssueCount > 0 && (
                                                                    <span className="inline-flex items-center rounded bg-amber-100/50 px-1.5 py-0.5 text-[10px] tabular-nums font-semibold text-amber-700 ring-1 ring-inset ring-amber-500/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20">
                                                                        待核验 {activeIssueCount}
                                                                    </span>
                                                                )}
                                                                {activeFieldItem && (
                                                                    <span className="inline-flex items-center rounded bg-blue-100/50 px-1.5 py-0.5 text-[10px] tabular-nums font-semibold text-blue-700 ring-1 ring-inset ring-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20">
                                                                        当前字段：{activeFieldItem.label}
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        {graphSyncSupported && (
                                                            <button
                                                                type="button"
                                                                data-testid="module2-trigger-graph-sync"
                                                                onClick={() => activeDoc && void requestGraphSync(activeDoc)}
                                                                disabled={graphSyncDisabled || graphSyncState === 'submitting'}
                                                                className={cn(
                                                                    'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold transition-all',
                                                                    (graphSyncDisabled || graphSyncState === 'submitting')
                                                                        ? 'cursor-not-allowed bg-slate-100 text-slate-400 ring-1 ring-inset ring-slate-200/80 dark:bg-white/[0.04] dark:text-slate-500 dark:ring-white/[0.08]'
                                                                        : graphSyncState === 'success'
                                                                            ? 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-500/20 hover:bg-emerald-100/70 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20'
                                                                            : 'bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-500/20 hover:bg-blue-100/80 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20'
                                                                )}
                                                                title={graphSyncDisabled && activeDoc?.errors?.length
                                                                    ? '当前文件存在解析错误，暂不能构建知识图谱'
                                                                    : '将当前解析产物提交到知识图谱构建链路'}
                                                            >
                                                                {graphSyncState === 'submitting' ? (
                                                                    <Loader2 size={12} className="animate-spin" />
                                                                ) : (
                                                                    <BarChart3 size={12} />
                                                                )}
                                                                <span>
                                                                    {graphSyncState === 'submitting'
                                                                        ? '提交中...'
                                                                        : graphSyncState === 'success'
                                                                            ? '已提交构图'
                                                                            : '构建知识图谱'}
                                                                </span>
                                                            </button>
                                                        )}
                                                        {graphSyncExcluded && (
                                                            <span className="inline-flex items-center rounded-lg bg-slate-100/80 px-3 py-1.5 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-200/70 dark:bg-white/[0.04] dark:text-slate-300 dark:ring-white/[0.08]">
                                                                Excel 文件不进行知识图谱渲染
                                                            </span>
                                                        )}
                                                        {graphSyncMessage && (
                                                            <span
                                                                className={cn(
                                                                    'text-[11px] font-medium',
                                                                    graphSyncState === 'error'
                                                                        ? 'text-rose-600 dark:text-rose-300'
                                                                        : 'text-slate-500 dark:text-slate-400'
                                                                )}
                                                            >
                                                                {graphSyncMessage}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                        {shouldShowTraceDetailPanel && (
                                        <motion.div
                                            data-testid="module2-trace-panel"
                                            initial={prefersReducedMotion ? false : { opacity: 0, y: -8 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                                            className="flex h-[176px] min-h-[176px] shrink-0 flex-col overflow-hidden border-b border-slate-200/50 bg-transparent px-4 py-3 dark:border-white/[0.05] dark:bg-transparent"
                                        >
                                            <div className="flex items-start justify-between gap-2.5">
                                                <div className="min-w-0">
                                                    <div className="flex items-center gap-2.5">
                                                        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-blue-50/50 text-blue-600 ring-1 ring-blue-500/20 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20">
                                                            <LocateFixed size={14} className={cn('text-blue-500 dark:text-blue-400', traceHits.length > 0 && 'text-blue-600 dark:text-blue-300')} />
                                                        </span>
                                                        <div className="min-w-0">
                                                            <h3 className="text-[12px] font-semibold tracking-wide text-slate-800 dark:text-slate-200">
                                                                原文定位
                                                            </h3>
                                                            {activeFieldItem && (
                                                                <div className="mt-1">
                                                                    <span className="inline-flex items-center rounded-md bg-blue-50/50 px-2 py-0.5 text-[10px] tabular-nums font-medium text-blue-700 ring-1 ring-inset ring-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20">
                                                                        {activeFieldItem.label}
                                                                    </span>
                                                                </div>
                                                            )}
                                                            <p className="mt-0.5 text-[10.5px] leading-relaxed text-slate-500 dark:text-slate-400">
                                                                {tracePanelHintText}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex shrink-0 items-start gap-2 self-start pt-0.5">
                                                    {traceLoading && (
                                                        <span className="inline-flex h-6 items-center gap-1.5 rounded-md bg-blue-50/50 px-2.5 text-[10.5px] tabular-nums font-medium text-blue-700 ring-1 ring-inset ring-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20">
                                                            <Loader2 size={12} className="animate-spin" />
                                                            同步中
                                                        </span>
                                                    )}
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            setTracePanelOpen(false);
                                                            setActiveFieldKey(null);
                                                            setActiveTraceKey('');
                                                            setExpandedTraceCardKey('');
                                                            setHoveredFieldKey(null);
                                                        }}
                                                        className="inline-flex h-6 w-6 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-white/[0.05] dark:hover:text-slate-300"
                                                        aria-label="收起原文定位"
                                                        title="收起原文定位"
                                                    >
                                                        <X size={14} />
                                                    </button>
                                                </div>
                                            </div>

                                            {hasTraceTypeStats && (
                                                <div className="mt-2.5 flex flex-wrap gap-1.5 text-[10.5px] tabular-nums">
                                                    {traceTypeStats.field > 0 && <span className="inline-flex items-center rounded-md bg-blue-50/50 px-2 py-0.5 font-medium text-blue-600 ring-1 ring-inset ring-blue-500/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20">字段 {traceTypeStats.field}</span>}
                                                    {traceTypeStats.table > 0 && <span className="inline-flex items-center rounded-md bg-emerald-50/50 px-2 py-0.5 font-medium text-emerald-600 ring-1 ring-inset ring-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20">表格 {traceTypeStats.table}</span>}
                                                    {traceTypeStats.image > 0 && <span className="inline-flex items-center rounded-md bg-amber-50/50 px-2 py-0.5 font-medium text-amber-600 ring-1 ring-inset ring-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20">图片 {traceTypeStats.image}</span>}
                                                    {traceTypeStats.chart > 0 && <span className="inline-flex items-center rounded-md bg-cyan-50/60 px-2 py-0.5 font-medium text-cyan-700 ring-1 ring-inset ring-cyan-500/20 dark:bg-cyan-500/10 dark:text-cyan-300 dark:ring-cyan-500/20">数据可视化 {traceTypeStats.chart}</span>}
                                                    {traceTypeStats.other > 0 && <span className="inline-flex items-center rounded-md bg-slate-100/50 px-2 py-0.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-500/20 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.1]">其他 {traceTypeStats.other}</span>}
                                                </div>
                                            )}

                                            {traceError && (
                                                <p className="mt-2.5 rounded-md bg-amber-50/50 px-3 py-2 text-[11px] tabular-nums font-medium text-amber-700 ring-1 ring-inset ring-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20">
                                                    {traceError}
                                                </p>
                                            )}

                                            {traceHits.length > 0 ? (
                                                <div className="mt-3 min-h-0 flex-1 overflow-y-auto rounded-lg bg-transparent pb-0 custom-scrollbar dark:bg-transparent">
                                                    {traceGroups.map((group) => (
                                                        <div key={`trace-group-${group.key}`} data-testid={`module2-trace-group-${group.key}`} className="mb-3 px-2 pt-2 last:mb-0">
                                                            <div data-testid="module2-trace-group-label" className="sticky top-0 z-10 mb-1.5 rounded bg-slate-100/80 px-2 py-0.5 text-[11px] tabular-nums font-bold text-slate-600 backdrop-blur dark:bg-white/[0.05] dark:text-slate-300">
                                                                {group.label}
                                                            </div>
                                                            <div className="space-y-0">
                                                                {group.items.map(({ hit, idx }) => {
                                                                    const objectType = String(hit.object_type || "field").toLowerCase();
                                                                    const displayKind = getTraceDisplayKind(hit);
                                                                    const objectLabel = getTraceDisplayLabel(hit);
                                                                    const objectId = String(hit.object_id || "");
                                                                    const page = toTracePage(hit);
                                                                    const rawSnippet = String(hit.snippet || "");
                                                                    let snippet = rawSnippet;
                                                                    if (displayKind === 'table') {
                                                                        snippet = snippet.replace(/([；;,. ]*)表头[:：].*$/, '');
                                                                    }
                                                                    let displayTitle = snippet || objectId || '定位片段';
                                                                    if (displayKind === 'image' || objectType === 'figure') {
                                                                        displayTitle = displayTitle.replace(/^(?:charts?|figures?|images?|图表)[:：\s]*/i, '').replace(/\s*\([^)]+\)$/, '');
                                                                    }
                                                                    const traceKey = toTraceHitKey(hit, idx);
                                                                    const isActiveTrace = activeTraceKey === traceKey;
                                                                    const jumpButtonLabel = activeRenderExt === 'pdf' && page > 0
                                                                        ? `定位到第 ${Math.round(page)} 页`
                                                                        : '聚焦当前证据';
                                                                    const artifactUrl = resolveArtifactUrl(hit);
                                                                    const locator = (hit.locator ?? {}) as Record<string, unknown>;
                                                                    const chartSpec = toTraceChartSpec(locator.chart_spec);
                                                                    const tablePreview = toRecord(locator.table_preview);
                                                                    const tableDataframeRaw = toRecord(locator.dataframe);
                                                                    const tableDataframe = pickBestTraceDataframePayload(tableDataframeRaw, tablePreview);
                                                                    const tableHeaders = tableDataframe.headers;
                                                                    const tableRows = tableDataframe.rows;
                                                                    const tableProjectedRowCount = Math.max(
                                                                        tableDataframe.rowCount,
                                                                        toPositiveRoundedInt(tableDataframeRaw.projected_row_count),
                                                                        toPositiveRoundedInt(tablePreview.projected_row_count),
                                                                    );
                                                                    const tableProjectedColCount = Math.max(
                                                                        tableDataframe.colCount,
                                                                        toPositiveRoundedInt(tableDataframeRaw.projected_col_count),
                                                                        toPositiveRoundedInt(tablePreview.projected_col_count),
                                                                    );
                                                                    const tableSourceRowCount = Math.max(
                                                                        toPositiveRoundedInt(tableDataframeRaw.source_nonempty_row_count),
                                                                        toPositiveRoundedInt(tablePreview.source_nonempty_row_count),
                                                                    );
                                                                    const tableSourceColCount = Math.max(
                                                                        toPositiveRoundedInt(tableDataframeRaw.source_used_col_count),
                                                                        toPositiveRoundedInt(tablePreview.source_used_col_count),
                                                                    );
                                                                    const tableProjectionTruncated = Boolean(tableDataframeRaw.xlsx_projection_truncated)
                                                                        || Boolean(tablePreview.xlsx_projection_truncated)
                                                                        || (tableSourceRowCount > 0 && tableSourceRowCount > tableProjectedRowCount)
                                                                        || (tableSourceColCount > 0 && tableSourceColCount > tableProjectedColCount);
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
                                                                    const showArtifactImage = canRenderTraceArtifactImage(artifactUrl, locator.artifact_source);
                                                                    const showArtifactSource = canShowTraceArtifactSource(locator.artifact_source);
                                                                    return (
                                                                        <div
                                                                            key={`trace-list-${traceKey}`}
                                                                            data-testid="module2-trace-card"
                                                                            data-trace-kind={displayKind}
                                                                            data-trace-active={isActiveTrace ? 'true' : 'false'}
                                                                            data-trace-expanded={isTraceExpanded ? 'true' : 'false'}
                                                                            onClick={() => activateTraceSelection({ traceKey, objectType, objectId, page })}
                                                                            className={cn(
                                                                                "group relative w-full rounded-xl border px-3 py-3 text-left shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-all duration-200 mb-2",
                                                                                isActiveTrace
                                                                                    ? "border-blue-400 ring-1 ring-blue-400 bg-blue-50/50 dark:border-blue-500/50 dark:ring-blue-500/30 dark:bg-blue-500/10"
                                                                                    : "border-slate-200/80 bg-slate-50/50 hover:border-slate-300 hover:bg-white hover:shadow-[0_2px_4px_rgba(0,0,0,0.04)] dark:border-white/[0.05] dark:bg-white/[0.01] dark:hover:border-white/[0.08] dark:hover:bg-white/[0.03]",
                                                                                isTraceExpanded && "bg-white shadow-[0_2px_4px_rgba(0,0,0,0.04)] border-slate-300 dark:bg-white/[0.04] dark:border-white/[0.1]"
                                                                            )}
                                                                        >
                                                                            <div className="mb-1.5 flex items-center justify-between gap-2">
                                                                                <div className="flex items-center gap-2">
                                                                                    <span className={cn(
                                                                                        "flex h-5 items-center justify-center rounded-md px-1.5 text-[10px] tabular-nums font-semibold uppercase tracking-wider",
                                                                                        displayKind === 'field' ? "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400" :
                                                                                            displayKind === 'table' ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400" :
                                                                                                displayKind === 'chart' ? "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300" :
                                                                                                displayKind === 'image' ? "bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400" :
                                                                                                    "bg-slate-100 text-slate-600 dark:bg-white/[0.05] dark:text-slate-400"
                                                                                    )}>
                                                                                        {objectLabel}
                                                                                    </span>
                                                                                    {activeRenderExt === 'pdf' && page > 0 && (
                                                                                        <span className="flex items-center gap-0.5 text-[10px] tabular-nums font-medium text-slate-400">
                                                                                            <span className="opacity-50">页</span>
                                                                                            <span>{Math.round(page)}</span>
                                                                                        </span>
                                                                                    )}
                                                                                </div>
                                                                                <span className="text-[10px] tabular-nums font-medium text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">{Math.round((Number(hit.confidence || 0) || 0) * 100)}%</span>
                                                                            </div>
                                                                            <div className="flex items-start gap-1.5">
                                                                                <div className={cn(
                                                                                    "mt-[1px] flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px]",
                                                                                    displayKind === 'table' ? "bg-emerald-50 text-emerald-600 ring-1 ring-inset ring-emerald-100/50 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20" :
                                                                                    displayKind === 'chart' ? "bg-cyan-50 text-cyan-700 ring-1 ring-inset ring-cyan-100/50 dark:bg-cyan-500/10 dark:text-cyan-300 dark:ring-cyan-500/20" :
                                                                                    displayKind === 'image' ? "bg-amber-50 text-amber-600 ring-1 ring-inset ring-amber-100/50 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20" :
                                                                                    displayKind === 'field' ? "bg-blue-50 text-blue-600 ring-1 ring-inset ring-blue-100/50 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20" :
                                                                                    "bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-200/50 dark:bg-white/[0.05] dark:text-slate-400 dark:ring-white/[0.1]"
                                                                                )}>
                                                                                    {displayKind === 'table' ? <FileSpreadsheet className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                                                                                     displayKind === 'chart' ? <Layout className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                                                                                     displayKind === 'image' ? <FileImage className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                                                                                     displayKind === 'field' ? <FileText className="h-[10px] w-[10px]" strokeWidth={2.5} /> :
                                                                                     <File className="h-[10px] w-[10px]" strokeWidth={2.5} />}
                                                                                </div>
                                                                                <p className="line-clamp-2 text-[11px] tabular-nums leading-relaxed text-slate-800 dark:text-slate-200">
                                                                                    {displayTitle}
                                                                                </p>
                                                                            </div>
                                                                            {locatorSummary && (
                                                                                <div className="mt-2 flex items-center gap-1.5">
                                                                                    <div className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600"></div>
                                                                                    <p className="truncate text-[10px] tabular-nums text-slate-500 dark:text-slate-400">
                                                                                        {locatorSummary}
                                                                                    </p>
                                                                                </div>
                                                                            )}

                                                                            {displayKind === 'table' && tableProjectionTruncated && (
                                                                                <div className="mt-2 rounded-md bg-slate-50/85 px-2.5 py-2 text-[10px] leading-relaxed text-slate-600 ring-1 ring-inset ring-slate-300/60 dark:bg-white/[0.03] dark:text-slate-300 dark:ring-white/[0.08]">
                                                                                    {`Table preview scope: ${formatCompactInt(tableProjectedRowCount)} rows × ${formatCompactInt(tableProjectedColCount)} cols shown; source non-empty scope ${formatCompactInt(tableSourceRowCount)} rows × ${formatCompactInt(tableSourceColCount)} cols.`}
                                                                                </div>
                                                                            )}

                                                                            {displayKind === 'table' && tableHeaderSummary.length > 0 && (
                                                                                <div className="mt-2.5 rounded-md bg-emerald-50/50 px-2.5 py-2 dark:bg-emerald-500/5">
                                                                                    <div className="mb-1.5 text-[10px] tabular-nums font-medium text-emerald-600 dark:text-emerald-400">
                                                                                        摘要
                                                                                    </div>
                                                                                    <div className="flex flex-wrap gap-1.5">
                                                                                        {tableHeaderSummary.map((header) => (
                                                                                            <span
                                                                                                key={`${traceKey}-header-${header}`}
                                                                                                className="rounded bg-white/60 px-1.5 py-0.5 text-[10px] tabular-nums text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                                                                                            >
                                                                                                {header}
                                                                                            </span>
                                                                                        ))}
                                                                                    </div>
                                                                                </div>
                                                                            )}

                                                                            {displayKind === 'chart' && chartSpec && (
                                                                                <div className="mt-2.5 space-y-2">
                                                                                    <XlsxTraceChart spec={chartSpec} className="rounded-md bg-white/70 dark:bg-slate-900/50" />
                                                                                    {(() => {
                                                                                        const xAxisLabel = String(chartSpec.x_axis_label || chartSpec.x_field || '').trim();
                                                                                        const yAxisLabel = String(
                                                                                            chartSpec.y_axis_label ||
                                                                                            (Array.isArray(chartSpec.y_fields) ? chartSpec.y_fields.filter(Boolean).join(' / ') : '')
                                                                                        ).trim();
                                                                                        if (!xAxisLabel && !yAxisLabel) return null;
                                                                                        return (
                                                                                            <div className="flex flex-wrap gap-1.5 text-[10px] tabular-nums text-cyan-700/95 dark:text-cyan-200/95">
                                                                                                {xAxisLabel && (
                                                                                                    <span className="inline-flex items-center gap-1 rounded-md bg-white/80 px-2 py-0.5 ring-1 ring-inset ring-cyan-500/20 dark:bg-cyan-500/10 dark:ring-cyan-500/30">
                                                                                                        X轴：{xAxisLabel}
                                                                                                    </span>
                                                                                                )}
                                                                                                {yAxisLabel && (
                                                                                                    <span className="inline-flex items-center gap-1 rounded-md bg-white/80 px-2 py-0.5 ring-1 ring-inset ring-cyan-500/20 dark:bg-cyan-500/10 dark:ring-cyan-500/30">
                                                                                                        Y轴：{yAxisLabel}
                                                                                                    </span>
                                                                                                )}
                                                                                            </div>
                                                                                        );
                                                                                    })()}
                                                                                    {(chartSpec.trend_summary || chartSpec.description) && (
                                                                                        <p className="text-[10px] leading-relaxed text-cyan-700/90 dark:text-cyan-300/90">
                                                                                            {chartSpec.trend_summary || chartSpec.description}
                                                                                        </p>
                                                                                    )}
                                                                                </div>
                                                                            )}

                                                                            {objectType === 'figure' && figureModes.length > 0 && (
                                                                                <div className="mt-2 flex flex-wrap gap-1">
                                                                                    {figureModes.map((mode) => (
                                                                                        <span
                                                                                            key={`${traceKey}-mode-${mode}`}
                                                                                            className="rounded-md bg-amber-50/50 px-1.5 py-0.5 text-[10px] tabular-nums text-amber-700/80 ring-1 ring-inset ring-amber-600/10 dark:bg-amber-900/20 dark:text-amber-300"
                                                                                        >
                                                                                            {modeLabelMap[mode] || mode}
                                                                                        </span>
                                                                                    ))}
                                                                                </div>
                                                                            )}

                                                                            {showArtifactImage && (
                                                                                <div className="mt-2.5 space-y-2">
                                                                                    <div className="overflow-hidden rounded-lg bg-slate-100/50 dark:bg-white/[0.02]">
                                                                                        <button
                                                                                            type="button"
                                                                                            data-trace-card-action="true"
                                                                                            onMouseDown={stopTraceCardAction}
                                                                                            onKeyDown={stopTraceCardAction}
                                                                                            onClick={(event) => {
                                                                                                stopTraceCardAction(event);
                                                                                                activateTraceSelection({ traceKey, objectType, objectId, page });
                                                                                            }}
                                                                                            className="block w-full text-left"
                                                                                            title={activeRenderExt === 'pdf' && page > 0 ? `定位到第 ${Math.round(page)} 页` : '聚焦当前证据'}
                                                                                            aria-label={activeRenderExt === 'pdf' && page > 0 ? `定位到第 ${Math.round(page)} 页` : '聚焦当前证据'}
                                                                                        >
                                                                                            <img
                                                                                                data-testid="module2-trace-artifact-image"
                                                                                                src={artifactUrl}
                                                                                                alt={`${objectLabel}-preview-${idx + 1}`}
                                                                                                className="h-40 w-full object-contain bg-white/50 p-1.5 dark:bg-transparent sm:h-56"
                                                                                                loading="lazy"
                                                                                            />
                                                                                        </button>
                                                                                    </div>
                                                                                    <div className="flex justify-start">
                                                                                        <a
                                                                                            href={artifactUrl}
                                                                                            target="_blank"
                                                                                            rel="noreferrer"
                                                                                            data-trace-card-action="true"
                                                                                            onMouseDown={stopTraceCardAction}
                                                                                            onKeyDown={stopTraceCardAction}
                                                                                            onClick={stopTraceCardAction}
                                                                                            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-2.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-200/80 shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-all hover:bg-slate-50 hover:text-slate-800 active:scale-95 dark:bg-white/[0.02] dark:text-slate-300 dark:ring-white/[0.05] dark:hover:bg-white/[0.04] dark:hover:text-slate-100"
                                                                                            style={{ height: '22px', fontSize: '11px' }}
                                                                                        >
                                                                                            <ExternalLink size={12} />
                                                                                            查看截图
                                                                                        </a>
                                                                                    </div>
                                                                                </div>
                                                                            )}

                                                                            {objectType === 'figure' && figureSummaryBullets.length > 0 && (
                                                                                <div className="mt-3 rounded-lg bg-[#F8FAFC]/80 px-3 py-2.5 shadow-[inset_0_0_0_1px_rgba(0,0,0,0.03)] dark:bg-white/[0.02] dark:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.05)]">
                                                                                    <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-slate-500 dark:text-slate-400">
                                                                                        <Sparkles size={10} className="text-blue-500" />
                                                                                        关键信息
                                                                                    </div>
                                                                                    <div className="space-y-2">
                                                                                        {figureSummaryBullets.map((item, itemIdx) => (
                                                                                            <div key={`${traceKey}-summary-${itemIdx}`} className="flex items-start gap-2">
                                                                                                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-blue-400 dark:bg-blue-500"></span>
                                                                                                <p className="text-[11px] leading-relaxed text-slate-700 dark:text-slate-300">{item}</p>
                                                                                            </div>
                                                                                        ))}
                                                                                    </div>
                                                                                </div>
                                                                            )}

                                                                            {displayKind === 'table' && tableRows.length > 0 && (
                                                                                <div className="mt-2 flex flex-wrap gap-1.5">
                                                                                    <button
                                                                                        type="button"
                                                                                        data-trace-card-action="true"
                                                                                        onMouseDown={stopTraceCardAction}
                                                                                        onKeyDown={stopTraceCardAction}
                                                                                        onClick={(event) => {
                                                                                            stopTraceCardAction(event);
                                                                                            void writeClipboard(
                                                                                                tablePreviewToTsv(
                                                                                                    tableHeaders.length > 0 ? tableHeaders : tableRows[0],
                                                                                                    tableRows
                                                                                                ),
                                                                                                "已复制表格内容（制表符分隔格式）。"
                                                                                            );
                                                                                        }}
                                                                                        className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-white px-2.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-200/80 shadow-[0_1px_2px_rgba(0,0,0,0.02)] transition-all hover:bg-slate-50 hover:text-slate-800 active:scale-95 dark:bg-white/[0.02] dark:text-slate-300 dark:ring-white/[0.05] dark:hover:bg-white/[0.04] dark:hover:text-slate-100"
                                                                                        style={{ height: '22px', fontSize: '11px' }}
                                                                                    >
                                                                                        <Copy size={12} />
                                                                                        复制表格
                                                                                    </button>
                                                                                </div>
                                                                            )}
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : (
                                                <div className="mt-4 flex flex-col items-center justify-center rounded-xl border border-slate-200/60 bg-slate-50/50 px-4 py-8 text-center dark:border-white/[0.05] dark:bg-white/[0.05]">
                                                    <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-white/[0.05] dark:text-slate-500">
                                                        <LocateFixed size={16} />
                                                    </div>
                                                    <p className="text-[12px] font-medium text-slate-600 dark:text-slate-300">
                                                        {activeDoc ? '暂无相关定位信息' : '尚未生成定位结果'}
                                                    </p>
                                                    <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                                                        {tracePanelHintText}
                                                    </p>
                                                </div>
                                            )}
                                        </motion.div>
                                        )}

                                        <div className="flex-1 min-h-0 space-y-0 overflow-y-auto custom-scrollbar bg-white dark:bg-transparent relative">
                                            <div className="px-4 pt-3 pb-1">
                                                {(activeSummaryLoading || activeSummaryText) && (
                                                    <div className="mb-2">
                                                        <button
                                                            type="button"
                                                            onClick={() => setIsSummaryExpanded((prev) => !prev)}
                                                            className="group flex w-full items-center justify-between rounded-[8px] bg-slate-50/80 px-3 py-2.5 transition-all hover:bg-slate-100/80 dark:bg-white/[0.02] dark:hover:bg-white/[0.04] outline-none"
                                                            aria-expanded={isSummaryExpanded ? 'true' : 'false'}
                                                        >
                                                            <div className="flex items-center gap-2.5">
                                                                <div className="flex h-5 w-5 items-center justify-center rounded-[6px] bg-blue-50/50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400">
                                                                    <Sparkles size={12} />
                                                                </div>
                                                                <span className="text-[12px] font-medium text-slate-700 transition-colors group-hover:text-slate-900 dark:text-slate-300 dark:group-hover:text-slate-100">
                                                                    文档摘要
                                                                </span>
                                                            </div>
                                                            <ChevronRight
                                                                size={14}
                                                                className={cn(
                                                                    "text-slate-400 transition-transform duration-200 dark:text-slate-500",
                                                                    isSummaryExpanded && "rotate-90 text-blue-500 dark:text-blue-400"
                                                                )}
                                                            />
                                                        </button>
                                                        {isSummaryExpanded && (
                                                            <div data-testid="module2-summary-text" className="mt-2 rounded-[8px] bg-slate-50/80 p-3.5 text-[12px] leading-relaxed text-slate-600 dark:bg-white/[0.02] dark:text-slate-300">
                                                                {activeSummaryLoading ? (
                                                                    <span className="flex items-center gap-2 text-slate-400 dark:text-slate-500">
                                                                        <Loader2 size={13} className="animate-spin" />
                                                                        正在生成文档摘要...
                                                                    </span>
                                                                ) : (
                                                                    activeSummaryText
                                                                )}
                                                            </div>
                                                        )}
                                                    </div>
                                                )}

                                            </div>

                                            <div className="sticky top-0 z-20 bg-slate-50/90 backdrop-blur-md dark:bg-slate-900/80 px-4 py-2 mb-2 border-b border-slate-200/50 dark:border-white/[0.05]">
                                                <div className="flex flex-wrap items-center justify-between gap-2 px-0.5">
                                                    <div className="flex items-center gap-1.5">
                                                        <LocateFixed size={13} className="text-slate-400 dark:text-slate-500" />
                                                        <h3 className="text-[12px] font-semibold text-slate-700 dark:text-slate-300">
                                                            原文定位
                                                        </h3>
                                                    </div>
                                                    {shouldShowTraceRootBlock && (
                                                        <div className="flex flex-wrap items-center gap-1.5">
                                                            {filteredFieldItems.length > 0 && (
                                                                <button
                                                                    type="button"
                                                                    onClick={() => document.getElementById('trace-section-field')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                                                                    className="inline-flex items-center justify-center rounded-full bg-white/60 px-2 font-medium text-blue-600 border border-slate-200/50 hover:bg-white transition-colors cursor-pointer dark:bg-white/[0.02] dark:text-blue-400 dark:hover:bg-white/[0.04] dark:border-white/[0.05]"
                                                                    style={{ height: '22px', fontSize: '11px' }}
                                                                >
                                                                    <span>字段 <span className="ml-0.5 font-semibold opacity-70" style={{ fontSize: '10px' }}>{filteredFieldItems.length}</span></span>
                                                                </button>
                                                            )}
                                                            {documentTraceGroups.map((group) => {
                                                                const colorClass = group.key === 'table' 
                                                                    ? 'text-emerald-600 dark:text-emerald-400'
                                                                    : group.key === 'image'
                                                                    ? 'text-amber-600 dark:text-amber-400'
                                                                    : group.key === 'chart'
                                                                    ? 'text-cyan-700 dark:text-cyan-300'
                                                                    : 'text-slate-600 dark:text-slate-300';
                                                                return (
                                                                    <button
                                                                        key={`doc-trace-chip-${group.key}`}
                                                                        type="button"
                                                                        onClick={() => document.getElementById(`trace-section-${group.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
                                                                        className={cn("inline-flex items-center justify-center rounded-full bg-white/60 px-2 font-medium border border-slate-200/50 hover:bg-white transition-colors cursor-pointer dark:bg-white/[0.02] dark:hover:bg-white/[0.04] dark:border-white/[0.05]", colorClass)}
                                                                        style={{ height: '22px', fontSize: '11px' }}
                                                                    >
                                                                        <span>{group.label} <span className="ml-0.5 font-semibold opacity-70" style={{ fontSize: '10px' }}>{group.items.length}</span></span>
                                                                    </button>
                                                                );
                                                            })}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="px-4 pb-3">
                                                {hasFieldResults && errorMessage && (
                                                <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-bold text-red-600 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
                                                    <div className="flex items-start gap-2">
                                                        <AlertCircle size={14} className="mt-0.5 shrink-0" />
                                                        <span>{errorMessage}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {hasFieldResults && !errorMessage && activeErrorMessages.length > 0 && (
                                                <div className="rounded-xl border border-amber-200/80 bg-amber-50/85 px-3 py-2 text-[10.5px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                                                    <div className="flex items-start gap-2">
                                                        <AlertCircle size={12} className="mt-0.5 shrink-0" />
                                                        <div className="min-w-0">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <span className="font-semibold">结果待核验</span>
                                                                {activeErrorMessages.length > 1 && (
                                                                    <span className="inline-flex items-center rounded-full bg-amber-100/80 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-500/10 dark:text-amber-200">
                                                                        {activeErrorMessages.length} 项
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <p className="mt-1 line-clamp-2 text-[10.5px] leading-5 text-amber-700/90 dark:text-amber-200/90">
                                                                {activeErrorMessages[0]}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {false && hasFieldResults && activeSoftWarningLabels.length > 0 && (
                                                <div className="rounded-xl border border-blue-200/80 bg-blue-50/80 px-3 py-2 text-[10.5px] text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
                                                    <div className="flex items-start gap-2">
                                                        <AlertCircle size={12} className="mt-0.5 shrink-0" />
                                                        <div className="min-w-0 flex-1">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <span className="font-semibold">结果提示</span>
                                                                {activeSoftWarningLabels.length > 0 && (
                                                                    <span className="inline-flex items-center rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-semibold text-blue-700 ring-1 ring-inset ring-blue-200/80 dark:bg-white/[0.05] dark:text-blue-200 dark:ring-blue-800/70">
                                                                        {activeSoftWarningLabels.length} 项
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <div className="mt-1 flex flex-wrap gap-1.5">
                                                                {activeSoftWarningLabels.slice(0, 2).map((warning) => (
                                                                    <span
                                                                        key={warning}
                                                                        className="inline-flex items-center rounded-full bg-white/90 px-2 py-0.5 text-[10px] leading-4 text-blue-700 ring-1 ring-inset ring-blue-200/70 dark:bg-white/[0.05] dark:text-blue-200 dark:ring-blue-800/70"
                                                                    >
                                                                        {warning}
                                                                    </span>
                                                                ))}
                                                                {activeSoftWarningLabels.length > 2 && (
                                                                    <span className="inline-flex items-center rounded-full bg-blue-100/80 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-blue-500/10 dark:text-blue-200">
                                                                        +{activeSoftWarningLabels.length - 2}
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {activeDoc && fieldItems.length > 0 && filteredFieldItems.length === 0 && !errorMessage && (
                                                <div className="flex flex-col items-center justify-center gap-2 py-12 text-center rounded-xl border border-slate-100 bg-slate-50/50 dark:border-white/[0.05] dark:bg-white/[0.02]">
                                                    <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-white text-slate-300 shadow-sm ring-1 ring-slate-100 dark:bg-white/[0.05] dark:text-slate-500 dark:ring-white/[0.1]">
                                                        <Search size={18} />
                                                    </div>
                                                    <p className="text-[12px] font-medium text-slate-600 dark:text-slate-300">未找到匹配 "{resultSearchQuery}" 的字段</p>
                                                    <button
                                                        onClick={() => setResultSearchQuery('')}
                                                        className="mt-1 inline-flex items-center justify-center rounded-md bg-white px-3 py-1.5 text-[11px] font-medium text-slate-600 shadow-sm ring-1 ring-inset ring-slate-200 transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-95 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.1] dark:hover:bg-white/[0.08] dark:hover:text-slate-100"
                                                    >
                                                        清除搜索
                                                    </button>
                                                </div>
                                            )}

                                            {shouldShowTraceRootBlock && (
                                                <div className="mb-4 pb-3">
                                                    <div className="space-y-6">
                                                        {filteredFieldItems.length > 0 && (
                                                            <div id="trace-section-field" className="scroll-mt-24" data-testid="module2-trace-group-field">
                                                                <div className="mb-3 flex items-center gap-2">
                                                                    <div
                                                                        data-testid="module2-trace-group-label"
                                                                        className="px-2 py-0.5 rounded text-[11px] tabular-nums font-bold text-slate-600 bg-slate-100/80 dark:text-slate-300 dark:bg-white/[0.05]"
                                                                    >
                                                                        字段
                                                                    </div>
                                                                    <div className="h-px flex-1 bg-gradient-to-r from-slate-100 to-transparent dark:from-white/[0.05]"></div>
                                                                </div>
                                                                <div className="space-y-0">
                                                                    {filteredFieldItems.map((item) => renderFieldEvidenceCard(item))}
                                                                </div>
                                                            </div>
                                                        )}

                                                        {hasDocumentTraceDetailHits &&
                                                            renderTraceEvidenceContent({
                                                                inline: true,
                                                                groups: documentTraceGroups,
                                                                loading: false,
                                                                error: '',
                                                                emptyTitle: '当前文档暂无表格、图片或数据可视化定位',
                                                                emptyHint: '文档解析完成后，会在这里直接展示可回跳的表格、图片、图表和其他原文证据。',
                                                                forceGroupLabels: filteredFieldItems.length > 0,
                                                            })}
                                                    </div>
                                                </div>
                                            )}
                                            </div>
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
                    )}
                </div>
            </div>
            {pendingRemoveFile && (
                <div className="fixed inset-0 z-[58] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[1px]">
                    <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_28px_70px_rgba(15,23,42,0.28)] dark:border-white/[0.08] dark:bg-slate-900">
                        <div className="border-b border-slate-100/90 px-5 py-4 dark:border-white/[0.08]">
                            <p className="text-[16px] font-semibold text-slate-900 dark:text-slate-100">
                                确认移除文件
                            </p>
                            <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
                                将从当前工作区移除，必要时会同步取消解析并清理结果。
                            </p>
                        </div>
                        <div className="px-5 py-4">
                            <p className="text-[13px] leading-relaxed text-slate-700 dark:text-slate-200">
                                {pendingRemoveFile.message}
                            </p>
                        </div>
                        <div className="flex items-center justify-end gap-2 border-t border-slate-100/90 px-5 py-4 dark:border-white/[0.08]">
                            <button
                                type="button"
                                onClick={cancelRemoveFile}
                                className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2 text-[13px] font-semibold text-slate-600 transition hover:bg-slate-100 dark:border-white/[0.12] dark:bg-white/[0.03] dark:text-slate-300 dark:hover:bg-white/[0.08]"
                            >
                                取消
                            </button>
                            <button
                                type="button"
                                onClick={confirmRemoveFile}
                                className="inline-flex items-center justify-center rounded-xl bg-rose-600 px-4 py-2 text-[13px] font-semibold text-white transition hover:bg-rose-700"
                            >
                                确认移除
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {showAssistantHelp && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 animate-in fade-in zoom-in-95 duration-200">
                    <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-white/[0.02] border border-slate-100/80 dark:border-white/[0.05]">
                        <div className="flex items-center justify-between border-b border-slate-100 p-4 dark:border-white/[0.05]">
                            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                                <Bot className="text-blue-500" size={20} />
                                信息提取助手功能说明
                            </h3>
                            <button
                                onClick={() => setShowAssistantHelp(false)}
                                title="关闭助手说明"
                                aria-label="关闭助手说明"
                                className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-white/[0.08] dark:hover:text-slate-300 transition-colors"
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
                                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 font-bold">2</div>
                                <div>
                                    <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">多模态原文定位</h4>
                                    <p>点击提取结果中的字段，系统会自动定位到文档原文位置。支持文字、表格、印章及图片的精准定位。</p>
                                </div>
                            </div>
                            <div className="flex gap-3">
                                <div className="shrink-0 flex h-8 w-8 items-center justify-center rounded-full bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 font-bold">3</div>
                                <div>
                                    <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">交互式结果修正</h4>
                                    <p>如果对结果不满意，可直接告诉助手“金额不对，应该是示例值”，助手会根据反馈进行修正并重新定位。</p>
                                </div>
                            </div>
                        </div>
                        <div className="bg-slate-50 p-4 text-center dark:bg-white/[0.05] border-t border-slate-100 dark:border-white/[0.05]">
                            <button
                                onClick={() => setShowAssistantHelp(false)}
                                className="px-6 py-2 rounded-xl bg-blue-600 text-white font-bold hover:bg-blue-700 transition-colors shadow-soft-lg shadow-blue-500/20 text-sm"
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
