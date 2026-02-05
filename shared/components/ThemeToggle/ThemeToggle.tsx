import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme, type Theme } from '../../contexts/ThemeContext';

// ============================================================================
// Types
// ============================================================================

export interface ThemeToggleProps {
  /** Show label text */
  showLabel?: boolean;
  /** Size variant */
  size?: 'sm' | 'md' | 'lg';
  /** Additional className */
  className?: string;
}

// ============================================================================
// Simple Toggle Button (Light/Dark only)
// ============================================================================

export function ThemeToggle({
  showLabel = false,
  size = 'md',
  className = '',
}: ThemeToggleProps) {
  const { resolvedTheme, toggleTheme } = useTheme();

  const sizeClasses = {
    sm: 'p-1.5',
    md: 'p-2',
    lg: 'p-2.5',
  };

  const iconSizes = {
    sm: 'h-4 w-4',
    md: 'h-5 w-5',
    lg: 'h-6 w-6',
  };

  return (
    <button
      onClick={toggleTheme}
      className={`
        ${sizeClasses[size]}
        rounded-lg
        text-neutral-500 dark:text-neutral-400
        hover:bg-neutral-100 dark:hover:bg-neutral-800
        hover:text-neutral-700 dark:hover:text-neutral-200
        transition-colors
        ${showLabel ? 'flex items-center gap-2' : ''}
        ${className}
      `}
      title={`Switch to ${resolvedTheme === 'dark' ? 'light' : 'dark'} mode`}
    >
      {resolvedTheme === 'dark' ? (
        <Sun className={iconSizes[size]} />
      ) : (
        <Moon className={iconSizes[size]} />
      )}
      {showLabel && (
        <span className="text-sm font-medium">
          {resolvedTheme === 'dark' ? 'Light mode' : 'Dark mode'}
        </span>
      )}
    </button>
  );
}

// ============================================================================
// Three-way Selector (Light/Dark/System)
// ============================================================================

export interface ThemeSelectorProps {
  /** Additional className */
  className?: string;
}

export function ThemeSelector({ className = '' }: ThemeSelectorProps) {
  const { theme, setTheme } = useTheme();

  const options: { value: Theme; icon: typeof Sun; label: string }[] = [
    { value: 'light', icon: Sun, label: 'Light' },
    { value: 'dark', icon: Moon, label: 'Dark' },
    { value: 'system', icon: Monitor, label: 'System' },
  ];

  return (
    <div
      className={`
        inline-flex items-center
        p-1 rounded-lg
        bg-neutral-100 dark:bg-neutral-800
        ${className}
      `}
    >
      {options.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          className={`
            flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium
            transition-colors
            ${
              theme === value
                ? 'bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-sm'
                : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
            }
          `}
          title={label}
        >
          <Icon className="h-4 w-4" />
          <span className="hidden sm:inline">{label}</span>
        </button>
      ))}
    </div>
  );
}

// ============================================================================
// Dropdown Selector
// ============================================================================

export interface ThemeDropdownProps {
  /** Additional className */
  className?: string;
}

export function ThemeDropdown({ className = '' }: ThemeDropdownProps) {
  const { theme, setTheme, resolvedTheme } = useTheme();

  const icons = {
    light: Sun,
    dark: Moon,
    system: Monitor,
  };

  const CurrentIcon = theme === 'system' ? icons[resolvedTheme] : icons[theme];

  return (
    <div className={`relative ${className}`}>
      <select
        value={theme}
        onChange={(e) => setTheme(e.target.value as Theme)}
        className="
          appearance-none
          pl-9 pr-8 py-2
          rounded-lg border border-neutral-200 dark:border-neutral-700
          bg-white dark:bg-neutral-800
          text-sm text-neutral-900 dark:text-neutral-100
          focus:ring-2 focus:ring-primary-500 focus:border-transparent
          cursor-pointer
        "
      >
        <option value="light">Light</option>
        <option value="dark">Dark</option>
        <option value="system">System</option>
      </select>
      <CurrentIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-400 pointer-events-none" />
    </div>
  );
}

export default ThemeToggle;
