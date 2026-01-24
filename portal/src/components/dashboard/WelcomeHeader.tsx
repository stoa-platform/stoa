/**
 * WelcomeHeader Component (CAB-299)
 *
 * Greeting banner with user name and time-based message.
 */

import { Sparkles } from 'lucide-react';
import type { User } from '../../types';

interface WelcomeHeaderProps {
  user: User | null;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function WelcomeHeader({ user }: WelcomeHeaderProps) {
  const firstName = user?.name?.split(' ')[0] || 'Developer';
  const greeting = getGreeting();

  return (
    <div className="relative overflow-hidden bg-gradient-to-r from-primary-600 via-primary-500 to-accent-500 rounded-2xl p-8">
      {/* Background decoration */}
      <div className="absolute top-0 right-0 -mt-4 -mr-4 w-40 h-40 bg-white/10 rounded-full blur-3xl" />
      <div className="absolute bottom-0 left-0 -mb-8 -ml-8 w-32 h-32 bg-accent-400/20 rounded-full blur-2xl" />

      <div className="relative">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="h-5 w-5 text-amber-300" />
          <span className="text-primary-100 text-sm font-medium">
            STOA Developer Portal
          </span>
        </div>

        <h1 className="text-3xl sm:text-4xl font-bold text-white mb-2">
          {greeting}, {firstName}!
        </h1>

        <p className="text-primary-100 text-lg max-w-xl">
          Discover AI-powered tools, manage your subscriptions, and build amazing integrations.
        </p>
      </div>
    </div>
  );
}

export default WelcomeHeader;
