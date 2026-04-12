import React from 'react';

import { cn } from '../../../lib/utils';
import {
    humanizeAssistantLockQuality,
    humanizeAssistantLockType,
    summarizeAssistantFactPreview,
} from './helpers';
import type { AssistantObjectLock } from './types';

type AssistantLockBannerProps = {
    lock: AssistantObjectLock | null;
    compact?: boolean;
};

export const AssistantLockBanner: React.FC<AssistantLockBannerProps> = ({
    lock,
    compact = false,
}) => {
    if (!lock) return null;

    const rowIndex = Number(lock.row_index || 0);
    const sourceRowIndex = Number(lock.source_row_index || 0);
    const lockQuality = String(lock.lock_quality || '').trim();
    const meta = lock.metadata && typeof lock.metadata === 'object' ? lock.metadata : {};
    const header = String(meta.header || '').trim();
    const recognitionTier = String(meta.recognition_tier || '').trim();
    const snippet = String(meta.snippet || '').trim();
    const factPreview = Array.isArray(meta.fact_preview)
        ? meta.fact_preview.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>
        : [];

    const bits = [
        `类型: ${humanizeAssistantLockType(String(lock.lock_type || ''))}`,
        lock.page ? `第 ${lock.page} 页` : '',
        rowIndex > 0 ? `表内第 ${rowIndex} 行` : '',
        sourceRowIndex > 0 ? `原始第 ${sourceRowIndex} 行` : '',
        header ? `当前列: ${header}` : '',
        lockQuality ? `锁定强度: ${humanizeAssistantLockQuality(lockQuality)}` : '',
        recognitionTier ? `识别层级: ${recognitionTier}` : '',
    ].filter(Boolean);

    return (
        <div
            className={cn(
                "rounded-2xl border border-blue-200/70 bg-blue-50/80 px-4 py-3 text-xs text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/20 dark:text-blue-100",
                compact && "rounded-xl px-3 py-2 text-[11px] tabular-nums",
            )}
        >
            <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-white px-2 py-0.5 text-[10px] tabular-nums font-semibold uppercase tracking-wide text-blue-700 ring-1 ring-inset ring-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:ring-blue-900/70">
                    上下文锁定
                </span>
                <span className="font-semibold">
                    {lock.label || lock.object_id || '当前对象'}
                </span>
            </div>
            {bits.length > 0 && (
                <div className="mt-1.5 text-[11px] tabular-nums leading-relaxed text-blue-800/90 dark:text-blue-100/80">
                    {bits.join(' · ')}
                </div>
            )}
            {snippet && (
                <div className="mt-2 rounded-xl bg-white/80 px-3 py-2 text-[10px] tabular-nums leading-relaxed text-blue-900/90 ring-1 ring-inset ring-blue-200/70 dark:bg-white/[0.05] dark:text-blue-100/90 dark:ring-blue-900/60">
                    当前摘要：{snippet}
                </div>
            )}
            {String(lock.lock_type || '').trim().toLowerCase() === 'ocr_fact_group' && factPreview.length > 0 && (
                <div className="mt-2 rounded-xl bg-white/80 px-3 py-2 text-[10px] tabular-nums leading-relaxed text-blue-900/90 ring-1 ring-inset ring-blue-200/70 dark:bg-white/[0.05] dark:text-blue-100/90 dark:ring-blue-900/60">
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
