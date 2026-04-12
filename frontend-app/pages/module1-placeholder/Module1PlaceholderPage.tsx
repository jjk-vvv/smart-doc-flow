import React from 'react';
import { Construction, Layers3, Workflow } from 'lucide-react';

export const Module1PlaceholderPage: React.FC = () => {
  return (
    <div className="flex min-h-[calc(100vh-2rem)] items-center justify-center bg-gradient-to-br from-slate-50 via-white to-blue-50 px-6 py-10">
      <div className="w-full max-w-4xl rounded-[32px] border border-slate-200 bg-white/95 p-8 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="mb-8 flex items-center gap-4">
          <div className="rounded-2xl bg-amber-100 p-4 text-amber-700">
            <Construction size={28} />
          </div>
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">Module 1</p>
            <h1 className="mt-1 text-3xl font-black tracking-tight text-slate-900">文档交互模块占位页</h1>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
            <Layers3 className="mb-3 text-sky-600" size={22} />
            <h2 className="text-lg font-bold text-slate-900">当前状态</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              该页面已保留在统一架构中，作为 Module 1 的稳定挂载位，避免导航结构和前端路由发生断裂。
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
            <Workflow className="mb-3 text-emerald-600" size={22} />
            <h2 className="text-lg font-bold text-slate-900">迁移策略</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              在阶段 0 到阶段 1 中，这里先作为占位页存在，等统一 FastAPI 入口和公共 API 边界稳定后再接入真实交互能力。
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
            <Construction className="mb-3 text-violet-600" size={22} />
            <h2 className="text-lg font-bold text-slate-900">后续方向</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              后续会把文档操作、编辑执行和结果预览能力逐步并入这一页面，同时保持现有工作台的整体信息架构不变。
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
