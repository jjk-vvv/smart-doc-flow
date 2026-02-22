import React, { useState, useEffect } from 'react';
import {
  Book, Code2, Zap, Layout, Shield,
  ChevronRight, FileText, Terminal,
  Cpu, GitBranch, Menu, X, ArrowRight
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// --- Mock Data for Navigation ---
const NAV_SECTIONS = [
  {
    title: '开始使用',
    items: [
      { id: 'intro', label: '平台简介' },
      { id: 'quickstart', label: '快速入门' },
      { id: 'architecture', label: 'MAOA 架构' },
    ]
  },
  {
    title: '核心功能',
    items: [
      { id: 'ocr', label: '智能文档解析' },
      { id: 'audit', label: '自动化审计' },
      { id: 'decision', label: '决策辅助引擎' },
    ]
  },
  {
    title: '开发者指南',
    items: [
      { id: 'api', label: 'API 参考' },
      { id: 'sdk', label: 'SDK 文档' },
      { id: 'changelog', label: '更新日志' },
    ]
  }
];

// --- Components ---

const DocCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
  color: string;
}> = ({ icon, title, description, color }) => (
  <div className="group relative p-6 rounded-2xl border border-slate-200 dark:border-white/5 bg-white dark:bg-slate-900/50 hover:shadow-lg hover:border-slate-300 dark:hover:border-white/10 transition-all duration-300 cursor-pointer overflow-hidden backdrop-blur-sm">
    <div className={cn("absolute inset-0 opacity-0 group-hover:opacity-[0.03] transition-opacity duration-500", color.replace('text-', 'bg-'))} />
    <div className="relative z-10">
      <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center mb-4 text-white shadow-sm ring-1 ring-black/5", color)}>
        {icon}
      </div>
      <h3 className="text-lg font-semibold font-['Microsoft_YaHei'] text-slate-900 dark:text-slate-50 mb-2 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
        {title}
      </h3>
      <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed font-['Microsoft_YaHei']">
        {description}
      </p>
    </div>
  </div>
);

const CodeBlock: React.FC = () => (
  <div className="rounded-xl overflow-hidden bg-[#0f1117] border border-white/10 shadow-2xl font-mono text-xs my-6 ring-1 ring-white/5">
    <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-[#13151c]">
      <div className="flex gap-1.5">
        <div className="w-3 h-3 rounded-full bg-[#FF5F56] opacity-80 hover:opacity-100 transition-opacity" />
        <div className="w-3 h-3 rounded-full bg-[#FFBD2E] opacity-80 hover:opacity-100 transition-opacity" />
        <div className="w-3 h-3 rounded-full bg-[#27C93F] opacity-80 hover:opacity-100 transition-opacity" />
      </div>
      <span className="text-slate-500 font-medium">curl request</span>
    </div>
    <div className="p-5 overflow-x-auto text-slate-300 leading-relaxed">
      <div className="flex">
        <span className="text-purple-400 mr-2">curl</span>
        <span className="text-emerald-400">https://api.maoa.dev/v1/extract</span>
      </div>
      <div className="pl-4 mt-1">
        <span className="text-slate-500">-H</span> <span className="text-amber-300">"Authorization: Bearer sk_live_..."</span>
      </div>
      <div className="pl-4 mt-1">
        <span className="text-slate-500">-d</span> <span className="text-blue-300">"file=@invoice.pdf"</span>
      </div>
      <div className="pl-4 mt-1">
        <span className="text-slate-500">-d</span> <span className="text-blue-300">"mode=deep_audit"</span>
      </div>
    </div>
  </div>
);

export const UserGuide: React.FC = () => {
  const [activeSection, setActiveSection] = useState('intro');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // Handle scroll effect for header
  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-transparent font-sans selection:bg-blue-500/20 selection:text-blue-900 dark:selection:text-blue-100 relative">

      {/* --- Background Dot Grid --- */}
      <div className="absolute inset-x-0 top-0 h-[800px] pointer-events-none select-none z-0 overflow-hidden">
        {/* Fade Out Mask: Bottom */}
        <div
          className="absolute inset-0"
          style={{
            maskImage: 'linear-gradient(to bottom, black 20%, transparent 100%)',
            WebkitMaskImage: 'linear-gradient(to bottom, black 20%, transparent 100%)'
          }}
        >
          {/* Fade Out Mask: Sides */}
          <div
            className="absolute inset-0"
            style={{
              maskImage: 'linear-gradient(to right, transparent 0%, black 15%, black 85%, transparent 100%)',
              WebkitMaskImage: 'linear-gradient(to right, transparent 0%, black 15%, black 85%, transparent 100%)'
            }}
          >
            {/* Dot Grid with Gradient */}
            <div
              className="absolute inset-0 bg-gradient-to-r from-indigo-500/30 via-purple-500/30 to-blue-500/30 dark:from-indigo-500/40 dark:via-purple-500/40 dark:to-blue-500/40"
              style={{
                maskImage: 'radial-gradient(circle at center, black 1.5px, transparent 1.5px)',
                WebkitMaskImage: 'radial-gradient(circle at center, black 1.5px, transparent 1.5px)',
                maskSize: '24px 24px',
                WebkitMaskSize: '24px 24px'
              }}
            />
          </div>
        </div>
      </div>

      {/* --- Header (Refined Glassmorphism) --- */}
      <header className={cn(
        "sticky top-0 z-40 w-full transition-all duration-300 border-b",
        scrolled
          ? "bg-slate-50/80 dark:bg-slate-950/80 backdrop-blur-xl border-slate-200/50 dark:border-white/5 shadow-sm"
          : "bg-transparent border-transparent"
      )}>
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              className="md:hidden p-2 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            >
              {isMobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div className="flex items-center gap-2.5 font-semibold text-slate-900 dark:text-white tracking-tight">
              <span className="bg-blue-600 text-white p-1.5 rounded-lg shadow-sm shadow-blue-500/20">
                <Layout size={16} strokeWidth={2.5} />
              </span>
              <span>Docs</span>
            </div>
            <nav className="hidden md:flex items-center gap-8 ml-8 text-[13px] font-medium font-['Microsoft_YaHei'] text-slate-500 dark:text-slate-400">
              <a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">指南</a>
              <a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">API 参考</a>
              <a href="#" className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors">示例</a>
            </nav>
          </div>

        </div>
      </header>

      <div className="flex-1 max-w-[1440px] mx-auto w-full flex items-start">

        {/* --- Sidebar (Refined Navigation) --- */}
        <aside className={cn(
          "fixed inset-y-0 left-0 z-30 w-72 bg-slate-50/95 dark:bg-slate-950/95 backdrop-blur-xl border-r border-slate-200/50 dark:border-white/5 transform transition-transform duration-300 md:translate-x-0 md:static md:bg-transparent md:h-[calc(100vh-64px)] md:sticky md:top-16 overflow-y-auto py-8 pl-6 pr-6 scrollbar-hide",
          isMobileMenuOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"
        )}>
          <div className="space-y-9">
            {NAV_SECTIONS.map((section) => (
              <div key={section.title}>
                <h4 className="text-[11px] font-bold font-['Microsoft_YaHei'] text-slate-900 dark:text-slate-100 uppercase tracking-widest mb-3 px-2.5 opacity-80">
                  {section.title}
                </h4>
                <ul className="space-y-0.5">
                  {section.items.map((item) => (
                    <li key={item.id}>
                      <button
                        onClick={() => setActiveSection(item.id)}
                        className={cn(
                          "w-full text-left px-2.5 py-2 rounded-lg text-[13px] transition-all duration-200 flex items-center justify-between group relative font-['Microsoft_YaHei']",
                          activeSection === item.id
                            ? "bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 font-medium font-bold"
                            : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-50 dark:hover:bg-white/5"
                        )}
                      >
                        {item.label}
                        {activeSection === item.id && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-4 rounded-r-full bg-blue-600 dark:bg-blue-400" />
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </aside>

        {/* --- Main Content --- */}
        <main className="flex-1 min-w-0 px-6 py-10 md:px-16 md:py-14">

          <div className="max-w-6xl mx-auto space-y-20">

            {/* Hero Section */}
            <section className="relative z-10 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
              {/* Text Highlight Glow — creates the "faded dot matrix" effect behind text */}
              <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[140%] h-[180%] -z-10 pointer-events-none">
                <div className="w-full h-full bg-[radial-gradient(closest-side,rgba(255,255,255,0.95)_0%,rgba(255,255,255,0)_100%)] dark:bg-[radial-gradient(closest-side,rgba(2,6,23,0.95)_0%,rgba(2,6,23,0)_100%)] opacity-100" />
              </div>
              
              <div className="space-y-6 relative">
                <h1 className="text-4xl md:text-5xl font-bold font-['Microsoft_YaHei'] tracking-tight text-slate-900 dark:text-white leading-[1.1]">
                  智能文档决策系统文档
                </h1>
                <p className="text-lg md:text-xl text-slate-600 dark:text-slate-400 leading-relaxed max-w-3xl font-light font-['Microsoft_YaHei']">
                  欢迎使用下一代智能文档处理平台。通过多智能体正交架构 (MAOA)，我们为您提供企业级的文档解析、审计与决策支持能力。
                </p>
              </div>
            </section>

            {/* Quick Links Grid */}
            <section className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <DocCard
                icon={<Book size={20} />}
                title="快速入门"
                description="在 5 分钟内完成环境配置并运行您的第一个文档解析任务。"
                color="bg-blue-500"
              />
              <DocCard
                icon={<Code2 size={20} />}
                title="API 参考"
                description="探索我们强大的 RESTful API，将智能文档能力集成到您的应用中。"
                color="bg-violet-500"
              />
              <DocCard
                icon={<Zap size={20} />}
                title="核心概念"
                description="了解 MAOA 架构、智能体协同工作流以及决策引擎原理。"
                color="bg-amber-500"
              />
              <DocCard
                icon={<Shield size={20} />}
                title="安全与合规"
                description="了解我们如何保护您的数据安全以及企业级合规标准。"
                color="bg-emerald-500"
              />
            </section>

            <div className="w-full h-px bg-slate-100 dark:bg-white/5" />

            {/* Split Content Section */}
            <section className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-start">
              <div className="space-y-8">
                <h2 className="text-2xl font-bold font-['Microsoft_YaHei'] text-slate-900 dark:text-white flex items-center gap-3">
                  <div className="p-1.5 rounded-lg bg-slate-100 dark:bg-white/5 text-slate-900 dark:text-white">
                    <Terminal size={20} strokeWidth={2} />
                  </div>
                  无缝集成
                </h2>
                <p className="text-slate-600 dark:text-slate-400 leading-7 font-['Microsoft_YaHei']">
                  我们的 API 设计遵循 RESTful 标准，支持多种编程语言。您只需几行代码即可启动复杂的文档分析任务，享受毫秒级的响应速度。
                </p>
                <ul className="space-y-4">
                  {[
                    '支持 PDF, PNG, JPG 等多种格式',
                    '实时 webhook 回调通知',
                    '细粒度的权限控制',
                    '99.9% 的系统可用性 SLA'
                  ].map((feature, i) => (
                    <li key={i} className="flex items-center gap-3 text-slate-700 dark:text-slate-300 text-sm font-medium font-['Microsoft_YaHei']">
                      <div className="w-5 h-5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-[10px]">✓</div>
                      {feature}
                    </li>
                  ))}
                </ul>
                <a href="#" className="inline-flex items-center gap-2 text-blue-600 dark:text-blue-400 text-sm font-semibold hover:gap-3 transition-all mt-2 font-['Microsoft_YaHei']">
                  查看完整 API 文档 <ArrowRight size={16} />
                </a>
              </div>

              <div className="relative group perspective-1000">
                <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-700 -z-10" />
                <CodeBlock />
              </div>
            </section>

            <div className="w-full h-px bg-slate-100 dark:bg-white/5" />

            {/* Feature Highlights */}
            <section className="space-y-10">
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">为什么选择我们？</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
                {[
                  {
                    icon: <Cpu size={24} />,
                    title: "MAOA 架构",
                    desc: "多智能体正交架构确保了各模块的独立性与高效协同，大幅降低错误率。"
                  },
                  {
                    icon: <GitBranch size={24} />,
                    title: "深度语义理解",
                    desc: "超越传统 OCR，真正理解文档背后的业务逻辑与潜在风险。"
                  },
                  {
                    icon: <Shield size={24} />,
                    title: "企业级安全",
                    desc: "全链路加密存储与传输，符合 SOC2 与 GDPR 标准，保障数据隐私。"
                  }
                ].map((item, i) => (
                  <div key={i} className="space-y-4">
                    <div className="w-12 h-12 rounded-2xl bg-slate-50 dark:bg-white/5 border border-slate-100 dark:border-white/5 flex items-center justify-center text-slate-900 dark:text-white transition-transform hover:scale-105 duration-300">
                      {item.icon}
                    </div>
                    <h3 className="font-semibold text-slate-900 dark:text-white text-base">{item.title}</h3>
                    <p className="text-slate-500 dark:text-slate-400 leading-relaxed text-sm">{item.desc}</p>
                  </div>
                ))}
              </div>
            </section>

          </div>
        </main>

        {/* --- Right Sidebar (On This Page) --- */}
        {/* Removed as requested */}

      </div>
    </div>
  );
};