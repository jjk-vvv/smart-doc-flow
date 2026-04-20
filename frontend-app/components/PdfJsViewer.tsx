import React, { useEffect, useRef, useState } from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';

export type PdfViewMode = 'fit-width' | 'fit-page' | 'actual';

type PdfJsViewerProps = {
  src: string;
  scale: number;
  rotation: number;
  viewMode: PdfViewMode;
  borderless?: boolean; // 新增: 是否启用无边框全屏模式
  scrollRequest?: {
    page: number;
    nonce: number;
  } | null;
  onPageCount?: (count: number) => void;
  onVisiblePageChange?: (page: number) => void;
};

export const PdfJsViewer: React.FC<PdfJsViewerProps> = ({
  src,
  scale,
  rotation,
  viewMode,
  borderless = false,
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
  const [viewportHeight, setViewportHeight] = useState(0);
  const [renderedPageCount, setRenderedPageCount] = useState(0);

  const swapLoopbackHost = (hostname: string): string | null => {
    const normalized = String(hostname || '').trim().toLowerCase();
    if (normalized === 'localhost') return '127.0.0.1';
    if (normalized === '127.0.0.1') return 'localhost';
    return null;
  };

  const buildPdfFetchCandidates = (targetSrc: string): string[] => {
    const normalizedSrc = String(targetSrc || '').trim();
    if (!normalizedSrc) return [];

    const candidates: string[] = [];
    const push = (value: string) => {
      const normalized = String(value || '').trim();
      if (!normalized) return;
      if (candidates.includes(normalized)) return;
      candidates.push(normalized);
    };

    push(normalizedSrc);

    if (/^https?:\/\//i.test(normalizedSrc)) {
      try {
        const parsed = new URL(normalizedSrc);
        const swappedHost = swapLoopbackHost(parsed.hostname);
        if (swappedHost) {
          const swapped = new URL(parsed.toString());
          swapped.hostname = swappedHost;
          push(swapped.toString());
        }
        if (parsed.pathname.startsWith('/extract/')) {
          push(`${parsed.pathname}${parsed.search}${parsed.hash}`);
        }
      } catch {
        // ignore malformed URL and keep existing candidates
      }
      return candidates;
    }

    if (normalizedSrc.startsWith('/')) {
      if (typeof window !== 'undefined') {
        const origin = String(window.location.origin || '').trim();
        if (origin) {
          push(`${origin}${normalizedSrc}`);
          try {
            const parsedOrigin = new URL(origin);
            const swappedHost = swapLoopbackHost(parsedOrigin.hostname);
            if (swappedHost) {
              const swappedOrigin = new URL(parsedOrigin.toString());
              swappedOrigin.hostname = swappedHost;
              push(`${swappedOrigin.origin}${normalizedSrc}`);
            }
          } catch {
            // ignore invalid origin
          }
        }
      }
    }

    return candidates;
  };

  const resolvePdfDocumentSource = async (targetSrc: string, signal: AbortSignal) => {
    const normalizedSrc = String(targetSrc || '').trim();
    if (!normalizedSrc) {
      throw new Error('PDF preview source is empty');
    }

    const shouldHydrateBinary =
      normalizedSrc.startsWith('blob:')
      || normalizedSrc.startsWith('data:')
      || normalizedSrc.startsWith('/')
      || /^https?:\/\//i.test(normalizedSrc);

    if (!shouldHydrateBinary) {
      return {
        url: normalizedSrc,
        withCredentials: false,
      };
    }

    const candidates = buildPdfFetchCandidates(normalizedSrc);
    const failures: string[] = [];
    for (const candidate of candidates) {
      try {
        const response = await fetch(candidate, {
          credentials: 'include',
          cache: 'no-store',
          signal,
        });
        if (!response.ok) {
          failures.push(`${candidate} -> HTTP ${response.status}`);
          continue;
        }
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength <= 0) {
          failures.push(`${candidate} -> empty body`);
          continue;
        }
        return {
          data: new Uint8Array(buffer),
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'request failed';
        failures.push(`${candidate} -> ${message}`);
      }
    }

    const summary = failures.slice(0, 3).join(' | ');
    throw new Error(summary ? `PDF preview request failed: ${summary}` : 'PDF preview request failed');
  };

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
    const stackTarget = stackRef.current;
    const scrollTarget = scrollRef.current;
    if ((!stackTarget && !scrollTarget) || typeof ResizeObserver === 'undefined') return;

    const updateMetrics = () => {
      setStackWidth(Math.max(0, Math.floor(stackTarget?.clientWidth || scrollTarget?.clientWidth || 0)));
      setViewportHeight(Math.max(0, Math.floor(scrollTarget?.clientHeight || 0)));
    };

    updateMetrics();
    const observer = new ResizeObserver(() => updateMetrics());
    if (stackTarget) {
      observer.observe(stackTarget);
    }
    if (scrollTarget && scrollTarget !== stackTarget) {
      observer.observe(scrollTarget);
    }

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: any = null;
    const abortController = new AbortController();

    const load = async () => {
      setLoading(true);
      setError('');
      setPageCount(0);
      setRenderedPageCount(0);
      try {
        const pdfjsLib: any = await import('pdfjs-dist');
        if (!pdfjsLib.GlobalWorkerOptions.workerSrc) {
          pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
            'pdfjs-dist/build/pdf.worker.min.mjs',
            import.meta.url
          ).toString();
        }
        const documentSource = await resolvePdfDocumentSource(src, abortController.signal);
        if (cancelled) {
          return;
        }
        loadingTask = pdfjsLib.getDocument(documentSource);
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
        const aborted =
          abortController.signal.aborted
          || (err instanceof DOMException && err.name === 'AbortError');
        if (!cancelled && !aborted) {
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
      abortController.abort();
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
      if (!doc || pageCount === 0 || stackWidth <= 0 || viewportHeight <= 0) return;
      try {
        setLoading(true);
        setError('');
        setRenderedPageCount(0);
        const safeRotation = Number(rotation) || 0;
        const safeScale = Math.max(0.5, scale);
        const pixelRatio = window.devicePixelRatio || 1;
        const availableWidth = Math.max(0, stackWidth - 8);
        const availableHeight = Math.max(0, viewportHeight - 20);

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
          const fitWidthScale = availableWidth > 0
            ? availableWidth / Math.max(1, baseViewport.width)
            : 1;
          const fitPageScale = availableHeight > 0
            ? Math.min(
                fitWidthScale,
                availableHeight / Math.max(1, baseViewport.height)
              )
            : fitWidthScale;
          const baseScale = viewMode === 'fit-page'
            ? fitPageScale
            : viewMode === 'actual'
              ? 1
              : fitWidthScale;
          const viewport = pdfPage.getViewport({
            scale: Math.max(0.35, baseScale * safeScale),
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
          setRenderedPageCount((current) => Math.max(current, pageNumber));
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
  }, [docReadyTick, pageCount, rotation, scale, src, stackWidth, viewMode, viewportHeight]);

  useEffect(() => {
    if (!scrollRequest?.page || pageCount === 0 || typeof window === 'undefined') return;

    const targetPage = Math.min(Math.max(1, Math.round(scrollRequest.page)), pageCount);
    const targetNode = pageWrapperRefs.current[targetPage - 1];
    const container = scrollRef.current;
    if (!targetNode || !container) return;

    const raf = window.requestAnimationFrame(() => {
      const top = Math.max(0, targetNode.offsetTop - 12);
      container.scrollTo({
        top,
        behavior: targetPage === 1 ? 'auto' : 'smooth',
      });
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

  const hasFirstPagePainted = renderedPageCount > 0;
  const hasMorePagesPending = loading && hasFirstPagePainted && renderedPageCount < pageCount;

  return (
    <div className={`relative h-full w-full overflow-hidden ${borderless ? 'bg-white dark:bg-slate-950' : 'bg-slate-100/70 dark:bg-transparent'}`}>
      <div
        ref={scrollRef}
        onScroll={scheduleVisiblePageSync}
        className={`absolute inset-0 z-0 overflow-auto overscroll-contain custom-scrollbar px-0 py-0`}
      >
        <div
          ref={stackRef}
          className={`mx-auto flex min-h-full w-full flex-col items-center gap-0 pb-0 bg-white dark:bg-slate-950`}
        >
          {Array.from({ length: pageCount }, (_, index) => index + 1).map((pageNumber) => (
            <div
              key={`${src}-${pageNumber}`}
              ref={(node) => {
                pageWrapperRefs.current[pageNumber - 1] = node;
              }}
              data-page-number={pageNumber}
              className={`mx-auto w-fit max-w-full overflow-hidden bg-white dark:bg-slate-950 ${
                borderless
                  ? 'rounded-none border-b border-slate-100/60 shadow-none dark:border-slate-800'
                  : 'rounded-none border-none shadow-none dark:border-none'
              }`}
            >
              <canvas
                ref={(node) => {
                  pageCanvasRefs.current[pageNumber - 1] = node;
                }}
                className="mx-auto block h-auto max-w-full bg-white dark:bg-slate-950"
              />
            </div>
          ))}
        </div>
      </div>
      {loading && !hasFirstPagePainted && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/20 dark:bg-slate-900/20">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/92 px-3 py-1.5 text-xs text-slate-600 shadow-sm dark:border-white/[0.05] dark:bg-white/[0.02]/92 dark:text-slate-300">
            <Loader2 size={14} className="animate-spin" />
            正在加载文档预览...
          </div>
        </div>
      )}
      {hasMorePagesPending && (
        <div className="pointer-events-none absolute right-3 top-3 z-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/90 px-3 py-1 text-[11px] text-slate-600 shadow-sm backdrop-blur-sm dark:border-white/[0.05] dark:bg-white/[0.02]/88 dark:text-slate-300">
            <Loader2 size={12} className="animate-spin" />
            正在补充其余页面...
          </div>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-white/84 p-4 text-center dark:bg-[#0B1120]/82">
          <p className="max-w-[420px] text-xs text-slate-600 dark:text-slate-300">{error}</p>
        </div>
      )}
    </div>
  );
};
