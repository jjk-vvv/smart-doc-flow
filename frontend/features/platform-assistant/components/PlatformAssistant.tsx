import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, ArrowUp, RotateCcw, Sparkles, X } from 'lucide-react';

import assistantOrb from '../../../assets/assistant-orb.mp4';
import assistantOrbPoster from '../../../assets/assistant-orb-poster.png';
import assistantOrbWebm from '../../../assets/assistant-orb.webm';
import GuideImage from '../../../assets/使用说明插图.png';
import QuestionImage from '../../../assets/问号插图.png';
import ContextImage from '../../../assets/上下文插图.png';
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

type LauncherEdge = 'left' | 'right' | 'top' | 'bottom';

type LauncherPosition = {
  x: number;
  y: number;
  edge: LauncherEdge;
};

const DEFAULT_LAUNCHER_OFFSET =
  'bottom-[calc(96px+env(safe-area-inset-bottom))] left-3 md:bottom-[140px] md:left-0';
const STREAM_DONE = '__done__';
const COMPACT_VIEWPORT_QUERY = '(max-width: 1180px)';
const PLATFORM_ASSISTANT_LAUNCHER_STORAGE_KEY = 'platform_assistant.launcher_position.v1';
const LAUNCHER_DRAG_THRESHOLD_PX = 8;
const LAUNCHER_EDGE_HIDE_RATIO = 0.38;

const clampNumber = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

const getLauncherSize = (compact: boolean) => (compact ? 58 : 62);

const getLauncherViewportPadding = (compact: boolean) => ({
  top: 16,
  right: 16,
  bottom: compact ? 20 : 24,
  left: 16,
});

const getHiddenLauncherOffset = (compact: boolean) =>
  Math.round(getLauncherSize(compact) * LAUNCHER_EDGE_HIDE_RATIO);

const buildDefaultLauncherPosition = (compact: boolean): LauncherPosition => {
  const size = getLauncherSize(compact);
  const padding = getLauncherViewportPadding(compact);
  if (typeof window === 'undefined') {
    return { x: 0, y: 160, edge: 'left' };
  }
  const preferredBottom = compact ? 96 : 140;
  return {
    x: 0,
    y: clampNumber(window.innerHeight - size - preferredBottom, padding.top, Math.max(padding.top, window.innerHeight - size - padding.bottom)),
    edge: 'left',
  };
};

const clampLauncherPosition = (
  position: LauncherPosition,
  compact: boolean,
): LauncherPosition => {
  if (typeof window === 'undefined') return position;
  const size = getLauncherSize(compact);
  const padding = getLauncherViewportPadding(compact);
  const maxX = Math.max(0, window.innerWidth - size);
  const maxY = Math.max(padding.top, window.innerHeight - size - padding.bottom);

  let x = clampNumber(Number(position.x || 0), 0, maxX);
  let y = clampNumber(Number(position.y || 0), padding.top, maxY);

  if (position.edge === 'left') x = 0;
  if (position.edge === 'right') x = maxX;
  if (position.edge === 'top') y = padding.top;
  if (position.edge === 'bottom') y = maxY;

  return {
    x,
    y,
    edge: position.edge,
  };
};

const snapLauncherPosition = (
  x: number,
  y: number,
  compact: boolean,
): LauncherPosition => {
  if (typeof window === 'undefined') return { x, y, edge: 'left' };
  const size = getLauncherSize(compact);
  const padding = getLauncherViewportPadding(compact);
  const maxX = Math.max(0, window.innerWidth - size);
  const maxY = Math.max(padding.top, window.innerHeight - size - padding.bottom);
  const nextX = clampNumber(x, 0, maxX);
  const nextY = clampNumber(y, padding.top, maxY);
  const centerX = nextX + size / 2;
  const centerY = nextY + size / 2;
  const distances: Array<{ edge: LauncherEdge; distance: number }> = [
    { edge: 'left', distance: centerX },
    { edge: 'right', distance: window.innerWidth - centerX },
    { edge: 'top', distance: centerY },
    { edge: 'bottom', distance: window.innerHeight - centerY },
  ];
  distances.sort((left, right) => left.distance - right.distance);
  const edge = distances[0]?.edge || 'left';

  return clampLauncherPosition(
    {
      x: edge === 'left' ? 0 : edge === 'right' ? maxX : nextX,
      y: edge === 'top' ? padding.top : edge === 'bottom' ? maxY : nextY,
      edge,
    },
    compact,
  );
};

const clampLauncherDragPosition = (
  x: number,
  y: number,
  compact: boolean,
): Pick<LauncherPosition, 'x' | 'y'> => {
  if (typeof window === 'undefined') return { x, y };
  const size = getLauncherSize(compact);
  const padding = getLauncherViewportPadding(compact);
  const hiddenOffset = getHiddenLauncherOffset(compact);
  return {
    x: clampNumber(x, -hiddenOffset, Math.max(-hiddenOffset, window.innerWidth - size + hiddenOffset)),
    y: clampNumber(y, padding.top, Math.max(padding.top, window.innerHeight - size - padding.bottom)),
  };
};

const readLauncherPosition = (compact: boolean): LauncherPosition => {
  if (typeof window === 'undefined') return buildDefaultLauncherPosition(compact);
  try {
    const raw = window.localStorage.getItem(PLATFORM_ASSISTANT_LAUNCHER_STORAGE_KEY);
    if (!raw) return buildDefaultLauncherPosition(compact);
    const parsed = JSON.parse(raw) as Partial<LauncherPosition>;
    const edge = parsed.edge === 'left' || parsed.edge === 'right' || parsed.edge === 'top' || parsed.edge === 'bottom'
      ? parsed.edge
      : 'left';
    return clampLauncherPosition(
      {
        x: Number(parsed.x || 0),
        y: Number(parsed.y || 0),
        edge,
      },
      compact,
    );
  } catch {
    return buildDefaultLauncherPosition(compact);
  }
};

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
      className="inline-flex items-center gap-2 rounded-[18px] bg-blue-50 px-5 py-2.5 text-[13px] font-medium text-blue-600 transition-all hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-400 dark:hover:bg-blue-500/20"
    >
      <span>{primaryAction.label}</span>
      <ArrowRight size={15} />
    </button>
    {secondaryAction ? (
      <button
        type="button"
        onClick={() => onAction(secondaryAction)}
        className="rounded-[18px] border border-slate-200 bg-transparent px-5 py-2.5 text-[13px] font-medium text-slate-600 transition-all hover:bg-slate-50 dark:border-white/10 dark:text-slate-300 dark:hover:bg-white/5"
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
  const initialCompactViewport =
    typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(COMPACT_VIEWPORT_QUERY).matches;
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCompactViewport, setIsCompactViewport] = useState(initialCompactViewport);
  const [launcherPosition, setLauncherPosition] = useState<LauncherPosition>(() =>
    readLauncherPosition(initialCompactViewport),
  );
  const [isLauncherDragging, setIsLauncherDragging] = useState(false);
  const [documents, setDocuments] = useState<ContextDocument[]>(
    () => readAssistantExtractionSnapshot().documents,
  );
  const [remotePageConfig, setRemotePageConfig] = useState<PlatformAssistantBootstrapPage | null>(null);
  const [remotePageCatalog, setRemotePageCatalog] = useState<AssistantPageCatalog | null>(null);
  const requestAbortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const messageSeqRef = useRef(0);
  const launcherPositionRef = useRef<LauncherPosition>(launcherPosition);
  const launcherDragStateRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    moved: boolean;
  } | null>(null);
  const suppressLauncherClickRef = useRef(false);
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

    const mediaQuery = window.matchMedia(COMPACT_VIEWPORT_QUERY);
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
    launcherPositionRef.current = launcherPosition;
  }, [launcherPosition]);

  useEffect(() => {
    setLauncherPosition((current) => clampLauncherPosition(current, isCompactViewport));
  }, [isCompactViewport]);

  useEffect(() => {
    if (typeof window === 'undefined' || isLauncherDragging) return;
    window.localStorage.setItem(
      PLATFORM_ASSISTANT_LAUNCHER_STORAGE_KEY,
      JSON.stringify(launcherPosition),
    );
  }, [isLauncherDragging, launcherPosition]);

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

  const handleLauncherPointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (isOpen) return;
    const size = getLauncherSize(isCompactViewport);
    const restingOffsetX =
      launcherPosition.edge === 'left'
        ? -getHiddenLauncherOffset(isCompactViewport)
        : launcherPosition.edge === 'right'
          ? getHiddenLauncherOffset(isCompactViewport)
          : 0;

    launcherDragStateRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: launcherPosition.x + restingOffsetX,
      originY: launcherPosition.y,
      moved: false,
    };

    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Ignore pointer capture failures in older environments.
    }
  };

  const handleLauncherPointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const dragState = launcherDragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId || isOpen) return;

    const deltaX = event.clientX - dragState.startX;
    const deltaY = event.clientY - dragState.startY;
    const movedEnough = Math.hypot(deltaX, deltaY) >= LAUNCHER_DRAG_THRESHOLD_PX;

    if (!dragState.moved && !movedEnough) return;

    if (!dragState.moved) {
      dragState.moved = true;
      setIsLauncherDragging(true);
      setLauncherPosition((current) =>
        clampLauncherPosition(
          {
            ...current,
            x: dragState.originX,
            y: dragState.originY,
          },
          isCompactViewport,
        ),
      );
    }

    const nextPosition = clampLauncherDragPosition(
      dragState.originX + deltaX,
      dragState.originY + deltaY,
      isCompactViewport,
    );
    setLauncherPosition((current) => ({
      ...current,
      x: nextPosition.x,
      y: nextPosition.y,
    }));
  };

  const handleLauncherPointerEnd = (event: React.PointerEvent<HTMLButtonElement>) => {
    const dragState = launcherDragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) return;

    if (dragState.moved) {
      setLauncherPosition((current) => snapLauncherPosition(current.x, current.y, isCompactViewport));
      setIsLauncherDragging(false);
      suppressLauncherClickRef.current = true;
      window.setTimeout(() => {
        suppressLauncherClickRef.current = false;
      }, 0);
    }

    launcherDragStateRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Ignore pointer capture release failures.
    }
  };

  const handleLauncherClick = () => {
    if (suppressLauncherClickRef.current || isLauncherDragging) {
      suppressLauncherClickRef.current = false;
      return;
    }
    setIsOpen((current) => !current);
  };

  const openLauncherX = isCompactViewport
    ? 0
    : launcherPosition.edge === 'right'
      ? -16
      : launcherPosition.edge === 'left'
        ? 16
        : 0;
  const hoverRevealX = launcherPosition.edge === 'right' ? -12 : launcherPosition.edge === 'left' ? 12 : 0;
  const launcherHoverAnimation = isCompactViewport || isLauncherDragging
    ? { scale: 1.02 }
    : { scale: 1.04, x: isOpen ? openLauncherX : hoverRevealX };
  const launcherRestingOffsetX = isOpen || isLauncherDragging
    ? 0
    : launcherPosition.edge === 'left'
      ? -getHiddenLauncherOffset(isCompactViewport)
      : launcherPosition.edge === 'right'
        ? getHiddenLauncherOffset(isCompactViewport)
        : 0;
  const assistantShellClassName = isCompactViewport
    ? 'pointer-events-auto fixed inset-x-3 bottom-20 top-14 overflow-hidden rounded-[28px] border border-slate-200/70 bg-[linear-gradient(180deg,rgba(248,251,255,0.98),rgba(255,255,255,0.96))] shadow-[0_28px_72px_rgba(15,23,42,0.18)] backdrop-blur-xl dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(8,15,30,0.96),rgba(10,20,38,0.96))]'
    : 'pointer-events-auto fixed inset-x-4 bottom-24 top-16 overflow-hidden rounded-[30px] border border-slate-200/70 bg-[linear-gradient(180deg,rgba(248,251,255,0.98),rgba(255,255,255,0.96))] shadow-[0_32px_90px_rgba(15,23,42,0.16)] backdrop-blur-xl dark:border-white/10 dark:bg-[linear-gradient(180deg,rgba(8,15,30,0.96),rgba(10,20,38,0.96))] md:left-[90px] md:right-auto md:top-auto md:h-[min(78vh,720px)] md:w-[430px]';

  return (
    <div className="pointer-events-none fixed inset-0 z-[100]">
      <motion.button
        type="button"
        initial={false}
        animate={{ x: isOpen ? openLauncherX : launcherRestingOffsetX }}
        whileHover={launcherHoverAnimation}
        whileTap={{ scale: 0.97 }}
        onClick={handleLauncherClick}
        onPointerDown={handleLauncherPointerDown}
        onPointerMove={handleLauncherPointerMove}
        onPointerUp={handleLauncherPointerEnd}
        onPointerCancel={handleLauncherPointerEnd}
        className={`pointer-events-auto fixed flex h-[58px] w-[58px] items-center justify-center overflow-hidden rounded-full border border-white/80 bg-white shadow-[0_12px_40px_rgba(34,211,238,0.2)] ring-1 ring-cyan-100 dark:border-white/20 dark:bg-slate-900 dark:shadow-[0_12px_40px_rgba(8,15,31,0.5)] dark:ring-cyan-400/20 md:h-[62px] md:w-[62px] ${isOpen ? 'cursor-pointer' : isLauncherDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
        style={{ left: launcherPosition.x, top: launcherPosition.y }}
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
            className={assistantShellClassName}
          >
            <div className="flex h-full flex-col">
              <div className={`border-b border-slate-100/50 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.1),transparent_36%),linear-gradient(135deg,rgba(255,255,255,0.9),rgba(248,250,252,0.88))] dark:border-white/5 dark:bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_30%),linear-gradient(135deg,rgba(10,20,38,0.98),rgba(12,24,45,0.96))] ${isCompactViewport ? 'px-4 py-3.5' : 'px-5 py-4'}`}>
                <div className={`flex items-center justify-between ${isCompactViewport ? 'gap-3' : 'gap-4'}`}>
                  <div>
                    <div className={`flex items-center ${isCompactViewport ? 'gap-1.5' : 'gap-2'}`}>
                      <h3 className={`${isCompactViewport ? 'text-[15px]' : 'text-base'} font-semibold tracking-tight text-slate-800 dark:text-slate-100`}>平台助手</h3>
                      <div className={`flex items-center rounded-full bg-slate-100 ${isCompactViewport ? 'px-1.5 py-0.5 text-[9px]' : 'px-2 py-0.5 text-[10px]'} font-medium text-slate-500 dark:bg-white/10 dark:text-slate-400`}>
                        <div className="mr-1.5 h-1.5 w-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                        同步 {documents.length} 份文档
                      </div>
                    </div>
                    <p className={`mt-1 leading-tight text-slate-500 dark:text-slate-400 ${isCompactViewport ? 'text-[11px]' : 'text-[12px]'}`}>
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

              <div className={`flex-1 overflow-y-auto [&::-webkit-scrollbar]:hidden scrollbar-hide ${isCompactViewport ? 'px-4 py-4' : 'px-6 py-6'}`}>
                {messages.length === 0 ? (
                  <div className={isCompactViewport ? 'space-y-6' : 'space-y-8'}>
                    <div className="px-1">
                      <div className={`flex items-center ${isCompactViewport ? 'gap-3' : 'gap-3.5'}`}>
                        <img src={GuideImage} alt="指南" className={`${isCompactViewport ? 'h-[40px] w-[40px]' : 'h-[46px] w-[46px]'} object-contain`} draggable={false} />
                        <div>
                          <p className="text-[11px] font-bold tracking-[0.08em] text-cyan-600 dark:text-cyan-400">您可以使用</p>
                          <h4 className={`mt-0.5 ${isCompactViewport ? 'text-[15px]' : 'text-[17px]'} font-semibold text-slate-900 dark:text-white`}>{pageConfig.starter.title}</h4>
                        </div>
                      </div>
                      <div className={`${isCompactViewport ? 'mt-4 space-y-3' : 'mt-5 space-y-4'}`}>
                        <div className="space-y-4 pt-1">
                          {pageConfig.starter.steps.map((step, index) => (
                            <div key={`${pageConfig.tab}-starter-${index}`} className={`flex items-start ${isCompactViewport ? 'gap-3 text-[13px]' : 'gap-3.5 text-[14px]'} leading-relaxed text-slate-700 dark:text-slate-200`}>
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

                    <div className={isCompactViewport ? 'mt-7' : 'mt-10'}>
                      <div className="flex items-center gap-1.5 text-[14px] font-semibold text-slate-800 dark:text-slate-100">
                        <img src={QuestionImage} alt="常见问题" className={`${isCompactViewport ? 'h-[20px] w-[20px]' : 'h-[22px] w-[22px]'} object-contain`} draggable={false} />
                        常见问题
                      </div>
                      <div className={`mt-3 flex flex-wrap ${isCompactViewport ? 'gap-1.5' : 'gap-2'} pl-1`}>
                        {visiblePrompts.map((prompt) => (
                          <button key={prompt.id} type="button" disabled={isLoading} onClick={() => void submitQuestion(prompt.question)} className={`rounded-[14px] border border-slate-100 bg-white ${isCompactViewport ? 'px-3 py-1.5 text-[12px]' : 'px-3.5 py-2 text-[13px]'} text-left text-slate-600 shadow-sm transition-colors hover:border-slate-200 hover:bg-slate-50 dark:border-white/5 dark:bg-[#0B1120] dark:text-slate-300 dark:hover:bg-white/5`}>
                            {prompt.question}
                          </button>
                        ))}
                      </div>
                    </div>

                    {documents.length ? (
                      <div className={isCompactViewport ? 'mt-7' : 'mt-10'}>
                        <div className="flex items-center gap-1.5 text-[14px] font-semibold text-slate-800 dark:text-slate-100">
                          <img src={ContextImage} alt="上下文" className={`${isCompactViewport ? 'h-[20px] w-[20px]' : 'h-[22px] w-[22px]'} object-contain`} draggable={false} />
                          最近提取上下文
                        </div>
                        <div className="mt-3 space-y-2 pl-1">
                          {documents.map((document) => (
                            <div key={document.id} className="group flex items-center justify-between rounded-[16px] border border-slate-100 bg-white px-3.5 py-3 shadow-sm transition-colors hover:border-slate-200 hover:bg-slate-50 dark:border-white/5 dark:bg-[#0B1120] dark:hover:bg-white/5">
                              <div className="min-w-0 flex-1">
                              <div className={`truncate ${isCompactViewport ? 'text-[12px]' : 'text-[13px]'} font-medium text-slate-700 dark:text-slate-200`}>{document.name}</div>
                              <div className={`mt-0.5 truncate ${isCompactViewport ? 'text-[11px]' : 'text-[12px]'} text-slate-500 dark:text-slate-400`}>
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
                  <div className={isCompactViewport ? 'space-y-3' : 'space-y-4'}>
                    {messages.map((message) => (
                      <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        {message.role === 'assistant' && message.card ? (
                          <div className={`max-w-[92%] rounded-[24px] bg-slate-50/50 ${isCompactViewport ? 'px-3.5 py-3.5' : 'px-4 py-4'} dark:bg-white/[0.02]`}>
                            <div className="mb-4">
                              <div className="inline-flex items-center gap-1.5 rounded-full bg-cyan-100/50 px-2 py-0.5 text-[11px] font-medium text-cyan-700 dark:bg-cyan-500/20 dark:text-cyan-300">
                                <Sparkles size={12} strokeWidth={2.5} />
                                操作建议
                              </div>
                              <h4 className={`mt-2 ${isCompactViewport ? 'text-[13px]' : 'text-[14px]'} font-semibold text-slate-800 dark:text-slate-100`}>{message.card.title}</h4>
                              <p className={`mt-1 ${isCompactViewport ? 'text-[12px]' : 'text-[13px]'} leading-relaxed text-slate-600 dark:text-slate-300`}>{message.card.summary}</p>
                            </div>
                            <div className="space-y-3">
                              {message.card.steps.map((step, index) => (
                                <div key={`${message.id}-step-${index}`} className={`flex items-start gap-3 ${isCompactViewport ? 'text-[12px]' : 'text-[13px]'} leading-relaxed text-slate-700 dark:text-slate-200`}>
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
                          <div className={`max-w-[88%] whitespace-pre-wrap rounded-[24px] ${isCompactViewport ? 'px-3.5 py-2.5 text-[13px] leading-6' : 'px-4 py-3 text-sm leading-6'} shadow-sm ${message.role === 'user' ? 'rounded-br-sm bg-slate-900 text-white dark:bg-cyan-300 dark:text-slate-950' : 'rounded-bl-sm border border-slate-200/80 bg-white/95 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200'}`}>
                            {message.content || (isLoading ? '正在整理回复…' : '')}
                          </div>
                        )}
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>

              <div className={`border-t border-slate-100 bg-white/80 backdrop-blur-md dark:border-white/5 dark:bg-slate-950/30 ${isCompactViewport ? 'px-4 py-4' : 'px-4 pb-6 pt-4'}`}>
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
                    className={`w-full resize-none rounded-[24px] border border-transparent bg-white pr-14 text-[14px] text-slate-700 shadow-[0_2px_12px_rgba(0,0,0,0.06)] outline-none ring-1 ring-transparent transition-all placeholder:text-slate-400 focus:border-slate-200 focus:shadow-[0_4px_20px_rgba(0,0,0,0.08)] dark:bg-[#1A1D24] dark:text-slate-100 dark:shadow-[0_2px_12px_rgba(0,0,0,0.2)] dark:placeholder:text-slate-500 dark:focus:border-white/10 dark:focus:shadow-[0_4px_20px_rgba(0,0,0,0.3)] ${isCompactViewport ? 'min-h-[52px] pl-4 pt-3.5 text-[13px]' : 'min-h-[56px] pl-5 pt-4'}`}
                  />
                  <button type="submit" disabled={isLoading || !input.trim()} className={`absolute right-2.5 flex items-center justify-center rounded-full bg-slate-900 text-white transition-all disabled:opacity-30 disabled:hover:scale-100 hover:scale-105 hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200 ${isCompactViewport ? 'bottom-2 h-[34px] w-[34px]' : 'bottom-2.5 h-[36px] w-[36px]'}`}>
                    <ArrowUp size={isCompactViewport ? 17 : 18} strokeWidth={2.5} />
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
