import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { AuthModal } from './components/AuthModal';
import { AccountSecurityModal } from './components/AccountSecurityModal';
import { AIAssistant } from './components/AIAssistant';
import { BrainCircuit } from 'lucide-react';
import { getCurrentUser, type AuthUser } from './shared/api/auth';

let meRequestPromise: Promise<AuthUser> | null = null;
const ME_REQUEST_TIMEOUT_MS = 20000;
const AUTH_PROBE_ENV = import.meta.env.VITE_ENABLE_AUTH_PROBE;
const APP_ACTIVE_TAB_STORAGE_KEY = 'smart_doc_flow.active_tab.v1';
const PROTECTED_APP_TABS = new Set([
  'deepread',
  'deepread_extraction',
  'deepread_interaction',
  'fusion',
  'nexus',
]);
const VALID_APP_TABS = new Set([
  'dashboard',
  'deepread',
  'deepread_extraction',
  'deepread_interaction',
  'fusion',
  'nexus',
  'guide',
]);

const normalizeActiveTab = (value: string | null | undefined): string => {
  const candidate = String(value || '').trim();
  return VALID_APP_TABS.has(candidate) ? candidate : 'dashboard';
};

const resolveInitialActiveTab = (): string => {
  if (typeof window === 'undefined') {
    return 'dashboard';
  }
  try {
    const url = new URL(window.location.href);
    const queryTab = url.searchParams.get('tab');
    if (queryTab) {
      return normalizeActiveTab(queryTab);
    }
    return normalizeActiveTab(window.localStorage.getItem(APP_ACTIVE_TAB_STORAGE_KEY));
  } catch {
    return 'dashboard';
  }
};

const syncActiveTabLocation = (activeTab: string): void => {
  if (typeof window === 'undefined') return;
  const normalizedTab = normalizeActiveTab(activeTab);
  try {
    if (window.localStorage.getItem(APP_ACTIVE_TAB_STORAGE_KEY) !== normalizedTab) {
      window.localStorage.setItem(APP_ACTIVE_TAB_STORAGE_KEY, normalizedTab);
    }
    const url = new URL(window.location.href);
    if (normalizedTab === 'dashboard') {
      url.searchParams.delete('tab');
    } else {
      url.searchParams.set('tab', normalizedTab);
    }
    const nextUrl = `${url.pathname}${url.search}${url.hash}`;
    const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (nextUrl !== currentUrl) {
      window.history.replaceState(null, '', nextUrl);
    }
  } catch {
    // Keep working even if storage or history updates fail.
  }
};

const shouldProbeAuth = () => {
  if (AUTH_PROBE_ENV === '1') return true;
  if (AUTH_PROBE_ENV === '0') return false;
  return true;
};

const isProtectedTab = (value: string | null | undefined): boolean =>
  shouldProbeAuth() && PROTECTED_APP_TABS.has(normalizeActiveTab(value));

const pushTabTrace = (from: string, to: string, reason: string) => {
  if (!import.meta.env.DEV || typeof window === 'undefined') return;
  const traceEntry = {
    at: new Date().toISOString(),
    from,
    to,
    reason,
    href: window.location.href,
  };
  const host = window as unknown as {
    __smartDocFlowTabTrace?: Array<Record<string, unknown>>;
  };
  const trace = host.__smartDocFlowTabTrace || [];
  trace.push(traceEntry);
  if (trace.length > 200) trace.shift();
  host.__smartDocFlowTabTrace = trace;
  // Keep console trace for rapid browser-side diagnosis.
  console.debug('[smart-doc-flow][tab]', traceEntry);
};

const syncCachedCurrentUser = (user: AuthUser): void => {
  meRequestPromise = Promise.resolve(user);
};

const fetchCurrentUser = (): Promise<AuthUser> => {
  if (!shouldProbeAuth()) {
    return Promise.resolve(null);
  }
  if (!meRequestPromise) {
    const request = getCurrentUser()
      .then((data) =>
        data?.user
          ? {
              id: data.user.id ? String(data.user.id) : undefined,
              name: String(data.user.name),
              email: String(data.user.email),
              phone: data.user.phone ? String(data.user.phone) : undefined,
              status: data.user.status ? String(data.user.status) : undefined,
              tenantId: data.user.tenantId ? String(data.user.tenantId) : undefined,
            }
          : null
      )
      .catch(() => null);

    meRequestPromise = new Promise<AuthUser>((resolve) => {
      const timer = window.setTimeout(() => resolve(null), ME_REQUEST_TIMEOUT_MS);
      request
        .then((result) => resolve(result))
        .catch(() => resolve(null))
        .finally(() => window.clearTimeout(timer));
    });
  }
  return meRequestPromise;
};

const Dashboard = lazy(() =>
  import('./pages/dashboard/Dashboard').then((mod) => ({ default: mod.Dashboard }))
);
const DeepReadWorkbench = lazy(() =>
  import('./pages/deepread/DeepReadWorkbench').then((mod) => ({ default: mod.DeepReadWorkbench }))
);
const Module1PlaceholderPage = lazy(() =>
  import('./pages/module1-placeholder/Module1PlaceholderPage').then((mod) => ({ default: mod.Module1PlaceholderPage }))
);
const FusionGrid = lazy(() =>
  import('./pages/fusion/FusionGrid').then((mod) => ({ default: mod.FusionGrid }))
);
const KnowledgeNexus = lazy(() =>
  import('./pages/knowledge-nexus/KnowledgeNexus').then((mod) => ({ default: mod.KnowledgeNexus }))
);
const UserGuide = lazy(() =>
  import('./pages/guide/UserGuide').then((mod) => ({ default: mod.UserGuide }))
);

const APP_LOADING_TEXT = '模块加载中...';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState(() => resolveInitialActiveTab());
  const [isDark, setIsDark] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [user, setUser] = useState<AuthUser>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showAccountSecurityModal, setShowAccountSecurityModal] = useState(false);
  const [authResolved, setAuthResolved] = useState(() => !shouldProbeAuth());
  const [pendingProtectedTab, setPendingProtectedTab] = useState<string | null>(null);

  const isFullPage = activeTab === 'guide';
  const isEdgeToEdgeWorkbench =
    activeTab === 'deepread' || activeTab === 'deepread_extraction' || activeTab === 'nexus';
  const activeTabRequiresAuth = isProtectedTab(activeTab);

  const applyUserState = (nextUser: AuthUser) => {
    setUser(nextUser);
    setAuthResolved(true);
    syncCachedCurrentUser(nextUser);
  };

  const applyActiveTab = (nextTab: string, reason: string) => {
    const normalizedTab = normalizeActiveTab(nextTab);
    setActiveTab((previous) => {
      pushTabTrace(normalizeActiveTab(previous), normalizedTab, reason);
      return normalizedTab;
    });
  };

  const handleLoginSuccess = (loggedInUser: NonNullable<AuthUser>) => {
    applyUserState(loggedInUser);
    if (pendingProtectedTab && isProtectedTab(pendingProtectedTab)) {
      applyActiveTab(pendingProtectedTab, 'login-success-pending-tab');
      setPendingProtectedTab(null);
    }
    setShowLoginModal(false);
  };

  const handleActiveTabChange = (nextTab: string) => {
    const normalizedTab = normalizeActiveTab(nextTab);
    if (isProtectedTab(normalizedTab) && authResolved && !user) {
      setPendingProtectedTab(normalizedTab);
      setShowLoginModal(true);
      applyActiveTab(normalizedTab, 'request-protected-tab-without-auth');
      return;
    }
    applyActiveTab(normalizedTab, 'user-tab-change');
  };

  useEffect(() => {
    const html = document.documentElement;
    if (isDark) {
      html.classList.add('dark');
    } else {
      html.classList.remove('dark');
    }
  }, [isDark]);

  useEffect(() => {
    let active = true;
    fetchCurrentUser().then((currentUser) => {
      if (!active) return;
      applyUserState(currentUser);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    syncActiveTabLocation(activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (!authResolved || user || !activeTabRequiresAuth) {
      return;
    }
    setPendingProtectedTab(activeTab);
    setShowLoginModal(true);
  }, [activeTabRequiresAuth, authResolved, user]);

  useEffect(() => {
    if (user) {
      return;
    }
    setShowAccountSecurityModal(false);
  }, [user]);

  const renderContent = () => {
    if (activeTabRequiresAuth && !authResolved) {
      return loadingFallback;
    }
    if (activeTabRequiresAuth && !user) {
      return (
        <div className="h-[calc(100vh-2rem)] flex items-center justify-center rounded-xl border border-border/40 bg-background/60">
          <div className="max-w-md text-center">
            <div className="text-base font-semibold text-foreground">需要登录后访问</div>
            <div className="mt-2 text-sm text-muted-foreground">
              请先登录账号，再访问当前工作区并继续文档流程。
            </div>
          </div>
        </div>
      );
    }
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />;
      case 'deepread':
      case 'deepread_extraction':
        return <DeepReadWorkbench isSidebarCollapsed={isSidebarCollapsed} />;
      case 'deepread_interaction':
        return <Module1PlaceholderPage />;
      case 'fusion':
        return <FusionGrid />;
      case 'nexus':
        return <KnowledgeNexus />;
      case 'guide':
        return (
          <UserGuide
            onBackToDashboard={() => handleActiveTabChange('dashboard')}
            onOpenLogin={() => setShowLoginModal(true)}
          />
        );
      default:
        return <Dashboard />;
    }
  };

  const loadingFallback = (
    <div className="h-[calc(100vh-2rem)] flex items-center justify-center rounded-xl border border-border/40 bg-background/60">
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <BrainCircuit size={18} className="animate-pulse text-primary" />
        <span>{APP_LOADING_TEXT}</span>
      </div>
    </div>
  );

  return (
    <>
      <div className="flex min-h-screen font-sans text-foreground selection:bg-primary/30 relative overflow-hidden bg-background transition-colors duration-500">
        <div className="bg-noise z-0"></div>
        <div className="fixed top-0 left-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[120px] -translate-x-1/2 -translate-y-1/2 pointer-events-none z-0"></div>

        {!isFullPage && (
          <Sidebar
            activeTab={activeTab}
            setActiveTab={handleActiveTabChange}
            isDark={isDark}
            toggleTheme={() => setIsDark(!isDark)}
            isCollapsed={isSidebarCollapsed}
            toggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            user={user}
            setUser={applyUserState}
            setShowLoginModal={setShowLoginModal}
            setShowAccountSecurityModal={setShowAccountSecurityModal}
          />
        )}

        <main
          data-active-tab={activeTab}
          className={`flex-1 transition-all duration-300 relative z-10 ${isFullPage
              ? 'w-full p-0'
              : isEdgeToEdgeWorkbench
                ? `${isSidebarCollapsed ? 'ml-[72px]' : 'ml-72'} p-0 overflow-hidden`
                : `p-4 pt-4 ${isSidebarCollapsed ? 'ml-[72px]' : 'ml-72'}`
            }`}>
          <Suspense fallback={loadingFallback}>{renderContent()}</Suspense>
        </main>
      </div>

      <AuthModal
        show={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onLoginSuccess={handleLoginSuccess}
      />

      <AccountSecurityModal
        show={showAccountSecurityModal}
        user={user}
        onClose={() => setShowAccountSecurityModal(false)}
        onLoggedOut={() => applyUserState(null)}
      />

      {user ? <AIAssistant /> : null}
    </>
  );
};

export default App;
