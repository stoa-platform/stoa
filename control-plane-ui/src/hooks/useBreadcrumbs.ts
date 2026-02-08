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
  'gateway-observability': 'Observability',
  applications: 'Applications',
  deployments: 'Deployments',
  monitoring: 'API Monitoring',
  mcp: 'MCP',
  errors: 'Error Snapshots',
  admin: 'Admin',
  prospects: 'Prospects',
};

/**
 * Hook to generate breadcrumbs from the current route
 */
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
