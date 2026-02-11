/**
 * WebhooksPage Tests - CAB-1133
 *
 * Tests for webhook management page.
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { WebhooksPage } from '../webhooks/WebhooksPage';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock useWebhooks hooks
const mockUseWebhooks = vi.fn();
const mockUseCreateWebhook = vi.fn();
const mockUseUpdateWebhook = vi.fn();
const mockUseDeleteWebhook = vi.fn();
const mockUseTestWebhook = vi.fn();
const mockUseWebhookDeliveries = vi.fn();
const mockUseRetryDelivery = vi.fn();

vi.mock('../../hooks/useWebhooks', () => ({
  useWebhooks: (tenantId: string) => mockUseWebhooks(tenantId),
  useCreateWebhook: () => mockUseCreateWebhook(),
  useUpdateWebhook: () => mockUseUpdateWebhook(),
  useDeleteWebhook: () => mockUseDeleteWebhook(),
  useTestWebhook: () => mockUseTestWebhook(),
  useWebhookDeliveries: (tenantId: string, webhookId: string) =>
    mockUseWebhookDeliveries(tenantId, webhookId),
  useRetryDelivery: () => mockUseRetryDelivery(),
}));

// Mock Toast
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: mockToastSuccess,
    error: mockToastError,
  }),
}));

// Mock ConfirmDialog
vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  ConfirmDialog: ({
    open,
    title,
    confirmLabel,
  }: {
    open: boolean;
    title: string;
    confirmLabel: string;
  }) =>
    open ? (
      <div data-testid="confirm-dialog">
        <h2>{title}</h2>
        <button>{confirmLabel}</button>
      </div>
    ) : null,
}));

describe('WebhooksPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCreateWebhook.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseUpdateWebhook.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseDeleteWebhook.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseTestWebhook.mockReturnValue({ mutateAsync: vi.fn() });
    mockUseWebhookDeliveries.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseRetryDelivery.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  });

  describe('No tenant ID - non-admin', () => {
    it('shows "Tenant Required" warning when user has no tenant_id and is not admin', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: null, is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({ data: null, isLoading: false, isError: false });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        expect(screen.getByText('Tenant Required')).toBeInTheDocument();
        expect(
          screen.getByText(/You need to be associated with a tenant to manage webhooks/)
        ).toBeInTheDocument();
      });
    });
  });

  describe('No tenant ID - admin', () => {
    it('shows tenant ID input form when admin has no tenant_id', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'admin@example.com', tenant_id: null, is_admin: true, roles: ['cpi-admin'] },
      });
      mockUseWebhooks.mockReturnValue({ data: null, isLoading: false, isError: false });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        expect(screen.getByText('Webhook Management')).toBeInTheDocument();
        expect(screen.getByPlaceholderText(/Enter tenant ID/)).toBeInTheDocument();
        expect(screen.getByText('Load Webhooks')).toBeInTheDocument();
      });
    });
  });

  describe('With tenant ID', () => {
    it('renders "Webhook Notifications" heading', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: { items: [] },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        expect(screen.getByText('Webhook Notifications')).toBeInTheDocument();
      });
    });

    it('renders "Add Webhook" button', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: { items: [] },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        expect(screen.getAllByText('Add Webhook')[0]).toBeInTheDocument();
      });
    });

    it('shows loading state', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: null,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      });

      const { container } = renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        const spinner = container.querySelector('.animate-spin');
        expect(spinner).toBeInTheDocument();
      });
    });

    it('shows error state with "Try again" button', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: null,
        isLoading: false,
        isError: true,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        expect(screen.getByText('Failed to load webhooks')).toBeInTheDocument();
        expect(screen.getByText('Try again')).toBeInTheDocument();
      });
    });

    it('shows empty state when no webhooks configured', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: { items: [] },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        expect(screen.getByText('No webhooks configured')).toBeInTheDocument();
        expect(
          screen.getByText(
            'Create your first webhook to start receiving subscription event notifications.'
          )
        ).toBeInTheDocument();
      });
    });

    it('renders webhook card with name, URL, events, and status badge', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: {
          items: [
            {
              id: 'wh-1',
              tenant_id: 'tenant-1',
              name: 'Slack Notifications',
              url: 'https://hooks.slack.com/services/xxx',
              events: ['subscription.created', 'subscription.approved'],
              has_secret: true,
              enabled: true,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-02-01T00:00:00Z',
              headers: {},
            },
          ],
        },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        expect(screen.getByText('Slack Notifications')).toBeInTheDocument();
        expect(screen.getByText('https://hooks.slack.com/services/xxx')).toBeInTheDocument();
        expect(screen.getByText('subscription.created')).toBeInTheDocument();
        expect(screen.getByText('subscription.approved')).toBeInTheDocument();
        expect(screen.getByText('Active')).toBeInTheDocument();
        expect(screen.getByText('Signed')).toBeInTheDocument();
      });
    });

    it('renders toggle enabled/disabled button', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: {
          items: [
            {
              id: 'wh-1',
              tenant_id: 'tenant-1',
              name: 'Test Webhook',
              url: 'https://example.com/webhook',
              events: ['*'],
              has_secret: false,
              enabled: true,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-02-01T00:00:00Z',
              headers: {},
            },
          ],
        },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        const toggleButton = screen.getByTitle('Disable webhook');
        expect(toggleButton).toBeInTheDocument();
      });
    });

    it('renders test button (play icon)', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: {
          items: [
            {
              id: 'wh-1',
              tenant_id: 'tenant-1',
              name: 'Test Webhook',
              url: 'https://example.com/webhook',
              events: ['*'],
              has_secret: false,
              enabled: true,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-02-01T00:00:00Z',
              headers: {},
            },
          ],
        },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        const testButton = screen.getByTitle('Send test event');
        expect(testButton).toBeInTheDocument();
      });
    });

    it('renders delete button', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: {
          items: [
            {
              id: 'wh-1',
              tenant_id: 'tenant-1',
              name: 'Test Webhook',
              url: 'https://example.com/webhook',
              events: ['*'],
              has_secret: false,
              enabled: true,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-02-01T00:00:00Z',
              headers: {},
            },
          ],
        },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        const deleteButton = screen.getByTitle('Delete webhook');
        expect(deleteButton).toBeInTheDocument();
      });
    });

    it('renders edit button', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: {
          items: [
            {
              id: 'wh-1',
              tenant_id: 'tenant-1',
              name: 'Test Webhook',
              url: 'https://example.com/webhook',
              events: ['*'],
              has_secret: false,
              enabled: true,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-02-01T00:00:00Z',
              headers: {},
            },
          ],
        },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        const editButton = screen.getByTitle('Edit webhook');
        expect(editButton).toBeInTheDocument();
      });
    });

    it('renders delivery history button', async () => {
      mockAuth.mockReturnValue({
        user: { email: 'test@example.com', tenant_id: 'tenant-1', is_admin: false, roles: [] },
      });
      mockUseWebhooks.mockReturnValue({
        data: {
          items: [
            {
              id: 'wh-1',
              tenant_id: 'tenant-1',
              name: 'Test Webhook',
              url: 'https://example.com/webhook',
              events: ['*'],
              has_secret: false,
              enabled: true,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-02-01T00:00:00Z',
              headers: {},
            },
          ],
        },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      });

      renderWithProviders(<WebhooksPage />);

      await waitFor(() => {
        const historyButton = screen.getByTitle('View delivery history');
        expect(historyButton).toBeInTheDocument();
      });
    });
  });
});
