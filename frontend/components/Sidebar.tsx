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
  ChevronDown, // Add ChevronDown
  Bot, // Add Bot icon for new module
  FileText // Add FileText icon for extraction module
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

  const [expandedItems, setExpandedItems] = React.useState<string[]>([]);
  
  // Auto-expand if active tab is a child
  React.useEffect(() => {
    const parent = menuItems.find(item => item.subItems?.some(sub => sub.id === activeTab));
    if (parent) {
      // Ensure active parent is expanded
      if (!expandedItems.includes(parent.id)) {
        setExpandedItems(prev => [...prev, parent.id]);
      }
    } else {
      // If active tab is NOT a child (i.e. we are on a root page like Dashboard),
      // collapse all expanded items to keep sidebar clean.
      setExpandedItems([]);
    }
  }, [activeTab]);

  const toggleExpand = (id: string) => {
    setExpandedItems(prev => 
      prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]
    );
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/logout', { method: 'POST' });
      setUser(null);
    } catch (err) {
      console.error('Logout failed:', err);
      setUser(null);
    }
  };

  const selectSubItem = (subId: string) => {
    setActiveTab(subId);
  };

  /*
  const menuItems = [
    { id: 'dashboard', label: '指挥控制台', sub: '指挥中心', icon: LayoutGrid },
    { 
      id: 'deepread', 
      label: '智能文档解析', 
      sub: '深度解析', 
      icon: FileSearch,
      subItems: [
        { id: 'deepread_interaction', label: '文档智能操作交互模块', icon: Bot },
        { id: 'deepread_extraction', label: '非结构化文档信息需求模块', icon: FileText }
      ]
    },
    { id: 'fusion', label: '多源数据融合', sub: '数据融合', icon: Database },
    { id: 'nexus', label: '全域知识图谱', sub: '知识图谱', icon: GitGraph },
  ];

  ];
  */

  const menuItems = [
    { id: 'dashboard', label: '指挥控制台', sub: '指挥中心', icon: LayoutGrid },
    {
      id: 'deepread',
      label: '智能文档解析',
      sub: '深度解析',
      icon: FileSearch,
      subItems: [
        { id: 'deepread_interaction', label: '文档智能操作交互模块', icon: Bot },
        { id: 'deepread_extraction', label: '非结构化文档信息需求模块', icon: FileText },
      ]
    },
    { id: 'fusion', label: '多源数据融合', sub: '数据融合', icon: Database },
    { id: 'nexus', label: '全域知识图谱', sub: '知识图谱', icon: GitGraph },
  ];

  return (
    <div className={cn(
      "bg-gradient-to-b from-slate-50 via-blue-50 to-blue-100 dark:from-[#0B1120] dark:via-[#0f172a] dark:to-[#0B1120] backdrop-blur-xl border-r border-slate-200 dark:border-slate-800 flex flex-col h-screen fixed left-0 top-0 z-50 shadow-2xl group/sidebar",
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
            "shrink-0 bg-gradient-to-br from-white to-blue-50 dark:from-slate-800 dark:to-slate-900 rounded-xl shadow-lg shadow-slate-200 dark:shadow-[0_0_8px_rgba(56,189,248,0.05)] flex items-center justify-center border border-blue-100 dark:border-cyan-400/10 dark:ring-1 dark:ring-cyan-400/5 relative overflow-hidden",
            isCollapsed ? "w-10 h-10" : "w-12 h-12"
          )}>
            <div className="absolute inset-0 bg-primary/5 opacity-0 dark:opacity-100 rounded-xl pointer-events-none" />
            <img src={LogoImage} alt="平台徽标" className={cn(
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
            <h1 className="font-sans font-black text-[17px] tracking-wide text-black dark:text-white leading-none drop-shadow-[0_0_2px_rgba(255,255,255,0.5)] dark:drop-shadow-none truncate whitespace-nowrap">智能文档流转平台</h1>
            <button
              onClick={() => setActiveTab('guide')}
              className="text-[10px] px-2 py-0.5 rounded-full bg-transparent text-blue-600 dark:text-blue-400 hover:opacity-70 transition-all duration-300 flex items-center gap-1 group/btn cursor-pointer font-black whitespace-nowrap font-sans"
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
          // Check if item or any of its sub-items is active
          const isParentActive = activeTab === item.id || (item.subItems && item.subItems.some(sub => sub.id === activeTab));
          const hasSubItems = item.subItems && item.subItems.length > 0;
          const isExpanded = expandedItems.includes(item.id);
          
          // 如果有子项且已展开，父项不需要显示强烈的选中背景，避免与子项的选中状态冲突
          const isParentVisuallySelected = isParentActive && (!hasSubItems || !isExpanded || isCollapsed);

          return (
            <div 
              key={item.id} 
              className="relative group/nav"
              onMouseEnter={() => {
                if (!isCollapsed && hasSubItems) {
                  setExpandedItems(prev => prev.includes(item.id) ? prev : [...prev, item.id]);
                }
              }}
              onMouseLeave={() => {
                if (!isCollapsed && hasSubItems) {
                  // Only collapse if active tab is NOT one of the sub-items
                  const isChildActive = item.subItems?.some(sub => sub.id === activeTab);
                  if (!isChildActive) {
                    setExpandedItems(prev => prev.filter(i => i !== item.id));
                  }
                }
              }}
            >
              <button
                type="button"
                data-testid={`sidebar-menu-${item.id}`}
                onClick={() => {
                  if (hasSubItems) {
                    // Click logic: 
                    // 1. Expand/Collapse
                    // 2. If expanding, navigate to interaction module (first sub-item is extraction, second is interaction)
                    // The user wants: "Click DeepRead -> jump to DocInteractionWorkbench"
                    // So we specifically look for 'deepread_interaction' or just the second item?
                    // Let's be generic: if subItems exist, toggle expand.
                    // If opening, set active tab to the desired default child.
                    
                    if (!isExpanded) {
                      setExpandedItems(prev => [...prev, item.id]);
                      // Specific logic for DeepRead: jump to interaction module
                      if (item.id === 'deepread') {
                         setActiveTab('deepread_interaction');
                      } else if (item.subItems) {
                         setActiveTab(item.subItems[0].id);
                      }
                    } else {
                      // If already expanded, just toggle collapse? Or keep it open and maybe navigate?
                      // Usually clicking the parent again collapses it.
                      setExpandedItems(prev => prev.filter(i => i !== item.id));
                    }
                  } else {
                    setActiveTab(item.id);
                  }
                  
                  if (!isCollapsed && !hasSubItems) {
                     // Leaf node click logic
                  } else if (isCollapsed && hasSubItems) {
                    // If collapsed, clicking a parent with subs should probably expand the sidebar first?
                    toggleCollapse();
                    // And then expand the item
                    if (!isExpanded) setExpandedItems(prev => [...prev, item.id]);
                  }
                }}
                className={cn(
                  "w-full flex items-center rounded-xl border transition-all duration-300 relative overflow-hidden",
                  isCollapsed
                    ? "justify-center px-0 py-3"
                    : "gap-4 px-4 py-3.5",
                  isParentVisuallySelected
                    ? 'bg-blue-50/80 shadow-soft-sm border-blue-100/60 text-blue-700 dark:bg-blue-900/20 dark:border-blue-800/40 dark:text-blue-400'
                    : 'bg-transparent border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-100/80 dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-800/60'
                )}
              >
                <Icon 
                  size={20} 
                  strokeWidth={isParentActive ? 2.5 : 2}
                  className={cn(
                    "relative z-10 transition-colors duration-300 shrink-0",
                    isParentActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-500 dark:text-slate-400 group-hover/nav:text-slate-700 dark:group-hover/nav:text-slate-300'
                  )} 
                />

                {/* Label — hidden when collapsed */}
                <div className={cn(
                  "text-left relative z-10 transition-all duration-300 flex items-center justify-between",
                  isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100 flex-1"
                )}>
                  <div className={cn("text-[15px] tracking-tight transition-colors whitespace-nowrap font-sans", isParentActive ? "font-bold text-blue-700 dark:text-blue-300" : "font-medium text-slate-600 dark:text-slate-400 group-hover/nav:text-slate-800 dark:group-hover/nav:text-slate-200")}>
                    {item.label}
                  </div>
                  {hasSubItems && (
                    <ChevronDown size={14} className={cn(
                      "transition-transform duration-300",
                      isParentActive ? "text-blue-500 dark:text-blue-400" : "text-slate-400",
                      isExpanded ? "rotate-180" : ""
                    )} />
                  )}
                </div>

                {isParentVisuallySelected && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] bg-blue-600 dark:bg-blue-400 rounded-r-full shadow-none" />
                )}
              </button>

              {/* Accordion Sub-items (Inline) */}
              {hasSubItems && isExpanded && !isCollapsed && (
                <div className="relative z-10 overflow-hidden">
                  <div className="pt-1 pb-2 pl-4 pr-2 space-y-1">
                    {item.subItems?.map((sub) => {
                      const isSubActive = activeTab === sub.id;
                      return (
                        <button
                          key={sub.id}
                          type="button"
                          data-testid={`sidebar-submenu-${sub.id}`}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            selectSubItem(sub.id);
                          }}
                          className={cn(
                            "relative z-10 w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm transition-all font-sans border overflow-hidden group/sub",
                            isSubActive
                              ? "bg-blue-50/60 shadow-soft-sm border-blue-100/40 text-blue-700 dark:bg-blue-900/20 dark:border-blue-800/30 dark:text-blue-400 font-bold"
                              : "text-slate-500 dark:text-slate-400 border-transparent hover:bg-slate-100/60 dark:hover:bg-slate-800/40 hover:text-slate-800 dark:hover:text-slate-200 font-medium"
                          )}
                        >
                          {isSubActive && (
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] bg-blue-600 dark:bg-blue-400 rounded-r-full shadow-none" />
                          )}
                          <div className={cn(
                            "w-1.5 h-1.5 rounded-full transition-all duration-300 ml-1",
                            isSubActive ? "bg-blue-600 dark:bg-blue-400 shadow-[0_0_8px_rgba(37,99,235,0.4)] scale-125" : "bg-slate-300 dark:bg-slate-600 group-hover/sub:bg-blue-400/50"
                          )} />
                          <span className="truncate">{sub.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Tooltip — only visible when collapsed */}
              {isCollapsed && (
                <div className="
                  absolute left-full top-1/2 -translate-y-1/2 ml-3
                  px-3 py-2 rounded-lg
                  bg-slate-800 dark:bg-slate-700 text-white text-xs font-black font-sans
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
              "w-full flex items-center justify-center rounded-xl bg-white/50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 shadow-sm hover:border-blue-300 dark:hover:border-cyan-400/60 hover:bg-blue-50 dark:hover:bg-slate-800/60 dark:hover:shadow-[0_0_20px_rgba(34,211,238,0.25)] transition-all duration-300 group/theme relative",
              isCollapsed ? "px-2 py-2.5 gap-0" : "px-4 py-2.5 gap-2"
            )}
            title={isDark ? '切换亮色模式' : '切换深色模式'}
          >
            {isDark ?
              <Sun size={18} className="text-amber-400 group-hover/theme:rotate-90 transition-transform shrink-0" /> :
              <Moon size={18} className="text-slate-600 group-hover/theme:-rotate-12 transition-transform shrink-0" />
            }
            <span className={cn(
              "text-sm font-black transition-all font-sans whitespace-nowrap",
              isDark ? "text-white" : "text-black",
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
            <div className="relative shrink-0 group cursor-pointer">
              <div
                className={cn(
                  "rounded-full flex items-center justify-center transition-all duration-300",
                  "bg-indigo-50 text-indigo-600 border border-indigo-100",
                  "dark:bg-indigo-500/20 dark:text-indigo-300 dark:border-indigo-500/30",
                  "shadow-sm dark:shadow-[0_0_15px_rgba(99,102,241,0.3)] shadow-indigo-200/50 font-bold font-sans select-none",
                  isCollapsed ? "w-8 h-8 text-xs" : "w-10 h-10 text-base"
                )}
              >
                {user.name.charAt(0).toUpperCase()}
              </div>
            </div>
            {/* User info — hidden when collapsed */}
            <div className={cn(
              "min-w-0 transition-all duration-300 group cursor-pointer overflow-hidden",
              isCollapsed ? "opacity-0 w-0" : "flex-1 opacity-100"
            )}>
              <div className="text-[10px] font-bold text-slate-400 dark:text-slate-500 mb-0.5 font-sans tracking-wide whitespace-nowrap">欢迎回来</div>
              <div className="text-sm font-bold truncate text-slate-700 dark:text-slate-200 font-sans group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors" title={user.name}>{user.name}</div>
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
                "w-full flex items-center justify-center rounded-xl bg-blue-900/80 hover:bg-blue-800 text-white font-black shadow-lg shadow-blue-950/30 hover:shadow-blue-900/50 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 group",
                isCollapsed ? "px-2 py-2.5 gap-0" : "px-4 py-2.5 gap-2"
              )}
            title="登录账号"
          >
            <User size={16} className="group-hover:animate-bounce shrink-0" />
            <span className={cn(
              "transition-all duration-300 whitespace-nowrap font-sans font-black",
              isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
            )}>登录账号</span>
          </button>
        )}
      </div>

    </div>
  );
};
