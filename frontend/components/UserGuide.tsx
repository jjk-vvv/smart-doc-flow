import React, { useState, useEffect, useMemo } from 'react';
import { Menu, X, Globe, User, ArrowRight, CircleDashed } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { motion, AnimatePresence } from 'framer-motion';

function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }

/* ═══════════════════════════════════════════════════════
   Bytedance Clone - Core Components
   ═══════════════════════════════════════════════════════ */

export const UserGuide: React.FC = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [currentSlide, setCurrentSlide] = useState(0);

  const slides = useMemo(() => [
    {
      image: "https://images.unsplash.com/photo-1497215728101-856f4ea42174?q=80&w=2070&auto=format&fit=crop",
      title: "文档智慧\n重塑未来",
      subtitle: "Smart Document Flow Platform",
      tag: "核心愿景"
    },
    {
      image: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop",
      title: "高效协同\n无界流转",
      subtitle: "Seamless Workflow Automation",
      tag: "卓越效能"
    },
    {
      image: "https://images.unsplash.com/photo-1556761175-5973dc0f32e7?q=80&w=2664&auto=format&fit=crop",
      title: "数据洞察\n决策之源",
      subtitle: "Intelligent Decision Support",
      tag: "深度智能"
    }
  ], []);

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % slides.length);
    }, 5000);
    return () => clearInterval(timer);
  }, [slides.length]);

  // Monitor scroll for Navbar transition
  useEffect(() => {
    const handleScroll = () => {
      const isScrolled = window.scrollY > 50;
      if (isScrolled !== scrolled) {
        setScrolled(isScrolled);
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [scrolled]);

  return (
    <div className="min-h-screen bg-white font-sans text-slate-900 selection:bg-indigo-500/30">

      {/* --- NAVBAR --- */}
      <nav className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-500 ease-in-out border-b border-transparent",
        scrolled
          ? "bg-[#3370ff]/95 backdrop-blur-xl shadow-[0_4px_30px_rgba(0,0,0,0.1)] py-4"
          : "bg-[#3370ff] py-6 shadow-md"
      )}>
        <div className="w-full px-6 lg:px-10 flex items-center justify-between text-white">

          {/* Logo Section */}
          <div className="flex items-center gap-6 xl:gap-10 cursor-pointer">
            <div className="text-xl md:text-2xl font-bold tracking-tight flex items-center whitespace-nowrap pt-1">
              <span className="hidden md:inline-block bg-clip-text text-transparent bg-gradient-to-r from-white via-indigo-100 to-white transition-all duration-500">
                智能文档流转平台
              </span>
              <span className="md:hidden text-white">SmartDoc</span>
            </div>

            {/* Desktop Links */}
            <div className="hidden lg:flex items-center gap-6 xl:gap-10 font-medium text-[15px]">
              {['关于我们', '我们的产品', '平台及开放支持', '社会责任', '资讯与动态'].map((item) => (
                <div key={item} className="cursor-pointer hover:text-indigo-100 transition-colors relative group whitespace-nowrap">
                  {item}
                  <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-white transition-all duration-300 group-hover:w-full" />
                </div>
              ))}
            </div>
          </div>

          {/* Right Section */}
          <div className="hidden lg:flex items-center gap-6 text-[15px] font-medium">
            <div className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity">
              <Globe size={18} />
              <span>中文</span>
            </div>
            <div className="w-px h-4 bg-white/30"></div>
            <div className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity">
              <User size={18} />
              <span>登录</span>
            </div>
          </div>

          {/* Mobile Menu Toggle */}
          <button
            className="lg:hidden p-2 text-white"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Mobile Dropdown */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="absolute top-full left-0 right-0 bg-white text-slate-900 p-6 shadow-2xl lg:hidden flex flex-col gap-4 font-medium"
            >
              {['关于我们', '我们的产品', '平台及开放支持', '社会责任', '资讯与动态'].map((item) => (
                <div key={item} className="py-2 border-b border-slate-100 last:border-0">{item}</div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* --- HERO SECTION --- */}
      <section className="relative w-full h-[100vh] min-h-[700px] overflow-hidden bg-slate-900">
        
        {/* Background Slider */}
        <AnimatePresence mode="wait">
          <motion.div
            key={currentSlide}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.5, ease: "easeInOut" }}
            className="absolute inset-0 z-0"
          >
            <div 
              className="absolute inset-0 bg-cover bg-center transform scale-105"
              style={{ backgroundImage: `url(${slides[currentSlide].image})` }}
            />
            <div className="absolute inset-0 bg-black/20" /> {/* Subtle overlay for contrast */}
          </motion.div>
        </AnimatePresence>

        {/* Floating White Component (Left Content Card) */}
        <div className="absolute top-0 left-0 h-full w-full pointer-events-none z-10">
          <div className="h-full relative w-full">
            
            {/* The White Card Shape */}
            <div className="absolute top-[80px] left-6 md:left-12 lg:left-[140px] w-[280px] md:w-[320px] lg:w-[360px] h-[320px] md:h-[360px] lg:h-[400px] bg-white rounded-br-[60px] pt-10 px-6 lg:px-10 shadow-[0_20px_50px_rgba(0,0,0,0.05)] pointer-events-auto flex flex-col justify-center">
              <AnimatePresence mode="wait">
                <motion.div
                  key={currentSlide}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ duration: 0.5, delay: 0.2 }}
                >
                  <p className="text-sm text-slate-500 font-medium mb-3 tracking-wider">
                    {slides[currentSlide].tag}
                  </p>
                  
                  <h1 className="text-3xl lg:text-[2.75rem] font-medium text-slate-900 leading-[1.2] tracking-tight mb-4 whitespace-pre-line">
                    {slides[currentSlide].title}
                  </h1>
                  
                  {/* Optional: Removed subtitle to match cleaner reference, or keep it smaller if needed */}
                  {/* <p className="text-lg text-slate-500 font-medium max-w-sm leading-relaxed">
                    {slides[currentSlide].subtitle}
                  </p> */}

                  {/* No button in the strict reference image, but keeping functionality hidden or minimal if desired. 
                      User asked for "exactly same size and position". 
                      I will remove the button visually to match the "picture" but keep the code commented just in case.
                  */}
                </motion.div>
              </AnimatePresence>
            </div>

          </div>
        </div>

        {/* Slider Indicators */}
        <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-20 flex gap-4">
          {slides.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentSlide(idx)}
              className={cn(
                "h-2 rounded-full transition-all duration-500 backdrop-blur-sm",
                currentSlide === idx 
                  ? "w-12 bg-white" 
                  : "w-2 bg-white/40 hover:bg-white/60"
              )}
              aria-label={`Go to slide ${idx + 1}`}
            />
          ))}
        </div>
      </section>

      {/* --- BYTESTYLES (文化区) --- */}
      <section className="bg-[#f8f9fa] py-32 px-6 lg:px-12">
        <div className="max-w-[1400px] mx-auto">
          <div className="mb-20">
            <h2 className="text-5xl md:text-6xl font-black text-slate-900 tracking-tight">字节范 <span className="text-slate-400 font-normal">ByteStyle</span></h2>
            <p className="mt-6 text-xl text-slate-500 max-w-3xl leading-relaxed">
              字节范是字节跳动企业文化的重要组成部分，是我们共同认可的行为准则。
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              { title: '始终创业', desc: '保持创业精神，始终渴求完美。', gradient: 'from-blue-50 to-indigo-50' },
              { title: '多元兼容', desc: '拥抱不同背景，用多元视角看世界。', gradient: 'from-purple-50 to-fuchsia-50' },
              { title: '坦诚清晰', desc: '敢于表达真实想法，沟通简单直接。', gradient: 'from-emerald-50 to-teal-50' },
              { title: '求真务实', desc: '探究本质，尊重事实，数据说话。', gradient: 'from-amber-50 to-orange-50' },
              { title: '卓越执行', desc: '追求极高标准，执行力决胜。', gradient: 'from-rose-50 to-red-50' },
              { title: '拥抱变化', desc: '在这个急速变化的时代，唯一不变的就是变化。', gradient: 'from-sky-50 to-cyan-50' }
            ].map((style, i) => (
              <motion.div
                initial={{ opacity: 0, y: 40 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-50px' }}
                transition={{ duration: 0.7, delay: i * 0.1, ease: [0.22, 1, 0.36, 1] }}
                key={i}
                className={cn(
                  "group relative p-10 h-[380px] rounded-[40px] flex flex-col justify-between overflow-hidden cursor-pointer",
                  "bg-white transition-all duration-500 ease-out hover:-translate-y-2 hover:shadow-[0_20px_40px_-15px_rgba(0,0,0,0.06)]"
                )}
              >
                <div className={cn("absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-700 bg-gradient-to-br -z-10", style.gradient)} />
                <div className="relative z-10">
                  <h3 className="text-3xl font-black text-slate-900 mb-4">{style.title}</h3>
                  <p className="text-lg text-slate-500 leading-relaxed font-medium">{style.desc}</p>
                </div>
                <div className="relative z-10 w-12 h-12 rounded-full bg-slate-50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-500 transform translate-x-4 group-hover:translate-x-0 shadow-sm">
                  <ArrowRight className="text-slate-900" />
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* --- TIMELINE (大事记) --- */}
      <section className="bg-white py-32 px-6 lg:px-12 relative">
        <div className="max-w-[1400px] mx-auto flex flex-col lg:flex-row gap-16 lg:gap-32">

          {/* Sticky Sidebar */}
          <div className="lg:w-1/3">
            <div className="sticky top-40">
              <h2 className="text-5xl md:text-6xl font-black text-slate-900 tracking-tight">大事记</h2>
              <p className="mt-6 text-xl text-slate-500 leading-relaxed">
                记录我们的成长印记，<br className="hidden lg:block" />见证每一步的历史足迹。
              </p>
            </div>
          </div>

          {/* Timeline Content */}
          <div className="lg:w-2/3 relative">
            <div className="absolute left-[23px] top-4 bottom-4 w-0.5 bg-slate-100" />

            <div className="flex flex-col gap-24">
              {[
                { year: '2023', events: ['推出全新的大模型及相关产品', '全球员工数持续增长，业务覆盖超过150个国家和地区'] },
                { year: '2021', events: ['正式提出“字节范”企业文化', '发布社会责任报告'] },
                { year: '2016', events: ['抖音上线，开启短视频新纪元', '头条号创作者平台全面爆发'] },
                { year: '2012', events: ['字节跳动在北京成立', '推出首款产品“今日头条”'] }
              ].map((group, idx) => (
                <div key={idx} className="relative pl-16">
                  {/* Timeline Dot */}
                  <div className="absolute left-[19px] top-2 w-2.5 h-2.5 rounded-full bg-indigo-600 ring-8 ring-white" />

                  <h3 className="text-4xl font-black text-slate-900 mb-8 tracking-tighter">{group.year}</h3>
                  <div className="flex flex-col gap-6">
                    {group.events.map((event, eIdx) => (
                      <div key={eIdx} className="p-8 rounded-[32px] bg-slate-50 border border-slate-100 hover:bg-white hover:shadow-xl transition-all duration-300">
                        <p className="text-xl text-slate-700 font-medium leading-relaxed">{event}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Footer Minimal */}
      <footer className="bg-slate-950 text-slate-400 py-12 text-center text-sm">
        <p>© {new Date().getFullYear()} Bytedance Clone. All rights reserved.</p>
      </footer>
    </div>
  );
};