// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Service Accounts Management Page (CAB-296)
 *
 * Allows users to create OAuth2 service accounts for MCP tool access.
 * Each service account inherits the user's RBAC roles.
 */

import { useState } from 'react';
import {
  Key,
  Plus,
  Trash2,
  RefreshCw,
  Copy,
  Check,
  AlertTriangle,
  Shield,
  Eye,
  EyeOff,
  Download,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../services/api';

interface ServiceAccount {
  id: string;
  client_id: string;
  name: string;
  description?: string;
  enabled: boolean;
}

interface NewServiceAccount {
  id: string;
  client_id: string;
  client_secret: string;
  name: string;
}

export function ServiceAccountsPage() {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newAccount, setNewAccount] = useState<NewServiceAccount | null>(null);
  const [regeneratedSecret, setRegeneratedSecret] = useState<{ id: string; secret: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Fetch service accounts
  const { data: accounts, isLoading, error } = useQuery<ServiceAccount[]>({
    queryKey: ['service-accounts'],
    queryFn: async () => {
      const res = await apiClient.get('/v1/service-accounts');
      return res.data;
    },
  });

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (data: { name: string; description?: string }) => {
      const res = await apiClient.post('/v1/service-accounts', data);
      return res.data as NewServiceAccount;
    },
    onSuccess: (data) => {
      setNewAccount(data);
      setShowCreateModal(false);
      queryClient.invalidateQueries({ queryKey: ['service-accounts'] });
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/v1/service-accounts/${id}`);
    },
    onSuccess: () => {
      setDeletingId(null);
      queryClient.invalidateQueries({ queryKey: ['service-accounts'] });
    },
  });

  // Regenerate secret mutation
  const regenerateMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiClient.post(`/v1/service-accounts/${id}/regenerate-secret`);
      return res.data;
    },
    onSuccess: (data) => {
      setRegeneratedSecret({ id: data.id, secret: data.client_secret });
    },
  });

  return (
    <div className="max-w-4xl mx-auto py-8 px-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
            <Shield className="h-7 w-7 text-primary-600" />
            Service Accounts
          </h1>
          <p className="text-gray-600 mt-1">
            Create OAuth2 credentials for MCP tool access (Claude Desktop, Cursor, etc.)
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Create Service Account
        </button>
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <h3 className="text-sm font-medium text-blue-800 mb-2">How it works</h3>
        <ul className="text-sm text-blue-700 space-y-1 list-disc list-inside">
          <li>Each service account gets a unique client_id and client_secret</li>
          <li>The account inherits your RBAC roles and tenant access</li>
          <li>Use the credentials in your MCP client configuration</li>
          <li>You can create multiple accounts (e.g., one per device)</li>
        </ul>
      </div>

      {/* Loading/Error States */}
      {isLoading && (
        <div className="text-center py-12">
          <RefreshCw className="h-8 w-8 text-gray-400 animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading service accounts...</p>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-700">Failed to load service accounts</p>
        </div>
      )}

      {/* Service Accounts List */}
      {accounts && accounts.length === 0 && (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <Key className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 mb-4">No service accounts yet</p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <Plus className="h-4 w-4" />
            Create your first service account
          </button>
        </div>
      )}

      {accounts && accounts.length > 0 && (
        <div className="space-y-4">
          {accounts.map((account) => (
            <ServiceAccountCard
              key={account.id}
              account={account}
              onDelete={() => setDeletingId(account.id)}
              onRegenerate={() => regenerateMutation.mutate(account.id)}
              isRegenerating={regenerateMutation.isPending}
              regeneratedSecret={regeneratedSecret?.id === account.id ? regeneratedSecret.secret : null}
              onClearSecret={() => setRegeneratedSecret(null)}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <CreateServiceAccountModal
          onClose={() => setShowCreateModal(false)}
          onCreate={(data) => createMutation.mutate(data)}
          isCreating={createMutation.isPending}
          error={createMutation.error?.message}
        />
      )}

      {/* New Account Created Modal (shows secret) */}
      {newAccount && (
        <NewAccountCreatedModal
          account={newAccount}
          onClose={() => setNewAccount(null)}
        />
      )}

      {/* Delete Confirmation */}
      {deletingId && (
        <DeleteConfirmModal
          onConfirm={() => deleteMutation.mutate(deletingId)}
          onCancel={() => setDeletingId(null)}
          isDeleting={deleteMutation.isPending}
        />
      )}
    </div>
  );
}

// Service Account Card Component
function ServiceAccountCard({
  account,
  onDelete,
  onRegenerate,
  isRegenerating,
  regeneratedSecret,
  onClearSecret,
}: {
  account: ServiceAccount;
  onDelete: () => void;
  onRegenerate: () => void;
  isRegenerating: boolean;
  regeneratedSecret: string | null;
  onClearSecret: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  const handleCopyClientId = async () => {
    await navigator.clipboard.writeText(account.client_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopySecret = async () => {
    if (regeneratedSecret) {
      await navigator.clipboard.writeText(regeneratedSecret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className="p-2 bg-primary-50 rounded-lg">
            <Key className="h-5 w-5 text-primary-600" />
          </div>
          <div>
            <h3 className="font-medium text-gray-900">{account.name}</h3>
            <p className="text-sm text-gray-500 mt-0.5">{account.description || 'No description'}</p>
            <div className="flex items-center gap-2 mt-2">
              <code className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">
                {account.client_id}
              </code>
              <button
                onClick={handleCopyClientId}
                className="text-gray-400 hover:text-gray-600"
                title="Copy client_id"
              >
                {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onRegenerate}
            disabled={isRegenerating}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm text-amber-600 hover:bg-amber-50 rounded-lg transition-colors disabled:opacity-50"
            title="Regenerate secret"
          >
            <RefreshCw className={`h-4 w-4 ${isRegenerating ? 'animate-spin' : ''}`} />
            Regenerate
          </button>
          <button
            onClick={onDelete}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 rounded-lg transition-colors"
            title="Delete service account"
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </button>
        </div>
      </div>

      {/* Show regenerated secret */}
      {regeneratedSecret && (
        <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-800">New secret generated!</p>
              <p className="text-xs text-amber-700 mb-2">Copy it now - it won't be shown again.</p>
              <div className="flex items-center gap-2">
                <code className="text-xs bg-amber-100 px-2 py-1 rounded font-mono flex-1 truncate">
                  {showSecret ? regeneratedSecret : '••••••••••••••••••••••••'}
                </code>
                <button
                  onClick={() => setShowSecret(!showSecret)}
                  className="text-amber-600 hover:text-amber-700"
                >
                  {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
                <button
                  onClick={handleCopySecret}
                  className="text-amber-600 hover:text-amber-700"
                >
                  <Copy className="h-4 w-4" />
                </button>
              </div>
              <button
                onClick={onClearSecret}
                className="mt-2 text-xs text-amber-600 hover:underline"
              >
                I've saved it, hide this
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Create Modal
function CreateServiceAccountModal({
  onClose,
  onCreate,
  isCreating,
  error,
}: {
  onClose: () => void;
  onCreate: (data: { name: string; description?: string }) => void;
  isCreating: boolean;
  error?: string;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({ name, description: description || undefined });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />
      <div className="relative bg-white rounded-xl shadow-xl max-w-md w-full p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Create Service Account</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="sa-name" className="block text-sm font-medium text-gray-700 mb-1">
              Name <span className="text-red-500" aria-hidden="true">*</span>
              <span className="sr-only">(required)</span>
            </label>
            <input
              id="sa-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., claude-desktop, cursor-ide"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              required
            />
          </div>

          <div>
            <label htmlFor="sa-description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              id="sa-description"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
          </div>

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 hover:text-gray-900"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isCreating || !name.trim()}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {isCreating ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" />
                  Create
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// New Account Created Modal (shows secret once)
function NewAccountCreatedModal({
  account,
  onClose,
}: {
  account: NewServiceAccount;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  const handleCopyAll = async () => {
    const text = `Client ID: ${account.client_id}\nClient Secret: ${account.client_secret}`;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadConfig = () => {
    const config = {
      mcpServers: {
        [`stoa-${account.name}`]: {
          url: 'https://mcp.gostoa.dev/mcp/sse',
          transport: 'sse',
          headers: {
            Authorization: `Basic ${btoa(`${account.client_id}:${account.client_secret}`)}`,
          },
          metadata: {
            icon: 'https://raw.githubusercontent.com/stoa-platform/stoa/main/docs/assets/logo.svg',
            title: `STOA - ${account.name}`,
          },
        },
      },
    };

    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'claude_desktop_config.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />
      <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-green-100 rounded-full">
            <Check className="h-6 w-6 text-green-600" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Service Account Created!</h2>
            <p className="text-sm text-gray-500">{account.name}</p>
          </div>
        </div>

        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0" aria-hidden="true" />
            <p className="text-sm text-amber-800">
              <strong>Important:</strong> Save these credentials now. The client secret will not be shown again.
            </p>
          </div>
        </div>

        <div className="space-y-3 mb-6">
          <div>
            <span id="sa-client-id-label" className="block text-xs font-medium text-gray-500 mb-1">Client ID</span>
            <code className="block w-full p-2 bg-gray-100 rounded text-sm font-mono break-all" aria-labelledby="sa-client-id-label">
              {account.client_id}
            </code>
          </div>
          <div>
            <span id="sa-client-secret-label" className="block text-xs font-medium text-gray-500 mb-1">Client Secret</span>
            <div className="flex items-center gap-2">
              <code className="flex-1 p-2 bg-gray-100 rounded text-sm font-mono break-all" aria-labelledby="sa-client-secret-label">
                {showSecret ? account.client_secret : '••••••••••••••••••••••••••••••••'}
              </code>
              <button
                onClick={() => setShowSecret(!showSecret)}
                className="p-2 text-gray-500 hover:text-gray-700"
                aria-label={showSecret ? 'Hide client secret' : 'Show client secret'}
              >
                {showSecret ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleCopyAll}
            className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
            {copied ? 'Copied!' : 'Copy Credentials'}
          </button>
          <button
            onClick={handleDownloadConfig}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <Download className="h-4 w-4" />
            Download MCP Config
          </button>
        </div>

        <div className="mt-6 pt-4 border-t border-gray-200">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 text-gray-700 hover:text-gray-900 font-medium"
          >
            I've saved my credentials
          </button>
        </div>
      </div>
    </div>
  );
}

// Delete Confirmation Modal
function DeleteConfirmModal({
  onConfirm,
  onCancel,
  isDeleting,
}: {
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-black/50"
        onClick={onCancel}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />
      <div className="relative bg-white rounded-xl shadow-xl max-w-sm w-full p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-red-100 rounded-full">
            <AlertTriangle className="h-6 w-6 text-red-600" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900">Delete Service Account?</h2>
        </div>

        <p className="text-gray-600 mb-6">
          This will immediately revoke access for any MCP clients using this account.
          This action cannot be undone.
        </p>

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-gray-700 hover:text-gray-900"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="inline-flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
          >
            {isDeleting ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 className="h-4 w-4" />
                Delete
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ServiceAccountsPage;
