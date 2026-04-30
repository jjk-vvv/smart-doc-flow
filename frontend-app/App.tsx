import React, { startTransition, useCallback, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { BookOpen, Database, FileSearch, Home, UserCircle2 } from 'lucide-react';

import { AccountSecurityModal } from './components/AccountSecurityModal';
import { PlatformAssistant } from './features/platform-assistant/components/PlatformAssistant';
import { AuthModal } from './components/AuthModal';
import { MobileProfilePage } from './pages/profile/MobileProfilePage';
import { Sidebar } from './components/Sidebar';
import { cn } from './lib/utils';
import { Dashboard } from './pages/dashboard/Dashboard';
import { MobileDashboard } from './pages/dashboard/MobileDashboard';
import { DeepReadWorkbench } from './pages/deepread/DeepReadWorkbench';
import { DocProcessingWorkbench } from './pages/doc-processing/DocProcessingWorkbench';
import { MobileDeepReadPage } from './pages/deepread/MobileDeepReadPage';
import { FusionGrid } from './pages/fusion/FusionGrid';
import { KnowledgeNexus } from './pages/knowledge-nexus/KnowledgeNexus';
import { OnboardingFlow } from './pages/onboarding/OnboardingFlow';
import { getCurrentUser, logoutAuth, type AuthUser } from './shared/api/auth';
import { getResponsiveDeviceClass, useResponsiveDevice } from './shared/hooks/useResponsiveDevice';
import { useVisualViewport } from './shared/hooks/useVisualViewport';

type AppTab =
  | 'dashboard'
  | 'doc-processing'
  | 'deepread_extraction'
  | 'fusion'
  | 'nexus'
  | 'mine';

type NormalizedTab = AppTab;

const ACTIVE_TAB_KEY = 'smart_doc_flow.frontend_app.active_tab';
const THEME_KEY = 'smart_doc_flow.frontend_app.theme';
const ONBOARDING_KEY = 'smart_doc_flow.has_seen_onboarding';
const AUTH_SESSION_HINT_KEY = 'smart_doc_flow.auth.session_hint';
const isMobileViewportWidth = (width: number): boolean =>
  getResponsiveDeviceClass(width) !== 'desktop';

const normalizeMobileTab = (tab: NormalizedTab): NormalizedTab => {
  if (tab === 'nexus') return 'dashboard';
  return tab;
};

const normalizeTab = (value: string | null | undefined): NormalizedTab => {
  if (
    value === 'dashboard' ||
    value === 'doc-processing' ||
    value === 'deepread_extraction' ||
    value === 'fusion' ||
    value === 'nexus' ||
    value === 'mine'
  ) {
    return value;
  }
  return 'dashboard';
};

const readRequestedTabFromUrl = (): NormalizedTab | null => {
  if (typeof window === 'undefined') return null;
  try {
    const url = new URL(window.location.href);
    const queryTab = url.searchParams.get('tab');
    return queryTab ? normalizeTab(queryTab) : null;
  } catch {
    return null;
  }
};

const syncActiveTabLocation = (activeTab: NormalizedTab): void => {
  if (typeof window === 'undefined') return;
  try {
    const url = new URL(window.location.href);
    if (activeTab === 'dashboard') {
      url.searchParams.delete('tab');
    } else {
      url.searchParams.set('tab', activeTab);
    }
    const nextUrl = `${url.pathname}${url.search}${url.hash}`;
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (nextUrl !== currentUrl) {
      window.history.replaceState(null, '', nextUrl);
    }
  } catch {
    // Ignore history sync failures so local navigation still works.
  }
};

const isProtectedTab = (tab: NormalizedTab): boolean => tab === 'deepread_extraction';

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
  const requestedTab = readRequestedTabFromUrl();
  const nextTab = requestedTab ?? normalizeTab(window.localStorage.getItem(ACTIVE_TAB_KEY));
  return isMobileViewportWidth(window.innerWidth) ? normalizeMobileTab(nextTab) : nextTab;
};

const readInitialOnboarding = (): boolean => {
  if (typeof window === 'undefined') return false;
  if (window.localStorage.getItem(ONBOARDING_KEY) === 'true') return false;
  const requestedTab = readRequestedTabFromUrl();
  if (requestedTab && requestedTab !== 'dashboard') return false;
  if (window.localStorage.getItem(AUTH_SESSION_HINT_KEY) === '1') return false;
  return true;
};

const MOBILE_BOTTOM_TABS: Array<{
  id: 'dashboard' | 'doc-processing' | 'deepread_extraction' | 'fusion' | 'mine';
  label: string;
  icon: React.ElementType;
}> = [
  { id: 'dashboard', label: '首页', icon: Home },
  { id: 'doc-processing', label: '文档处理', icon: BookOpen },
  { id: 'deepread_extraction', label: 'AI提取', icon: FileSearch },
  { id: 'fusion', label: '智能填表', icon: Database },
  { id: 'mine', label: '我的', icon: UserCircle2 },
];

type AiApiBrowserConsoleLogEntry = {
  id?: number;
  logger?: string;
  message?: string;
};

type AiApiBrowserConsolePayload = {
  enabled?: boolean;
  entries?: AiApiBrowserConsoleLogEntry[];
  next_since?: number;
  latest_id?: number;
};

const shouldMirrorAiApiLogsToBrowserConsole = (): boolean => {
  const flag = String(import.meta.env.VITE_AI_API_BROWSER_CONSOLE_LOGS ?? '').trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(flag)) return true;
  if (['0', 'false', 'no', 'off'].includes(flag)) return false;
  return Boolean(import.meta.env.DEV);
};

const startAiApiBrowserConsoleMirror = (): (() => void) | undefined => {
  if (typeof window === 'undefined' || !shouldMirrorAiApiLogsToBrowserConsole()) {
    return undefined;
  }

  let stopped = false;
  let timer: number | undefined;
  let sinceId = 0;

  const schedule = (delayMs: number) => {
    if (stopped) return;
    timer = window.setTimeout(poll, delayMs);
  };

  const poll = async () => {
    try {
      const response = await fetch(
        `/api/diagnostics/ai-api-logs?since_id=${encodeURIComponent(String(sinceId))}&limit=100`,
        {
          cache: 'no-store',
          credentials: 'include',
        },
      );

      if (response.status === 404) {
        return;
      }
      if (response.status === 401 || response.status === 403) {
        schedule(5000);
        return;
      }
      if (!response.ok) {
        schedule(5000);
        return;
      }

      const payload = (await response.json()) as AiApiBrowserConsolePayload;
      const entries = Array.isArray(payload.entries) ? payload.entries : [];
      if (Number.isFinite(payload.next_since)) {
        sinceId = Number(payload.next_since);
      } else if (entries.length > 0) {
        sinceId = Number(entries[entries.length - 1]?.id ?? sinceId);
      }

      if (payload.enabled !== false) {
        for (const entry of entries) {
          console.info(
            '%c[AI API]',
            'color:#0891b2;font-weight:700;',
            entry.message ?? '',
            { id: entry.id, logger: entry.logger },
          );
        }
      }

      schedule(1500);
    } catch {
      schedule(5000);
    }
  };

  void poll();

  return () => {
    stopped = true;
    if (timer !== undefined) {
      window.clearTimeout(timer);
    }
  };
};

export default function App() {
  const [activeTab, setActiveTab] = useState<NormalizedTab>(() => readInitialTab());
  const [isDark, setIsDark] = useState(() => readInitialTheme());
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showAccountSecurityModal, setShowAccountSecurityModal] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(() => readInitialOnboarding());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [user, setUser] = useState<AuthUser>(null);
  const [authBootstrapDone, setAuthBootstrapDone] = useState(false);
  const [pendingProtectedTab, setPendingProtectedTab] = useState<NormalizedTab | null>(null);
  const { isMobile } = useResponsiveDevice();
  useVisualViewport();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
    window.localStorage.setItem(THEME_KEY, isDark ? 'dark' : 'light');
  }, [isDark]);

  useEffect(() => {
    document.documentElement.classList.toggle('mobile-runtime-root', isMobile);
    document.body.classList.toggle('mobile-runtime-root', isMobile);
    return () => {
      document.documentElement.classList.remove('mobile-runtime-root');
      document.body.classList.remove('mobile-runtime-root');
    };
  }, [isMobile]);

  useEffect(() => {
    window.localStorage.setItem(ACTIVE_TAB_KEY, activeTab);
    syncActiveTabLocation(activeTab);
  }, [activeTab]);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      try {
        const payload = await getCurrentUser();
        if (!cancelled) setUser(payload?.user ?? null);
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setAuthBootstrapDone(true);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => startAiApiBrowserConsoleMirror(), []);

  useEffect(() => {
    if (isMobile && activeTab === 'nexus') {
      setActiveTab('dashboard');
    }
  }, [activeTab, isMobile]);

  useEffect(() => {
    if (!authBootstrapDone) return;
    if (user || !isProtectedTab(activeTab)) return;
    setPendingProtectedTab(activeTab);
    setShowLoginModal(true);
    if (activeTab !== 'dashboard') {
      startTransition(() => setActiveTab('dashboard'));
    }
  }, [activeTab, authBootstrapDone, user]);

  useEffect(() => {
    if (!user) return;
    setShowLoginModal(false);
  }, [user]);

  useEffect(() => {
    if (!authBootstrapDone || !user || !pendingProtectedTab) return;
    const nextTab = isMobile ? normalizeMobileTab(pendingProtectedTab) : pendingProtectedTab;
    startTransition(() => setActiveTab(nextTab));
    setPendingProtectedTab(null);
  }, [authBootstrapDone, isMobile, pendingProtectedTab, user]);

  useEffect(() => {
    if (!showOnboarding || !authBootstrapDone || !user) return;
    if (activeTab === 'deepread_extraction') {
      setShowOnboarding(false);
    }
  }, [activeTab, authBootstrapDone, showOnboarding, user]);

  const toggleTheme = useCallback(() => setIsDark((prev) => !prev), []);

  const handleTabChange = useCallback((next: AppTab) => {
    const normalized = isMobile ? normalizeMobileTab(normalizeTab(next)) : normalizeTab(next);
    if (isProtectedTab(normalized) && !user) {
      if (!authBootstrapDone) {
        startTransition(() => setActiveTab(normalized));
        return;
      }
      setPendingProtectedTab(normalized);
      setShowLoginModal(true);
      return;
    }
    startTransition(() => setActiveTab(normalized));
    if (normalized === 'deepread_extraction' && user && showOnboarding) {
      setShowOnboarding(false);
    }
    if (normalized !== 'deepread_extraction') {
      setPendingProtectedTab(null);
    }
  }, [authBootstrapDone, isMobile, showOnboarding, user]);

  const handleLogout = useCallback(async () => {
    try {
      await logoutAuth();
    } catch (error) {
      console.error('Logout failed:', error);
    } finally {
      setUser(null);
      setShowAccountSecurityModal(false);
      setActiveTab('dashboard');
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
      case 'doc-processing':
        return (
          <div className="h-screen overflow-hidden p-4">
            <DocProcessingWorkbench />
          </div>
        );
      case 'deepread_extraction':
        if (!authBootstrapDone) {
          return (
            <div className="h-screen flex items-center justify-center p-6">
              <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-white/10 dark:bg-slate-900">
                <div className="text-base font-semibold text-slate-900 dark:text-slate-100">Checking Login</div>
                <div className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                  Verifying your session before opening DeepRead extraction.
                </div>
              </div>
            </div>
          );
        }
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
          <div className="h-screen overflow-hidden">
            <FusionGrid />
          </div>
        );
      case 'nexus':
        return (
          <div className="h-screen overflow-hidden p-4">
            <KnowledgeNexus />
          </div>
        );
      case 'mine':
        return (
          <MobileProfilePage
            user={user}
            onOpenAccountSecurity={() => setShowAccountSecurityModal(true)}
            onToggleTheme={toggleTheme}
            isDark={isDark}
            onLogout={handleLogout}
          />
        );
      default:
        return null;
    }
  };

  const renderMobileContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <MobileDashboard user={user} onNavigate={handleTabChange} />;
      case 'doc-processing':
        return <DocProcessingWorkbench onBack={() => handleTabChange('dashboard')} />;
      case 'deepread_extraction':
        if (!authBootstrapDone) {
          return (
            <div className="min-h-[var(--app-visual-height,100dvh)] bg-slate-50 px-4 pt-[max(6rem,var(--mobile-safe-top))] dark:bg-slate-950">
              <div className="mx-auto max-w-md rounded-3xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-white/10 dark:bg-slate-900">
                <div className="text-base font-semibold text-slate-900 dark:text-slate-100">Checking Login</div>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                  Verifying your session before starting file extraction.
                </p>
              </div>
            </div>
          );
        }
        if (!user) {
          return (
            <div className="min-h-[var(--app-visual-height,100dvh)] bg-slate-50 px-4 pt-[max(6rem,var(--mobile-safe-top))] dark:bg-slate-950">
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
        return <MobileDeepReadPage />;
      case 'fusion':
        return <FusionGrid />;
      case 'nexus':
        return <MobileDashboard user={user} onNavigate={handleTabChange} />;
      case 'mine':
        return (
          <MobileProfilePage
            user={user}
            onOpenAccountSecurity={() => setShowAccountSecurityModal(true)}
            onToggleTheme={toggleTheme}
            isDark={isDark}
            onLogout={handleLogout}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className={cn(
      'min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100',
      isMobile && 'mobile-runtime',
    )}>
      <AuthModal
        show={showLoginModal && authBootstrapDone && !user}
        onClose={() => setShowLoginModal(false)}
        onLoginSuccess={(nextUser) => {
          setUser(nextUser);
          if (pendingProtectedTab) {
            startTransition(() => setActiveTab(pendingProtectedTab));
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

      {isMobile ? (
        <div className="relative min-h-[var(--app-visual-height,100dvh)] overflow-x-hidden">
          <div>{renderMobileContent()}</div>
          {activeTab !== 'doc-processing' && (
            <nav className="mobile-bottom-nav fixed inset-x-0 bottom-0 z-40 border-t border-slate-100 bg-white/95 shadow-[0_-4px_24px_rgba(15,23,42,0.02)] backdrop-blur-2xl dark:border-white/[0.04] dark:bg-[#0B1120]/95 dark:shadow-none">
              <div className="mobile-bottom-nav-inner mx-auto flex w-full max-w-md items-center justify-between px-2 min-[600px]:max-w-xl">
                {MOBILE_BOTTOM_TABS.map((item) => {
                  const Icon = item.icon;
                  const active = activeTab === item.id;

                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleTabChange(item.id)}
                      className="group relative flex h-full flex-1 flex-col items-center justify-center outline-none transition-transform active:scale-[0.96] focus:outline-none"
                    >
                      <span className="relative z-10 flex flex-col items-center justify-center gap-1">
                        <div
                          className={cn(
                            'relative flex h-[28px] w-[56px] items-center justify-center rounded-[12px] transition-colors duration-300',
                            active ? 'bg-cyan-50 dark:bg-cyan-500/10' : 'bg-transparent',
                          )}
                        >
                          <Icon
                            size={20}
                            strokeWidth={active ? 2.5 : 2}
                            className={cn(
                              'transition-colors duration-300',
                              active
                                ? 'text-cyan-600 dark:text-cyan-400'
                                : 'text-slate-400 group-hover:text-slate-600 dark:text-slate-500 dark:group-hover:text-slate-300'
                            )}
                          />
                        </div>
                        <span
                          className={cn(
                            'text-[11px] transition-colors duration-300',
                            active
                              ? 'font-bold text-cyan-700 dark:text-cyan-400'
                              : 'font-medium text-slate-400 group-hover:text-slate-600 dark:text-slate-500 dark:group-hover:text-slate-300'
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
            className={cn(
              'min-h-screen flex-1 transition-[margin-left] duration-300 ease-in-out',
              sidebarCollapsed ? 'ml-[72px]' : 'ml-72',
            )}
          >
            {renderDesktopContent()}
          </main>
        </div>
      )}
      {user ? (
        <PlatformAssistant
          activeTab={activeTab}
          onNavigate={(target) => handleTabChange(target as AppTab)}
        />
      ) : null}
    </div>
  );
}
