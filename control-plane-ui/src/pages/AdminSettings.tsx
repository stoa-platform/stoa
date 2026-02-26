/**
 * Admin Platform Settings Page (CAB-1454)
 *
 * View and edit platform configuration grouped by category.
 * cpi-admin only.
 */
import { useState, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { usePlatformSettings, useUpdatePlatformSetting } from '../hooks/usePlatformSettings';
import type { SettingCategory, PlatformSetting } from '../types';
import { AlertTriangle, Settings, Save, Check, X } from 'lucide-react';

const categoryLabels: Record<SettingCategory, string> = {
  general: 'General',
  security: 'Security',
  gateway: 'Gateway',
  notifications: 'Notifications',
};

const categoryColors: Record<SettingCategory, { bg: string; text: string }> = {
  general: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-800 dark:text-blue-400' },
  security: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-800 dark:text-red-400' },
  gateway: {
    bg: 'bg-purple-100 dark:bg-purple-900/30',
    text: 'text-purple-800 dark:text-purple-400',
  },
  notifications: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-800 dark:text-amber-400',
  },
};

function formatDate(date: string | undefined | null): string {
  if (!date) return '\u2014';
  return new Date(date).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function SettingRow({
  setting,
  onSave,
  isSaving,
}: {
  setting: PlatformSetting;
  onSave: (key: string, value: string) => void;
  isSaving: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(setting.value);
  const [saved, setSaved] = useState(false);

  const handleSave = useCallback(() => {
    onSave(setting.key, editValue);
    setEditing(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }, [setting.key, editValue, onSave]);

  const handleCancel = useCallback(() => {
    setEditValue(setting.value);
    setEditing(false);
  }, [setting.value]);

  const colors = categoryColors[setting.category] || categoryColors.general;

  return (
    <tr className="hover:bg-neutral-50 dark:hover:bg-neutral-700/50 transition-colors">
      <td className="px-4 py-3">
        <div>
          <p className="text-sm font-medium text-neutral-900 dark:text-white font-mono">
            {setting.key}
          </p>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-0.5">
            {setting.description}
          </p>
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}
        >
          {categoryLabels[setting.category]}
        </span>
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              className="w-full px-2 py-1 rounded border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono"
              autoFocus
            />
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="p-1 rounded hover:bg-green-100 dark:hover:bg-green-900/30 text-green-600 dark:text-green-400"
            >
              <Save className="h-4 w-4" />
            </button>
            <button
              onClick={handleCancel}
              className="p-1 rounded hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-500"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-sm text-neutral-900 dark:text-white font-mono">
              {setting.value}
            </span>
            {saved && <Check className="h-4 w-4 text-green-500" />}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-sm text-neutral-500 dark:text-neutral-400">
        {formatDate(setting.updated_at)}
      </td>
      <td className="px-4 py-3">
        {setting.editable && !editing && (
          <button
            onClick={() => setEditing(true)}
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
          >
            Edit
          </button>
        )}
      </td>
    </tr>
  );
}

export function AdminSettings() {
  const { hasRole } = useAuth();
  const [categoryFilter, setCategoryFilter] = useState<SettingCategory | ''>('');

  const {
    data: settingsData,
    isLoading,
    error,
  } = usePlatformSettings(
    { category: categoryFilter || undefined },
    { enabled: hasRole('cpi-admin') }
  );

  const updateMutation = useUpdatePlatformSetting();

  const handleSave = useCallback(
    (key: string, value: string) => {
      updateMutation.mutate({ key, value });
    },
    [updateMutation]
  );

  if (!hasRole('cpi-admin')) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <h1 className="text-xl font-semibold text-neutral-900 dark:text-white mb-2">
            Access Denied
          </h1>
          <p className="text-neutral-600 dark:text-neutral-400">
            Platform admin role required to view this page.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">
              Platform Settings
            </h1>
            <p className="text-neutral-500 dark:text-neutral-400 mt-1">
              Configure platform-wide settings and parameters
            </p>
          </div>
          {settingsData && (
            <span className="text-sm text-neutral-500 dark:text-neutral-400">
              {settingsData.total} setting{settingsData.total !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {/* Filters */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 p-4">
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Category
            </label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value as SettingCategory | '')}
              className="rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All categories</option>
              <option value="general">General</option>
              <option value="security">Security</option>
              <option value="gateway">Gateway</option>
              <option value="notifications">Notifications</option>
            </select>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-700 dark:text-red-400">
              Failed to load settings. Please try again.
            </p>
          </div>
        )}

        {/* Table */}
        <div className="bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center p-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent" />
            </div>
          ) : !settingsData?.settings.length ? (
            <div className="flex flex-col items-center justify-center p-12 text-neutral-500 dark:text-neutral-400">
              <Settings className="h-10 w-10 mb-3 opacity-50" />
              <p className="text-sm">No settings found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-neutral-200 dark:divide-neutral-700">
                <thead className="bg-neutral-50 dark:bg-neutral-800/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Setting
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Category
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Value
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Updated
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-200 dark:divide-neutral-700">
                  {settingsData.settings.map((setting) => (
                    <SettingRow
                      key={setting.key}
                      setting={setting}
                      onSave={handleSave}
                      isSaving={updateMutation.isPending}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
