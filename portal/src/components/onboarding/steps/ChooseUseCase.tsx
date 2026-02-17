/**
 * Step 1: Choose Use Case (CAB-1306)
 */

import { Bot, Globe, Layers } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export type UseCase = 'mcp-agent' | 'rest-api' | 'both';

interface ChooseUseCaseProps {
  onSelect: (useCase: UseCase) => void;
}

const USE_CASES = [
  {
    id: 'mcp-agent' as UseCase,
    titleKey: 'chooseUseCase.mcpAgent',
    descKey: 'chooseUseCase.mcpAgentDesc',
    icon: Bot,
    color: 'from-violet-500 to-violet-600',
  },
  {
    id: 'rest-api' as UseCase,
    titleKey: 'chooseUseCase.restApi',
    descKey: 'chooseUseCase.restApiDesc',
    icon: Globe,
    color: 'from-emerald-500 to-emerald-600',
  },
  {
    id: 'both' as UseCase,
    titleKey: 'chooseUseCase.both',
    descKey: 'chooseUseCase.bothDesc',
    icon: Layers,
    color: 'from-primary-500 to-primary-600',
  },
];

export function ChooseUseCase({ onSelect }: ChooseUseCaseProps) {
  const { t } = useTranslation('onboarding');

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
          {t('chooseUseCase.title')}
        </h2>
        <p className="mt-2 text-gray-500 dark:text-neutral-400">{t('chooseUseCase.subtitle')}</p>
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
                {t(uc.titleKey)}
              </h3>
              <p className="text-sm text-gray-500 dark:text-neutral-400">{t(uc.descKey)}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
