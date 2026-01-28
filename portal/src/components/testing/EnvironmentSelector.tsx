// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Environment Selector Component
 *
 * Dropdown for selecting the target environment for API testing.
 */

import { ChevronDown, Server, AlertTriangle } from 'lucide-react';
import { config } from '../../config';

export interface Environment {
  id: string;
  name: string;
  displayName: string;
  baseUrl: string;
  isProduction: boolean;
}

interface EnvironmentSelectorProps {
  environments: Environment[];
  selectedEnvironment: Environment | null;
  onSelect: (env: Environment) => void;
  disabled?: boolean;
}

export function EnvironmentSelector({
  environments,
  selectedEnvironment,
  onSelect,
  disabled = false,
}: EnvironmentSelectorProps) {
  const isProductionPortal = config.portalMode === 'production';

  return (
    <div className="relative">
      <label htmlFor="environment-select" className="block text-sm font-medium text-gray-700 mb-1">
        Target Environment
      </label>
      <div className="relative">
        <select
          id="environment-select"
          value={selectedEnvironment?.id || ''}
          onChange={(e) => {
            const env = environments.find((env) => env.id === e.target.value);
            if (env) onSelect(env);
          }}
          disabled={disabled || environments.length === 0}
          className={`
            w-full pl-10 pr-10 py-2.5
            border rounded-lg appearance-none cursor-pointer
            focus:ring-2 focus:ring-primary-500 focus:border-primary-500
            disabled:bg-gray-100 disabled:cursor-not-allowed
            ${selectedEnvironment?.isProduction
              ? 'border-amber-300 bg-amber-50'
              : 'border-gray-300 bg-white'
            }
          `}
        >
          {environments.length === 0 ? (
            <option value="">No environments available</option>
          ) : (
            environments.map((env) => (
              <option key={env.id} value={env.id}>
                {env.displayName}
                {env.isProduction ? ' (Production)' : ''}
              </option>
            ))
          )}
        </select>
        <Server className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
      </div>

      {/* Production Warning */}
      {selectedEnvironment?.isProduction && (
        <div className="mt-2 flex items-start gap-2 p-2 bg-amber-50 border border-amber-200 rounded-lg">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-amber-700">
            You are targeting a <strong>production</strong> environment.
            {isProductionPortal && ' Requests will be logged for audit purposes.'}
          </p>
        </div>
      )}

      {/* Environment URL */}
      {selectedEnvironment && (
        <p className="mt-1 text-xs text-gray-500">
          Base URL: <code className="bg-gray-100 px-1 rounded">{selectedEnvironment.baseUrl}</code>
        </p>
      )}
    </div>
  );
}

export default EnvironmentSelector;
