import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, Compass, FileStack, RotateCcw, ArrowUp, Sparkles, X } from 'lucide-react';

import assistantOrb from '../../../assets/assistant-orb.mp4';
import assistantOrbPoster from '../../../assets/assistant-orb-poster.png';
import assistantOrbWebm from '../../../assets/assistant-orb.webm';
import GuideImage from '../../../assets/使用说明插图.png';
import QuestionImage from '../../../assets/问号插图.png';
import ContextImage from '../../../assets/上下文插图.png';
import { cn } from '../../../lib/utils';
import {
  requestPlatformAssistantCatalog,
  requestPlatformAssistantBootstrap,
  requestPlatformAssistantChatStream,
  type PlatformAssistantCatalogResponse,
  type PlatformAssistantBootstrapPage,
  type PlatformAssistantBootstrapResponse,
} from '../../../shared/api/platformAssistant';
import {
  buildAssistantRequestContext,
  readAssistantExtractionSnapshot,
  subscribeAssistantExtractionSnapshot,
  type ContextDocument,
} from '../lib/assistantContext';
import { useMobileOverlayPresence } from '../../../shared/hooks/useMobileOverlayPresence';
import {
  buildAssistantPageCatalog,
  buildUsageFallbackCard,
  findGuidedPrompt,
  getPagePromptGroups,
  guidedCardToText,
  hydrateAssistantPageConfig,
  normalizePlatformTab,
  type AssistantCardAction,
  type AssistantPageCatalog,
  type GuidedAnswerCard,
  type PlatformTabId,
} from '../lib/platformAssistant';

type AssistantMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  card?: GuidedAnswerCard;
};

type PlatformAssistantProps = {
  activeTab?: string;
  onNavigate?: (target: PlatformTabId) => void;
  launcherOffsetClassName?: string;
};

const DEFAULT_LAUNCHER_OFFSET =
  'bottom-[calc(var(--mobile-content-bottom)+18px)] left-[var(--mobile-page-x)] lg:bottom-[140px] lg:left-0';
const STREAM_DONE = '__done__';

const normalizeStreamChunk = (value: string): string =>
  value.replace(/\r/g, '').replace(/\u0000/g, '').replace(/\u200b/g, '');

const parseStreamLine = (line: string): string | null => {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith(':')) return null;
  if (trimmed.startsWith('0:')) {
    try {
      const parsed = JSON.parse(trimmed.slice(2)) as string;
      return parsed === '[DONE]' ? STREAM_DONE : normalizeStreamChunk(String(parsed || ''));
    } catch {
      return null;
    }
  }
  if (!trimmed.startsWith('data:')) return null;
  const payload = trimmed.slice(5).trim();
  if (!payload) return null;
  if (payload === '[DONE]') return STREAM_DONE;
  try {
    const parsed = JSON.parse(payload) as any;
    const content =
      parsed?.choices?.[0]?.delta?.content ??
      parsed?.delta?.content ??
      parsed?.content ??
      parsed?.text ??
      '';
    return normalizeStreamChunk(String(content || ''));
  } catch {
    return normalizeStreamChunk(payload);
  }
};

const ActionButtons = ({
  primaryAction,
  secondaryAction,
  onAction,
}: {
  primaryAction: AssistantCardAction;
  secondaryAction?: AssistantCardAction;
  onAction: (action: AssistantCardAction) => void;
}) => (
  <div className="flex flex-wrap gap-3 pt-1">
    <button
      type="button"
      onClick={() => onAction(primaryAction)}
      className="inline-flex items-center gap-1.5 rounded-[18px] bg-blue-50 px-5 py-2.5 text-[13px] font-medium text-blue-600 transition-colors hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-400 dark:hover:bg-blue-500/20"
    >
      <span>{primaryAction.label}</span>
      <ArrowRight size={15} />
    </button>
    {secondaryAction ? (
      <button
        type="button"
        onClick={() => onAction(secondaryAction)}
        className="rounded-[18px] border border-slate-200 bg-transparent px-5 py-2.5 text-[13px] font-medium text-slate-600 transition-colors hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5"
      >
        {secondaryAction.label}
      </button>
    ) : null}
  </div>
);

export function PlatformAssistant({
  activeTab,
  onNavigate,
  launcherOffsetClassName,
}: PlatformAssistantProps) {
  const normalizedTab = normalizePlatformTab(activeTab);
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCompactViewport, setIsCompactViewport] = useState(false);
  const externalMobileOverlayActive = useMobileOverlayPresence();
  const [documents, setDocuments] = useState<ContextDocument[]>(
    () => readAssistantExtractionSnapshot().documents,
  );
  const [remotePageConfig, setRemotePageConfig] = useState<PlatformAssistantBootstrapPage | null>(null);
  const [remotePageCatalog, setRemotePageCatalog] = useState<AssistantPageCatalog | null>(null);
  const requestAbortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messageSeqRef = useRef(0);
  const pageConfig = hydrateAssistantPageConfig(normalizedTab, remotePageConfig, remotePageCatalog);
  const promptGroups = getPagePromptGroups(normalizedTab, pageConfig);
  const visiblePrompts = [...promptGroups.primary, ...promptGroups.secondary].slice(0, 6);

  useEffect(() => {
    return subscribeAssistantExtractionSnapshot((snapshot) => {
      setDocuments(snapshot.documents);
    });
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;

    const mediaQuery = window.matchMedia('(max-width: 1023px)');
    const syncViewport = () => setIsCompactViewport(mediaQuery.matches);
    syncViewport();

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', syncViewport);
      return () => mediaQuery.removeEventListener('change', syncViewport);
    }

    mediaQuery.addListener(syncViewport);
    return () => mediaQuery.removeListener(syncViewport);
  }, []);

  useEffect(() => {
    let cancelled = false;
    requestPlatformAssistantCatalog()
      .then(async ({ response }) => {
        if (!response.ok || cancelled) return;
        const payload = (await response.json()) as PlatformAssistantCatalogResponse;
        if (cancelled) return;
        setRemotePageCatalog(buildAssistantPageCatalog(payload?.pages) || null);
      })
      .catch(() => {
        if (!cancelled) setRemotePageCatalog(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setRemotePageConfig(null);
    let cancelled = false;
    requestPlatformAssistantBootstrap(normalizedTab)
      .then(async ({ response }) => {
        if (!response.ok || cancelled) return;
        const payload = (await response.json()) as PlatformAssistantBootstrapResponse;
        if (!cancelled && payload?.page) {
          setRemotePageConfig(payload.page);
        }
      })
      .catch(() => {
        if (!cancelled) setRemotePageConfig(null);
      });
    return () => {
      cancelled = true;
    };
  }, [normalizedTab]);

  useEffect(() => {
    if (!isOpen) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [isOpen, messages]);

  useEffect(() => {
    return () => {
      requestAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!isCompactViewport || !externalMobileOverlayActive || !isOpen) return;
    setIsOpen(false);
  }, [externalMobileOverlayActive, isCompactViewport, isOpen]);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;

    const shouldDimNavigation = isCompactViewport && isOpen;
    document.documentElement.classList.toggle('platform-assistant-open', shouldDimNavigation);
    document.body.classList.toggle('platform-assistant-open', shouldDimNavigation);

    return () => {
      document.documentElement.classList.remove('platform-assistant-open');
      document.body.classList.remove('platform-assistant-open');
    };
  }, [isCompactViewport, isOpen]);

  const nextMessageId = () => {
    messageSeqRef.current += 1;
    return `${Date.now()}-${messageSeqRef.current}`;
  };

  const closeAssistant = () => setIsOpen(false);

  const clearConversation = () => {
    requestAbortRef.current?.abort();
    requestAbortRef.current = null;
    setIsLoading(false);
    setMessages([]);
  };

  const handleCardAction = (action: AssistantCardAction) => {
    onNavigate?.(action.targetTab);
    closeAssistant();
  };

  const replaceAssistantMessage = (
    messageId: string,
    updater: (current: AssistantMessage) => AssistantMessage,
  ) => {
    setMessages((current) =>
      current.map((message) => (message.id === messageId ? updater(message) : message)),
    );
  };

  const streamAssistantAnswer = async (question: string) => {
    const id = nextMessageId();
    const assistantId = `${id}-assistant`;
    const queuedMessages: AssistantMessage[] = [
      ...messages,
      { id: `${id}-user`, role: 'user', content: question },
      { id: assistantId, role: 'assistant', content: '' },
    ];
    const abortController = new AbortController();
    requestAbortRef.current?.abort();
    requestAbortRef.current = abortController;
    setMessages(queuedMessages);
    setIsLoading(true);

    try {
      const { response } = await requestPlatformAssistantChatStream(
        {
          messages: queuedMessages.slice(-12).map((message) => ({
            role: message.role,
            content: message.content,
          })),
          context: buildAssistantRequestContext(normalizedTab, pageConfig.cue, documents),
        },
        abortController.signal,
      );

      if (!response.ok || !response.body) {
        throw new Error((await response.text().catch(() => '')) || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let receivedText = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || '';
        for (const line of lines) {
          const parsed = parseStreamLine(line);
          if (!parsed || parsed === STREAM_DONE) continue;
          receivedText = true;
          replaceAssistantMessage(assistantId, (current) => ({
            ...current,
            content: `${current.content}${parsed}`,
            card: undefined,
          }));
        }
      }

      if (!receivedText) {
        const fallback = buildUsageFallbackCard(normalizedTab, question, pageConfig);
        replaceAssistantMessage(assistantId, () => ({
          id: assistantId,
          role: 'assistant',
          content: guidedCardToText(fallback),
          card: fallback,
        }));
      }
    } catch (error) {
      if ((error as Error)?.name === 'AbortError') return;
      const fallback = buildUsageFallbackCard(normalizedTab, question, pageConfig);
      replaceAssistantMessage(assistantId, () => ({
        id: assistantId,
        role: 'assistant',
        content: guidedCardToText(fallback),
        card: fallback,
      }));
    } finally {
      if (requestAbortRef.current === abortController) {
        requestAbortRef.current = null;
      }
      setIsLoading(false);
    }
  };

  const submitQuestion = async (rawQuestion: string) => {
    const question = rawQuestion.trim();
    if (!question || isLoading) return;
    setInput('');
    const matchedPrompt = findGuidedPrompt(question, normalizedTab, pageConfig, remotePageCatalog);
    if (matchedPrompt) {
      const id = nextMessageId();
      setMessages((current) => [
        ...current,
        { id: `${id}-user`, role: 'user', content: question },
        {
          id: `${id}-assistant`,
          role: 'assistant',
          content: guidedCardToText(matchedPrompt.answer),
          card: matchedPrompt.answer,
        },
      ]);
      return;
    }
    await streamAssistantAnswer(question);
  };

  const closedLauncherX = isCompactViewport ? 0 : -31;
  const openLauncherX = isCompactViewport ? 0 : 16;
  const shouldHideLauncher = isCompactViewport && externalMobileOverlayActive && !isOpen;
  const launcherHoverAnimation = isCompactViewport
    ? { scale: 1.02 }
    : { scale: 1.04, x: isOpen ? openLauncherX : 12 };

  return (
    <div className="pointer-events-none fixed inset-0 z-[100]">
      <motion.button
        type="button"
        initial={false}
        animate={{ x: isOpen ? openLauncherX : closedLauncherX }}
        whileHover={launcherHoverAnimation}
        whileTap={{ scale: 0.97 }}
        onClick={() => setIsOpen((current) => !current)}
        disabled={shouldHideLauncher}
        aria-hidden={shouldHideLauncher}
        className={cn(
          'pointer-events-auto fixed flex h-[58px] w-[58px] items-center justify-center overflow-hidden rounded-full border border-white/80 bg-white shadow-[0_12px_40px_rgba(34,211,238,0.2)] ring-1 ring-cyan-100 transition-[opacity,transform,filter] duration-200 dark:border-white/20 dark:bg-slate-900 dark:shadow-[0_12px_40px_rgba(8,15,31,0.5)] dark:ring-cyan-400/20 md:h-[62px] md:w-[62px]',
          launcherOffsetClassName || DEFAULT_LAUNCHER_OFFSET,
          shouldHideLauncher && 'pointer-events-none scale-90 opacity-0 blur-[1px]',
        )}
        aria-label={isOpen ? '关闭平台助手' : '打开平台助手'}
      >
        <video
          className="h-full w-full object-cover"
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          poster={assistantOrbPoster}
        >
          <source src={assistantOrbWebm} type="video/webm" />
          <source src={assistantOrb} type="video/mp4" />
        </video>
        <span className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.6),transparent_50%),linear-gradient(135deg,rgba(255,255,255,0.2),transparent)] dark:bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.3),transparent_50%),linear-gradient(135deg,rgba(255,255,255,0.05),transparent)]" />
        <AnimatePresence>
          {isOpen && (
            <motion.span
              initial={{ opacity: 0, scale: 0.8, rotate: -90 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              exit={{ opacity: 0, scale: 0.8, rotate: 90 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 flex items-center justify-center"
            >
              <X size={18} className="text-white" />
            </motion.span>
          )}
        </AnimatePresence>
      </motion.button>

      <AnimatePresence>
        {isOpen ? (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 18, scale: 0.98 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="pointer-events-auto fixed inset-x-3 bottom-[calc(var(--mobile-content-bottom)+8px)] top-[max(3.5rem,var(--mobile-safe-top))] overflow-hidden rounded-[30px] border border-slate-200/70 bg-[linear-gradient(180deg,rgba(248,251,255,0.98),rgba(255,255,255,0.96))] shadow-[0_32px_90px_rgba(15,23,42,0.16)] backdrop-blur-xl dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(8,15,30,0.96),rgba(10,20,38,0.96))] lg:bottom-20 lg:left-6 lg:right-auto lg:top-auto lg:h-[min(78vh,720px)] lg:w-[430px]"
          >
            <div className="flex h-full flex-col">
              <div className="border-b border-slate-100/50 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.1),transparent_36%),linear-gradient(135deg,rgba(255,255,255,0.9),rgba(248,250,252,0.88))] px-5 py-4 dark:border-white/5 dark:bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_30%),linear-gradient(135deg,rgba(10,20,38,0.98),rgba(12,24,45,0.96))]">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-semibold tracking-tight text-slate-800 dark:text-slate-100">平台助手</h3>
                      <div className="flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-white/10 dark:text-slate-400">
                        <div className="mr-1.5 h-1.5 w-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                        同步 {documents.length} 份文档
                      </div>
                    </div>
                    <p className="mt-1 text-[12px] leading-tight text-slate-500 dark:text-slate-400">
                      当前：{pageConfig.label}模块
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <button type="button" onClick={clearConversation} className="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-white/10 dark:hover:text-slate-200" title="清空对话">
                      <RotateCcw size={15} />
                    </button>
                    <button type="button" onClick={closeAssistant} className="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-white/10 dark:hover:text-slate-200" title="关闭助手">
                      <X size={16} />
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-6 py-6 [&::-webkit-scrollbar]:hidden scrollbar-hide">
                {messages.length === 0 ? (
                  <div className="space-y-8">
                    <div className="px-1">
                      <div className="flex items-center gap-3.5">
                        <img src={GuideImage} alt="指南" className="h-[46px] w-[46px] object-contain" draggable={false} />
                        <div>
                          <p className="text-[11px] font-bold tracking-[0.08em] text-cyan-600 dark:text-cyan-400">您可以使用</p>
                          <h4 className="mt-0.5 text-[17px] font-semibold text-slate-900 dark:text-white">{pageConfig.starter.title}</h4>
                        </div>
                      </div>
                      <div className="mt-5 space-y-4">
                        <div className="space-y-4 pt-1">
                          {pageConfig.starter.steps.map((step, index) => (
                            <div key={`${pageConfig.tab}-starter-${index}`} className="flex items-start gap-3.5 text-[14px] leading-relaxed text-slate-700 dark:text-slate-200">
                              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-50 text-[11px] font-medium text-cyan-600 dark:bg-cyan-500/10 dark:text-cyan-400">{index + 1}</span>
                              <span>{step}</span>
                            </div>
                          ))}
                        </div>
                        <div className="pt-2">
                          <ActionButtons primaryAction={pageConfig.starter.primaryAction} secondaryAction={pageConfig.starter.secondaryAction} onAction={handleCardAction} />
                        </div>
                      </div>
                    </div>

                    <div className="mt-10">
                      <div className="flex items-center gap-1.5 text-[14px] font-semibold text-slate-800 dark:text-slate-100">
                        <img src={QuestionImage} alt="常见问题" className="h-[22px] w-[22px] object-contain" draggable={false} />
                        常见问题
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 pl-1">
                        {visiblePrompts.map((prompt) => (
                          <button key={prompt.id} type="button" disabled={isLoading} onClick={() => void submitQuestion(prompt.question)} className="rounded-[14px] border border-slate-100 bg-white px-3.5 py-2 text-left text-[13px] text-slate-600 shadow-sm transition-colors hover:border-slate-200 hover:bg-slate-50 dark:border-white/5 dark:bg-[#0B1120] dark:text-slate-300 dark:hover:bg-white/5">
                            {prompt.question}
                          </button>
                        ))}
                      </div>
                    </div>

                    {documents.length ? (
                      <div className="mt-10">
                        <div className="flex items-center gap-1.5 text-[14px] font-semibold text-slate-800 dark:text-slate-100">
                          <img src={ContextImage} alt="上下文" className="h-[22px] w-[22px] object-contain" draggable={false} />
                          最近提取上下文
                        </div>
                        <div className="mt-3 space-y-2 pl-1">
                          {documents.map((document) => (
                            <div key={document.id} className="group flex items-center justify-between rounded-[16px] border border-slate-100 bg-white px-3.5 py-3 shadow-sm transition-colors hover:border-slate-200 hover:bg-slate-50 dark:border-white/5 dark:bg-[#0B1120] dark:hover:bg-white/5">
                              <div className="min-w-0 flex-1">
                                <div className="truncate text-[13px] font-medium text-slate-700 dark:text-slate-200">{document.name}</div>
                                <div className="mt-0.5 truncate text-[12px] text-slate-500 dark:text-slate-400">
                                  {document.track} · {document.fieldCount} 个字段{document.warningCount ? ` · ${document.warningCount} 条提醒` : ''}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="space-y-4">
                    {messages.map((message) => (
                      <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        {message.role === 'assistant' && message.card ? (
                          <div className="max-w-[92%] rounded-[24px] bg-slate-50/50 px-4 py-4 dark:bg-white/[0.02]">
                            <div className="mb-4">
                              <div className="inline-flex items-center gap-1.5 rounded-full bg-cyan-100/50 px-2 py-0.5 text-[11px] font-medium text-cyan-700 dark:bg-cyan-500/20 dark:text-cyan-300">
                                <Sparkles size={12} strokeWidth={2.5} />
                                操作建议
                              </div>
                              <h4 className="mt-2 text-[14px] font-semibold text-slate-800 dark:text-slate-100">{message.card.title}</h4>
                              <p className="mt-1 text-[13px] leading-relaxed text-slate-600 dark:text-slate-300">{message.card.summary}</p>
                            </div>
                            <div className="space-y-3">
                              {message.card.steps.map((step, index) => (
                                <div key={`${message.id}-step-${index}`} className="flex items-start gap-3 text-[13px] leading-relaxed text-slate-700 dark:text-slate-200">
                                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-cyan-100/60 text-[10px] font-bold text-cyan-700 dark:bg-cyan-500/20 dark:text-cyan-300">{index + 1}</span>
                                  <span>{step}</span>
                                </div>
                              ))}
                              <div className="pt-3">
                                <ActionButtons primaryAction={message.card.primaryAction} secondaryAction={message.card.secondaryAction} onAction={handleCardAction} />
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className={`max-w-[88%] whitespace-pre-wrap rounded-[24px] px-4 py-3 text-sm leading-6 shadow-sm ${message.role === 'user' ? 'rounded-br-sm bg-slate-900 text-white dark:bg-cyan-300 dark:text-slate-950' : 'rounded-bl-sm border border-slate-200/80 bg-white/95 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200'}`}>
                            {message.content || (isLoading ? '正在整理回复…' : '')}
                          </div>
                        )}
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              <div className="border-t border-slate-100 bg-white/80 px-4 py-4 backdrop-blur-md dark:border-white/5 dark:bg-slate-950/30">
                <form onSubmit={(event) => { event.preventDefault(); void submitQuestion(input); }} className="relative flex items-end">
                  <textarea
                    value={input}
                    rows={1}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        void submitQuestion(input);
                      }
                    }}
                    placeholder={visiblePrompts[0]?.question || '输入你当前想做的事，我来给你下一步建议'}
                    className="min-h-[56px] w-full resize-none rounded-[24px] border border-transparent bg-white pl-5 pr-14 pt-4 text-[14px] text-slate-700 shadow-[0_2px_12px_rgba(0,0,0,0.06)] outline-none ring-1 ring-transparent transition-all placeholder:text-slate-400 focus:border-slate-200 focus:shadow-[0_4px_20px_rgba(0,0,0,0.08)] dark:bg-[#1A1D24] dark:text-slate-100 dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)] dark:placeholder:text-slate-500 dark:focus:border-white/10 dark:focus:shadow-[0_4px_20px_rgba(0,0,0,0.3)]"
                  />
                  <button type="submit" disabled={isLoading || !input.trim()} className="absolute bottom-2.5 right-2.5 flex h-[36px] w-[36px] items-center justify-center rounded-full bg-slate-900 text-white transition-all disabled:opacity-30 disabled:hover:scale-100 hover:scale-105 hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200">
                    <ArrowUp size={18} strokeWidth={2.5} />
                  </button>
                </form>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
