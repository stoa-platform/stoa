import { Search } from 'lucide-react';

interface MarketplaceSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function MarketplaceSearch({
  value,
  onChange,
  placeholder = 'Search APIs, AI tools, and more...',
}: MarketplaceSearchProps) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-neutral-400" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-10 pr-4 py-3 rounded-lg border border-neutral-200 bg-white text-sm
          placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-emerald-500
          focus:border-transparent dark:bg-neutral-800 dark:border-neutral-700 dark:text-white"
      />
    </div>
  );
}
