import { Link } from 'react-router-dom';
import { Wrench, CreditCard, BookOpen, ArrowRight, Zap, Shield, Code, AppWindow } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { config } from '../config';

export function HomePage() {
  const { user } = useAuth();

  const features = [
    {
      icon: Wrench,
      title: 'MCP Tools',
      description: 'Discover and use AI-powered tools through the Model Context Protocol',
      href: '/tools',
      enabled: config.features.enableMCPTools,
    },
    {
      icon: BookOpen,
      title: 'API Catalog',
      description: 'Browse available APIs and integrate them into your applications',
      href: '/apis',
      enabled: config.features.enableAPICatalog,
    },
    {
      icon: AppWindow,
      title: 'My Applications',
      description: 'Create and manage your consumer applications with API credentials',
      href: '/apps',
      enabled: config.features.enableApplications,
    },
    {
      icon: CreditCard,
      title: 'My Subscriptions',
      description: 'Manage your tool and API subscriptions, monitor usage',
      href: '/subscriptions',
      enabled: config.features.enableSubscriptions,
    },
  ].filter(f => f.enabled);

  const highlights = [
    {
      icon: Zap,
      title: 'Fast Integration',
      description: 'Get up and running in minutes with our SDKs and documentation',
    },
    {
      icon: Shield,
      title: 'Enterprise Security',
      description: 'OAuth 2.0, OIDC, and fine-grained access control built-in',
    },
    {
      icon: Code,
      title: 'Developer First',
      description: 'Comprehensive APIs, webhooks, and real-time events',
    },
  ];

  return (
    <div className="space-y-8">
      {/* Welcome Banner */}
      <div className="bg-gradient-to-r from-primary-600 to-accent-600 rounded-xl p-8 text-white">
        <h1 className="text-3xl font-bold mb-2">
          Welcome back, {user?.name?.split(' ')[0] || 'Developer'}!
        </h1>
        <p className="text-primary-100 text-lg mb-6">
          Explore our tools and APIs to build powerful integrations.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/tools"
            className="inline-flex items-center gap-2 px-4 py-2 bg-white text-primary-700 rounded-lg font-medium hover:bg-primary-50 transition-colors"
          >
            Browse MCP Tools
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href={config.services.docs.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-700 text-white rounded-lg font-medium hover:bg-primary-800 transition-colors"
          >
            View Documentation
          </a>
        </div>
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {features.map((feature) => (
            <Link
              key={feature.title}
              to={feature.href}
              className="group bg-white rounded-lg border border-gray-200 p-6 hover:border-primary-300 hover:shadow-md transition-all"
            >
              <div className="flex items-start gap-4">
                <div className="p-3 bg-primary-50 rounded-lg group-hover:bg-primary-100 transition-colors">
                  <feature.icon className="h-6 w-6 text-primary-600" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-900 group-hover:text-primary-700 transition-colors">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-gray-500 mt-1">{feature.description}</p>
                </div>
                <ArrowRight className="h-5 w-5 text-gray-400 group-hover:text-primary-600 transition-colors" />
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Platform Highlights */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-6">Platform Highlights</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {highlights.map((highlight) => (
            <div key={highlight.title} className="text-center">
              <div className="inline-flex p-3 bg-gray-100 rounded-full mb-4">
                <highlight.icon className="h-6 w-6 text-gray-600" />
              </div>
              <h3 className="font-medium text-gray-900 mb-2">{highlight.title}</h3>
              <p className="text-sm text-gray-500">{highlight.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Getting Started */}
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg border border-gray-200 p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Getting Started</h2>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-medium text-sm">
              1
            </div>
            <p className="text-gray-700">Browse the MCP Tools catalog to find tools that fit your needs</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-medium text-sm">
              2
            </div>
            <p className="text-gray-700">Subscribe to tools and get your API credentials</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-medium text-sm">
              3
            </div>
            <p className="text-gray-700">Integrate using our SDKs or direct API calls</p>
          </div>
        </div>
      </div>
    </div>
  );
}
