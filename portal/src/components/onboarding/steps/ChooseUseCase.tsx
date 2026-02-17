/**
 * Step 1: Choose Use Case (CAB-1306)
 */

import { Bot, Globe, Layers } from 'lucide-react';

export type UseCase = 'mcp-agent' | 'rest-api' | 'both';

interface ChooseUseCaseProps {
  onSelect: (useCase: UseCase) => void;
}

const USE_CASES = [
  {
    id: 'mcp-agent' as UseCase,
    title: 'MCP Agent',
    description: 'Connect an AI agent (Claude, GPT, custom) to enterprise APIs via MCP protocol.',
    icon: Bot,
    color: 'from-violet-500 to-violet-600',
  },
  {
    id: 'rest-api' as UseCase,
    title: 'REST API',
    description: 'Integrate with traditional REST APIs using OAuth2 credentials and API keys.',
    icon: Globe,
    color: 'from-emerald-500 to-emerald-600',
  },
  {
    id: 'both' as UseCase,
    title: 'Both',
    description: 'Use MCP tools for AI agents AND REST endpoints for traditional integration.',
    icon: Layers,
    color: 'from-primary-500 to-primary-600',
  },
];

export function ChooseUseCase({ onSelect }: ChooseUseCaseProps) {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">How will you use STOA?</h2>
        <p className="mt-2 text-gray-500 dark:text-neutral-400">
          Choose your primary integration pattern. You can always change this later.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
        {USE_CASES.map((uc) => {
          const Icon = uc.icon;
          return (
            <button
              key={uc.id}
              onClick={() => onSelect(uc.id)}
              className="group relative bg-white dark:bg-neutral-900 rounded-xl border border-gray-200 dark:border-neutral-700 p-6 hover:border-primary-400 dark:hover:border-primary-500 hover:shadow-lg transition-all text-left"
            >
              <div
                className={`absolute top-0 left-0 right-0 h-1 rounded-t-xl bg-gradient-to-r ${uc.color} opacity-0 group-hover:opacity-100 transition-opacity`}
              />
              <div
                className={`p-3 rounded-lg bg-gradient-to-br ${uc.color} text-white shadow-sm w-fit mb-4`}
              >
                <Icon className="h-6 w-6" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                {uc.title}
              </h3>
              <p className="text-sm text-gray-500 dark:text-neutral-400">{uc.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
