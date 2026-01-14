/**
 * QuickActions Component (CAB-299)
 *
 * Quick action buttons for common tasks.
 */

import { Link } from 'react-router-dom';
import {
  Wrench,
  BarChart3,
  CreditCard,
  BookOpen,
  ArrowRight,
  ExternalLink,
} from 'lucide-react';
import { config } from '../../config';

interface QuickAction {
  title: string;
  description: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  external?: boolean;
  enabled?: boolean;
}

const actions: QuickAction[] = [
  {
    title: 'Browse Tools',
    description: 'Discover AI-powered MCP tools',
    href: '/tools',
    icon: Wrench,
    color: 'from-primary-500 to-primary-600',
    enabled: config.features.enableMCPTools,
  },
  {
    title: 'View Usage',
    description: 'Monitor your API consumption',
    href: '/usage',
    icon: BarChart3,
    color: 'from-cyan-500 to-cyan-600',
    enabled: config.features.enableSubscriptions,
  },
  {
    title: 'My Subscriptions',
    description: 'Manage your tool subscriptions',
    href: '/subscriptions',
    icon: CreditCard,
    color: 'from-emerald-500 to-emerald-600',
    enabled: config.features.enableSubscriptions,
  },
  {
    title: 'Documentation',
    description: 'Read the developer docs',
    href: config.services.docs.url,
    icon: BookOpen,
    color: 'from-purple-500 to-purple-600',
    external: true,
  },
];

export function QuickActions() {
  const enabledActions = actions.filter(a => a.enabled !== false);

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {enabledActions.map((action) => {
          const Icon = action.icon;
          const content = (
            <div className="group relative bg-white rounded-xl border border-gray-200 p-5 hover:border-gray-300 hover:shadow-md transition-all overflow-hidden">
              {/* Gradient accent */}
              <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${action.color}`} />

              <div className="flex items-start gap-4">
                <div className={`p-2.5 rounded-lg bg-gradient-to-br ${action.color} text-white shadow-sm`}>
                  <Icon className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-gray-900 group-hover:text-primary-600 transition-colors flex items-center gap-1">
                    {action.title}
                    {action.external && (
                      <ExternalLink className="h-3 w-3 text-gray-400" />
                    )}
                  </h3>
                  <p className="text-sm text-gray-500 mt-0.5">{action.description}</p>
                </div>
                <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-primary-500 group-hover:translate-x-1 transition-all flex-shrink-0" />
              </div>
            </div>
          );

          if (action.external) {
            return (
              <a
                key={action.title}
                href={action.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {content}
              </a>
            );
          }

          return (
            <Link key={action.title} to={action.href}>
              {content}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default QuickActions;
