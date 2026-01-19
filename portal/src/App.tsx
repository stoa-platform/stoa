import { Routes, Route, Navigate } from 'react-router-dom';
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

// Protected route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <LoginScreen />;
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
            <Route path="/" element={<HomePage />} />
            {/* MCP Servers (grouped tools with role-based visibility) */}
            <Route path="/servers" element={<MCPServersPage />} />
            <Route path="/servers/:serverId" element={<ServerDetailPage />} />
            {/* Redirect legacy /tools to /servers */}
            <Route path="/tools" element={<Navigate to="/servers" replace />} />
            <Route path="/tools/:id" element={<Navigate to="/servers" replace />} />
            <Route path="/subscriptions" element={<MySubscriptions />} />
            {/* API Consumer Routes */}
            <Route path="/apis" element={<APICatalog />} />
            <Route path="/apis/:id" element={<APIDetail />} />
            <Route path="/apis/:id/test" element={<APITestingSandbox />} />
            {/* Consumer Applications */}
            <Route path="/apps" element={<MyApplications />} />
            <Route path="/apps/:id" element={<ApplicationDetail />} />
            {/* Universal API Contracts (UAC) */}
            <Route path="/contracts" element={<ContractListPage />} />
            <Route path="/contracts/new" element={<CreateContractPage />} />
            <Route path="/contracts/:id" element={<ContractDetailPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            {/* Usage Dashboard */}
            <Route path="/usage" element={<UsagePage />} />
            {/* Service Accounts for MCP */}
            <Route path="/service-accounts" element={<ServiceAccountsPage />} />
            {/* Tenant Admin Routes */}
            <Route path="/webhooks" element={<WebhooksPage />} />
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
