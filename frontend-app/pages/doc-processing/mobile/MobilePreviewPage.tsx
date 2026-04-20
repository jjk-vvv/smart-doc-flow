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
  onSwitchMode,
  onPdfPageInputChange,
  onPdfPageInputCommit,
  onNavigatePdfPage,
  onZoomOut,
  onZoomIn,
  onRotate,
  onResetView,
}) => {
  const shouldShowModeSwitcher = Boolean(currentFile) && (canPreviewOriginal || canComparePreview);

  return (
    <div className="absolute inset-0 flex flex-col">
      {currentFile ? (
      <div className="relative z-10 shrink-0 space-y-1 border-b border-slate-100/50 bg-white/95 pb-1.5 pt-1.5 shadow-sm backdrop-blur-xl dark:border-slate-800/50 dark:bg-slate-950/95">
        {shouldShowModeSwitcher ? (
          <div className="flex items-center gap-1.5 overflow-x-auto px-3 pb-1">
            <button
              type="button"
              onClick={() => onSwitchMode('current')}
              className={`shrink-0 rounded-full px-3 py-1 text-[13px] font-medium ${
                mode === 'current' ? secondaryActiveButtonClassName : secondaryButtonClassName
              }`}
            >
              {currentFile?.sourceFileId ? '修改文件' : '当前文件'}
            </button>
            {canPreviewOriginal ? (
              <button
                type="button"
                onClick={() => onSwitchMode('original')}
                className={`shrink-0 rounded-full px-3 py-1 text-[13px] font-medium ${
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
                className={`shrink-0 rounded-full px-3 py-1 text-[13px] font-medium ${
                  mode === 'compare' ? secondaryActiveButtonClassName : secondaryButtonClassName
                }`}
              >
                前后对比
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="flex items-center gap-1.5 overflow-x-auto px-3 pb-0.5 hide-scrollbar">
          {isPreviewPdf && (
            <>
              <button
                type="button"
                onClick={() => onNavigatePdfPage(pdfPage - 1)}
                disabled={pdfPage <= 1}
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
                title="上一页"
                aria-label="上一页"
              >
                <ChevronLeft size={16} strokeWidth={2} />
              </button>
              <div className="flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-slate-200/60 bg-white/90 px-3 shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:border-slate-700/80 dark:bg-slate-900/80">
                <span className="text-[12px] font-medium text-slate-500 dark:text-slate-400">第</span>
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
                  className="w-10 bg-transparent text-center text-[13px] font-bold text-slate-700 outline-none dark:text-slate-200"
                />
                <span className="text-[12px] font-medium text-slate-500 dark:text-slate-400">
                  页{maxPdfPage ? ` / ${maxPdfPage}` : ''}
                </span>
              </div>
              <button
                type="button"
                onClick={() => onNavigatePdfPage(pdfPage + 1)}
                disabled={Boolean(maxPdfPage && pdfPage >= maxPdfPage)}
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
                title="下一页"
                aria-label="下一页"
              >
                <ChevronRight size={16} strokeWidth={2} />
              </button>
              <div className="h-4 w-px bg-slate-200 mx-1 dark:bg-slate-700"></div>
            </>
          )}
          <button
            type="button"
            onClick={onZoomOut}
            disabled={!canTransformPreview}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="缩小"
            aria-label="缩小"
          >
            <ZoomOut size={14} strokeWidth={2} />
          </button>
          <span className="min-w-[3rem] shrink-0 text-center text-[12px] font-semibold text-slate-600 dark:text-slate-400">
            {Math.round(scale * 100)}%
          </span>
          <button
            type="button"
            onClick={onZoomIn}
            disabled={!canTransformPreview}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="放大"
            aria-label="放大"
          >
            <ZoomIn size={14} strokeWidth={2} />
          </button>
          <button
            type="button"
            onClick={onRotate}
            disabled={!canTransformPreview}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="旋转"
            aria-label="旋转"
          >
            <RotateCw size={14} strokeWidth={2} />
          </button>
          <button
            type="button"
            onClick={onResetView}
            disabled={!canTransformPreview && !isPreviewPdf}
            className={`shrink-0 rounded-full px-3 py-1 text-[12px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${secondaryButtonClassName}`}
            title="重置视图"
          >
            重置
          </button>
        </div>
      </div>
    ) : null}

    <div className="relative min-h-0 flex-1 w-full bg-white dark:bg-slate-950">
      {body}
    </div>
    </div>
  );
};
