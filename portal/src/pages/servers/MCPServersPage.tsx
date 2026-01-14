/**
 * MCP Servers Page
 *
 * Browse MCP Servers (grouped tool collections) with role-based visibility.
 * - Platform servers (admin-only) shown only to cpi-admin/tenant-admin/devops
 * - Tenant APIs visible to all tenant members
 * - Public APIs visible to all authenticated users
 */

import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Server,
  Settings,
  Users,
  Globe,
  ArrowRight,
  Wrench,
  Loader2,
  AlertCircle,
  RefreshCw,
  Shield,
  CheckCircle,
  Clock,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { mcpServersService, MOCK_SERVERS } from '../../services/mcpServers';
import type { MCPServer, MCPServerSubscription } from '../../types';

type ServerCategory = 'all' | 'platform' | 'tenant' | 'public';

const categoryConfig: Record<ServerCategory, {
  label: string;
  icon: React.ElementType;
  description: string;
}> = {
  all: { label: 'All Servers', icon: Server, description: 'All available MCP servers' },
  platform: { label: 'Platform Tools', icon: Settings, description: 'STOA administration tools' },
  tenant: { label: 'Tenant APIs', icon: Users, description: 'Organization-specific APIs' },
  public: { label: 'Public APIs', icon: Globe, description: 'Publicly available APIs' },
};

const statusColors: Record<string, { bg: string; text: string }> = {
  active: { bg: 'bg-green-100', text: 'text-green-700' },
  maintenance: { bg: 'bg-amber-100', text: 'text-amber-700' },
  deprecated: { bg: 'bg-red-100', text: 'text-red-700' },
};

export function MCPServersPage() {
  const { user, isAuthenticated, accessToken } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<ServerCategory>('all');
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [subscriptions, setSubscriptions] = useState<MCPServerSubscription[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Check if user has admin/devops role
  const isAdminUser = useMemo(() => {
    const roles = user?.roles || [];
    return roles.includes('cpi-admin') || roles.includes('tenant-admin') || roles.includes('devops');
  }, [user?.roles]);

  // Load servers
  useEffect(() => {
    if (!isAuthenticated || !accessToken) return;

    async function loadServers() {
      setIsLoading(true);
      setError(null);

      try {
        // Try to fetch from API, fallback to mock data
        let fetchedServers: MCPServer[];
        try {
          fetchedServers = await mcpServersService.getVisibleServers(user);
        } catch {
          // Use mock data filtered by user roles
          fetchedServers = mcpServersService.filterServersByRole(MOCK_SERVERS, user);
        }

        setServers(fetchedServers);

        // Try to fetch subscriptions
        try {
          const subs = await mcpServersService.getMyServerSubscriptions();
          setSubscriptions(subs);
        } catch {
          setSubscriptions([]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load servers');
      } finally {
        setIsLoading(false);
      }
    }

    loadServers();
  }, [isAuthenticated, accessToken, user]);

  // Filter servers by category and search
  const filteredServers = useMemo(() => {
    let result = servers;

    // Filter by category
    if (selectedCategory !== 'all') {
      result = result.filter(s => s.category === selectedCategory);
    }

    // Filter by search
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        s =>
          s.displayName.toLowerCase().includes(query) ||
          s.description.toLowerCase().includes(query) ||
          s.tools.some(t => t.displayName.toLowerCase().includes(query))
      );
    }

    return result;
  }, [servers, selectedCategory, searchQuery]);

  // Get subscription status for a server
  const getSubscriptionStatus = (serverId: string) => {
    return subscriptions.find(s => s.server_id === serverId);
  };

  // Available categories based on user's roles
  const availableCategories = useMemo(() => {
    const cats: ServerCategory[] = ['all'];
    if (isAdminUser) cats.push('platform');
    cats.push('tenant', 'public');
    return cats;
  }, [isAdminUser]);

  // Get category icon
  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'platform':
        return Settings;
      case 'tenant':
        return Users;
      case 'public':
        return Globe;
      default:
        return Server;
    }
  };

  const handleRefresh = () => {
    setIsLoading(true);
    // Re-trigger the effect
    setServers([]);
    setTimeout(() => {
      const filtered = mcpServersService.filterServersByRole(MOCK_SERVERS, user);
      setServers(filtered);
      setIsLoading(false);
    }, 500);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">MCP Servers</h1>
          <p className="text-gray-500 mt-1">
            Subscribe to server collections for unified API access
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={isLoading}
          className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Admin Notice */}
      {isAdminUser && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <Shield className="h-5 w-5 text-blue-600 mt-0.5" />
            <div>
              <h3 className="font-medium text-blue-800">Admin Access</h3>
              <p className="text-sm text-blue-600 mt-1">
                You have access to Platform Tools (STOA administration) which are not visible to standard users.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Search and Category Filter */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search servers or tools..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
      </div>

      {/* Category Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-gray-200 pb-4">
        {availableCategories.map((cat) => {
          const config = categoryConfig[cat];
          const Icon = config.icon;
          const count = cat === 'all'
            ? servers.length
            : servers.filter(s => s.category === cat).length;

          return (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                selectedCategory === cat
                  ? 'bg-primary-100 text-primary-700 border border-primary-200'
                  : 'bg-gray-50 text-gray-600 border border-gray-200 hover:bg-gray-100'
              }`}
            >
              <Icon className="h-4 w-4" />
              {config.label}
              <span className={`px-2 py-0.5 rounded-full text-xs ${
                selectedCategory === cat ? 'bg-primary-200' : 'bg-gray-200'
              }`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <Loader2 className="h-8 w-8 text-primary-600 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading servers...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
            <div>
              <h3 className="font-medium text-red-800">Failed to load servers</h3>
              <p className="text-sm text-red-600 mt-1">{error}</p>
              <button
                onClick={handleRefresh}
                className="mt-3 px-4 py-2 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm font-medium transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Servers Grid */}
      {!isLoading && !error && filteredServers.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredServers.map((server) => {
            const CategoryIcon = getCategoryIcon(server.category);
            const statusStyle = statusColors[server.status] || statusColors.active;
            const subscription = getSubscriptionStatus(server.id);

            return (
              <Link
                key={server.id}
                to={`/servers/${server.id}`}
                className="bg-white rounded-lg border border-gray-200 p-5 hover:border-primary-300 hover:shadow-md transition-all group"
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="p-2 bg-primary-50 rounded-lg">
                    <CategoryIcon className="h-5 w-5 text-primary-600" />
                  </div>
                  <div className="flex items-center gap-2">
                    {subscription && (
                      <span className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded ${
                        subscription.status === 'active'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}>
                        {subscription.status === 'active' ? (
                          <><CheckCircle className="h-3 w-3" /> Subscribed</>
                        ) : (
                          <><Clock className="h-3 w-3" /> Pending</>
                        )}
                      </span>
                    )}
                    <span className={`px-2 py-1 text-xs font-medium rounded ${statusStyle.bg} ${statusStyle.text}`}>
                      {server.status}
                    </span>
                  </div>
                </div>

                {/* Title & Description */}
                <h3 className="font-semibold text-gray-900 group-hover:text-primary-700 transition-colors">
                  {server.displayName}
                </h3>
                <p className="text-sm text-gray-500 mt-1 line-clamp-2">
                  {server.description}
                </p>

                {/* Tools Count */}
                <div className="flex items-center gap-4 mt-4 text-sm text-gray-500">
                  <div className="flex items-center gap-1">
                    <Wrench className="h-4 w-4" />
                    <span>{server.tools.length} tools</span>
                  </div>
                  {server.version && (
                    <span className="text-gray-400">v{server.version}</span>
                  )}
                </div>

                {/* Tools Preview */}
                <div className="flex flex-wrap gap-1 mt-3">
                  {server.tools.slice(0, 3).map((tool) => (
                    <span
                      key={tool.id}
                      className="inline-flex items-center px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-full"
                    >
                      {tool.displayName}
                    </span>
                  ))}
                  {server.tools.length > 3 && (
                    <span className="text-xs text-gray-400">
                      +{server.tools.length - 3} more
                    </span>
                  )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
                  <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded capitalize">
                    {server.category}
                  </span>
                  <span className="flex items-center gap-1 text-sm font-medium text-primary-600 group-hover:text-primary-700">
                    {subscription ? 'Manage' : 'Subscribe'}
                    <ArrowRight className="h-4 w-4" />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredServers.length === 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-12 text-center">
          <div className="inline-flex p-4 bg-gray-100 rounded-full mb-4">
            <Server className="h-8 w-8 text-gray-400" />
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">No Servers Found</h2>
          <p className="text-gray-500 max-w-md mx-auto mb-6">
            {searchQuery || selectedCategory !== 'all'
              ? 'No servers match your current filters. Try adjusting your search or category.'
              : 'No MCP servers are currently available for your account.'}
          </p>
          {(searchQuery || selectedCategory !== 'all') && (
            <button
              onClick={() => {
                setSearchQuery('');
                setSelectedCategory('all');
              }}
              className="text-primary-600 hover:text-primary-700 font-medium"
            >
              Clear Filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default MCPServersPage;
