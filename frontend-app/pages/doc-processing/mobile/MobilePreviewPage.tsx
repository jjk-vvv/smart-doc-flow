import React from 'react';
import { ChevronLeft, ChevronRight, RotateCw, ZoomIn, ZoomOut } from 'lucide-react';

type MobilePreviewFile = {
  name: string;
  sourceFileId?: string;
};

type MobilePreviewPageProps = {
  currentFile: MobilePreviewFile | null;
  mode: 'current' | 'original' | 'compare';
  canPreviewOriginal: boolean;
  canComparePreview: boolean;
  isPreviewPdf: boolean;
  canTransformPreview: boolean;
  pdfPage: number;
  maxPdfPage: number | null;
  pdfPageInput: string;
  scale: number;
  body: React.ReactNode;
  secondaryButtonClassName: string;
  secondaryActiveButtonClassName: string;
  primaryButtonClassName: string;
  onDownload: () => void;
  onSwitchMode: (mode: 'current' | 'original' | 'compare') => void;
  onPdfPageInputChange: (value: string) => void;
  onPdfPageInputCommit: () => void;
  onNavigatePdfPage: (page: number) => void;
  onZoomOut: () => void;
  onZoomIn: () => void;
  onRotate: () => void;
  onResetView: () => void;
};

export const MobilePreviewPage: React.FC<MobilePreviewPageProps> = ({
  currentFile,
  mode,
  canPreviewOriginal,
  canComparePreview,
  isPreviewPdf,
  canTransformPreview,
  pdfPage,
  maxPdfPage,
  pdfPageInput,
  scale,
  body,
  secondaryButtonClassName,
  secondaryActiveButtonClassName,
  primaryButtonClassName,
  onDownload,
  onSwitchMode,
  onPdfPageInputChange,
  onPdfPageInputCommit,
  onNavigatePdfPage,
  onZoomOut,
  onZoomIn,
  onRotate,
  onResetView,
}) => {
  const shouldShowModeSwitcher = Boolean(currentFile) && mode !== 'original';

  return (
    <div className="flex h-full min-h-0 flex-col">
      {currentFile ? (
      <div className="mt-3 shrink-0 space-y-2.5">
        {shouldShowModeSwitcher ? (
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            {canPreviewOriginal ? (
              <button
                type="button"
                onClick={() => onSwitchMode('original')}
                className={`shrink-0 rounded-2xl px-3 py-1.5 text-sm font-medium ${
                  mode === 'original' ? secondaryActiveButtonClassName : secondaryButtonClassName
                }`}
              >
                原文件
              </button>
            ) : null}
            {canComparePreview ? (
              <button
                type="button"
                onClick={() => onSwitchMode('compare')}
                className={`shrink-0 rounded-2xl px-3 py-1.5 text-sm font-medium ${
                  mode === 'compare' ? secondaryActiveButtonClassName : secondaryButtonClassName
                }`}
              >
                前后对比
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          {isPreviewPdf && (
            <>
              <button
                type="button"
                onClick={() => onNavigatePdfPage(pdfPage - 1)}
                disabled={pdfPage <= 1}
                className={`shrink-0 rounded-xl p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
                title="上一页"
                aria-label="上一页"
              >
                <ChevronLeft size={16} />
              </button>
              <div className="flex shrink-0 items-center gap-2 rounded-xl border border-[#deebff] bg-white/88 px-2.5 py-1.5 shadow-[0_8px_18px_-18px_rgba(42,100,246,0.18)] dark:border-slate-700 dark:bg-slate-900/88 dark:shadow-none">
                <span className="text-xs font-medium text-[#6c8197] dark:text-slate-400">第</span>
                <input
                  type="number"
                  min={1}
                  max={maxPdfPage ?? undefined}
                  value={pdfPageInput}
                  onChange={(event) => onPdfPageInputChange(event.target.value)}
                  onBlur={onPdfPageInputCommit}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      onPdfPageInputCommit();
                    }
                  }}
                  className="w-14 rounded-lg border border-[#d6e4fb] bg-white px-2 py-1 text-center text-xs font-semibold text-[#36516f] outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                />
                <span className="text-xs font-medium text-[#6c8197] dark:text-slate-400">
                  页{maxPdfPage ? ` / ${maxPdfPage}` : ''}
                </span>
              </div>
              <button
                type="button"
                onClick={() => onNavigatePdfPage(pdfPage + 1)}
                disabled={Boolean(maxPdfPage && pdfPage >= maxPdfPage)}
                className={`shrink-0 rounded-xl p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
                title="下一页"
                aria-label="下一页"
              >
                <ChevronRight size={16} />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={onZoomOut}
            disabled={!canTransformPreview}
            className={`shrink-0 rounded-xl p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="缩小"
            aria-label="缩小"
          >
            <ZoomOut size={16} />
          </button>
          <span className="min-w-[4.25rem] shrink-0 text-center text-xs font-semibold text-[#6c8197] dark:text-slate-400">
            {Math.round(scale * 100)}%
          </span>
          <button
            type="button"
            onClick={onZoomIn}
            disabled={!canTransformPreview}
            className={`shrink-0 rounded-xl p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="放大"
            aria-label="放大"
          >
            <ZoomIn size={16} />
          </button>
          <button
            type="button"
            onClick={onRotate}
            disabled={!canTransformPreview}
            className={`shrink-0 rounded-xl p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="旋转"
            aria-label="旋转"
          >
            <RotateCw size={16} />
          </button>
          <button
            type="button"
            onClick={onResetView}
            disabled={!canTransformPreview && !isPreviewPdf}
            className={`shrink-0 rounded-xl px-3 py-2 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="重置视图"
          >
            重置
          </button>
        </div>
      </div>
    ) : null}

    <div className="min-h-0 flex-1 overflow-hidden px-1.5 py-2">
      {body}
    </div>
    </div>
  );
};
