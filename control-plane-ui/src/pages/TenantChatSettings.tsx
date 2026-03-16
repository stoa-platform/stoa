/**
 * TenantChatSettings — per-tenant chat feature toggles and daily budget.
 * Accessible by cpi-admin and tenant-admin (mirrors API authorization).
 * CAB-1852
 */
import { useState, useEffect } from 'react';
import { MessageSquare, Save, AlertTriangle, BarChart2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import type { TenantChatSettings as Settings } from '../services/api';

const ACTIVE_TENANT_KEY = 'stoa-active-tenant';

export function TenantChatSettings() {
  const { user } = useAuth();
  const tenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || '';

  const [settings, setSettings] = useState<Settings>({
    chat_console_enabled: true,
    chat_portal_enabled: true,
    chat_daily_budget: 100_000,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!tenantId) return;
    setLoading(true);
    apiService
      .getChatSettings(tenantId)
      .then((data) => setSettings(data))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        setError(`Failed to load settings: ${msg}`);
      })
      .finally(() => setLoading(false));
  }, [tenantId]);

  const handleSave = async () => {
    if (!tenantId) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await apiService.updateChatSettings(tenantId, settings);
      setSettings(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Failed to save settings: ${msg}`);
    } finally {
      setSaving(false);
    }
  };

  if (!tenantId) {
    return (
      <div className="p-6 text-sm text-neutral-500 dark:text-neutral-400">No tenant selected.</div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-neutral-900 dark:text-white flex items-center gap-2">
          <MessageSquare className="h-6 w-6 text-blue-500" />
          Chat Agent Settings
        </h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1">
          Configure the AI Chat Agent for tenant{' '}
          <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
            {tenantId}
          </span>
        </p>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 rounded-lg flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {saved && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 px-4 py-3 rounded-lg text-sm text-green-700 dark:text-green-400">
          Settings saved successfully.
        </div>
      )}

      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow divide-y divide-neutral-100 dark:divide-neutral-700">
        {/* Console toggle */}
        <div className="flex items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm font-medium text-neutral-900 dark:text-white">
              Enable Chat in Console
            </p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              Allow admin and devops users to use the AI Chat Agent in the Control Plane Console.
            </p>
          </div>
          <button
            role="switch"
            aria-checked={settings.chat_console_enabled}
            disabled={loading}
            onClick={() =>
              setSettings((s) => ({ ...s, chat_console_enabled: !s.chat_console_enabled }))
            }
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 ${
              settings.chat_console_enabled ? 'bg-blue-600' : 'bg-neutral-300 dark:bg-neutral-600'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                settings.chat_console_enabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>

        {/* Portal toggle */}
        <div className="flex items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm font-medium text-neutral-900 dark:text-white">
              Enable Chat in Developer Portal
            </p>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
              Allow tenant developers to use the AI Chat Agent in the Developer Portal.
            </p>
          </div>
          <button
            role="switch"
            aria-checked={settings.chat_portal_enabled}
            disabled={loading}
            onClick={() =>
              setSettings((s) => ({ ...s, chat_portal_enabled: !s.chat_portal_enabled }))
            }
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 ${
              settings.chat_portal_enabled ? 'bg-blue-600' : 'bg-neutral-300 dark:bg-neutral-600'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                settings.chat_portal_enabled ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>
        </div>

        {/* Daily budget */}
        <div className="px-6 py-4">
          <label
            htmlFor="chat-daily-budget"
            className="block text-sm font-medium text-neutral-900 dark:text-white"
          >
            Daily Token Budget
          </label>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5 mb-3">
            Maximum tokens the chat agent may consume per day across all users in this tenant.
          </p>
          <div className="flex items-center gap-3">
            <input
              id="chat-daily-budget"
              type="number"
              min={0}
              step={10_000}
              disabled={loading}
              value={settings.chat_daily_budget}
              onChange={(e) =>
                setSettings((s) => ({
                  ...s,
                  chat_daily_budget: Math.max(0, parseInt(e.target.value, 10) || 0),
                }))
              }
              className="w-40 rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
            <span className="text-sm text-neutral-500 dark:text-neutral-400">tokens / day</span>
          </div>
        </div>
      </div>

      {/* Usage link */}
      <div className="flex justify-end">
        <Link
          to="/chat-usage"
          className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          <BarChart2 className="h-4 w-4" />
          View token usage
        </Link>
      </div>

      {/* Save button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={loading || saving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          <Save className="h-4 w-4" />
          {saving ? 'Saving…' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
