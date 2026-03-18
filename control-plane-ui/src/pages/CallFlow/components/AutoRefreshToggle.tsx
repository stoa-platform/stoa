interface AutoRefreshToggleProps {
  value: number; // 0 = off, else interval in seconds
  onChange: (seconds: number) => void;
}

const OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '15s', value: 15 },
  { label: '30s', value: 30 },
  { label: '60s', value: 60 },
];

export function AutoRefreshToggle({ value, onChange }: AutoRefreshToggleProps) {
  return (
    <div className="flex items-center gap-1 bg-neutral-100 dark:bg-neutral-700 rounded-lg p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-2 py-1 text-xs font-medium rounded-md transition-colors ${
            value === opt.value
              ? 'bg-white dark:bg-neutral-600 text-neutral-900 dark:text-white shadow-sm'
              : 'text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
