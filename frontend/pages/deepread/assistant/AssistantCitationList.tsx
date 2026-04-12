import React from 'react';
import { FileImage, FileSpreadsheet, FileText } from 'lucide-react';

import { cn } from '../../../lib/utils';
import type { AssistantCitation } from './types';

type AssistantCitationListProps = {
    citations?: AssistantCitation[] | null;
    compact?: boolean;
    onSelectCitation: (citation: AssistantCitation) => void;
};

export const AssistantCitationList: React.FC<AssistantCitationListProps> = ({
    citations,
    compact = false,
    onSelectCitation,
}) => {
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
                        onClick={() => onSelectCitation(citation)}
                        className={cn(
                            "w-full rounded-xl border border-slate-100/50 bg-slate-50/80 px-3 py-2 text-left transition-colors hover:border-blue-300 hover:bg-blue-50/70 dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:border-blue-500/30 dark:hover:bg-white/[0.05]",
                            compact && "rounded-lg px-2.5 py-2",
                        )}
                        title="定位到该引用证据"
                    >
                        <div className="flex items-start gap-2">
                            <div
                                className={cn(
                                    "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-white text-slate-500 ring-1 ring-inset ring-slate-200/70 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.05]",
                                    compact && "h-5 w-5 rounded-md",
                                )}
                            >
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
                                    <span
                                        className={cn(
                                            "text-[11px] tabular-nums font-semibold text-slate-800 dark:text-slate-100",
                                            compact && "text-[10px] tabular-nums",
                                        )}
                                    >
                                        {citation.title || citation.object_id || '引用证据'}
                                    </span>
                                    <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] tabular-nums font-medium text-slate-500 ring-1 ring-inset ring-slate-200/80 dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.05]">
                                        {citation.citation_type || 'other'}
                                    </span>
                                </div>
                                {summaryBits.length > 0 && (
                                    <div className="mt-1 text-[10px] tabular-nums leading-relaxed text-slate-500 dark:text-slate-400">
                                        {summaryBits.join(' · ')}
                                    </div>
                                )}
                                {value && citation.citation_type === 'table' && (
                                    <div className="mt-1 text-[11px] tabular-nums font-medium text-slate-800 dark:text-slate-200">
                                        当前值：{value}
                                    </div>
                                )}
                                {keyPoints.length > 0 && (
                                    <div className="mt-1 text-[10px] tabular-nums leading-relaxed text-slate-600 dark:text-slate-300">
                                        要点：{keyPoints.slice(0, 3).join('；')}
                                    </div>
                                )}
                                {!!citation.snippet && (
                                    <div className="mt-1 line-clamp-3 text-[10px] tabular-nums leading-relaxed text-slate-500 dark:text-slate-400">
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
