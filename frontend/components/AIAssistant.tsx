import React, { useEffect, useRef, useState } from 'react';
import { X, Send, Bot, Sparkles } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { readExtractionDocuments, readExtractionUpdatedAt, type ExtractionDocument } from '@/lib/extractionStore';

type ChatRole = 'user' | 'assistant';
type ChatMessage = { id: string; role: ChatRole; content: string };

const MAX_HISTORY_MESSAGES = 20;
const TYPEWRITER_INTERVAL_MS = 16;
const MAX_CONTEXT_DOCUMENTS = 3;
const MAX_CONTEXT_FIELDS = 8;
const MAX_CONTEXT_LENGTH = 6000;

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

const buildOfflineReply = (question: string, platformContext: string): string => {
  const q = String(question || '').toLowerCase();
  const hasContext = platformContext.trim().length > 0;

  if (/如何|怎么|上手|使用这个平台|怎么用/.test(q)) {
    const contextHint = hasContext
      ? '另外，你的平台里已经有最近一次抽取数据，我会优先按这些结果回答后续问题。'
      : '当前还没有读到最近抽取结果，你可以先在智能文档解析模块上传文件并执行抽取。';
    return [
      '我先给你一个可直接执行的使用路径。',
      '第一步，先登录账号进入系统主页。',
      '第二步，打开智能文档解析模块，上传 PDF、DOCX、XLSX、TXT 或 MD 文件。',
      '第三步，点击批量抽取，接口是 /extract/batch，每批最多 5 个文件。',
      '第四步，抽取完成后去仪表盘看指标和风险统计。',
      '第五步，去全域知识图谱查看最近一次抽取形成的结构化关系。',
      '文档交互工作台目前核心交互能力仍在建设中，建议先以解析和图谱查看为主。',
      contextHint,
      '当前聊天模型服务连接不稳定，我已切换到本地兜底回答模式。',
    ].join('\n');
  }

  if (/格式|支持.*文件|文件类型|上传什么/.test(q)) {
    return [
      '智能文档解析模块当前支持 5 种格式。',
      '分别是 PDF、DOCX、XLSX、TXT、MD。',
      '批量抽取接口为 /extract/batch，每次最多上传 5 个文件。',
      '当前聊天模型服务连接不稳定，我已切换到本地兜底回答模式。',
    ].join('\n');
  }

  if (/最近.*抽取|抽取.*文档|解析结果|有哪些文档|平台内容/.test(q)) {
    if (hasContext) {
      return [
        '根据你当前平台里的最近抽取数据，我先给你汇总如下。',
        platformContext,
        '如果你要我继续分析某一份文档，请直接说文档名或字段名。',
        '当前聊天模型服务连接不稳定，我已切换到本地兜底回答模式。',
      ].join('\n');
    }
    return [
      '我现在还没有读到最近抽取数据。',
      '你可以先到智能文档解析模块上传文档并执行抽取，完成后我就能基于平台内容回答你。',
      '当前聊天模型服务连接不稳定，我已切换到本地兜底回答模式。',
    ].join('\n');
  }

  return [
    '我已收到你的问题。',
    '当前聊天模型服务连接不稳定，我先按平台已知能力给你兜底答复。',
    '你可以继续问我三类问题：平台功能说明、操作步骤排障、基于最近抽取结果的解读。',
    hasContext ? '我也可以结合你当前平台中的最近抽取数据继续回答。' : '如需基于平台内容回答，请先完成一次文档抽取。',
  ].join('\n');
};

export const AIAssistant: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const messagesRef = useRef<ChatMessage[]>([]);
  const messageSeqRef = useRef(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const typingQueuesRef = useRef<Record<string, string[]>>({});
  const typingTimerRef = useRef<number | null>(null);
  const activeRequestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const nextMessageId = () => {
    messageSeqRef.current += 1;
    return `${Date.now()}-${messageSeqRef.current}`;
  };

  const stopTypingLoop = () => {
    if (typingTimerRef.current !== null) {
      window.clearInterval(typingTimerRef.current);
      typingTimerRef.current = null;
    }
  };

  const drainTypingQueueStep = () => {
    setMessages((prev) => {
      let changed = false;
      const next = prev.map((msg) => {
        if (msg.role !== 'assistant') return msg;
        const queue = typingQueuesRef.current[msg.id];
        if (!queue || queue.length === 0) return msg;

        const nextChar = queue.shift();
        if (typeof nextChar !== 'string') return msg;

        changed = true;
        return { ...msg, content: msg.content + nextChar };
      });
      return changed ? next : prev;
    });

    const hasPending = Object.values(typingQueuesRef.current).some((queue) => queue.length > 0);
    if (!hasPending) {
      stopTypingLoop();
    }
  };

  const ensureTypingLoop = () => {
    if (typingTimerRef.current !== null) return;
    typingTimerRef.current = window.setInterval(drainTypingQueueStep, TYPEWRITER_INTERVAL_MS);
  };

  const enqueueAssistantText = (messageId: string, text: string): boolean => {
    const cleaned = normalizeAssistantText(text);
    if (!cleaned) return false;

    if (!typingQueuesRef.current[messageId]) {
      typingQueuesRef.current[messageId] = [];
    }
    typingQueuesRef.current[messageId].push(...Array.from(cleaned));
    ensureTypingLoop();
    return true;
  };

  useEffect(() => {
    return () => {
      stopTypingLoop();
      if (activeRequestRef.current) {
        activeRequestRef.current.abort();
      }
    };
  }, []);

  const sendMessage = async (userContent: string) => {
    const baseId = nextMessageId();
    const userMsg: ChatMessage = { id: `${baseId}-user`, role: 'user', content: userContent };
    const aiMsgId = `${baseId}-assistant`;
    const assistantMsg: ChatMessage = { id: aiMsgId, role: 'assistant', content: '' };
    const requestMessages = normalizeOutgoingMessages([...messagesRef.current, userMsg]);
    const platformContext = buildPlatformContext();
    const offlineReply = buildOfflineReply(userContent, platformContext);
    let receivedAnyText = false;

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    if (activeRequestRef.current) {
      activeRequestRef.current.abort();
      activeRequestRef.current = null;
    }

    const controller = new AbortController();
    activeRequestRef.current = controller;

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: requestMessages, platformContext }),
        signal: controller.signal,
      });

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
      const aborted =
        (err instanceof DOMException && err.name === 'AbortError')
        || String((err as Error)?.message || '').includes('ERR_ABORTED');

      if (!aborted) {
        const message = String((err as Error)?.message || '');
        const shouldFallback =
          /HTTP 500|Failed to fetch|NetworkError|ECONNREFUSED|socket hang up|proxy/i.test(message);

        if (shouldFallback) {
          enqueueAssistantText(aiMsgId, offlineReply);
        } else {
          console.warn('Chat request failed:', err);
          enqueueAssistantText(aiMsgId, '请求失败，请稍后重试。');
        }
      }
    } finally {
      if (activeRequestRef.current === controller) {
        activeRequestRef.current = null;
      }
      setIsLoading(false);
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

  return (
    <div className="fixed bottom-32 left-0 z-[100] flex flex-col items-start pointer-events-none font-['Microsoft_YaHei']">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, x: -20, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -20, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="mb-4 ml-2 flex h-[580px] w-[380px] max-h-[85vh] flex-col overflow-hidden rounded-2xl border border-slate-200/50 bg-white/80 shadow-2xl backdrop-blur-3xl pointer-events-auto origin-bottom-left dark:border-slate-800/50 dark:bg-slate-900/80"
          >
            <div className="flex items-center justify-between border-b border-slate-200/50 bg-gradient-to-r from-blue-50/50 to-indigo-50/50 px-5 py-4 dark:border-slate-800/50 dark:from-blue-900/20 dark:to-indigo-900/20">
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 p-2 text-white shadow-inner">
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

            <div className="custom-scrollbar flex-1 space-y-5 overflow-y-auto bg-slate-50/30 p-4 dark:bg-slate-950/30">
              {messages.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center space-y-4 text-center opacity-80">
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-blue-100 to-indigo-50 text-blue-500 dark:from-blue-900/40 dark:to-indigo-900/40">
                    <Bot size={32} />
                  </div>
                  <div>
                    <p className="font-medium text-slate-700 dark:text-slate-300">您好，我是您的专属 AI 助理。</p>
                    <p className="mt-2 max-w-[240px] text-sm text-slate-500 dark:text-slate-400">
                      您可以咨询平台功能、系统操作、文档解析与辅助决策相关问题。
                    </p>
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {msg.role !== 'user' && (
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400">
                        <Bot size={16} />
                      </div>
                    )}
                    {msg.role !== 'user' && msg.content === '' && isLoading ? (
                      <div className="flex max-w-[80%] items-center gap-1.5 rounded-2xl rounded-tl-sm border border-slate-200/50 bg-white px-4 py-3 shadow-sm dark:border-slate-700/50 dark:bg-slate-800">
                        <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-400 [animation-delay:-0.3s]" />
                        <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-400 [animation-delay:-0.15s]" />
                        <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-400" />
                      </div>
                    ) : (
                      <div
                        className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2.5 text-[14px] leading-relaxed ${
                          msg.role === 'user'
                            ? 'rounded-tr-sm bg-blue-600 text-white shadow-sm'
                            : 'rounded-tl-sm border border-slate-200/50 bg-white text-slate-700 shadow-sm dark:border-slate-700/50 dark:bg-slate-800 dark:text-slate-200'
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

            <div className="border-t border-slate-200/50 bg-white p-3 dark:border-slate-800/50 dark:bg-slate-900">
              <form
                onSubmit={handleFormSubmit}
                className="relative flex items-end overflow-hidden rounded-xl border border-slate-200 bg-slate-50 transition-shadow focus-within:ring-2 focus-within:ring-blue-500/50 dark:border-slate-800 dark:bg-slate-950"
              >
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="输入消息，开始对话..."
                  className="min-h-[50px] max-h-[120px] w-full resize-none bg-transparent py-3 pl-4 pr-12 text-sm placeholder:text-slate-400 focus:outline-none dark:placeholder:text-slate-500"
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
                  className="absolute bottom-2 right-2 rounded-lg bg-blue-600 p-2 text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600"
                >
                  <Send size={15} className={input.trim() ? '-translate-y-0.5 translate-x-0.5 transition-transform' : ''} />
                </button>
              </form>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        drag="y"
        dragConstraints={{ top: -500, bottom: 0 }}
        dragElastic={0}
        dragMomentum={false}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setIsOpen(!isOpen)}
        className={`group relative flex h-[64px] w-[44px] items-center justify-center rounded-r-2xl border border-l-0 shadow-lg transition-colors duration-200 pointer-events-auto ${
          isOpen
            ? 'border-slate-700 bg-slate-800 text-white hover:bg-slate-700'
            : 'border-emerald-400/50 bg-emerald-500 text-white shadow-emerald-500/30 hover:bg-emerald-400 hover:shadow-emerald-500/50'
        }`}
      >
        {isOpen ? <X size={20} className="-ml-1 opacity-80" /> : <Bot size={22} className="-ml-1" />}
      </motion.button>
    </div>
  );
};
