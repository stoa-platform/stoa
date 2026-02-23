import { Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy, memo } from 'react';
import { useTranslation } from 'react-i18next';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { EnvironmentProvider } from './contexts/EnvironmentContext';
import { Layout } from './components/Layout';
import { FloatingChat } from './components/FloatingChat';
import { PlatformStatus } from './components/PlatformStatus';
import { quickLinks } from './config';
import { ToastProvider } from '@stoa/shared/components/Toast';
import { CommandPaletteProvider } from '@stoa/shared/components/CommandPalette';
import { ThemeProvider } from '@stoa/shared/contexts';
import { CelebrationProvider } from '@stoa/shared/components/Celebration';
import { StoaLoader } from '@stoa/shared/components/StoaLoader';

// Lazy load pages for code splitting
// Consolidated imports — single module loader per multi-export file
const aiToolsModule = () => import('./pages/AITools');
const externalMcpModule = () => import('./pages/ExternalMCPServers');
const gatewaysModule = () => import('./pages/Gateways');

const Tenants = lazy(() => import('./pages/Tenants').then((m) => ({ default: m.Tenants })));
const APIs = lazy(() => import('./pages/APIs').then((m) => ({ default: m.APIs })));
const Applications = lazy(() =>
  import('./pages/Applications').then((m) => ({ default: m.Applications }))
);
const Consumers = lazy(() => import('./pages/Consumers').then((m) => ({ default: m.Consumers })));
const Deployments = lazy(() =>
  import('./pages/Deployments').then((m) => ({ default: m.Deployments }))
);
const APIMonitoring = lazy(() =>
  import('./pages/APIMonitoring').then((m) => ({ default: m.APIMonitoring }))
);
const ErrorSnapshots = lazy(() =>
  import('./pages/ErrorSnapshots').then((m) => ({ default: m.ErrorSnapshots }))
);
const ToolCatalog = lazy(() => aiToolsModule().then((m) => ({ default: m.ToolCatalog })));
const ToolDetail = lazy(() => aiToolsModule().then((m) => ({ default: m.ToolDetail })));
const MySubscriptions = lazy(() => aiToolsModule().then((m) => ({ default: m.MySubscriptions })));
const UsageDashboard = lazy(() => aiToolsModule().then((m) => ({ default: m.UsageDashboard })));
const ExternalMCPServersList = lazy(() =>
  externalMcpModule().then((m) => ({ default: m.ExternalMCPServersList }))
);
const ExternalMCPServerDetail = lazy(() =>
  externalMcpModule().then((m) => ({ default: m.ExternalMCPServerDetail }))
);
const AdminProspects = lazy(() =>
  import('./pages/AdminProspects').then((m) => ({ default: m.AdminProspects }))
);
const GatewayStatus = lazy(() => import('./pages/GatewayStatus'));
const GatewayRegistry = lazy(() => gatewaysModule().then((m) => ({ default: m.GatewayList })));
const GatewayModes = lazy(() =>
  gatewaysModule().then((m) => ({ default: m.GatewayModesDashboard }))
);
const GatewayDeployments = lazy(() =>
  import('./pages/GatewayDeployments').then((m) => ({ default: m.GatewayDeploymentsDashboard }))
);
const DriftDetection = lazy(() =>
  import('./pages/DriftDetection').then((m) => ({ default: m.DriftDetection }))
);
const GatewayObservability = lazy(() =>
  import('./pages/GatewayObservability').then((m) => ({ default: m.GatewayObservabilityDashboard }))
);
const OperationsDashboard = lazy(() =>
  import('./pages/Operations').then((m) => ({ default: m.OperationsDashboard }))
);
const TenantDashboard = lazy(() =>
  import('./pages/TenantDashboard').then((m) => ({ default: m.TenantDashboard }))
);
const BusinessDashboard = lazy(() =>
  import('./pages/Business').then((m) => ({ default: m.BusinessDashboard }))
);

// Native observability dashboards (replace iframe embeds)
const PlatformMetrics = lazy(() =>
  import('./pages/PlatformMetrics').then((m) => ({ default: m.PlatformMetricsDashboard }))
);
// CAB-1108: Embedded iframe pages for unified STOA experience (retained for deep-link fallback)
const GrafanaEmbed = lazy(() => import('./pages/GrafanaEmbed'));
const IdentityEmbed = lazy(() => import('./pages/IdentityEmbed'));
const RequestExplorer = lazy(() =>
  import('./pages/RequestExplorer').then((m) => ({ default: m.RequestExplorerDashboard }))
);
// CAB-1114: OpenSearch Dashboards for API trace logs (retained for deep-link fallback)
const LogsEmbed = lazy(() => import('./pages/LogsEmbed'));

// CAB-1118: Skeleton pages for upcoming features
const ShadowDiscovery = lazy(() =>
  import('./pages/ShadowDiscovery').then((m) => ({ default: m.ShadowDiscovery }))
);
const TokenOptimizer = lazy(() =>
  import('./pages/TokenOptimizer').then((m) => ({ default: m.TokenOptimizer }))
);
const Policies = lazy(() => import('./pages/Policies').then((m) => ({ default: m.Policies })));
const AuditLog = lazy(() => import('./pages/AuditLog').then((m) => ({ default: m.AuditLog })));
const Workflows = lazy(() => import('./pages/Workflows').then((m) => ({ default: m.Workflows })));

// CAB-1251: SaaS Self-Service pages
const backendApisModule = () => import('./pages/BackendApis');
const saasApiKeysModule = () => import('./pages/SaasApiKeys');
const BackendApisList = lazy(() =>
  backendApisModule().then((m) => ({ default: m.BackendApisList }))
);
const SaasApiKeysList = lazy(() =>
  saasApiKeysModule().then((m) => ({ default: m.SaasApiKeysList }))
);

// CAB-1372: Federation UI pages
const federationModule = () => import('./pages/FederationAccounts');
const FederationAccountsList = lazy(() =>
  federationModule().then((m) => ({ default: m.FederationAccountsList }))
);
const FederationAccountDetail = lazy(() =>
  federationModule().then((m) => ({ default: m.FederationAccountDetail }))
);

// CAB-1366: Skills UI page
const skillsModule = () => import('./pages/Skills');
const SkillsList = lazy(() => skillsModule().then((m) => ({ default: m.SkillsList })));

// CAB-1318: Execution View
const ExecutionViewDashboard = lazy(() =>
  import('./pages/ExecutionView').then((m) => ({ default: m.ExecutionViewDashboard }))
);

// CAB-1323: Audience Governance page
const AudienceGovernance = lazy(() =>
  import('./pages/AudienceGovernance').then((m) => ({ default: m.AudienceGovernance }))
);

// Loading indicator for lazy-loaded pages and auth init
function PageLoader() {
  return <StoaLoader variant="inline" />;
}

function Dashboard() {
  const { user } = useAuth();
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
          {t('dashboard.title')}
        </h1>
        <p className="text-neutral-500 dark:text-neutral-400 mt-2">{t('dashboard.welcome')}</p>
      </div>

      {/* Welcome Card */}
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center">
            <svg
              className="w-6 h-6 text-blue-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
              {t('dashboard.hello', { name: user?.name || 'User' })}
            </h2>
            <p className="text-sm text-neutral-500 dark:text-neutral-400">{user?.email}</p>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <QuickActionCard
          title={t('dashboard.quickActions.apis')}
          description={t('dashboard.quickActions.apisDesc')}
          href="/apis"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          }
          color="blue"
        />
        <QuickActionCard
          title={t('dashboard.quickActions.aiTools')}
          description={t('dashboard.quickActions.aiToolsDesc')}
          href="/ai-tools"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
          }
          color="orange"
        />
        <QuickActionCard
          title={t('dashboard.quickActions.applications')}
          description={t('dashboard.quickActions.applicationsDesc')}
          href="/applications"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
              />
            </svg>
          }
          color="purple"
        />
        <QuickActionCard
          title={t('dashboard.quickActions.deployments')}
          description={t('dashboard.quickActions.deploymentsDesc')}
          href="/deployments"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
          }
          color="green"
        />
      </div>

      {/* Platform Status (CAB-654) */}
      <PlatformStatus />

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6">
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
            {t('dashboard.quickLinks')}
          </h3>
          <ul className="space-y-3">
            {quickLinks.map((link) => (
              <li key={link.name}>
                <a
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-blue-600 hover:text-blue-800"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                    />
                  </svg>
                  {link.name}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow dark:shadow-none p-6">
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
            {t('dashboard.gettingStarted')}
          </h3>
          <ol className="space-y-3 text-sm text-neutral-600 dark:text-neutral-400">
            <li className="flex gap-2">
              <span className="font-bold text-blue-600">1.</span>
              <span>
                Go to{' '}
                <a href="/apis" className="text-blue-600 hover:underline">
                  APIs
                </a>{' '}
                and create a new API
              </span>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-blue-600">2.</span>
              <span>Import your OpenAPI/Swagger specification or create manually</span>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-blue-600">3.</span>
              <span>Deploy to DEV environment to test</span>
            </li>
            <li className="flex gap-2">
              <span className="font-bold text-blue-600">4.</span>
              <span>
                Monitor deployments in the{' '}
                <a href="/deployments" className="text-blue-600 hover:underline">
                  Deployments
                </a>{' '}
                page
              </span>
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}

interface QuickActionCardProps {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  color: 'blue' | 'purple' | 'green' | 'orange';
}

// Color classes moved outside component to avoid recreation on each render
const quickActionColorClasses = {
  blue: 'bg-blue-50 dark:bg-blue-950/30 text-blue-600 dark:text-blue-400 border-2 border-blue-200 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/30',
  purple:
    'bg-purple-50 dark:bg-purple-950/30 text-purple-600 dark:text-purple-400 border-2 border-purple-200 dark:border-purple-800 hover:bg-purple-100 dark:hover:bg-purple-900/30',
  green:
    'bg-green-50 dark:bg-green-950/30 text-green-600 dark:text-green-400 border-2 border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-900/30',
  orange:
    'bg-orange-50 dark:bg-orange-950/30 text-orange-600 dark:text-orange-400 border-2 border-orange-200 dark:border-orange-800 hover:bg-orange-100 dark:hover:bg-orange-900/30',
} as const;

const QuickActionCard = memo(function QuickActionCard({
  title,
  description,
  href,
  icon,
  color,
}: QuickActionCardProps) {
  return (
    <a
      href={href}
      className={`block p-6 rounded-xl transition-all hover:shadow-lg ${quickActionColorClasses[color]}`}
    >
      <div className="flex items-center gap-4">
        <div className="flex-shrink-0 p-2 rounded-lg bg-white/60 dark:bg-neutral-800 shadow-sm">
          {icon}
        </div>
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="text-sm opacity-75">{description}</p>
        </div>
      </div>
    </a>
  );
});

function ProtectedRoutes() {
  const { isAuthenticated, isLoading } = useAuth();

  if (!isAuthenticated && !isLoading) {
    return <Navigate to="/login" replace />;
  }

  return (
    <EnvironmentProvider>
      <CommandPaletteProvider>
        <Layout>
          {isLoading ? (
            <PageLoader />
          ) : (
            <Suspense fallback={<PageLoader />}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/tenants" element={<Tenants />} />
                <Route path="/apis" element={<APIs />} />
                <Route path="/ai-tools" element={<ToolCatalog />} />
                <Route path="/ai-tools/subscriptions" element={<MySubscriptions />} />
                <Route path="/ai-tools/usage" element={<UsageDashboard />} />
                <Route path="/ai-tools/:toolName" element={<ToolDetail />} />
                <Route path="/applications" element={<Applications />} />
                <Route path="/consumers" element={<Consumers />} />
                <Route path="/deployments" element={<Deployments />} />
                <Route path="/monitoring" element={<APIMonitoring />} />
                <Route path="/errors" element={<ErrorSnapshots />} />
                <Route path="/external-mcp-servers" element={<ExternalMCPServersList />} />
                <Route path="/external-mcp-servers/:id" element={<ExternalMCPServerDetail />} />
                <Route path="/gateway" element={<GatewayStatus />} />
                <Route path="/gateways/modes" element={<GatewayModes />} />
                <Route path="/gateways" element={<GatewayRegistry />} />
                <Route path="/gateway-deployments" element={<GatewayDeployments />} />
                <Route path="/drift" element={<DriftDetection />} />
                <Route path="/gateway-observability" element={<GatewayObservability />} />
                <Route path="/operations" element={<OperationsDashboard />} />
                <Route path="/my-usage" element={<TenantDashboard />} />
                <Route path="/business" element={<BusinessDashboard />} />
                <Route path="/admin/prospects" element={<AdminProspects />} />
                {/* Native observability dashboards (replace iframe embeds) */}
                <Route path="/observability" element={<PlatformMetrics />} />
                <Route path="/observability/grafana" element={<GrafanaEmbed />} />
                <Route path="/observability/benchmarks" element={<GrafanaEmbed />} />
                <Route path="/identity" element={<IdentityEmbed />} />
                {/* Native request explorer (replace OpenSearch iframe) */}
                <Route path="/logs" element={<RequestExplorer />} />
                <Route path="/logs/opensearch" element={<LogsEmbed />} />
                {/* CAB-1118: Skeleton pages for upcoming features */}
                <Route path="/shadow-discovery" element={<ShadowDiscovery />} />
                <Route path="/token-optimizer" element={<TokenOptimizer />} />
                <Route path="/policies" element={<Policies />} />
                <Route path="/audit-log" element={<AuditLog />} />
                <Route path="/workflows" element={<Workflows />} />
                {/* CAB-1251: SaaS Self-Service */}
                <Route path="/backend-apis" element={<BackendApisList />} />
                <Route path="/saas-api-keys" element={<SaasApiKeysList />} />
                <Route path="/federation/accounts" element={<FederationAccountsList />} />
                <Route path="/federation/accounts/:id" element={<FederationAccountDetail />} />
                <Route path="/skills" element={<SkillsList />} />
                <Route path="/executions" element={<ExecutionViewDashboard />} />
                <Route path="/audience-governance" element={<AudienceGovernance />} />
              </Routes>
            </Suspense>
          )}
        </Layout>
      </CommandPaletteProvider>
      {/* CAB-285: Floating AI assistant — rendered above Layout so it persists across page navigation */}
      <FloatingChat />
    </EnvironmentProvider>
  );
}

function Login() {
  const { login, isLoading } = useAuth();
  const { t } = useTranslation();

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-blue-500 to-purple-600">
      <div className="bg-white p-8 rounded-xl shadow-2xl w-96">
        <div className="text-center mb-6">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg
              className="w-8 h-8 text-blue-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-neutral-900">{t('login.title')}</h1>
          <p className="text-neutral-500 mt-1">{t('login.subtitle')}</p>
        </div>
        <button
          onClick={login}
          disabled={isLoading}
          className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              {t('common.loading')}
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"
                />
              </svg>
              {t('login.button')}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <CelebrationProvider>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/*" element={<ProtectedRoutes />} />
            </Routes>
          </AuthProvider>
        </CelebrationProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App;
