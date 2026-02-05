import { ReactNode } from 'react';
import { Plus, Search, FileText, Server, Layers, Wrench, Rocket, Users, Package } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export type EmptyStateVariant =
  | 'default'
  | 'search'
  | 'apis'
  | 'tools'
  | 'servers'
  | 'deployments'
  | 'users'
  | 'subscriptions';

export interface EmptyStateProps {
  /** Variant determines the illustration and default messaging */
  variant?: EmptyStateVariant;
  /** Custom title (overrides variant default) */
  title?: string;
  /** Custom description (overrides variant default) */
  description?: string;
  /** Custom illustration (overrides variant default) */
  illustration?: ReactNode;
  /** Primary action button */
  action?: {
    label: string;
    onClick: () => void;
    icon?: ReactNode;
  };
  /** Secondary action link */
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  /** Additional class for styling */
  className?: string;
  /** Compact mode for inline use */
  compact?: boolean;
}

// ============================================================================
// Illustrations (SVG-based for crisp rendering)
// ============================================================================

function DefaultIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-neutral-100 to-neutral-200 dark:from-neutral-800 dark:to-neutral-700 flex items-center justify-center">
        <FileText className="w-10 h-10 text-neutral-400" />
      </div>
      <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-lg bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
        <Plus className="w-4 h-4 text-primary-600 dark:text-primary-400" />
      </div>
    </div>
  );
}

function SearchIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-full bg-gradient-to-br from-neutral-100 to-neutral-200 dark:from-neutral-800 dark:to-neutral-700 flex items-center justify-center">
        <Search className="w-10 h-10 text-neutral-400" />
      </div>
      <div className="absolute top-0 right-0 w-6 h-6 rounded-full bg-warning-100 dark:bg-warning-900 flex items-center justify-center">
        <span className="text-warning-600 dark:text-warning-400 text-xs font-bold">?</span>
      </div>
    </div>
  );
}

function APIsIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-primary-50 to-primary-100 flex items-center justify-center">
        <Layers className="w-10 h-10 text-primary-500" />
      </div>
      <div className="absolute -bottom-2 -right-2 flex -space-x-1">
        <div className="w-6 h-6 rounded-full bg-success-100 border-2 border-white" />
        <div className="w-6 h-6 rounded-full bg-primary-100 border-2 border-white" />
        <div className="w-6 h-6 rounded-full bg-accent-100 border-2 border-white" />
      </div>
    </div>
  );
}

function ToolsIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-warning-50 to-warning-100 flex items-center justify-center">
        <Wrench className="w-10 h-10 text-warning-500" />
      </div>
      <div className="absolute -top-1 -right-1 w-8 h-8 rounded-lg bg-success-100 flex items-center justify-center animate-pulse">
        <span className="text-success-600 text-lg">✨</span>
      </div>
    </div>
  );
}

function ServersIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-accent-50 to-accent-100 flex items-center justify-center">
        <Server className="w-10 h-10 text-accent-500" />
      </div>
      <div className="absolute bottom-2 left-2 w-3 h-3 rounded-full bg-neutral-300 animate-pulse" />
      <div className="absolute bottom-2 left-7 w-3 h-3 rounded-full bg-neutral-300 animate-pulse" style={{ animationDelay: '0.2s' }} />
      <div className="absolute bottom-2 left-12 w-3 h-3 rounded-full bg-neutral-300 animate-pulse" style={{ animationDelay: '0.4s' }} />
    </div>
  );
}

function DeploymentsIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-success-50 to-success-100 flex items-center justify-center">
        <Rocket className="w-10 h-10 text-success-500 transform -rotate-45" />
      </div>
      <div className="absolute -top-2 right-4 text-lg">🚀</div>
    </div>
  );
}

function UsersIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-purple-50 to-purple-100 flex items-center justify-center">
        <Users className="w-10 h-10 text-purple-500" />
      </div>
    </div>
  );
}

function SubscriptionsIllustration() {
  return (
    <div className="relative">
      <div className="w-24 h-24 rounded-2xl bg-gradient-to-br from-primary-50 to-accent-50 flex items-center justify-center">
        <Package className="w-10 h-10 text-primary-500" />
      </div>
      <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-lg bg-success-500 flex items-center justify-center text-white text-xs font-bold">
        +
      </div>
    </div>
  );
}

// ============================================================================
// Variant Configurations
// ============================================================================

const variantConfig: Record<EmptyStateVariant, {
  illustration: ReactNode;
  title: string;
  description: string;
}> = {
  default: {
    illustration: <DefaultIllustration />,
    title: 'Nothing here yet',
    description: 'Get started by creating your first item.',
  },
  search: {
    illustration: <SearchIllustration />,
    title: 'No results found',
    description: 'Try adjusting your search or filters to find what you\'re looking for.',
  },
  apis: {
    illustration: <APIsIllustration />,
    title: 'No APIs yet',
    description: 'Create your first API to start managing your endpoints.',
  },
  tools: {
    illustration: <ToolsIllustration />,
    title: 'No tools available',
    description: 'Browse the catalog to discover and subscribe to AI tools.',
  },
  servers: {
    illustration: <ServersIllustration />,
    title: 'No servers registered',
    description: 'Connect your first MCP server to start proxying tools through STOA.',
  },
  deployments: {
    illustration: <DeploymentsIllustration />,
    title: 'No deployments yet',
    description: 'Deploy your first API to see it here.',
  },
  users: {
    illustration: <UsersIllustration />,
    title: 'No users found',
    description: 'Users will appear here once they sign up.',
  },
  subscriptions: {
    illustration: <SubscriptionsIllustration />,
    title: 'No subscriptions yet',
    description: 'Subscribe to tools to start using them in your applications.',
  },
};

// ============================================================================
// Component
// ============================================================================

export function EmptyState({
  variant = 'default',
  title,
  description,
  illustration,
  action,
  secondaryAction,
  className = '',
  compact = false,
}: EmptyStateProps) {
  const config = variantConfig[variant];

  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${
        compact ? 'py-8' : 'py-16'
      } ${className}`}
    >
      {/* Illustration */}
      <div className={compact ? 'mb-4' : 'mb-6'}>
        {illustration || config.illustration}
      </div>

      {/* Title */}
      <h3
        className={`font-semibold text-neutral-900 dark:text-neutral-100 ${
          compact ? 'text-base' : 'text-lg'
        }`}
      >
        {title || config.title}
      </h3>

      {/* Description */}
      <p
        className={`text-neutral-500 dark:text-neutral-400 max-w-sm ${
          compact ? 'text-sm mt-1' : 'mt-2'
        }`}
      >
        {description || config.description}
      </p>

      {/* Actions */}
      {(action || secondaryAction) && (
        <div className={`flex flex-col sm:flex-row items-center gap-3 ${compact ? 'mt-4' : 'mt-6'}`}>
          {action && (
            <button
              onClick={action.onClick}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 dark:bg-primary-500 dark:hover:bg-primary-600 transition-colors"
            >
              {action.icon || <Plus className="w-4 h-4" />}
              {action.label}
            </button>
          )}
          {secondaryAction && (
            <button
              onClick={secondaryAction.onClick}
              className="text-sm text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium"
            >
              {secondaryAction.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default EmptyState;
