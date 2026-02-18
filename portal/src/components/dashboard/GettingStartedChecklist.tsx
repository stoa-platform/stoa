/**
 * GettingStartedChecklist — Persistent onboarding checklist on Home (CAB-1325)
 *
 * Shows 4 steps with checkmarks, progress bar, and "Continue Setup" button.
 * Dismissible per session (sessionStorage). Hidden when loading, complete, or dismissed.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useOnboardingProgress } from '../../hooks/useOnboarding';

const STEPS = [
  { key: 'choose_use_case', label: 'Choose your use case' },
  { key: 'create_app', label: 'Create your first app' },
  { key: 'subscribe_api', label: 'Subscribe to an API' },
  { key: 'first_call', label: 'Make your first API call' },
];

export function GettingStartedChecklist() {
  const navigate = useNavigate();
  const { data: progress, isLoading } = useOnboardingProgress();
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem('checklist_dismissed') === 'true'
  );

  if (isLoading || !progress || progress.is_complete || dismissed) {
    return null;
  }

  const completedSteps = Object.keys(progress.steps_completed || {});
  const completedCount = STEPS.filter((s) => completedSteps.includes(s.key)).length;
  const progressPct = Math.round((completedCount / STEPS.length) * 100);

  const handleDismiss = () => {
    sessionStorage.setItem('checklist_dismissed', 'true');
    setDismissed(true);
  };

  return (
    <div className="bg-white dark:bg-neutral-800 rounded-lg border border-gray-200 dark:border-neutral-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Getting Started</h3>
        <button
          onClick={handleDismiss}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300 text-sm"
          aria-label="Dismiss checklist"
        >
          Dismiss
        </button>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 dark:bg-neutral-700 rounded-full h-2 mb-4">
        <div
          className="bg-primary-600 h-2 rounded-full transition-all"
          style={{ width: `${progressPct}%` }}
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <p className="text-sm text-gray-500 dark:text-neutral-400 mb-4">
        {completedCount} of {STEPS.length} steps complete
      </p>

      {/* Steps */}
      <ul className="space-y-3 mb-4">
        {STEPS.map((step) => {
          const done = completedSteps.includes(step.key);
          return (
            <li key={step.key} className="flex items-center gap-3">
              <span
                className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                  done
                    ? 'bg-green-100 text-green-600 dark:bg-green-900 dark:text-green-400'
                    : 'bg-gray-100 text-gray-400 dark:bg-neutral-700 dark:text-neutral-500'
                }`}
              >
                {done ? '\u2713' : '\u2022'}
              </span>
              <span
                className={`text-sm ${
                  done
                    ? 'text-gray-500 dark:text-neutral-400 line-through'
                    : 'text-gray-900 dark:text-white'
                }`}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ul>

      <button
        onClick={() => navigate('/onboarding')}
        className="w-full py-2 px-4 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors"
      >
        Continue Setup
      </button>
    </div>
  );
}
