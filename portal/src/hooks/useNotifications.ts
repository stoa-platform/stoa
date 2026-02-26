/**
 * Notifications Hooks (CAB-1470)
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notificationsService } from '../services/notifications';
import { useAuth } from '../contexts/AuthContext';
import type { NotificationsResponse } from '../types';

export function useNotifications() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<NotificationsResponse>({
    queryKey: ['notifications'],
    queryFn: () => notificationsService.getNotifications(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 30 * 1000,
  });
}

export function useUnreadCount() {
  const { isAuthenticated, accessToken } = useAuth();

  return useQuery<number>({
    queryKey: ['notifications-unread-count'],
    queryFn: () => notificationsService.getUnreadCount(),
    enabled: isAuthenticated && !!accessToken,
    staleTime: 15 * 1000,
    refetchInterval: 60 * 1000,
  });
}

export function useMarkAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (notificationId: string) => notificationsService.markAsRead(notificationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      void queryClient.invalidateQueries({ queryKey: ['notifications-unread-count'] });
    },
  });
}

export function useMarkAllAsRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => notificationsService.markAllAsRead(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      void queryClient.invalidateQueries({ queryKey: ['notifications-unread-count'] });
    },
  });
}
