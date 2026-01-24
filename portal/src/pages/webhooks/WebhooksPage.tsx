/**
 * Webhooks Management Page (CAB-315)
 *
 * Allows tenant admins to configure webhook notifications for subscription events.
 */

import { useState } from 'react';
import {
  Webhook,
  Plus,
  Trash2,
  Edit2,
  Play,
  History,
  CheckCircle,
  XCircle,
  AlertCircle,
  RefreshCw,
  Loader2,
  ToggleLeft,
  ToggleRight,
  ExternalLink,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import {
  useWebhooks,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useWebhookDeliveries,
  useRetryDelivery,
} from '../../hooks/useWebhooks';
import type { TenantWebhook, WebhookCreate, WebhookDelivery, WebhookEventType } from '../../types';

// Available webhook events
const WEBHOOK_EVENTS: { value: WebhookEventType; label: string; description: string }[] = [
  { value: '*', label: 'All Events', description: 'Receive all subscription events' },
  { value: 'subscription.created', label: 'Created', description: 'When a new subscription is requested' },
  { value: 'subscription.approved', label: 'Approved', description: 'When a subscription is approved' },
  { value: 'subscription.revoked', label: 'Revoked', description: 'When a subscription is revoked' },
  { value: 'subscription.key_rotated', label: 'Key Rotated', description: 'When an API key is rotated' },
  { value: 'subscription.expired', label: 'Expired', description: 'When a subscription expires' },
];

const statusConfig: Record<string, { label: string; color: string; icon: typeof CheckCircle }> = {
  success: { label: 'Delivered', color: 'text-green-600 bg-green-100', icon: CheckCircle },
  failed: { label: 'Failed', color: 'text-red-600 bg-red-100', icon: XCircle },
  pending: { label: 'Pending', color: 'text-yellow-600 bg-yellow-100', icon: AlertCircle },
  retrying: { label: 'Retrying', color: 'text-blue-600 bg-blue-100', icon: RefreshCw },
};

export function WebhooksPage() {
  const { user } = useAuth();
  const [selectedTenantId, setSelectedTenantId] = useState<string>('');

  // Use user's tenant_id if available, otherwise allow admin to select
  const tenantId = user?.tenant_id || selectedTenantId;
  const isAdmin = user?.is_admin || user?.roles?.includes('cpi-admin');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingWebhook, setEditingWebhook] = useState<TenantWebhook | null>(null);
  const [viewingDeliveries, setViewingDeliveries] = useState<string | null>(null);
  const [testingWebhook, setTestingWebhook] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const { data: webhooksData, isLoading, isError, refetch } = useWebhooks(tenantId);
  const createMutation = useCreateWebhook();
  const updateMutation = useUpdateWebhook();
  const deleteMutation = useDeleteWebhook();
  const testMutation = useTestWebhook();

  const handleCreate = async (data: WebhookCreate) => {
    try {
      await createMutation.mutateAsync({ tenantId, data });
      setShowCreateModal(false);
    } catch (error) {
      console.error('Failed to create webhook:', error);
    }
  };

  const handleUpdate = async (webhookId: string, data: Partial<WebhookCreate>) => {
    try {
      await updateMutation.mutateAsync({ tenantId, webhookId, data });
      setEditingWebhook(null);
    } catch (error) {
      console.error('Failed to update webhook:', error);
    }
  };

  const handleDelete = async (webhookId: string) => {
    if (!confirm('Are you sure you want to delete this webhook? This action cannot be undone.')) {
      return;
    }
    try {
      await deleteMutation.mutateAsync({ tenantId, webhookId });
    } catch (error) {
      console.error('Failed to delete webhook:', error);
    }
  };

  const handleToggleEnabled = async (webhook: TenantWebhook) => {
    try {
      await updateMutation.mutateAsync({
        tenantId,
        webhookId: webhook.id,
        data: { enabled: !webhook.enabled },
      });
    } catch (error) {
      console.error('Failed to toggle webhook:', error);
    }
  };

  const handleTest = async (webhookId: string) => {
    setTestingWebhook(webhookId);
    setTestResult(null);
    try {
      const result = await testMutation.mutateAsync({ tenantId, webhookId });
      setTestResult({
        success: result.success,
        message: result.success
          ? `Test delivered successfully (${result.status_code})`
          : result.error || 'Test failed',
      });
    } catch (error) {
      setTestResult({
        success: false,
        message: error instanceof Error ? error.message : 'Test failed',
      });
    } finally {
      setTestingWebhook(null);
    }
  };

  // If no tenant_id and user is admin, show tenant selector
  if (!tenantId && isAdmin) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="flex items-center gap-3 mb-4">
            <Webhook className="h-8 w-8 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900">Webhook Management</h2>
          </div>
          <p className="text-gray-600 mb-4">
            As a platform administrator, enter the tenant ID to manage webhooks for:
          </p>
          <div className="flex gap-3">
            <input
              type="text"
              value={selectedTenantId}
              onChange={(e) => setSelectedTenantId(e.target.value)}
              placeholder="Enter tenant ID (e.g., acme, team-alpha)"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
            <button
              onClick={() => {}}
              disabled={!selectedTenantId}
              className="px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium disabled:opacity-50"
            >
              Load Webhooks
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!tenantId) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
          <AlertCircle className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-yellow-800">Tenant Required</h3>
          <p className="text-yellow-700 mt-2">
            You need to be associated with a tenant to manage webhooks.
            Contact your administrator to be assigned to a tenant.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
            <Webhook className="h-7 w-7 text-primary-600" />
            Webhook Notifications
          </h1>
          <p className="text-gray-500 mt-1">
            Configure webhooks to receive notifications for subscription events
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium"
        >
          <Plus className="h-4 w-4" />
          Add Webhook
        </button>
      </div>

      {/* Test Result Toast */}
      {testResult && (
        <div
          className={`fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg ${
            testResult.success ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}
        >
          <div className="flex items-center gap-2">
            {testResult.success ? (
              <CheckCircle className="h-5 w-5" />
            ) : (
              <XCircle className="h-5 w-5" />
            )}
            <span className="font-medium">{testResult.message}</span>
            <button
              onClick={() => setTestResult(null)}
              className="ml-4 text-gray-500 hover:text-gray-700"
            >
              &times;
            </button>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
        </div>
      )}

      {/* Error State */}
      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <XCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-red-800">Failed to load webhooks</h3>
          <button
            onClick={() => refetch()}
            className="mt-4 text-red-600 hover:text-red-700 font-medium"
          >
            Try again
          </button>
        </div>
      )}

      {/* Webhooks List */}
      {webhooksData && (
        <div className="space-y-4">
          {webhooksData.items.length === 0 ? (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-12 text-center">
              <Webhook className="h-16 w-16 text-gray-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-700">No webhooks configured</h3>
              <p className="text-gray-500 mt-2">
                Create your first webhook to start receiving subscription event notifications.
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium"
              >
                <Plus className="h-4 w-4" />
                Add Webhook
              </button>
            </div>
          ) : (
            webhooksData.items.map((webhook) => (
              <WebhookCard
                key={webhook.id}
                webhook={webhook}
                onEdit={() => setEditingWebhook(webhook)}
                onDelete={() => handleDelete(webhook.id)}
                onToggle={() => handleToggleEnabled(webhook)}
                onTest={() => handleTest(webhook.id)}
                onViewDeliveries={() => setViewingDeliveries(webhook.id)}
                isToggling={updateMutation.isPending}
                isTesting={testingWebhook === webhook.id}
              />
            ))
          )}
        </div>
      )}

      {/* Create/Edit Modal */}
      {(showCreateModal || editingWebhook) && (
        <WebhookModal
          webhook={editingWebhook}
          onClose={() => {
            setShowCreateModal(false);
            setEditingWebhook(null);
          }}
          onSave={(data) =>
            editingWebhook
              ? handleUpdate(editingWebhook.id, data)
              : handleCreate(data as WebhookCreate)
          }
          isLoading={createMutation.isPending || updateMutation.isPending}
        />
      )}

      {/* Deliveries Modal */}
      {viewingDeliveries && (
        <DeliveriesModal
          tenantId={tenantId}
          webhookId={viewingDeliveries}
          onClose={() => setViewingDeliveries(null)}
        />
      )}
    </div>
  );
}

// ============ Webhook Card Component ============

interface WebhookCardProps {
  webhook: TenantWebhook;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
  onTest: () => void;
  onViewDeliveries: () => void;
  isToggling: boolean;
  isTesting: boolean;
}

function WebhookCard({
  webhook,
  onEdit,
  onDelete,
  onToggle,
  onTest,
  onViewDeliveries,
  isToggling,
  isTesting,
}: WebhookCardProps) {
  return (
    <div
      className={`bg-white border rounded-lg p-6 ${
        webhook.enabled ? 'border-gray-200' : 'border-gray-200 opacity-60'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-gray-900">{webhook.name}</h3>
            <span
              className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                webhook.enabled
                  ? 'bg-green-100 text-green-700'
                  : 'bg-gray-100 text-gray-600'
              }`}
            >
              {webhook.enabled ? 'Active' : 'Disabled'}
            </span>
            {webhook.has_secret && (
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-700">
                Signed
              </span>
            )}
          </div>
          <div className="mt-2 flex items-center gap-2 text-sm text-gray-500">
            <ExternalLink className="h-4 w-4" />
            <code className="bg-gray-100 px-2 py-0.5 rounded text-xs break-all">
              {webhook.url}
            </code>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {webhook.events.map((event) => (
              <span
                key={event}
                className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-md"
              >
                {event === '*' ? 'All Events' : event}
              </span>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onToggle}
            disabled={isToggling}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            title={webhook.enabled ? 'Disable webhook' : 'Enable webhook'}
          >
            {webhook.enabled ? (
              <ToggleRight className="h-5 w-5 text-green-600" />
            ) : (
              <ToggleLeft className="h-5 w-5" />
            )}
          </button>
          <button
            onClick={onTest}
            disabled={isTesting || !webhook.enabled}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            title="Send test event"
          >
            {isTesting ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Play className="h-5 w-5" />
            )}
          </button>
          <button
            onClick={onViewDeliveries}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            title="View delivery history"
          >
            <History className="h-5 w-5" />
          </button>
          <button
            onClick={onEdit}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            title="Edit webhook"
          >
            <Edit2 className="h-5 w-5" />
          </button>
          <button
            onClick={onDelete}
            className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
            title="Delete webhook"
          >
            <Trash2 className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ============ Webhook Modal Component ============

interface WebhookModalProps {
  webhook: TenantWebhook | null;
  onClose: () => void;
  onSave: (data: WebhookCreate | Partial<WebhookCreate>) => void;
  isLoading: boolean;
}

function WebhookModal({ webhook, onClose, onSave, isLoading }: WebhookModalProps) {
  const [name, setName] = useState(webhook?.name || '');
  const [url, setUrl] = useState(webhook?.url || '');
  const [secret, setSecret] = useState('');
  const [events, setEvents] = useState<WebhookEventType[]>(webhook?.events || ['*']);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Name is required');
      return;
    }
    if (!url.trim()) {
      setError('URL is required');
      return;
    }
    if (events.length === 0) {
      setError('At least one event must be selected');
      return;
    }

    const data: WebhookCreate | Partial<WebhookCreate> = {
      name: name.trim(),
      url: url.trim(),
      events,
    };

    if (secret.trim()) {
      data.secret = secret.trim();
    }

    onSave(data);
  };

  const toggleEvent = (event: WebhookEventType) => {
    if (event === '*') {
      setEvents(['*']);
    } else {
      const newEvents = events.filter((e) => e !== '*');
      if (newEvents.includes(event)) {
        setEvents(newEvents.filter((e) => e !== event));
      } else {
        setEvents([...newEvents, event]);
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full">
          <div className="p-6 border-b border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900">
              {webhook ? 'Edit Webhook' : 'Create Webhook'}
            </h2>
          </div>

          <form onSubmit={handleSubmit} className="p-6 space-y-6">
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="webhook-name" className="block text-sm font-medium text-gray-700 mb-2">
                Name
              </label>
              <input
                id="webhook-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., Slack Notifications"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <div>
              <label htmlFor="webhook-url" className="block text-sm font-medium text-gray-700 mb-2">
                Webhook URL
              </label>
              <input
                id="webhook-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://hooks.example.com/webhook"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <div>
              <label htmlFor="webhook-secret" className="block text-sm font-medium text-gray-700 mb-2">
                Secret (optional)
                <span className="text-gray-400 font-normal ml-2">
                  For HMAC signature verification
                </span>
              </label>
              <input
                id="webhook-secret"
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder={webhook?.has_secret ? '••••••••' : 'Enter a secret (min 16 characters)'}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>

            <div>
              <span className="block text-sm font-medium text-gray-700 mb-3">
                Events
              </span>
              <div className="space-y-2" role="group" aria-label="Webhook events">
                {WEBHOOK_EVENTS.map((eventType) => (
                  <label
                    key={eventType.value}
                    className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50"
                  >
                    <input
                      type="checkbox"
                      checked={
                        events.includes(eventType.value) ||
                        (eventType.value !== '*' && events.includes('*'))
                      }
                      onChange={() => toggleEvent(eventType.value)}
                      disabled={eventType.value !== '*' && events.includes('*')}
                      className="mt-0.5 h-4 w-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                      aria-label={eventType.label}
                    />
                    <div>
                      <div className="font-medium text-gray-900">{eventType.label}</div>
                      <div className="text-sm text-gray-500">{eventType.description}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg transition-colors font-medium"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-6 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors font-medium disabled:opacity-50"
              >
                {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                {webhook ? 'Save Changes' : 'Create Webhook'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

// ============ Deliveries Modal Component ============

interface DeliveriesModalProps {
  tenantId: string;
  webhookId: string;
  onClose: () => void;
}

function DeliveriesModal({ tenantId, webhookId, onClose }: DeliveriesModalProps) {
  const { data, isLoading, refetch } = useWebhookDeliveries(tenantId, webhookId);
  const retryMutation = useRetryDelivery();

  const handleRetry = async (deliveryId: string) => {
    try {
      await retryMutation.mutateAsync({ tenantId, webhookId, deliveryId });
    } catch (error) {
      console.error('Failed to retry delivery:', error);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[80vh] overflow-hidden">
          <div className="p-6 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-xl font-semibold text-gray-900">Delivery History</h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => refetch()}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
                aria-label="Refresh"
              >
                <RefreshCw className="h-5 w-5" aria-hidden="true" />
              </button>
              <button
                onClick={onClose}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
                aria-label="Close"
              >
                &times;
              </button>
            </div>
          </div>

          <div className="p-6 overflow-y-auto max-h-[60vh]">
            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
              </div>
            ) : data?.items.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                No deliveries yet
              </div>
            ) : (
              <div className="space-y-4">
                {data?.items.map((delivery) => (
                  <DeliveryRow
                    key={delivery.id}
                    delivery={delivery}
                    onRetry={() => handleRetry(delivery.id)}
                    isRetrying={retryMutation.isPending}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Delivery Row Component ============

interface DeliveryRowProps {
  delivery: WebhookDelivery;
  onRetry: () => void;
  isRetrying: boolean;
}

function DeliveryRow({ delivery, onRetry, isRetrying }: DeliveryRowProps) {
  const [expanded, setExpanded] = useState(false);
  const status = statusConfig[delivery.status] || statusConfig.pending;
  const StatusIcon = status.icon;

  return (
    <div className="border border-gray-200 rounded-lg">
      <div
        className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => e.key === 'Enter' && setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-4">
          <span className={`p-1.5 rounded-full ${status.color}`}>
            <StatusIcon className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <div className="font-medium text-gray-900">{delivery.event_type}</div>
            <div className="text-sm text-gray-500">
              {new Date(delivery.created_at).toLocaleString()}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {delivery.response_status_code && (
            <span className="text-sm text-gray-500">
              HTTP {delivery.response_status_code}
            </span>
          )}
          <span className="text-sm text-gray-500">
            {delivery.attempt_count}/{delivery.max_attempts} attempts
          </span>
          {delivery.status === 'failed' && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRetry();
              }}
              disabled={isRetrying}
              className="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 disabled:opacity-50"
            >
              Retry
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-200 p-4 bg-gray-50 space-y-4">
          {delivery.error_message && (
            <div>
              <span className="text-xs font-medium text-gray-500 uppercase">Error</span>
              <div className="mt-1 text-sm text-red-600">{delivery.error_message}</div>
            </div>
          )}
          <div>
            <span className="text-xs font-medium text-gray-500 uppercase">Payload</span>
            <pre className="mt-1 text-xs bg-gray-900 text-gray-100 p-3 rounded overflow-x-auto">
              {JSON.stringify(delivery.payload, null, 2)}
            </pre>
          </div>
          {delivery.response_body && (
            <div>
              <span className="text-xs font-medium text-gray-500 uppercase">Response</span>
              <pre className="mt-1 text-xs bg-gray-900 text-gray-100 p-3 rounded overflow-x-auto max-h-40">
                {delivery.response_body}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default WebhooksPage;
