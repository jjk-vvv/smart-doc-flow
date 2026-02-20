import React, { useState } from 'react';
import { Filter, Wand2, Download, Table, AlertCircle, CheckCircle2, MoreHorizontal, ArrowRight } from 'lucide-react';
import { TableRow } from '../types';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const mockTableData: TableRow[] = [];

export const FusionGrid: React.FC = () => {
  const [selectedRows, setSelectedRows] = useState<string[]>([]);

  const toggleRow = (id: string) => {
    if (selectedRows.includes(id)) {
      setSelectedRows(selectedRows.filter(rowId => rowId !== id));
    } else {
      setSelectedRows([...selectedRows, id]);
    }
  };

  return (
    <div className="h-[calc(100vh-2rem)] flex flex-col rounded-xl overflow-hidden glass-card shadow-2xl relative border border-white/10">
      {/* Ambient Background Glow */}
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[100px] pointer-events-none z-0"></div>
      
      {/* Toolbar */}
      <div className="h-16 border-b border-white/10 dark:border-white/10 flex items-center px-6 justify-between bg-white/40 dark:bg-white/5 backdrop-blur-md relative z-10">
        <div className="flex items-center gap-4">
            <div className="p-2 bg-gradient-to-br from-emerald-500/20 to-teal-500/20 rounded-lg border border-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.2)]">
                <Table size={18} className="text-emerald-500 dark:text-emerald-400" />
            </div>
            <div>
                <h2 className="font-bold text-sm tracking-wide text-foreground flex items-center gap-2">
                  No File Loaded
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-500"></span>
                </h2>
                <div className="flex items-center gap-2 mt-0.5">
                   <span className="text-[10px] text-muted-foreground font-mono">Last updated: --</span>
                   <span className="px-1.5 py-0.5 rounded-md bg-white/20 dark:bg-white/5 border border-white/20 dark:border-white/10 text-[10px] font-bold text-muted-foreground">
                      IDLE
                   </span>
                </div>
            </div>
        </div>
        <div className="flex items-center gap-3">
            <button className="flex items-center gap-2 px-3 py-1.5 bg-white/20 dark:bg-white/5 border border-white/20 dark:border-white/10 rounded-lg text-xs font-bold text-muted-foreground hover:text-foreground hover:bg-white/30 dark:hover:bg-white/10 hover:border-white/30 dark:hover:border-white/20 transition-all active:scale-95">
                <Filter size={14} /> 筛选 (Filter)
            </button>
            <button className="flex items-center gap-2 px-3 py-1.5 bg-primary/10 border border-primary/20 text-primary rounded-lg text-xs font-bold hover:bg-primary/20 hover:shadow-[0_0_15px_rgba(56,189,248,0.3)] transition-all active:scale-95 group">
                <Wand2 size={14} className="group-hover:rotate-12 transition-transform" /> AI 自动填充
            </button>
            <div className="w-px h-6 bg-white/20 dark:bg-white/10 mx-2"></div>
            <button className="p-2 text-muted-foreground hover:text-primary transition-colors hover:bg-white/20 dark:hover:bg-white/5 rounded-lg border border-transparent hover:border-white/20 dark:hover:border-white/10">
                <Download size={18} />
            </button>
        </div>
      </div>

      {/* Grid Container */}
      <div className="flex-1 overflow-auto bg-slate-50/50 dark:bg-slate-900/30 relative z-10 custom-scrollbar pb-24">
        <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 z-20 bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl text-[10px] uppercase font-bold text-muted-foreground tracking-wider shadow-sm border-b border-border/10 dark:border-white/10">
                <tr>
                    <th className="p-4 w-16 text-center">
                       <div className="w-4 h-4 border border-muted-foreground/20 rounded mx-auto"></div>
                    </th>
                    <th className="p-4 font-bold font-['Microsoft_YaHei']">费用项目 (Item)</th>
                    <th className="p-4 font-bold font-['Microsoft_YaHei']">金额 (CNY)</th>
                    <th className="p-4 font-bold font-['Microsoft_YaHei']">日期 (Date)</th>
                    <th className="p-4 font-bold font-['Microsoft_YaHei']">来源文档 (Source)</th>
                    <th className="p-4 font-bold font-['Microsoft_YaHei']">置信度 (Confidence)</th>
                    <th className="p-4 font-bold font-['Microsoft_YaHei']">状态 (Status)</th>
                    <th className="p-4 w-10"></th>
                </tr>
            </thead>
            <tbody className="text-sm font-mono">
                <AnimatePresence>
                {mockTableData.map((row, index) => (
                    <motion.tr 
                       initial={{ opacity: 0, y: 10 }}
                       animate={{ opacity: 1, y: 0 }}
                       transition={{ delay: index * 0.05 }}
                       key={row.id} 
                       onClick={() => toggleRow(row.id)}
                       className={cn(
                          "group border-b border-white/5 transition-colors cursor-pointer relative",
                          selectedRows.includes(row.id) ? "bg-primary/5" : "hover:bg-white/5"
                       )}
                    >
                        <td className="p-4 text-center relative">
                            {selectedRows.includes(row.id) && (
                               <motion.div layoutId="active-row-indicator" className="absolute left-0 top-0 bottom-0 w-1 bg-primary shadow-[0_0_10px_#38bdf8]" />
                            )}
                            <div className={cn(
                               "w-4 h-4 border rounded mx-auto transition-colors flex items-center justify-center",
                               selectedRows.includes(row.id) ? "bg-primary border-primary text-black" : "border-white/20 group-hover:border-white/40"
                            )}>
                               {selectedRows.includes(row.id) && <CheckCircle2 size={10} />}
                            </div>
                        </td>
                        <td className="p-4 font-medium text-foreground group-hover:text-primary transition-colors">{row.item}</td>
                        <td className="p-4 text-muted-foreground font-bold">¥{row.amount.toLocaleString()}</td>
                        <td className="p-4 text-muted-foreground/70">{row.date}</td>
                        <td className="p-4">
                           <span className="flex items-center gap-2 px-2 py-1 rounded-md bg-white/5 border border-white/10 text-[10px] text-muted-foreground group-hover:border-primary/30 transition-colors w-fit">
                              <span className="w-1 h-4 bg-indigo-500/50 rounded-full"></span>
                              {row.sourceDoc}
                           </span>
                        </td>
                        <td className="p-4">
                            <div className="flex items-center gap-3">
                                <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden w-20">
                                   <motion.div 
                                      initial={{ width: 0 }}
                                      animate={{ width: `${row.confidence * 100}%` }}
                                      transition={{ duration: 1, delay: 0.5 + index * 0.1 }}
                                      className={cn(
                                         "h-full rounded-full shadow-[0_0_10px_currentColor]",
                                         row.confidence > 0.9 ? 'bg-emerald-500' : 
                                         row.confidence > 0.8 ? 'bg-amber-500' : 'bg-red-500'
                                      )}
                                   />
                                </div>
                                <span className={cn(
                                   "text-xs font-bold",
                                   row.confidence > 0.9 ? 'text-emerald-500' : 
                                   row.confidence > 0.8 ? 'text-amber-500' : 'text-red-500'
                                )}>{Math.floor(row.confidence * 100)}%</span>
                            </div>
                        </td>
                        <td className="p-4">
                           {row.status === 'VERIFIED' ? (
                              <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-bold text-emerald-500 w-fit shadow-[0_0_10px_rgba(16,185,129,0.1)]">
                                 <CheckCircle2 size={12} /> 已核验
                              </div>
                           ) : (
                              <button className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-red-500/10 border border-red-500/20 text-[10px] font-bold text-red-500 w-fit animate-pulse shadow-[0_0_10px_rgba(239,68,68,0.1)] hover:bg-red-500/20 hover:scale-105 transition-all group/btn">
                                 <AlertCircle size={12} /> 
                                 Mismatch
                                 <ArrowRight size={10} className="ml-1 opacity-0 -translate-x-2 group-hover/btn:opacity-100 group-hover/btn:translate-x-0 transition-all" />
                              </button>
                           )}
                        </td>
                        <td className="p-4 text-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <button className="p-1 hover:bg-white/10 rounded text-muted-foreground hover:text-foreground">
                               <ArrowRight size={14} />
                            </button>
                        </td>
                    </motion.tr>
                ))}
                </AnimatePresence>
                
                {/* Simulated Scanning Rows */}
                {[1, 2, 3].map((i) => (
                    <tr key={`ghost-${i}`} className="border-b border-white/5 opacity-30">
                       <td className="p-4 text-center"><div className="w-4 h-4 border border-white/10 rounded mx-auto"></div></td>
                       <td className="p-4"><div className="h-4 w-32 bg-white/10 rounded animate-pulse"></div></td>
                       <td className="p-4"><div className="h-4 w-20 bg-white/10 rounded animate-pulse"></div></td>
                       <td className="p-4"><div className="h-4 w-24 bg-white/10 rounded animate-pulse"></div></td>
                       <td className="p-4"><div className="h-4 w-28 bg-white/10 rounded animate-pulse"></div></td>
                       <td className="p-4"><div className="h-4 w-16 bg-white/10 rounded animate-pulse"></div></td>
                       <td className="p-4"><div className="h-4 w-20 bg-white/10 rounded animate-pulse"></div></td>
                       <td className="p-4"></td>
                    </tr>
                ))}
            </tbody>
        </table>
        
        {/* Scanning Line Effect */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
           <div className="w-full h-[2px] bg-gradient-to-r from-transparent via-primary/30 to-transparent absolute top-0 animate-[scan_3s_linear_infinite]"></div>
        </div>
      </div>
      
      {/* Floating Capsule Footer */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border border-white/20 dark:border-white/10 shadow-2xl rounded-full px-6 py-2.5 flex items-center gap-6 z-20 hover:scale-105 transition-transform duration-300">
         <div className="flex items-center gap-2">
             <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
             <span className="text-[10px] text-muted-foreground font-bold font-mono">MAOA 引擎运行中</span>
         </div>
         <div className="w-px h-4 bg-white/20 dark:bg-white/10"></div>
         <div className="flex items-center gap-4 text-[10px] font-mono font-bold text-muted-foreground">
             <span>已选中: <span className="text-foreground">{selectedRows.length}</span></span>
             <span>已核验: <span className="text-foreground">0</span></span>
         </div>
         <div className="w-px h-4 bg-white/20 dark:bg-white/10"></div>
         <div className="flex gap-4 text-[10px] font-mono font-bold">
             <span className="text-muted-foreground">总计: <span className="text-foreground">¥0.00</span></span>
             <span className="text-slate-400">差额: ¥0.00</span>
         </div>
      </div>
    </div>
  );
};