import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Database,
  FileSearch,
  FileText,
  ShieldCheck,
  Sparkles,
  User,
} from 'lucide-react';

import { cn } from '../../lib/utils';
import type { AuthUser } from '../../shared/api/auth';
import ImageModule1 from '../../assets/模块一.png';
import ImageModule2 from '../../assets/模块二.png';
import ImageModule3 from '../../assets/模块三.png';
import {
  readExtractionDocuments,
  readExtractionUpdatedAt,
  subscribeExtractionUpdates,
  type ExtractionDocument,
  type ExtractionEntity,
} from '../../shared/state/extractionDocuments';

type MobileDashboardAction = 'deepread_extraction' | 'fusion' | 'guide' | 'doc-processing';

type MobileDashboardProps = {
  user: AuthUser;
  onNavigate: (target: MobileDashboardAction) => void;
};

type MetricCard = {
  label: string;
  value: string;
  helper: string;
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  tone: 'blue' | 'amber' | 'emerald' | 'slate';
};

const toneClassMap: Record<MetricCard['tone'], string> = {
  blue: 'bg-blue-50 text-blue-500 dark:bg-blue-500/20 dark:text-blue-300',
  amber: 'bg-amber-50 text-amber-500 dark:bg-amber-500/20 dark:text-amber-300',
  emerald: 'bg-emerald-50 text-emerald-500 dark:bg-emerald-500/20 dark:text-emerald-300',
  slate: 'bg-slate-50 text-slate-500 dark:bg-slate-500/20 dark:text-slate-300',
};

const averageConfidence = (documents: ExtractionDocument[]): number => {
  const entities: ExtractionEntity[] = [];
  documents.forEach((doc) => {
    Object.values(doc.result || {}).forEach((entity) => entities.push(entity));
  });
  if (entities.length === 0) return 0;
  const total = entities.reduce((acc, entity) => acc + Number(entity.confidence || 0), 0);
  return Math.round((total / entities.length) * 100);
};

export const MobileDashboard: React.FC<MobileDashboardProps> = ({
  user,
  onNavigate,
}) => {
  const [documents, setDocuments] = useState<ExtractionDocument[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [activeCardIndex, setActiveCardIndex] = useState(0);

  const handleScroll = useCallback(() => {
    if (!scrollContainerRef.current) return;
    const scrollLeft = scrollContainerRef.current.scrollLeft;
    const cardWidth = 310; // 300px width + 10px gap
    const newIndex = Math.round(scrollLeft / cardWidth);
    setActiveCardIndex(Math.max(0, Math.min(newIndex, 2)));
  }, []);

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    let interval: NodeJS.Timeout;
    const play = () => {
      interval = setInterval(() => {
        setActiveCardIndex((prev) => {
          const next = (prev + 1) % 3;
          const cardWidth = 310;
          container.scrollTo({
            left: next * cardWidth,
            behavior: 'smooth'
          });
          return next;
        });
      }, 4000);
    };

    play();

    const pause = () => clearInterval(interval);

    container.addEventListener('touchstart', pause, { passive: true });
    container.addEventListener('touchend', play, { passive: true });
    container.addEventListener('mouseenter', pause);
    container.addEventListener('mouseleave', play);

    return () => {
      clearInterval(interval);
      container.removeEventListener('touchstart', pause);
      container.removeEventListener('touchend', play);
      container.removeEventListener('mouseenter', pause);
      container.removeEventListener('mouseleave', play);
    };
  }, []);

  useEffect(() => {
    const load = () => {
      setDocuments(readExtractionDocuments());
      setUpdatedAt(readExtractionUpdatedAt());
    };
    load();
    return subscribeExtractionUpdates(load);
  }, []);

  const docCount = documents.length;
  const errorCount = documents.filter((item) => item.errors.length > 0).length;
  const confidence = averageConfidence(documents);
  const totalFieldCount = documents.reduce((acc, item) => acc + Object.keys(item.result || {}).length, 0);
  const recentDocs = documents.slice(0, 3);
  const latestUpdatedLabel = updatedAt ? new Date(updatedAt).toLocaleString() : '暂无';

  const metrics = useMemo<MetricCard[]>(
    () => [
      {
        label: '已解析文档',
        value: String(docCount),
        helper: docCount > 0 ? '包含最近一次抽取结果' : '还没有解析记录',
        icon: FileText,
        tone: 'blue',
      },
      {
        label: '待复核任务',
        value: String(errorCount),
        helper: errorCount > 0 ? '存在异常或警告，建议人工复查' : '当前没有异常任务',
        icon: AlertTriangle,
        tone: 'amber',
      },
      {
        label: '平均置信度',
        value: `${confidence}%`,
        helper: confidence > 0 ? '来自当前字段抽取结果' : '上传文档后即可生成',
        icon: BarChart3,
        tone: 'emerald',
      },
      {
        label: '累计字段数',
        value: String(totalFieldCount),
        helper: '字段、表格与图片产物会同步沉淀',
        icon: Database,
        tone: 'slate',
      },
    ],
    [confidence, docCount, errorCount, totalFieldCount],
  );

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="-mb-28 relative flex min-h-[calc(100dvh-4.5rem)] flex-col overflow-hidden bg-[#F8FAFC] font-sans dark:bg-slate-950"
    >
      {/* Impeccable Ambient Background Glow */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.5] mix-blend-multiply dark:opacity-[0.15] dark:mix-blend-normal bg-[radial-gradient(circle_at_1px_1px,_rgba(15,23,42,0.06)_1px,_transparent_0)] dark:bg-[radial-gradient(circle_at_1px_1px,_rgba(255,255,255,0.06)_1px,_transparent_0)] bg-[length:24px_24px]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[600px] bg-[radial-gradient(ellipse_100%_100%_at_top_center,_var(--tw-gradient-stops))] from-cyan-100/60 via-cyan-50/20 to-transparent dark:from-cyan-900/20 dark:via-cyan-950/5" />
      <motion.div 
        animate={{ opacity: [0.6, 1, 0.6], scale: [1, 1.05, 1] }}
        transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        className="pointer-events-none absolute -left-[20%] top-[-10%] h-[400px] w-[600px] rounded-full bg-cyan-200/20 blur-[80px] dark:bg-cyan-900/20" 
      />
      <motion.div 
        animate={{ opacity: [0.5, 0.8, 0.5], scale: [1, 1.05, 1] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", delay: 2 }}
        className="pointer-events-none absolute -right-[20%] top-[10%] h-[300px] w-[500px] rounded-full bg-sky-200/20 blur-[80px] dark:bg-sky-900/10" 
      />
      <div className="pointer-events-none absolute bottom-[10%] left-[20%] h-[400px] w-[500px] rounded-full bg-blue-200/10 blur-[100px] dark:bg-blue-900/10" />

      <div className="relative z-10 px-5 pb-6 pt-[max(1.5rem,env(safe-area-inset-top))]">
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h1 className="text-[20px] font-black tracking-tight text-[#11323B] dark:text-white">
              早上好，{user?.name || 'Reader'}
            </h1>
            <span className="text-[18px] leading-none">👋</span>
          </div>
        </div>

        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="-mx-5 flex snap-x gap-2.5 overflow-x-auto px-5 pb-0 pt-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]"
        >
          <article
            onClick={() => onNavigate('doc-processing')}
            className="group relative flex h-[260px] w-[290px] shrink-0 snap-center flex-col overflow-hidden rounded-[24px] bg-white shadow-[0_8px_32px_rgba(15,23,42,0.04)] ring-1 ring-slate-100 active:scale-[0.98] transition-all duration-300 dark:bg-slate-800/80 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)] dark:ring-white/[0.05]"
          >
            <div className="absolute inset-x-0 top-0 h-[185px] overflow-hidden bg-[#D4F4F6] dark:bg-cyan-950/30">
              <img src={ImageModule1} alt="智能文档解析" className="h-full w-full object-cover object-bottom transition-transform duration-500 group-hover:scale-105" />
              {/* Subtle gradient to blend image into the white bottom area */}
              <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white to-transparent dark:from-slate-800/80" />
            </div>
            
            <div className="relative z-10 mt-auto flex items-center justify-between px-5 pb-5 pt-3">
              <div className="flex flex-col justify-center">
                <h2 className="text-[18px] font-bold leading-tight tracking-tight text-slate-900 dark:text-white">
                  AI文档处理
                </h2>
                <p className="mt-1 text-[12px] font-medium text-slate-500 dark:text-slate-400">
                  语义驱动，智能编辑
                </p>
              </div>
              <div className="flex shrink-0 items-center justify-center">
                <div className="inline-flex h-[32px] items-center justify-center rounded-full bg-slate-900 px-4 text-[13px] font-semibold text-white shadow-md shadow-slate-900/10 transition-colors group-hover:bg-cyan-600 dark:bg-cyan-500 dark:text-slate-900 dark:shadow-cyan-500/20 dark:group-hover:bg-cyan-400">
                  立即处理
                </div>
              </div>
            </div>
          </article>

          <article
            onClick={() => onNavigate('deepread_extraction')}
            className="group relative flex h-[260px] w-[290px] shrink-0 snap-center flex-col overflow-hidden rounded-[24px] bg-white shadow-[0_8px_32px_rgba(15,23,42,0.04)] ring-1 ring-slate-100 active:scale-[0.98] transition-all duration-300 dark:bg-slate-800/80 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)] dark:ring-white/[0.05]"
          >
            <div className="absolute inset-x-0 top-0 h-[185px] overflow-hidden bg-[#EAF5FD] dark:bg-sky-950/30">
              <img src={ImageModule2} alt="AI信息提取" className="h-full w-full object-cover object-bottom transition-transform duration-500 group-hover:scale-105" />
              <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white to-transparent dark:from-slate-800/80" />
            </div>

            <div className="relative z-10 mt-auto flex items-center justify-between px-5 pb-5 pt-3">
              <div className="flex flex-col justify-center">
                <h2 className="text-[18px] font-bold leading-tight tracking-tight text-slate-900 dark:text-white">
                  AI信息提取
                </h2>
                <p className="mt-1 text-[12px] font-medium text-slate-500 dark:text-slate-400">
                  深度解析，零误提取
                </p>
              </div>
              <div className="flex shrink-0 items-center justify-center">
                <div className="inline-flex h-[32px] items-center justify-center rounded-full bg-slate-900 px-4 text-[13px] font-semibold text-white shadow-md shadow-slate-900/10 transition-colors group-hover:bg-sky-600 dark:bg-sky-500 dark:text-slate-900 dark:shadow-sky-500/20 dark:group-hover:bg-sky-400">
                  立即提取
                </div>
              </div>
            </div>
          </article>

          <article
            onClick={() => onNavigate('fusion')}
            className="group relative flex h-[260px] w-[290px] shrink-0 snap-center flex-col overflow-hidden rounded-[24px] bg-white shadow-[0_8px_32px_rgba(15,23,42,0.04)] ring-1 ring-slate-100 active:scale-[0.98] transition-all duration-300 dark:bg-slate-800/80 dark:shadow-[0_8px_32px_rgba(0,0,0,0.2)] dark:ring-white/[0.05]"
          >
            <div className="absolute inset-x-0 top-0 h-[185px] overflow-hidden bg-[#F5F1FD] dark:bg-indigo-950/30">
              <img src={ImageModule3} alt="自定义智能填表" className="h-full w-full object-cover object-bottom transition-transform duration-500 group-hover:scale-105" />
              <div className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white to-transparent dark:from-slate-800/80" />
            </div>

            <div className="relative z-10 mt-auto flex items-center justify-between px-5 pb-5 pt-3">
              <div className="flex flex-col justify-center">
                <h2 className="text-[18px] font-bold leading-tight tracking-tight text-slate-900 dark:text-white">
                  自定义智能填表
                </h2>
                <p className="mt-1 text-[12px] font-medium text-slate-500 dark:text-slate-400">
                  按需抽取，自动填表
                </p>
              </div>
              <div className="flex shrink-0 items-center justify-center">
                <div className="inline-flex h-[32px] items-center justify-center rounded-full bg-slate-900 px-4 text-[13px] font-semibold text-white shadow-md shadow-slate-900/10 transition-colors group-hover:bg-indigo-500 dark:bg-indigo-500 dark:text-slate-900 dark:shadow-indigo-500/20 dark:group-hover:bg-indigo-400">
                  立即填表
                </div>
              </div>
            </div>
          </article>
        </div>
      </div>

      <motion.div 
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
        className="-mt-2 flex-1 rounded-t-[32px] bg-white/95 px-4 pb-32 pt-6 shadow-[0_-4px_24px_rgba(0,0,0,0.02)] backdrop-blur-2xl dark:bg-slate-900/95"
      >
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-[16px] font-bold text-[#11323B] dark:text-slate-100">最近处理文档</h3>
            <button type="button" onClick={() => onNavigate('deepread_extraction')} className="flex items-center gap-1 text-[13px] font-semibold text-[#64748B] transition-colors hover:text-[#11323B] dark:text-slate-400 dark:hover:text-slate-200">
              全部历史 <ArrowRight size={14} />
            </button>
          </div>

          {recentDocs.length === 0 ? (
            <div className="mt-2 flex w-full flex-col items-center justify-center rounded-[24px] border-2 border-dashed border-slate-200/60 bg-slate-50/50 py-14 text-center dark:border-slate-700/60 dark:bg-slate-800/20">
              <div className="mb-4 flex h-[60px] w-[60px] items-center justify-center rounded-[18px] bg-white shadow-[0_8px_30px_rgba(6,182,212,0.15)] ring-1 ring-slate-100 dark:bg-slate-800 dark:shadow-[0_8px_30px_rgba(6,182,212,0.08)] dark:ring-slate-700">
                <FileText size={28} className="text-cyan-500 dark:text-cyan-400" strokeWidth={1.5} />
              </div>
              <p className="text-[15px] font-bold text-[#11323B] dark:text-slate-200">还没有解析文档</p>
              <p className="mt-1.5 max-w-[220px] text-[13px] leading-relaxed text-[#64748B] dark:text-slate-400">
                上传文件后，这里会展示最近的解析结果摘要
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {recentDocs.map((doc, index) => {
                const hasError = doc.errors.length > 0;
                const ext = doc.file_name.split('.').pop()?.toLowerCase() || '';
                const iconSrc = ['doc', 'docx'].includes(ext)
                  ? '/assets/WORD.png'
                  : ['xls', 'xlsx'].includes(ext)
                    ? '/assets/xlsx.png'
                    : ext === 'pdf'
                      ? '/assets/pdf.png'
                      : '/assets/txt.png';
                const iconBgColor = ['doc', 'docx'].includes(ext)
                  ? 'bg-blue-50 dark:bg-blue-500/10'
                  : ['xls', 'xlsx'].includes(ext)
                    ? 'bg-green-50 dark:bg-green-500/10'
                    : ext === 'pdf'
                      ? 'bg-red-50 dark:bg-red-500/10'
                      : 'bg-slate-50 dark:bg-slate-500/10';

                return (
                  <div key={doc.file_hash}>
                    <button type="button" onClick={() => onNavigate('deepread_extraction')} className="group flex w-full items-center justify-between text-left active:scale-[0.98] transition-transform">
                      <div className="flex items-center gap-3">
                        <div className={cn('flex h-12 w-12 shrink-0 items-center justify-center rounded-full shadow-sm', iconBgColor)}>
                          <img src={iconSrc} alt={ext} className="h-6 w-6 object-contain drop-shadow-sm" />
                        </div>
                        <div className="flex min-w-0 flex-col items-start">
                          <p className="line-clamp-1 text-[15px] font-bold text-[#11323B] group-hover:text-blue-600 transition-colors dark:text-slate-100 dark:group-hover:text-blue-400">{doc.file_name}</p>
                          <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] font-medium text-[#64748B] dark:text-slate-400">
                            <span>{Object.keys(doc.result || {}).length} 个字段</span>
                            <span className="text-slate-300 dark:text-slate-600">|</span>
                            <span>{doc.cached ? '缓存命中' : '解析成功'}</span>
                            {hasError && (
                              <>
                                <span className="text-slate-300 dark:text-slate-600">|</span>
                                <span className="inline-flex items-center gap-1 text-amber-500">
                                  <AlertTriangle size={12} />
                                  异常
                                </span>
                              </>
                            )}
                          </p>
                        </div>
                      </div>
                      <ArrowRight size={18} strokeWidth={2.5} className="shrink-0 text-slate-300 transition-colors group-hover:text-[#11323B] dark:text-slate-600 dark:group-hover:text-slate-400" />
                    </button>
                    {/* Divider */}
                    {index < recentDocs.length - 1 && (
                      <div className="ml-[60px] mt-4 h-px border-b border-dashed border-slate-200 dark:border-slate-800" />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </motion.div>
    </motion.div>
  );
};
