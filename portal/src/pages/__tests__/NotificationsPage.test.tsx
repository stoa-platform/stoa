/**
 * NotificationsPage Tests - CAB-1470
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { NotificationsPage } from '../notifications/NotificationsPage';

const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../i18n', () => ({
  loadNamespace: vi.fn(),
  LANGUAGE_KEY: 'stoa:language',
}));

vi.mock('../../config', () => ({
  config: {
    features: { enableI18n: false },
  },
}));

const mockNotificationsData = vi.fn();
const mockMarkAsRead = vi.fn();
const mockMarkAllAsRead = vi.fn();
const mockMarkAllIsPending = vi.fn();

vi.mock('../../hooks/useNotifications', () => ({
  useNotifications: () => ({
    data: mockNotificationsData(),
    isLoading: false,
  }),
  useMarkAsRead: () => ({
    mutate: mockMarkAsRead,
  }),
  useMarkAllAsRead: () => ({
    mutate: mockMarkAllAsRead,
    isPending: mockMarkAllIsPending(),
  }),
  useUnreadCount: () => ({
    data: { count: 0 },
  }),
}));

const sampleNotifications = [
  {
    id: 'n1',
    type: 'api_update',
    title: 'API v2 Released',
    message: 'The Payment API has been updated to v2.',
    read: false,
    created_at: '2026-02-25T10:00:00Z',
    link: '/apis/payment',
  },
  {
    id: 'n2',
    type: 'subscription_expiry',
    title: 'Subscription Expiring',
    message: 'Your Maps API subscription expires in 7 days.',
    read: true,
    created_at: '2026-02-24T08:00:00Z',
    link: null,
  },
];

describe('NotificationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
    mockNotificationsData.mockReturnValue({
      notifications: sampleNotifications,
      unread_count: 1,
    });
    mockMarkAllIsPending.mockReturnValue(false);
  });

  it('renders the page heading and subtitle', async () => {
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Notifications')).toBeInTheDocument();
    });
    expect(screen.getByText('1 unread')).toBeInTheDocument();
  });

  it('shows "All caught up" when no unread', async () => {
    mockNotificationsData.mockReturnValue({
      notifications: [sampleNotifications[1]],
      unread_count: 0,
    });
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('All caught up')).toBeInTheDocument();
    });
  });

  it('renders notification items', async () => {
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('API v2 Released')).toBeInTheDocument();
    });
    expect(screen.getByText('Subscription Expiring')).toBeInTheDocument();
    expect(screen.getByText('API Update')).toBeInTheDocument();
  });

  it('shows Mark all read button when unread > 0', async () => {
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Mark all read')).toBeInTheDocument();
    });
  });

  it('hides Mark all read button when no unread', async () => {
    mockNotificationsData.mockReturnValue({
      notifications: [sampleNotifications[1]],
      unread_count: 0,
    });
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Notifications')).toBeInTheDocument();
    });
    expect(screen.queryByText('Mark all read')).not.toBeInTheDocument();
  });

  it('shows empty state when no notifications', async () => {
    mockNotificationsData.mockReturnValue({ notifications: [], unread_count: 0 });
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('No notifications yet')).toBeInTheDocument();
    });
  });

  it('shows filter tabs', async () => {
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('All')).toBeInTheDocument();
    });
    expect(screen.getByText('Unread (1)')).toBeInTheDocument();
  });

  it('filters to unread on tab click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Unread (1)')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Unread (1)'));
    expect(screen.getByText('API v2 Released')).toBeInTheDocument();
    expect(screen.queryByText('Subscription Expiring')).not.toBeInTheDocument();
  });

  it('shows Mark read button on unread notifications', async () => {
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Mark read')).toBeInTheDocument();
    });
  });

  it('calls markAsRead on button click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Mark read')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Mark read'));
    expect(mockMarkAsRead).toHaveBeenCalledWith('n1');
  });

  it('calls markAllAsRead on button click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<NotificationsPage />);
    await waitFor(() => {
      expect(screen.getByText('Mark all read')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Mark all read'));
    expect(mockMarkAllAsRead).toHaveBeenCalled();
  });

  it('returns null when not authenticated', () => {
    mockAuth.mockReturnValue({
      ...createAuthMock('cpi-admin'),
      isAuthenticated: false,
      isLoading: false,
    });
    const { container } = renderWithProviders(<NotificationsPage />);
    expect(container.innerHTML).toBe('');
  });

  describe('Persona-based Tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(personas)('%s can access notifications page', async (persona) => {
      mockAuth.mockReturnValue(createAuthMock(persona));
      renderWithProviders(<NotificationsPage />);
      await waitFor(() => {
        expect(screen.getByText('Notifications')).toBeInTheDocument();
      });
    });
  });
});
