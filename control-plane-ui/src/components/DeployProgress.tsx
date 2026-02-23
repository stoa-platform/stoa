import { CheckCircle, Circle, Loader2, XCircle } from 'lucide-react';
import type { DeployLogEntry, DeployEventType } from '@/types';

const DEPLOY_STEPS = ['validating', 'syncing', 'health-check', 'complete'] as const;
type DeployStep = (typeof DEPLOY_STEPS)[number];

interface DeployProgressProps {
  logs: DeployLogEntry[];
  lastEvent: DeployEventType | null;
}

function getStepStatus(
  step: DeployStep,
  activeSteps: Set<string>,
  lastEvent: DeployEventType | null
): 'pending' | 'active' | 'done' | 'failed' {
  const isFailed = lastEvent === 'deploy-failed';
  const isDone = lastEvent === 'deploy-success';

  if (isDone) return 'done';
  if (isFailed && activeSteps.has(step)) return 'failed';
  if (activeSteps.has(step)) return 'active';

  // Infer completion: if a later step is active, earlier steps are done
  const stepIdx = DEPLOY_STEPS.indexOf(step);
  for (let i = stepIdx + 1; i < DEPLOY_STEPS.length; i++) {
    if (activeSteps.has(DEPLOY_STEPS[i])) return 'done';
  }

  return 'pending';
}

function StepIcon({ status }: { status: 'pending' | 'active' | 'done' | 'failed' }) {
  switch (status) {
    case 'done':
      return <CheckCircle className="h-5 w-5 text-green-500" />;
    case 'active':
      return <Loader2 className="h-5 w-5 animate-spin text-blue-500" />;
    case 'failed':
      return <XCircle className="h-5 w-5 text-red-500" />;
    default:
      return <Circle className="h-5 w-5 text-gray-400" />;
  }
}

export function DeployProgress({ logs, lastEvent }: DeployProgressProps) {
  const activeSteps = new Set(logs.filter((l) => l.step).map((l) => l.step as string));

  return (
    <div className="flex items-center gap-2">
      {DEPLOY_STEPS.map((step, idx) => {
        const status = getStepStatus(step, activeSteps, lastEvent);
        return (
          <div key={step} className="flex items-center gap-2">
            {idx > 0 && (
              <div
                className={`h-0.5 w-8 ${
                  status === 'done' || status === 'active'
                    ? 'bg-blue-500'
                    : status === 'failed'
                      ? 'bg-red-500'
                      : 'bg-gray-600'
                }`}
              />
            )}
            <div className="flex items-center gap-1.5">
              <StepIcon status={status} />
              <span
                className={`text-xs capitalize ${
                  status === 'active'
                    ? 'font-medium text-blue-400'
                    : status === 'done'
                      ? 'text-green-400'
                      : status === 'failed'
                        ? 'text-red-400'
                        : 'text-gray-500'
                }`}
              >
                {step}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
