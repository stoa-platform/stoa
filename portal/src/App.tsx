import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { Layout } from './components/layout';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ErrorBoundary, SkipLink } from './components/common';
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
const UnauthorizedPage = lazy(() =>
  import('./pages/Unauthorized').then((m) => ({ default: m.UnauthorizedPage }))
);

// Loading indicator for lazy-loaded pages
function PageLoader() {
  return <StoaLoader variant="inline" />;
}

// Full-screen loading during auth initialization
function LoadingScreen() {
  return <StoaLoader variant="fullscreen" />;
}

// Login screen
function LoginScreen() {
  const { login } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-600 to-accent-600 dark:from-primary-900 dark:to-accent-900 flex items-center justify-center p-4 transition-colors">
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl p-8 max-w-md w-full">
        <div className="text-center mb-8">
          <div className="mx-auto mb-4">
            <StoaLogo size="lg" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            STOA Developer Portal
          </h1>
          <p className="text-gray-500 dark:text-neutral-400 mt-2">
            Sign in to access tools and APIs
          </p>
        </div>

        <button
          onClick={login}
          className="w-full py-3 px-4 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors"
        >
          Sign in with SSO
        </button>

        <p className="text-center text-sm text-gray-500 dark:text-neutral-400 mt-6">
          Don't have an account?{' '}
          <a
            href={`${config.services.console.url}/register`}
            className="text-primary-600 dark:text-primary-400 hover:underline"
          >
            Contact your administrator
          </a>
        </p>
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

            {/* Consumer Registration (CAB-1121) */}
            <Route
              path="/consumers/register"
              element={
                <ProtectedRoute scope="stoa:subscriptions:write">
                  <ConsumerRegistrationPage />
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
        // Log to console in development
        console.error('[App] Unhandled error:', error.message);
        console.error('[App] Component stack:', errorInfo.componentStack);

        // TODO: Send to error tracking service
        // trackError(error, { componentStack: errorInfo.componentStack });
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
