import React from 'react';
import { Bot, MessageSquare, Sparkles } from 'lucide-react';

export const DocInteractionWorkbench: React.FC = () => {
  return (
    <div className="h-full flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <div className="p-3 rounded-2xl bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400">
          <Bot size={24} />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white font-['Microsoft_YaHei']">文档智能操作交互模块</h1>
          <p className="text-slate-500 dark:text-slate-400">与文档进行自然语言交互，执行智能操作指令</p>
        </div>
      </div>

      <div className="flex-1 bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm flex items-center justify-center relative overflow-hidden group">
        <div className="absolute inset-0 bg-grid-slate-100 [mask-image:linear-gradient(0deg,white,rgba(255,255,255,0.6))] dark:bg-grid-slate-700/25 dark:[mask-image:linear-gradient(0deg,rgba(255,255,255,0.1),rgba(255,255,255,0.5))]" />
        
        <div className="relative z-10 text-center space-y-4 max-w-lg mx-auto p-8">
          <div className="w-20 h-20 bg-indigo-50 dark:bg-indigo-900/20 rounded-full flex items-center justify-center mx-auto mb-6 group-hover:scale-110 transition-transform duration-500">
            <Sparkles className="text-indigo-500 w-10 h-10" />
          </div>
          <h3 className="text-xl font-bold text-slate-900 dark:text-white font-['Microsoft_YaHei']">智能交互中心</h3>
          <p className="text-slate-500 dark:text-slate-400 leading-relaxed">
            在此模块中，您可以直接与文档进行对话，发送指令如"提取合同金额"、"总结文档摘要"或"翻译这段内容"。
            <br />
            <span className="text-sm text-indigo-500 mt-2 block">功能开发中...</span>
          </p>
          
          <button className="mt-8 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium transition-all shadow-lg shadow-indigo-200 dark:shadow-indigo-900/20 flex items-center gap-2 mx-auto">
            <MessageSquare size={18} />
            <span>开始交互会话</span>
          </button>
        </div>
      </div>
    </div>
  );
};
