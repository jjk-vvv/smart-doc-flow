import React, { useState, useRef, useEffect } from 'react';
import { Bot, Send, Sparkles, User } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
};

interface Module2InlineAssistantProps {
  className?: string;
}

export const Module2InlineAssistant: React.FC<Module2InlineAssistantProps> = ({ className }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue,
      timestamp: Date.now(),
    };

    const aiMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: '当前面板暂未接入实时指令执行，请使用模块二主工作台右侧助手面板进行操作。',
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg, aiMsg]);
    setInputValue('');
  };

  return (
    <div className={cn("flex flex-col h-full bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800", className)}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2 bg-slate-50/50 dark:bg-slate-900/50">
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center shadow-sm">
          <Bot size={16} className="text-white" />
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">信息提取任务助手</h3>
          <div className="flex items-center gap-1 text-[10px] text-slate-500">
            <Sparkles size={10} className="text-blue-500" />
            <span>助手功能详情</span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0 scroll-smooth custom-scrollbar"
      >
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-center text-xs text-slate-500 dark:text-slate-400">
            暂无对话记录，请输入指令开始会话。
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn(
              "flex gap-3 max-w-[90%]",
              msg.role === 'user' ? "ml-auto flex-row-reverse" : "mr-auto"
            )}
          >
            <div className={cn(
              "w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1",
              msg.role === 'assistant' ? "bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400" : "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
            )}>
              {msg.role === 'assistant' ? <Bot size={16} /> : <User size={16} />}
            </div>
            <div className={cn(
              "p-3 rounded-2xl text-xs leading-relaxed shadow-sm",
              msg.role === 'assistant' 
                ? "bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-tl-none" 
                : "bg-blue-600 text-white rounded-tr-none"
            )}>
              {msg.content}
            </div>
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="p-3 bg-slate-50/50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-800">
        <div
          className="relative flex flex-col rounded-[20px] border border-slate-200/80 bg-white shadow-sm transition-all focus-within:border-blue-400/50 focus-within:shadow-md hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:focus-within:border-blue-500/50 dark:hover:border-slate-600"
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            // Implement file drop handling here if needed
          }}
        >
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="输入自然语言指令..."
            className="w-full bg-transparent px-4 pt-3 pb-2 text-[13px] text-slate-700 dark:text-slate-200 focus:outline-none resize-none min-h-[60px] custom-scrollbar"
          />
          <div className="flex items-center justify-between px-2 pb-2 pt-1">
            <div className="flex items-center gap-1">
              {/* Optional actions placeholder */}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSend}
                disabled={!inputValue.trim()}
                className={cn(
                  'inline-flex h-7 w-7 items-center justify-center rounded-full transition-all duration-300',
                  !inputValue.trim()
                    ? 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-slate-800/80 dark:text-slate-500'
                    : 'bg-[#a3b8d7] text-white shadow-sm hover:bg-[#8ba3c7] hover:scale-105 active:scale-95 dark:bg-blue-600 dark:hover:bg-blue-700'
                )}
              >
                <Send size={12} className="ml-0.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
