import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockWebhooks = [
  {
    id: 'wh-1',
    tenant_id: 'oasis-gunters',
    name: 'Order Notifications',
    url: 'https://example.com/webhooks',
    events: ['subscription.created', 'subscription.approved'],
    enabled: true,
    secret: 'whsec_test123',
    headers: {},
    created_at: '2026-02-15T10:00:00Z',
    updated_at: '2026-02-15T10:00:00Z',
  },
  {
    id: 'wh-2',
    tenant_id: 'oasis-gunters',
    name: 'Audit Trail',
    url: 'https://audit.example.com/hook',
    events: ['*'],
    enabled: false,
    secret: null,
    headers: {},
    created_at: '2026-02-16T10:00:00Z',
    updated_at: '2026-02-16T10:00:00Z',
  },
];

const mockGetWebhooks = vi.fn().mockResolvedValue({ items: mockWebhooks, total: 2 });
const mockCreateWebhook = vi.fn().mockResolvedValue(mockWebhooks[0]);
const mockUpdateWebhook = vi.fn().mockResolvedValue(mockWebhooks[0]);
const mockDeleteWebhook = vi.fn().mockResolvedValue({});
const mockTestWebhook = vi.fn().mockResolvedValue({ success: true, status_code: 200 });

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([
      {
        id: 'oasis-gunters',
        name: 'oasis-gunters',
        display_name: 'Oasis Gunters',
        status: 'active',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]),
    getWebhooks: (...args: unknown[]) => mockGetWebhooks(...args),
    createWebhook: (...args: unknown[]) => mockCreateWebhook(...args),
    updateWebhook: (...args: unknown[]) => mockUpdateWebhook(...args),
    deleteWebhook: (...args: unknown[]) => mockDeleteWebhook(...args),
    testWebhook: (...args: unknown[]) => mockTestWebhook(...args),
    getWebhookDeliveries: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    retryWebhookDelivery: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  ConfirmDialog: ({
    open,
    title,
    onConfirm,
    onCancel,
  }: {
    open: boolean;
    title: string;
    onConfirm: () => void;
    onCancel: () => void;
  }) =>
    open ? (
      <div data-testid="confirm-dialog">
        <span>{title}</span>
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));

// Lazy import the component (after mocks are set up)
const { Webhooks } = await import('./Webhooks');

describe('Webhooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetWebhooks.mockResolvedValue({ items: mockWebhooks, total: 2 });
  });

  it('renders the page title and add button', async () => {
    renderWithProviders(<Webhooks />);
    expect(screen.getByText('Webhook Notifications')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Add Webhook')).toBeInTheDocument();
    });
  });

  it('displays webhooks after loading', async () => {
    renderWithProviders(<Webhooks />);
    await waitFor(() => {
      expect(screen.getByText('Order Notifications')).toBeInTheDocument();
      expect(screen.getByText('Audit Trail')).toBeInTheDocument();
    });
  });

  it('shows empty state when no webhooks', async () => {
    mockGetWebhooks.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<Webhooks />);
    await waitFor(() => {
      expect(screen.getByText('No webhooks configured')).toBeInTheDocument();
    });
  });

  it('opens create modal when button clicked', async () => {
    const user = userEvent.setup();
    mockGetWebhooks.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<Webhooks />);
    await waitFor(() => {
      expect(screen.getByText('No webhooks configured')).toBeInTheDocument();
    });
    const addButtons = screen.getAllByText('Add Webhook');
    await user.click(addButtons[addButtons.length - 1]);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Create Webhook' })).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<Webhooks />);
        expect(screen.getByText('Webhook Notifications')).toBeInTheDocument();
      });
    }
  );
});
