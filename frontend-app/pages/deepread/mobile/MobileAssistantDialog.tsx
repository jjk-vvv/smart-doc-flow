import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUp, Bot, Sparkles, X } from 'lucide-react';

import assistantBotIcon from '../../../assets/文心智能体-copy.png';
import { cn } from '../../../lib/utils';
import { parseErrorMessage } from '../../../shared/api/client';
import {
  requestAssistant1ChatStream,
  requestExtractionSummary,
  resolveExtractBase,
} from '../../../shared/api/extraction';
import type { ExtractionDocument, ExtractionEntity, TraceHit } from '../../../shared/state/extractionDocuments';
import { AssistantActionPreviewCard } from '../assistant/AssistantActionPreviewCard';
import { AssistantCitationList } from '../assistant/AssistantCitationList';
import { AssistantComposerStatus } from '../assistant/AssistantComposerStatus';
import { AssistantCompanionPanel } from '../assistant/AssistantCompanionPanel';
import { buildAssistantExtraContext } from '../assistant/contextBuilder';
import { isRenderableAssistantDialogMessage } from '../assistant/helpers';
import { AssistantLockBanner } from '../assistant/AssistantLockBanner';
import { AssistantMessageBubble } from '../assistant/AssistantMessageBubble';
import {
  GENERIC_ASSISTANT_SESSION_KEY,
  persistAssistantSessionForFile,
  readAssistantSessionMap,
} from '../assistant/sessionStore';
import type {
  AssistantActionPreview,
  AssistantCitation,
  AssistantDialogMessage,
  AssistantObjectLock,
  AssistantToolEvent,
} from '../assistant/types';
import { useAssistantStream } from '../assistant/useAssistantStream';

type MobileAssistantDialogProps = {
  open: boolean;
  activeDoc: ExtractionDocument | null;
  activeDocIndex: number;
  documents: ExtractionDocument[];
  traceHits: TraceHit[];
  preferredBase: string;
  onPreferredBaseChange: (nextBase: string) => void;
  onClose: () => void;
  onSelectCitation?: (citation: AssistantCitation) => void;
};

type AssistantFieldItem = {
  key: string;
  label: string;
  valueText: string;
  confidence: number;
  refId?: string | null;
  pageNumber?: number | null;
};

const toPageNumber = (bbox: unknown): number | null => {
  if (!Array.isArray(bbox) || bbox.length < 1) return null;
  const value = Number(bbox[0]);
  if (!Number.isFinite(value) || value < 1) return null;
  return Math.round(value);
};

const toFieldItems = (document: ExtractionDocument | null): AssistantFieldItem[] => {
  if (!document) return [];
  return Object.entries(document.result || {})
    .map(([fieldName, entity]) => {
      const normalizedEntity = entity as ExtractionEntity;
      const valueText = String(normalizedEntity?.value ?? '').trim();
      const confidence = Number(normalizedEntity?.confidence ?? 0);
      return {
        key: fieldName,
        label: fieldName,
        valueText,
        confidence: Number.isFinite(confidence) ? confidence : 0,
        refId: normalizedEntity?.source_ref_id ?? null,
        pageNumber: toPageNumber(normalizedEntity?.bbox),
      };
    })
    .filter((item) => item.valueText.length > 0);
};

export const MobileAssistantDialog: React.FC<MobileAssistantDialogProps> = ({
  open,
  activeDoc,
  activeDocIndex,
  documents,
  traceHits,
  preferredBase,
  onPreferredBaseChange,
  onClose,
  onSelectCitation,
}) => {
  const [assistantSummaryLoading, setAssistantSummaryLoading] = useState(false);
  const [assistantSummaryText, setAssistantSummaryText] = useState('');
  const [assistantInput, setAssistantInput] = useState('');
  const [assistantDialog, setAssistantDialog] = useState<AssistantDialogMessage[]>([]);
  const [assistantQueryLoading, setAssistantQueryLoading] = useState(false);
  const [assistantWarnings, setAssistantWarnings] = useState<string[]>([]);
  const [assistantAnswer, setAssistantAnswer] = useState('');
  const [assistantMessage, setAssistantMessage] = useState('');
  const [assistantSessionId, setAssistantSessionId] = useState('');
  const [assistantCurrentLock, setAssistantCurrentLock] = useState<AssistantObjectLock | null>(null);
  const [assistantCompanionOpen, setAssistantCompanionOpen] = useState(false);
  const [assistantCompanionCitations, setAssistantCompanionCitations] = useState<AssistantCitation[]>([]);
  const [assistantCompanionActionPreview, setAssistantCompanionActionPreview] =
    useState<AssistantActionPreview | null>(null);
  const [assistantRuntimeEvents, setAssistantRuntimeEvents] = useState<AssistantToolEvent[]>([]);

  const assistantAbortRef = useRef<AbortController | null>(null);
  const assistantDialogRef = useRef<HTMLDivElement | null>(null);
  const assistantInputRef = useRef<HTMLTextAreaElement | null>(null);
  const extractionJobApiBaseRef = useRef(preferredBase);

  useEffect(() => {
    extractionJobApiBaseRef.current = preferredBase;
  }, [preferredBase]);

  const activeAssistantSessionKey = String(activeDoc?.file_hash || '').trim() || GENERIC_ASSISTANT_SESSION_KEY;
  const fieldItems = useMemo(() => toFieldItems(activeDoc), [activeDoc]);
  const hasActiveDoc = Boolean(activeDoc);
  const assistantUnavailableMessage = '请先上传并解析文档后再使用文档助手。';

  useEffect(() => {
    assistantAbortRef.current?.abort();
    assistantAbortRef.current = null;
    setAssistantInput('');
    setAssistantAnswer('');
    setAssistantWarnings([]);
    setAssistantDialog([]);
    setAssistantQueryLoading(false);
    setAssistantCompanionOpen(false);
    setAssistantCompanionCitations([]);
    setAssistantCompanionActionPreview(null);
    setAssistantRuntimeEvents([]);
    setAssistantCurrentLock(null);
    setAssistantMessage('');
    const storedSessionId = String(readAssistantSessionMap()[activeAssistantSessionKey] || '').trim();
    setAssistantSessionId(storedSessionId);
  }, [activeAssistantSessionKey]);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      if (!activeDoc) {
        setAssistantSummaryText('');
        setAssistantSummaryLoading(false);
        return;
      }

      setAssistantSummaryLoading(true);
      try {
        const result = await requestExtractionSummary(
          {
            file_name: activeDoc.file_name,
            result: activeDoc.result,
            diagnostics: activeDoc.diagnostics ?? {},
            errors: activeDoc.errors ?? [],
            soft_warnings: activeDoc.soft_warnings ?? [],
            trace_hits: activeDoc.trace_hits ?? [],
            max_chars: 520,
          },
          extractionJobApiBaseRef.current || resolveExtractBase(preferredBase),
        );
        if (cancelled) return;
        if (result.usedBase) {
          extractionJobApiBaseRef.current = result.usedBase;
          onPreferredBaseChange(result.usedBase);
        }
        if (!result.response.ok) {
          throw new Error(await parseErrorMessage(result.response));
        }
        const payload = (await result.response.json()) as { summary?: string };
        if (cancelled) return;
        setAssistantSummaryText(String(payload.summary || '').trim());
      } catch (error) {
        if (cancelled) return;
        const fallback = String(activeDoc.errors?.[0] || '').trim();
        setAssistantSummaryText(
          fallback || (error instanceof Error ? error.message : '暂时无法生成文档摘要'),
        );
      } finally {
        if (!cancelled) {
          setAssistantSummaryLoading(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [activeDoc, onPreferredBaseChange, preferredBase]);

  const assistantExtraContext = useMemo(
    () =>
      buildAssistantExtraContext({
        activeDoc,
        activeDocIndex,
        documents,
        fieldItems,
        traceHits,
        activeSummaryText: assistantSummaryText,
        smartUnitTab: 'assistant',
        currentObjectLock: assistantCurrentLock,
      }),
    [
      activeDoc,
      activeDocIndex,
      assistantCurrentLock,
      assistantSummaryText,
      documents,
      fieldItems,
      traceHits,
    ],
  );

  const updateAssistantDialogMessage = (
    messageId: string,
    updater: (current: AssistantDialogMessage) => AssistantDialogMessage,
  ) => {
    const normalizedId = String(messageId || '').trim();
    if (!normalizedId) return;
    setAssistantDialog((current) =>
      current.map((item) => (item.id === normalizedId ? updater(item) : item)),
    );
  };

  const resetAssistantCompanionState = (keepLock = false) => {
    setAssistantCompanionOpen(false);
    setAssistantCompanionCitations([]);
    setAssistantCompanionActionPreview(null);
    setAssistantRuntimeEvents([]);
    if (!keepLock) {
      setAssistantCurrentLock(null);
    }
  };

  const syncAssistantEvidence = (
    citations: AssistantCitation[],
    nextLock?: AssistantObjectLock | null,
  ) => {
    setAssistantCompanionCitations(Array.isArray(citations) ? citations : []);
    if (nextLock !== undefined) {
      setAssistantCurrentLock(nextLock ?? null);
    }
  };

  const fetchExtractWithFallback = async (
    path: string,
    init: RequestInit,
    candidateBase: string,
  ): Promise<{ response: Response; usedBase?: string }> => {
    if (path === '/extract/assistant1/chat/stream') {
      const payload =
        typeof init.body === 'string'
          ? (JSON.parse(init.body) as Record<string, unknown>)
          : {};
      const result = await requestAssistant1ChatStream(
        payload,
        init.signal ?? undefined,
        candidateBase,
      );
      if (result.usedBase) {
        extractionJobApiBaseRef.current = result.usedBase;
        onPreferredBaseChange(result.usedBase);
      }
      return { response: result.response, usedBase: result.usedBase };
    }

    const response = await fetch(path, {
      credentials: init.credentials ?? 'include',
      ...init,
    });
    return { response, usedBase: candidateBase };
  };

  const renderableAssistantDialog = useMemo(
    () => assistantDialog.filter((message) => isRenderableAssistantDialogMessage(message)),
    [assistantDialog],
  );

  const latestRenderableAssistantMessageId = useMemo(() => {
    for (let index = renderableAssistantDialog.length - 1; index >= 0; index -= 1) {
      const current = renderableAssistantDialog[index];
      if (current.role === 'assistant' && current.messageType === 'assistant_text') {
        return current.id;
      }
    }
    return '';
  }, [renderableAssistantDialog]);

  const latestStreamingAssistantMessage = useMemo(() => {
    for (let index = assistantDialog.length - 1; index >= 0; index -= 1) {
      const current = assistantDialog[index];
      if (current.role === 'assistant' && current.status === 'streaming') {
        return current;
      }
    }
    return null;
  }, [assistantDialog]);

  useEffect(() => {
    if (!open) return;
    const panel = assistantDialogRef.current;
    if (!panel) return;
    panel.scrollTo({ top: panel.scrollHeight, behavior: 'smooth' });
  }, [assistantDialog, assistantQueryLoading, open]);

  const { runAssistantInstruction } = useAssistantStream({
    assistantQueryLoading,
    assistantInput,
    assistantDialog,
    assistantSessionId,
    activeAssistantSessionKey,
    activeDocFileHash: String(activeDoc?.file_hash || '').trim(),
    assistantExtraContext,
    extractionJobApiBaseRef,
    assistantAbortRef,
    fetchExtractWithFallback,
    resolveExtractBase: () => resolveExtractBase(extractionJobApiBaseRef.current || preferredBase),
    readAssistantSessionMap,
    persistAssistantSessionForFile,
    resetAssistantCompanionState,
    updateAssistantDialogMessage,
    syncAssistantEvidence,
    setAssistantDialog,
    setAssistantQueryLoading,
    setAssistantWarnings,
    setAssistantAnswer,
    setAssistantInput,
    setAssistantMessage,
    setAssistantSessionId,
    setAssistantCompanionCitations,
    setAssistantCompanionActionPreview,
    setAssistantCompanionOpen,
    setAssistantRuntimeEvents,
  });

  const renderAssistantLockBanner = (compact = false) => (
    <AssistantLockBanner lock={assistantCurrentLock} compact={compact} />
  );

  const renderAssistantCitations = (
    citations?: AssistantCitation[] | null,
    compact = false,
  ) => (
    <AssistantCitationList
      citations={citations}
      compact={compact}
      onSelectCitation={(citation) => {
        onSelectCitation?.(citation);
      }}
    />
  );

  const renderAssistantActionPreview = (
    preview?: AssistantActionPreview | null,
    compact = false,
  ) => (
    <AssistantActionPreviewCard preview={preview} compact={compact} />
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[80]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.button
            type="button"
            aria-label="关闭智能助手"
            className="absolute inset-0 bg-slate-950/55 backdrop-blur-sm"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />

          <motion.div
            initial={{ y: '8%', opacity: 0.94 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: '8%', opacity: 0.94 }}
            transition={{ type: 'spring', stiffness: 260, damping: 28 }}
            className="absolute inset-x-0 bottom-0 top-[max(0.75rem,env(safe-area-inset-top))] flex flex-col overflow-hidden rounded-t-[30px] bg-[#F6F8FB] shadow-2xl dark:bg-[#0B1120]"
          >
            <div className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/92 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur-xl dark:border-white/[0.05] dark:bg-[#0B1120]/92">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-2">
                  <img
                    src={assistantBotIcon}
                    alt="Bot"
                    className="h-5 w-5 shrink-0 translate-y-[2px] object-contain"
                  />
                  <div className="min-w-0">
                    <h3 className="truncate text-[18px] font-semibold leading-tight text-slate-900 dark:text-white">
                      智能助手
                    </h3>
                    <p className="mt-0.5 truncate text-[13px] text-slate-500 dark:text-slate-400">
                      {activeDoc?.file_name || '当前无解析文档'}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600 transition hover:bg-slate-200 dark:bg-white/[0.05] dark:text-slate-300 dark:hover:bg-white/[0.08]"
                  aria-label="关闭智能助手"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-hidden">
              <div className="flex h-full min-h-0 flex-col">
                {hasActiveDoc && (assistantSummaryLoading || assistantSummaryText) && (
                  <div className="px-4 pt-4">
                    <div className="rounded-[22px] border border-slate-200/80 bg-white px-4 py-3 shadow-[0_4px_18px_rgba(15,23,42,0.04)] dark:border-white/[0.06] dark:bg-white/[0.03]">
                      <div className="mb-1.5 flex items-center gap-2 text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                        <Sparkles size={14} className="text-cyan-500" />
                        当前文档摘要
                      </div>
                      <p className="text-[13px] leading-6 text-slate-600 dark:text-slate-300">
                        {assistantSummaryLoading
                          ? '正在整理当前文档摘要...'
                          : assistantSummaryText}
                      </p>
                    </div>
                  </div>
                )}

                <div
                  ref={assistantDialogRef}
                  data-testid="mobile-module2-assistant-dialog"
                  className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
                >
                  {!hasActiveDoc ? (
                    <div className="flex h-full flex-col items-center justify-center px-4 pb-10 text-center">
                      <div className="mb-4">
                        <Bot size={48} className="text-[#D97757] dark:text-[#E2886A]" strokeWidth={1.5} />
                      </div>
                      <h4 className="text-[18px] font-semibold text-slate-800 dark:text-slate-100">
                        暂无可用文档
                      </h4>
                      <p className="mt-2 max-w-[280px] text-[13px] leading-6 text-slate-500 dark:text-slate-400">
                        {assistantUnavailableMessage}
                      </p>
                    </div>
                  ) : renderableAssistantDialog.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center px-4 pb-10 text-center">
                      <div className="mb-4">
                        <Sparkles size={48} className="text-[#D97757] dark:text-[#E2886A]" strokeWidth={1.5} />
                      </div>
                      <h4 className="text-[18px] font-semibold text-slate-800 dark:text-slate-100">
                        你好，我是文档助手
                      </h4>
                      <p className="mt-2 max-w-[280px] text-[13px] leading-6 text-slate-500 dark:text-slate-400">
                        你可以让我总结文件、解释字段，或快速定位关键信息。
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-5 pb-3">
                      {renderableAssistantDialog.map((message) => (
                        <AssistantMessageBubble
                          key={message.id}
                          message={message}
                          isLatestAnswer={message.id === latestRenderableAssistantMessageId}
                        />
                      ))}
                    </div>
                  )}
                </div>

                {hasActiveDoc && (
                  <div className="px-4">
                    <AssistantCompanionPanel
                      compact
                      open={assistantCompanionOpen}
                      onToggle={() => setAssistantCompanionOpen((current) => !current)}
                      warnings={assistantWarnings}
                      currentLock={assistantCurrentLock}
                      citations={assistantCompanionCitations}
                      actionPreview={assistantCompanionActionPreview}
                      runtimeEvents={assistantRuntimeEvents}
                      renderLockBanner={renderAssistantLockBanner}
                      renderCitations={renderAssistantCitations}
                      renderActionPreview={renderAssistantActionPreview}
                    />
                  </div>
                )}

                <div className="px-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] pt-2">
                  <div className="rounded-[24px] border border-transparent bg-white p-2.5 shadow-[0_4px_18px_rgba(15,23,42,0.06)] transition-all focus-within:shadow-[0_8px_24px_rgba(15,23,42,0.12)] focus-within:ring-1 focus-within:ring-slate-200 dark:border-white/[0.05] dark:bg-[#1A1D24] dark:shadow-none dark:focus-within:ring-white/[0.1]">
                    <AssistantComposerStatus
                      isLoading={assistantQueryLoading}
                      streamingMessage={latestStreamingAssistantMessage}
                    />
                    <div className="flex items-end gap-2">
                      <textarea
                        ref={assistantInputRef}
                        value={assistantInput}
                        onChange={(event) => setAssistantInput(event.target.value)}
                        disabled={!hasActiveDoc}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' && !event.shiftKey) {
                            event.preventDefault();
                            void runAssistantInstruction();
                          }
                        }}
                        placeholder={hasActiveDoc ? "输入任务指令或提问..." : "暂无可用文档"}
                        className={cn(
                          'max-h-[140px] min-h-[36px] flex-1 resize-none bg-transparent px-1.5 py-[6px] text-[15px] leading-6 outline-none',
                          hasActiveDoc
                            ? 'text-slate-800 placeholder:text-slate-400 dark:text-slate-100'
                            : 'cursor-not-allowed text-slate-400 placeholder:text-slate-400 dark:text-slate-500',
                        )}
                      />
                      <button
                        type="button"
                        onClick={() => void runAssistantInstruction()}
                        disabled={!hasActiveDoc || (!assistantQueryLoading && !assistantInput.trim())}
                        className={cn(
                          'flex h-[36px] w-[36px] shrink-0 items-center justify-center rounded-full transition-colors',
                          !hasActiveDoc || (!assistantQueryLoading && !assistantInput.trim())
                            ? 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-white/[0.05] dark:text-slate-500'
                            : assistantQueryLoading
                              ? 'bg-slate-900 text-white hover:bg-black dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200'
                              : 'bg-slate-900 text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200',
                        )}
                        title={assistantQueryLoading ? '停止本次回答' : '发送'}
                        aria-label={assistantQueryLoading ? '停止本次回答' : '发送'}
                      >
                        {assistantQueryLoading ? <X size={16} /> : <ArrowUp size={18} strokeWidth={2.5} />}
                      </button>
                    </div>
                    {assistantMessage && (
                      <p className="mt-2 px-1.5 text-[11px] leading-5 text-red-500 dark:text-red-400">
                        {assistantMessage}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
