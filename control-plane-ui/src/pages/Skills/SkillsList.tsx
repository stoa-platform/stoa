import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, AlertTriangle, Sparkles, Trash2, Pencil } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { skillsService, type SkillEntry, type SkillUpsert } from '../../services/skillsApi';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import { EmptyState } from '@stoa/shared/components/EmptyState';
import { SkillFormModal } from './SkillFormModal';
import { SkillPreview } from './SkillPreview';

const scopeConfig: Record<string, { color: string; label: string; specificity: number }> = {
  global: {
    color: 'bg-neutral-100 text-neutral-800 dark:bg-neutral-900/30 dark:text-neutral-400',
    label: 'Global',
    specificity: 0,
  },
  tenant: {
    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    label: 'Tenant',
    specificity: 1,
  },
  tool: {
    color: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
    label: 'Tool',
    specificity: 2,
  },
  user: {
    color: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
    label: 'User',
    specificity: 3,
  },
};

export function SkillsList() {
  const { hasRole } = useAuth();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [showModal, setShowModal] = useState(false);
  const [editingSkill, setEditingSkill] = useState<SkillEntry | null>(null);

  const {
    data: skills,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['skills'],
    queryFn: () => skillsService.listSkills(),
  });

  const handleDelete = useCallback(
    async (key: string, name: string) => {
      const confirmed = await confirm({
        title: 'Delete Skill',
        message: `Are you sure you want to delete "${name}" (${key})? This action cannot be undone.`,
        confirmLabel: 'Delete',
        variant: 'danger',
      });
      if (!confirmed) return;

      try {
        await skillsService.deleteSkill(key);
        queryClient.invalidateQueries({ queryKey: ['skills'] });
        toast.success('Skill deleted', `${name} has been removed`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to delete skill';
        toast.error('Delete failed', message);
      }
    },
    [queryClient, toast, confirm]
  );

  const handleSave = useCallback(
    async (payload: SkillUpsert) => {
      try {
        await skillsService.upsertSkill(payload);
        queryClient.invalidateQueries({ queryKey: ['skills'] });
        toast.success(
          editingSkill ? 'Skill updated' : 'Skill created',
          `${payload.name} has been saved`
        );
        setShowModal(false);
        setEditingSkill(null);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Failed to save skill';
        toast.error('Save failed', message);
      }
    },
    [queryClient, toast, editingSkill]
  );

  const isAdmin = hasRole('cpi-admin') || hasRole('tenant-admin');
  const items = skills || [];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <div className="h-8 w-64 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
          <div className="h-10 w-36 bg-neutral-200 dark:bg-neutral-700 rounded animate-pulse" />
        </div>
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <div className="p-6 space-y-4">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-12 bg-neutral-100 dark:bg-neutral-700 rounded animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Skills</h1>
          <p className="text-neutral-500 dark:text-neutral-400 mt-1">
            Manage agent skill instructions using the CSS cascade model
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => {
              setEditingSkill(null);
              setShowModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Add Skill
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {error instanceof Error ? error.message : 'Failed to load skills'}
        </div>
      )}

      {/* Cascade legend */}
      <div className="flex items-center gap-3 text-xs text-neutral-500 dark:text-neutral-400">
        <span className="font-medium">Cascade order:</span>
        {['global', 'tenant', 'tool', 'user'].map((scope) => {
          const cfg = scopeConfig[scope];
          return (
            <span key={scope} className={`inline-flex px-2 py-0.5 rounded-full ${cfg.color}`}>
              {cfg.label} ({cfg.specificity})
            </span>
          );
        })}
        <span className="ml-1 italic">Higher specificity wins</span>
      </div>

      {/* Table */}
      {items.length === 0 ? (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
          <EmptyState
            variant="default"
            title="No skills configured"
            description="Add skills to inject context instructions into agent conversations using the CSS cascade model."
            action={
              isAdmin
                ? {
                    label: 'Add Skill',
                    onClick: () => {
                      setEditingSkill(null);
                      setShowModal(true);
                    },
                  }
                : undefined
            }
          />
        </div>
      ) : (
        <div className="bg-white dark:bg-neutral-800 rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800">
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Name
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Scope
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Priority
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Tenant
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                  Status
                </th>
                {isAdmin && (
                  <th className="text-right px-4 py-3 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase">
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-neutral-700">
              {items.map((skill) => {
                const scope = scopeConfig[skill.scope] || scopeConfig.global;
                return (
                  <tr key={skill.key} className="hover:bg-neutral-50 dark:hover:bg-neutral-750">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-amber-500 flex-shrink-0" />
                        <div>
                          <div className="font-medium text-neutral-900 dark:text-white text-sm">
                            {skill.name}
                          </div>
                          <div className="text-xs text-neutral-500 dark:text-neutral-400 font-mono truncate max-w-xs">
                            {skill.key}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${scope.color}`}
                      >
                        {scope.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300 font-mono">
                      {skill.priority}
                    </td>
                    <td className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300">
                      {skill.tenant_id}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${
                          skill.enabled
                            ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-900/30 dark:text-neutral-400'
                        }`}
                      >
                        {skill.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </td>
                    {isAdmin && (
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => {
                              setEditingSkill(skill);
                              setShowModal(true);
                            }}
                            className="text-xs px-2 py-1 text-blue-600 border border-blue-200 dark:border-blue-800 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20"
                          >
                            <Pencil className="h-3 w-3" />
                          </button>
                          <button
                            onClick={() => handleDelete(skill.key, skill.name)}
                            className="text-xs px-2 py-1 text-red-600 border border-red-200 dark:border-red-800 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Resolution Preview */}
      <SkillPreview />

      {/* Modal */}
      {showModal && (
        <SkillFormModal
          skill={editingSkill}
          onClose={() => {
            setShowModal(false);
            setEditingSkill(null);
          }}
          onSave={handleSave}
        />
      )}

      {ConfirmDialog}
    </div>
  );
}
