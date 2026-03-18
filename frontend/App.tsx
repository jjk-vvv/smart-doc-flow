import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { AuthModal } from './components/AuthModal';
import { AIAssistant } from './components/AIAssistant';
import { BrainCircuit } from 'lucide-react';

type AuthUser = { name: string; email: string } | null;
let meRequestPromise: Promise<AuthUser> | null = null;
const ME_REQUEST_TIMEOUT_MS = 6000;
const AUTH_PROBE_ENV = import.meta.env.VITE_ENABLE_AUTH_PROBE;

const shouldProbeAuth = () => {
  if (AUTH_PROBE_ENV === '1') return true;
  if (AUTH_PROBE_ENV === '0') return false;
  const host = window.location.hostname.toLowerCase();
  return !(host === '127.0.0.1' || host === 'localhost');
};

const fetchCurrentUser = (): Promise<AuthUser> => {
  if (!shouldProbeAuth()) {
    return Promise.resolve(null);
  }
  if (!meRequestPromise) {
    const request = fetch('/api/me')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => (data?.user ? { name: String(data.user.name), email: String(data.user.email) } : null))
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
  import('./components/Dashboard').then((mod) => ({ default: mod.Dashboard }))
);
const DeepReadWorkbench = lazy(() =>
  import('./components/DeepReadWorkbench').then((mod) => ({ default: mod.DeepReadWorkbench }))
);
const DocInteractionWorkbench = lazy(() =>
  import('./components/DocInteractionWorkbench').then((mod) => ({ default: mod.DocInteractionWorkbench }))
);
const FusionGrid = lazy(() =>
  import('./components/FusionGrid').then((mod) => ({ default: mod.FusionGrid }))
);
const KnowledgeNexus = lazy(() =>
  import('./components/KnowledgeNexus').then((mod) => ({ default: mod.KnowledgeNexus }))
);
const UserGuide = lazy(() =>
  import('./components/UserGuide').then((mod) => ({ default: mod.UserGuide }))
);

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isDark, setIsDark] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [user, setUser] = useState<AuthUser>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);

  const isFullPage = activeTab === 'guide';
  const isEdgeToEdgeWorkbench =
    activeTab === 'deepread' || activeTab === 'deepread_extraction' || activeTab === 'nexus';

  const handleLoginSuccess = (loggedInUser: { name: string; email: string }) => {
    setUser(loggedInUser);
    setShowLoginModal(false);
  };

  // Apply theme class to HTML element
  useEffect(() => {
    const html = document.documentElement;
    if (isDark) {
      html.classList.add('dark');
    } else {
      html.classList.remove('dark');
    }
  }, [isDark]);

  // Fetch user on mount
  useEffect(() => {
    let active = true;
    fetchCurrentUser().then((currentUser) => {
      if (!active) return;
      setUser(currentUser);
    });
    return () => {
      active = false;
    };
  }, []);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />;
      case 'deepread':
      case 'deepread_extraction':
        return <DeepReadWorkbench isSidebarCollapsed={isSidebarCollapsed} />;
      case 'deepread_interaction':
        return <DocInteractionWorkbench />;
      case 'fusion':
        return <FusionGrid />;
      case 'nexus':
        return <KnowledgeNexus />;
      case 'guide':
        return <UserGuide />;
      default:
        return <Dashboard />;
    }
  };

  const loadingFallback = (
    <div className="h-[calc(100vh-2rem)] flex items-center justify-center rounded-xl border border-border/40 bg-background/60">
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <BrainCircuit size={18} className="animate-pulse text-primary" />
        <span>模块加载中...</span>
      </div>
    </div>
  );

  return (
    <>
      <div className="flex min-h-screen font-sans text-foreground selection:bg-primary/30 relative overflow-hidden bg-background transition-colors duration-500">
        {/* Background Noise Texture */}
        <div className="bg-noise z-0"></div>

        {/* Ambient Background Glows */}
        <div className="fixed top-0 left-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[120px] -translate-x-1/2 -translate-y-1/2 pointer-events-none z-0"></div>

        {!isFullPage && (
          <Sidebar
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            isDark={isDark}
            toggleTheme={() => setIsDark(!isDark)}
            isCollapsed={isSidebarCollapsed}
            toggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            user={user}
            setUser={setUser}
            showLoginModal={showLoginModal}
            setShowLoginModal={setShowLoginModal}
          />
        )}

        <main
          data-active-tab={activeTab}
          className={`flex-1 transition-all duration-300 relative z-10 ${
          isFullPage
            ? 'w-full p-0'
            : isEdgeToEdgeWorkbench
              ? `${isSidebarCollapsed ? 'ml-[72px]' : 'ml-72'} p-0 overflow-hidden`
              : `p-4 pt-4 ${isSidebarCollapsed ? 'ml-[72px]' : 'ml-72'}`
        }`}>
          <Suspense fallback={loadingFallback}>{renderContent()}</Suspense>
        </main>
      </div>

      {/* Auth Modal — rendered at root level to avoid sidebar stacking context */}
      <AuthModal
        show={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onLoginSuccess={handleLoginSuccess}
        isDark={isDark}
      />

      {/* Vercel AI SDK Floating Assistant */}
      <AIAssistant />
    </>
  );
};

export default App;
