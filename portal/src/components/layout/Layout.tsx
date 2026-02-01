import { useState, ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Footer } from './Footer';
import { UACSpotlight, useUACSpotlight } from '../uac';
import { TrialWarningBanner } from '../TrialWarningBanner';
import { useAuth } from '../../contexts/AuthContext';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { showSpotlight, dismissSpotlight } = useUACSpotlight();
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <Header onMenuClick={() => setSidebarOpen(true)} />

      {/* CAB-409: Trial lifecycle warning banner */}
      <TrialWarningBanner tenantId={user?.tenant_id} />

      <div className="flex flex-1">
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <main id="main-content" className="flex-1 p-6 overflow-auto" tabIndex={-1}>
          <div className="max-w-7xl mx-auto">
            {children}
          </div>
        </main>
      </div>

      <Footer />

      {/* First-time user UAC education spotlight */}
      {showSpotlight && <UACSpotlight onDismiss={dismissSpotlight} />}
    </div>
  );
}
