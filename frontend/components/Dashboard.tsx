import React, { useState, useEffect } from 'react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar
} from 'recharts';
import { 
  UploadCloud, FileText, Activity, AlertOctagon, Terminal, 
  Zap, Loader2, ArrowRight, Database, Server, BrainCircuit
} from 'lucide-react';
import { motion } from 'framer-motion';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Utility for merging classes
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Mock Data
const dataRadar: any[] = [];

  const StatCard = ({ title, value, icon: Icon, trend, isDanger, index }: any) => (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.4 }}
      className="glass-card p-5 flex flex-col justify-between group hover:border-primary/30 hover:shadow-[0_0_20px_rgba(56,189,248,0.1)] relative overflow-hidden bg-white/50 dark:bg-slate-900/40"
    >
      <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
        <Icon className="w-12 h-12 text-primary" />
      </div>
      <div className="flex justify-between items-start z-10">
        <div className="text-[10px] font-bold font-['Microsoft_YaHei'] text-muted-foreground tracking-widest uppercase">{title}</div>
        <Icon className={cn("w-4 h-4", isDanger ? 'text-destructive' : 'text-primary')} />
      </div>
      <div className="flex items-end justify-between mt-4 z-10">
         <div className="text-3xl font-mono font-bold text-foreground tracking-tighter">{value}</div>
         <div className={cn(
           "text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1",
           trend.includes('+') ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-100 dark:bg-slate-800 text-muted-foreground'
         )}>
            {trend}
         </div>
      </div>
    </motion.div>
  );

export const Dashboard: React.FC = () => {
  const [logIndex, setLogIndex] = useState(0);
  const [displayedLog, setDisplayedLog] = useState('');
  
  const fullLog = "";

  useEffect(() => {
    if (logIndex < fullLog.length) {
      const timeout = setTimeout(() => {
        setDisplayedLog(prev => prev + fullLog[logIndex]);
        setLogIndex(prev => prev + 1);
      }, 30);
      return () => clearTimeout(timeout);
    }
  }, [logIndex]);

  return (
    <div className="h-[calc(100vh-2rem)] w-full overflow-hidden bg-background text-foreground p-2 font-sans">
      {/* Bento Grid Container */}
      <div className="grid grid-cols-12 grid-rows-12 gap-4 h-full max-w-[1920px] mx-auto">
        
        {/* 1. Header & Stats (Top Row) */}
        <div className="col-span-12 row-span-2 grid grid-cols-4 gap-4">
          <StatCard title="文档处理总数" value="0" icon={FileText} trend="--%" index={0} />
          <StatCard title="风险检出" value="0" icon={AlertOctagon} trend="--" isDanger index={1} />
          <StatCard title="平均置信度" value="0%" icon={Zap} trend="--%" index={2} />
          <StatCard title="活跃智能体" value="0" icon={Activity} trend="待命" index={3} />
        </div>

        {/* 2. Process Visualization (Central Hub) */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="col-span-8 row-span-4 glass-card p-6 relative overflow-hidden group border-primary/20 bg-white/60 dark:bg-slate-900/40"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-primary/5 opacity-50"></div>
          
          <div className="relative z-10 h-full flex flex-col">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-xs font-bold font-['Microsoft_YaHei'] tracking-[0.2em] uppercase flex items-center gap-2 text-muted-foreground">
                <BrainCircuit size={16} className="text-primary"/>
                实时算力流
              </h3>
            </div>

            {/* The Stream Visualization */}
            <div className="flex-1 flex items-center justify-center px-12 relative w-full h-full">
               
               {/* Step 1: Ingestion */}
                <div className="flex flex-col items-center gap-4 group/step relative z-10 w-24">
                  <div className="w-16 h-16 rounded-2xl bg-white/50 dark:bg-slate-900/50 backdrop-blur border border-border flex items-center justify-center relative group-hover/step:-translate-y-2 transition-transform duration-500 shadow-lg">
                     <FileText className="text-muted-foreground group-hover/step:text-primary transition-colors" />
                     <div className="absolute -top-2 -right-2 bg-primary text-primary-foreground text-[10px] font-bold px-1.5 py-0.5 rounded-md shadow-md">0</div>
                  </div>
                  <span className="text-[10px] font-bold text-muted-foreground tracking-widest absolute -bottom-8 whitespace-nowrap">INGESTION</span>
               </div>

               <div className="flex-1 max-w-[120px] relative mx-2 h-20 flex flex-col justify-center gap-4 group-hover:bg-primary/5 rounded-lg transition-colors px-1">
                  {/* Line 1 - High Frequency Data */}
                  <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                     <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.5s_linear_infinite]"></div>
                     <div className="absolute inset-y-0 w-4 bg-primary/50 blur-[1px] animate-[flow-particle_1.5s_linear_infinite]"></div>
                  </div>
                  
                  {/* Line 2 - Main Data Bus */}
                  <div className="h-[3px] bg-primary/10 relative overflow-hidden w-full rounded-full">
                     <div className="absolute inset-y-0 w-16 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-beam_2s_linear_infinite] shadow-[0_0_10px_rgba(56,189,248,0.5)]"></div>
                     <div className="absolute inset-y-0 w-full bg-gradient-to-r from-transparent via-primary/20 to-transparent opacity-20"></div>
                  </div>
 
                  {/* Line 3 - Ack Signals */}
                  <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                     <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.5s_linear_infinite]"></div>
                     <div className="absolute inset-y-0 w-4 bg-primary/50 blur-[1px] animate-[flow-particle_1.5s_linear_infinite]"></div>
                  </div>
                </div>

               {/* Step 2: MAOA Core */}
                <div className="flex flex-col items-center gap-4 relative z-10 w-32">
                  <div className="w-24 h-24 rounded-full bg-white/80 dark:bg-slate-900/80 backdrop-blur border border-primary/30 shadow-[0_0_30px_rgba(56,189,248,0.15)] flex items-center justify-center relative animate-[float_4s_ease-in-out_infinite]">
                     <BrainCircuit className="w-10 h-10 text-primary drop-shadow-[0_0_10px_rgba(56,189,248,0.5)]" />
                     <div className="absolute inset-0 border border-primary rounded-full animate-ping opacity-20"></div>
                     <div className="absolute inset-0 border border-primary/50 rounded-full animate-[spin_10s_linear_infinite] opacity-30 border-t-transparent border-l-transparent"></div>
                  </div>
                  <span className="text-sm font-bold text-primary tracking-widest absolute -bottom-10 whitespace-nowrap">MAOA ENGINE</span>
               </div>

               <div className="flex-1 max-w-[120px] relative mx-2 h-20 flex flex-col justify-center gap-4 group-hover:bg-primary/5 rounded-lg transition-colors px-1">
                  {/* Line 1 */}
                  <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                     <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.8s_linear_infinite_0.2s]"></div>
                  </div>
                  
                  {/* Line 2 - Main Data Bus */}
                  <div className="h-[3px] bg-primary/10 relative overflow-hidden w-full rounded-full">
                     <div className="absolute inset-y-0 w-20 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-beam_2.2s_linear_infinite_0.5s] shadow-[0_0_10px_rgba(56,189,248,0.5)]"></div>
                     <div className="absolute inset-y-0 w-full bg-gradient-to-r from-transparent via-primary/20 to-transparent opacity-20"></div>
                  </div>
 
                  {/* Line 3 */}
                  <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                     <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.8s_linear_infinite_0.2s]"></div>
                  </div>
                </div>

               {/* Step 3: Structured Data */}
                <div className="flex flex-col items-center gap-4 group/step relative z-10 w-24">
                  <div className="w-16 h-16 rounded-2xl bg-white/50 dark:bg-slate-900/50 backdrop-blur border border-border flex items-center justify-center group-hover/step:-translate-y-2 transition-transform duration-500 delay-100 shadow-lg">
                     <Database className="text-emerald-500" />
                  </div>
                  <span className="text-[10px] font-bold text-muted-foreground tracking-widest absolute -bottom-8 whitespace-nowrap">STORAGE</span>
               </div>
            </div>
          </div>
        </motion.div>

        {/* 3. Risk Radar (Right Column) */}
        <motion.div 
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3, duration: 0.5 }}
          className="col-span-4 row-span-6 glass-card p-6 flex flex-col relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-destructive/5 rounded-full blur-3xl -z-10 pointer-events-none"></div>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-xs font-bold font-['Microsoft_YaHei'] text-muted-foreground uppercase tracking-[0.2em]">
              多维风险态势
            </h3>
            <Activity size={14} className="text-destructive/50" />
          </div>
          <div className="flex-1 min-h-0 -ml-4 relative">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart cx="50%" cy="50%" outerRadius="70%" data={dataRadar}>
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis 
                  dataKey="subject" 
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11, fontWeight: 600 }} 
                />
                <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                <Radar 
                  name="风险指数" 
                  dataKey="A" 
                  stroke="hsl(var(--destructive))" 
                  strokeWidth={2} 
                  fill="hsl(var(--destructive))" 
                  fillOpacity={0.3} 
                />
                <defs>
                  <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="hsl(var(--destructive))" stopOpacity={0.6}/>
                    <stop offset="95%" stopColor="hsl(var(--destructive))" stopOpacity={0.1}/>
                  </linearGradient>
                </defs>
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'rgba(15, 23, 42, 0.9)', 
                    borderColor: 'rgba(255,255,255,0.1)', 
                    color: 'white',
                    backdropFilter: 'blur(8px)',
                    borderRadius: '8px',
                    fontSize: '12px'
                  }} 
                  itemStyle={{ color: 'white' }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        {/* 4. Logs (Bottom Left) */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
          className="col-span-8 row-span-6 glass-card flex flex-col font-mono relative overflow-hidden border-t-2 border-t-primary/50 bg-white/50 dark:bg-slate-900/40"
        >
          <div className="h-10 border-b border-border bg-white/80 dark:bg-slate-900/50 flex items-center px-4 justify-between backdrop-blur-md">
             <div className="flex items-center gap-2">
                <Terminal className="w-3.5 h-3.5 text-primary animate-pulse" />
                <span className="text-[10px] font-bold text-muted-foreground tracking-widest">SYSTEM LOG</span>
             </div>

          </div>
          
          <div className="flex-1 p-4 overflow-hidden bg-slate-50 dark:bg-black/40 relative">
             <div className="absolute inset-0 bg-scanline opacity-5 pointer-events-none"></div>
             <div className="text-xs leading-relaxed text-slate-600 dark:text-slate-400 whitespace-pre-wrap font-mono typewriter">
               <span className="text-primary mr-2">➜</span>
               {displayedLog}
               <span className="inline-block w-2 h-4 bg-primary align-middle ml-1 animate-pulse"></span>
             </div>
          </div>
        </motion.div>

        {/* 5. Upload Mini (Bottom Right) */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.5, duration: 0.5 }}
          className="col-span-4 row-span-4 glass-card p-1 relative group cursor-pointer hover:border-primary/50 transition-all duration-300 bg-white/80 dark:bg-slate-900/40 dark:border-slate-800"
        >
          <div className="h-full w-full border-2 border-dashed border-slate-300 dark:border-slate-800 rounded-lg flex flex-col items-center justify-center bg-transparent hover:bg-primary/5 transition-colors">
             <div className="p-4 bg-primary/10 rounded-full mb-4 shadow-sm group-hover:shadow-[0_0_20px_rgba(56,189,248,0.2)] group-hover:scale-110 transition-all duration-300 border border-primary/20">
                <UploadCloud className="w-8 h-8 text-primary/70 group-hover:text-primary transition-colors animate-bounce" />
             </div>
             <h3 className="text-sm font-bold text-foreground tracking-wider uppercase">Quick Upload</h3>
             <p className="text-[10px] text-muted-foreground mt-1 font-bold">Drag & Drop supported</p>
          </div>
        </motion.div>

      </div>
    </div>
  );
};
