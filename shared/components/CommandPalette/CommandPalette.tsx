import { useState, useEffect, useCallback, useRef, useMemo, createContext, useContext } from 'react';
import { Search, Command, ArrowRight } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon?: React.ReactNode;
  shortcut?: string[];
  section?: string;
  keywords?: string[];
  onSelect: () => void;
}

export interface CommandPaletteProps {
  items: CommandItem[];
  placeholder?: string;
  onClose: () => void;
}

interface CommandPaletteContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  items: CommandItem[];
  setItems: (items: CommandItem[]) => void;
}

// ============================================================================
// Context
// ============================================================================

const CommandPaletteContext = createContext<CommandPaletteContextValue | null>(null);

export function useCommandPalette() {
  const context = useContext(CommandPaletteContext);
  if (!context) {
    throw new Error('useCommandPalette must be used within a CommandPaletteProvider');
  }
  return context;
}

// ============================================================================
// Fuzzy Search
// ============================================================================

function fuzzyMatch(query: string, text: string): boolean {
  const queryLower = query.toLowerCase();
  const textLower = text.toLowerCase();

  // Simple contains match
  if (textLower.includes(queryLower)) return true;

  // Fuzzy character match
  let queryIndex = 0;
  for (let i = 0; i < textLower.length && queryIndex < queryLower.length; i++) {
    if (textLower[i] === queryLower[queryIndex]) {
      queryIndex++;
    }
  }
  return queryIndex === queryLower.length;
}

function filterItems(items: CommandItem[], query: string): CommandItem[] {
  if (!query) return items;

  return items.filter(item => {
    const searchableText = [
      item.label,
      item.description || '',
      ...(item.keywords || []),
    ].join(' ');
    return fuzzyMatch(query, searchableText);
  });
}

// ============================================================================
// Keyboard Shortcut Display
// ============================================================================

function ShortcutKey({ shortcut }: { shortcut: string[] }) {
  return (
    <div className="flex items-center gap-1">
      {shortcut.map((key, index) => (
        <kbd
          key={index}
          className="px-1.5 py-0.5 text-xs font-medium text-neutral-500 dark:text-neutral-400 bg-neutral-100 dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded"
        >
          {key}
        </kbd>
      ))}
    </div>
  );
}

// ============================================================================
// Command Palette Component
// ============================================================================

export function CommandPalette({ items, placeholder = 'Search commands...', onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filteredItems = useMemo(() => filterItems(items, query), [items, query]);

  // Group items by section
  const groupedItems = useMemo(() => {
    const groups: Record<string, CommandItem[]> = {};
    filteredItems.forEach(item => {
      const section = item.section || 'Actions';
      if (!groups[section]) groups[section] = [];
      groups[section].push(item);
    });
    return groups;
  }, [filteredItems]);

  // Flatten for index-based selection
  const flatItems = useMemo(() => {
    return Object.values(groupedItems).flat();
  }, [groupedItems]);

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(i => Math.min(i + 1, flatItems.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(i => Math.max(i - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (flatItems[selectedIndex]) {
          flatItems[selectedIndex].onSelect();
          onClose();
        }
        break;
      case 'Escape':
        e.preventDefault();
        onClose();
        break;
    }
  }, [flatItems, selectedIndex, onClose]);

  // Scroll selected item into view
  useEffect(() => {
    const selectedElement = listRef.current?.querySelector(`[data-index="${selectedIndex}"]`);
    selectedElement?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  // Handle backdrop click
  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  let currentIndex = 0;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]"
      onClick={handleBackdropClick}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 animate-fade-in" />

      {/* Dialog */}
      <div
        className="relative bg-white dark:bg-neutral-900 rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden animate-scale-in"
        onKeyDown={handleKeyDown}
      >
        {/* Search Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-neutral-200 dark:border-neutral-700">
          <Search className="h-5 w-5 text-neutral-400 flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            className="flex-1 text-base text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 dark:placeholder-neutral-500 outline-none bg-transparent"
          />
          <kbd className="hidden sm:flex items-center gap-1 px-2 py-1 text-xs font-medium text-neutral-400 bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded">
            esc
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[60vh] overflow-y-auto">
          {flatItems.length === 0 ? (
            <div className="px-4 py-12 text-center text-neutral-500 dark:text-neutral-400">
              <Command className="h-8 w-8 mx-auto mb-3 text-neutral-300 dark:text-neutral-600" />
              <p className="text-sm">No results found</p>
              <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">Try a different search term</p>
            </div>
          ) : (
            Object.entries(groupedItems).map(([section, sectionItems]) => (
              <div key={section}>
                {/* Section Header */}
                <div className="px-4 py-2 text-xs font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider bg-neutral-50 dark:bg-neutral-800">
                  {section}
                </div>

                {/* Section Items */}
                {sectionItems.map((item) => {
                  const itemIndex = currentIndex++;
                  const isSelected = itemIndex === selectedIndex;

                  return (
                    <button
                      key={item.id}
                      data-index={itemIndex}
                      onClick={() => {
                        item.onSelect();
                        onClose();
                      }}
                      onMouseEnter={() => setSelectedIndex(itemIndex)}
                      className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
                        isSelected ? 'bg-primary-50 dark:bg-primary-900/30' : 'hover:bg-neutral-50 dark:hover:bg-neutral-800'
                      }`}
                    >
                      {/* Icon */}
                      {item.icon && (
                        <div className={`flex-shrink-0 ${isSelected ? 'text-primary-600 dark:text-primary-400' : 'text-neutral-400'}`}>
                          {item.icon}
                        </div>
                      )}

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-medium ${isSelected ? 'text-primary-700 dark:text-primary-300' : 'text-neutral-900 dark:text-neutral-100'}`}>
                          {item.label}
                        </div>
                        {item.description && (
                          <div className="text-xs text-neutral-500 dark:text-neutral-400 truncate">
                            {item.description}
                          </div>
                        )}
                      </div>

                      {/* Shortcut or Arrow */}
                      {item.shortcut ? (
                        <ShortcutKey shortcut={item.shortcut} />
                      ) : isSelected ? (
                        <ArrowRight className="h-4 w-4 text-primary-500 dark:text-primary-400" />
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 text-xs text-neutral-500 dark:text-neutral-400">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded text-[10px]">↑</kbd>
              <kbd className="px-1 py-0.5 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded text-[10px]">↓</kbd>
              <span className="ml-1">navigate</span>
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded text-[10px]">↵</kbd>
              <span className="ml-1">select</span>
            </span>
          </div>
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-white dark:bg-neutral-700 border border-neutral-200 dark:border-neutral-600 rounded text-[10px]">esc</kbd>
            <span className="ml-1">close</span>
          </span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Provider
// ============================================================================

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<CommandItem[]>([]);

  // Global keyboard shortcut (Cmd+K / Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(prev => !prev);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  const value = useMemo(() => ({ open, setOpen, items, setItems }), [open, items]);

  return (
    <CommandPaletteContext.Provider value={value}>
      {children}
      {open && items.length > 0 && (
        <CommandPalette items={items} onClose={() => setOpen(false)} />
      )}
    </CommandPaletteContext.Provider>
  );
}

// ============================================================================
// Hook to register commands
// ============================================================================

export function useRegisterCommands(commands: CommandItem[], deps: React.DependencyList = []) {
  const { setItems } = useCommandPalette();

  useEffect(() => {
    setItems(commands);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export default CommandPalette;
