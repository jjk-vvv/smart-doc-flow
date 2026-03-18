import React, { Suspense, lazy } from 'react';
import { BrainCircuit } from 'lucide-react';

const KnowledgeNexusScreen = lazy(() =>
  import('./knowledge-nexus/KnowledgeNexusNeo4j').then((mod) => ({ default: mod.KnowledgeNexus }))
);

const loadingFallback = (
  <div className="module4-workbench flex h-screen items-center justify-center px-6">
    <div className="module4-empty-state flex items-center gap-3 border border-slate-200 px-5 py-4 text-sm font-medium text-slate-600 shadow-none">
      <BrainCircuit size={18} className="animate-pulse text-sky-600" />
      <span>正在加载知识图谱工作台...</span>
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
