/**
 * Clients & Certificates Dashboard (CAB-870)
 *
 * List page with stats cards, filters, table, and pagination.
 * Follows APIs.tsx pattern with React Query hooks.
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Search, X, Eye, RotateCw, Trash2, ShieldCheck, AlertTriangle, Clock, Copy, Download, Check } from 'lucide-react';
import { useClients, useCreateClient, useRotateClient, useRevokeClient } from '../hooks/useClients';
import {
  computeClientStats,
  getCertificateHealth,
  getDaysRemaining,
  healthColors,
  healthLabels,
} from '../types/client';
import type { Client, ClientWithCertificate, CertificateHealthStatus } from '../types/client';

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

const PAGE_SIZE = 25;

// ---------------------------------------------------------------------------
// Stats Card
// ---------------------------------------------------------------------------

function StatsCard({ title, value, color, subtitle }: {
  title: string;
  value: number;
  color: 'blue' | 'green' | 'yellow' | 'red';
  subtitle?: string;
}) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    red: 'bg-red-50 text-red-700 border-red-200',
  };

  return (
    <div className={`rounded-lg border p-4 ${colorMap[color]}`}>
      <p className="text-sm font-medium opacity-80">{title}</p>
      <p className="text-3xl font-bold mt-1">{value}</p>
      {subtitle && <p className="text-xs opacity-60 mt-1">{subtitle}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Health Badge
// ---------------------------------------------------------------------------

function HealthBadge({ health }: { health: CertificateHealthStatus }) {
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${healthColors[health]}`}>
      {healthLabels[health]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Create Client Modal
// ---------------------------------------------------------------------------

function CreateClientModal({ onClose, onSubmit, isLoading }: {
  onClose: () => void;
  onSubmit: (name: string) => void;
  isLoading: boolean;
}) {
  const [name, setName] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Create New Client</h2>
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Client Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="my-api-consumer"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            autoFocus
          />
          <p className="text-xs text-gray-500 mt-1">CN will be auto-generated from the name</p>
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onSubmit(name)}
            disabled={!name.trim() || isLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? 'Creating...' : 'Create Client'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Download Certificate Modal (ONE TIME private key)
// ---------------------------------------------------------------------------

function DownloadCertificateModal({ client, onClose }: {
  client: ClientWithCertificate;
  onClose: () => void;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const copyToClipboard = useCallback(async (text: string, label: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  }, []);

  const downloadFile = useCallback((content: string, filename: string) => {
    const blob = new Blob([content], { type: 'application/x-pem-file' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        {/* Warning Banner */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <h3 className="font-semibold text-amber-900">Private Key - Save Now</h3>
            <p className="text-amber-700 text-sm mt-1">
              The private key is shown ONE TIME only. It is not stored and cannot be retrieved again.
              Download or copy it before closing this dialog.
            </p>
          </div>
        </div>

        <h2 className="text-lg font-semibold text-gray-900 mb-2">Client: {client.name}</h2>
        <p className="text-sm text-gray-500 mb-4">CN: {client.certificate_cn}</p>

        {client.grace_period_ends && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-600" />
            <span className="text-sm text-blue-700">
              Grace period ends: {new Date(client.grace_period_ends).toLocaleString()}
            </span>
          </div>
        )}

        {/* Certificate PEM */}
        <div className="mb-4">
          <div className="flex justify-between items-center mb-1">
            <label className="text-sm font-medium text-gray-700">Certificate (PEM)</label>
            <div className="flex gap-2">
              <button
                onClick={() => copyToClipboard(client.certificate_pem || '', 'cert')}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                {copied === 'cert' ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied === 'cert' ? 'Copied' : 'Copy'}
              </button>
              <button
                onClick={() => downloadFile(client.certificate_pem || '', `${client.name}-cert.pem`)}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                <Download className="w-3 h-3" /> Download
              </button>
            </div>
          </div>
          <pre className="bg-gray-50 rounded border border-gray-200 p-3 text-xs overflow-x-auto max-h-32">
            {client.certificate_pem}
          </pre>
        </div>

        {/* Private Key PEM */}
        <div className="mb-4">
          <div className="flex justify-between items-center mb-1">
            <label className="text-sm font-medium text-red-700">Private Key (PEM)</label>
            <div className="flex gap-2">
              <button
                onClick={() => copyToClipboard(client.private_key_pem, 'key')}
                className="text-xs text-red-600 hover:text-red-800 flex items-center gap-1"
              >
                {copied === 'key' ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied === 'key' ? 'Copied' : 'Copy'}
              </button>
              <button
                onClick={() => downloadFile(client.private_key_pem, `${client.name}-key.pem`)}
                className="text-xs text-red-600 hover:text-red-800 flex items-center gap-1"
              >
                <Download className="w-3 h-3" /> Download
              </button>
            </div>
          </div>
          <pre className="bg-red-50 rounded border border-red-200 p-3 text-xs overflow-x-auto max-h-32">
            {client.private_key_pem}
          </pre>
        </div>

        {/* Confirmation checkbox + close */}
        <div className="border-t pt-4 mt-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 mb-4 cursor-pointer">
            <input
              type="checkbox"
              checked={saved}
              onChange={e => setSaved(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            I have saved the private key securely
          </label>
          <button
            onClick={onClose}
            disabled={!saved}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Confirm Modal (reusable for rotate/revoke)
// ---------------------------------------------------------------------------

function ConfirmModal({ title, message, confirmLabel, danger, isLoading, onClose, onConfirm }: {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  isLoading: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-gray-900 mb-2">{title}</h2>
        <p className="text-gray-600 text-sm mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-4 py-2 rounded-lg text-white disabled:opacity-50 ${
              danger
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {isLoading ? 'Processing...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Clients Page
// ---------------------------------------------------------------------------

export function Clients() {
  const { data: clients = [], isLoading, error } = useClients();
  const createMutation = useCreateClient();
  const rotateMutation = useRotateClient();
  const revokeMutation = useRevokeClient();

  // Local state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [downloadedClient, setDownloadedClient] = useState<ClientWithCertificate | null>(null);
  const [rotateTarget, setRotateTarget] = useState<Client | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Client | null>(null);

  const debouncedSearch = useDebounce(searchQuery, 300);

  // Compute stats
  const stats = useMemo(() => computeClientStats(clients), [clients]);

  // Client-side filtering
  const filteredClients = useMemo(() => {
    let result = [...clients];

    if (debouncedSearch) {
      const search = debouncedSearch.toLowerCase();
      result = result.filter(c =>
        c.name.toLowerCase().includes(search) ||
        c.certificate_cn.toLowerCase().includes(search) ||
        (c.certificate_fingerprint || '').toLowerCase().includes(search)
      );
    }

    if (statusFilter) {
      if (statusFilter === 'grace_period') {
        result = result.filter(c => c.is_in_grace_period);
      } else {
        result = result.filter(c => c.status === statusFilter);
      }
    }

    return result;
  }, [clients, debouncedSearch, statusFilter]);

  // Pagination
  const paginatedClients = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredClients.slice(start, start + PAGE_SIZE);
  }, [filteredClients, currentPage]);

  const totalPages = Math.ceil(filteredClients.length / PAGE_SIZE);

  // Reset page on filter change
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearch, statusFilter]);

  // Handlers
  const handleCreate = useCallback(async (name: string) => {
    try {
      const result = await createMutation.mutateAsync({ name });
      setShowCreateModal(false);
      setDownloadedClient(result);
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to create client');
    }
  }, [createMutation]);

  const handleRotate = useCallback(async () => {
    if (!rotateTarget) return;
    try {
      const result = await rotateMutation.mutateAsync({
        clientId: rotateTarget.id,
        body: { reason: 'manual_rotation' },
      });
      setRotateTarget(null);
      setDownloadedClient(result);
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to rotate certificate');
    }
  }, [rotateTarget, rotateMutation]);

  const handleRevoke = useCallback(async () => {
    if (!revokeTarget) return;
    try {
      await revokeMutation.mutateAsync(revokeTarget.id);
      setRevokeTarget(null);
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to revoke client');
    }
  }, [revokeTarget, revokeMutation]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Clients & Certificates</h1>
          <p className="text-gray-500 mt-1">Manage mTLS client certificates</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 flex items-center gap-2"
        >
          <Plus className="w-5 h-5" />
          Create Client
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatsCard title="Total Clients" value={stats.total} color="blue" />
        <StatsCard title="Active" value={stats.active} color="green" />
        <StatsCard title="Expiring Soon" value={stats.expiring_soon} color="yellow" subtitle="< 30 days" />
        <StatsCard title="Critical" value={stats.critical + stats.expired} color="red" subtitle="< 7 days or expired" />
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Search</label>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search by name, CN, fingerprint..."
                className="w-full border border-gray-300 rounded-lg px-3 py-2 pl-10 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <Search className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                >
                  <X className="h-5 w-5" />
                </button>
              )}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All</option>
              <option value="active">Active</option>
              <option value="revoked">Revoked</option>
              <option value="expired">Expired</option>
              <option value="grace_period">Grace Period</option>
            </select>
          </div>

          <div className="text-sm text-gray-500 pb-2">
            {filteredClients.length} of {clients.length} clients
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error.message}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {clients.length === 0 ? (
          <div className="text-center py-16">
            <ShieldCheck className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No clients yet</h3>
            <p className="text-gray-500 mb-6">Create your first mTLS client to get started.</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
            >
              Create Client
            </button>
          </div>
        ) : filteredClients.length === 0 ? (
          <div className="text-center py-16">
            <Search className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No matching clients</h3>
            <p className="text-gray-500 mb-4">Try adjusting your search or filters.</p>
            <button
              onClick={() => { setSearchQuery(''); setStatusFilter(''); }}
              className="text-blue-600 hover:text-blue-800"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Health</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Expires</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rotations</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {paginatedClients.map(client => {
                    const health = getCertificateHealth(client);
                    const days = getDaysRemaining(client.certificate_not_after);

                    return (
                      <tr key={client.id} className="hover:bg-gray-50">
                        <td className="px-6 py-4">
                          <Link to={`/clients/${client.id}`} className="hover:text-blue-600">
                            <div className="text-sm font-medium text-gray-900">{client.name}</div>
                            <div className="text-xs text-gray-500">{client.certificate_cn}</div>
                          </Link>
                        </td>
                        <td className="px-6 py-4">
                          <HealthBadge health={health} />
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600">
                          {days !== null ? (
                            <span className={days < 7 ? 'text-red-600 font-semibold' : ''}>
                              {days}d
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-600">
                          {client.rotation_count}
                          {client.is_in_grace_period && (
                            <Clock className="inline w-3.5 h-3.5 text-blue-500 ml-1" />
                          )}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-500">
                          {new Date(client.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Link
                              to={`/clients/${client.id}`}
                              className="p-1.5 text-gray-400 hover:text-blue-600 rounded"
                              title="View details"
                            >
                              <Eye className="w-4 h-4" />
                            </Link>
                            <button
                              onClick={() => setRotateTarget(client)}
                              disabled={client.status !== 'active'}
                              className="p-1.5 text-gray-400 hover:text-blue-600 rounded disabled:opacity-30"
                              title="Rotate certificate"
                            >
                              <RotateCw className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => setRevokeTarget(client)}
                              disabled={client.status === 'revoked'}
                              className="p-1.5 text-gray-400 hover:text-red-600 rounded disabled:opacity-30"
                              title="Revoke client"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="bg-gray-50 px-6 py-3 flex items-center justify-between border-t border-gray-200">
                <div className="text-sm text-gray-600">
                  Showing {(currentPage - 1) * PAGE_SIZE + 1} to{' '}
                  {Math.min(currentPage * PAGE_SIZE, filteredClients.length)} of{' '}
                  {filteredClients.length} results
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCurrentPage(p => p - 1)}
                    disabled={currentPage === 1}
                    className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-gray-600">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(p => p + 1)}
                    disabled={currentPage === totalPages}
                    className="px-3 py-1 text-sm border border-gray-300 rounded hover:bg-gray-100 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Modals */}
      {showCreateModal && (
        <CreateClientModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreate}
          isLoading={createMutation.isPending}
        />
      )}

      {downloadedClient && (
        <DownloadCertificateModal
          client={downloadedClient}
          onClose={() => setDownloadedClient(null)}
        />
      )}

      {rotateTarget && (
        <ConfirmModal
          title="Rotate Certificate"
          message={`Rotate the certificate for "${rotateTarget.name}"? Both old and new certificates will be valid during the grace period.`}
          confirmLabel="Rotate"
          isLoading={rotateMutation.isPending}
          onClose={() => setRotateTarget(null)}
          onConfirm={handleRotate}
        />
      )}

      {revokeTarget && (
        <ConfirmModal
          title="Revoke Client"
          message={`Permanently revoke "${revokeTarget.name}"? This action cannot be undone. The client will no longer be able to authenticate.`}
          confirmLabel="Revoke"
          danger
          isLoading={revokeMutation.isPending}
          onClose={() => setRevokeTarget(null)}
          onConfirm={handleRevoke}
        />
      )}
    </div>
  );
}
