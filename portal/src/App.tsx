// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { Layout } from './components/layout';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ErrorBoundary, SkipLink } from './components/common';
import { config } from './config';

// Lazy load pages for code splitting - reduces initial bundle by ~60%
const HomePage = lazy(() => import('./pages/Home').then(m => ({ default: m.HomePage })));
const MCPServersPage = lazy(() => import('./pages/servers').then(m => ({ default: m.MCPServersPage })));
const ServerDetailPage = lazy(() => import('./pages/servers').then(m => ({ default: m.ServerDetailPage })));
const MySubscriptions = lazy(() => import('./pages/subscriptions/MySubscriptions').then(m => ({ default: m.MySubscriptions })));
const APICatalog = lazy(() => import('./pages/apis').then(m => ({ default: m.APICatalog })));
const APIDetail = lazy(() => import('./pages/apis').then(m => ({ default: m.APIDetail })));
const APITestingSandbox = lazy(() => import('./pages/apis').then(m => ({ default: m.APITestingSandbox })));
const MyApplications = lazy(() => import('./pages/apps').then(m => ({ default: m.MyApplications })));
const ApplicationDetail = lazy(() => import('./pages/apps').then(m => ({ default: m.ApplicationDetail })));
const ContractListPage = lazy(() => import('./pages/contracts').then(m => ({ default: m.ContractListPage })));
const ContractDetailPage = lazy(() => import('./pages/contracts').then(m => ({ default: m.ContractDetailPage })));
const CreateContractPage = lazy(() => import('./pages/contracts').then(m => ({ default: m.CreateContractPage })));
const ProfilePage = lazy(() => import('./pages/profile/Profile').then(m => ({ default: m.ProfilePage })));
const WebhooksPage = lazy(() => import('./pages/webhooks/WebhooksPage').then(m => ({ default: m.WebhooksPage })));
const UsagePage = lazy(() => import('./pages/usage').then(m => ({ default: m.UsagePage })));
const ServiceAccountsPage = lazy(() => import('./pages/service-accounts/ServiceAccountsPage').then(m => ({ default: m.ServiceAccountsPage })));
const UnauthorizedPage = lazy(() => import('./pages/Unauthorized').then(m => ({ default: m.UnauthorizedPage })));

// Page loader skeleton for lazy-loaded pages
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="text-center">
        <div className="w-10 h-10 bg-primary-600 rounded-lg flex items-center justify-center mx-auto mb-3 animate-pulse">
          <span className="text-white font-bold text-sm">SP</span>
        </div>
        <p className="text-gray-500 text-sm">Loading...</p>
      </div>
    </div>
  );
}

// Loading screen
function LoadingScreen() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 bg-primary-600 rounded-xl flex items-center justify-center mx-auto mb-4 animate-pulse">
          <span className="text-white font-bold text-xl">SP</span>
        </div>
        <p className="text-gray-500">Loading...</p>
      </div>
    </div>
  );
}

// Login screen
function LoginScreen() {
  const { login } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-600 to-accent-600 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl p-8 max-w-md w-full">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-primary-600 rounded-xl flex items-center justify-center mx-auto mb-4">
            <span className="text-white font-bold text-xl">SP</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">STOA Developer Portal</h1>
          <p className="text-gray-500 mt-2">
            Sign in to access tools and APIs
          </p>
        </div>

        <button
          onClick={login}
          className="w-full py-3 px-4 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors"
        >
          Sign in with SSO
        </button>

        <p className="text-center text-sm text-gray-500 mt-6">
          Don't have an account?{' '}
          <a href={`${config.services.console.url}/register`} className="text-primary-600 hover:underline">
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
  const { isAuthenticated, isLoading, hasPermission, hasAnyPermission, hasAllPermissions, hasRole, hasScope } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  // Check single permission
  if (permission && !hasPermission(permission)) {
    return <Navigate to="/unauthorized" state={{ from: location }} replace />;
  }

  // Check multiple permissions
  if (permissions && permissions.length > 0) {
    const hasAccess = requireAll
      ? hasAllPermissions(permissions)
      : hasAnyPermission(permissions);
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

            {/* MCP Servers - requires catalog read */}
            <Route path="/servers" element={
              <ProtectedRoute scope="stoa:catalog:read">
                <MCPServersPage />
              </ProtectedRoute>
            } />
            <Route path="/servers/:serverId" element={
              <ProtectedRoute scope="stoa:catalog:read">
                <ServerDetailPage />
              </ProtectedRoute>
            } />

            {/* Redirect legacy /tools to /servers */}
            <Route path="/tools" element={<Navigate to="/servers" replace />} />
            <Route path="/tools/:id" element={<Navigate to="/servers" replace />} />

            {/* Subscriptions - requires subscriptions read */}
            <Route path="/subscriptions" element={
              <ProtectedRoute scope="stoa:subscriptions:read">
                <MySubscriptions />
              </ProtectedRoute>
            } />

            {/* API Consumer Routes - requires catalog read */}
            <Route path="/apis" element={
              <ProtectedRoute scope="stoa:catalog:read">
                <APICatalog />
              </ProtectedRoute>
            } />
            <Route path="/apis/:id" element={
              <ProtectedRoute scope="stoa:catalog:read">
                <APIDetail />
              </ProtectedRoute>
            } />
            <Route path="/apis/:id/test" element={
              <ProtectedRoute scope="stoa:tools:execute">
                <APITestingSandbox />
              </ProtectedRoute>
            } />

            {/* Consumer Applications - requires apps read */}
            <Route path="/apps" element={
              <ProtectedRoute permission="apps:read">
                <MyApplications />
              </ProtectedRoute>
            } />
            <Route path="/apps/:id" element={
              <ProtectedRoute permission="apps:read">
                <ApplicationDetail />
              </ProtectedRoute>
            } />

            {/* Universal API Contracts (UAC) - requires catalog read/write */}
            <Route path="/contracts" element={
              <ProtectedRoute scope="stoa:catalog:read">
                <ContractListPage />
              </ProtectedRoute>
            } />
            <Route path="/contracts/new" element={
              <ProtectedRoute scope="stoa:catalog:write">
                <CreateContractPage />
              </ProtectedRoute>
            } />
            <Route path="/contracts/:id" element={
              <ProtectedRoute scope="stoa:catalog:read">
                <ContractDetailPage />
              </ProtectedRoute>
            } />

            {/* Usage Dashboard - requires metrics read */}
            <Route path="/usage" element={
              <ProtectedRoute scope="stoa:metrics:read">
                <UsagePage />
              </ProtectedRoute>
            } />

            {/* Service Accounts for MCP - requires subscriptions write (tenant-admin+) */}
            <Route path="/service-accounts" element={
              <ProtectedRoute scope="stoa:subscriptions:write">
                <ServiceAccountsPage />
              </ProtectedRoute>
            } />

            {/* Tenant Admin Routes - requires subscriptions write */}
            <Route path="/webhooks" element={
              <ProtectedRoute scope="stoa:subscriptions:write">
                <WebhooksPage />
              </ProtectedRoute>
            } />

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
