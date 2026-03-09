import React, { useEffect, useRef, useState } from 'react';
import { X, Send, Bot, Sparkles } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { readExtractionDocuments, readExtractionUpdatedAt, type ExtractionDocument } from '@/lib/extractionStore';

type ChatRole = 'user' | 'assistant';
type ChatMessage = { id: string; role: ChatRole; content: string };
type ResizeMode = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
type DialogPosition = { x: number; y: number };

const MAX_HISTORY_MESSAGES = 20;
const CHAT_CONNECT_TIMEOUT_MS = 25000;
const MAX_CONTEXT_DOCUMENTS = 3;
const MAX_CONTEXT_FIELDS = 8;
const MAX_CONTEXT_LENGTH = 6000;
const MIN_DIALOG_WIDTH = 300;
const MIN_DIALOG_HEIGHT = 420;
const VIEWPORT_MARGIN = 16;
const DEFAULT_DIALOG_SIZE = { width: 360, height: 560 };
const DEFAULT_DIALOG_OFFSET = { left: 56, bottom: 192 };

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const getInitialDialogPosition = (size = DEFAULT_DIALOG_SIZE): DialogPosition => {
  if (typeof window === 'undefined') {
    return { x: DEFAULT_DIALOG_OFFSET.left, y: 120 };
  }

  const maxX = Math.max(VIEWPORT_MARGIN, window.innerWidth - VIEWPORT_MARGIN - size.width);
  const maxY = Math.max(VIEWPORT_MARGIN, window.innerHeight - VIEWPORT_MARGIN - size.height);
  const rawY = window.innerHeight - DEFAULT_DIALOG_OFFSET.bottom - size.height;
  return {
    x: clamp(DEFAULT_DIALOG_OFFSET.left, VIEWPORT_MARGIN, maxX),
    y: clamp(rawY, VIEWPORT_MARGIN, maxY),
  };
};

const normalizeAssistantText = (text: string): string => (
  text
    .replace(/\r/g, '')
    .replace(/\u200b/g, '')
    .replace(/\u0000/g, '')
    .replace(/\uFFFD/g, '')
    .replace(/[*`#>]/g, '')
);

const normalizeOutgoingMessages = (messages: ChatMessage[]) =>
  messages
    .slice(-MAX_HISTORY_MESSAGES)
    .map((msg) => ({ role: msg.role, content: String(msg.content || '') }));

const toSingleLine = (value: unknown): string => {
  if (value == null) return '';
  let raw = '';
  if (typeof value === 'string') {
    raw = value;
  } else if (typeof value === 'number' || typeof value === 'boolean') {
    raw = String(value);
  } else {
    try {
      raw = JSON.stringify(value);
    } catch {
      raw = String(value);
    }
  }
  return raw.replace(/\s+/g, ' ').replace(/[*`#>]/g, '').trim();
};

const summarizeDocument = (doc: ExtractionDocument): string => {
  const fieldSummaries = Object.entries(doc.result || {})
    .slice(0, MAX_CONTEXT_FIELDS)
    .map(([field, entity]) => {
      const valueText = toSingleLine(entity?.value).slice(0, 80) || '空值';
      const confidenceRaw = Number(entity?.confidence);
      const confidenceText = Number.isFinite(confidenceRaw) ? `，置信度${Math.round(confidenceRaw * 100)}%` : '';
      return `${field}=${valueText}${confidenceText}`;
    });

  const base = `文档:${doc.file_name}（轨道:${doc.track}，缓存:${doc.cached ? '是' : '否'}）`;
  if (fieldSummaries.length === 0) return base;
  return `${base}；关键字段:${fieldSummaries.join('；')}`;
};

const buildPlatformContext = (): string => {
  const docs = readExtractionDocuments();
  if (!docs.length) return '';

  const updatedAt = readExtractionUpdatedAt() || '未知';
  const lines: string[] = [
    `最近一次抽取更新时间:${updatedAt}`,
    `最近抽取文档总数:${docs.length}`,
  ];

  for (const doc of docs.slice(0, MAX_CONTEXT_DOCUMENTS)) {
    lines.push(summarizeDocument(doc));
  }
  if (docs.length > MAX_CONTEXT_DOCUMENTS) {
    lines.push(`其余 ${docs.length - MAX_CONTEXT_DOCUMENTS} 份文档已省略。`);
  }

  return lines.join('\n').slice(0, MAX_CONTEXT_LENGTH);
};

const buildOfflineReply = (_question: string, _platformContext: string): string => (
  [
    '当前模型服务连接不稳定，本轮未获取到有效结果。',
    '请稍后重试；如果连续失败，请确认前端 3000 与后端 3001 服务均已启动。',
  ].join('\n')
);

export const AIAssistant: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [dialogSize, setDialogSize] = useState(DEFAULT_DIALOG_SIZE);
  const [dialogPosition, setDialogPosition] = useState<DialogPosition>(() => getInitialDialogPosition(DEFAULT_DIALOG_SIZE));

  const messagesRef = useRef<ChatMessage[]>([]);
  const messageSeqRef = useRef(0);
  const activeRequestIdRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingAssistantChunksRef = useRef<Record<string, string>>({});
  const flushFrameRef = useRef<number | null>(null);
  const dragMovedRef = useRef(false);
  const dragStartYRef = useRef<number | null>(null);
  const isDraggingRef = useRef(false);
  const resizeFrameRef = useRef<number | null>(null);
  const resizeLatestRef = useRef<{ x: number; y: number } | null>(null);
  const resizeStartRef = useRef<{
    x: number;
    y: number;
    width: number;
    height: number;
    left: number;
    top: number;
    mode: ResizeMode;
  } | null>(null);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    const handleViewportResize = () => {
      setDialogSize((prevSize) => {
        const maxWidth = Math.max(MIN_DIALOG_WIDTH, window.innerWidth - VIEWPORT_MARGIN * 2);
        const maxHeight = Math.max(MIN_DIALOG_HEIGHT, window.innerHeight - VIEWPORT_MARGIN * 2);
        const nextSize = {
          width: clamp(prevSize.width, MIN_DIALOG_WIDTH, maxWidth),
          height: clamp(prevSize.height, MIN_DIALOG_HEIGHT, maxHeight),
        };

        setDialogPosition((prevPos) => {
          const maxX = Math.max(VIEWPORT_MARGIN, window.innerWidth - VIEWPORT_MARGIN - nextSize.width);
          const maxY = Math.max(VIEWPORT_MARGIN, window.innerHeight - VIEWPORT_MARGIN - nextSize.height);
          return {
            x: clamp(prevPos.x, VIEWPORT_MARGIN, maxX),
            y: clamp(prevPos.y, VIEWPORT_MARGIN, maxY),
          };
        });

        return nextSize;
      });
    };

    handleViewportResize();
    window.addEventListener('resize', handleViewportResize);
    return () => window.removeEventListener('resize', handleViewportResize);
  }, []);

  const nextMessageId = () => {
    messageSeqRef.current += 1;
    return `${Date.now()}-${messageSeqRef.current}`;
  };

  const flushAssistantChunks = () => {
    flushFrameRef.current = null;
    const updates = pendingAssistantChunksRef.current;
    pendingAssistantChunksRef.current = {};
    const ids = Object.keys(updates);
    if (ids.length === 0) return;

    setMessages((prev) => {
      let changed = false;
      const next = prev.map((msg) => {
        if (msg.role !== 'assistant') return msg;
        const delta = updates[msg.id];
        if (!delta) return msg;

        changed = true;
        return { ...msg, content: msg.content + delta };
      });
      return changed ? next : prev;
    });
  };

  const scheduleFlushAssistantChunks = () => {
    if (flushFrameRef.current !== null) return;
    flushFrameRef.current = window.requestAnimationFrame(flushAssistantChunks);
  };

  const enqueueAssistantText = (messageId: string, text: string): boolean => {
    const cleaned = normalizeAssistantText(text);
    if (!cleaned) return false;

    const current = pendingAssistantChunksRef.current[messageId] || '';
    pendingAssistantChunksRef.current[messageId] = current + cleaned;
    scheduleFlushAssistantChunks();
    return true;
  };

  useEffect(() => {
    return () => {
      if (flushFrameRef.current !== null) {
        window.cancelAnimationFrame(flushFrameRef.current);
        flushFrameRef.current = null;
      }
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
        resizeFrameRef.current = null;
      }
      pendingAssistantChunksRef.current = {};
      activeRequestIdRef.current = null;
    };
  }, []);

  const sendMessage = async (userContent: string) => {
    const baseId = nextMessageId();
    const userMsg: ChatMessage = { id: `${baseId}-user`, role: 'user', content: userContent };
    const aiMsgId = `${baseId}-assistant`;
    const requestId = `${baseId}-request`;
    const assistantMsg: ChatMessage = { id: aiMsgId, role: 'assistant', content: '' };
    const requestMessages = normalizeOutgoingMessages([...messagesRef.current, userMsg]);
    const platformContext = buildPlatformContext();
    const offlineReply = buildOfflineReply(userContent, platformContext);
    let receivedAnyText = false;
    const isActiveRequest = () => activeRequestIdRef.current === requestId;
    const requestController = new AbortController();
    let didConnectTimeout = false;

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);
    activeRequestIdRef.current = requestId;
    let connectTimeoutHandle: number | null = null;

    try {
      connectTimeoutHandle = window.setTimeout(() => {
        didConnectTimeout = true;
        requestController.abort();
      }, CHAT_CONNECT_TIMEOUT_MS);

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: requestMessages, platformContext }),
        signal: requestController.signal,
      }).catch((error) => {
        if (didConnectTimeout || requestController.signal.aborted) {
          if (isActiveRequest()) {
            enqueueAssistantText(aiMsgId, offlineReply);
          }
          return null;
        }
        throw error;
      });

      if (connectTimeoutHandle !== null) {
        window.clearTimeout(connectTimeoutHandle);
        connectTimeoutHandle = null;
      }

      if (!isActiveRequest()) return;
      if (!res) return;

      if (!res.ok) {
        const errText = await res.text().catch(() => '');
        const detail = `${res.status} ${errText}`.toLowerCase();
        const shouldFallback =
          res.status >= 500
          || detail.includes('proxy')
          || detail.includes('econnrefused')
          || detail.includes('connect');

        if (shouldFallback) {
          enqueueAssistantText(aiMsgId, offlineReply);
          return;
        }
        throw new Error(errText || `HTTP ${res.status}`);
      }
      if (!res.body) {
        throw new Error('No response body');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (!isActiveRequest()) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line.startsWith('0:')) continue;

            try {
              const textPart = JSON.parse(line.slice(2));
              if (textPart === '[DONE]') continue;
              if (typeof textPart === 'string' && textPart) {
                if (enqueueAssistantText(aiMsgId, textPart)) {
                  receivedAnyText = true;
                }
              }
            } catch {
              // ignore broken partial chunks
            }
          }
        }
      } finally {
        reader.releaseLock();
      }

      const leftover = buffer.trim();
      if (leftover.startsWith('0:')) {
        try {
          const textPart = JSON.parse(leftover.slice(2));
          if (typeof textPart === 'string' && textPart !== '[DONE]') {
            if (enqueueAssistantText(aiMsgId, textPart)) {
              receivedAnyText = true;
            }
          }
        } catch {
          // ignore trailing broken chunk
        }
      }

      if (!receivedAnyText) {
        enqueueAssistantText(aiMsgId, offlineReply);
      }
    } catch (err) {
      if (!isActiveRequest()) return;
      const message = String((err as Error)?.message || '');
      const shouldFallback =
        /HTTP 500|Failed to fetch|NetworkError|ECONNREFUSED|socket hang up|proxy|aborted/i.test(message);

      if (shouldFallback) {
        enqueueAssistantText(aiMsgId, offlineReply);
      } else {
        console.warn('Chat request failed:', err);
        enqueueAssistantText(aiMsgId, '请求失败，请稍后重试。');
      }
    } finally {
      if (connectTimeoutHandle !== null) {
        window.clearTimeout(connectTimeoutHandle);
      }
      flushAssistantChunks();
      if (isActiveRequest()) {
        activeRequestIdRef.current = null;
        setIsLoading(false);
      }
    }
  };

  const handleFormSubmit = (e?: React.FormEvent<HTMLFormElement>) => {
    if (e) e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setInput('');
    void sendMessage(trimmed);
  };

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  const handleToggleClick = () => {
    if (dragMovedRef.current || isDraggingRef.current) {
      dragMovedRef.current = false;
      return;
    }
    setIsOpen((prev) => !prev);
  };

  const startResize = (mode: ResizeMode, event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);

    resizeStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      width: dialogSize.width,
      height: dialogSize.height,
      left: dialogPosition.x,
      top: dialogPosition.y,
      mode,
    };

    const applyResize = () => {
      resizeFrameRef.current = null;
      if (!resizeStartRef.current || !resizeLatestRef.current) return;
      const {
        x,
        y,
        width,
        height,
        left,
        top,
        mode: activeMode,
      } = resizeStartRef.current;
      const latest = resizeLatestRef.current;
      const dx = latest.x - x;
      const dy = latest.y - y;

      let nextWidth = width;
      let nextHeight = height;
      let nextLeft = left;
      let nextTop = top;

      if (activeMode.includes('e')) {
        const maxWidth = Math.max(MIN_DIALOG_WIDTH, Math.floor(window.innerWidth - VIEWPORT_MARGIN - left));
        nextWidth = clamp(width + dx, MIN_DIALOG_WIDTH, maxWidth);
      }
      if (activeMode.includes('s')) {
        const maxHeight = Math.max(MIN_DIALOG_HEIGHT, Math.floor(window.innerHeight - VIEWPORT_MARGIN - top));
        nextHeight = clamp(height + dy, MIN_DIALOG_HEIGHT, maxHeight);
      }
      if (activeMode.includes('w')) {
        const maxLeft = left + width - MIN_DIALOG_WIDTH;
        nextLeft = clamp(left + dx, VIEWPORT_MARGIN, maxLeft);
        nextWidth = width - (nextLeft - left);
      }
      if (activeMode.includes('n')) {
        const maxTop = top + height - MIN_DIALOG_HEIGHT;
        nextTop = clamp(top + dy, VIEWPORT_MARGIN, maxTop);
        nextHeight = height - (nextTop - top);
      }

      setDialogSize({ width: nextWidth, height: nextHeight });
      setDialogPosition({ x: nextLeft, y: nextTop });
    };

    const scheduleResize = () => {
      if (resizeFrameRef.current !== null) return;
      resizeFrameRef.current = window.requestAnimationFrame(applyResize);
    };

    const handleMove = (moveEvent: PointerEvent) => {
      if (!resizeStartRef.current) return;
      resizeLatestRef.current = { x: moveEvent.clientX, y: moveEvent.clientY };
      scheduleResize();
    };

    const handleUp = (upEvent: PointerEvent) => {
      resizeStartRef.current = null;
      resizeLatestRef.current = null;
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
        resizeFrameRef.current = null;
      }
      if (target.hasPointerCapture(upEvent.pointerId)) {
        target.releasePointerCapture(upEvent.pointerId);
      }
      window.removeEventListener('pointermove', handleMove);
      window.removeEventListener('pointerup', handleUp);
      window.removeEventListener('pointercancel', handleUp);
    };

    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleUp);
    window.addEventListener('pointercancel', handleUp);
  };

  return (
    <div className="fixed bottom-48 left-0 z-[100] pointer-events-none font-['Microsoft_YaHei']">

      <motion.button
        drag="y"
        dragConstraints={{ top: -500, bottom: 0 }}
        dragElastic={0}
        dragMomentum={false}
        onDragStart={() => {
          isDraggingRef.current = true;
          dragMovedRef.current = false;
        }}
        onDragEnd={(_, info) => {
          if (Math.abs(info.offset.y) > 4) {
            dragMovedRef.current = true;
          }
          isDraggingRef.current = false;
        }}
        onPointerDown={(event) => {
          dragStartYRef.current = event.clientY;
          dragMovedRef.current = false;
        }}
        onPointerMove={(event) => {
          if (dragStartYRef.current === null) return;
          if (Math.abs(event.clientY - dragStartYRef.current) > 4) {
            dragMovedRef.current = true;
          }
        }}
        onPointerUp={() => {
          dragStartYRef.current = null;
        }}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={handleToggleClick}
        className={`group relative flex h-[64px] w-[44px] items-center justify-center rounded-r-2xl border border-l-0 shadow-lg transition-colors duration-200 pointer-events-auto ${
          isOpen
            ? 'border-slate-700 bg-slate-800 text-white hover:bg-slate-700'
            : 'border-blue-200/80 bg-gradient-to-br from-white via-white to-blue-50/80 text-blue-600 shadow-[0_12px_26px_rgba(59,130,246,0.18)] ring-1 ring-blue-100/70 hover:to-blue-100/70 dark:border-cyan-500/40 dark:bg-gradient-to-br dark:from-[#0b1528] dark:via-[#0c1a33] dark:to-[#0f2544] dark:text-cyan-100 dark:ring-1 dark:ring-cyan-400/20 dark:shadow-[0_10px_26px_rgba(6,182,212,0.18)] dark:hover:to-[#113158]'
        }`}
      >
        {isOpen ? <X size={20} className="-ml-1 opacity-80" /> : <Bot size={22} className="-ml-1" />}
      </motion.button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="fixed pointer-events-auto origin-top-left"
            style={{ left: dialogPosition.x, top: dialogPosition.y }}
          >
            <div
              className="relative flex min-h-[420px] min-w-[300px] max-h-[80vh] max-w-[calc(100vw-120px)] flex-col overflow-hidden rounded-2xl border border-slate-200/70 bg-gradient-to-b from-white via-white to-slate-50/80 shadow-[0_22px_60px_rgba(15,23,42,0.14),_inset_0_1px_0_rgba(255,255,255,0.9)] backdrop-blur-3xl ring-1 ring-slate-200/60 dark:border-slate-700/50 dark:bg-gradient-to-b dark:from-[#0b162a] dark:via-[#0c1b33] dark:to-[#0a1428] dark:ring-1 dark:ring-slate-700/40 dark:shadow-[0_22px_80px_rgba(1,6,18,0.7),_inset_0_1px_0_rgba(255,255,255,0.04)]"
              style={{ width: dialogSize.width, height: dialogSize.height }}
            >
            <div className="pointer-events-none absolute inset-0 opacity-70">
              <div className="absolute -left-16 -top-20 h-40 w-40 rounded-full bg-gradient-to-br from-blue-100/70 via-indigo-100/25 to-transparent blur-2xl dark:from-cyan-400/15 dark:via-blue-900/25" />
              <div className="absolute -right-20 top-8 h-44 w-44 rounded-full bg-gradient-to-br from-slate-200/40 via-slate-100/20 to-transparent blur-2xl dark:from-sky-400/10 dark:via-slate-900/25" />
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-slate-200/70 to-transparent dark:via-slate-700/60" />
            </div>
            <div className="flex items-center justify-between border-b border-slate-200/70 bg-gradient-to-r from-slate-50/90 via-white to-blue-50/40 px-5 py-4 shadow-[inset_0_-1px_0_rgba(15,23,42,0.04)] dark:border-slate-700/50 dark:bg-gradient-to-r dark:from-[#0e1c36]/95 dark:via-[#0c1a33]/85 dark:to-[#0a1428]/90 dark:shadow-[inset_0_-1px_0_rgba(255,255,255,0.04)]">
              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-slate-200/70 bg-gradient-to-br from-white via-white to-blue-50/70 p-2 text-blue-600 shadow-[0_8px_18px_rgba(59,130,246,0.16)] dark:border-slate-700/40 dark:bg-gradient-to-br dark:from-[#0c213d] dark:via-[#0f2a4d] dark:to-[#14335f] dark:text-cyan-100 dark:shadow-[0_10px_24px_rgba(34,211,238,0.18)]">
                  <Sparkles size={18} />
                </div>
                <h3 className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
                  智能文档助手
                </h3>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-full p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              >
                <X size={18} />
              </button>
            </div>

            <div className="custom-scrollbar flex-1 space-y-5 overflow-y-auto bg-gradient-to-b from-white via-white to-slate-50/80 p-4 dark:bg-gradient-to-b dark:from-[#0a152a]/70 dark:via-[#0b1730]/70 dark:to-[#0c1f3a]/75">
              {messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center space-y-4 text-center opacity-80">
                  <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl border border-slate-200/70 bg-gradient-to-br from-white via-white to-blue-50/70 text-blue-600 shadow-[0_10px_22px_rgba(59,130,246,0.16)] dark:border-slate-700/40 dark:bg-gradient-to-br dark:from-[#0c203d] dark:via-[#102a4e] dark:to-[#14335f] dark:text-cyan-100 dark:shadow-[0_12px_28px_rgba(34,211,238,0.18)]">
                    <div className="absolute inset-0 rounded-2xl border border-white/60 opacity-70 dark:border-cyan-200/15" />
                    <Bot size={32} />
                  </div>
                  <div>
                    <p className="font-medium text-slate-700 dark:text-slate-300">您好，我是您的专属智能助理。</p>
                    <p className="mt-2 max-w-[240px] text-sm text-slate-500 dark:text-slate-400">
                      您可以咨询平台功能、系统操作、文档解析与辅助决策相关问题。
                    </p>
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {msg.role !== 'user' && (
                      <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200/70 bg-gradient-to-br from-white via-white to-blue-50/70 text-blue-600 dark:border-slate-700/40 dark:bg-gradient-to-br dark:from-[#0c203d] dark:via-[#102a4e] dark:to-[#14335f] dark:text-cyan-100">
                        <div className="absolute inset-0 rounded-full border border-white/60 opacity-60 dark:border-cyan-200/15" />
                        <Bot size={16} />
                      </div>
                    )}
                    {msg.role !== 'user' && msg.content === '' && isLoading ? (
                      <div className="flex max-w-[80%] items-center gap-1.5 rounded-2xl rounded-tl-sm border border-slate-200/60 bg-white px-4 py-3 shadow-sm dark:border-cyan-600/30 dark:bg-[#0f223f]/80">
                        <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-200/90 [animation-delay:-0.3s]" />
                        <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-200/90 [animation-delay:-0.15s]" />
                        <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-cyan-200/90" />
                      </div>
                    ) : (
                      <div
                        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed backdrop-blur ${
                          msg.role === 'user'
                            ? 'rounded-tr-sm bg-slate-900 text-white shadow-sm dark:bg-cyan-400/90 dark:text-slate-900'
                            : 'rounded-tl-sm border border-slate-200/60 bg-white/95 text-slate-700 shadow-sm dark:border-cyan-600/30 dark:bg-[#0e223f]/75 dark:text-slate-200'
                        }`}
                      >
                        {msg.content}
                      </div>
                    )}
                  </div>
                ))
              )}
              <div ref={messagesEndRef} className="h-1" />
            </div>

            <div className="border-t border-slate-200/70 bg-gradient-to-b from-white via-slate-50/90 to-slate-100/70 p-3 dark:border-slate-700/40 dark:bg-gradient-to-b dark:from-[#0b162a] dark:via-[#0c1a32] dark:to-[#0b1a30]">
              <form
                onSubmit={handleFormSubmit}
                className="relative flex items-end overflow-hidden rounded-xl border border-slate-200/70 bg-white/95 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)] transition-shadow focus-within:ring-2 focus-within:ring-indigo-500/30 dark:border-slate-700/40 dark:bg-gradient-to-b dark:from-[#0d223f] dark:via-[#0f2745] dark:to-[#0e213e] dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.04),_0_10px_30px_rgba(3,7,18,0.45)] dark:focus-within:ring-cyan-300/30"
              >
                <div className="absolute inset-x-3 top-2 h-px bg-gradient-to-r from-transparent via-slate-200/70 to-transparent dark:via-cyan-400/20" />
                <div className="pointer-events-none absolute inset-0 rounded-xl border border-white/50 opacity-60 dark:border-cyan-200/10" />
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="输入消息，开始对话..."
                  className="min-h-[50px] max-h-[120px] w-full resize-none bg-transparent py-3 pl-4 pr-12 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none dark:text-slate-200 dark:placeholder:text-slate-400/70"
                  rows={1}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      if (input.trim() && !isLoading) {
                        handleFormSubmit();
                      }
                    }
                  }}
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isLoading}
                  className="absolute bottom-2 right-2 rounded-lg bg-slate-900 p-2 text-white shadow-sm transition-colors hover:bg-slate-800 disabled:opacity-50 disabled:hover:bg-slate-900 dark:bg-gradient-to-br dark:from-cyan-200 dark:via-cyan-300 dark:to-sky-200 dark:text-slate-900 dark:shadow-[0_8px_18px_rgba(34,211,238,0.2)] dark:hover:from-cyan-100 dark:hover:to-sky-100"
                >
                  <Send size={15} className={input.trim() ? '-translate-y-0.5 translate-x-0.5 transition-transform' : ''} />
                </button>
              </form>
            </div>
            <div className="absolute -top-1.5 left-3 right-3 z-20 h-3 cursor-ns-resize" onPointerDown={(event) => startResize('n', event)} style={{ touchAction: 'none' }} />
            <div className="absolute -bottom-1.5 left-3 right-3 z-20 h-3 cursor-ns-resize" onPointerDown={(event) => startResize('s', event)} style={{ touchAction: 'none' }} />
            <div className="absolute -left-1.5 top-3 bottom-3 z-20 w-3 cursor-ew-resize" onPointerDown={(event) => startResize('w', event)} style={{ touchAction: 'none' }} />
            <div className="absolute -right-1.5 top-3 bottom-3 z-20 w-3 cursor-ew-resize" onPointerDown={(event) => startResize('e', event)} style={{ touchAction: 'none' }} />
            <div className="absolute -left-1.5 -top-1.5 z-30 h-4 w-4 cursor-nwse-resize" onPointerDown={(event) => startResize('nw', event)} style={{ touchAction: 'none' }} />
            <div className="absolute -right-1.5 -top-1.5 z-30 h-4 w-4 cursor-nesw-resize" onPointerDown={(event) => startResize('ne', event)} style={{ touchAction: 'none' }} />
            <div className="absolute -left-1.5 -bottom-1.5 z-30 h-4 w-4 cursor-nesw-resize" onPointerDown={(event) => startResize('sw', event)} style={{ touchAction: 'none' }} />
            <div className="absolute -right-1.5 -bottom-1.5 z-30 h-4 w-4 cursor-nwse-resize" onPointerDown={(event) => startResize('se', event)} style={{ touchAction: 'none' }} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
