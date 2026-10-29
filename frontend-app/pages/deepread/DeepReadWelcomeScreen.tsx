import React from 'react';
import { UploadCloud, FileText, Zap, Shield } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '../../lib/utils';

const useTypewriter = (text: string, speed: number = 50, delay: number = 0) => {
    const [displayedText, setDisplayedText] = React.useState('');
    const [started, setStarted] = React.useState(false);
    const [completed, setCompleted] = React.useState(false);

    React.useEffect(() => {
        const startTimer = setTimeout(() => setStarted(true), delay);
        return () => clearTimeout(startTimer);
    }, [delay]);

    React.useEffect(() => {
        if (!started) return;
        let i = 0;
        const timer = setInterval(() => {
            if (i <= text.length) {
                setDisplayedText(text.slice(0, i));
                i++;
            } else {
                setCompleted(true);
                clearInterval(timer);
            }
        }, speed);
        return () => clearInterval(timer);
    }, [text, speed, started]);

    return { displayedText, completed, started };
};

interface DeepReadWelcomeScreenProps {
    onUploadClick: () => void;
    onDragEnter: (e: React.DragEvent) => void;
    onDragOver: (e: React.DragEvent) => void;
    onDragLeave: (e: React.DragEvent) => void;
    onDrop: (e: React.DragEvent) => void;
    isUploaderDragOver: boolean;
}

export const DeepReadWelcomeScreen: React.FC<DeepReadWelcomeScreenProps> = ({
    onUploadClick,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
    isUploaderDragOver
}) => {
    const { displayedText: titleText, completed: titleCompleted } = useTypewriter("非结构化文档智能信息抽取", 80, 600);
    const { displayedText: subtitleText, completed: subtitleCompleted } = useTypewriter("基于大模型的深度阅读与分析工作台。支持多文档对比、结构化信息提取、智能问答协同，帮助您快速洞察文档核心价值。", 40, 1500);

    return (
        <div className="relative flex h-full w-full flex-col items-center justify-center bg-slate-50/50 dark:bg-transparent p-6 overflow-hidden">
            {/* Center glow for dark mode to reduce overall darkness */}
            <div className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[70%] h-[70%] bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.04)_0%,transparent_70%)] hidden dark:block rounded-full blur-[80px]" />
            
            <div className="pointer-events-none absolute inset-0 hidden dark:block bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.08)_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_100%_80%_at_50%_50%,#000_70%,transparent_100%)] opacity-100" />
            <div className="pointer-events-none absolute inset-0 block dark:hidden bg-[radial-gradient(circle_at_center,rgba(0,0,0,0.03)_1px,transparent_1px)] bg-[size:24px_24px] [mask-image:radial-gradient(ellipse_80%_60%_at_50%_40%,#000_70%,transparent_100%)] opacity-80" />

            <div className="pointer-events-none absolute inset-0 overflow-hidden flex items-center justify-center">
                <motion.div 
                    animate={{ scale: [1, 1.05, 1], x: [0, 20, 0], y: [0, 15, 0] }}
                    transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute top-[-15%] left-[-5%] w-[45%] h-[45%] rounded-full bg-blue-500/10 blur-[100px] dark:bg-blue-400/20" 
                />
                <motion.div 
                    animate={{ scale: [1, 1.1, 1], x: [0, -30, 0], y: [0, -20, 0] }}
                    transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute bottom-[-15%] right-[-5%] w-[45%] h-[45%] rounded-full bg-indigo-500/10 blur-[100px] dark:bg-indigo-400/20" 
                />
                <motion.div 
                    animate={{ opacity: [0.4, 0.7, 0.4], scale: [1, 1.02, 1] }}
                    transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute top-[5%] left-[50%] -translate-x-1/2 w-[50%] h-[50%] bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-blue-300/30 via-transparent to-transparent dark:from-blue-300/25 dark:via-transparent dark:to-transparent blur-[80px]" 
                />
            </div>

            <div className="relative z-10 w-full max-w-5xl mx-auto flex flex-col items-center text-center mt-[-4vh]">
                <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}>
                    <h1 className="mb-4 text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-slate-900 via-blue-600 to-slate-900 dark:from-white dark:via-blue-300 dark:to-white bg-[length:200%_auto] animate-text-shimmer sm:text-4xl drop-shadow-sm dark:drop-shadow-[0_4px_24px_rgba(255,255,255,0.1)] min-h-[40px] sm:min-h-[48px] flex items-center justify-center">
                        {titleText}
                        <span className={cn("inline-block w-1 h-8 sm:h-9 ml-1 bg-slate-800 dark:bg-blue-300", titleCompleted ? "hidden" : "animate-pulse")} />
                    </h1>
                    <p className="mb-10 max-w-2xl mx-auto text-[15px] text-slate-600 dark:text-slate-200 leading-relaxed font-normal min-h-[44px]">
                        {subtitleText}
                        {titleCompleted && !subtitleCompleted && (
                            <span className="inline-block w-0.5 h-4 ml-0.5 bg-slate-500 dark:bg-slate-200 animate-pulse align-middle" />
                        )}
                    </p>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, y: 30, scale: 0.95, filter: "blur(12px)" }}
                    animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
                    transition={{ duration: 2.4, delay: 2.4, ease: [0.22, 1, 0.36, 1] }}
                    onClick={onUploadClick}
                    onDragEnter={onDragEnter}
                    onDragOver={onDragOver}
                    onDragLeave={onDragLeave}
                    onDrop={onDrop}
                    className={cn(
                        "group relative flex w-full max-w-2xl select-none cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[24px] border border-slate-200/80 bg-white/40 py-10 transition-all duration-300 ease-out mb-12 backdrop-blur-xl dark:border-white/[0.1] dark:bg-white/[0.04] dark:shadow-[inset_0_1px_1px_rgba(255,255,255,0.08),0_4px_24px_rgba(0,0,0,0.4)]",
                        isUploaderDragOver
                            ? "border-blue-500 bg-blue-50/80 dark:border-blue-400/80 dark:bg-blue-500/[0.15] scale-[1.01] shadow-[0_8px_40px_rgba(59,130,246,0.1)] dark:shadow-[inset_0_0_20px_rgba(59,130,246,0.2),0_8px_40px_rgba(59,130,246,0.25)]"
                            : "hover:border-blue-400/60 hover:bg-white/60 hover:shadow-[0_8px_30px_rgba(0,0,0,0.04)] dark:hover:border-white/[0.15] dark:hover:bg-white/[0.06] dark:hover:shadow-[inset_0_1px_1px_rgba(255,255,255,0.12),0_8px_32px_rgba(0,0,0,0.5)]"
                    )}
                >
                    <div className={cn(
                        "absolute inset-3 rounded-[16px] border border-dashed pointer-events-none transition-colors duration-300",
                        isUploaderDragOver ? "border-blue-500/40 dark:border-blue-400/40" : "border-slate-300/60 group-hover:border-blue-400/40 dark:border-white/[0.15] dark:group-hover:border-white/[0.3]"
                    )} />

                    <div className="relative z-10 mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-white/80 bg-white/90 shadow-[0_4px_20px_rgba(0,0,0,0.04)] backdrop-blur-xl transition-all duration-400 group-hover:-translate-y-1 group-hover:scale-105 group-hover:border-blue-100 group-hover:shadow-[0_8px_30px_rgba(59,130,246,0.15)] dark:border-white/[0.15] dark:bg-white/[0.12] dark:shadow-[0_4px_24px_rgba(0,0,0,0.4)] dark:group-hover:border-white/[0.25] dark:group-hover:bg-white/[0.16] dark:group-hover:shadow-[0_8px_32px_rgba(255,255,255,0.05)]">
                        <UploadCloud strokeWidth={1.5} size={28} className="text-slate-500 transition-colors duration-300 group-hover:text-blue-500 dark:text-slate-200 dark:group-hover:text-white" />
                        <div className="absolute inset-0 rounded-full bg-blue-400/20 blur-xl opacity-0 transition-opacity duration-300 group-hover:opacity-100 dark:bg-white/10" />
                    </div>

                    <div className="relative z-10 flex flex-col items-center text-center">
                        <h3 className="mb-2 text-[17px] font-semibold tracking-tight text-slate-800 transition-colors duration-300 group-hover:text-blue-600 dark:text-white dark:group-hover:text-blue-200">
                            点击或拖拽上传文档
                        </h3>
                        <p className="text-[13px] text-slate-500 transition-colors duration-300 dark:text-slate-300 font-normal">
                            支持 PDF, Word, Excel, TXT, md等格式
                        </p>
                    </div>
                </motion.div>

                <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-3 gap-5 text-left mx-auto">
                    {/* Feature Card 1 */}
                    <motion.div 
                        initial={{ opacity: 0, y: 30, scale: 0.95, filter: "blur(12px)" }}
                        animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
                        transition={{ duration: 2.4, delay: 2.7, ease: [0.22, 1, 0.36, 1] }}
                        className="group relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white/40 p-5 backdrop-blur-xl transition-all duration-300 hover:-translate-y-0.5 hover:bg-white/80 hover:shadow-[0_8px_30px_rgba(59,130,246,0.06)] hover:border-blue-200/60 dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:bg-white/[0.05] dark:hover:shadow-[inset_0_1px_1px_rgba(255,255,255,0.1),0_8px_32px_rgba(0,0,0,0.5)] dark:hover:border-white/[0.15]"
                    >
                        <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-blue-500/10 to-transparent dark:via-white/20" />
                        <div className="flex items-center gap-3 mb-3 relative z-10">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-50/80 text-blue-600 ring-1 ring-blue-100/50 dark:bg-blue-500/20 dark:text-blue-300 dark:ring-blue-500/30 group-hover:dark:bg-blue-500/30 group-hover:dark:text-blue-200 transition-colors">
                                <FileText size={18} strokeWidth={2} />
                            </div>
                            <h3 className="text-[15px] font-semibold text-slate-800 dark:text-white group-hover:dark:text-white transition-colors">多格式支持</h3>
                        </div>
                        <p className="text-[13px] text-slate-500 dark:text-slate-300 leading-relaxed font-normal group-hover:dark:text-slate-200 transition-colors relative z-10">支持 PDF、Word、Excel 及各类图片格式的无缝解析与深度信息提取。</p>
                    </motion.div>
                    
                    {/* Feature Card 2 */}
                    <motion.div 
                        initial={{ opacity: 0, y: 30, scale: 0.95, filter: "blur(12px)" }}
                        animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
                        transition={{ duration: 2.4, delay: 2.9, ease: [0.22, 1, 0.36, 1] }}
                        className="group relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white/40 p-5 backdrop-blur-xl transition-all duration-300 hover:-translate-y-0.5 hover:bg-white/80 hover:shadow-[0_8px_30px_rgba(14,165,233,0.06)] hover:border-sky-200/60 dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:bg-white/[0.05] dark:hover:shadow-[inset_0_1px_1px_rgba(255,255,255,0.1),0_8px_32px_rgba(0,0,0,0.5)] dark:hover:border-white/[0.15]"
                    >
                        <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-sky-500/10 to-transparent dark:via-white/20" />
                        <div className="flex items-center gap-3 mb-3 relative z-10">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sky-50/80 text-sky-600 ring-1 ring-sky-100/50 dark:bg-sky-500/20 dark:text-sky-300 dark:ring-sky-500/30 group-hover:dark:bg-sky-500/30 group-hover:dark:text-sky-200 transition-colors">
                                <Zap size={18} strokeWidth={2} />
                            </div>
                            <h3 className="text-[15px] font-semibold text-slate-800 dark:text-white group-hover:dark:text-white transition-colors">智能信息抽取</h3>
                        </div>
                        <p className="text-[13px] text-slate-500 dark:text-slate-300 leading-relaxed font-normal group-hover:dark:text-slate-200 transition-colors relative z-10">自动提取关键实体、时间、金额等结构化字段，并支持与原文的精准追溯定位。</p>
                    </motion.div>
                    
                    {/* Feature Card 3 */}
                    <motion.div 
                        initial={{ opacity: 0, y: 30, scale: 0.95, filter: "blur(12px)" }}
                        animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
                        transition={{ duration: 2.4, delay: 3.1, ease: [0.22, 1, 0.36, 1] }}
                        className="group relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white/40 p-5 backdrop-blur-xl transition-all duration-300 hover:-translate-y-0.5 hover:bg-white/80 hover:shadow-[0_8px_30px_rgba(99,102,241,0.06)] hover:border-indigo-200/60 dark:border-white/[0.08] dark:bg-white/[0.03] dark:hover:bg-white/[0.05] dark:hover:shadow-[inset_0_1px_1px_rgba(255,255,255,0.1),0_8px_32px_rgba(0,0,0,0.5)] dark:hover:border-white/[0.15]"
                    >
                        <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-indigo-500/10 to-transparent dark:via-white/20" />
                        <div className="flex items-center gap-3 mb-3 relative z-10">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-50/80 text-indigo-600 ring-1 ring-indigo-100/50 dark:bg-indigo-500/20 dark:text-indigo-300 dark:ring-indigo-500/30 group-hover:dark:bg-indigo-500/30 group-hover:dark:text-indigo-200 transition-colors">
                                <Shield size={18} strokeWidth={2} />
                            </div>
                            <h3 className="text-[15px] font-semibold text-slate-800 dark:text-white group-hover:dark:text-white transition-colors">数据安全隐私</h3>
                        </div>
                        <p className="text-[13px] text-slate-500 dark:text-slate-300 leading-relaxed font-normal group-hover:dark:text-slate-200 transition-colors relative z-10">所有文档处理过程严格加密，解析完成后数据落库，保障您的商业机密安全。</p>
                    </motion.div>
                </div>
            </div>
        </div>
    );
};
