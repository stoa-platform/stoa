/**
 * TrialWarningBanner -- Portal component for demo tenant lifecycle
 * CAB-409: Displays contextual warnings based on trial status
 *
 * States:
 *   - Hidden: loading, error, > 3 days remaining, converted, deleted
 *   - Warning (amber): 1-3 days remaining
 *   - Urgent (orange): < 1 day remaining
 *   - Error (red): expired
 */
import { useState } from 'react';
import { useTenantLifecycle } from '../hooks/useTenantLifecycle';

interface TrialWarningBannerProps {
  tenantId: string | undefined;
}

export function TrialWarningBanner({ tenantId }: TrialWarningBannerProps) {
  const { data: status, loading, error } = useTenantLifecycle(tenantId);
  const [extending, setExtending] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // Silent fail: don't block UI on loading/error
  if (loading || error || !status) return null;
  if (status.state === 'converted' || status.state === 'deleted') return null;
  if (status.state === 'active' && status.days_left !== null && status.days_left > 3) return null;
  if (dismissed && status.state !== 'expired') return null;

  const handleExtend = async () => {
    if (!tenantId) return;
    setExtending(true);
    try {
      const res = await fetch(`/api/v1/tenants/${tenantId}/lifecycle/extend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error('Extension failed');
      // Reload page to refresh status
      window.location.reload();
    } catch (err) {
      console.error('Extension failed:', err);
    } finally {
      setExtending(false);
    }
  };

  const isExpired = status.state === 'expired';
  const isUrgent = status.days_left !== null && status.days_left <= 1;

  const variant = isExpired
    ? { bg: 'bg-red-50 border-red-200', textColor: 'text-red-800', buttonClass: 'bg-red-600 hover:bg-red-700 text-white' }
    : isUrgent
    ? { bg: 'bg-orange-50 border-orange-200', textColor: 'text-orange-800', buttonClass: 'bg-orange-600 hover:bg-orange-700 text-white' }
    : { bg: 'bg-amber-50 border-amber-200', textColor: 'text-amber-800', buttonClass: 'bg-amber-600 hover:bg-amber-700 text-white' };

  return (
    <div
      className={`${variant.bg} border rounded-lg px-4 py-3 flex items-center justify-between gap-4`}
      role="alert"
    >
      <div className={`flex items-center gap-3 ${variant.textColor}`}>
        <div>
          {isExpired ? (
            <p className="font-medium">
              Your trial has expired. Your tenant is in <strong>read-only mode</strong>.
              {status.is_read_only && ' API calls will return 403.'}
            </p>
          ) : (
            <p className="font-medium">
              Your trial expires in{' '}
              <strong>
                {status.days_left} day{status.days_left !== 1 ? 's' : ''}
              </strong>
              .
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {status.can_extend && (
          <button
            onClick={handleExtend}
            disabled={extending}
            className={`${variant.buttonClass} px-3 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50`}
          >
            {extending ? 'Extending...' : 'Extend +7 days'}
          </button>
        )}
        {status.can_upgrade && (
          <a
            href="/upgrade"
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 rounded text-sm font-medium transition-colors"
          >
            Upgrade
          </a>
        )}
        {!isExpired && (
          <button
            onClick={() => setDismissed(true)}
            className="text-gray-400 hover:text-gray-600 p-1"
            aria-label="Dismiss"
          >
            x
          </button>
        )}
      </div>
    </div>
  );
}
