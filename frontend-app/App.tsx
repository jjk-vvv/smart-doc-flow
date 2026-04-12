import React, { startTransition, useCallback, useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { BookOpen, Database, FileSearch, Home } from 'lucide-react';

import { AccountSecurityModal } from './components/AccountSecurityModal';
import { AuthModal } from './components/AuthModal';
import { MobileAvatarButton } from './components/MobileAvatarButton';
import {
  MobilePersonalDrawer,
  type MobileDrawerItem,
} from './components/MobilePersonalDrawer';
import { Sidebar } from './components/Sidebar';
import { cn } from './lib/utils';
import { Dashboard } from './pages/dashboard/Dashboard';
import { MobileDashboard } from './pages/dashboard/MobileDashboard';
import { DeepReadWorkbench } from './pages/deepread/DeepReadWorkbench';
import { DocInteractionWorkbench } from './pages/deepread/DocInteractionWorkbench';
import { MobileDeepReadPage } from './pages/deepread/MobileDeepReadPage';
import { FusionGrid } from './pages/fusion/FusionGrid';
import { UserGuide } from './pages/guide/UserGuide';
import { KnowledgeNexus } from './pages/knowledge-nexus/KnowledgeNexus';
import { OnboardingFlow } from './pages/onboarding/OnboardingFlow';
import { getCurrentUser, logoutAuth, type AuthUser } from './shared/api/auth';

type AppTab =
  | 'dashboard'
  | 'deepread_interaction'
  | 'deepread_extraction'
  | 'fusion'
  | 'nexus'
  | 'guide'
  | 'mine';

type NormalizedTab = Exclude<AppTab, 'mine'>;

const ACTIVE_TAB_KEY = 'smart_doc_flow.frontend_app.active_tab';
const THEME_KEY = 'smart_doc_flow.frontend_app.theme';
const ONBOARDING_KEY = 'smart_doc_flow.has_seen_onboarding';
const MOBILE_BREAKPOINT = 1024;
const MOBILE_DRAWER_EVENT = 'open-mobile-drawer';

const normalizeMobileTab = (tab: NormalizedTab): NormalizedTab => {
  if (tab === 'nexus') return 'dashboard';
  return tab;
};

const normalizeTab = (value: string | null | undefined): NormalizedTab => {
  if (value === 'mine') return 'dashboard';
  if (
    value === 'dashboard' ||
    value === 'deepread_interaction' ||
    value === 'deepread_extraction' ||
    value === 'fusion' ||
    value === 'nexus' ||
    value === 'guide'
  ) {
    return value;
  }
  return 'dashboard';
};

const isProtectedTab = (tab: NormalizedTab): boolean => tab === 'deepread_extraction';

const getAvatarText = (user: AuthUser): string => {
  const source = String(user?.name || user?.email || '').trim();
  return source ? source.slice(0, 1).toUpperCase() : '';
};

const readInitialTheme = (): boolean => {
  if (typeof window === 'undefined') return false;
  const stored = window.localStorage.getItem(THEME_KEY);
  if (stored === 'dark') return true;
  if (stored === 'light') return false;
  if (document.documentElement.classList.contains('dark')) return true;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
};

const readInitialTab = (): NormalizedTab => {
  if (typeof window === 'undefined') return 'dashboard';
  const nextTab = normalizeTab(window.localStorage.getItem(ACTIVE_TAB_KEY));
  return window.innerWidth < MOBILE_BREAKPOINT ? normalizeMobileTab(nextTab) : nextTab;
};

const readInitialOnboarding = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(ONBOARDING_KEY) !== 'true';
};

const MOBILE_DRAWER_ITEMS: MobileDrawerItem[] = [
  { id: 'guide', label: '操作指南', desc: '查看平台介绍与使用路径', icon: BookOpen },
];

const MOBILE_BOTTOM_TABS: Array<{
  id: 'dashboard' | 'deepread_extraction' | 'fusion';
  label: string;
  icon: MobileDrawerItem['icon'];
}> = [
  { id: 'dashboard', label: '首页', icon: Home },
  { id: 'deepread_extraction', label: '提取', icon: FileSearch },
  { id: 'fusion', label: '融合', icon: Database },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<NormalizedTab>(() => readInitialTab());
  const [isDark, setIsDark] = useState(() => readInitialTheme());
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < MOBILE_BREAKPOINT : false,
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showAccountSecurityModal, setShowAccountSecurityModal] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(() => readInitialOnboarding());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [user, setUser] = useState<AuthUser>(null);
  const [pendingProtectedTab, setPendingProtectedTab] = useState<NormalizedTab | null>(null);
  const [mobileExtractionMode, setMobileExtractionMode] = useState<'summary' | 'workbench'>(
    'summary',
  );

  const avatarText = useMemo(() => getAvatarText(user), [user]);
  const showMobileWorkbench =
    isMobile && Boolean(user) && activeTab === 'deepread_extraction' && mobileExtractionMode === 'workbench';

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
    window.localStorage.setItem(THEME_KEY, isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    const handleResize = () => {
      const nextMobile = window.innerWidth < MOBILE_BREAKPOINT;
      setIsMobile(nextMobile);
      if (!nextMobile) setDrawerOpen(false);
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(ACTIVE_TAB_KEY, activeTab);
  }, [activeTab]);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      try {
        const payload = await getCurrentUser();
        if (!cancelled) setUser(payload?.user ?? null);
      } catch {
        if (!cancelled) setUser(null);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (isMobile && activeTab === 'nexus') {
      setActiveTab('dashboard');
      setDrawerOpen(false);
    }
  }, [activeTab, isMobile]);

  useEffect(() => {
    if (user || !isProtectedTab(activeTab)) return;
    setMobileExtractionMode('summary');
    setPendingProtectedTab(activeTab);
    setShowLoginModal(true);
    if (activeTab !== 'dashboard') {
      startTransition(() => setActiveTab('dashboard'));
    }
  }, [activeTab, user]);

  useEffect(() => {
    const openDrawer = () => setDrawerOpen(true);
    window.addEventListener(MOBILE_DRAWER_EVENT, openDrawer);
    return () => window.removeEventListener(MOBILE_DRAWER_EVENT, openDrawer);
  }, []);

  const openDrawer = useCallback(() => setDrawerOpen(true), []);
  const toggleTheme = useCallback(() => setIsDark((prev) => !prev), []);

  const handleTabChange = useCallback((next: AppTab) => {
    if (next === 'mine') {
      setDrawerOpen(true);
      return;
    }

    const normalized = isMobile ? normalizeMobileTab(normalizeTab(next)) : normalizeTab(next);
    if (isProtectedTab(normalized) && !user) {
      setPendingProtectedTab(normalized);
      setShowLoginModal(true);
      setDrawerOpen(false);
      return;
    }
    startTransition(() => setActiveTab(normalized));
    setDrawerOpen(false);
    if (normalized !== 'deepread_extraction') {
      setMobileExtractionMode('summary');
      setPendingProtectedTab(null);
    }
  }, [isMobile, user]);

  const handleLogout = useCallback(async () => {
    try {
      await logoutAuth();
    } catch (error) {
      console.error('Logout failed:', error);
    } finally {
      setUser(null);
      setDrawerOpen(false);
      setShowAccountSecurityModal(false);
      setActiveTab('dashboard');
      setMobileExtractionMode('summary');
      setPendingProtectedTab(null);
    }
  }, []);

  const renderDesktopContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <div className="h-screen overflow-hidden p-4">
            <Dashboard />
          </div>
        );
      case 'deepread_interaction':
        return (
          <div className="h-screen overflow-hidden p-4">
            <DocInteractionWorkbench />
          </div>
        );
      case 'deepread_extraction':
        if (!user) {
          return (
            <div className="h-screen flex items-center justify-center p-6">
              <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-white/10 dark:bg-slate-900">
                <div className="text-base font-semibold text-slate-900 dark:text-slate-100">Login Required</div>
                <div className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                  Please login to access DeepRead extraction.
                </div>
                <button
                  type="button"
                  onClick={() => setShowLoginModal(true)}
                  className="mt-4 rounded-full bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500"
                >
                  Login
                </button>
              </div>
            </div>
          );
        }
        return <DeepReadWorkbench isSidebarCollapsed={sidebarCollapsed} />;
      case 'fusion':
        return (
          <div className="h-screen overflow-hidden p-4">
            <FusionGrid />
          </div>
        );
      case 'nexus':
        return (
          <div className="h-screen overflow-hidden p-4">
            <KnowledgeNexus />
          </div>
        );
      case 'guide':
        return <UserGuide onBackToDashboard={() => handleTabChange('dashboard')} />;
      default:
        return null;
    }
  };

  const renderMobileContent = () => {
    if (showMobileWorkbench) {
      return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
          <div className="sticky top-0 z-40 flex items-center justify-between border-b border-slate-200/70 bg-white/92 px-4 py-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/92">
            <button
              type="button"
              onClick={() => setMobileExtractionMode('summary')}
              className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-700 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-200"
            >
              返回解析概览
            </button>
            <MobileAvatarButton
              avatarText={avatarText}
              onClick={openDrawer}
              className="shadow-sm dark:shadow-none"
            />
          </div>
          <DeepReadWorkbench isSidebarCollapsed={false} />
        </div>
      );
    }

    switch (activeTab) {
      case 'dashboard':
        return <MobileDashboard user={user} onNavigate={handleTabChange} onOpenDrawer={openDrawer} />;
      case 'deepread_interaction':
        return <DocInteractionWorkbench />;
      case 'deepread_extraction':
        if (!user) {
          return (
            <div className="min-h-screen bg-slate-50 px-4 pt-24 dark:bg-slate-950">
              <div className="mx-auto max-w-md rounded-3xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-white/10 dark:bg-slate-900">
                <div className="text-base font-semibold text-slate-900 dark:text-slate-100">Login Required</div>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                  Please login before starting file extraction.
                </p>
                <button
                  type="button"
                  onClick={() => setShowLoginModal(true)}
                  className="mt-4 rounded-full bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-500"
                >
                  Login
                </button>
              </div>
            </div>
          );
        }
        return (
          <MobileDeepReadPage
            onOpenLegacyWorkbench={() => setMobileExtractionMode('workbench')}
          />
        );
      case 'fusion':
        return <FusionGrid />;
      case 'nexus':
        return <MobileDashboard user={user} onNavigate={handleTabChange} onOpenDrawer={openDrawer} />;
      case 'guide':
        return <UserGuide onBackToDashboard={() => handleTabChange('dashboard')} />;
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <AuthModal
        show={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onLoginSuccess={(nextUser) => {
          setUser(nextUser);
          if (pendingProtectedTab) {
            startTransition(() => setActiveTab(pendingProtectedTab));
            setMobileExtractionMode('summary');
            setPendingProtectedTab(null);
          }
          setShowLoginModal(false);
        }}
      />
      <AccountSecurityModal
        show={showAccountSecurityModal}
        user={user}
        onClose={() => setShowAccountSecurityModal(false)}
        onLoggedOut={() => {
          setUser(null);
          setShowAccountSecurityModal(false);
        }}
      />
      {showOnboarding && (
        <OnboardingFlow
          onComplete={() => setShowOnboarding(false)}
          onOpenLogin={() => setShowLoginModal(true)}
        />
      )}

      <AnimatePresence>
        {drawerOpen && (
          <MobilePersonalDrawer
            user={user}
            avatarText={avatarText}
            isDark={isDark}
            activeTab={activeTab}
            items={MOBILE_DRAWER_ITEMS}
            onClose={() => setDrawerOpen(false)}
            onNavigate={(target) => handleTabChange(target as AppTab)}
            onToggleTheme={toggleTheme}
            onOpenAccountSecurity={() => {
              setDrawerOpen(false);
              user ? setShowAccountSecurityModal(true) : setShowLoginModal(true);
            }}
            onResetOnboarding={() => {
              window.localStorage.removeItem(ONBOARDING_KEY);
              setDrawerOpen(false);
              setShowOnboarding(true);
            }}
            onLogin={() => {
              setDrawerOpen(false);
              setShowLoginModal(true);
            }}
            onLogout={handleLogout}
          />
        )}
      </AnimatePresence>

      {isMobile ? (
        <div className="relative min-h-screen overflow-x-hidden">
          {!showMobileWorkbench && activeTab !== 'dashboard' && activeTab !== 'deepread_extraction' && (
            <div className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-end px-4 pt-[max(1rem,env(safe-area-inset-top))]">
              <MobileAvatarButton
                avatarText={avatarText}
                onClick={openDrawer}
                className="pointer-events-auto shadow-sm dark:shadow-none"
              />
            </div>
          )}
          <div aria-hidden={drawerOpen}>{renderMobileContent()}</div>
          {!showMobileWorkbench && (
            <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200/80 bg-white/90 pb-[env(safe-area-inset-bottom)] shadow-sm backdrop-blur-2xl dark:border-white/[0.05] dark:bg-[#0B1120]/90">
              <div className="mx-auto flex h-[56px] w-full max-w-md items-center justify-between px-6">
                {MOBILE_BOTTOM_TABS.map((item) => {
                  const Icon = item.icon;
                  const active = activeTab === item.id;

                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleTabChange(item.id)}
                      className="group relative flex h-full flex-1 flex-col items-center justify-center transition-transform active:scale-95"
                    >
                      <span className="relative z-10 flex flex-col items-center justify-center gap-1">
                        <div
                          className={cn(
                            'relative flex h-[28px] w-[48px] items-center justify-center rounded-full transition-colors duration-300',
                            active ? 'bg-cyan-50 dark:bg-cyan-900/30' : 'bg-transparent',
                          )}
                        >
                          <Icon
                            size={20}
                            strokeWidth={active ? 2.5 : 2}
                            className={cn(
                              'transition-colors duration-300',
                              active
                                ? 'text-cyan-600 dark:text-cyan-300'
                                : 'text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-300'
                            )}
                          />
                        </div>
                        <span
                          className={cn(
                            'text-[10px] transition-colors duration-300',
                            active
                              ? 'font-semibold text-cyan-700 dark:text-cyan-300'
                              : 'font-medium text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-300'
                          )}
                        >
                          {item.label}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </nav>
          )}
        </div>
      ) : (
        <div className="flex min-h-screen">
          <Sidebar
            activeTab={activeTab}
            setActiveTab={(nextTab) => handleTabChange(nextTab as AppTab)}
            isDark={isDark}
            toggleTheme={toggleTheme}
            isCollapsed={sidebarCollapsed}
            toggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
            user={user}
            setUser={(nextUser) => setUser(nextUser)}
            setShowLoginModal={setShowLoginModal}
            setShowAccountSecurityModal={setShowAccountSecurityModal}
          />
          <main
            aria-hidden={drawerOpen}
            className={cn(
              'min-h-screen flex-1 transition-[margin-left] duration-300 ease-in-out',
              sidebarCollapsed ? 'ml-[72px]' : 'ml-72',
            )}
          >
            {renderDesktopContent()}
          </main>
        </div>
      )}
    </div>
  );
}
