import type { MarketplaceCategory, MarketplaceItemType } from '../../types';

interface MarketplaceFiltersProps {
  selectedType: MarketplaceItemType | 'all';
  onTypeChange: (type: MarketplaceItemType | 'all') => void;
  categories: MarketplaceCategory[];
  selectedCategory: string;
  onCategoryChange: (category: string) => void;
}

const typeOptions: { value: MarketplaceItemType | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'api', label: 'APIs' },
  { value: 'mcp-server', label: 'AI Tools' },
];

export function MarketplaceFilterBar({
  selectedType,
  onTypeChange,
  categories,
  selectedCategory,
  onCategoryChange,
}: MarketplaceFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Type filter pills */}
      <div className="flex items-center gap-1 rounded-lg bg-neutral-100 p-1 dark:bg-neutral-800">
        {typeOptions.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onTypeChange(opt.value)}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              selectedType === opt.value
                ? 'bg-white text-emerald-700 shadow-sm dark:bg-neutral-700 dark:text-emerald-400'
                : 'text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Category dropdown */}
      {categories.length > 0 && (
        <select
          value={selectedCategory}
          onChange={(e) => onCategoryChange(e.target.value)}
          className="px-3 py-2 text-sm rounded-lg border border-neutral-200 bg-white
            focus:outline-none focus:ring-2 focus:ring-emerald-500
            dark:bg-neutral-800 dark:border-neutral-700 dark:text-white"
        >
          <option value="">All Categories</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.id}>
              {cat.name} ({cat.count})
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
