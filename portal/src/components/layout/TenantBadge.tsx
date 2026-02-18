import { Building2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';

interface TenantBadgeProps {
  className?: string;
}

export function TenantBadge({ className }: TenantBadgeProps) {
  const { user } = useAuth();

  const tenantName = user?.organization || user?.tenant_id;
  if (!tenantName) return null;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 ${className ?? ''}`}
      data-testid="tenant-badge"
    >
      <Building2 className="h-3 w-3" aria-hidden="true" />
      {tenantName}
    </span>
  );
}
