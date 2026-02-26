/**
 * Notifications Service (CAB-1470)
 */

import { apiClient } from './api';
import type { NotificationsResponse } from '../types';

async function getNotifications(): Promise<NotificationsResponse> {
  try {
    const response = await apiClient.get<NotificationsResponse>('/v1/portal/notifications');
    return response.data;
  } catch {
    console.warn('Notifications endpoint not available, using fallback');
    return {
      notifications: [],
      total: 0,
      unread_count: 0,
    };
  }
}

async function getUnreadCount(): Promise<number> {
  try {
    const response = await apiClient.get<{ unread_count: number }>(
      '/v1/portal/notifications/unread-count'
    );
    return response.data.unread_count;
  } catch {
    return 0;
  }
}

async function markAsRead(notificationId: string): Promise<void> {
  await apiClient.patch(`/v1/portal/notifications/${notificationId}/read`);
}

async function markAllAsRead(): Promise<void> {
  await apiClient.post('/v1/portal/notifications/mark-all-read');
}

export const notificationsService = {
  getNotifications,
  getUnreadCount,
  markAsRead,
  markAllAsRead,
};
