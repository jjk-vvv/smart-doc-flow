import React from 'react';
import {
  Home,
  FileSearch,
  Database,
  GitGraph,
  Moon,
  Sun,
  User,
  LogOut,
  ArrowRight,
  ChevronLeft,
  ChevronDown,
  Bot,
  FileText,
  Shield
} from 'lucide-react';
import LogoImage from '../assets/app-logo.png';
import { logoutAuth, type AuthUser } from '../shared/api/auth';
import { cn } from '../lib/utils';
import { motion } from 'framer-motion';

const SIDEBAR_TEXT = {
  collapseSidebar: '收起侧边栏',
  expandSidebar: '展开侧边栏',
  logoAlt: '平台徽标',
  appTitle: '文枢智动',
  appSubtitle: '你的智能文档流转平台',
  guideLabel: '平台操作指南',
  lightMode: '亮色模式',
  darkMode: '深色模式',
  switchToLight: '切换亮色模式',
  switchToDark: '切换深色模式',
  welcomeBack: '欢迎回来',
  accountSecurity: '账户安全',
  logout: '退出登录',
  login: '登录账号',
} as const;

type SidebarMenuLeaf = {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
};

type SidebarMenuItem = SidebarMenuLeaf & {
  subItems?: SidebarMenuLeaf[];
};

const MENU_ITEMS: readonly SidebarMenuItem[] = [
  { id: 'dashboard', label: '文档中心', icon: Home },
  {
    id: 'deepread',
    label: '智能文档解析',
    icon: FileSearch,
    subItems: [
      { id: 'doc-processing', label: 'AI文档处理', icon: Bot },
      { id: 'deepread_extraction', label: 'AI信息提取', icon: FileText },
    ],
  },
  { id: 'fusion', label: '自定义智能填表', icon: Database },
  { id: 'nexus', label: '全域知识图谱', icon: GitGraph },
];

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isDark: boolean;
  toggleTheme: () => void;
  isCollapsed: boolean;
  toggleCollapse: () => void;
  user: AuthUser;
  setUser: (user: AuthUser) => void;
  setShowLoginModal: (show: boolean) => void;
  setShowAccountSecurityModal: (show: boolean) => void;
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
  setShowLoginModal,
  setShowAccountSecurityModal
}) => {

  const [expandedItems, setExpandedItems] = React.useState<string[]>([]);
  
  React.useEffect(() => {
    const parent = MENU_ITEMS.find(item => item.subItems?.some(sub => sub.id === activeTab));
    if (parent) {
      setExpandedItems(prev => prev.includes(parent.id) ? prev : [...prev, parent.id]);
    } else {
      setExpandedItems([]);
    }
  }, [activeTab]);

  const handleLogout = async () => {
    try {
      await logoutAuth();
      setUser(null);
    } catch (err) {
      console.error('Logout failed:', err);
      setUser(null);
    }
  };

  const selectSubItem = (subId: string) => {
    setActiveTab(subId);
  };

  return (
    <div className={cn(
      "bg-gradient-to-b from-slate-50 via-blue-50 to-blue-100 dark:from-[#0B1120] dark:via-[#0f172a] dark:to-[#0B1120] backdrop-blur-xl border-r border-slate-200 dark:border-slate-800 flex flex-col h-screen fixed left-0 top-0 z-50 shadow-2xl group/sidebar",
      "transition-[width] duration-300 ease-in-out",
      isCollapsed ? "w-[72px]" : "w-72"
    )}>

      <div
        className="absolute -right-4 top-1/2 -translate-y-1/2 h-24 w-8 z-[60] flex items-center justify-center cursor-pointer group/toggle opacity-0 group-hover/sidebar:opacity-100 transition-opacity duration-300"
        onClick={toggleCollapse}
        title={isCollapsed ? SIDEBAR_TEXT.expandSidebar : SIDEBAR_TEXT.collapseSidebar}
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

      <div className={cn(
        "h-auto py-5 flex items-center border-b border-slate-200 dark:border-slate-800/80 relative overflow-hidden group",
        isCollapsed ? "justify-center px-3" : "justify-between px-6"
      )}>
        <div className={cn(
          "flex items-center relative z-10",
          isCollapsed ? "justify-center" : "gap-3 w-full"
        )}>
          <div className={cn(
            "shrink-0 flex items-center justify-center relative transition-all duration-300",
            isCollapsed ? "w-10 h-10" : "w-11 h-11 ml-1.5"
          )}>
            <img src={LogoImage} alt={SIDEBAR_TEXT.logoAlt} className={cn(
              "object-contain dark:drop-shadow-sm relative z-10 transition-all duration-300 hover:scale-105",
              isCollapsed ? "w-8 h-8" : "w-10 h-10"
            )} />
          </div>
          <div className={cn(
            "flex flex-col items-start gap-1 transition-all duration-300",
            isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
          )}>
            <div className="flex items-center gap-2.5 w-full mt-0.5">
              <h1 className="font-sans font-bold text-[17px] tracking-wide text-slate-800 dark:text-slate-100 leading-none drop-shadow-[0_0_2px_rgba(255,255,255,0.5)] dark:drop-shadow-none truncate whitespace-nowrap">{SIDEBAR_TEXT.appTitle}</h1>
              <motion.button
                onClick={() => setActiveTab('guide')}
                className="flex items-center gap-0.5 text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors duration-300 group/btn cursor-pointer shrink-0 mt-[2px]"
                title={SIDEBAR_TEXT.guideLabel}
                animate={{ y: [0, -2, 0, 2, 0] }}
                transition={{ duration: 2.5, ease: "easeInOut", repeat: Infinity }}
              >
                <span className="text-[10px] font-bold leading-none tracking-wide">{SIDEBAR_TEXT.guideLabel}</span>
                <ArrowRight size={10} className="group-hover/btn:translate-x-[2px] transition-transform duration-300" strokeWidth={2.5} />
              </motion.button>
            </div>
            <p className="text-[11px] font-medium tracking-wide truncate bg-clip-text text-transparent bg-[linear-gradient(110deg,#64748b,45%,#cbd5e1,55%,#64748b)] dark:bg-[linear-gradient(110deg,#94a3b8,45%,#f8fafc,55%,#94a3b8)] bg-[length:200%_auto] animate-text-shimmer pb-[1px]">{SIDEBAR_TEXT.appSubtitle}</p>
          </div>
        </div>
      </div>

      <nav className={cn(
        "flex-1 py-8 space-y-2",
        isCollapsed ? "px-2" : "px-4"
      )}>
        {MENU_ITEMS.map((item) => {
          const Icon = item.icon;
          const isParentActive = activeTab === item.id || (item.subItems && item.subItems.some(sub => sub.id === activeTab));
          const hasSubItems = item.subItems && item.subItems.length > 0;
          const isExpanded = expandedItems.includes(item.id);
          
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
                    if (!isExpanded) {
                      setExpandedItems(prev => [...prev, item.id]);
                      if (item.id === 'deepread') {
                         setActiveTab('doc-processing');
                      } else if (item.subItems) {
                         setActiveTab(item.subItems[0].id);
                      }
                    } else {
                      setExpandedItems(prev => prev.filter(i => i !== item.id));
                    }
                  } else {
                    setActiveTab(item.id);
                  }

                  if (isCollapsed && hasSubItems) {
                    toggleCollapse();
                    if (!isExpanded) setExpandedItems(prev => [...prev, item.id]);
                  }
                }}
                className={cn(
                  "w-full flex items-center rounded-[10px] border transition-all duration-300 relative overflow-hidden group/navbtn active:scale-[0.98]",
                  isCollapsed
                    ? "justify-center px-0 py-2.5"
                    : "gap-3.5 px-3.5 py-2.5",
                  isParentVisuallySelected
                    ? 'bg-gradient-to-r from-blue-50/80 to-transparent shadow-[0_1px_3px_rgba(37,99,235,0.06)] border-blue-100/60 text-slate-900 dark:from-blue-500/10 dark:to-transparent dark:border-blue-500/20 dark:text-slate-100'
                    : 'bg-transparent border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-100/80 hover:shadow-[0_1px_2px_rgba(0,0,0,0.02)] dark:text-slate-400 dark:hover:text-slate-200 dark:hover:bg-slate-800/50'
                )}
              >
                <Icon 
                  size={18} 
                  strokeWidth={isParentActive ? 2.5 : 2}
                  className={cn(
                    "relative z-10 transition-all duration-300 shrink-0",
                    isParentActive ? 'text-blue-600 dark:text-blue-400 scale-105' : 'text-slate-500 dark:text-slate-400 group-hover/navbtn:text-slate-700 dark:group-hover/navbtn:text-slate-300 group-hover/navbtn:scale-105'
                  )} 
                />

                <div className={cn(
                  "text-left relative z-10 transition-all duration-300 flex items-center justify-between",
                  isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100 flex-1",
                  !isParentActive && "group-hover/navbtn:translate-x-0.5"
                )}>
                  <div className={cn("text-[14px] tracking-tight transition-colors whitespace-nowrap font-sans", isParentActive ? "font-semibold text-slate-900 dark:text-slate-100" : "font-medium text-slate-600 dark:text-slate-400 group-hover/navbtn:text-slate-900 dark:group-hover/navbtn:text-slate-200")}>
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
                  <div className="absolute left-1 top-1/2 -translate-y-1/2 h-[18px] w-1 bg-blue-600 dark:bg-blue-400 rounded-full shadow-[0_0_8px_rgba(37,99,235,0.4)]" />
                )}
              </button>

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
                            "relative z-10 w-full flex items-center gap-2.5 px-3.5 py-2 rounded-[10px] text-[13px] transition-all duration-300 font-sans border overflow-hidden group/sub active:scale-[0.98]",
                            isSubActive
                              ? "bg-gradient-to-r from-blue-50/60 to-transparent shadow-[0_1px_3px_rgba(37,99,235,0.06)] border-blue-100/40 text-slate-900 dark:from-blue-500/10 dark:to-transparent dark:border-blue-500/20 dark:text-slate-100 font-semibold"
                              : "text-slate-500 dark:text-slate-400 border-transparent hover:bg-slate-100/60 dark:hover:bg-slate-800/50 hover:text-slate-800 dark:hover:text-slate-200 font-medium hover:shadow-[0_1px_2px_rgba(0,0,0,0.02)]"
                          )}
                        >
                          {isSubActive && (
                            <div className="absolute left-1 top-1/2 -translate-y-1/2 h-[14px] w-[3px] bg-blue-600 dark:bg-blue-400 rounded-full shadow-[0_0_8px_rgba(37,99,235,0.4)]" />
                          )}
                          <div className={cn(
                            "w-1.5 h-1.5 rounded-full transition-all duration-300 ml-2",
                            isSubActive ? "bg-blue-600 dark:bg-blue-400 shadow-[0_0_8px_rgba(37,99,235,0.4)] scale-125" : "bg-slate-300 dark:bg-slate-600 group-hover/sub:bg-blue-400/50"
                          )} />
                          <span className="truncate transition-transform duration-300 group-hover/sub:translate-x-0.5">{sub.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

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

      <div className={cn(
        "border-t border-slate-200 dark:border-slate-800/80 bg-background/50 backdrop-blur-md flex flex-col gap-4",
        isCollapsed ? "p-3" : "p-6"
      )}>
        <div className="mb-2 w-full transition-all duration-300">
          <button
            onClick={toggleTheme}
            className={cn(
              "w-full flex items-center justify-center rounded-[10px] bg-white/50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/50 shadow-sm hover:border-blue-300 dark:hover:border-slate-600 hover:bg-blue-50/50 dark:hover:bg-slate-700/50 hover:shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:hover:shadow-[0_2px_8px_rgba(0,0,0,0.2)] transition-all duration-300 group/theme relative active:scale-[0.98]",
              isCollapsed ? "px-2 py-2 gap-0" : "px-3.5 py-2 gap-2"
            )}
            title={isDark ? SIDEBAR_TEXT.switchToLight : SIDEBAR_TEXT.switchToDark}
          >
            {isDark ?
              <Sun size={16} className="text-amber-400 group-hover/theme:rotate-90 transition-transform duration-300 shrink-0" /> :
              <Moon size={16} className="text-slate-500 group-hover/theme:-rotate-12 transition-transform duration-300 shrink-0" />
            }
            <span className={cn(
              "text-[13px] font-medium transition-all font-sans whitespace-nowrap",
              isDark ? "text-slate-200" : "text-slate-600 group-hover/theme:text-slate-800",
              isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
            )}>
              {isDark ? SIDEBAR_TEXT.lightMode : SIDEBAR_TEXT.darkMode}
            </span>
          </button>
        </div>

        {user ? (
          <div className={cn(
            "flex items-center rounded-[10px] bg-white/50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/50 shadow-sm hover:shadow-[0_2px_8px_rgba(0,0,0,0.02)] dark:hover:shadow-[0_2px_8px_rgba(0,0,0,0.2)] transition-all duration-300",
            isCollapsed ? "justify-center p-1.5" : "gap-2.5 p-2.5"
          )}>
            <button
              type="button"
              onClick={() => setShowAccountSecurityModal(true)}
              className="relative shrink-0 rounded-full transition-transform duration-300 hover:scale-[1.05]"
              title={SIDEBAR_TEXT.accountSecurity}
            >
              <div
                className={cn(
                  "rounded-full flex items-center justify-center transition-all duration-300",
                  "bg-blue-50 text-blue-600 border border-blue-100",
                  "dark:bg-blue-500/20 dark:text-blue-300 dark:border-blue-500/30",
                  "shadow-sm dark:shadow-[0_0_10px_rgba(59,130,246,0.2)] shadow-blue-200/50 font-semibold font-sans select-none",
                  isCollapsed ? "w-7 h-7 text-xs" : "w-8 h-8 text-sm"
                )}
              >
                {user.name.charAt(0).toUpperCase()}
              </div>
            </button>
            <div className={cn(
              "min-w-0 transition-all duration-300 group cursor-pointer overflow-hidden",
              isCollapsed ? "opacity-0 w-0" : "flex-1 opacity-100"
            )}>
              <div className="text-[9px] font-medium text-slate-400 dark:text-slate-500 mb-0.5 font-sans tracking-wide whitespace-nowrap uppercase">{SIDEBAR_TEXT.welcomeBack}</div>
              <div className="text-[13px] font-medium truncate text-slate-700 dark:text-slate-200 font-sans group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors" title={user.name}>{user.name}</div>
            </div>
            {!isCollapsed && (
              <div className="flex items-center gap-0.5">
                <button
                  type="button"
                  onClick={() => setShowAccountSecurityModal(true)}
                  className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-900/30 dark:hover:text-blue-300"
                  title={SIDEBAR_TEXT.accountSecurity}
                >
                  <Shield size={14} />
                </button>
                <button
                  onClick={handleLogout}
                  className="p-1.5 hover:bg-red-50 dark:hover:bg-red-900/20 text-slate-400 hover:text-red-500 rounded-md transition-colors"
                  title={SIDEBAR_TEXT.logout}
                >
                  <LogOut size={14} />
                </button>
              </div>
            )}
          </div>
        ) : (
          <button
            onClick={() => setShowLoginModal(true)}
            className={cn(
                "w-full flex items-center justify-center rounded-[10px] bg-blue-600 dark:bg-blue-600/90 hover:bg-blue-500 dark:hover:bg-blue-500 text-white font-medium shadow-[0_2px_8px_rgba(37,99,235,0.2),inset_0_1px_0_rgba(255,255,255,0.15)] dark:shadow-[0_2px_10px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.1)] hover:shadow-[0_4px_12px_rgba(37,99,235,0.3),inset_0_1px_0_rgba(255,255,255,0.2)] dark:hover:shadow-[0_4px_15px_rgba(37,99,235,0.2),inset_0_1px_0_rgba(255,255,255,0.15)] hover:-translate-y-0.5 active:scale-[0.98] transition-all duration-300 group ring-1 ring-transparent dark:border-t dark:border-blue-400/30",
                isCollapsed ? "px-2 py-2 gap-0" : "px-3.5 py-2 gap-2"
              )}
            title={SIDEBAR_TEXT.login}
          >
            <User size={15} className="transition-transform duration-300 group-hover:scale-110 shrink-0" />
            <span className={cn(
              "text-[13px] transition-all duration-300 whitespace-nowrap font-sans",
              isCollapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100"
            )}>{SIDEBAR_TEXT.login}</span>
          </button>
        )}
      </div>

    </div>
  );
};
