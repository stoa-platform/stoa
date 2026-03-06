import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Lock, Check } from 'lucide-react';
import {
  usePortalEnvironment,
  type PortalEnvironment,
  type PortalEnvironmentConfig,
} from '../../contexts/EnvironmentContext';

const ENV_COLORS: Record<string, { dot: string; bg: string; text: string }> = {
  green: {
    dot: 'bg-green-500',
    bg: 'bg-green-50 dark:bg-green-900/20',
    text: 'text-green-700 dark:text-green-400',
  },
  amber: {
    dot: 'bg-amber-500',
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    text: 'text-amber-700 dark:text-amber-400',
  },
  red: {
    dot: 'bg-red-500',
    bg: 'bg-red-50 dark:bg-red-900/20',
    text: 'text-red-700 dark:text-red-400',
  },
};

function getColors(color: string) {
  return ENV_COLORS[color] ?? ENV_COLORS.green;
}

interface EnvironmentSelectorProps {
  variant?: 'header' | 'mobile';
}

export function EnvironmentSelector({ variant = 'header' }: EnvironmentSelectorProps) {
  const { activeEnvironment, activeConfig, environments, switchEnvironment, loading } =
    usePortalEnvironment();
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  if (loading || environments.length <= 1) return null;

  const colors = getColors(activeConfig.color);
  const isReadOnly = activeConfig.mode === 'read-only';

  function handleSelect(env: PortalEnvironment) {
    if (env !== activeEnvironment) {
      switchEnvironment(env);
    }
    setIsOpen(false);
  }

  if (variant === 'mobile') {
    return (
      <div className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-1.5 px-1">
          Environment
        </p>
        <div className="flex flex-col gap-1">
          {environments.map((env) => (
            <EnvOption
              key={env.name}
              env={env}
              isActive={env.name === activeEnvironment}
              onSelect={() => handleSelect(env.name as PortalEnvironment)}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${colors.bg} ${colors.text} hover:opacity-80`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={`Environment: ${activeConfig.label}`}
      >
        <span className={`w-2 h-2 rounded-full ${colors.dot}`} aria-hidden="true" />
        <span className="hidden sm:inline">{activeConfig.label}</span>
        {isReadOnly && <Lock className="h-3 w-3 opacity-60" aria-label="Read-only" />}
        <ChevronDown className="h-3.5 w-3.5 opacity-60" aria-hidden="true" />
      </button>

      {isOpen && (
        <div
          className="absolute right-0 mt-1 w-48 bg-white dark:bg-neutral-800 rounded-md shadow-lg border border-neutral-200 dark:border-neutral-700 py-1 z-50"
          role="listbox"
          aria-label="Select environment"
        >
          {environments.map((env) => (
            <EnvOption
              key={env.name}
              env={env}
              isActive={env.name === activeEnvironment}
              onSelect={() => handleSelect(env.name as PortalEnvironment)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EnvOption({
  env,
  isActive,
  onSelect,
}: {
  env: PortalEnvironmentConfig;
  isActive: boolean;
  onSelect: () => void;
}) {
  const colors = getColors(env.color);
  const isReadOnly = env.mode === 'read-only';

  return (
    <button
      onClick={onSelect}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors ${
        isActive
          ? 'bg-neutral-100 dark:bg-neutral-700 font-medium'
          : 'hover:bg-neutral-50 dark:hover:bg-neutral-700/50'
      } text-neutral-700 dark:text-neutral-300`}
      role="option"
      aria-selected={isActive}
    >
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${colors.dot}`} aria-hidden="true" />
      <span className="flex-1 text-left">{env.label}</span>
      {isReadOnly && (
        <Lock className="h-3 w-3 text-neutral-400 dark:text-neutral-500" aria-label="Read-only" />
      )}
      {isActive && (
        <Check className="h-3.5 w-3.5 text-primary-600 dark:text-primary-400" aria-hidden="true" />
      )}
    </button>
  );
}
