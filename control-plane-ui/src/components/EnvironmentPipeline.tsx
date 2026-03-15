import { CheckCircle, Circle, ArrowRight } from 'lucide-react';

interface EnvironmentPipelineProps {
  deployed_dev: boolean;
  deployed_staging: boolean;
  deployed_prod?: boolean;
  compact?: boolean;
}

interface EnvNode {
  label: string;
  deployed: boolean;
}

export function EnvironmentPipeline({
  deployed_dev,
  deployed_staging,
  deployed_prod = false,
  compact = false,
}: EnvironmentPipelineProps) {
  const envs: EnvNode[] = [
    { label: 'DEV', deployed: deployed_dev },
    { label: 'STG', deployed: deployed_staging },
    { label: 'PROD', deployed: deployed_prod },
  ];

  if (compact) {
    return (
      <div className="flex items-center gap-1">
        {envs.map((env, i) => (
          <span key={env.label} className="flex items-center gap-1">
            <span
              className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs font-medium rounded ${
                env.deployed
                  ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                  : 'bg-neutral-100 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-500'
              }`}
            >
              {env.label}
            </span>
            {i < envs.length - 1 && (
              <ArrowRight className="h-3 w-3 text-neutral-300 dark:text-neutral-600" />
            )}
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      {envs.map((env, i) => (
        <div key={env.label} className="flex items-center gap-3">
          <div
            className={`flex flex-col items-center gap-1 px-4 py-3 rounded-lg border-2 min-w-[80px] ${
              env.deployed
                ? 'border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-900/20'
                : 'border-neutral-200 bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-800/50'
            }`}
          >
            {env.deployed ? (
              <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
            ) : (
              <Circle className="h-5 w-5 text-neutral-300 dark:text-neutral-600" />
            )}
            <span
              className={`text-xs font-semibold ${
                env.deployed
                  ? 'text-green-700 dark:text-green-400'
                  : 'text-neutral-400 dark:text-neutral-500'
              }`}
            >
              {env.label}
            </span>
          </div>
          {i < envs.length - 1 && (
            <ArrowRight className="h-5 w-5 text-neutral-300 dark:text-neutral-600 flex-shrink-0" />
          )}
        </div>
      ))}
    </div>
  );
}
