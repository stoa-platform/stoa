import { useState, ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Footer } from './Footer';
import { UACSpotlight, useUACSpotlight } from '../uac';
import { EnvironmentChrome } from '@stoa/shared/components/EnvironmentChrome';
import { usePortalEnvironment } from '../../contexts/EnvironmentContext';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { showSpotlight, dismissSpotlight } = useUACSpotlight();
  const { activeConfig } = usePortalEnvironment();

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900 flex flex-col transition-colors">
      <EnvironmentChrome
        current={{
          name: activeConfig.name,
          label: activeConfig.label,
          mode: activeConfig.mode as 'full' | 'read-only' | 'promote-only',
        }}
        environments={[]}
        onSwitch={() => {}}
        variant="consumer"
        portalLabels
      />
      <Header onMenuClick={() => setSidebarOpen(true)} />

      <div className="flex flex-1">
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <main id="main-content" className="flex-1 p-6 overflow-auto" tabIndex={-1}>
          <div className="max-w-7xl mx-auto">{children}</div>
        </main>
      </div>

      <Footer />

      {/* First-time user UAC education spotlight */}
      {showSpotlight && <UACSpotlight onDismiss={dismissSpotlight} />}
    </div>
  );
}
