/**
 * StepIndicator — Progress bar for onboarding wizard (CAB-1306)
 */

import { Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Step {
  labelKey: string;
  descKey: string;
}

const STEPS: Step[] = [
  { labelKey: 'steps.useCase', descKey: 'steps.useCaseDesc' },
  { labelKey: 'steps.createApp', descKey: 'steps.createAppDesc' },
  { labelKey: 'steps.subscribe', descKey: 'steps.subscribeDesc' },
  { labelKey: 'steps.firstCall', descKey: 'steps.firstCallDesc' },
];

interface StepIndicatorProps {
  currentStep: number;
}

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  const { t } = useTranslation('onboarding');

  return (
    <nav aria-label="Onboarding progress" className="mb-8">
      <ol className="flex items-center w-full">
        {STEPS.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;

          return (
            <li
              key={step.labelKey}
              className={`flex items-center ${index < STEPS.length - 1 ? 'flex-1' : ''}`}
            >
              <div className="flex flex-col items-center">
                <div
                  className={`flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors ${
                    isCompleted
                      ? 'bg-primary-600 border-primary-600 text-white'
                      : isCurrent
                        ? 'border-primary-600 text-primary-600 bg-primary-50 dark:bg-primary-900/30'
                        : 'border-gray-300 dark:border-neutral-600 text-gray-400 dark:text-neutral-500'
                  }`}
                >
                  {isCompleted ? (
                    <Check className="w-5 h-5" />
                  ) : (
                    <span className="text-sm font-semibold">{index + 1}</span>
                  )}
                </div>
                <div className="mt-2 text-center">
                  <p
                    className={`text-xs font-medium ${
                      isCurrent
                        ? 'text-primary-600 dark:text-primary-400'
                        : 'text-gray-500 dark:text-neutral-400'
                    }`}
                  >
                    {t(step.labelKey)}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-neutral-500 hidden sm:block">
                    {t(step.descKey)}
                  </p>
                </div>
              </div>
              {index < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-4 mt-[-1.5rem] ${
                    isCompleted ? 'bg-primary-600' : 'bg-gray-200 dark:bg-neutral-700'
                  }`}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
