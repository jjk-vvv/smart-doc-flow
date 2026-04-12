import React from 'react';
import { Bot } from 'lucide-react';

import { cn } from '../../../lib/utils';
import type { AssistantDialogMessage } from './types';

type AssistantMessageBubbleProps = {
    message: AssistantDialogMessage;
    compact?: boolean;
    isLatestAnswer?: boolean;
};

export const AssistantMessageBubble: React.FC<AssistantMessageBubbleProps> = ({
    message,
    compact = false,
    isLatestAnswer = false,
}) => {
    const isAssistant = message.role === 'assistant';
    const detail = String(message.payload?.detail || '').trim();
    const toolName = String(message.payload?.tool_name || '').trim();
    const toolStatus = String(message.payload?.status || '').trim();
    const isToolStatus = message.messageType === 'tool_status';
    const contentText = String(message.content || '').trim();

    if (isAssistant && message.status === 'streaming' && !contentText) {
        return null;
    }

    return (
        <div
            className={cn(
                compact ? 'flex gap-2.5 max-w-[95%]' : 'flex gap-4 max-w-[85%]',
                isAssistant ? 'mr-auto' : 'ml-auto',
            )}
        >
            {isAssistant && (
                <div
                    className={cn(
                        compact
                            ? 'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-slate-200/50 bg-white/50 text-slate-600 shadow-sm dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-300'
                            : 'mt-0.5 flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[10px] border border-slate-200/50 bg-white/50 text-slate-600 shadow-sm dark:border-white/[0.05] dark:bg-[#1A1D24] dark:text-slate-300',
                    )}
                >
                    <Bot size={compact ? 12 : 16} strokeWidth={1.5} />
                </div>
            )}
            <div className="min-w-0 flex-1">
                <div
                    className={cn(
                        compact
                            ? 'text-[12px] tabular-nums leading-relaxed break-words whitespace-pre-wrap'
                            : 'text-[15px] leading-[1.65] break-words whitespace-pre-wrap',
                        isAssistant
                            ? isToolStatus
                                ? compact
                                    ? 'rounded-xl border border-slate-200/60 bg-slate-50/50 p-2.5 text-slate-600 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-300'
                                    : 'rounded-2xl border border-slate-200/60 bg-slate-50/50 p-4 text-slate-600 dark:border-white/[0.05] dark:bg-white/[0.02] dark:text-slate-300'
                                : compact
                                    ? 'py-0.5 text-slate-800 dark:text-slate-200'
                                    : 'py-1 text-slate-800 dark:text-slate-200'
                            : compact
                                ? 'rounded-[20px] bg-[#F3F4F6] px-3.5 py-2 text-slate-800 dark:bg-[#2A2D35] dark:text-slate-200'
                                : 'rounded-[24px] bg-[#F3F4F6] px-5 py-3 text-slate-800 dark:bg-[#2A2D35] dark:text-slate-200',
                    )}
                >
                    <div data-testid={isLatestAnswer ? 'module2-assistant-answer' : undefined}>
                        {isToolStatus && (
                            <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] tabular-nums font-medium text-slate-500 dark:text-slate-400">
                                <span className="uppercase tracking-wider">进展提示</span>
                                {toolName && (
                                    <span className="rounded-md bg-white px-1.5 py-0.5 text-slate-600 ring-1 ring-inset ring-slate-200/80 shadow-sm dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.1]">
                                        {toolName}
                                    </span>
                                )}
                                {toolStatus && (
                                    <span className="rounded-md bg-white px-1.5 py-0.5 text-slate-600 ring-1 ring-inset ring-slate-200/80 shadow-sm dark:bg-white/[0.05] dark:text-slate-300 dark:ring-white/[0.1]">
                                        {toolStatus}
                                    </span>
                                )}
                            </div>
                        )}
                        {contentText ? (
                            <span>{contentText}</span>
                        ) : (
                            <span className="text-slate-400 dark:text-slate-500">正在思考...</span>
                        )}
                        {detail && isToolStatus && (
                            <div className="mt-2 text-[12px] leading-relaxed text-slate-500 dark:text-slate-400">
                                {detail}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
