/**
 * useTenantLifecycle — Hook to fetch tenant lifecycle status
 * CAB-409: COUNCIL #2
 */
import { useState, useEffect } from 'react';
import { useAuth } from 'react-oidc-context';

interface TenantLifecycleStatus {
  tenant_id: string;
  tenant_name: string;
  state: 'active' | 'warning' | 'expired' | 'deleted' | 'converted';
  created_at: string;
  expires_at: string | null;
  lifecycle_changed_at: string;
  days_left: number | null;
  can_extend: boolean;
  can_upgrade: boolean;
  is_read_only: boolean;
}

export function useTenantLifecycle(tenantId: string | undefined) {
  const auth = useAuth();
  const [data, setData] = useState<TenantLifecycleStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!tenantId || !auth.user?.access_token) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    fetch(`/api/v1/tenants/${tenantId}/lifecycle/status`, {
      headers: { Authorization: `Bearer ${auth.user.access_token}` },
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(d => { if (!cancelled) setData(d); })
      .catch(e => { if (!cancelled) setError(e); })
      .finally(() => { if (!cancelled) setLoading(false); });

    // Refresh every 5 minutes
    const interval = setInterval(() => {
      if (!auth.user?.access_token) return;
      fetch(`/api/v1/tenants/${tenantId}/lifecycle/status`, {
        headers: { Authorization: `Bearer ${auth.user.access_token}` },
      })
        .then(res => res.ok ? res.json() : null)
        .then(d => { if (d && !cancelled) setData(d); })
        .catch(() => {});
    }, 5 * 60 * 1000);

    return () => { cancelled = true; clearInterval(interval); };
  }, [tenantId, auth.user?.access_token]);

  return { data, loading, error };
}
