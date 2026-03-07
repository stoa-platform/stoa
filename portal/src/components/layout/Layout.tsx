import { useState, useCallback, ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Footer } from './Footer';
import { UACSpotlight, useUACSpotlight } from '../uac';
import { EnvironmentChrome } from '@stoa/shared/components/EnvironmentChrome';
import { usePortalEnvironment, type PortalEnvironment } from '../../contexts/EnvironmentContext';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { showSpotlight, dismissSpotlight } = useUACSpotlight();
  const { activeConfig, environments, switchEnvironment } = usePortalEnvironment();

  const handleEnvSwitch = useCallback(
    (env: string) => {
      switchEnvironment(env as PortalEnvironment);
    },
    [switchEnvironment]
  );

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900 flex flex-col transition-colors">
      <EnvironmentChrome
        current={{
          name: activeConfig.name,
          label: activeConfig.label,
          mode: activeConfig.mode as 'full' | 'read-only' | 'promote-only',
        }}
        environments={environments.map((env) => ({
          name: env.name,
          label: env.label,
          mode: env.mode,
        }))}
        onSwitch={handleEnvSwitch}
        variant="consumer"
        portalLabels
        className="sticky top-0 z-50"
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
