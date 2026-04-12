import React from 'react';
import { AlertCircle, ChevronRight, Loader2, Sparkles } from 'lucide-react';

import { cn } from '../../../lib/utils';
import type { AssistantActionPreview, AssistantCitation, AssistantObjectLock, AssistantToolEvent } from './types';

type AssistantCompanionPanelProps = {
    compact?: boolean;
    open: boolean;
    onToggle: () => void;
    warnings: string[];
    currentLock: AssistantObjectLock | null;
    citations: AssistantCitation[];
    actionPreview: AssistantActionPreview | null;
    runtimeEvents: AssistantToolEvent[];
    renderLockBanner: (compact?: boolean) => React.ReactNode;
    renderCitations: (citations?: AssistantCitation[] | null, compact?: boolean) => React.ReactNode;
    renderActionPreview: (preview: AssistantActionPreview, compact?: boolean) => React.ReactNode;
};

export const AssistantCompanionPanel: React.FC<AssistantCompanionPanelProps> = ({
    compact = false,
    open,
    onToggle,
    warnings,
    currentLock,
    citations,
    actionPreview,
    runtimeEvents,
    renderLockBanner,
    renderCitations,
    renderActionPreview,
}) => {
    const hasContent = (
        warnings.length > 0 ||
        Boolean(currentLock) ||
        citations.length > 0 ||
        Boolean(actionPreview) ||
        runtimeEvents.length > 0
    );
    if (!hasContent) return null;

    const badges = [
        citations.length > 0 ? `${citations.length} 条依据` : '',
        actionPreview ? '操作预览' : '',
        warnings.length > 0 ? `${warnings.length} 条提示` : '',
        runtimeEvents.length > 0 ? '本轮进展' : '',
    ].filter(Boolean);

    return (
        <div className={cn(
            "border-t border-slate-100/80/70 bg-slate-50/70 px-3 py-2.5 dark:border-white/[0.05] dark:bg-white/[0.02]",
            compact && "px-2.5 py-2"
        )}>
            <button
                type="button"
                onClick={onToggle}
                className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-2xl border border-slate-100/50 bg-white/80 px-3 py-2 text-left shadow-soft-sm transition-colors hover:border-blue-200 hover:bg-white dark:border-white/[0.05] dark:bg-white/[0.02] dark:hover:border-blue-500/30",
                    compact && "rounded-xl px-2.5 py-2"
                )}
                aria-controls={compact ? 'module2-assistant-companion-compact' : 'module2-assistant-companion'}
            >
                <div className="min-w-0">
                    <div className="text-[11px] tabular-nums font-semibold text-slate-800 dark:text-slate-200">
                        辅助信息
                    </div>
                    <div className="mt-0.5 truncate text-[10px] tabular-nums text-slate-500 dark:text-slate-400">
                        {badges.length > 0 ? badges.join(' · ') : '查看当前回答的辅助信息'}
                    </div>
                </div>
                <ChevronRight
                    size={14}
                    className={cn(
                        "shrink-0 text-slate-400 transition-transform dark:text-slate-500",
                        open && "rotate-90 text-blue-500 dark:text-blue-400"
                    )}
                />
            </button>

            {open && (
                <div
                    id={compact ? 'module2-assistant-companion-compact' : 'module2-assistant-companion'}
                    className={cn("mt-2.5 space-y-2.5", compact && "mt-2 space-y-2")}
                >
                    {warnings.length > 0 && (
                        <div className="rounded-[16px] border border-amber-200 bg-amber-50/70 px-3 py-2 text-[11px] tabular-nums text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                            <div className="mb-1 flex items-center gap-1.5 text-[10px] tabular-nums font-semibold uppercase tracking-[0.08em]">
                                <AlertCircle size={12} />
                                当前提示
                            </div>
                            <div className="leading-relaxed">{warnings.join('；')}</div>
                        </div>
                    )}

                    {currentLock && (
                        <div>
                            <div className="mb-1 px-1 text-[10px] tabular-nums font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                                当前上下文
                            </div>
                            {renderLockBanner(compact)}
                        </div>
                    )}

                    {citations.length > 0 && (
                        <div>
                            <div className="mb-1 px-1 text-[10px] tabular-nums font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                                回答依据
                            </div>
                            {renderCitations(citations, compact)}
                        </div>
                    )}

                    {actionPreview && (
                        <div>
                            <div className="mb-1 px-1 text-[10px] tabular-nums font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                                操作预览
                            </div>
                            {renderActionPreview(actionPreview, compact)}
                        </div>
                    )}

                    {runtimeEvents.length > 0 && (
                        <div className="rounded-[16px] border border-slate-100/50 bg-white/75 px-3 py-2 text-[11px] tabular-nums text-slate-600 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-300">
                            <div className="mb-1 text-[10px] tabular-nums font-semibold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
                                本轮进展
                            </div>
                            <div className="space-y-1">
                                {runtimeEvents.slice(-3).map((event, index) => (
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
