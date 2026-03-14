import { Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { EnvironmentProvider } from './contexts/EnvironmentContext';
import { Layout } from './components/Layout';
import { FloatingChat } from './components/FloatingChat';
import { useChatService } from './hooks/useChatService';
import { ToastProvider } from '@stoa/shared/components/Toast';
import { CommandPaletteProvider } from '@stoa/shared/components/CommandPalette';
import { ThemeProvider } from '@stoa/shared/contexts';
import { CelebrationProvider } from '@stoa/shared/components/Celebration';
import { StoaLoader } from '@stoa/shared/components/StoaLoader';
import { ErrorBoundary } from '@stoa/shared/components/ErrorBoundary';

// Lazy load pages for code splitting
// Consolidated imports — single module loader per multi-export file
const aiToolsModule = () => import('./pages/AITools');
const mcpServersModule = () => import('./pages/MCPServers');
const externalMcpModule = () => import('./pages/ExternalMCPServers');
const mcpConnectorsModule = () => import('./pages/MCPConnectors');
const gatewaysModule = () => import('./pages/Gateways');

const Tenants = lazy(() => import('./pages/Tenants').then((m) => ({ default: m.Tenants })));
const APIsUnified = lazy(() =>
  import('./pages/APIsUnified').then((m) => ({ default: m.APIsUnified }))
);
const APIDetail = lazy(() => import('./pages/APIDetail').then((m) => ({ default: m.APIDetail })));
const Applications = lazy(() =>
  import('./pages/Applications').then((m) => ({ default: m.Applications }))
);
const Consumers = lazy(() => import('./pages/Consumers').then((m) => ({ default: m.Consumers })));
const Subscriptions = lazy(() =>
  import('./pages/Subscriptions').then((m) => ({ default: m.Subscriptions }))
);
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
const MCPServersUnified = lazy(() =>
  mcpServersModule().then((m) => ({ default: m.MCPServersUnified }))
);
const ExternalMCPServerDetail = lazy(() =>
  externalMcpModule().then((m) => ({ default: m.ExternalMCPServerDetail }))
);
const ConnectorCallback = lazy(() =>
  mcpConnectorsModule().then((m) => ({ default: m.ConnectorCallback }))
);
const AdminProspects = lazy(() =>
  import('./pages/AdminProspects').then((m) => ({ default: m.AdminProspects }))
);
const AdminAccessRequests = lazy(() =>
  import('./pages/AdminAccessRequests').then((m) => ({ default: m.AdminAccessRequests }))
);
const AdminUsers = lazy(() =>
  import('./pages/AdminUsers').then((m) => ({ default: m.AdminUsers }))
);
const AdminSettings = lazy(() =>
  import('./pages/AdminSettings').then((m) => ({ default: m.AdminSettings }))
);
const AdminRoles = lazy(() =>
  import('./pages/AdminRoles').then((m) => ({ default: m.AdminRoles }))
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
const HegemonDashboard = lazy(() =>
  import('./pages/HegemonDashboard').then((m) => ({ default: m.HegemonDashboard }))
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
const saasApiKeysModule = () => import('./pages/SaasApiKeys');
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

// CAB-1316: Platform Diagnostics page
const DiagnosticsPage = lazy(() =>
  import('./pages/DiagnosticsPage').then((m) => ({ default: m.DiagnosticsPage }))
);

// Wave 1: Dashboard pages (CAB-1461, CAB-1476)
const SecurityPostureDashboard = lazy(() =>
  import('./pages/SecurityPosture').then((m) => ({ default: m.SecurityPostureDashboard }))
);
const AnalyticsDashboard = lazy(() =>
  import('./pages/AnalyticsDashboard').then((m) => ({ default: m.AnalyticsDashboard }))
);

// CAB-1545: Proxy Owner Dashboard
const ProxyOwnerDashboard = lazy(() =>
  import('./pages/ProxyOwner').then((m) => ({ default: m.ProxyOwnerDashboard }))
);

// CAB-1730: API Traffic Dashboard (proxy backend observability)
const ApiTrafficDashboard = lazy(() =>
  import('./pages/ApiTraffic').then((m) => ({ default: m.ApiTrafficDashboard }))
);

// CAB-1487: LLM Cost Dashboard
const LLMCostDashboard = lazy(() =>
  import('./pages/LLMCost').then((m) => ({ default: m.LLMCostDashboard }))
);

// CAB-1647: Webhooks management (ported from Portal)
const Webhooks = lazy(() => import('./pages/Webhooks').then((m) => ({ default: m.Webhooks })));

// CAB-1648: Credential Mappings management (ported from Portal)
const CredentialMappings = lazy(() =>
  import('./pages/CredentialMappings').then((m) => ({ default: m.CredentialMappings }))
);

// CAB-1649: Contracts / UAC management
const Contracts = lazy(() => import('./pages/Contracts').then((m) => ({ default: m.Contracts })));

// CAB-1786: Certificate Management Page
const CertificatesPage = lazy(() =>
  import('./pages/Certificates').then((m) => ({ default: m.Certificates }))
);

// CAB-1706: GitOps Promotion Flow
const PromotionsPage = lazy(() =>
  import('./pages/Promotions').then((m) => ({ default: m.Promotions }))
);

// CAB-1775: Platform Health Dashboard
const PlatformDashboard = lazy(() =>
  import('./pages/Dashboard/PlatformDashboard').then((m) => ({
    default: m.PlatformDashboard,
  }))
);

// Loading indicator for lazy-loaded pages and auth init
function PageLoader() {
  return <StoaLoader variant="inline" />;
}

function ConnectedFloatingChat() {
  const {
    sendMessageStream,
    confirmTool,
    fetchBudgetStatus,
    abort,
    loadConversations,
    switchConversation,
    newConversation,
    deleteConversation,
    activeConversationId,
  } = useChatService();

  return (
    <FloatingChat
      onSendMessageStream={sendMessageStream}
      onConfirmTool={confirmTool}
      onFetchBudgetStatus={fetchBudgetStatus}
      onAbort={abort}
      onLoadConversations={loadConversations}
      onSwitchConversation={switchConversation}
      onNewConversation={newConversation}
      onDeleteConversation={deleteConversation}
      activeConversationId={activeConversationId}
    />
  );
}

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
                <Route path="/" element={<PlatformDashboard />} />
                <Route path="/tenants" element={<Tenants />} />
                <Route path="/apis" element={<APIsUnified />} />
                <Route path="/apis/:tenantId/:apiId" element={<APIDetail />} />
                <Route path="/ai-tools" element={<ToolCatalog />} />
                <Route path="/ai-tools/subscriptions" element={<MySubscriptions />} />
                <Route path="/ai-tools/usage" element={<UsageDashboard />} />
                <Route path="/ai-tools/:toolName" element={<ToolDetail />} />
                <Route path="/applications" element={<Applications />} />
                <Route path="/consumers" element={<Consumers />} />
                <Route path="/certificates" element={<CertificatesPage />} />
                <Route path="/subscriptions" element={<Subscriptions />} />
                <Route path="/deployments" element={<Deployments />} />
                <Route path="/monitoring" element={<APIMonitoring />} />
                <Route path="/errors" element={<ErrorSnapshots />} />
                <Route path="/mcp-servers" element={<MCPServersUnified />} />
                <Route path="/external-mcp-servers/:id" element={<ExternalMCPServerDetail />} />
                <Route
                  path="/mcp-connectors"
                  element={<Navigate to="/mcp-servers?tab=catalog" replace />}
                />
                <Route
                  path="/external-mcp-servers"
                  element={<Navigate to="/mcp-servers?tab=custom" replace />}
                />
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
                <Route path="/admin/access-requests" element={<AdminAccessRequests />} />
                <Route path="/admin/users" element={<AdminUsers />} />
                <Route path="/admin/settings" element={<AdminSettings />} />
                <Route path="/admin/roles" element={<AdminRoles />} />
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
                <Route
                  path="/backend-apis"
                  element={<Navigate to="/apis?tab=backends" replace />}
                />
                <Route path="/saas-api-keys" element={<SaasApiKeysList />} />
                <Route path="/federation/accounts" element={<FederationAccountsList />} />
                <Route path="/federation/accounts/:id" element={<FederationAccountDetail />} />
                <Route path="/skills" element={<SkillsList />} />
                <Route path="/executions" element={<ExecutionViewDashboard />} />
                <Route path="/audience-governance" element={<AudienceGovernance />} />
                <Route path="/diagnostics" element={<DiagnosticsPage />} />
                {/* Wave 1: Dashboard pages */}
                <Route path="/security-posture" element={<SecurityPostureDashboard />} />
                <Route path="/analytics" element={<AnalyticsDashboard />} />
                <Route path="/hegemon" element={<HegemonDashboard />} />
                <Route path="/proxy-owner" element={<ProxyOwnerDashboard />} />
                <Route path="/api-traffic" element={<ApiTrafficDashboard />} />
                <Route path="/llm-cost" element={<LLMCostDashboard />} />
                <Route path="/webhooks" element={<Webhooks />} />
                <Route path="/credential-mappings" element={<CredentialMappings />} />
                <Route path="/contracts" element={<Contracts />} />
                <Route path="/promotions" element={<PromotionsPage />} />
                <Route
                  path="/internal-apis"
                  element={<Navigate to="/apis?tab=platform" replace />}
                />
              </Routes>
            </Suspense>
          )}
        </Layout>
      </CommandPaletteProvider>
      {/* CAB-285: Floating AI assistant — rendered above Layout so it persists across page navigation */}
      <ConnectedFloatingChat />
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
    <ErrorBoundary>
      <ThemeProvider>
        <ToastProvider>
          <CelebrationProvider>
            <AuthProvider>
              <Routes>
                <Route path="/login" element={<Login />} />
                {/* MCP connector callback is outside ProtectedRoutes — the API
                    callback endpoint uses CSRF state for security (no auth needed),
                    and oidc-client-ts would intercept the code/state params. */}
                <Route
                  path="/mcp-connectors/callback"
                  element={
                    <Suspense fallback={<PageLoader />}>
                      <ConnectorCallback />
                    </Suspense>
                  }
                />
                <Route path="/*" element={<ProtectedRoutes />} />
              </Routes>
            </AuthProvider>
          </CelebrationProvider>
        </ToastProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
