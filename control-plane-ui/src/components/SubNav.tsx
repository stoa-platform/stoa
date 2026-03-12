/**
 * SubNav — Contextual sub-navigation tab bar (CAB-1785)
 *
 * Renders a horizontal tab bar below the page header to group related pages.
 * Uses React Router Links for actual navigation between routes.
 * Active tab is determined by matching the current pathname.
 *
 * Tab group definitions are in subNavGroups.ts (separate file to avoid
 * react-refresh/only-export-components warnings).
 */

import { type ComponentType } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { clsx } from 'clsx';

export interface SubNavTab {
  label: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
}

export interface SubNavProps {
  tabs: SubNavTab[];
}

/**
 * Matches the current pathname against a tab's href.
 * Exact match required to avoid /apis matching /api-traffic, etc.
 */
function isTabActive(pathname: string, href: string): boolean {
  return pathname === href || pathname === href + '/';
}

export function SubNav({ tabs }: SubNavProps) {
  const location = useLocation();

  return (
    <nav
      className="border-b border-neutral-200 dark:border-neutral-700 mb-6"
      aria-label="Sub-navigation"
    >
      <div className="-mb-px flex gap-1 overflow-x-auto">
        {tabs.map((tab) => {
          const active = isTabActive(location.pathname, tab.href);
          const Icon = tab.icon;
          return (
            <Link
              key={tab.href}
              to={tab.href}
              className={clsx(
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors',
                active
                  ? 'border-primary-600 text-primary-600 dark:text-primary-400 dark:border-primary-400'
                  : 'border-transparent text-neutral-500 dark:text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300 hover:border-neutral-300 dark:hover:border-neutral-600'
              )}
              aria-current={active ? 'page' : undefined}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
