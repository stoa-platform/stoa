/**
 * Notifications Center (CAB-1470)
 */

import { useState } from 'react';
import { Bell, CheckCheck, Mail, MailOpen, ExternalLink } from 'lucide-react';
import { useNotifications, useMarkAsRead, useMarkAllAsRead } from '../../hooks/useNotifications';
import { useAuth } from '../../contexts/AuthContext';
import type { Notification } from '../../types';

const TYPE_LABELS: Record<string, string> = {
  api_update: 'API Update',
  subscription_expiry: 'Subscription Expiry',
  key_rotation: 'Key Rotation',
  system_alert: 'System Alert',
  usage_threshold: 'Usage Threshold',
};

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: Notification;
  onMarkRead: (id: string) => void;
}) {
  return (
    <div
      className={`flex items-start gap-4 p-4 border-b border-neutral-200 dark:border-neutral-700 ${
        !notification.read
          ? 'bg-primary-50/50 dark:bg-primary-900/10'
          : 'bg-white dark:bg-neutral-800'
      }`}
    >
      <div className="flex-shrink-0 mt-0.5">
        {notification.read ? (
          <MailOpen className="w-5 h-5 text-neutral-400" />
        ) : (
          <Mail className="w-5 h-5 text-primary-500" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium text-neutral-900 dark:text-white truncate">
            {notification.title}
          </h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300">
            {TYPE_LABELS[notification.type] || notification.type}
          </span>
        </div>
        <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">
          {notification.message}
        </p>
        <div className="flex items-center gap-3 mt-2">
          <time className="text-xs text-neutral-400">
            {new Date(notification.created_at).toLocaleString()}
          </time>
          {notification.link && (
            <a
              href={notification.link}
              className="text-xs text-primary-600 dark:text-primary-400 hover:underline inline-flex items-center gap-1"
            >
              View details <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      </div>
      {!notification.read && (
        <button
          onClick={() => onMarkRead(notification.id)}
          className="text-xs text-primary-600 dark:text-primary-400 hover:underline whitespace-nowrap"
        >
          Mark read
        </button>
      )}
    </div>
  );
}

export function NotificationsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { data, isLoading } = useNotifications();
  const markAsRead = useMarkAsRead();
  const markAllAsRead = useMarkAllAsRead();
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  if (authLoading || !isAuthenticated) {
    return null;
  }

  const notifications = data?.notifications ?? [];
  const filtered = filter === 'unread' ? notifications.filter((n) => !n.read) : notifications;
  const unreadCount = data?.unread_count ?? 0;

  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Bell className="w-6 h-6 text-neutral-700 dark:text-neutral-200" />
            <div>
              <h1 className="text-2xl font-bold text-neutral-900 dark:text-white">Notifications</h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
              </p>
            </div>
          </div>
          {unreadCount > 0 && (
            <button
              onClick={() => markAllAsRead.mutate()}
              disabled={markAllAsRead.isPending}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-700 dark:text-primary-300 bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-700 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/30 transition-colors disabled:opacity-50"
            >
              <CheckCheck className="w-4 h-4" />
              Mark all read
            </button>
          )}
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 mb-4">
          {(['all', 'unread'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                filter === f
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                  : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700'
              }`}
            >
              {f === 'all' ? 'All' : `Unread (${unreadCount})`}
            </button>
          ))}
        </div>

        {/* List */}
        <div className="bg-white dark:bg-neutral-800 rounded-xl border border-neutral-200 dark:border-neutral-700 overflow-hidden">
          {isLoading ? (
            <div className="p-8 text-center text-neutral-400">Loading notifications...</div>
          ) : filtered.length === 0 ? (
            <div className="p-8 text-center text-neutral-400">
              {filter === 'unread' ? 'No unread notifications' : 'No notifications yet'}
            </div>
          ) : (
            filtered.map((n) => (
              <NotificationRow
                key={n.id}
                notification={n}
                onMarkRead={(id) => markAsRead.mutate(id)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default NotificationsPage;
