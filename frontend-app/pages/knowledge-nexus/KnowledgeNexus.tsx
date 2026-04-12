import React, { Suspense, lazy } from 'react';
import { BrainCircuit } from 'lucide-react';

const KnowledgeNexusScreen = lazy(() =>
  import('./KnowledgeNexusGraphRAGG6').then((mod) => ({ default: mod.KnowledgeNexus }))
);

const LOADING_TEXT = '正在加载知识图谱工作台...';

const loadingFallback = (
  <div className="flex h-[calc(100vh-2rem)] items-center justify-center rounded-[24px] border border-white/60 bg-gradient-to-br from-cyan-50 via-white to-slate-50 px-6 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:border-slate-800/80 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 dark:shadow-[0_8px_30px_rgb(0,0,0,0.2)]">
    <div className="flex items-center gap-3 rounded-[16px] border border-slate-200/60 bg-white/80 px-6 py-4 text-sm font-bold text-slate-700 shadow-[0_2px_10px_rgb(0,0,0,0.02)] backdrop-blur-md dark:border-slate-700/60 dark:bg-slate-900/60 dark:text-slate-200 dark:shadow-[0_2px_10px_rgb(0,0,0,0.2)]">
      <BrainCircuit size={18} className="animate-pulse text-cyan-600 dark:text-cyan-400" />
      <span>{LOADING_TEXT}</span>
    </div>
  </div>
);

export const KnowledgeNexus: React.FC = () => {
  return (
    <Suspense fallback={loadingFallback}>
      <KnowledgeNexusScreen />
    </Suspense>
  );
};
