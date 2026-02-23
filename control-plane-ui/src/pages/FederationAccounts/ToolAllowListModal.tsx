import { useState, useEffect, useCallback } from 'react';
import { X, Wrench, Search } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { federationService } from '../../services/federationApi';
import { mcpGatewayService } from '../../services/mcpGatewayApi';
import { useToastActions } from '@stoa/shared/components/Toast';

interface ToolAllowListModalProps {
  tenantId: string;
  masterId: string;
  subAccountId: string;
  subAccountName: string;
  isAdmin: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function ToolAllowListModal({
  tenantId,
  masterId,
  subAccountId,
  subAccountName,
  isAdmin,
  onClose,
  onSaved,
}: ToolAllowListModalProps) {
  const toast = useToastActions();
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const { data: allowList, isLoading: allowListLoading } = useQuery({
    queryKey: ['federation-tool-allow-list', tenantId, masterId, subAccountId],
    queryFn: () => federationService.getToolAllowList(tenantId, masterId, subAccountId),
  });

  const {
    data: catalog,
    isLoading: catalogLoading,
    isError: catalogError,
  } = useQuery({
    queryKey: ['mcp-tools-catalog'],
    queryFn: () => mcpGatewayService.getTools({ limit: 100 }),
  });

  useEffect(() => {
    if (allowList) {
      setSelectedTools(new Set(allowList.allowed_tools));
    }
  }, [allowList]);

  const handleToggle = useCallback(
    (toolName: string) => {
      if (!isAdmin) return;
      setSelectedTools((prev) => {
        const next = new Set(prev);
        if (next.has(toolName)) {
          next.delete(toolName);
        } else {
          next.add(toolName);
        }
        return next;
      });
    },
    [isAdmin]
  );

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      await federationService.updateToolAllowList(
        tenantId,
        masterId,
        subAccountId,
        Array.from(selectedTools)
      );
      toast.success('Tools updated', `Allow-list updated for ${subAccountName}`);
      onSaved();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to update tool allow-list';
      toast.error('Update failed', message);
    } finally {
      setIsSaving(false);
    }
  }, [tenantId, masterId, subAccountId, selectedTools, subAccountName, toast, onSaved]);

  const isLoading = allowListLoading || catalogLoading;

  const filteredTools = catalog?.tools.filter(
    (t) =>
      !search ||
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.description.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-lg p-6 max-h-[80vh] flex flex-col">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-white flex items-center gap-2">
              <Wrench className="h-5 w-5" />
              Tool Allow-List
            </h3>
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-0.5">
              {subAccountName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center py-8">
            <div className="h-6 w-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : catalogError || !catalog ? (
          <div className="flex-1 overflow-y-auto">
            <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-3">
              Tool catalog unavailable. Showing current allow-list as read-only.
            </p>
            <div className="flex flex-wrap gap-2">
              {Array.from(selectedTools).map((tool) => (
                <span
                  key={tool}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-sm bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded-full"
                >
                  <Wrench className="h-3 w-3" />
                  {tool}
                </span>
              ))}
              {selectedTools.size === 0 && (
                <p className="text-sm text-neutral-400 dark:text-neutral-500">No tools allowed</p>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tools..."
                className="w-full pl-9 pr-3 py-2 text-sm border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
              {filteredTools && filteredTools.length > 0 ? (
                filteredTools.map((tool) => (
                  <label
                    key={tool.name}
                    className={`flex items-start gap-3 p-2 rounded-lg ${
                      isAdmin
                        ? 'hover:bg-neutral-50 dark:hover:bg-neutral-750 cursor-pointer'
                        : 'opacity-75 cursor-default'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedTools.has(tool.name)}
                      onChange={() => handleToggle(tool.name)}
                      disabled={!isAdmin}
                      className="mt-0.5 h-4 w-4 rounded border-neutral-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
                    />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-neutral-900 dark:text-white">
                        {tool.name}
                      </div>
                      <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                        {tool.description}
                      </div>
                    </div>
                  </label>
                ))
              ) : (
                <p className="text-sm text-neutral-400 dark:text-neutral-500 text-center py-4">
                  {search ? 'No tools match your search' : 'No tools available'}
                </p>
              )}
            </div>
          </>
        )}

        <div className="flex justify-between items-center pt-4 mt-4 border-t dark:border-neutral-700">
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            {selectedTools.size} tool{selectedTools.size !== 1 ? 's' : ''} selected
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-neutral-700 dark:text-neutral-300 border border-neutral-300 dark:border-neutral-600 rounded-lg hover:bg-neutral-50 dark:hover:bg-neutral-700"
            >
              Cancel
            </button>
            {isAdmin && !catalogError && catalog && (
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
