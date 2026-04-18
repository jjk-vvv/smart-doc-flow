import React, { Suspense, lazy, useState } from 'react';
import { BrainCircuit, GitGraph, X } from 'lucide-react';
import {
  clearModule4DraftFromHomeWorkbench,
  readModule4DraftFromHomeWorkbench,
} from '../../shared/state/homeWorkbench';

const KnowledgeNexusScreen = lazy(() =>
  import('./KnowledgeNexusGraphRAGG6').then((mod) => ({ default: mod.KnowledgeNexus }))
);

const LOADING_TEXT = '正在加载知识图谱工作台...';
const RENDER_ERROR_TITLE = '知识图谱页面加载失败';
const RENDER_ERROR_HINT = '请点击“重试”刷新页面，或稍后再次进入该模块。';

type KnowledgeNexusErrorBoundaryState = {
  hasError: boolean;
  message: string;
};

class KnowledgeNexusErrorBoundary extends React.Component<React.PropsWithChildren, KnowledgeNexusErrorBoundaryState> {
  constructor(props: React.PropsWithChildren) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: unknown): KnowledgeNexusErrorBoundaryState {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : '未知错误',
    };
  }

  componentDidCatch(error: unknown) {
    console.error('[module4] KnowledgeNexus render failed', error);
  }

  private handleRetry = () => {
    this.setState({ hasError: false, message: '' });
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <section className="module4-workbench flex h-screen items-center justify-center bg-white px-6 dark:bg-slate-950">
        <div className="w-full max-w-lg rounded-lg border border-rose-200 bg-rose-50/80 p-5 text-left text-sm text-rose-800 dark:border-rose-500/40 dark:bg-rose-950/50 dark:text-rose-100">
          <div className="text-base font-semibold">{RENDER_ERROR_TITLE}</div>
          <p className="mt-2 leading-6">{RENDER_ERROR_HINT}</p>
          <p className="mt-2 break-all text-xs text-rose-700/90 dark:text-rose-200/80">
            错误详情：{this.state.message || '未提供'}
          </p>
          <button
            type="button"
            onClick={this.handleRetry}
            className="mt-4 inline-flex items-center rounded-md border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100 dark:border-rose-400/50 dark:bg-rose-950 dark:text-rose-100 dark:hover:bg-rose-900"
          >
            重试
          </button>
        </div>
      </section>
    );
  }
}

const loadingFallback = (
  <div className="module4-workbench flex h-screen items-center justify-center px-6">
    <div className="module4-empty-state flex items-center gap-3 border border-slate-200 px-5 py-4 text-sm font-medium text-slate-600 shadow-none">
      <BrainCircuit size={18} className="animate-pulse text-sky-600" />
      <span>{LOADING_TEXT}</span>
    </div>
  </div>
);

export const KnowledgeNexus: React.FC = () => {
  const [showHomeDraftBanner, setShowHomeDraftBanner] = useState(() =>
    Boolean(readModule4DraftFromHomeWorkbench())
  );

  return (
    <KnowledgeNexusErrorBoundary>
      {showHomeDraftBanner ? (
        <div className="fixed left-1/2 top-5 z-[80] -translate-x-1/2">
          <div className="flex max-w-[840px] items-center gap-3 rounded-full border border-slate-200 bg-white/96 px-4 py-2 text-sm text-slate-700 shadow-[0_18px_40px_-26px_rgba(15,23,42,0.28)] backdrop-blur-xl dark:border-slate-700 dark:bg-slate-900/95 dark:text-slate-200">
            <GitGraph size={16} className="text-sky-600 dark:text-sky-400" />
            <span>首页已有文件加入模块四候选清单。模块四当前以图谱工作台为主，建议先在模块二完成抽取后再继续下游图谱处理。</span>
            <button
              type="button"
              onClick={() => {
                clearModule4DraftFromHomeWorkbench();
                setShowHomeDraftBanner(false);
              }}
              className="rounded-full p-1 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      ) : null}
      <Suspense fallback={loadingFallback}>
        <KnowledgeNexusScreen />
      </Suspense>
    </KnowledgeNexusErrorBoundary>
  );
};
