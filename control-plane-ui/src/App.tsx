import { Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy, memo } from 'react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { Layout } from './components/Layout';
import { PlatformStatus } from './components/PlatformStatus';
import { quickLinks } from './config';

// Lazy load pages for code splitting
const Tenants = lazy(() => import('./pages/Tenants').then(m => ({ default: m.Tenants })));
const APIs = lazy(() => import('./pages/APIs').then(m => ({ default: m.APIs })));
const Applications = lazy(() => import('./pages/Applications').then(m => ({ default: m.Applications })));
const Deployments = lazy(() => import('./pages/Deployments').then(m => ({ default: m.Deployments })));
const APIMonitoring = lazy(() => import('./pages/APIMonitoring').then(m => ({ default: m.APIMonitoring })));
const ErrorSnapshots = lazy(() => import('./pages/ErrorSnapshots').then(m => ({ default: m.ErrorSnapshots })));
const ToolCatalog = lazy(() => import('./pages/AITools').then(m => ({ default: m.ToolCatalog })));
const ToolDetail = lazy(() => import('./pages/AITools').then(m => ({ default: m.ToolDetail })));
const MySubscriptions = lazy(() => import('./pages/AITools').then(m => ({ default: m.MySubscriptions })));
const UsageDashboard = lazy(() => import('./pages/AITools').then(m => ({ default: m.UsageDashboard })));
const ExternalMCPServersList = lazy(() => import('./pages/ExternalMCPServers').then(m => ({ default: m.ExternalMCPServersList })));
const ExternalMCPServerDetail = lazy(() => import('./pages/ExternalMCPServers').then(m => ({ default: m.ExternalMCPServerDetail })));
const AdminProspects = lazy(() => import('./pages/AdminProspects').then(m => ({ default: m.AdminProspects })));
const GatewayStatus = lazy(() => import('./pages/GatewayStatus'));

// Loading spinner for lazy-loaded pages
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  );
}

function Dashboard() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-2">Welcome to STOA Control Plane</p>
      </div>

      {/* Welcome Card */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Hello, {user?.name || 'User'}!</h2>
            <p className="text-sm text-gray-500">{user?.email}</p>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <QuickActionCard
          title="APIs"
          description="Manage API definitions and deployments"
          href="/apis"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          }
          color="blue"
        />
        <QuickActionCard
          title="AI Tools"
          description="Browse MCP tools catalog"
          href="/ai-tools"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          }
          color="orange"
        />
        <QuickActionCard
          title="Applications"
          description="Manage consumer applications"
          href="/applications"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
          }
          color="purple"
        />
        <QuickActionCard
          title="Deployments"
          description="View deployment history"
          href="/deployments"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          }
          color="green"
        />
      </div>

      {/* Platform Status (CAB-654) */}
      <PlatformStatus />

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Links</h3>
          <ul className="space-y-3">
            {quickLinks.map((link) => (
              <li key={link.name}>
                <a href={link.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-blue-600 hover:text-blue-800">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  {link.name}
                </a>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Getting Started</h3>
          <ol className="space-y-3 text-sm text-gray-600">
            <li className="flex gap-2">
              <span className="font-bold text-blue-600">1.</span>
              <span>Go to <a href="/apis" className="text-blue-600 hover:underline">APIs</a> and create a new API</span>
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
              <span>Monitor deployments in the <a href="/deployments" className="text-blue-600 hover:underline">Deployments</a> page</span>
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
  blue: 'bg-blue-50 text-blue-600 hover:bg-blue-100',
  purple: 'bg-purple-50 text-purple-600 hover:bg-purple-100',
  green: 'bg-green-50 text-green-600 hover:bg-green-100',
  orange: 'bg-orange-50 text-orange-600 hover:bg-orange-100',
} as const;

const QuickActionCard = memo(function QuickActionCard({ title, description, href, icon, color }: QuickActionCardProps) {
  return (
    <a
      href={href}
      className={`block p-6 rounded-lg transition-colors ${quickActionColorClasses[color]}`}
    >
      <div className="flex items-center gap-4">
        <div className="flex-shrink-0">{icon}</div>
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="text-sm opacity-80">{description}</p>
        </div>
      </div>
    </a>
  );
});

function ProtectedRoutes() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <Layout>
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
          <Route path="/deployments" element={<Deployments />} />
          <Route path="/monitoring" element={<APIMonitoring />} />
          <Route path="/mcp/errors" element={<ErrorSnapshots />} />
          <Route path="/external-mcp-servers" element={<ExternalMCPServersList />} />
          <Route path="/external-mcp-servers/:id" element={<ExternalMCPServerDetail />} />
          <Route path="/gateway" element={<GatewayStatus />} />
          <Route path="/admin/prospects" element={<AdminProspects />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}

function Login() {
  const { login, isLoading } = useAuth();

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-blue-500 to-purple-600">
      <div className="bg-white p-8 rounded-xl shadow-2xl w-96">
        <div className="text-center mb-6">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">STOA Control Plane</h1>
          <p className="text-gray-500 mt-1">Multi-tenant API Management</p>
        </div>
        <button
          onClick={login}
          disabled={isLoading}
          className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              Loading...
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1" />
              </svg>
              Login with Keycloak
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={<ProtectedRoutes />} />
      </Routes>
    </AuthProvider>
  );
}

export default App;
