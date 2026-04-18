import React, { useEffect, useMemo, useRef, useState } from 'react';

type MobileMessageFile = {
  id: string;
  name: string;
};

type MobileMessage = {
  id: string;
  type: 'user' | 'assistant' | 'system';
  content: string;
  displayMode?: 'chat' | 'report';
  fileIds?: string[];
};

type FollowUpItem = {
  label: string;
  prompt: string;
  icon: React.ComponentType<{ size?: number }>;
};

type MobileMessageListProps = {
  messages: MobileMessage[];
  filesById: Record<string, MobileMessageFile | undefined>;
  streamingAssistantMessageId: string | null;
  messagesViewportRef: React.RefObject<HTMLDivElement | null>;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  onOpenReportFile: (fileId: string) => void;
  renderFileIcon: (file: MobileMessageFile) => React.ReactNode;
  followUpItems: FollowUpItem[];
  showFollowUpSuggestions: boolean;
  showBatchSwitcher: boolean;
  onRotateSuggestions: () => void;
  onPickSuggestion: (prompt: string) => void;
  disabled: boolean;
};

const getMobileAssistantTypingInterval = (contentLength: number): number => {
  if (contentLength <= 40) {
    return 18;
  }

  if (contentLength <= 120) {
    return 26;
  }

  if (contentLength <= 240) {
    return 34;
  }

  return 42;
};

export const MobileMessageList: React.FC<MobileMessageListProps> = ({
  messages,
  filesById,
  streamingAssistantMessageId,
  messagesViewportRef,
  messagesEndRef,
  onScroll,
  onOpenReportFile,
  renderFileIcon,
  followUpItems,
  showFollowUpSuggestions,
  showBatchSwitcher,
  onRotateSuggestions,
  onPickSuggestion,
  disabled,
}) => {
  const [displayedAssistantContent, setDisplayedAssistantContent] = useState<Record<string, string>>({});
  const hasHydratedAssistantContentRef = useRef(false);
  const previousMessageIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const previousMessageIds = previousMessageIdsRef.current;
    const previousMessageCount = previousMessageIds.size;
    const overlappingMessageCount = messages.filter((message) => previousMessageIds.has(message.id)).length;
    const shouldHydrateAssistantHistory = (
      !hasHydratedAssistantContentRef.current
      || (streamingAssistantMessageId === null && previousMessageCount > 0 && overlappingMessageCount === 0)
    );

    setDisplayedAssistantContent((prev) => {
      const next: Record<string, string> = {};

      messages.forEach((message) => {
        if (message.type !== 'assistant') {
          return;
        }

        const previousDisplayedContent = prev[message.id];

        if (shouldHydrateAssistantHistory) {
          next[message.id] = message.content;
          return;
        }

        if (previousDisplayedContent === undefined) {
          next[message.id] = '';
          return;
        }

        if (
          previousDisplayedContent.length > message.content.length
          || !message.content.startsWith(previousDisplayedContent)
        ) {
          next[message.id] = message.content;
          return;
        }

        next[message.id] = previousDisplayedContent;
      });

      const previousKeys = Object.keys(prev);
      const nextKeys = Object.keys(next);
      if (previousKeys.length !== nextKeys.length) {
        return next;
      }

      for (const key of nextKeys) {
        if (prev[key] !== next[key]) {
          return next;
        }
      }

      return prev;
    });

    previousMessageIdsRef.current = new Set(messages.map((message) => message.id));
    hasHydratedAssistantContentRef.current = true;
  }, [messages, streamingAssistantMessageId]);

  const pendingAssistantMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.type !== 'assistant') {
        continue;
      }

      const displayedContent = displayedAssistantContent[message.id] ?? '';
      if (displayedContent !== message.content) {
        return message;
      }
    }

    return null;
  }, [displayedAssistantContent, messages]);

  useEffect(() => {
    if (!pendingAssistantMessage) {
      return undefined;
    }

    const displayedContent = displayedAssistantContent[pendingAssistantMessage.id] ?? '';
    if (
      displayedContent.length > pendingAssistantMessage.content.length
      || !pendingAssistantMessage.content.startsWith(displayedContent)
    ) {
      setDisplayedAssistantContent((prev) => ({
        ...prev,
        [pendingAssistantMessage.id]: pendingAssistantMessage.content,
      }));
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      setDisplayedAssistantContent((prev) => {
        const currentContent = prev[pendingAssistantMessage.id] ?? '';
        if (
          currentContent.length >= pendingAssistantMessage.content.length
          || !pendingAssistantMessage.content.startsWith(currentContent)
        ) {
          return prev;
        }

        return {
          ...prev,
          [pendingAssistantMessage.id]: pendingAssistantMessage.content.slice(0, currentContent.length + 1),
        };
      });

      messagesEndRef.current?.scrollIntoView({
        behavior: 'auto',
        block: 'end',
      });
    }, getMobileAssistantTypingInterval(pendingAssistantMessage.content.length));

    return () => window.clearTimeout(timeoutId);
  }, [displayedAssistantContent, messagesEndRef, pendingAssistantMessage]);

  return (
    <div
      ref={messagesViewportRef}
      onScroll={onScroll}
      className="min-h-0 pb-4"
    >
      <div className="space-y-4">
        {messages.map((message) => {
          const isStreamingMessage = streamingAssistantMessageId === message.id;
          const isReportMessage = message.type === 'assistant' && message.displayMode === 'report';
          const displayedContent = message.type === 'assistant'
            ? (displayedAssistantContent[message.id] ?? '')
            : message.content;
          const isAnimatingAssistantMessage = message.type === 'assistant' && displayedContent !== message.content;
          const reportFiles = (message.fileIds ?? [])
            .map((fileId) => filesById[fileId])
            .filter((file): file is MobileMessageFile => Boolean(file));

          return (
            <div
              key={message.id}
              className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'} animate-fadeIn`}
            >
              <div
                className={`max-w-[92%] ${
                  message.type === 'user'
                    ? 'rounded-[22px] rounded-tr-md border border-[rgba(42,100,246,0.18)] bg-[rgb(42,100,246)] px-4 py-3 text-white shadow-[0_14px_30px_-24px_rgba(42,100,246,0.34)]'
                    : 'rounded-[22px] rounded-tl-md border border-[#e7effc] bg-white px-4 py-3 text-slate-700 shadow-[0_12px_28px_-24px_rgba(42,100,246,0.12)] dark:border-slate-800/80 dark:bg-slate-900 dark:text-slate-100 dark:shadow-[0_16px_32px_-24px_rgba(2,6,23,0.82)]'
                }`}
              >
                <div className="whitespace-pre-wrap text-[14px] leading-7">
                  {isStreamingMessage || isAnimatingAssistantMessage ? (
                    <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-[#d7e5fd] bg-[#f7faff] px-2.5 py-1 text-[11px] font-medium text-[#245eb6] dark:border-slate-700 dark:bg-slate-800 dark:text-sky-200">
                      <span className="h-1.5 w-1.5 rounded-full bg-[#2a64f6] animate-pulse" />
                      {isStreamingMessage ? '正在实时输出' : '正在逐字输出'}
                    </div>
                  ) : null}
                  {isReportMessage && !isStreamingMessage && !isAnimatingAssistantMessage ? (
                    <div className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-[#d7e5fd] bg-[#f7faff] px-2.5 py-1 text-[11px] font-medium text-[#245eb6] dark:border-slate-700 dark:bg-slate-800 dark:text-sky-200">
                      <span className="h-1.5 w-1.5 rounded-full bg-[#2a64f6]" />
                      分析报告
                    </div>
                  ) : null}
                  {displayedContent}
                  {isStreamingMessage || isAnimatingAssistantMessage ? (
                    <span className="ml-1 inline-block h-4 w-2 rounded-sm bg-[#2a64f6] align-[-2px] animate-pulse" />
                  ) : null}
                </div>
                {isReportMessage && reportFiles.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {reportFiles.map((file) => (
                      <button
                        key={`${message.id}-${file.id}`}
                        type="button"
                        onClick={() => onOpenReportFile(file.id)}
                        className="inline-flex max-w-full items-center gap-2 rounded-full border border-[#dbe7fb] bg-[#fbfdff] px-3 py-1.5 text-left text-[12px] font-medium text-[#35516d] transition-all hover:-translate-y-0.5 hover:border-[#d4e3fb] hover:bg-[#f9fbff] dark:border-slate-800/80 dark:bg-slate-900/78 dark:text-slate-200 dark:hover:border-slate-700 dark:hover:bg-slate-900/82"
                      >
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#e4ecf8] bg-[#fbfdff] dark:border-slate-700 dark:bg-slate-900/72">
                          {renderFileIcon(file)}
                        </span>
                        <span className="max-w-[9.5rem] truncate">{file.name}</span>
                        <span className="text-[#245eb6] dark:text-sky-200">查看完整报告</span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}

        {showFollowUpSuggestions ? (
          <div className="rounded-[22px] border border-[#e7effc] bg-white/92 p-3 shadow-[0_12px_28px_-24px_rgba(42,100,246,0.12)] dark:border-slate-800 dark:bg-slate-950/72 dark:shadow-[0_16px_32px_-24px_rgba(2,6,23,0.84)]">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[#5d7390] dark:text-slate-400">
                <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[#eef5ff] text-[#1d4ed8] dark:bg-slate-800 dark:text-sky-300">AI</span>
                猜你想做
              </div>
              {showBatchSwitcher ? (
                <button
                  type="button"
                  onClick={onRotateSuggestions}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[#dbe8fd] bg-white px-2.5 py-1 text-[11px] font-medium text-[#35516d] transition-colors hover:border-[#c8dcff] hover:bg-[#f7faff] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-slate-800"
                >
                  换一批
                </button>
              ) : null}
            </div>
            <div className="custom-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
              {followUpItems.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={`${item.label}-${item.prompt}`}
                    type="button"
                    onClick={() => onPickSuggestion(item.prompt)}
                    disabled={disabled}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[#dbe8fd] bg-white px-3 py-1.5 text-xs font-medium text-[#35516d] transition-all hover:-translate-y-0.5 hover:border-[#c8dcff] hover:bg-[#f7faff] hover:text-[#234a79] dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:bg-slate-800 dark:hover:text-sky-200 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Icon size={13} />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};
