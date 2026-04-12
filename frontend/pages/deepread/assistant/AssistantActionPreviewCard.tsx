import React from 'react';

import { cn } from '../../../lib/utils';
import {
    humanizeAssistantActionType,
    humanizeAssistantFocusScope,
    humanizeAssistantLockQuality,
    humanizeAssistantLockType,
    humanizeAssistantOperationType,
    summarizeAssistantFactPreview,
    summarizeAssistantRowPreview,
} from './helpers';
import type { AssistantActionPreview, AssistantObjectLock } from './types';

type AssistantActionPreviewCardProps = {
    preview?: AssistantActionPreview | null;
    compact?: boolean;
};

export const AssistantActionPreviewCard: React.FC<AssistantActionPreviewCardProps> = ({
    preview,
    compact = false,
}) => {
    if (!preview) return null;

    const payload = preview.payload && typeof preview.payload === 'object' ? preview.payload : {};
    const matchedFields = Array.isArray(payload.matched_fields)
        ? payload.matched_fields.map((item) => String(item || '').trim()).filter(Boolean)
        : [];
    const previewStatus = String(payload.preview_status || 'ready').trim().toLowerCase();
    const lockQuality = String(payload.lock_quality || '').trim();
    const focusScope = String(payload.focus_scope || '').trim();
    const focusReason = String(payload.focus_reason || '').trim();
    const clarificationQuestion = String(payload.clarification_question || '').trim();
    const operationType = String(payload.operation_type || '').trim();
    const targetTable = String(payload.target_table || '').trim();
    const tableStatus = String(payload.target_table_status || '').trim().toLowerCase();
    const sqlReady = Boolean(payload.sql_ready);
    const sqlPreviewText = String(payload.sql_preview_text || '').trim();
    const affectedScope = String(payload.affected_scope || '').trim();
    const missingRequirements = Array.isArray(payload.missing_requirements)
        ? payload.missing_requirements.map((item) => String(item || '').trim()).filter(Boolean)
        : [];
    const confirmationChecklist = Array.isArray(payload.confirmation_checklist)
        ? payload.confirmation_checklist.map((item) => String(item || '').trim()).filter(Boolean)
        : [];
    const evidenceBasis =
        payload.evidence_basis && typeof payload.evidence_basis === 'object'
            ? (payload.evidence_basis as Record<string, unknown>)
            : null;
    const identifierFields = Array.isArray(evidenceBasis?.identifier_fields)
        ? (evidenceBasis.identifier_fields.filter(
              (item) => item && typeof item === 'object',
          ) as Array<Record<string, unknown>>)
        : [];
    const factItems = Array.isArray(payload.fact_items)
        ? (payload.fact_items.filter(
              (item) => item && typeof item === 'object',
          ) as Array<Record<string, unknown>>)
        : [];
    const focusLock =
        payload.focus_lock && typeof payload.focus_lock === 'object'
            ? (payload.focus_lock as AssistantObjectLock)
            : null;
    const candidateRows = Array.isArray(payload.candidate_rows)
        ? (payload.candidate_rows.filter(
              (item) => item && typeof item === 'object',
          ) as Array<Record<string, unknown>>)
        : [];

    return (
        <div
            className={cn(
                'mt-2.5 rounded-2xl border border-amber-200/80 bg-amber-50/80 px-3.5 py-3 text-left dark:border-amber-900/70 dark:bg-amber-950/20',
                compact && 'mt-2 rounded-xl px-3 py-2.5',
            )}
        >
            <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:ring-amber-900/70">
                    动作预览
                </span>
                <span className="text-[10px] text-amber-700/90 dark:text-amber-200/80">
                    {preview.requires_confirmation ? '需要确认后执行' : '可直接执行'}
                </span>
            </div>

            <div className="mt-2 text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                {preview.title || '数据库动作预览'}
            </div>

            {preview.description && (
                <div className="mt-1 text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                    {preview.description}
                </div>
            )}

            <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-slate-600 dark:text-slate-300">
                {preview.action_type && (
                    <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                        类型：{humanizeAssistantActionType(preview.action_type)}
                    </span>
                )}
                {operationType && (
                    <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                        操作：{humanizeAssistantOperationType(operationType)}
                    </span>
                )}
                {preview.target && (
                    <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                        目标：{preview.target}
                    </span>
                )}
                <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                    状态：{previewStatus === 'blocked' ? '已阻塞' : '可继续确认'}
                </span>
                {lockQuality && (
                    <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                        锁定强度：{humanizeAssistantLockQuality(lockQuality)}
                    </span>
                )}
                {focusScope && (
                    <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                        绑定范围：{humanizeAssistantFocusScope(focusScope)}
                    </span>
                )}
                {matchedFields.length > 0 && (
                    <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                        字段：{matchedFields.slice(0, 4).join('、')}
                    </span>
                )}
                {targetTable && (
                    <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                        目标表：{targetTable}
                    </span>
                )}
                <span className="rounded-full bg-white px-2 py-0.5 ring-1 ring-inset ring-slate-200 dark:bg-white/[0.05] dark:ring-white/[0.05]">
                    SQL：{sqlReady ? '已生成预览' : '仍待补充'}
                </span>
            </div>

            {targetTable && (
                <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300">
                    目标表校验：
                    {tableStatus === 'whitelisted'
                        ? ` ${targetTable} 已在白名单内。`
                        : ` ${targetTable} 当前不在白名单内，正式执行前仍需补齐表级校验。`}
                </div>
            )}

            {focusLock && (
                <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300">
                    当前绑定对象：{humanizeAssistantLockType(String(focusLock.lock_type || ''))}
                    {focusLock.label ? ` / ${focusLock.label}` : ''}
                    {focusLock.page ? ` / 第 ${focusLock.page} 页` : ''}
                </div>
            )}

            {affectedScope && (
                <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300">
                    影响范围：{affectedScope}
                </div>
            )}

            {identifierFields.length > 0 && (
                <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300">
                    <div className="font-semibold text-slate-800 dark:text-slate-100">
                        当前用于定位记录的条件
                    </div>
                    <div className="mt-1 space-y-1">
                        {identifierFields.slice(0, 3).map((item, index) => {
                            const label = String(item.label || item.field || '字段').trim();
                            const value = String(item.value || '').trim();
                            const source = String(item.source || '').trim();

                            return (
                                <div key={`assistant-preview-id-${index}`}>
                                    {label}
                                    {value ? ` = ${value}` : ''}
                                    {source ? ` / ${source}` : ''}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {sqlPreviewText && (
                <div className="mt-2 rounded-xl border border-slate-200/80 bg-slate-950 px-3 py-2 text-[10px] leading-relaxed text-slate-100 dark:border-slate-700">
                    <div className="mb-1 font-semibold text-slate-200">SQL 预览</div>
                    <pre className="whitespace-pre-wrap break-words">{sqlPreviewText}</pre>
                </div>
            )}

            {missingRequirements.length > 0 && (
                <div className="mt-2 rounded-xl border border-dashed border-amber-300/80 bg-white/70 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-amber-500/60 dark:bg-white/[0.05] dark:text-slate-300">
                    还不能形成最终 SQL，主要还缺少：
                    <div className="mt-1 space-y-1">
                        {missingRequirements.slice(0, 4).map((item, index) => (
                            <div key={`assistant-preview-missing-${index}`}>- {item}</div>
                        ))}
                    </div>
                </div>
            )}

            {confirmationChecklist.length > 0 && (
                <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300">
                    <div className="font-semibold text-slate-800 dark:text-slate-100">确认清单</div>
                    <div className="mt-1 space-y-1">
                        {confirmationChecklist.slice(0, 4).map((item, index) => (
                            <div key={`assistant-preview-check-${index}`}>- {item}</div>
                        ))}
                    </div>
                </div>
            )}

            {previewStatus === 'blocked' && (
                <div className="mt-2 space-y-2">
                    <div className="rounded-xl border border-dashed border-amber-300/80 bg-white/70 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-amber-500/60 dark:bg-white/[0.05] dark:text-slate-300">
                        当前候选数：{candidateRows.length}。请先确认目标记录后，再继续生成可执行预览。
                        {focusReason ? ` 当前阻塞原因：${focusReason}。` : ''}
                        {clarificationQuestion ? ` ${clarificationQuestion}` : ''}
                    </div>

                    {candidateRows.length > 0 && (
                        <div className="space-y-1.5">
                            {candidateRows.slice(0, 3).map((candidate, index) => {
                                const rank = Number(candidate.rank || index + 1);
                                const tableId = String(candidate.table_id || '表格').trim();
                                const rowLabel = String(candidate.row_label || '').trim();
                                const matchedTerms = Array.isArray(candidate.matched_anchor_terms)
                                    ? candidate.matched_anchor_terms
                                          .map((item) => String(item || '').trim())
                                          .filter(Boolean)
                                    : [];
                                const nearTerms = Array.isArray(candidate.near_anchor_terms)
                                    ? candidate.near_anchor_terms
                                          .map((item) => String(item || '').trim())
                                          .filter(Boolean)
                                    : [];
                                const missingTerms = Array.isArray(candidate.missing_anchor_terms)
                                    ? candidate.missing_anchor_terms
                                          .map((item) => String(item || '').trim())
                                          .filter(Boolean)
                                    : [];
                                const previewText = summarizeAssistantRowPreview(candidate);

                                return (
                                    <div
                                        key={`assistant-preview-candidate-${rank}-${tableId}-${index}`}
                                        className="rounded-xl border border-white/80 bg-white/85 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300"
                                    >
                                        <div className="font-semibold text-slate-800 dark:text-slate-100">
                                            候选 {rank} / {tableId}
                                            {candidate.row_index
                                                ? ` / 表内第 ${candidate.row_index} 行`
                                                : ''}
                                            {candidate.page ? ` / 第 ${candidate.page} 页` : ''}
                                        </div>
                                        {rowLabel && <div className="mt-1">行标签：{rowLabel}</div>}
                                        {previewText && <div className="mt-1">行预览：{previewText}</div>}
                                        {matchedTerms.length > 0 && (
                                            <div className="mt-1">
                                                已命中锚点：{matchedTerms.join('、')}
                                            </div>
                                        )}
                                        {nearTerms.length > 0 && (
                                            <div className="mt-1">近似锚点：{nearTerms.join('、')}</div>
                                        )}
                                        {missingTerms.length > 0 && (
                                            <div className="mt-1 text-amber-700 dark:text-amber-300">
                                                缺失锚点：{missingTerms.join('、')}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            )}

            {focusScope === 'ocr_fact_group' && factItems.length > 0 && (
                <div className="mt-2 rounded-xl border border-white/80 bg-white/80 px-3 py-2 text-[10px] leading-relaxed text-slate-800 dark:border-white/[0.05] dark:bg-white/[0.05] dark:text-slate-300">
                    <div className="font-semibold text-slate-800 dark:text-slate-100">
                        当前基于 OCR 事实组生成预览
                    </div>
                    <div className="mt-1 space-y-1">
                        {factItems.slice(0, 4).map((item, index) => (
                            <div key={`assistant-preview-fact-${index}`}>
                                {summarizeAssistantFactPreview(item)}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
