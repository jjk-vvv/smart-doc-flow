import type {
    Assistant1HistoryMessage,
    AssistantActionPreview,
    AssistantCitation,
    AssistantCompanionState,
    AssistantDialogMessage,
    AssistantObjectLock,
    AssistantSessionMessagePayload,
    AssistantToolEvent,
} from './types';
import { EMPTY_ASSISTANT_COMPANION_STATE } from './types';

const isInternalAssistantWarning = (warningRaw: unknown): boolean => {
    const warning = String(warningRaw || '').trim();
    if (!warning) return false;
    return (
        warning.startsWith('assistant_provider_fallback:') ||
        warning.startsWith('assistant_context_fallback:')
    );
};

const WARNING_MESSAGE_MAP: Array<[string, string]> = [
    [
        'auto_ingest_completed_but_no_units_built',
        '系统已自动补做文档索引，但暂时还没有形成稳定的可检索片段，我先基于当前可见内容继续回答。',
    ],
    [
        'initial_unit_type_filter_returned_no_matches; broadened_to_all_unit_types',
        '第一次检索没有命中最相关内容，我已自动扩大检索范围继续查找。',
    ],
    [
        'content_list unavailable; fell back to markdown-only content items',
        '结构化内容清单暂不可用，本次回答主要基于正文内容。',
    ],
    [
        'assistant payload artifact is missing or unreadable',
        '文档的部分结构化解析产物暂不可用，本次回答可能更依赖正文内容。',
    ],
    [
        'assistant payload artifact not found',
        '文档的部分结构化解析产物暂不可用，本次回答可能更依赖正文内容。',
    ],
    [
        'mineru markdown artifact is missing or unreadable',
        '文档正文解析产物暂不可用，本次回答可能不够完整。',
    ],
    [
        'mineru markdown path missing',
        '文档正文解析产物暂不可用，本次回答可能不够完整。',
    ],
    [
        'stream_error:',
        '生成过程里出现了一次非致命波动，我已经尽量整理当前可用结果。',
    ],
    [
        'broadened_retry_failed:',
        '扩大检索范围时遇到了一些问题，我先基于当前已命中的内容继续回答。',
    ],
    [
        'retrieval_stats_unavailable:',
        '本次检索统计信息暂不可用，但不影响继续回答。',
    ],
];

export const normalizeAssistantWarningMessage = (warningRaw: unknown): string => {
    const warning = String(warningRaw || '').trim();
    if (!warning || isInternalAssistantWarning(warning)) return '';
    const lowered = warning.toLowerCase();
    for (const [marker, replacement] of WARNING_MESSAGE_MAP) {
        if (warning.includes(marker) || lowered.includes(marker)) {
            return replacement;
        }
    }
    if (/[\u4e00-\u9fff]/.test(warning)) {
        return warning;
    }
    if (warning.includes('_') || warning.includes(';') || warning.includes(':')) {
        return '处理中出现了一条非致命提示，我已继续完成当前回答。';
    }
    return warning;
};

export const filterAssistantWarnings = (warningsRaw: unknown): string[] => {
    if (!Array.isArray(warningsRaw)) return [];
    const next: string[] = [];
    const seen = new Set<string>();
    warningsRaw.forEach((item) => {
        const normalized = normalizeAssistantWarningMessage(item);
        if (!normalized || seen.has(normalized)) return;
        seen.add(normalized);
        next.push(normalized);
    });
    return next;
};

const mergeShortAssistantBridgeParagraphs = (text: string): string => {
    const paragraphs = String(text || '')
        .split(/\n\s*\n/)
        .map((part) => part.trim())
        .filter(Boolean);
    if (paragraphs.length < 2) return paragraphs.join('\n\n');

    const bridgeParagraphRe =
        /^(先看|先说|先把|再看|再说|再把|最后|最后再|整体看|整体来说|单看|当前这条记录|整份文档|关于文档内证据|关于通用经验|关于是否需要联网查询)[^。！？?]{0,20}[。！？?]?$/;

    const merged: string[] = [];
    for (let index = 0; index < paragraphs.length; index += 1) {
        const current = paragraphs[index];
        const normalized = current.replace(/\s+/g, '');
        const next = paragraphs[index + 1];
        if (next && normalized.length <= 26 && bridgeParagraphRe.test(normalized)) {
            const prefix = /[。！？?]$/.test(current) ? current : `${current}。`;
            merged.push(`${prefix}${next}`);
            index += 1;
            continue;
        }
        merged.push(current);
    }
    return merged.join('\n\n');
};

export const normalizeAssistantDisplayText = (textRaw: unknown): string => (
    mergeShortAssistantBridgeParagraphs(
        String(textRaw || '')
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .replace(/\u200b/g, '')
            .replace(/\u0000/g, '')
            .replace(/\ufeff/g, '')
            .replace(/[\u00a0\u3000\u2002\u2003\u2009\u202f\u205f]/g, ' ')
            .replace(/[ \t]+\n/g, '\n')
            .replace(/\n[ \t]+/g, '\n')
            .split('\n')
            .map((line) => line.trim())
            .join('\n')
            .replace(/[ \t]{2,}/g, ' ')
            .replace(/\n{3,}/g, '\n\n')
            .replace(/\n\n(?=[-*•\d]\s)/g, '\n')
            .trim()
    )
);

export const mergeAssistantFinalAnswer = (currentContent: string, finalContent: string): string => {
    const current = normalizeAssistantDisplayText(currentContent);
    const final = normalizeAssistantDisplayText(finalContent);
    if (!final) return current;
    const currentTrimmed = current.trimEnd();
    if (!currentTrimmed) return final;
    if (final === currentTrimmed) return currentTrimmed;
    if (final.startsWith(currentTrimmed)) {
        return `${currentTrimmed}${final.slice(currentTrimmed.length)}`;
    }
    const maxOverlap = Math.min(currentTrimmed.length, final.length, 120);
    for (let size = maxOverlap; size > 0; size -= 1) {
        if (currentTrimmed.endsWith(final.slice(0, size))) {
            return `${currentTrimmed}${final.slice(size)}`;
        }
    }
    return final;
};

export const humanizeAssistantLockType = (lockTypeRaw: string): string => {
    const lockType = String(lockTypeRaw || '').trim().toLowerCase();
    if (!lockType) return '未锁定';
    if (lockType === 'table_row') return '表格行';
    if (lockType === 'table_region') return '表格区域';
    if (lockType === 'figure') return '图像 / 图表';
    if (lockType === 'ocr_fact_group') return 'OCR 事实组';
    if (lockType === 'field') return '字段';
    return lockTypeRaw || '未锁定';
};

export const humanizeAssistantLockQuality = (lockQualityRaw: string): string => {
    const lockQuality = String(lockQualityRaw || '').trim().toLowerCase();
    if (!lockQuality) return '';
    if (lockQuality === 'stable_lock') return '稳定锁定';
    if (lockQuality === 'weak_lock') return '弱锁定';
    if (lockQuality === 'no_lock') return '尚未形成稳定锁定';
    return lockQualityRaw;
};

export const humanizeAssistantFocusScope = (focusScopeRaw: string): string => {
    const focusScope = String(focusScopeRaw || '').trim().toLowerCase();
    if (!focusScope) return '';
    if (focusScope === 'table_row') return '表格行绑定';
    if (focusScope === 'ocr_fact_group') return 'OCR 事实组绑定';
    if (focusScope === 'unresolved_table_row') return '未稳定表格行';
    if (focusScope === 'context') return '普通上下文';
    return focusScopeRaw;
};

export const humanizeAssistantActionType = (actionTypeRaw: string): string => {
    const actionType = String(actionTypeRaw || '').trim().toLowerCase();
    if (!actionType) return '';
    if (actionType === 'sql_preview') return 'SQL 预览';
    if (actionType === 'save_preview') return '入库预览';
    return actionTypeRaw;
};

export const humanizeAssistantOperationType = (operationTypeRaw: string): string => {
    const operationType = String(operationTypeRaw || '').trim().toLowerCase();
    if (!operationType) return '';
    if (operationType === 'select') return '查询';
    if (operationType === 'insert') return '写入';
    if (operationType === 'update') return '更新';
    if (operationType === 'delete') return '删除';
    return operationTypeRaw;
};

export const humanizeAssistantToolEvent = (event: {
    tool_name?: unknown;
    status?: unknown;
    message?: unknown;
    detail?: unknown;
}): string => {
    const toolName = String(event.tool_name || '').trim().toLowerCase();
    const status = String(event.status || '').trim().toLowerCase();

    if (toolName === 'search_knowledge_base') return '正在检索当前文档';
    if (toolName === 'search_knowledge_base_grouped') return '正在按时间和版本整理内容';
    if (toolName === 'web_search_tavily') return '正在补充外部资料';
    if (toolName === 'inspect_database_schema') return '正在检查数据库结构';
    if (toolName === 'design_schema_draft') return '正在整理表结构草案';
    if (toolName === 'draft_sql_from_nl') return '正在生成 SQL 草案';
    if (toolName === 'execute_sql_with_audit') {
        return status === 'error' ? 'SQL 校验或执行失败' : '正在校验并执行 SQL';
    }
    if (toolName === 'ingest_document') return '正在准备文档知识底座';

    const message = String(event.message || '').trim();
    if (message) return message;
    if (status === 'fallback') return '正在切换到保守回答模式';
    return '正在处理你的问题';
};

export const summarizeAssistantRowPreview = (candidate: Record<string, unknown>): string => {
    const rowPreview = Array.isArray(candidate.row_preview) ? candidate.row_preview as Array<unknown> : [];
    return rowPreview
        .flatMap((row) => {
            if (!row || typeof row !== 'object') return [];
            const cells = Array.isArray((row as Record<string, unknown>).cells)
                ? (row as Record<string, unknown>).cells as Array<unknown>
                : [];
            return cells
                .filter((cell) => cell && typeof cell === 'object')
                .slice(0, 4)
                .map((cell) => {
                    const item = cell as Record<string, unknown>;
                    const header = String(item.header || item.label || '列').trim();
                    const text = String(item.text || item.value || '').trim();
                    return text ? `${header}=${text}` : '';
                })
                .filter(Boolean);
        })
        .slice(0, 4)
        .join(' | ');
};

export const summarizeAssistantFactPreview = (item: Record<string, unknown>): string => {
    const kind = String(item.kind || '').trim().toLowerCase();
    if (kind === 'field') {
        const label = String(item.label || '字段').trim();
        const value = String(item.value || '').trim();
        const page = Number(item.page || 0);
        const bits = [
            value ? `${label}: ${value}` : label,
            page > 0 ? `第 ${page} 页` : '',
        ].filter(Boolean);
        return bits.join(' · ');
    }
    if (kind === 'table') {
        const tableId = String(item.table_id || '表格').trim();
        const headers = Array.isArray(item.headers)
            ? (item.headers as Array<unknown>).map((header) => String(header || '').trim()).filter(Boolean)
            : [];
        const rowPreview = Array.isArray(item.row_preview) ? item.row_preview as Array<unknown> : [];
        const firstRow = rowPreview[0] && typeof rowPreview[0] === 'object'
            ? rowPreview[0] as Record<string, unknown>
            : null;
        const cells = Array.isArray(firstRow?.cells) ? firstRow.cells as Array<unknown> : [];
        const previewText = cells
            .filter((cell) => cell && typeof cell === 'object')
            .slice(0, 3)
            .map((cell) => {
                const current = cell as Record<string, unknown>;
                const header = String(current.header || '列').trim();
                const text = String(current.text || '').trim();
                return text ? `${header}=${text}` : '';
            })
            .filter(Boolean)
            .join(' | ');
        const bits = [
            tableId,
            headers.length > 0 ? `表头: ${headers.slice(0, 3).join('、')}` : '',
            previewText,
        ].filter(Boolean);
        return bits.join(' · ');
    }
    return String(item.label || item.kind || '').trim();
};

export const isRenderableAssistantDialogMessage = (msg: AssistantDialogMessage): boolean => {
    const messageType = String(msg.messageType || '').trim();
    return messageType !== 'tool_status' && messageType !== 'action_preview' && messageType !== 'system_notice';
};

export const toAssistantPayloadRecord = (value: unknown): Record<string, unknown> =>
    value && typeof value === 'object' ? value as Record<string, unknown> : {};

export const toAssistantCitations = (value: unknown): AssistantCitation[] =>
    Array.isArray(value) ? value as AssistantCitation[] : [];

export const toAssistantActionPreview = (value: unknown): AssistantActionPreview | null =>
    value && typeof value === 'object' && Object.keys(value as Record<string, unknown>).length > 0
        ? value as AssistantActionPreview
        : null;

export const toAssistantToolEvents = (value: unknown): AssistantToolEvent[] =>
    Array.isArray(value) ? value as AssistantToolEvent[] : [];

export const toAssistantObjectLock = (value: unknown): AssistantObjectLock | null =>
    value && typeof value === 'object' && Object.keys(value as Record<string, unknown>).length > 0
        ? value as AssistantObjectLock
        : null;

export const toAssistantCompanionState = (payloadRaw: unknown): AssistantCompanionState => {
    const payload = toAssistantPayloadRecord(payloadRaw);
    return {
        citations: toAssistantCitations(payload.citations),
        actionPreview: toAssistantActionPreview(payload.action_preview),
        toolEvents: toAssistantToolEvents(payload.tool_events),
    };
};

export const findLatestAssistantPayload = (messages: AssistantSessionMessagePayload[]): Record<string, unknown> => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
        const current = messages[index];
        if (String(current.role || '').trim().toLowerCase() === 'assistant') {
            return toAssistantPayloadRecord(current.payload);
        }
    }
    return {};
};

export const toAssistantVisibleWarnings = (payloadRaw: unknown): string[] => {
    const payload = toAssistantPayloadRecord(payloadRaw);
    const userVisible = payload.user_visible_warnings;
    return filterAssistantWarnings(Array.isArray(userVisible) ? userVisible : payload.warnings);
};

export const buildAssistant1HistoryFromDialog = (messages: AssistantDialogMessage[]): Assistant1HistoryMessage[] =>
    messages
        .filter((item) => isRenderableAssistantDialogMessage(item))
        .map((item): Assistant1HistoryMessage => ({
            role: item.role === 'assistant' ? 'assistant' : 'user',
            content: normalizeAssistantDisplayText(item.content),
        }))
        .filter((item) => item.content)
        .slice(-10);

export { EMPTY_ASSISTANT_COMPANION_STATE };
