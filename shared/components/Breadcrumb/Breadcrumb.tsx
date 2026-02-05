import React from 'react';
import { ChevronRight, Home } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface BreadcrumbItem {
  label: string;
  href?: string;
  icon?: React.ReactNode;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
  /** Show home icon as first item */
  showHome?: boolean;
  /** Custom separator */
  separator?: React.ReactNode;
  /** Additional className */
  className?: string;
  /** Navigation function (for React Router integration) */
  onNavigate?: (href: string) => void;
}

// ============================================================================
// Component
// ============================================================================

export function Breadcrumb({
  items,
  showHome = true,
  separator,
  className = '',
  onNavigate,
}: BreadcrumbProps) {
  const allItems = showHome
    ? [{ label: 'Home', href: '/', icon: <Home className="h-4 w-4" /> }, ...items]
    : items;

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>, href?: string) => {
    if (href && onNavigate) {
      e.preventDefault();
      onNavigate(href);
    }
  };

  return (
    <nav aria-label="Breadcrumb" className={`flex items-center ${className}`}>
      <ol className="flex items-center gap-1.5 text-sm">
        {allItems.map((item, index) => {
          const isLast = index === allItems.length - 1;
          const isFirst = index === 0;

          return (
            <li key={index} className="flex items-center gap-1.5">
              {/* Separator (not on first item) */}
              {!isFirst && (
                <span className="text-neutral-300" aria-hidden="true">
                  {separator || <ChevronRight className="h-4 w-4" />}
                </span>
              )}

              {/* Breadcrumb item */}
              {isLast ? (
                // Current page (not a link)
                <span
                  className="font-medium text-neutral-900 flex items-center gap-1.5"
                  aria-current="page"
                >
                  {item.icon}
                  <span className={item.icon && !isFirst ? '' : ''}>{item.label}</span>
                </span>
              ) : (
                // Link to previous page
                <a
                  href={item.href || '#'}
                  onClick={(e) => handleClick(e, item.href)}
                  className="text-neutral-500 hover:text-neutral-700 flex items-center gap-1.5 transition-colors"
                >
                  {item.icon}
                  {/* Hide label on home icon for cleaner look */}
                  {!(isFirst && showHome && item.icon) && <span>{item.label}</span>}
                </a>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// ============================================================================
// Simplified API for common use case
// ============================================================================

export interface SimpleBreadcrumbProps {
  /** Array of labels, last one is current page */
  path: string[];
  /** Base href (default: /) */
  baseHref?: string;
  /** Additional className */
  className?: string;
  /** Navigation function */
  onNavigate?: (href: string) => void;
}

/**
 * Simplified breadcrumb for common use cases
 * @example
 * <SimpleBreadcrumb path={['APIs', 'Payment API']} />
 * // Renders: Home > APIs > Payment API
 */
export function SimpleBreadcrumb({
  path,
  baseHref = '/',
  className,
  onNavigate,
}: SimpleBreadcrumbProps) {
  const items: BreadcrumbItem[] = path.map((label, index) => {
    // Generate href based on path position
    // e.g., ['APIs', 'Payment API'] -> /apis, /apis/payment-api
    const segments = path.slice(0, index + 1).map((s) =>
      s.toLowerCase().replace(/\s+/g, '-')
    );
    const href = index === path.length - 1 ? undefined : `${baseHref}${segments.join('/')}`;

    return { label, href };
  });

  return (
    <Breadcrumb
      items={items}
      className={className}
      onNavigate={onNavigate}
    />
  );
}

export default Breadcrumb;
