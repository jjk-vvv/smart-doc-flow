import React from 'react';
import { AlertCircle, CheckCircle, ScanLine } from 'lucide-react';
import { ReportSelectionToolbar } from '../ReportSelectionToolbar';
import type { ReportQuickEditAction } from '../lib/reportQuickEdit';
import type { ReportSelectionRect } from '../lib/reportSelection';
import {
  buildReportTextSegments,
  type ReportBlockType,
  type ReportFormattingState,
  type ReportTextAlign,
} from '../lib/reportRichFormatting';

type MobileReportBlock = {
  key: string;
  type: ReportBlockType;
  text: string;
};

type ReportToneStyles = {
  heading1: string;
  heading2: string;
  heading3: string;
  paragraph: string;
};

type MobileReportSelection = {
  fileId: string;
  selectedText: string;
  rect: ReportSelectionRect;
};

type MobileReportPageProps = {
  currentFileId: string | null;
  hasReport: boolean;
  currentFileName: string | null;
  emptyStateClassName: string;
  panelSoftClassName: string;
  activeStatus?: 'idle' | 'active' | 'completed' | 'fallback' | 'failed';
  blocks: MobileReportBlock[];
  formatting: ReportFormattingState;
  toneStyles: ReportToneStyles;
  streamHighlightNonce: number;
  reportContentRef: React.RefObject<HTMLDivElement | null>;
  reportPreviewScrollRef: React.RefObject<HTMLDivElement | null>;
  selection: MobileReportSelection | null;
  busyAction: ReportQuickEditAction | null;
  canUndo: boolean;
  manualEditOpen: boolean;
  manualEditValue: string;
  manualEditBusy: boolean;
  toolbarFeedback: string;
  currentTextColor: string | null;
  currentFontSize: string | null;
  currentBlockType: ReportBlockType;
  currentTextAlign: ReportTextAlign;
  onAction: (action: ReportQuickEditAction) => void;
  onUndo: () => void;
  onOpenManualEdit: () => void;
  onManualEditChange: (value: string) => void;
  onManualEditApply: () => void;
  onManualEditCancel: () => void;
  onTextColorChange: (value: string | null) => void;
  onFontSizeChange: (value: string | null) => void;
  onBlockTypeChange: (value: ReportBlockType) => void;
  onTextAlignChange: (value: ReportTextAlign) => void;
};

export const MobileReportPage: React.FC<MobileReportPageProps> = ({
  currentFileId,
  hasReport,
  currentFileName,
  emptyStateClassName,
  panelSoftClassName,
  activeStatus,
  blocks,
  formatting,
  toneStyles,
  streamHighlightNonce,
  reportContentRef,
  reportPreviewScrollRef,
  selection,
  busyAction,
  canUndo,
  manualEditOpen,
  manualEditValue,
  manualEditBusy,
  toolbarFeedback,
  currentTextColor,
  currentFontSize,
  currentBlockType,
  currentTextAlign,
  onAction,
  onUndo,
  onOpenManualEdit,
  onManualEditChange,
  onManualEditApply,
  onManualEditCancel,
  onTextColorChange,
  onFontSizeChange,
  onBlockTypeChange,
  onTextAlignChange,
}) => {
  if (!currentFileId) {
    return (
      <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${emptyStateClassName}`}>
        <ScanLine size={54} className="mb-4 text-[#9fb8d0] opacity-70" />
        <p className="text-lg font-medium text-[#274768] dark:text-slate-100">当前没有可查看报告</p>
      </div>
    );
  }

  if (!hasReport) {
    return (
      <div className={`flex h-full flex-col items-center justify-center rounded-[26px] px-8 text-center ${emptyStateClassName}`}>
        <ScanLine size={54} className="mb-4 text-[#9fb8d0] opacity-70" />
        <p className="text-lg font-medium text-[#274768] dark:text-slate-100">暂无分析或提取报告</p>
        <p className="mt-2 text-sm text-[#6b8198] dark:text-slate-400">先在对话页发起分析或提取请求，结果生成后会出现在这里。</p>
      </div>
    );
  }

  if (blocks.length === 0) {
    if (activeStatus === 'failed') {
      return (
        <div className={`flex h-full items-center gap-3 rounded-2xl px-4 py-3 text-sm text-[#8d3d49] dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-100 ${panelSoftClassName}`}>
          <AlertCircle size={16} />
          <span>本次分析暂未生成报告，请稍后重试或缩小分析范围。</span>
        </div>
      );
    }

    if (activeStatus === 'fallback') {
      return (
        <div className={`flex h-full items-center gap-3 rounded-2xl px-4 py-3 text-sm text-[#7b442e] dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-100 ${panelSoftClassName}`}>
          <CheckCircle size={16} />
          <span>已返回本地整理摘要，你可以先查看结果，稍后再重试 AI 分析。</span>
        </div>
      );
    }

    if (activeStatus === 'completed') {
      return (
        <div className={`flex h-full items-center gap-3 rounded-2xl px-4 py-3 text-sm text-[#215d3b] dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-100 ${panelSoftClassName}`}>
          <AlertCircle size={16} />
          <span>分析已完成，但本次报告内容为空。请重试一次，或缩小分析范围。</span>
        </div>
      );
    }
  }

  return (
    <div ref={reportPreviewScrollRef} className="h-full overflow-auto">
      <div className="mx-auto max-w-[1120px]">
        <div
          ref={reportContentRef}
          className={`rounded-[22px] border bg-[linear-gradient(180deg,#ffffff,#fcfdff)] px-5 py-5 shadow-[0_18px_38px_-32px_rgba(42,100,246,0.14)] dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.9),rgba(15,23,42,0.82))] dark:shadow-[0_24px_48px_-36px_rgba(2,6,23,0.78)] sm:px-8 sm:py-7 ${panelSoftClassName}`}
        >
          {blocks.map((block, index) => {
            const isStreamingTailBlock = activeStatus === 'active' && index === blocks.length - 1;
            const blockFormatting = formatting[block.key];
            const effectiveBlockType = blockFormatting?.type ?? block.type;
            const effectiveAlign = blockFormatting?.align ?? 'left';
            const textSegments = buildReportTextSegments(block.text, blockFormatting?.inlineFormats);

            const renderedText = textSegments.map((segment, segmentIndex) => (
              <span
                key={`${block.key}-${segmentIndex}`}
                style={{
                  color: segment.color,
                  fontSize: segment.fontSize,
                }}
              >
                {segment.text}
              </span>
            ));

            if (effectiveBlockType === 'heading1') {
              return (
                <h4
                  key={isStreamingTailBlock ? `${block.key}-${streamHighlightNonce}` : block.key}
                  data-report-block-key={block.key}
                  data-report-block-type={effectiveBlockType}
                  className={`${toneStyles.heading1} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                  style={{ textAlign: effectiveAlign }}
                >
                  {renderedText}
                </h4>
              );
            }

            if (effectiveBlockType === 'heading2') {
              return (
                <h5
                  key={isStreamingTailBlock ? `${block.key}-${streamHighlightNonce}` : block.key}
                  data-report-block-key={block.key}
                  data-report-block-type={effectiveBlockType}
                  className={`${toneStyles.heading2} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                  style={{ textAlign: effectiveAlign }}
                >
                  {renderedText}
                </h5>
              );
            }

            if (effectiveBlockType === 'heading3') {
              return (
                <div
                  key={isStreamingTailBlock ? `${block.key}-${streamHighlightNonce}` : block.key}
                  data-report-block-key={block.key}
                  data-report-block-type={effectiveBlockType}
                  className={`${toneStyles.heading3} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                  style={{ textAlign: effectiveAlign }}
                >
                  {renderedText}
                </div>
              );
            }

            return (
              <p
                key={isStreamingTailBlock ? `${block.key}-${streamHighlightNonce}` : block.key}
                data-report-block-key={block.key}
                data-report-block-type={effectiveBlockType}
                className={`${toneStyles.paragraph} ${isStreamingTailBlock ? 'report-stream-highlight typewriter' : ''}`}
                style={{ textAlign: effectiveAlign }}
              >
                {renderedText}
              </p>
            );
          })}
        </div>

        {selection?.fileId === currentFileId ? (
          <ReportSelectionToolbar
            anchorRect={selection.rect}
            busyAction={busyAction}
            canUndo={canUndo}
            manualEditOpen={manualEditOpen}
            manualEditValue={manualEditValue}
            manualEditBusy={manualEditBusy}
            feedback={toolbarFeedback}
            currentTextColor={currentTextColor}
            currentFontSize={currentFontSize}
            currentBlockType={currentBlockType}
            currentTextAlign={currentTextAlign}
            onAction={onAction}
            onUndo={onUndo}
            onOpenManualEdit={onOpenManualEdit}
            onManualEditChange={onManualEditChange}
            onManualEditApply={onManualEditApply}
            onManualEditCancel={onManualEditCancel}
            onTextColorChange={onTextColorChange}
            onFontSizeChange={onFontSizeChange}
            onBlockTypeChange={onBlockTypeChange}
            onTextAlignChange={onTextAlignChange}
          />
        ) : null}
      </div>

      {currentFileName ? (
        <div className="mt-3 text-center text-xs text-[#6b8198] dark:text-slate-400">
          当前报告来源：{currentFileName}
        </div>
      ) : null}
    </div>
  );
};
