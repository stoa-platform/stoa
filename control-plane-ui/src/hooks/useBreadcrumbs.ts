import { useMemo } from 'react';
import { useLocation, useParams } from 'react-router-dom';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

// Route configuration for breadcrumb labels
const routeLabels: Record<string, string> = {
  '': 'Dashboard',
  tenants: 'Tenants',
  apis: 'APIs',
  'ai-tools': 'AI Tools',
  subscriptions: 'Subscriptions',
  usage: 'Usage',
  'external-mcp-servers': 'External MCP Servers',
  gateway: 'Gateway',
  gateways: 'Gateway Registry',
  'gateway-deployments': 'Gateway Deployments',
  drift: 'Drift Detection',
  'gateway-observability': 'Gateway Observability',
  observability: 'Observability',
  'live-calls': 'Live Calls',
  security: 'Security & Guardrails',
  'call-flow': 'Live Calls',
  applications: 'Applications',
  deployments: 'Deployments',
  monitoring: 'API Monitoring',
  mcp: 'MCP',
  errors: 'Error Snapshots',
  admin: 'Admin',
  prospects: 'Prospects',
  analytics: 'Analytics',
  'access-requests': 'Access Requests',
  roles: 'Roles',
  settings: 'Settings',
  users: 'Users',
  'audience-governance': 'Audience Governance',
  'audit-log': 'Audit Log',
  'backend-apis': 'Backend APIs',
  business: 'Business',
  consumers: 'Consumers',
  diagnostics: 'Diagnostics',
  executions: 'Executions',
  federation: 'Federation',
  accounts: 'Accounts',
  'gateways/modes': 'Modes',
  modes: 'Modes',
  identity: 'Identity',
  'llm-cost': 'LLM Cost',
  login: 'Login',
  logs: 'Logs',
  opensearch: 'OpenSearch',
  'my-usage': 'My Usage',
  'observability/benchmarks': 'Benchmarks',
  'observability/platform': 'Platform Metrics',
  platform: 'Platform Metrics',
  benchmarks: 'Benchmarks',
  'observability/grafana': 'Grafana',
  grafana: 'Grafana',
  operations: 'Operations',
  policies: 'Policies',
  'proxy-owner': 'Proxy Owner',
  'saas-api-keys': 'SaaS API Keys',
  'security-posture': 'Security Posture',
  'shadow-discovery': 'Shadow Discovery',
  skills: 'Skills',
  'token-optimizer': 'Token Optimizer',
  workflows: 'Workflows',
};

/**
 * Hook to generate breadcrumbs from the current route
 */
function safeDecodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

export function useBreadcrumbs(): BreadcrumbItem[] {
  const location = useLocation();
  const params = useParams();

  return useMemo(() => {
    const pathSegments = location.pathname.split('/').filter(Boolean);

    // Always start with Dashboard
    const breadcrumbs: BreadcrumbItem[] = [{ label: 'Dashboard', href: '/' }];

    // If we're on the dashboard, don't add more
    if (pathSegments.length === 0) {
      return [{ label: 'Dashboard' }]; // No href = current page
    }

    if (
      pathSegments[0] === 'observability' &&
      pathSegments[1] === 'live-calls' &&
      pathSegments[2] === 'trace'
    ) {
      const traceId = safeDecodeSegment(pathSegments[3] || '');
      return [
        { label: 'Dashboard', href: '/' },
        { label: 'Observability', href: '/observability' },
        { label: 'Live Calls', href: '/observability/live-calls' },
        { label: traceId ? `Trace ${traceId}` : 'Trace' },
      ];
    }

    // Build breadcrumbs from path segments
    let currentPath = '';

    pathSegments.forEach((segment, index) => {
      currentPath += `/${segment}`;
      const isLast = index === pathSegments.length - 1;

      // Check if this segment is a dynamic param (like an ID)
      const isDynamicParam = Object.values(params).includes(segment);

      // Get label from route config or format the segment
      let label = routeLabels[segment];

      if (!label) {
        if (isDynamicParam) {
          // For dynamic params, try to get a meaningful name or use "Details"
          label = 'Details';
        } else {
          // Format segment as title case
          label = segment
            .split('-')
            .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
        }
      }

      breadcrumbs.push({
        label,
        href: isLast ? undefined : currentPath,
      });
    });

    return breadcrumbs;
  }, [location.pathname, params]);
}

export default useBreadcrumbs;
