import { CheckCircle2, Loader2, Circle } from 'lucide-react';
import { clsx } from 'clsx';
import type { DeploymentStatus } from '../types';

const DEPLOY_STEPS = [
  { key: 'init', label: 'Validating' },
  { key: 'sync', label: 'Syncing' },
  { key: 'health-check', label: 'Health Check' },
  { key: 'complete', label: 'Complete' },
] as const;

type StepStatus = 'done' | 'active' | 'pending' | 'failed';

function getStepStatus(
  stepKey: string,
  currentStep: string | null,
  deployStatus: DeploymentStatus | null
): StepStatus {
  if (deployStatus === 'failed') {
    const idx = DEPLOY_STEPS.findIndex((s) => s.key === stepKey);
    const currentIdx = DEPLOY_STEPS.findIndex((s) => s.key === currentStep);
    if (idx < currentIdx) return 'done';
    if (idx === currentIdx) return 'failed';
    return 'pending';
  }
  if (deployStatus === 'success') return 'done';

  const idx = DEPLOY_STEPS.findIndex((s) => s.key === stepKey);
  const currentIdx = DEPLOY_STEPS.findIndex((s) => s.key === currentStep);
  if (currentIdx < 0) return 'pending';
  if (idx < currentIdx) return 'done';
  if (idx === currentIdx) return 'active';
  return 'pending';
}

interface DeployProgressProps {
  currentStep: string | null;
  status: DeploymentStatus | null;
}

export function DeployProgress({ currentStep, status }: DeployProgressProps) {
  return (
    <div className="flex items-center gap-1">
      {DEPLOY_STEPS.map((step, index) => {
        const stepStatus = getStepStatus(step.key, currentStep, status);
        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={clsx(
                  'flex items-center justify-center w-7 h-7 rounded-full',
                  stepStatus === 'done' && 'bg-green-100 dark:bg-green-900/30',
                  stepStatus === 'active' && 'bg-blue-100 dark:bg-blue-900/30',
                  stepStatus === 'failed' && 'bg-red-100 dark:bg-red-900/30',
                  stepStatus === 'pending' && 'bg-neutral-100 dark:bg-neutral-700'
                )}
              >
                {stepStatus === 'done' && (
                  <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                )}
                {stepStatus === 'active' && (
                  <Loader2 className="h-4 w-4 text-blue-600 dark:text-blue-400 animate-spin" />
                )}
                {stepStatus === 'failed' && (
                  <Circle className="h-4 w-4 text-red-600 dark:text-red-400" />
                )}
                {stepStatus === 'pending' && (
                  <Circle className="h-4 w-4 text-neutral-400 dark:text-neutral-500" />
                )}
              </div>
              <span
                className={clsx(
                  'text-[10px] mt-1 whitespace-nowrap',
                  stepStatus === 'done' && 'text-green-600 dark:text-green-400',
                  stepStatus === 'active' && 'text-blue-600 dark:text-blue-400 font-medium',
                  stepStatus === 'failed' && 'text-red-600 dark:text-red-400',
                  stepStatus === 'pending' && 'text-neutral-400 dark:text-neutral-500'
                )}
              >
                {step.label}
              </span>
            </div>
            {index < DEPLOY_STEPS.length - 1 && (
              <div
                className={clsx(
                  'w-8 h-0.5 mx-1 mb-4',
                  stepStatus === 'done'
                    ? 'bg-green-300 dark:bg-green-700'
                    : 'bg-neutral-200 dark:bg-neutral-600'
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
