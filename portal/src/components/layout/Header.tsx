import { useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Menu, Bell, User, LogOut, ExternalLink } from 'lucide-react';
import { StoaLogo } from '@stoa/shared/components/StoaLogo';
import { ThemeToggle } from '@stoa/shared/components/ThemeToggle';
import { useAuth } from '../../contexts/AuthContext';
import { config } from '../../config';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Close user menu on outside click
  useEffect(() => {
    if (!userMenuOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [userMenuOpen]);

  return (
    <header className="bg-white dark:bg-neutral-900 border-b border-gray-200 dark:border-neutral-800 sticky top-0 z-30 transition-colors">
      <div className="flex items-center justify-between h-16 px-4 sm:px-6 lg:px-8">
        {/* Left: Menu button + Logo */}
        <div className="flex items-center gap-4">
          <button
            onClick={onMenuClick}
            className="lg:hidden p-2.5 text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
            aria-label="Open menu"
          >
            <Menu className="h-6 w-6" aria-hidden="true" />
          </button>

          <Link to="/" className="flex items-center gap-3">
            <StoaLogo size="sm" />
            <div className="hidden sm:block">
              <h1 className="text-lg font-semibold text-gray-900 dark:text-white">STOA</h1>
              <p className="text-xs text-gray-500 dark:text-neutral-400 -mt-1">Developer Portal</p>
            </div>
          </Link>
        </div>

        {/* Center: Search (future) */}
        <div className="hidden md:flex flex-1 max-w-lg mx-8">
          {/* Placeholder for search - can be implemented later */}
        </div>

        {/* Right: Actions + User */}
        <div className="flex items-center gap-2">
          {/* Console link */}
          <a
            href={config.services.console.url}
            target="_blank"
            rel="noopener noreferrer"
            className="hidden sm:flex items-center gap-1 px-3 py-2 text-sm text-gray-600 dark:text-neutral-400 hover:text-gray-900 dark:hover:text-neutral-100 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
          >
            <span>Console</span>
            <ExternalLink className="h-3 w-3" aria-hidden="true" />
            <span className="sr-only">(opens in new tab)</span>
          </a>

          {/* Theme toggle */}
          <ThemeToggle size="md" />

          {/* Notifications */}
          <button
            className="p-2.5 text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md relative transition-colors"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" aria-hidden="true" />
          </button>

          {/* User menu */}
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2 p-2.5 hover:bg-gray-100 dark:hover:bg-neutral-800 rounded-md transition-colors"
              aria-label="User menu"
              aria-haspopup="true"
              aria-expanded={userMenuOpen}
            >
              <div className="w-8 h-8 bg-primary-100 dark:bg-primary-900/30 rounded-full flex items-center justify-center">
                <User
                  className="h-4 w-4 text-primary-600 dark:text-primary-400"
                  aria-hidden="true"
                />
              </div>
              <span className="hidden sm:block text-sm font-medium text-gray-700 dark:text-neutral-300">
                {user?.name || 'User'}
              </span>
            </button>

            {/* Dropdown */}
            {userMenuOpen && (
              <div className="absolute right-0 mt-1 w-56 bg-white dark:bg-neutral-800 rounded-md shadow-lg border border-gray-200 dark:border-neutral-700">
                <div className="px-4 py-3 border-b border-gray-100 dark:border-neutral-700">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">{user?.name}</p>
                  <p className="text-xs text-gray-500 dark:text-neutral-400 truncate">
                    {user?.email}
                  </p>
                </div>
                <div className="py-1">
                  <Link
                    to="/profile"
                    onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-700"
                  >
                    <User className="h-4 w-4" aria-hidden="true" />
                    My Profile
                  </Link>
                  <button
                    onClick={() => {
                      setUserMenuOpen(false);
                      logout();
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                  >
                    <LogOut className="h-4 w-4" aria-hidden="true" />
                    Sign out
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
