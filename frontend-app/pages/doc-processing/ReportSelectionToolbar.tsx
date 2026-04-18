import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlignCenter, AlignJustify, AlignLeft, Check, RotateCcw, Sparkles, Wand2, Expand, ScissorsLineDashed, X } from 'lucide-react';

import type { ReportQuickEditAction } from './lib/reportQuickEdit';
import type { ReportSelectionRect } from './lib/reportSelection';
import { computeToolbarPosition } from './lib/reportSelection';
import {
  REPORT_BLOCK_TYPE_OPTIONS,
  REPORT_FONT_SIZE_OPTIONS,
  REPORT_TEXT_ALIGN_OPTIONS,
  REPORT_TEXT_COLOR_OPTIONS,
  type ReportBlockType,
  type ReportTextAlign,
} from './lib/reportRichFormatting';

interface ReportSelectionToolbarProps {
  anchorRect: ReportSelectionRect;
  busyAction: ReportQuickEditAction | null;
  canUndo: boolean;
  manualEditOpen: boolean;
  manualEditValue: string;
  manualEditBusy: boolean;
  feedback: string;
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
}

const ACTIONS: Array<{
  key: ReportQuickEditAction;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}> = [
  { key: 'rewrite', label: '改写', icon: Wand2 },
  { key: 'expand', label: '扩写', icon: Expand },
  { key: 'condense', label: '精简', icon: ScissorsLineDashed },
  { key: 'polish', label: '润色', icon: Sparkles },
];

const ALIGN_ICON_BY_VALUE: Record<ReportTextAlign, React.ComponentType<{ size?: number; className?: string }>> = {
  left: AlignLeft,
  center: AlignCenter,
  justify: AlignJustify,
};

export const ReportSelectionToolbar: React.FC<ReportSelectionToolbarProps> = ({
  anchorRect,
  busyAction,
  canUndo,
  manualEditOpen,
  manualEditValue,
  manualEditBusy,
  feedback,
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
  const toolbarRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState(() => ({
    top: Math.max(12, anchorRect.top - 120),
    left: Math.max(12, anchorRect.left),
    placement: 'top' as const,
  }));

  useEffect(() => {
    const updatePosition = () => {
      const rect = toolbarRef.current?.getBoundingClientRect();
      const next = computeToolbarPosition(
        anchorRect,
        Math.ceil(rect?.width ?? 640),
        Math.ceil(rect?.height ?? (manualEditOpen ? 260 : 126)),
      );
      setPosition(next);
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    return () => window.removeEventListener('resize', updatePosition);
  }, [anchorRect, manualEditOpen]);

  const wrapperStyle = useMemo<React.CSSProperties>(() => ({
    position: 'fixed',
    top: position.top,
    left: position.left,
    zIndex: 120,
  }), [position.left, position.top]);

  return (
    <div
      ref={toolbarRef}
      style={wrapperStyle}
      data-report-selection-toolbar="true"
      onMouseDown={(event) => {
        if (
          !(event.target instanceof HTMLTextAreaElement)
          && !(event.target instanceof HTMLSelectElement)
        ) {
          event.preventDefault();
        }
      }}
      className="pointer-events-auto max-w-[min(94vw,720px)]"
    >
      <div className="overflow-hidden rounded-[22px] border border-[#d9e4f6] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(248,250,252,0.98))] p-2.5 text-slate-900 shadow-[0_20px_44px_-24px_rgba(15,23,42,0.22)] backdrop-blur-xl dark:border-white/12 dark:bg-[linear-gradient(180deg,rgba(15,23,42,0.94),rgba(15,23,42,0.9))] dark:text-slate-100 dark:shadow-[0_20px_44px_-24px_rgba(15,23,42,0.55)]">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onOpenManualEdit}
            className="inline-flex h-10 items-center gap-2 rounded-[14px] border border-[#d7e4fb] bg-white px-3 text-sm font-medium text-slate-700 transition-all hover:border-sky-300/40 hover:bg-sky-50 dark:border-white/10 dark:bg-white/6 dark:text-slate-100 dark:hover:border-sky-300/24 dark:hover:bg-white/10"
          >
            <Sparkles size={14} className="text-sky-300" />
            手动改
          </button>

          {ACTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => onAction(key)}
              disabled={Boolean(busyAction) || manualEditBusy}
              className="inline-flex h-10 items-center gap-2 rounded-[14px] border border-[#d7e4fb] bg-white px-3 text-sm font-medium text-slate-700 transition-all hover:border-sky-300/40 hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-55 dark:border-white/10 dark:bg-white/6 dark:text-slate-100 dark:hover:border-sky-300/24 dark:hover:bg-white/10"
            >
              <Icon size={14} className="text-sky-300" />
              {busyAction === key ? '处理中...' : label}
            </button>
          ))}

          <button
            type="button"
            onClick={onUndo}
            disabled={!canUndo || Boolean(busyAction) || manualEditBusy}
            className="inline-flex h-10 items-center gap-2 rounded-[14px] border border-rose-200 bg-rose-50 px-3 text-sm font-medium text-rose-700 transition-all hover:border-rose-300 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-45 dark:border-rose-300/18 dark:bg-rose-400/10 dark:text-rose-100 dark:hover:border-rose-200/28 dark:hover:bg-rose-400/16"
          >
            <RotateCcw size={14} />
            回退
          </button>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-[18px] border border-[#e3ebf7] bg-white/88 p-2.5 dark:border-white/10 dark:bg-white/6">
          <div className="flex items-center gap-2 rounded-[14px] border border-[#e4ebf8] bg-[#f8fbff] px-2.5 py-2 dark:border-white/10 dark:bg-slate-950/40">
            <span className="text-[11px] font-semibold tracking-[0.08em] text-slate-500 dark:text-slate-400">颜色</span>
            <div className="flex flex-wrap items-center gap-1.5">
              {REPORT_TEXT_COLOR_OPTIONS.map((option) => {
                const selected = (currentTextColor ?? '') === (option.value ?? '');
                return (
                  <button
                    key={option.label}
                    type="button"
                    title={option.label}
                    onClick={() => onTextColorChange(option.value)}
                    disabled={manualEditBusy}
                    className={`h-7 w-7 rounded-full border transition-all disabled:cursor-not-allowed disabled:opacity-45 ${
                      selected
                        ? 'scale-105 border-slate-900 ring-2 ring-sky-200 dark:border-white dark:ring-sky-400/50'
                        : 'border-[#d2dceb] hover:scale-105 dark:border-white/16'
                    }`}
                    style={{ backgroundColor: option.swatch }}
                  />
                );
              })}
            </div>
          </div>

          <label className="flex items-center gap-2 rounded-[14px] border border-[#e4ebf8] bg-[#f8fbff] px-2.5 py-2 text-[11px] font-semibold tracking-[0.08em] text-slate-500 dark:border-white/10 dark:bg-slate-950/40 dark:text-slate-400">
            字号
            <select
              value={currentFontSize ?? ''}
              onChange={(event) => onFontSizeChange(event.target.value || null)}
              disabled={manualEditBusy}
              className="rounded-[10px] border border-[#d7e4fb] bg-white px-2.5 py-1.5 text-xs font-medium tracking-normal text-slate-700 outline-none transition-all hover:border-sky-300 focus:border-sky-400 dark:border-white/10 dark:bg-slate-900/90 dark:text-slate-100"
            >
              {REPORT_FONT_SIZE_OPTIONS.map((option) => (
                <option key={option.label} value={option.value ?? ''}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 rounded-[14px] border border-[#e4ebf8] bg-[#f8fbff] px-2.5 py-2 text-[11px] font-semibold tracking-[0.08em] text-slate-500 dark:border-white/10 dark:bg-slate-950/40 dark:text-slate-400">
            段落
            <select
              value={currentBlockType}
              onChange={(event) => onBlockTypeChange(event.target.value as ReportBlockType)}
              disabled={manualEditBusy}
              className="rounded-[10px] border border-[#d7e4fb] bg-white px-2.5 py-1.5 text-xs font-medium tracking-normal text-slate-700 outline-none transition-all hover:border-sky-300 focus:border-sky-400 dark:border-white/10 dark:bg-slate-900/90 dark:text-slate-100"
            >
              {REPORT_BLOCK_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-center gap-1 rounded-[14px] border border-[#e4ebf8] bg-[#f8fbff] px-2 py-2 dark:border-white/10 dark:bg-slate-950/40">
            <span className="px-1 text-[11px] font-semibold tracking-[0.08em] text-slate-500 dark:text-slate-400">对齐</span>
            {REPORT_TEXT_ALIGN_OPTIONS.map((option) => {
              const Icon = ALIGN_ICON_BY_VALUE[option.value];
              const selected = currentTextAlign === option.value;

              return (
                <button
                  key={option.value}
                  type="button"
                  title={option.label}
                  onClick={() => onTextAlignChange(option.value)}
                  disabled={manualEditBusy}
                  className={`inline-flex h-8 w-8 items-center justify-center rounded-[10px] border transition-all disabled:cursor-not-allowed disabled:opacity-45 ${
                    selected
                      ? 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-400/40 dark:bg-sky-500/12 dark:text-sky-100'
                      : 'border-transparent bg-white text-slate-600 hover:border-[#d7e4fb] hover:bg-white dark:bg-slate-900/70 dark:text-slate-300 dark:hover:border-white/12 dark:hover:bg-slate-900'
                  }`}
                >
                  <Icon size={14} />
                </button>
              );
            })}
          </div>
        </div>

        {manualEditOpen && (
          <div className="mt-2 rounded-[18px] border border-[#e3ebf7] bg-white/90 p-3 dark:border-white/10 dark:bg-white/6">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold tracking-[0.12em] text-slate-600 dark:text-slate-300">手动替换选中文本</span>
              <span className="text-[11px] text-slate-500 dark:text-slate-400">{position.placement === 'top' ? '悬浮于选区上方' : '悬浮于选区下方'}</span>
            </div>
            <textarea
              value={manualEditValue}
              onChange={(event) => onManualEditChange(event.target.value)}
              rows={3}
              className="mt-2 w-full resize-none rounded-[14px] border border-[#d7e4fb] bg-white px-3 py-2 text-sm leading-6 text-slate-800 outline-none placeholder:text-slate-400 dark:border-white/10 dark:bg-slate-950/50 dark:text-slate-100 dark:placeholder:text-slate-500"
              placeholder="输入新的文本内容"
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-[11px] text-slate-500 dark:text-slate-400">修改将直接应用到当前会话的报告预览</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onManualEditCancel}
                  className="inline-flex h-9 items-center gap-1.5 rounded-[12px] border border-[#d7e4fb] bg-white px-3 text-xs font-medium text-slate-700 transition-all hover:bg-slate-50 dark:border-white/10 dark:bg-white/6 dark:text-slate-200 dark:hover:bg-white/10"
                >
                  <X size={13} />
                  取消
                </button>
                <button
                  type="button"
                  onClick={onManualEditApply}
                  disabled={!manualEditValue.trim() || manualEditBusy}
                  className="inline-flex h-9 items-center gap-1.5 rounded-[12px] border border-sky-300 bg-sky-600 px-3 text-xs font-medium text-white transition-all hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-45 dark:border-sky-300/16 dark:bg-sky-500/18 dark:text-sky-50 dark:hover:bg-sky-500/24"
                >
                  <Check size={13} />
                  {manualEditBusy ? '应用中...' : '应用修改'}
                </button>
              </div>
            </div>
          </div>
        )}

        {feedback ? (
          <div className="mt-2 text-[11px] text-slate-600 dark:text-slate-300">
            {feedback}
          </div>
        ) : null}
      </div>
    </div>
  );
};
