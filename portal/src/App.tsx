import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Suspense, lazy, useState } from 'react';
import { Layout } from './components/layout';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ErrorBoundary, SkipLink } from './components/common';
import { captureException } from './services/errorTracking';
import { StoaLogo } from '@stoa/shared/components/StoaLogo';
import { StoaLoader } from '@stoa/shared/components/StoaLoader';
import { config } from './config';

// Lazy load pages for code splitting - reduces initial bundle by ~60%
const HomePage = lazy(() => import('./pages/Home').then((m) => ({ default: m.HomePage })));
const MCPServersPage = lazy(() =>
  import('./pages/servers').then((m) => ({ default: m.MCPServersPage }))
);
const ServerDetailPage = lazy(() =>
  import('./pages/servers').then((m) => ({ default: m.ServerDetailPage }))
);
const MyMCPServersPage = lazy(() =>
  import('./pages/servers').then((m) => ({ default: m.MyMCPServersPage }))
);
const APICatalog = lazy(() => import('./pages/apis').then((m) => ({ default: m.APICatalog })));
const APIDetail = lazy(() => import('./pages/apis').then((m) => ({ default: m.APIDetail })));
const APITestingSandbox = lazy(() =>
  import('./pages/apis').then((m) => ({ default: m.APITestingSandbox }))
);
const ApplicationDetail = lazy(() =>
  import('./pages/apps').then((m) => ({ default: m.ApplicationDetail }))
);
const ContractDetailPage = lazy(() =>
  import('./pages/contracts').then((m) => ({ default: m.ContractDetailPage }))
);
const CreateContractPage = lazy(() =>
  import('./pages/contracts').then((m) => ({ default: m.CreateContractPage }))
);
const ProfilePage = lazy(() =>
  import('./pages/profile/Profile').then((m) => ({ default: m.ProfilePage }))
);
const WebhooksPage = lazy(() =>
  import('./pages/webhooks/WebhooksPage').then((m) => ({ default: m.WebhooksPage }))
);
const UsagePage = lazy(() => import('./pages/usage').then((m) => ({ default: m.UsagePage })));
const ServiceAccountsPage = lazy(() =>
  import('./pages/service-accounts/ServiceAccountsPage').then((m) => ({
    default: m.ServiceAccountsPage,
  }))
);
const WorkspacePage = lazy(() =>
  import('./pages/workspace').then((m) => ({ default: m.WorkspacePage }))
);
const ConsumerRegistrationPage = lazy(() =>
  import('./pages/consumers').then((m) => ({ default: m.ConsumerRegistrationPage }))
);
const GatewaysPage = lazy(() =>
  import('./pages/gateways').then((m) => ({ default: m.GatewaysPage }))
);
const ExecutionHistoryPage = lazy(() =>
  import('./pages/executions').then((m) => ({ default: m.ExecutionHistoryPage }))
);
const UnauthorizedPage = lazy(() =>
  import('./pages/Unauthorized').then((m) => ({ default: m.UnauthorizedPage }))
);
const OnboardingWizardPage = lazy(() =>
  import('./pages/onboarding').then((m) => ({ default: m.OnboardingWizardPage }))
);
const CredentialMappingsPage = lazy(() =>
  import('./pages/credential-mappings').then((m) => ({ default: m.CredentialMappingsPage }))
);

// Loading indicator for lazy-loaded pages
function PageLoader() {
  return <StoaLoader variant="inline" />;
}

// Full-screen loading during auth initialization
function LoadingScreen() {
  return <StoaLoader variant="fullscreen" />;
}

// Login screen — registration-first design with enterprise access fallback
function LoginScreen() {
  const { login, register } = useAuth();
  const [showEnterprise, setShowEnterprise] = useState(false);
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [website, setWebsite] = useState(''); // Honeypot — hidden, traps bots
  const [submitState, setSubmitState] = useState<'idle' | 'submitting' | 'success' | 'error'>(
    'idle'
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitState('submitting');
    try {
      const res = await fetch('/api/v1/access-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          first_name: firstName || undefined,
          last_name: lastName || undefined,
          company: company || undefined,
          role: role || undefined,
          source: 'portal',
          website: website || undefined,
        }),
      });
      if (res.ok) {
        setSubmitState('success');
      } else {
        setSubmitState('error');
      }
    } catch {
      setSubmitState('error');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-600 to-accent-600 dark:from-primary-900 dark:to-accent-900 flex items-center justify-center p-4 transition-colors">
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl max-w-2xl w-full flex flex-col md:flex-row overflow-hidden">
        {/* Left panel — value prop */}
        <div className="bg-primary-700 dark:bg-primary-900 text-white p-8 md:w-1/2 flex flex-col justify-center">
          <h2 className="text-2xl font-bold mb-4">Discover AI-powered APIs</h2>
          <ul className="space-y-3 text-primary-100">
            <li className="flex items-start gap-2">
              <span className="mt-1 flex-shrink-0">&#x2713;</span>
              <span>Browse the API &amp; MCP tool catalog</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 flex-shrink-0">&#x2713;</span>
              <span>Connect AI agents to enterprise APIs</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 flex-shrink-0">&#x2713;</span>
              <span>Monitor usage &amp; analytics</span>
            </li>
          </ul>
          <a
            href={config.services.docs.url}
            className="mt-6 text-sm text-primary-200 hover:text-white underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            Browse documentation &rarr;
          </a>
        </div>

        {/* Right panel — registration-first */}
        <div className="p-8 md:w-1/2">
          <div className="mx-auto mb-6">
            <StoaLogo size="lg" />
          </div>

          {/* Primary: Create account */}
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-white mb-2">
            Create your free developer account
          </h3>
          <ul className="text-sm text-neutral-600 dark:text-neutral-400 space-y-1 mb-4">
            <li>&#x2713; Instant access to the API &amp; MCP catalog</li>
            <li>&#x2713; Personal workspace with API keys</li>
            <li>&#x2713; Free tier &mdash; no credit card required</li>
          </ul>
          <button
            onClick={register}
            className="w-full py-3 px-4 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors"
          >
            Create Free Account
          </button>
          <p className="text-xs text-neutral-500 dark:text-neutral-500 mt-2 text-center">
            By creating an account, you agree to our{' '}
            <a
              href={`${config.services.docs.url}/legal/terms`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 dark:text-primary-400 hover:underline"
            >
              Terms of Service
            </a>
          </p>

          {/* Sign in link */}
          <p className="text-sm text-neutral-500 dark:text-neutral-400 text-center mt-4">
            Already have an account?{' '}
            <button
              onClick={login}
              className="text-primary-600 dark:text-primary-400 hover:underline font-medium"
            >
              Sign in
            </button>
          </p>

          {/* Divider */}
          <div className="border-t border-neutral-200 dark:border-neutral-700 mt-6 pt-4">
            {/* Enterprise access toggle */}
            <button
              onClick={() => setShowEnterprise(!showEnterprise)}
              className="text-sm text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 w-full text-center"
            >
              Need enterprise access?{' '}
              <span className="text-primary-600 dark:text-primary-400 hover:underline">
                Request here
              </span>
            </button>

            {showEnterprise && (
              <div className="mt-4">
                {submitState === 'success' ? (
                  <div className="text-center py-4">
                    <div className="text-2xl mb-2">&#x2705;</div>
                    <p className="text-neutral-900 dark:text-white font-medium text-sm">
                      Thank you! We&apos;ll reach out shortly.
                    </p>
                  </div>
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label
                          htmlFor="firstName"
                          className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                        >
                          First name *
                        </label>
                        <input
                          id="firstName"
                          type="text"
                          required
                          value={firstName}
                          onChange={(e) => setFirstName(e.target.value)}
                          placeholder="Jane"
                          className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                        />
                      </div>
                      <div>
                        <label
                          htmlFor="lastName"
                          className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                        >
                          Last name *
                        </label>
                        <input
                          id="lastName"
                          type="text"
                          required
                          value={lastName}
                          onChange={(e) => setLastName(e.target.value)}
                          placeholder="Doe"
                          className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                        />
                      </div>
                    </div>
                    <div>
                      <label
                        htmlFor="email"
                        className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                      >
                        Work email *
                      </label>
                      <input
                        id="email"
                        type="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@company.com"
                        className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                      />
                    </div>
                    <div>
                      <label
                        htmlFor="company"
                        className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                      >
                        Company *
                      </label>
                      <input
                        id="company"
                        type="text"
                        required
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        placeholder="Acme Corp"
                        className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                      />
                    </div>
                    <div>
                      <label
                        htmlFor="role"
                        className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                      >
                        Role
                      </label>
                      <select
                        id="role"
                        value={role}
                        onChange={(e) => setRole(e.target.value)}
                        className="w-full px-3 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
                      >
                        <option value="">Select your role...</option>
                        <option value="developer">Developer</option>
                        <option value="architect">Architect</option>
                        <option value="devops">DevOps / SRE</option>
                        <option value="tech-lead">Tech Lead / CTO</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                    {/* Honeypot — hidden from real users, traps bots */}
                    <div style={{ position: 'absolute', left: '-9999px' }} aria-hidden="true">
                      <label htmlFor="website">Website</label>
                      <input
                        id="website"
                        type="text"
                        value={website}
                        onChange={(e) => setWebsite(e.target.value)}
                        tabIndex={-1}
                        autoComplete="off"
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={submitState === 'submitting'}
                      className="w-full py-2.5 px-4 bg-neutral-600 text-white rounded-lg font-medium hover:bg-neutral-700 disabled:opacity-50 transition-colors text-sm"
                    >
                      {submitState === 'submitting' ? 'Submitting...' : 'Request Enterprise Access'}
                    </button>
                    {submitState === 'error' && (
                      <p className="text-sm text-red-600 dark:text-red-400 text-center">
                        Something went wrong. Please try again.
                      </p>
                    )}
                  </form>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Protected route wrapper with RBAC support
interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Single permission to check */
  permission?: string;
  /** Multiple permissions to check */
  permissions?: string[];
  /** If true, ALL permissions must be present. If false (default), ANY permission suffices */
  requireAll?: boolean;
  /** Role to check (Keycloak realm role) */
  role?: string;
  /** OAuth2 scope to check */
  scope?: string;
}

function ProtectedRoute({
  children,
  permission,
  permissions,
  requireAll = false,
  role,
  scope,
}: ProtectedRouteProps) {
  const {
    isAuthenticated,
    isLoading,
    isReady,
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    hasRole,
    hasScope,
  } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  // Wait for permissions to be loaded before evaluating RBAC checks
  const hasRbacCheck = !!(permission || (permissions && permissions.length > 0) || role || scope);
  if (hasRbacCheck && !isReady) {
    return <LoadingScreen />;
  }

  // Check single permission
  if (permission && !hasPermission(permission)) {
    return <Navigate to="/unauthorized" state={{ from: location }} replace />;
  }

  // Check multiple permissions
  if (permissions && permissions.length > 0) {
    const hasAccess = requireAll ? hasAllPermissions(permissions) : hasAnyPermission(permissions);
    if (!hasAccess) {
      return <Navigate to="/unauthorized" state={{ from: location }} replace />;
    }
  }

  // Check role
  if (role && !hasRole(role)) {
    return <Navigate to="/unauthorized" state={{ from: location }} replace />;
  }

  // Check scope
  if (scope && !hasScope(scope)) {
    return <Navigate to="/unauthorized" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

// Main app content with routes
function AppContent() {
  return (
    <ProtectedRoute>
      <Layout>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            {/* Public routes (within authenticated context) */}
            <Route path="/" element={<HomePage />} />
            <Route path="/unauthorized" element={<UnauthorizedPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/onboarding" element={<OnboardingWizardPage />} />

            {/* Workspace - tabbed view for apps, subscriptions, contracts */}
            <Route
              path="/workspace"
              element={
                <ProtectedRoute permission="apps:read">
                  <WorkspacePage />
                </ProtectedRoute>
              }
            />

            {/* MCP Servers - requires catalog read */}
            <Route
              path="/servers"
              element={
                <ProtectedRoute scope="stoa:catalog:read">
                  <MCPServersPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/servers/:serverId"
              element={
                <ProtectedRoute scope="stoa:catalog:read">
                  <ServerDetailPage />
                </ProtectedRoute>
              }
            />

            {/* My MCP Servers - self-service management (CAB-1319) */}
            <Route
              path="/my-servers"
              element={
                <ProtectedRoute scope="stoa:catalog:read">
                  <MyMCPServersPage />
                </ProtectedRoute>
              }
            />

            {/* Redirect legacy /tools to /servers */}
            <Route path="/tools" element={<Navigate to="/servers" replace />} />
            <Route path="/tools/:id" element={<Navigate to="/servers" replace />} />

            {/* Redirect legacy /subscriptions to workspace */}
            <Route
              path="/subscriptions"
              element={<Navigate to="/workspace?tab=subscriptions" replace />}
            />

            {/* API Consumer Routes - requires catalog read */}
            <Route
              path="/apis"
              element={
                <ProtectedRoute scope="stoa:catalog:read">
                  <APICatalog />
                </ProtectedRoute>
              }
            />
            <Route
              path="/apis/:id"
              element={
                <ProtectedRoute scope="stoa:catalog:read">
                  <APIDetail />
                </ProtectedRoute>
              }
            />
            <Route
              path="/apis/:id/test"
              element={
                <ProtectedRoute scope="stoa:tools:execute">
                  <APITestingSandbox />
                </ProtectedRoute>
              }
            />

            {/* Redirect legacy /apps to workspace */}
            <Route path="/apps" element={<Navigate to="/workspace?tab=apps" replace />} />
            <Route
              path="/apps/:id"
              element={
                <ProtectedRoute permission="apps:read">
                  <ApplicationDetail />
                </ProtectedRoute>
              }
            />

            {/* Redirect legacy /contracts to workspace */}
            <Route path="/contracts" element={<Navigate to="/workspace?tab=contracts" replace />} />
            <Route
              path="/contracts/new"
              element={
                <ProtectedRoute scope="stoa:catalog:write">
                  <CreateContractPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/contracts/:id"
              element={
                <ProtectedRoute scope="stoa:catalog:read">
                  <ContractDetailPage />
                </ProtectedRoute>
              }
            />

            {/* Usage Dashboard - requires metrics read */}
            <Route
              path="/usage"
              element={
                <ProtectedRoute scope="stoa:metrics:read">
                  <UsagePage />
                </ProtectedRoute>
              }
            />

            {/* Execution History — Consumer execution view (CAB-1318) */}
            <Route
              path="/executions"
              element={
                <ProtectedRoute scope="stoa:metrics:read">
                  <ExecutionHistoryPage />
                </ProtectedRoute>
              }
            />

            {/* Consumer Registration (CAB-1121) */}
            <Route
              path="/consumers/register"
              element={
                <ProtectedRoute scope="stoa:subscriptions:write">
                  <ConsumerRegistrationPage />
                </ProtectedRoute>
              }
            />

            {/* Gateway Instances (Operations) — admin only */}
            <Route
              path="/gateways"
              element={
                <ProtectedRoute scope="stoa:admin">
                  <GatewaysPage />
                </ProtectedRoute>
              }
            />

            {/* Service Accounts — kept for backward compat */}
            <Route
              path="/service-accounts"
              element={
                <ProtectedRoute scope="stoa:subscriptions:write">
                  <ServiceAccountsPage />
                </ProtectedRoute>
              }
            />

            {/* Credential Mappings — consumer→API backend credentials (CAB-1432) */}
            <Route
              path="/credentials"
              element={
                <ProtectedRoute scope="stoa:catalog:read">
                  <CredentialMappingsPage />
                </ProtectedRoute>
              }
            />

            {/* Tenant Admin Routes - requires subscriptions write */}
            <Route
              path="/webhooks"
              element={
                <ProtectedRoute scope="stoa:subscriptions:write">
                  <WebhooksPage />
                </ProtectedRoute>
              }
            />

            {/* Catch all - redirect to home */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Layout>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <ErrorBoundary
      onError={(error, errorInfo) => {
        console.error('[App] Unhandled error:', error.message);
        captureException(error, { componentStack: errorInfo.componentStack });
      }}
    >
      <SkipLink />
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
