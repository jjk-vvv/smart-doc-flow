import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { Dashboard } from './components/Dashboard';
import { DeepReadWorkbench } from './components/DeepReadWorkbench';
import { FusionGrid } from './components/FusionGrid';
import { KnowledgeNexus } from './components/KnowledgeNexus';
import { UserGuide } from './components/UserGuide';
import { AuthModal } from './components/AuthModal';
import { BrainCircuit } from 'lucide-react';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isDark, setIsDark] = useState(false); // Default to light mode as requested
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [user, setUser] = useState<{ name: string; email: string } | null>(null);
  const [showLoginModal, setShowLoginModal] = useState(false);

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
    fetch('/api/me')
      .then(res => {
        if (res.ok) return res.json();
        throw new Error('Not authenticated');
      })
      .then(data => {
        setUser(data.user);
      })
      .catch(() => setUser(null));
  }, []);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />;
      case 'deepread':
        return <DeepReadWorkbench />;
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

  return (
    <>
      <div className="flex min-h-screen font-sans text-foreground selection:bg-primary/30 relative overflow-hidden bg-background transition-colors duration-500">
        {/* Background Noise Texture */}
        <div className="bg-noise z-0"></div>

        {/* Ambient Background Glows */}
        <div className="fixed top-0 left-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[120px] -translate-x-1/2 -translate-y-1/2 pointer-events-none z-0"></div>

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

        <main className={`flex-1 transition-all duration-300 relative z-10 p-4 pt-4 ${isSidebarCollapsed ? 'ml-[72px]' : 'ml-72'}`}>
          {renderContent()}
        </main>
      </div>

      {/* Auth Modal — rendered at root level to avoid sidebar stacking context */}
      <AuthModal
        show={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onLoginSuccess={handleLoginSuccess}
        isDark={isDark}
      />
    </>
  );
};

export default App;
