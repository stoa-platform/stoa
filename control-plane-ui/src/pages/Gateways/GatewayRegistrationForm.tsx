import { useState } from 'react';
import { apiService } from '../../services/api';
import type { GatewayType } from '../../types';

interface GatewayRegistrationFormProps {
  onCreated: () => void;
  onCancel: () => void;
}

const gatewayTypes: { value: GatewayType; label: string }[] = [
  { value: 'webmethods', label: 'webMethods' },
  { value: 'kong', label: 'Kong' },
  { value: 'apigee', label: 'Apigee' },
  { value: 'aws_apigateway', label: 'AWS API Gateway' },
  { value: 'stoa', label: 'STOA' },
];

const environments = ['dev', 'staging', 'production'];

export function GatewayRegistrationForm({ onCreated, onCancel }: GatewayRegistrationFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: '',
    display_name: '',
    gateway_type: 'webmethods' as GatewayType,
    environment: 'dev',
    base_url: '',
    tenant_id: '',
    capabilities: '',
    tags: '',
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const payload = {
        name: form.name,
        display_name: form.display_name,
        gateway_type: form.gateway_type,
        environment: form.environment,
        base_url: form.base_url,
        tenant_id: form.tenant_id || undefined,
        capabilities: form.capabilities
          ? form.capabilities
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
        tags: form.tags
          ? form.tags
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
        auth_config: {},
      };

      await apiService.createGatewayInstance(payload);
      onCreated();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to register gateway');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-neutral-900 dark:text-white mb-4">
        Register Gateway Instance
      </h2>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="name"
              value={form.name}
              onChange={handleChange}
              required
              placeholder="webmethods-prod"
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
              Unique identifier (lowercase, hyphens)
            </p>
          </div>

          {/* Display Name */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Display Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="display_name"
              value={form.display_name}
              onChange={handleChange}
              required
              placeholder="webMethods Production"
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Gateway Type */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Gateway Type <span className="text-red-500">*</span>
            </label>
            <select
              name="gateway_type"
              value={form.gateway_type}
              onChange={handleChange}
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {gatewayTypes.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          {/* Environment */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Environment <span className="text-red-500">*</span>
            </label>
            <select
              name="environment"
              value={form.environment}
              onChange={handleChange}
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {environments.map((env) => (
                <option key={env} value={env}>
                  {env}
                </option>
              ))}
            </select>
          </div>

          {/* Base URL */}
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Admin API URL <span className="text-red-500">*</span>
            </label>
            <input
              type="url"
              name="base_url"
              value={form.base_url}
              onChange={handleChange}
              required
              placeholder="https://gateway-admin.example.com"
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Tenant (optional) */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Tenant ID
            </label>
            <input
              type="text"
              name="tenant_id"
              value={form.tenant_id}
              onChange={handleChange}
              placeholder="Leave empty for platform-wide"
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Capabilities */}
          <div>
            <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
              Capabilities
            </label>
            <input
              type="text"
              name="capabilities"
              value={form.capabilities}
              onChange={handleChange}
              placeholder="rest, oidc, rate_limiting"
              className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
              Comma-separated list
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors text-sm font-medium"
          >
            {submitting ? 'Registering...' : 'Register Gateway'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="border border-neutral-300 dark:border-neutral-600 text-neutral-700 dark:text-neutral-300 px-4 py-2 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700 transition-colors text-sm"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
