/**
 * Approval Queue Component
 *
 * Shows pending subscription requests for tenant admins to approve or reject.
 *
 * Reference: CAB-1121 Phase 5
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Clock, Loader2, AlertCircle, Inbox, User, FileCode2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { apiSubscriptionsService, APISubscriptionResponse } from '../../services/apiSubscriptions';
import { useToastActions } from '@stoa/shared/components/Toast';

export function ApprovalQueue() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToastActions();
  const [approvingId, setApprovingId] = useState<string | null>(null);

  const tenantId = user?.tenant_id;

  const {
    data: pendingData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['pending-subscriptions', tenantId],
    queryFn: () => apiSubscriptionsService.listPendingForTenant(tenantId!),
    enabled: !!tenantId,
    staleTime: 15 * 1000,
    refetchInterval: 30 * 1000,
  });

  const approveMutation = useMutation({
    mutationFn: (subscriptionId: string) =>
      apiSubscriptionsService.approveSubscription(subscriptionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['api-subscriptions'] });
      queryClient.invalidateQueries({ queryKey: ['my-api-subscriptions'] });
      toast.success('Subscription approved');
      setApprovingId(null);
    },
    onError: (err: Error) => {
      toast.error(`Failed to approve: ${err.message}`);
      setApprovingId(null);
    },
  });

  const handleApprove = (subscriptionId: string) => {
    setApprovingId(subscriptionId);
    approveMutation.mutate(subscriptionId);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-neutral-400 dark:text-neutral-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
        <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
        <p className="text-sm text-red-700 dark:text-red-300">
          Failed to load pending requests. You may not have admin access.
        </p>
      </div>
    );
  }

  const pendingItems = pendingData?.items || [];

  if (pendingItems.length === 0) {
    return (
      <div className="text-center py-12">
        <Inbox className="h-12 w-12 mx-auto text-neutral-300 dark:text-neutral-600 mb-3" />
        <h3 className="text-lg font-medium text-neutral-900 dark:text-white">No pending requests</h3>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          All subscription requests have been processed.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Clock className="h-5 w-5 text-amber-500" />
        <h3 className="text-lg font-medium text-neutral-900 dark:text-white">
          Pending Requests ({pendingItems.length})
        </h3>
      </div>

      {pendingItems.map((sub: APISubscriptionResponse) => (
        <div
          key={sub.id}
          className="flex items-center justify-between p-4 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg"
        >
          <div className="flex items-start gap-3 min-w-0">
            <div className="p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg flex-shrink-0">
              <Clock className="h-5 w-5 text-amber-500" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-neutral-900 dark:text-white truncate">
                  {sub.api_name}
                </span>
                {sub.api_version && (
                  <span className="text-xs px-1.5 py-0.5 bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 rounded">
                    v{sub.api_version}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                <span className="flex items-center gap-1">
                  <User className="h-3 w-3" />
                  {sub.subscriber_email}
                </span>
                <span className="flex items-center gap-1">
                  <FileCode2 className="h-3 w-3" />
                  {sub.application_name}
                </span>
                {sub.plan_name && (
                  <span className="px-1.5 py-0.5 bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 rounded">
                    {sub.plan_name}
                  </span>
                )}
              </div>
              <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
                Requested {new Date(sub.created_at).toLocaleDateString()}
              </p>
            </div>
          </div>

          <button
            onClick={() => handleApprove(sub.id)}
            disabled={approvingId === sub.id}
            className="flex-shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {approvingId === sub.id ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
            Approve
          </button>
        </div>
      ))}
    </div>
  );
}

export default ApprovalQueue;
