import { useState, useRef, useEffect, useCallback } from 'react';
import { ChevronDown, Lock, Check, Shield } from 'lucide-react';
import {
  type CanonicalEnvironment,
  normalizeEnvironment,
  getEnvColors,
  getEnvLabel,
} from '../../constants/environments';

export interface EnvironmentInfo {
  name: string;
  label?: string;
  mode: 'full' | 'read-only' | 'promote-only';
  color?: string;
}

export interface EnvironmentChromeProps {
  current: EnvironmentInfo;
  environments: EnvironmentInfo[];
  onSwitch: (envName: string) => void;
  variant?: 'admin' | 'consumer';
  portalLabels?: boolean;
  className?: string;
}

export function EnvironmentChrome({
  current,
  environments,
  onSwitch,
  variant = 'admin',
  portalLabels = false,
  className = '',
}: EnvironmentChromeProps) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const canonical = normalizeEnvironment(current.name);
  const colors = getEnvColors(current.name);
  const isReadOnly = current.mode === 'read-only';

  // Close dropdown on outside click
  useEffect(() => {
    if (!dropdownOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [dropdownOpen]);

  // Keyboard shortcut: Cmd/Ctrl+Shift+E to toggle dropdown
  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'e') {
        e.preventDefault();
        setDropdownOpen((prev) => !prev);
      }
    }
    document.addEventListener('keydown', handleKeydown);
    return () => document.removeEventListener('keydown', handleKeydown);
  }, []);

  const handleSelect = useCallback(
    (envName: string) => {
      if (envName !== current.name) {
        onSwitch(envName);
      }
      setDropdownOpen(false);
    },
    [current.name, onSwitch]
  );

  if (variant === 'consumer') {
    return (
      <ConsumerChrome
        current={current}
        canonical={canonical}
        colors={colors}
        environments={environments}
        onSwitch={onSwitch}
        className={className}
      />
    );
  }

  return (
    <div className={`${colors.chrome} ${colors.chromeText} ${className}`} data-testid="env-chrome">
      <div className="flex items-center justify-between h-9 px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tracking-wide uppercase">
            {getEnvLabel(current.name, portalLabels)}
          </span>
          {isReadOnly && (
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold bg-white/20"
              data-testid="env-readonly-badge"
            >
              <Lock className="h-3 w-3" />
              READ ONLY
            </span>
          )}
          {current.mode === 'promote-only' && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold bg-white/20">
              <Shield className="h-3 w-3" />
              PROMOTE ONLY
            </span>
          )}
        </div>

        {/* Environment switcher dropdown */}
        {environments.length > 1 && (
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 px-2 py-1 rounded text-sm font-medium hover:bg-white/10 transition-colors"
              aria-haspopup="listbox"
              aria-expanded={dropdownOpen}
              aria-label="Switch environment"
              data-testid="env-switcher"
            >
              <span className="hidden sm:inline">Switch</span>
              <ChevronDown
                className={`h-4 w-4 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`}
              />
            </button>

            {dropdownOpen && (
              <div
                className="absolute right-0 mt-1 w-56 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-lg z-[60] py-1"
                role="listbox"
                aria-label="Select environment"
              >
                {environments.map((env) => {
                  const envColors = getEnvColors(env.name);
                  const isCurrent = env.name === current.name;
                  return (
                    <button
                      key={env.name}
                      onClick={() => handleSelect(env.name)}
                      className={`w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors ${
                        isCurrent
                          ? 'bg-neutral-100 dark:bg-neutral-700 font-medium'
                          : 'hover:bg-neutral-50 dark:hover:bg-neutral-700/50'
                      } text-neutral-700 dark:text-neutral-300`}
                      role="option"
                      aria-selected={isCurrent}
                    >
                      <span
                        className={`h-2 w-2 rounded-full flex-shrink-0 ${envColors.dot}`}
                        aria-hidden="true"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="truncate">{getEnvLabel(env.name, portalLabels)}</p>
                        <p className="text-xs text-neutral-500 dark:text-neutral-400">
                          {env.mode === 'read-only' ? 'Read only' : 'Full access'}
                        </p>
                      </div>
                      {env.mode === 'read-only' && (
                        <Lock className="h-3 w-3 text-neutral-400 flex-shrink-0" />
                      )}
                      {isCurrent && (
                        <Check className="h-3.5 w-3.5 text-primary-600 dark:text-primary-400 flex-shrink-0" />
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ConsumerChrome({
  current,
  canonical,
  colors,
  environments,
  onSwitch,
  className = '',
}: {
  current: EnvironmentInfo;
  canonical: CanonicalEnvironment;
  colors: ReturnType<typeof getEnvColors>;
  environments: EnvironmentInfo[];
  onSwitch: (envName: string) => void;
  className?: string;
}) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const isReadOnly = current.mode === 'read-only';
  const isProduction = canonical === 'production';
  const showBar = isProduction || isReadOnly || canonical === 'staging';
  const canSwitch = environments.length > 1;

  useEffect(() => {
    if (!dropdownOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [dropdownOpen]);

  const handleSelect = useCallback(
    (envName: string) => {
      if (envName !== current.name) {
        onSwitch(envName);
      }
      setDropdownOpen(false);
    },
    [current.name, onSwitch]
  );

  return (
    <div className={className}>
      {/* Thin colored line */}
      <div className={`h-1 ${colors.chrome}`} />
      {/* Compact info bar (only for non-default envs or read-only) */}
      {showBar && (
        <div
          className={`flex items-center justify-center gap-2 py-1 text-xs font-medium ${colors.bg} ${colors.bgDark} ${colors.text} ${colors.textDark} ${colors.border} ${colors.borderDark} border-b relative`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${colors.dot}`} />
          <span>{current.label || getEnvLabel(current.name, true)}</span>
          {isReadOnly && (
            <span className="inline-flex items-center gap-0.5 opacity-70">
              <Lock className="h-2.5 w-2.5" />
              Read only
            </span>
          )}
          {canSwitch && (
            <div className="absolute right-3" ref={dropdownRef}>
              <button
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                aria-haspopup="listbox"
                aria-expanded={dropdownOpen}
                aria-label="Switch environment"
                data-testid="env-switcher-consumer"
              >
                <span className="hidden sm:inline">Switch</span>
                <ChevronDown
                  className={`h-3 w-3 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`}
                />
              </button>

              {dropdownOpen && (
                <div
                  className="absolute right-0 mt-1 w-56 bg-white dark:bg-neutral-800 rounded-lg border border-neutral-200 dark:border-neutral-700 shadow-lg z-[60] py-1"
                  role="listbox"
                  aria-label="Select environment"
                >
                  {environments.map((env) => {
                    const envColors = getEnvColors(env.name);
                    const isCurrent = env.name === current.name;
                    return (
                      <button
                        key={env.name}
                        onClick={() => handleSelect(env.name)}
                        className={`w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors ${
                          isCurrent
                            ? 'bg-neutral-100 dark:bg-neutral-700 font-medium'
                            : 'hover:bg-neutral-50 dark:hover:bg-neutral-700/50'
                        } text-neutral-700 dark:text-neutral-300`}
                        role="option"
                        aria-selected={isCurrent}
                      >
                        <span
                          className={`h-2 w-2 rounded-full flex-shrink-0 ${envColors.dot}`}
                          aria-hidden="true"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="truncate">{getEnvLabel(env.name, true)}</p>
                          <p className="text-xs text-neutral-500 dark:text-neutral-400">
                            {env.mode === 'read-only' ? 'Read only' : 'Full access'}
                          </p>
                        </div>
                        {env.mode === 'read-only' && (
                          <Lock className="h-3 w-3 text-neutral-400 flex-shrink-0" />
                        )}
                        {isCurrent && (
                          <Check className="h-3.5 w-3.5 text-primary-600 dark:text-primary-400 flex-shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
