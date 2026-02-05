import { useState, useCallback, useRef, useEffect } from 'react';
import { ChevronDown } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface CollapsibleProps {
  /** Header/trigger content */
  title: React.ReactNode;
  /** Collapsible content */
  children: React.ReactNode;
  /** Initial expanded state */
  defaultExpanded?: boolean;
  /** Controlled expanded state */
  expanded?: boolean;
  /** Callback when expanded state changes */
  onExpandedChange?: (expanded: boolean) => void;
  /** Additional class for the container */
  className?: string;
  /** Icon to show in header */
  icon?: React.ReactNode;
  /** Badge/count to show in header */
  badge?: React.ReactNode;
  /** Variant affects styling */
  variant?: 'default' | 'bordered' | 'filled';
}

// ============================================================================
// Component
// ============================================================================

export function Collapsible({
  title,
  children,
  defaultExpanded = false,
  expanded: controlledExpanded,
  onExpandedChange,
  className = '',
  icon,
  badge,
  variant = 'default',
}: CollapsibleProps) {
  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState<number | undefined>(undefined);

  // Use controlled or uncontrolled state
  const isControlled = controlledExpanded !== undefined;
  const isExpanded = isControlled ? controlledExpanded : internalExpanded;

  // Measure content height for smooth animation
  useEffect(() => {
    if (contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight);
    }
  }, [children, isExpanded]);

  const toggle = useCallback(() => {
    const newExpanded = !isExpanded;
    if (!isControlled) {
      setInternalExpanded(newExpanded);
    }
    onExpandedChange?.(newExpanded);
  }, [isExpanded, isControlled, onExpandedChange]);

  // Variant styles
  const variantStyles = {
    default: {
      container: '',
      header: 'py-3',
      content: 'pb-4',
    },
    bordered: {
      container: 'border border-neutral-200 rounded-lg',
      header: 'px-4 py-3',
      content: 'px-4 pb-4',
    },
    filled: {
      container: 'bg-neutral-50 rounded-lg',
      header: 'px-4 py-3',
      content: 'px-4 pb-4',
    },
  };

  const styles = variantStyles[variant];

  return (
    <div className={`${styles.container} ${className}`}>
      {/* Header/Trigger */}
      <button
        type="button"
        onClick={toggle}
        className={`w-full flex items-center justify-between text-left ${styles.header} hover:bg-neutral-50/50 transition-colors rounded-lg -mx-1 px-1`}
        aria-expanded={isExpanded}
      >
        <div className="flex items-center gap-3">
          {icon && (
            <span className="text-neutral-400">{icon}</span>
          )}
          <span className="font-medium text-neutral-900">{title}</span>
          {badge && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-neutral-100 text-neutral-600">
              {badge}
            </span>
          )}
        </div>
        <ChevronDown
          className={`h-5 w-5 text-neutral-400 transition-transform duration-200 ${
            isExpanded ? 'rotate-180' : ''
          }`}
        />
      </button>

      {/* Content with animation */}
      <div
        className="overflow-hidden transition-all duration-200 ease-in-out"
        style={{
          maxHeight: isExpanded ? contentHeight : 0,
          opacity: isExpanded ? 1 : 0,
        }}
      >
        <div ref={contentRef} className={styles.content}>
          {children}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Accordion (multiple collapsible sections, only one open at a time)
// ============================================================================

export interface AccordionItem {
  id: string;
  title: React.ReactNode;
  content: React.ReactNode;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
}

export interface AccordionProps {
  items: AccordionItem[];
  /** Allow multiple items to be expanded */
  allowMultiple?: boolean;
  /** Initially expanded item IDs */
  defaultExpandedIds?: string[];
  /** Variant affects styling */
  variant?: 'default' | 'bordered' | 'filled';
  /** Additional class for the container */
  className?: string;
}

export function Accordion({
  items,
  allowMultiple = false,
  defaultExpandedIds = [],
  variant = 'bordered',
  className = '',
}: AccordionProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(
    new Set(defaultExpandedIds)
  );

  const handleExpand = useCallback((id: string, expanded: boolean) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (expanded) {
        if (!allowMultiple) {
          next.clear();
        }
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }, [allowMultiple]);

  return (
    <div className={`space-y-2 ${className}`}>
      {items.map(item => (
        <Collapsible
          key={item.id}
          title={item.title}
          icon={item.icon}
          badge={item.badge}
          variant={variant}
          expanded={expandedIds.has(item.id)}
          onExpandedChange={(expanded) => handleExpand(item.id, expanded)}
        >
          {item.content}
        </Collapsible>
      ))}
    </div>
  );
}

export default Collapsible;
