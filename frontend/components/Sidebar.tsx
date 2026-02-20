import React from 'react';
import {
  LayoutGrid,
  FileSearch,
  Database,
  GitGraph,
  Moon,
  Sun,
  User,
  LogOut,
  ArrowRight,
  ChevronLeft,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import LogoImage from '../image.png';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isDark: boolean;
  toggleTheme: () => void;
  isCollapsed: boolean;
  toggleCollapse: () => void;
  user: { name: string; email: string } | null;
  setUser: (user: { name: string; email: string } | null) => void;
  showLoginModal: boolean;
  setShowLoginModal: (show: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  isDark,
  toggleTheme,
  isCollapsed,
  toggleCollapse,
  user,
  setUser,
  showLoginModal,
  setShowLoginModal
}) => {

  const handleLogout = async () => {
    try {
      await fetch('/api/logout', { method: 'POST' });
      setUser(null);
    } catch (err) {
      console.error('Logout failed:', err);
      setUser(null);
    }
  };

  const menuItems = [
    { id: 'dashboard', label: '指挥控制台', sub: 'Command Center', icon: LayoutGrid },
    { id: 'deepread', label: '智能文档解析', sub: 'Deep Parsing', icon: FileSearch },
    { id: 'fusion', label: '多源数据融合', sub: 'Data Fusion', icon: Database },
    { id: 'nexus', label: '全域知识图谱', sub: 'Knowledge Graph', icon: GitGraph },
  ];

  return (
    <div className={cn(
      "bg-gradient-to-b from-slate-50 via-blue-50 to-blue-100 dark:from-slate-950 dark:via-slate-900 dark:to-blue-900/40 backdrop-blur-xl border-r border-slate-200 dark:border-blue-700/30 flex flex-col h-screen fixed left-0 top-0 z-50 shadow-2xl group/sidebar",
      "transition-[width] duration-300 ease-in-out",
      isCollapsed ? "w-[72px]" : "w-72"
    )}>

      {/* Modern Hover-Triggered Collapse Control (Vertical Center) */}
      <div
        className="absolute -right-4 top-1/2 -translate-y-1/2 h-24 w-8 z-[60] flex items-center justify-center cursor-pointer group/toggle opacity-0 group-hover/sidebar:opacity-100 transition-opacity duration-300"
        onClick={toggleCollapse}
        title={isCollapsed ? '展开侧边栏' : '收起侧边栏'}
      >
        {/* The visible pill button */}
        <div className={cn(
          "w-6 h-6 rounded-full flex items-center justify-center transition-all duration-300 shadow-sm backdrop-blur-md border",
          "bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700",
          "group-hover/toggle:scale-125 group-hover/toggle:shadow-md group-hover/toggle:border-blue-200 dark:group-hover/toggle:border-blue-500/50",
          "text-slate-400 dark:text-slate-500 group-hover/toggle:text-blue-600 dark:group-hover/toggle:text-blue-400"
        )}>
          <ChevronLeft size={14} className={cn("transition-transform duration-300", isCollapsed && "rotate-180")} />
        </div>
      </div>

      {/* Header */}
      <div className={cn(
        "h-auto py-5 flex items-center border-b border-slate-200 dark:border-blue-700/30 relative overflow-hidden group",
        isCollapsed ? "justify-center px-3" : "justify-between px-6"
      )}>
        <div className={cn(
          "flex items-center relative z-10",
          isCollapsed ? "justify-center" : "gap-3 w-full"
        )}>
          <div className={cn(
            "shrink-0 bg-gradient-to-br from-white to-blue-50 dark:from-slate-800 dark:to-slate-900 rounded-xl shadow-lg shadow-slate-200 dark:shadow-[0_0_20px_rgba(56,189,248,0.2)] flex items-center justify-center border border-blue-100 dark:border-cyan-400/30 dark:ring-1 dark:ring-cyan-400/20 relative overflow-hidden",
            isCollapsed ? "w-10 h-10" : "w-12 h-12"
          )}>
            <div className="absolute inset-0 bg-primary/10 opacity-0 dark:opacity-100 rounded-xl pointer-events-none" />
            <img src={LogoImage} alt="Logo" className={cn(
              "object-contain drop-shadow-sm relative z-10",
              isCollapsed ? "w-7 h-7" : "w-9 h-9"
            )} />
          </div>
          {/* Title text — hidden when collapsed */}
          <div className={cn(
            "flex flex-col items-center gap-1 transition-all duration-300",
            isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
          )}>
            <div className="h-1.5 w-full" aria-hidden="true" />
            <h1 className="font-['Microsoft_YaHei'] font-bold text-[17px] tracking-wide text-black dark:text-white leading-none drop-shadow-[0_0_2px_rgba(255,255,255,0.5)] dark:drop-shadow-none truncate whitespace-nowrap">智能文档流转平台</h1>
            <button
              onClick={() => setActiveTab('guide')}
              className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary hover:bg-primary/20 hover:text-primary transition-all duration-300 flex items-center gap-1 group/btn cursor-pointer font-medium whitespace-nowrap"
            >
              <span>平台功能说明</span>
              <ArrowRight size={10} className="group-hover/btn:translate-x-0.5 transition-transform" />
            </button>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className={cn(
        "flex-1 py-8 space-y-2",
        isCollapsed ? "px-2" : "px-4"
      )}>
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <div key={item.id} className="relative group/nav">
              <button
                onClick={() => setActiveTab(item.id)}
                className={cn(
                  "w-full flex items-center rounded-xl border transition-all duration-300 relative overflow-hidden",
                  isCollapsed
                    ? "justify-center px-0 py-3"
                    : "gap-4 px-4 py-4",
                  isActive
                    ? 'bg-primary/10 border-primary/30 text-primary shadow-[0_0_20px_rgba(56,189,248,0.15)]'
                    : 'bg-transparent border-transparent text-muted-foreground hover:text-foreground hover:bg-slate-100 dark:hover:bg-blue-900/20 hover:border-slate-200 dark:hover:border-blue-800/30'
                )}
              >
                <div className={cn(
                  "absolute inset-0 bg-gradient-to-r from-primary/10 to-transparent opacity-0 transition-opacity duration-300",
                  isActive && "opacity-100"
                )}></div>

                <Icon size={20} className={cn(
                  "relative z-10 transition-colors duration-300 shrink-0",
                  isActive ? 'text-primary drop-shadow-[0_0_8px_rgba(56,189,248,0.5)]' : 'group-hover/nav:text-foreground'
                )} />

                {/* Label — hidden when collapsed */}
                <div className={cn(
                  "text-left relative z-10 transition-all duration-300",
                  isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
                )}>
                  <div className={cn("text-sm font-bold tracking-tight transition-colors whitespace-nowrap", isActive ? "text-primary" : "")}>{item.label}</div>
                </div>

                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 h-8 w-1 bg-primary rounded-r-full shadow-[0_0_10px_currentColor]" />
                )}
              </button>

              {/* Tooltip — only visible when collapsed */}
              {isCollapsed && (
                <div className="
                  absolute left-full top-1/2 -translate-y-1/2 ml-3
                  px-3 py-2 rounded-lg
                  bg-slate-800 dark:bg-slate-700 text-white text-xs font-bold
                  shadow-xl
                  opacity-0 invisible group-hover/nav:opacity-100 group-hover/nav:visible
                  transition-all duration-200
                  pointer-events-none z-[100]
                  whitespace-nowrap
                  before:content-[''] before:absolute before:right-full before:top-1/2 before:-translate-y-1/2
                  before:border-[5px] before:border-transparent before:border-r-slate-800 dark:before:border-r-slate-700
                ">
                  {item.label}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Status Footer */}
      <div className={cn(
        "border-t border-slate-200 dark:border-blue-700/30 bg-background/50 backdrop-blur-md flex flex-col gap-4",
        isCollapsed ? "p-3" : "p-6"
      )}>
        {/* Theme Toggle */}
        <div className="flex items-center justify-between">
          <button
            onClick={toggleTheme}
            className={cn(
              "w-full flex items-center justify-center gap-2 rounded-xl bg-white/50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 shadow-sm hover:border-blue-300 dark:hover:border-cyan-400/60 hover:bg-blue-50 dark:hover:bg-slate-800/60 dark:hover:shadow-[0_0_20px_rgba(34,211,238,0.25)] transition-all duration-300 group/theme relative",
              isCollapsed ? "px-2 py-2.5" : "px-4 py-2.5"
            )}
            title={isDark ? '切换亮色模式' : '切换深色模式'}
          >
            {isDark ?
              <Sun size={18} className="text-amber-400 group-hover/theme:rotate-90 transition-transform shrink-0" /> :
              <Moon size={18} className="text-slate-600 group-hover/theme:-rotate-12 transition-transform shrink-0" />
            }
            <span className={cn(
              "text-[15px] font-bold transition-all font-['Microsoft_YaHei'] whitespace-nowrap",
              isDark ? "text-white" : "text-muted-foreground group-hover/theme:text-foreground",
              isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
            )}>
              {isDark ? '亮色模式' : '深色模式'}
            </span>
          </button>
        </div>

        {/* User Management Section */}
        {user ? (
          <div className={cn(
            "flex items-center rounded-xl bg-white/50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 shadow-sm animate-in slide-in-from-bottom-2 duration-300",
            isCollapsed ? "justify-center p-2" : "gap-3 p-3"
          )}>
            <div className="relative shrink-0">
              <div
                className={cn(
                  "rounded-full bg-gradient-to-br from-blue-200 to-blue-400 dark:from-cyan-400 dark:to-blue-600 flex items-center justify-center text-black dark:text-white font-bold font-['Microsoft_YaHei'] shadow-lg dark:shadow-[0_0_15px_rgba(6,182,212,0.6)] relative overflow-hidden",
                  isCollapsed ? "w-8 h-8 text-xs" : "w-10 h-10"
                )}
              >
                {user.name.charAt(0)}
              </div>

            </div>
            {/* User info — hidden when collapsed */}
            <div className={cn(
              "flex-1 min-w-0 transition-all duration-300",
              isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
            )}>
              <div className="text-[10px] font-medium text-primary mb-0.5">欢迎回来,</div>
              <div className="text-sm font-bold truncate text-foreground">{user.name}</div>
            </div>
            {!isCollapsed && (
              <button
                onClick={handleLogout}
                className="p-1.5 hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500 rounded-lg transition-colors"
                title="退出登录"
              >
                <LogOut size={16} />
              </button>
            )}
          </div>
        ) : (
          <button
            onClick={() => setShowLoginModal(true)}
            className={cn(
              "w-full flex items-center justify-center gap-2 rounded-xl bg-primary text-primary-foreground font-bold shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 group",
              isCollapsed ? "px-2 py-2.5" : "px-4 py-2.5"
            )}
            title="登录账号"
          >
            <User size={16} className="group-hover:animate-bounce shrink-0" />
            <span className={cn(
              "transition-all duration-300 whitespace-nowrap",
              isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
            )}>登录账号</span>
          </button>
        )}
      </div>

    </div>
  );
};
