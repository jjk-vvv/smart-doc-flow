import React, { useState, useEffect } from 'react';
import { 
  LayoutGrid, GitGraph, ArrowRight, 
  Terminal, Activity, MessageSquare, CheckCircle2,
  FileText, Zap, ChevronRight, 
  Users, RefreshCw
} from 'lucide-react';

export const UserGuide: React.FC = () => {
  const [simulationStatus, setSimulationStatus] = useState<'idle' | 'running' | 'completed'>('idle');
  const [activeTab, setActiveTab] = useState('overview');

  const runSimulation = () => {
    setSimulationStatus('running');
    setTimeout(() => {
      setSimulationStatus('completed');
    }, 2500);
  };

  return (
    <div className="h-full overflow-y-auto bg-white dark:bg-slate-950 font-sans selection:bg-indigo-500/30">
      <div className="max-w-[1400px] mx-auto px-6 py-12 space-y-24">
        
        {/* --- 1. Hero Section: Aurora & 3D Tilt --- */}
        <div className="relative isolate">
          {/* Aurora Background */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 -z-10 w-full h-[600px] opacity-30 dark:opacity-20 pointer-events-none overflow-hidden">
            <div className="absolute top-[-10%] left-[20%] w-[500px] h-[500px] bg-purple-400/40 rounded-full blur-[120px] mix-blend-multiply dark:mix-blend-screen animate-pulse duration-700" />
            <div className="absolute top-[10%] right-[20%] w-[400px] h-[400px] bg-indigo-400/40 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-screen animate-pulse delay-700 duration-1000" />
            <div className="absolute bottom-0 left-[40%] w-[600px] h-[300px] bg-blue-400/30 rounded-full blur-[120px] mix-blend-multiply dark:mix-blend-screen" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center min-h-[600px]">
            {/* Left Content */}
            <div className="space-y-8 text-center lg:text-left z-10">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-100/80 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 backdrop-blur-sm">
                <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="text-xs font-mono font-medium text-slate-600 dark:text-slate-300">
                  V4.2.0 Enterprise Edition
                </span>
              </div>
              
              <div className="space-y-4">
                <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-slate-900 dark:text-white leading-[1.1]">
                  智能文档 <br/>
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-slate-900 via-indigo-600 to-violet-600 dark:from-white dark:via-indigo-400 dark:to-violet-400">
                    流转平台
                  </span>
                </h1>
                <p className="text-xl md:text-2xl font-light text-slate-500 dark:text-slate-400 max-w-lg mx-auto lg:mx-0">
                  基于 MAOA 架构 · 90秒极速响应 · 农业/审计多场景赋能
                </p>
              </div>

              <div className="flex flex-wrap justify-center lg:justify-start gap-4">
                <button className="group px-8 py-4 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-full font-bold transition-all hover:scale-105 active:scale-95 flex items-center gap-2 shadow-xl shadow-indigo-500/20">
                  立即开始
                  <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                </button>
                <button className="px-8 py-4 bg-white/50 dark:bg-slate-900/50 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 rounded-full font-bold hover:bg-white dark:hover:bg-slate-800 transition-all backdrop-blur-sm">
                  <span className="font-mono">npm install @maoa/sdk</span>
                </button>
              </div>
            </div>

            {/* Right 3D Visual Anchor */}
            <div className="relative perspective-1000 hidden lg:block h-[500px] w-full group">
              {/* Floating Dashboard Mockup */}
              <div className="absolute inset-0 w-full h-full transform transition-transform duration-700 ease-out hover:rotate-y-[-5deg] hover:rotate-x-[5deg] rotate-y-[-12deg] rotate-x-[6deg] preserve-3d">
                <div className="w-full h-full bg-slate-900 rounded-xl border border-slate-700/50 shadow-2xl shadow-indigo-500/30 overflow-hidden flex flex-col relative z-10">
                  {/* Mockup Header */}
                  <div className="h-10 bg-slate-800 border-b border-slate-700 flex items-center px-4 gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500/80" />
                    <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                    <div className="w-3 h-3 rounded-full bg-green-500/80" />
                    <div className="ml-4 h-5 w-64 bg-slate-700/50 rounded text-[10px] text-slate-400 flex items-center px-2 font-mono">
                      maoa-dashboard.internal
                    </div>
                  </div>
                  {/* Mockup Body */}
                  <div className="flex-1 p-6 grid grid-cols-12 gap-4 bg-slate-900/95 backdrop-blur-xl">
                    {/* Sidebar */}
                    <div className="col-span-2 space-y-3">
                      <div className="h-8 w-full bg-indigo-500/20 rounded animate-pulse" />
                      <div className="h-4 w-3/4 bg-slate-700/50 rounded" />
                      <div className="h-4 w-1/2 bg-slate-700/50 rounded" />
                      <div className="h-4 w-2/3 bg-slate-700/50 rounded" />
                    </div>
                    {/* Main Content */}
                    <div className="col-span-10 grid grid-cols-2 gap-4">
                      <div className="col-span-2 h-32 bg-gradient-to-br from-slate-800 to-slate-900 rounded-lg border border-slate-700 p-4 relative overflow-hidden">
                         <div className="absolute inset-0 bg-grid-slate-700/20 [mask-image:linear-gradient(0deg,white,rgba(255,255,255,0.6))]" />
                         <div className="absolute bottom-4 left-4 right-4 h-12 flex items-end gap-1">
                            {[40, 60, 45, 70, 50, 80, 65, 85, 90, 75].map((h, i) => (
                              <div key={i} style={{ height: `${h}%` }} className="flex-1 bg-indigo-500/50 rounded-t-sm" />
                            ))}
                         </div>
                      </div>
                      <div className="h-40 bg-slate-800/50 rounded-lg border border-slate-700 p-4">
                         <div className="flex items-center gap-3 mb-4">
                           <div className="w-8 h-8 rounded bg-emerald-500/20 flex items-center justify-center text-emerald-500"><Activity size={16}/></div>
                           <div className="h-3 w-20 bg-slate-700 rounded"/>
                         </div>
                         <div className="space-y-2">
                           <div className="h-2 w-full bg-slate-700/30 rounded"/>
                           <div className="h-2 w-5/6 bg-slate-700/30 rounded"/>
                           <div className="h-2 w-4/6 bg-slate-700/30 rounded"/>
                         </div>
                      </div>
                      <div className="h-40 bg-slate-800/50 rounded-lg border border-slate-700 p-4">
                         <div className="flex items-center gap-3 mb-4">
                           <div className="w-8 h-8 rounded bg-blue-500/20 flex items-center justify-center text-blue-500"><Users size={16}/></div>
                           <div className="h-3 w-20 bg-slate-700 rounded"/>
                         </div>
                         <div className="flex items-center justify-center h-20">
                           <div className="w-16 h-16 rounded-full border-4 border-slate-700 border-t-blue-500 rotate-45" />
                         </div>
                      </div>
                    </div>
                  </div>
                </div>
                {/* Back Glow */}
                <div className="absolute inset-0 bg-indigo-600/20 blur-3xl -z-10 transform translate-y-10 scale-90" />
              </div>
            </div>
          </div>
        </div>

        {/* --- 2. Interactive Simulation: Workflow Flow --- */}
        <div className="space-y-12">
          <div className="text-center">
            <h2 className="text-3xl font-bold text-slate-900 dark:text-white">交互式工作流模拟</h2>
            <p className="mt-4 text-slate-500 dark:text-slate-400">实时观察多智能体协同处理文档的全过程</p>
          </div>

          <div className="relative bg-slate-50 dark:bg-slate-900/50 rounded-3xl p-8 md:p-12 border border-slate-200 dark:border-slate-800 overflow-hidden">
            {/* Background Grid */}
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]" />
            
            <div className="relative z-10 grid grid-cols-1 md:grid-cols-3 gap-8 items-center">
              
              {/* Step 1: Input */}
              <div className="group relative bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-lg hover:border-indigo-500/50 transition-all duration-500">
                <div className="absolute -top-3 -left-3 w-8 h-8 bg-slate-100 dark:bg-slate-800 rounded-full border border-slate-200 dark:border-slate-700 flex items-center justify-center font-bold text-sm text-slate-500 z-10">1</div>
                <div className="h-32 flex flex-col items-center justify-center border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-xl bg-slate-50 dark:bg-slate-950/50 group-hover:bg-indigo-50/10 transition-colors">
                   <FileText className="w-10 h-10 text-slate-400 group-hover:text-indigo-500 transition-colors mb-3" />
                   <span className="text-xs font-mono text-slate-500">contract_v2.pdf</span>
                </div>
                <div className="mt-4 text-center">
                  <h3 className="font-bold text-slate-900 dark:text-white">文档注入</h3>
                  <p className="text-xs text-slate-500 mt-1">支持 PDF/Word/Image 流式传输</p>
                </div>
              </div>

              {/* Arrow Connector 1 -> 2 */}
              <div className="hidden md:flex justify-center text-slate-300 dark:text-slate-700 relative">
                 <div className={`absolute top-1/2 left-0 w-full h-[2px] bg-slate-200 dark:bg-slate-800 -translate-y-1/2 overflow-hidden`}>
                    <div className={`w-full h-full bg-indigo-500/50 transform -translate-x-full ${simulationStatus !== 'idle' ? 'animate-[shimmer_1.5s_infinite]' : ''}`} />
                 </div>
                 <ChevronRight className={`relative z-10 bg-slate-50 dark:bg-slate-900 p-1 rounded-full ${simulationStatus !== 'idle' ? 'text-indigo-500' : ''}`} />
              </div>

              {/* Step 2: Engine (Central Hub) */}
              <div className="relative">
                 <div className="absolute inset-0 bg-indigo-500/10 blur-xl rounded-full scale-75 animate-pulse" />
                 <div className="relative bg-white dark:bg-slate-900 p-8 rounded-2xl border border-indigo-100 dark:border-indigo-900/30 shadow-xl flex flex-col items-center text-center">
                    <div className="mb-6 relative">
                       <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/30 ${simulationStatus === 'running' ? 'animate-spin' : ''}`}>
                          <RefreshCw size={32} />
                       </div>
                       {simulationStatus === 'completed' && (
                         <div className="absolute -bottom-2 -right-2 w-8 h-8 bg-emerald-500 rounded-full flex items-center justify-center text-white border-4 border-white dark:border-slate-900 animate-in zoom-in">
                           <CheckCircle2 size={16} />
                         </div>
                       )}
                    </div>
                    
                    <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-2">MAOA 风险引擎</h3>
                    
                    {simulationStatus === 'idle' ? (
                      <button 
                        onClick={runSimulation}
                        className="mt-4 px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-full transition-all hover:scale-105 active:scale-95 shadow-lg shadow-indigo-500/20"
                      >
                        启动模拟程序
                      </button>
                    ) : simulationStatus === 'running' ? (
                      <div className="mt-4 px-4 py-2 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 text-xs font-mono rounded border border-indigo-100 dark:border-indigo-800">
                        Analyzing tokens...
                      </div>
                    ) : (
                      <div className="mt-4 px-4 py-2 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 text-xs font-bold rounded border border-emerald-100 dark:border-emerald-800">
                        Risk Score: 98/100
                      </div>
                    )}
                 </div>
              </div>

               {/* Arrow Connector 2 -> 3 */}
               <div className="hidden md:flex justify-center text-slate-300 dark:text-slate-700 relative">
                 <div className={`absolute top-1/2 left-0 w-full h-[2px] bg-slate-200 dark:bg-slate-800 -translate-y-1/2 overflow-hidden`}>
                    <div className={`w-full h-full bg-indigo-500/50 transform -translate-x-full ${simulationStatus === 'completed' ? 'animate-[shimmer_1s_forwards]' : ''}`} />
                 </div>
                 <ChevronRight className={`relative z-10 bg-slate-50 dark:bg-slate-900 p-1 rounded-full ${simulationStatus === 'completed' ? 'text-indigo-500' : ''}`} />
              </div>

              {/* Step 3: Copilot Output */}
              <div className="group relative bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-lg hover:border-indigo-500/50 transition-all duration-500">
                <div className="absolute -top-3 -left-3 w-8 h-8 bg-slate-100 dark:bg-slate-800 rounded-full border border-slate-200 dark:border-slate-700 flex items-center justify-center font-bold text-sm text-slate-500 z-10">3</div>
                
                <div className="h-48 bg-slate-50 dark:bg-slate-950/50 rounded-xl p-4 overflow-hidden relative">
                   {simulationStatus === 'completed' ? (
                     <div className="space-y-3 animate-in fade-in slide-in-from-bottom-4 duration-700">
                       <div className="flex gap-2">
                         <div className="w-6 h-6 rounded bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center shrink-0">
                           <Zap size={14} className="text-indigo-600 dark:text-indigo-400" />
                         </div>
                         <div className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                           <p className="font-bold text-slate-900 dark:text-white mb-1">风险警报</p>
                           发现不可抗力条款缺失，建议补充。
                         </div>
                       </div>
                       <div className="h-px w-full bg-slate-200 dark:bg-slate-800" />
                       <div className="flex gap-2 opacity-70">
                         <div className="w-6 h-6 rounded bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
                           <Terminal size={14} />
                         </div>
                         <div className="text-[10px] font-mono text-slate-500 truncate">
                           JSON payload generated...
                         </div>
                       </div>
                     </div>
                   ) : (
                     <div className="flex flex-col items-center justify-center h-full text-slate-400">
                       <MessageSquare size={24} className="mb-2 opacity-50" />
                       <span className="text-xs">等待分析结果...</span>
                     </div>
                   )}
                </div>
              </div>

            </div>
          </div>
        </div>

        {/* --- 3. Module Guides: Bento Grid --- */}
        <div className="space-y-12 pb-24">
          <div className="text-center max-w-2xl mx-auto">
            <h2 className="text-3xl font-bold text-slate-900 dark:text-white">全景能力模块</h2>
            <p className="mt-4 text-slate-500 dark:text-slate-400">打破传统文档的平铺直叙，通过可视化的 Bento Grid 快速定位核心能力。</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 auto-rows-[180px]">
            
            {/* 1. Knowledge Graph (Big 2x2) */}
            <div className="group md:col-span-2 md:row-span-2 relative overflow-hidden rounded-3xl bg-slate-900 text-white p-8 flex flex-col justify-between cursor-pointer transition-all hover:shadow-2xl hover:shadow-indigo-500/20">
               <div className="absolute inset-0 bg-gradient-to-br from-indigo-600/20 to-purple-600/20 group-hover:opacity-100 transition-opacity" />
               <div className="absolute right-0 top-0 w-full h-full opacity-30 group-hover:scale-105 transition-transform duration-700">
                  {/* Abstract Graph Background CSS Pattern */}
                  <svg className="w-full h-full" viewBox="0 0 400 400">
                     <circle cx="200" cy="200" r="100" stroke="currentColor" strokeWidth="0.5" fill="none" className="text-indigo-400 animate-[spin_20s_linear_infinite]" />
                     <circle cx="200" cy="200" r="150" stroke="currentColor" strokeWidth="0.5" fill="none" className="text-purple-400 animate-[spin_30s_linear_infinite_reverse]" />
                     <path d="M200,200 L300,300 M200,200 L100,100 M200,200 L300,100" stroke="currentColor" strokeWidth="1" className="text-slate-500" />
                     <circle cx="200" cy="200" r="4" fill="white" />
                     <circle cx="300" cy="300" r="4" fill="white" />
                     <circle cx="100" cy="100" r="4" fill="white" />
                  </svg>
               </div>
               
               <div className="relative z-10">
                 <div className="w-12 h-12 rounded-xl bg-white/10 backdrop-blur-md flex items-center justify-center mb-4 border border-white/20">
                   <GitGraph className="text-white" />
                 </div>
                 <h3 className="text-3xl font-bold mb-2">全域知识图谱</h3>
                 <p className="text-slate-300 max-w-sm">
                   深度挖掘隐性关联。支持 Cypher 查询语法，可视化展示资金链路与风险传导路径。
                 </p>
               </div>
               <div className="relative z-10 flex items-center gap-2 text-sm font-bold text-indigo-300 group-hover:text-white transition-colors">
                 查看图谱文档 <ArrowRight size={16} />
               </div>
            </div>

            {/* 2. Command Center (Wide 2x1) */}
            <div className="group md:col-span-2 relative overflow-hidden rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-8 flex flex-col justify-center cursor-pointer hover:border-indigo-500/50 transition-colors">
               <div className="absolute right-[-20px] top-[-20px] w-48 h-48 bg-slate-50 dark:bg-slate-800 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity" />
               <div className="relative z-10 flex items-start justify-between">
                 <div className="space-y-2 max-w-[60%]">
                    <div className="w-10 h-10 rounded-lg bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center text-blue-600 dark:text-blue-400 mb-2">
                       <LayoutGrid size={20} />
                    </div>
                    <h3 className="text-xl font-bold text-slate-900 dark:text-white">指挥舱布局配置</h3>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      拖拽式自定义组件，打造专属监控大屏。支持多分辨率适配与暗黑模式自动切换。
                    </p>
                 </div>
                 {/* Visual Mockup for Layout */}
                 <div className="hidden sm:block w-32 h-24 bg-slate-100 dark:bg-slate-800 rounded border border-slate-200 dark:border-slate-700 relative shadow-sm group-hover:scale-105 transition-transform origin-right">
                    <div className="absolute top-2 left-2 right-2 h-4 bg-slate-200 dark:bg-slate-700 rounded-sm" />
                    <div className="absolute top-8 left-2 w-8 bottom-2 bg-slate-200 dark:bg-slate-700 rounded-sm" />
                    <div className="absolute top-8 left-12 right-2 bottom-2 bg-indigo-500/20 rounded-sm border border-indigo-500/30" />
                 </div>
               </div>
            </div>

            {/* 3. OCR (Small 1x1) */}
            <div className="group relative overflow-hidden rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 flex flex-col justify-between hover:border-indigo-500/50 transition-colors">
               <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px] opacity-0 group-hover:opacity-30 transition-opacity" />
               <FileText className="w-8 h-8 text-slate-400 group-hover:text-indigo-500 transition-colors" />
               <div>
                 <h4 className="font-bold text-slate-900 dark:text-white">OCR 最佳实践</h4>
                 <p className="text-xs text-slate-500 mt-1">提升识别准确率技巧</p>
               </div>
            </div>

            {/* 4. Risk Threshold (Small 1x1) */}
            <div className="group relative overflow-hidden rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 flex flex-col justify-between hover:border-indigo-500/50 transition-colors">
               <div className="w-full h-1 bg-slate-100 dark:bg-slate-800 rounded-full mb-auto mt-2 overflow-hidden">
                 <div className="h-full w-2/3 bg-indigo-500 group-hover:w-full transition-all duration-500" />
               </div>
               <div>
                 <h4 className="font-bold text-slate-900 dark:text-white">风险阈值设定</h4>
                 <p className="text-xs text-slate-500 mt-1">动态调整灵敏度</p>
               </div>
            </div>

            {/* 5. Audit Log (Small 1x1) */}
            <div className="group relative overflow-hidden rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 flex flex-col justify-between hover:border-indigo-500/50 transition-colors">
               <div className="space-y-1 mb-auto opacity-50 group-hover:opacity-100 transition-opacity">
                 <div className="h-1 w-full bg-slate-200 dark:bg-slate-700 rounded" />
                 <div className="h-1 w-3/4 bg-slate-200 dark:bg-slate-700 rounded" />
                 <div className="h-1 w-1/2 bg-slate-200 dark:bg-slate-700 rounded" />
               </div>
               <div>
                 <h4 className="font-bold text-slate-900 dark:text-white">审计日志追踪</h4>
                 <p className="text-xs text-slate-500 mt-1">合规与操作记录</p>
               </div>
            </div>

             {/* 6. CLI (Small 1x1) */}
             <div className="group relative overflow-hidden rounded-3xl bg-slate-900 border border-slate-800 p-6 flex flex-col justify-between hover:ring-2 ring-indigo-500 transition-all">
               <div className="font-mono text-[10px] text-green-400 opacity-70">
                 $ maoa deploy <br/>
                 &gt; Success!
               </div>
               <div>
                 <h4 className="font-bold text-white">CLI 工具</h4>
                 <p className="text-xs text-slate-400 mt-1">无头模式批量处理</p>
               </div>
            </div>

          </div>
        </div>

      </div>
      
      {/* Global CSS for Animations */}
      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
        .perspective-1000 {
          perspective: 1000px;
        }
        .preserve-3d {
          transform-style: preserve-3d;
        }
      `}</style>
    </div>
  );
};
