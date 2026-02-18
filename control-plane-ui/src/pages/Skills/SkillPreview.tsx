import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Play } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { skillsService, type ResolvedSkill } from '../../services/skillsApi';

const scopeColors: Record<string, string> = {
  global: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  tenant: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  tool: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  user: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
};

export function SkillPreview() {
  const { user } = useAuth();
  const tenantId = user?.tenant_id || '';
  const [expanded, setExpanded] = useState(false);
  const [toolRef, setToolRef] = useState('');
  const [userRef, setUserRef] = useState('');

  const {
    data: resolved,
    isLoading,
    refetch,
  } = useQuery<ResolvedSkill[]>({
    queryKey: ['skills-resolve', tenantId, toolRef, userRef],
    queryFn: () =>
      skillsService.resolveSkills(tenantId, toolRef || undefined, userRef || undefined),
    enabled: false,
  });

  const handleResolve = () => {
    refetch();
  };

  const mergedInstructions = resolved
    ?.filter((s) => s.instructions)
    .map((s) => s.instructions)
    .join('\n\n---\n\n');

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg shadow">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-4 py-3 text-sm font-medium text-gray-700 dark:text-neutral-300 hover:bg-gray-50 dark:hover:bg-neutral-750"
      >
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        Resolution Preview
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t dark:border-neutral-700">
          <p className="text-xs text-gray-500 dark:text-neutral-400 pt-3">
            Test the CSS cascade resolution for a given context. Skills are resolved by specificity
            (global &lt; tenant &lt; tool &lt; user), then by priority within the same scope.
          </p>

          <div className="flex items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-600 dark:text-neutral-400 mb-1">
                Tool Name
              </label>
              <input
                type="text"
                value={toolRef}
                onChange={(e) => setToolRef(e.target.value)}
                placeholder="e.g. code-review"
                className="w-full px-3 py-1.5 text-sm border dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white"
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-600 dark:text-neutral-400 mb-1">
                User Ref
              </label>
              <input
                type="text"
                value={userRef}
                onChange={(e) => setUserRef(e.target.value)}
                placeholder="e.g. alice"
                className="w-full px-3 py-1.5 text-sm border dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white"
              />
            </div>
            <button
              onClick={handleResolve}
              disabled={isLoading}
              className="flex items-center gap-1.5 px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              <Play className="h-3 w-3" />
              {isLoading ? 'Resolving...' : 'Resolve'}
            </button>
          </div>

          {resolved && resolved.length > 0 && (
            <div className="space-y-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b dark:border-neutral-700">
                    <th className="text-left py-2 text-xs font-medium text-gray-500 dark:text-neutral-400">
                      Name
                    </th>
                    <th className="text-left py-2 text-xs font-medium text-gray-500 dark:text-neutral-400">
                      Scope
                    </th>
                    <th className="text-left py-2 text-xs font-medium text-gray-500 dark:text-neutral-400">
                      Specificity
                    </th>
                    <th className="text-left py-2 text-xs font-medium text-gray-500 dark:text-neutral-400">
                      Priority
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y dark:divide-neutral-700">
                  {resolved.map((skill, i) => (
                    <tr key={i}>
                      <td className="py-2 text-gray-900 dark:text-white">{skill.name}</td>
                      <td className="py-2">
                        <span
                          className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${scopeColors[skill.scope] || scopeColors.global}`}
                        >
                          {skill.scope}
                        </span>
                      </td>
                      <td className="py-2 font-mono text-gray-600 dark:text-neutral-300">
                        {skill.specificity}
                      </td>
                      <td className="py-2 font-mono text-gray-600 dark:text-neutral-300">
                        {skill.priority}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {mergedInstructions && (
                <div>
                  <h4 className="text-xs font-medium text-gray-500 dark:text-neutral-400 mb-1">
                    Merged Instructions
                  </h4>
                  <pre className="text-xs bg-gray-50 dark:bg-neutral-900 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap text-gray-800 dark:text-neutral-200 max-h-48 overflow-y-auto">
                    {mergedInstructions}
                  </pre>
                </div>
              )}
            </div>
          )}

          {resolved && resolved.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-neutral-400 italic">
              No skills matched the given context.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
