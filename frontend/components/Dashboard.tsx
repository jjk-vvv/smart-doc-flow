import React, { useEffect, useMemo, useState } from "react";
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip } from "recharts";
import { UploadCloud, FileText, Activity, AlertOctagon, Terminal, Zap, BrainCircuit } from "lucide-react";
import { motion } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  readExtractionDocuments,
  readExtractionUpdatedAt,
  subscribeExtractionUpdates,
  type ExtractionDocument,
  type ExtractionEntity,
} from "../lib/extractionStore";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type StatCardProps = {
  title: string;
  value: string;
  icon: React.ElementType;
  trend: string;
  isDanger?: boolean;
  index: number;
};

const StatCard: React.FC<StatCardProps> = ({ title, value, icon: Icon, trend, isDanger, index }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay: index * 0.08, duration: 0.35 }}
    className="glass-card p-5 flex flex-col justify-between group hover:border-primary/30 hover:shadow-[0_0_20px_rgba(56,189,248,0.1)] relative overflow-hidden bg-white/50 dark:bg-slate-900/40"
  >
    <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
      <Icon className="w-12 h-12 text-primary" />
    </div>
    <div className="flex justify-between items-start z-10">
      <div className="text-[10px] font-bold font-['Microsoft_YaHei'] text-muted-foreground dark:text-white tracking-widest uppercase">{title}</div>
      <Icon className={cn("w-4 h-4", isDanger ? "text-destructive" : "text-primary")} />
    </div>
    <div className="flex items-end justify-between mt-4 z-10">
      <div className="text-3xl font-mono font-bold text-foreground tracking-tighter">{value}</div>
      <div
        className={cn(
          "text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1",
          trend.startsWith("+") ? "bg-emerald-500/10 text-emerald-500" : "bg-slate-100 dark:bg-slate-800 text-muted-foreground"
        )}
      >
        {trend}
      </div>
    </div>
  </motion.div>
);

const averageConfidence = (documents: ExtractionDocument[]): number => {
  const entities: ExtractionEntity[] = [];
  for (const doc of documents) {
    for (const value of Object.values(doc.result || {})) {
      entities.push(value);
    }
  }
  if (entities.length === 0) return 0;
  const sum = entities.reduce((acc, item) => acc + Number(item.confidence || 0), 0);
  return Math.round((sum / entities.length) * 100);
};

const buildRadarData = (documents: ExtractionDocument[]) => {
  if (documents.length === 0) {
    return [
      { subject: "完整性", A: 0 },
      { subject: "置信度", A: 0 },
      { subject: "可追溯性", A: 0 },
      { subject: "缓存命中", A: 0 },
      { subject: "吞吐量", A: 0 },
    ];
  }

  const docCount = documents.length;
  const noErrorCount = documents.filter((d) => d.errors.length === 0).length;
  const cachedCount = documents.filter((d) => d.cached).length;
  const allEntities = documents.flatMap((d) => Object.values(d.result || {}));
  const traceable = allEntities.filter((e) => Boolean(e.source_ref_id)).length;
  const traceability = allEntities.length === 0 ? 0 : Math.round((traceable / allEntities.length) * 100);

  return [
    { subject: "完整性", A: Math.round((noErrorCount / docCount) * 100) },
    { subject: "置信度", A: averageConfidence(documents) },
    { subject: "可追溯性", A: traceability },
    { subject: "缓存命中", A: Math.round((cachedCount / docCount) * 100) },
    { subject: "吞吐量", A: Math.min(100, docCount * 20) },
  ];
};

const buildLogText = (documents: ExtractionDocument[], updatedAt: string | null): string => {
  const at = updatedAt ? new Date(updatedAt).toLocaleString() : "--";
  if (documents.length === 0) {
    return `[${at}] Waiting for extraction payload...\nNo documents have been extracted yet.`;
  }

  const lines: string[] = [];
  lines.push(`[${at}] Loaded ${documents.length} extracted documents.`);
  for (const doc of documents.slice(0, 6)) {
    const fieldCount = Object.keys(doc.result || {}).length;
    const errCount = doc.errors.length;
    lines.push(
      `- ${doc.file_name} | track=${doc.track} | fields=${fieldCount} | errors=${errCount} | cached=${doc.cached ? "yes" : "no"}`
    );
  }
  if (documents.length > 6) {
    lines.push(`... and ${documents.length - 6} more documents.`);
  }
  return lines.join("\n");
};

export const Dashboard: React.FC = () => {
  const [documents, setDocuments] = useState<ExtractionDocument[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [logIndex, setLogIndex] = useState(0);
  const [displayedLog, setDisplayedLog] = useState("");

  useEffect(() => {
    const load = () => {
      setDocuments(readExtractionDocuments());
      setUpdatedAt(readExtractionUpdatedAt());
    };
    load();
    return subscribeExtractionUpdates(load);
  }, []);

  const fullLog = useMemo(() => buildLogText(documents, updatedAt), [documents, updatedAt]);
  const radarData = useMemo(() => buildRadarData(documents), [documents]);

  const errorCount = useMemo(() => documents.filter((d) => d.errors.length > 0).length, [documents]);
  const avgConfidence = useMemo(() => averageConfidence(documents), [documents]);
  const activeAgents = useMemo(() => {
    if (documents.length === 0) return 0;
    const resultCount = documents.reduce((acc, d) => acc + Object.keys(d.result || {}).length, 0);
    return Math.max(1, Math.min(6, Math.ceil(resultCount / 6)));
  }, [documents]);

  useEffect(() => {
    setLogIndex(0);
    setDisplayedLog("");
  }, [fullLog]);

  useEffect(() => {
    if (logIndex < fullLog.length) {
      const timeout = setTimeout(() => {
        setDisplayedLog((prev) => prev + fullLog[logIndex]);
        setLogIndex((prev) => prev + 1);
      }, 8);
      return () => clearTimeout(timeout);
    }
    return undefined;
  }, [fullLog, logIndex]);

  const trendDocs = documents.length > 0 ? `+${documents.length}` : "--";
  const trendRisk = errorCount > 0 ? `+${errorCount}` : "--";
  const trendConf = avgConfidence > 0 ? `+${avgConfidence}%` : "--";
  const trendAgents = activeAgents > 0 ? `+${activeAgents}` : "--";

  return (
    <div className="h-[calc(100vh-2rem)] w-full overflow-hidden bg-background text-foreground p-2 font-sans">
      <div className="grid grid-cols-12 grid-rows-12 gap-4 h-full max-w-[1920px] mx-auto">
        <div className="col-span-12 row-span-2 grid grid-cols-4 gap-4">
          <StatCard title="已处理文档" value={String(documents.length)} icon={FileText} trend={trendDocs} index={0} />
          <StatCard title="异常文档" value={String(errorCount)} icon={AlertOctagon} trend={trendRisk} isDanger index={1} />
          <StatCard title="平均置信度" value={`${avgConfidence}%`} icon={Zap} trend={trendConf} index={2} />
          <StatCard title="活跃智能体" value={String(activeAgents)} icon={Activity} trend={trendAgents} index={3} />
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.45 }}
          className="col-span-8 row-span-4 glass-card p-6 relative overflow-hidden group border-primary/20 bg-white/60 dark:bg-slate-900/40"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-primary/5 opacity-50" />
          <div className="relative z-10 h-full flex flex-col">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-xs font-bold font-['Microsoft_YaHei'] tracking-[0.2em] uppercase flex items-center gap-2 text-muted-foreground">
                <BrainCircuit size={16} className="text-primary" />
                运行时流水线
              </h3>
            </div>
            <div className="flex-1 flex items-center justify-center px-12 relative w-full h-full">
              <div className="flex flex-col items-center gap-4 group/step relative z-10 w-24">
                <div className="w-16 h-16 rounded-2xl bg-white/50 dark:bg-slate-900/50 backdrop-blur border border-border flex items-center justify-center relative group-hover/step:-translate-y-2 transition-transform duration-500 shadow-lg">
                  <FileText className="text-muted-foreground group-hover/step:text-primary transition-colors" />
                  <div className="absolute -top-2 -right-2 bg-primary text-primary-foreground text-[10px] font-bold px-1.5 py-0.5 rounded-md shadow-md">
                    {documents.length}
                  </div>
                </div>
                <span className="text-[10px] font-bold font-['Microsoft_YaHei'] text-muted-foreground tracking-widest absolute -bottom-8 whitespace-nowrap">数据摄入</span>
              </div>
              <div className="flex-1 max-w-[120px] relative mx-2 h-20 flex flex-col justify-center gap-4 px-1">
                <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                  <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.5s_linear_infinite]" />
                </div>
                <div className="h-[3px] bg-primary/10 relative overflow-hidden w-full rounded-full">
                  <div className="absolute inset-y-0 w-16 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-beam_2s_linear_infinite] shadow-[0_0_10px_rgba(56,189,248,0.5)]" />
                </div>
                <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                  <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.5s_linear_infinite]" />
                </div>
              </div>
              <div className="flex flex-col items-center gap-4 relative z-10 w-32">
                <div className="w-24 h-24 rounded-full bg-white/80 dark:bg-slate-900/80 backdrop-blur border border-primary/30 shadow-[0_0_30px_rgba(56,189,248,0.15)] flex items-center justify-center relative animate-[float_4s_ease-in-out_infinite]">
                  <BrainCircuit className="w-10 h-10 text-primary drop-shadow-[0_0_10px_rgba(56,189,248,0.5)]" />
                  <div className="absolute inset-0 border border-primary rounded-full animate-ping opacity-20" />
                </div>
                <span className="text-sm font-bold font-['Microsoft_YaHei'] text-primary tracking-widest absolute -bottom-10 whitespace-nowrap">MAOA 引擎</span>
              </div>
              <div className="flex-1 max-w-[120px] relative mx-2 h-20 flex flex-col justify-center gap-4 px-1">
                <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                  <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.8s_linear_infinite_0.2s]" />
                </div>
                <div className="h-[3px] bg-primary/10 relative overflow-hidden w-full rounded-full">
                  <div className="absolute inset-y-0 w-20 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-beam_2.2s_linear_infinite_0.5s] shadow-[0_0_10px_rgba(56,189,248,0.5)]" />
                </div>
                <div className="h-[1px] bg-primary/10 relative overflow-hidden w-full">
                  <div className="absolute inset-y-0 w-8 bg-gradient-to-r from-transparent via-primary to-transparent animate-[flow-particle_1.8s_linear_infinite_0.2s]" />
                </div>
              </div>
              <div className="flex flex-col items-center gap-4 group/step relative z-10 w-24">
                <div className="w-16 h-16 rounded-2xl bg-white/50 dark:bg-slate-900/50 backdrop-blur border border-border flex items-center justify-center group-hover/step:-translate-y-2 transition-transform duration-500 delay-100 shadow-lg">
                  <Activity className="text-emerald-500" />
                </div>
                <span className="text-[10px] font-bold font-['Microsoft_YaHei'] text-muted-foreground tracking-widest absolute -bottom-8 whitespace-nowrap">智能洞察</span>
              </div>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.25, duration: 0.45 }}
          className="col-span-4 row-span-6 glass-card p-6 flex flex-col relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-destructive/5 rounded-full blur-3xl -z-10 pointer-events-none" />
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-xs font-bold font-['Microsoft_YaHei'] text-muted-foreground uppercase tracking-[0.2em]">质量雷达</h3>
            <Activity size={14} className="text-destructive/50" />
          </div>
          <div className="flex-1 min-h-0 -ml-4 relative">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                <PolarGrid stroke="var(--border)" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11, fontWeight: 600, fontFamily: "Microsoft YaHei" }} />
                <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                <Radar name="Index" dataKey="A" stroke="hsl(var(--destructive))" strokeWidth={2} fill="hsl(var(--destructive))" fillOpacity={0.3} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.9)",
                    borderColor: "rgba(255,255,255,0.1)",
                    color: "white",
                    backdropFilter: "blur(8px)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                  itemStyle={{ color: "white" }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.45 }}
          className="col-span-8 row-span-6 glass-card flex flex-col font-mono relative overflow-hidden border-t-2 border-t-primary/50 bg-white/50 dark:bg-slate-900/40"
        >
          <div className="h-10 border-b border-border bg-white/80 dark:bg-slate-900/50 flex items-center px-4 justify-between backdrop-blur-md">
            <div className="flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5 text-primary animate-pulse" />
              <span className="text-[10px] font-bold font-['Microsoft_YaHei'] text-muted-foreground tracking-widest">系统日志</span>
            </div>
          </div>
          <div className="flex-1 p-4 overflow-hidden bg-slate-50 dark:bg-black/40 relative">
            <div className="absolute inset-0 bg-scanline opacity-5 pointer-events-none" />
            <div className="text-xs leading-relaxed text-slate-600 dark:text-slate-400 whitespace-pre-wrap font-mono typewriter">
              <span className="text-primary mr-2">{">"}</span>
              {displayedLog}
              <span className="inline-block w-2 h-4 bg-primary align-middle ml-1 animate-pulse" />
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.35, duration: 0.45 }}
          className="col-span-4 row-span-4 glass-card p-1 relative group cursor-pointer hover:border-primary/50 transition-all duration-300 bg-white/80 dark:bg-slate-900/40 dark:border-slate-800"
        >
          <div className="h-full w-full border-2 border-dashed border-slate-300 dark:border-slate-800 rounded-lg flex flex-col items-center justify-center bg-transparent hover:bg-primary/5 transition-colors">
            <div className="p-4 bg-primary/10 rounded-full mb-4 shadow-sm group-hover:shadow-[0_0_20px_rgba(56,189,248,0.2)] group-hover:scale-110 transition-all duration-300 border border-primary/20">
              <UploadCloud className="w-8 h-8 text-primary/70 group-hover:text-primary transition-colors animate-bounce" />
            </div>
            <h3 className="text-sm font-bold font-['Microsoft_YaHei'] text-foreground tracking-wider uppercase">快速上传</h3>
            <p className="text-[10px] text-muted-foreground mt-1 font-bold font-['Microsoft_YaHei']">使用深度解析以刷新指标</p>
          </div>
        </motion.div>
      </div>
    </div>
  );
};
