import React, { useState } from 'react';
import { EntityNode, EntityLink } from '../types';
import { X, ExternalLink, ShieldAlert, Zap, Network, Share2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const nodes: EntityNode[] = [];

const links: EntityLink[] = [];

export const KnowledgeNexus: React.FC = () => {
  const [selectedNode, setSelectedNode] = useState<EntityNode | null>(null);

  return (
    <div className="h-[calc(100vh-2rem)] rounded-xl overflow-hidden glass-card relative shadow-2xl border border-white/10 flex">
      
      {/* Background Grid & Ambient Glow */}
      <div className="absolute inset-0 bg-slate-50 dark:bg-[#020617] pointer-events-none">
         <div className="absolute inset-0 bg-[radial-gradient(#cbd5e1_1px,transparent_1px)] dark:bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:20px_20px] opacity-5"></div>
         <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-[120px] animate-pulse"></div>
         <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-[120px] animate-pulse delay-1000"></div>
      </div>

      {/* Overlay UI */}
      <div className="absolute top-6 left-6 z-10 pointer-events-none">
        <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-primary/10 border border-primary/20 rounded-lg backdrop-blur-md">
                <Network className="text-primary" size={24} />
            </div>
            <div>
                <h2 className="text-black dark:text-white font-bold font-['Microsoft_YaHei'] text-xl tracking-tight flex items-center gap-2">
                  全域知识图谱
                </h2>
            </div>
        </div>
      </div>

      <div className="absolute bottom-6 left-6 z-10 pointer-events-none">
          <div className="glass px-4 py-3 rounded-xl flex items-center gap-4">
              <div className="flex flex-col">
                  <span className="text-[10px] text-muted-foreground font-bold uppercase">Nodes</span>
                  <span className="text-lg font-mono font-bold text-foreground">0</span>
              </div>
              <div className="w-px h-8 bg-white/10"></div>
              <div className="flex flex-col">
                  <span className="text-[10px] text-muted-foreground font-bold uppercase">Edges</span>
                  <span className="text-lg font-mono font-bold text-foreground">0</span>
              </div>
              <div className="w-px h-8 bg-white/10"></div>
              <div className="flex flex-col">
                  <span className="text-[10px] text-muted-foreground font-bold uppercase">Risk</span>
                  <span className="text-lg font-mono font-bold text-slate-500">0</span>
              </div>
          </div>
      </div>

      <div className="absolute top-6 right-6 z-10 glass-panel p-4 rounded-xl flex flex-col gap-3 w-48 backdrop-blur-xl border border-white/20 dark:border-white/10 bg-white/60 dark:bg-slate-900/60 shadow-2xl hover:-translate-y-1 transition-transform duration-300">
         <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1">Legend</h3>
         <div className="flex items-center gap-2 text-xs text-muted-foreground font-bold">
            <span className="w-3 h-3 bg-primary/20 border border-primary rounded-sm shadow-[0_0_10px_rgba(56,189,248,0.3)]"></span> 
            <span className="text-foreground font-bold font-['Microsoft_YaHei']">普通实体 (Entity)</span>
         </div>
         <div className="flex items-center gap-2 text-xs text-muted-foreground font-bold">
            <span className="w-3 h-3 bg-red-500/20 border border-red-500 rounded-sm shadow-[0_0_10px_rgba(239,68,68,0.4)] animate-pulse"></span> 
            <span className="text-red-500 dark:text-red-400 font-bold font-['Microsoft_YaHei']">风险节点 (Risk)</span>
         </div>
      </div>

      {/* Graph Visualizer */}
      <div className="flex-1 relative z-0 overflow-hidden cursor-move">
        <svg className="w-full h-full">
            <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--muted-foreground))" />
                </marker>
                <marker id="arrow-risk" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#ef4444" />
                </marker>
                <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
                <feMerge>
                    <feMergeNode in="coloredBlur"/>
                    <feMergeNode in="SourceGraphic"/>
                </feMerge>
                </filter>
                <linearGradient id="link-gradient" gradientUnits="userSpaceOnUse">
                    <stop offset="0%" stopColor="rgba(56,189,248,0.1)" />
                    <stop offset="50%" stopColor="rgba(56,189,248,0.5)" />
                    <stop offset="100%" stopColor="rgba(56,189,248,0.1)" />
                </linearGradient>
            </defs>

            {/* Links */}
            {links.map((link, i) => {
                const start = nodes.find(n => n.id === link.source)!;
                const end = nodes.find(n => n.id === link.target)!;
                const isRiskLink = nodes.find(n => n.id === link.source)?.type === 'Risk' || nodes.find(n => n.id === link.target)?.type === 'Risk';
                const pathData = `M${start.x},${start.y} C${start.x},${(start.y + end.y)/2} ${end.x},${(start.y + end.y)/2} ${end.x},${end.y}`;
                
                return (
                    <g key={i} className="group">
                        <path 
                            d={pathData} 
                            fill="none" 
                            stroke={isRiskLink ? "rgba(239,68,68,0.5)" : "rgba(148,163,184,0.1)"} 
                            strokeWidth={isRiskLink ? 3 : 1.5} 
                            markerEnd={isRiskLink ? "url(#arrow-risk)" : "url(#arrow)"}
                            className="transition-all duration-300 group-hover:stroke-primary group-hover:stroke-[2px]"
                        />
                        {/* Animated Dash for Data Flow */}
                        <path 
                            d={pathData} 
                            fill="none" 
                            stroke={isRiskLink ? "#ef4444" : "#38bdf8"} 
                            strokeWidth={isRiskLink ? 3 : 2} 
                            strokeDasharray={isRiskLink ? "4, 12" : "4, 8"}
                            className={cn(
                                "animate-[dash_1s_linear_infinite]", 
                                isRiskLink ? "opacity-80" : "opacity-0 group-hover:opacity-100"
                            )}
                        />
                        
                        <rect 
                            x={(start.x + end.x) / 2 - 24} 
                            y={(start.y + end.y) / 2 - 10} 
                            width="48" height="20" 
                            rx="4" 
                            fill="#0f172a" 
                            stroke={isRiskLink ? "rgba(239,68,68,0.3)" : "rgba(255,255,255,0.1)"}
                            className="group-hover:stroke-primary transition-colors"
                        />
                        <text 
                            x={(start.x + end.x) / 2} 
                            y={(start.y + end.y) / 2 + 4} 
                            fill={isRiskLink ? "#fca5a5" : "#94a3b8"} 
                            fontSize="9"
                            textAnchor="middle"
                            fontFamily="monospace"
                            fontWeight="bold"
                            className="group-hover:fill-primary transition-colors pointer-events-none select-none"
                        >
                            {link.label}
                        </text>
                    </g>
                );
            })}

            {/* Nodes */}
            {nodes.map((node) => {
                const isRisk = node.type === 'Risk';
                const isSelected = selectedNode?.id === node.id;
                
                return (
                <g 
                key={node.id} 
                onClick={() => setSelectedNode(node)}
                className="cursor-pointer transition-all duration-300"
                style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
                >
                    {/* Selection Ring */}
                    {isSelected && (
                        <circle cx={node.x} cy={node.y} r="45" fill="none" stroke={isRisk ? "#ef4444" : "#38bdf8"} strokeWidth="1" strokeDasharray="4,4" className="animate-[spin_10s_linear_infinite]" />
                    )}

                    {/* Node Shape */}
                    <rect 
                        x={node.x - 60} 
                        y={node.y - 25} 
                        width="120" 
                        height="50" 
                        rx="12" 
                        fill={isRisk ? 'rgba(69, 10, 10, 0.8)' : 'rgba(15, 23, 42, 0.8)'} 
                        stroke={isRisk ? '#ef4444' : isSelected ? '#38bdf8' : 'rgba(255,255,255,0.1)'}
                        strokeWidth={isRisk || isSelected ? 2 : 1}
                        className={cn(
                            "transition-all duration-300 shadow-[0_0_20px_rgba(0,0,0,0.5)] backdrop-blur-sm",
                            isSelected && "shadow-[0_0_30px_rgba(56,189,248,0.3)]"
                        )}
                    />
                    
                    {/* Status Dot */}
                    <circle cx={node.x - 45} cy={node.y} r="4" fill={isRisk ? '#ef4444' : '#38bdf8'} className={isRisk ? 'animate-pulse' : ''} />
                    
                    {/* Text */}
                    <text 
                        x={node.x} 
                        y={node.y - 2} 
                        textAnchor="middle" 
                        fill="#fff"
                        className="text-sm font-bold tracking-wide pointer-events-none select-none"
                        fontSize="12" 
                    >
                        {node.label}
                    </text>
                    <text 
                        x={node.x} 
                        y={node.y + 12} 
                        textAnchor="middle" 
                        fill={isRisk ? '#fca5a5' : '#94a3b8'} 
                        fontSize="9"
                        className="uppercase font-mono font-bold tracking-wider pointer-events-none select-none"
                    >
                        {node.type}
                    </text>
                </g>
            )})}
        </svg>
      </div>

      {/* Side Detail Panel */}
      <AnimatePresence>
      {selectedNode && (
         <motion.div 
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="absolute top-0 right-0 h-full w-96 bg-slate-900/90 backdrop-blur-xl border-l border-white/10 shadow-2xl z-20"
         >
               <div className="flex flex-col h-full">
                  <div className="p-6 border-b border-white/10 relative overflow-hidden">
                     <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent pointer-events-none"></div>
                     <div className="flex justify-between items-start mb-4 relative z-10">
                        <span className={cn(
                           "px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider border",
                           selectedNode.type === 'Risk' 
                              ? 'bg-red-500/10 text-red-400 border-red-500/20' 
                              : 'bg-primary/10 text-primary border-primary/20'
                        )}>
                           {selectedNode.type}
                        </span>
                        <button 
                           onClick={() => setSelectedNode(null)} 
                           className="text-muted-foreground hover:text-foreground p-1 hover:bg-white/10 rounded transition-colors"
                        >
                           <X size={18}/>
                        </button>
                     </div>
                     <h3 className="text-xl font-bold text-white mb-1 relative z-10 flex items-center gap-2">
                        {selectedNode.label}
                        <ExternalLink size={14} className="text-muted-foreground hover:text-primary cursor-pointer" />
                     </h3>
                     <p className="text-xs text-muted-foreground font-mono relative z-10">UUID: {selectedNode.id}-XJ9-2023</p>
                  </div>
                  
                  <div className="flex-1 p-6 space-y-6 overflow-y-auto custom-scrollbar">
                     {/* Attributes */}
                     <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                           <div className="text-[10px] text-muted-foreground uppercase mb-1">Created At</div>
                           <div className="text-xs font-mono text-white">2023-06-15</div>
                        </div>
                        <div className="p-3 bg-white/5 rounded-lg border border-white/5">
                           <div className="text-[10px] text-muted-foreground uppercase mb-1">Data Source</div>
                           <div className="text-xs font-mono text-white">ERP_V3.0</div>
                        </div>
                     </div>

                     <div>
                        <h4 className="text-xs font-bold text-muted-foreground uppercase mb-3 flex items-center gap-2">
                           <Share2 size={12} />
                           关联关系 (Relationships)
                        </h4>
                        <div className="space-y-2">
                           {links.filter(l => l.source === selectedNode.id || l.target === selectedNode.id).map((l, i) => (
                              <div key={i} className="flex items-center gap-3 text-sm p-3 bg-white/5 rounded-lg border border-white/5 hover:border-white/20 transition-colors cursor-pointer group">
                                 <span className="w-1.5 h-1.5 rounded-full bg-primary group-hover:shadow-[0_0_8px_#38bdf8] transition-all"></span>
                                 <span className="text-slate-300 font-mono text-xs">{l.label}</span>
                                 <div className="flex-1 h-px bg-white/10"></div>
                                 <span className="text-xs text-muted-foreground">
                                    {l.source === selectedNode.id ? nodes.find(n => n.id === l.target)?.label : nodes.find(n => n.id === l.source)?.label}
                                 </span>
                              </div>
                           ))}
                        </div>
                     </div>

                     {selectedNode.type === 'Risk' && (
                        <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl relative overflow-hidden group">
                           <div className="absolute inset-0 bg-gradient-to-r from-red-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                           <div className="flex items-center gap-2 mb-2 text-red-400 font-bold text-sm relative z-10">
                              <ShieldAlert size={16} className="animate-pulse" />
                              高风险因子 (High Risk Factor)
                           </div>
                           <p className="text-xs text-red-300/80 leading-relaxed relative z-10">
                              该实体因与 <strong className="text-red-300">气象报告 #2023-07</strong> 存在逻辑冲突而被系统标记。可能会影响“履约能力”。
                           </p>
                           <div className="mt-3 flex gap-2 relative z-10">
                              <button className="flex-1 py-1.5 bg-red-500 hover:bg-red-400 text-white text-[10px] font-bold rounded shadow-lg shadow-red-500/20 transition-all">查看详情</button>
                              <button className="flex-1 py-1.5 bg-transparent border border-red-500/30 text-red-400 hover:bg-red-500/10 text-[10px] font-bold rounded transition-all">忽略警告</button>
                           </div>
                        </div>
                     )}
                     
                     {/* AI Insight */}
                     <div className="p-4 bg-indigo-500/5 border border-dashed border-indigo-500/30 rounded-xl">
                        <div className="flex items-center gap-2 mb-2 text-indigo-400 font-bold text-sm">
                           <Zap size={14} />
                           AI 预测 (Prediction)
                        </div>
                        <p className="text-xs text-indigo-300/70 leading-relaxed">
                           基于当前图谱结构，系统预测该节点在未来 30 天内活跃度将提升 <span className="text-indigo-300 font-bold">15%</span>。
                        </p>
                     </div>
                  </div>
               </div>
         </motion.div>
      )}
      </AnimatePresence>
    </div>
  );
};