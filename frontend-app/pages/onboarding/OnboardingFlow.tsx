import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { LogIn, ArrowDownRight } from 'lucide-react';
import { cn } from '../../lib/utils';

// @ts-ignore
import splashBg from '../../assets/前导页.png';
// @ts-ignore
import appLogo from '../../../frontend/assets/app-logo.png';

export interface OnboardingFlowProps {
  onComplete: () => void;
  onOpenLogin: () => void;
}

// === OnboardingSlogan Component ===
const OnboardingSlogan = () => (
  <motion.div 
    initial={{ opacity: 0, y: 30 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay: 0, duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
    className="absolute left-0 right-0 flex flex-col items-center text-center w-full"
    style={{ top: 'calc(13vw + 10px)' }}
  >
    {/* 背景 Logo 装饰 (Atmospheric Watermark) - 移除之前的背景暗纹方案 */}
    
    {/* 大标题：错位排版设计 (Staggered Layout) */}
    {/* 极限微调：使用 -translate-y 把整个文字块整体向上平移极其微小的距离 (例如 2px 或 0.5vw) */}
    <div className="relative z-10 flex flex-col justify-center items-center w-full -translate-y-[0.5vw]" style={{ height: '26vw' }}>
      <div 
        className="font-black tracking-[0.1em] text-slate-900 leading-[1.05] flex flex-col justify-between" 
        style={{ 
          fontFamily: 'system-ui, -apple-system, sans-serif',
          fontSize: 'clamp(36px, 12vw, 56px)', // 字号大幅提升，真正撑满高度
          width: '78%', // 宽度占比调大，贴紧左右边缘
          height: '100%', // 容器高度拉满，配合 justify-between 让两行字贴紧上下边缘
          paddingTop: '1vw', // 稍微减小顶部 padding，让文字整体向上微移
          paddingBottom: '3vw' // 稍微增大底部 padding，把第二行字往上托一点
        }}
      >
        {/* 第一行：靠左对齐，增加孟菲斯风格纯色硬投影 */}
        <span className="self-start text-left block" style={{ marginTop: '-0.1em', textShadow: '3px 3px 0px #E8DCC4' }}>智阅文档</span>
        {/* 第二行：靠右对齐，增加孟菲斯风格纯色硬投影 */}
        <span className="self-end text-right block" style={{ marginBottom: '-0.1em', textShadow: '3px 3px 0px #E8DCC4' }}>聚数成网</span>
      </div>
    </div>
    
    {/* 副标题描述：将整个图文块居中，平衡视觉重心，同时内部保持左对齐 */}
    <div 
      className="relative z-10 flex items-start justify-center gap-1.5 leading-[1.6]" 
      style={{ 
        marginTop: 'clamp(10px, 3vw, 20px)',
        // 增大副标题字号，提升整体阅读体验和排版协调性
        fontSize: 'clamp(13px, 3.5vw, 16px)', 
        // 放开宽度限制，让 flex 的 justify-center 能够在整个屏幕宽度范围内完美居中
        width: '100%', 
        textAlign: 'left'
      }}
    >
      <ArrowDownRight size={18} strokeWidth={2.5} className="shrink-0 text-slate-900 mt-[0.15em]" />
      <div className="flex flex-col">
        {/* Impeccable 级：第一行核心功能词流光效果，减弱对比度，更加内敛 */}
        <motion.span 
          className="font-bold bg-clip-text text-transparent"
          style={{ 
            backgroundImage: 'linear-gradient(110deg, #0f172a 40%, #475569 50%, #0f172a 60%)', 
            backgroundSize: '200% auto' 
          }}
          animate={{ backgroundPosition: ['200% center', '-200% center'] }}
          transition={{ duration: 4.5, repeat: Infinity, ease: "linear", delay: 0.1 }}
        >
          编辑、抽取、融合、填表，
        </motion.span>
        {/* Impeccable 级：第二行说明文字延迟流光效果，减弱对比度，更加内敛 */}
        <motion.span 
          className="font-medium bg-clip-text text-transparent"
          style={{ 
            backgroundImage: 'linear-gradient(110deg, #475569 40%, #64748b 50%, #475569 60%)', 
            backgroundSize: '200% auto' 
          }}
          animate={{ backgroundPosition: ['200% center', '-200% center'] }}
          transition={{ duration: 4.5, repeat: Infinity, ease: "linear", delay: 0.3 }}
        >
          一站式轻松管理全量非结构化文档
        </motion.span>
      </div>
    </div>
  </motion.div>
);

export const OnboardingFlow: React.FC<OnboardingFlowProps> = ({ onComplete, onOpenLogin }) => {
  const [isVisible, setIsVisible] = useState(true);

  const handleStart = () => {
    try {
      window.localStorage.setItem('smart_doc_flow.has_seen_onboarding', 'true');
    } catch {}
    setIsVisible(false);
    setTimeout(onComplete, 400); // Wait for exit animation
  };

  const handleLoginClick = () => {
    handleStart();
    onOpenLogin();
  };

  if (!isVisible) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-[#f8f9fa] overflow-hidden dark:bg-slate-950">
      <AnimatePresence mode="wait">
        <motion.div
          key="unified-onboarding"
          initial={{ opacity: 0, scale: 1.05 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
          className="absolute inset-0 bg-[#BCECFA]/20 bg-cover bg-no-repeat flex flex-col justify-between items-center dark:bg-slate-900"
          style={{ backgroundImage: `url(${splashBg})`, backgroundPosition: 'center calc(50% + 9vh)' }}
        >
          {/* 顶部文字区域 */}
          <OnboardingSlogan />

          {/* 中部气泡提示 - 保持完美的弹出延迟 */}
          <motion.div 
            className="absolute z-[50] flex flex-col items-center justify-center"
            style={{ 
              left: '34%', 
              top: '68%', 
              transformOrigin: 'bottom center' 
            }}
            initial={{ opacity: 0, scale: 0, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ 
              delay: 0.9, 
              type: "spring", 
              stiffness: 280, 
              damping: 24,
              mass: 1
            }}
          >
            <div className="relative w-[22vw] h-[22vw] max-w-[95px] max-h-[95px] flex items-center justify-center">
              <svg viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" className="absolute inset-0 w-full h-full overflow-visible drop-shadow-[4px_4px_0px_#0f172a]">
                <defs>
                  <clipPath id="thought-bubble-clip-unified">
                    <ellipse cx="60" cy="50" rx="46" ry="36" transform="rotate(5 60 50)" />
                  </clipPath>
                </defs>
                <ellipse cx="60" cy="50" rx="46" ry="36" fill="#e0f2fe" transform="rotate(5 60 50)" />
                <ellipse cx="52" cy="42" rx="46" ry="36" fill="white" transform="rotate(5 60 50)" clipPath="url(#thought-bubble-clip-unified)" />
                <ellipse cx="60" cy="50" rx="46" ry="36" fill="none" stroke="#0f172a" strokeWidth="3.5" transform="rotate(5 60 50)" />
                
                <path d="M 47 25 C 37 28 30 36 27 45" fill="none" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
                <path d="M 26 52 L 25 56" fill="none" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
                
                <circle cx="5" cy="66" r="7" fill="white" stroke="#0f172a" strokeWidth="3.5" />
                <circle cx="-10" cy="70" r="4" fill="white" stroke="#0f172a" strokeWidth="3" />
              </svg>
              <img src={appLogo} alt="Smart Doc Flow Logo" className="relative z-10 w-[48%] h-[48%] object-contain -mt-4" />
            </div>
          </motion.div>

          {/* 底部按钮区域 - 与气泡形成完美错峰连贯动画 */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.5, duration: 0.8, ease: [0.22, 1, 0.36, 1] }} // 紧接着气泡弹出后平滑进入
            className="relative flex w-full flex-col items-center z-10 mt-auto"
            style={{ paddingBottom: 'calc(env(safe-area-inset-bottom, 0px) + 0.75rem)' }}
          >
            <motion.button
              whileHover={{ x: -2, y: -4, boxShadow: '4px 4px 0px #E8DCC4, 4px 4px 0px 2px #0f172a', transition: { duration: 0.15, ease: "easeOut" } }}
              whileTap={{ x: 0, y: 0, boxShadow: 'none', transition: { duration: 0.1, ease: "easeOut" } }}
              animate={{ scale: [1, 1.02, 1] }}
              transition={{ 
                scale: { 
                  duration: 2.5, 
                  ease: "easeInOut", 
                  repeat: Infinity,
                  repeatType: "loop",
                  repeatDelay: 1
                }
              }}
              className="group relative flex h-[52px] w-[220px] items-center justify-center gap-2.5 rounded-full border-[2px] border-slate-900 bg-[#1A1C29] text-[16px] font-black tracking-wide text-white"
              onClick={handleLoginClick}
            >
              <motion.div
                 animate={{ x: [0, 4, 0] }}
                 transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
              >
                <LogIn size={20} strokeWidth={3} />
              </motion.div>
              立即登录体验
            </motion.button>
          </motion.div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
};
