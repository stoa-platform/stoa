import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/layout';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { HomePage } from './pages/Home';
import { MCPServersPage, ServerDetailPage } from './pages/servers';
import { MySubscriptions } from './pages/subscriptions/MySubscriptions';
import { APICatalog, APIDetail, APITestingSandbox } from './pages/apis';
import { MyApplications, ApplicationDetail } from './pages/apps';
import { ProfilePage } from './pages/profile/Profile';
import { WebhooksPage } from './pages/webhooks/WebhooksPage';
import { UsagePage } from './pages/usage';
import { ServiceAccountsPage } from './pages/service-accounts/ServiceAccountsPage';
import { config } from './config';

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
          <Route path="/profile" element={<ProfilePage />} />
          {/* Usage Dashboard */}
          <Route path="/usage" element={<UsagePage />} />
          {/* Service Accounts for MCP */}
          <Route path="/service-accounts" element={<ServiceAccountsPage />} />
          {/* Tenant Admin Routes */}
          <Route path="/webhooks" element={<WebhooksPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
