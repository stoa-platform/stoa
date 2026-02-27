import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { notificationsService } from './notifications';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from './api';

const mockGet = apiClient.get as Mock;
const mockPatch = apiClient.patch as Mock;
const mockPost = apiClient.post as Mock;

describe('notificationsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getNotifications', () => {
    it('returns notifications from the API', async () => {
      const mockData = {
        notifications: [{ id: 'n-1', title: 'New API', read: false }],
        total: 1,
        unread_count: 1,
      };
      mockGet.mockResolvedValueOnce({ data: mockData });

      const result = await notificationsService.getNotifications();

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/notifications');
      expect(result).toEqual(mockData);
    });

    it('returns fallback on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));

      const result = await notificationsService.getNotifications();

      expect(result).toEqual({ notifications: [], total: 0, unread_count: 0 });
    });
  });

  describe('getUnreadCount', () => {
    it('returns unread count from the API', async () => {
      mockGet.mockResolvedValueOnce({ data: { unread_count: 3 } });

      const result = await notificationsService.getUnreadCount();

      expect(mockGet).toHaveBeenCalledWith('/v1/portal/notifications/unread-count');
      expect(result).toBe(3);
    });

    it('returns 0 on error', async () => {
      mockGet.mockRejectedValueOnce(new Error('Network error'));

      const result = await notificationsService.getUnreadCount();

      expect(result).toBe(0);
    });
  });

  describe('markAsRead', () => {
    it('patches a notification as read', async () => {
      mockPatch.mockResolvedValueOnce({});

      await notificationsService.markAsRead('n-1');

      expect(mockPatch).toHaveBeenCalledWith('/v1/portal/notifications/n-1/read');
    });
  });

  describe('markAllAsRead', () => {
    it('posts to mark all notifications as read', async () => {
      mockPost.mockResolvedValueOnce({});

      await notificationsService.markAllAsRead();

      expect(mockPost).toHaveBeenCalledWith('/v1/portal/notifications/mark-all-read');
    });
  });
});
