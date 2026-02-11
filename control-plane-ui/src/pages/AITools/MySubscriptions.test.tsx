import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetMySubscriptions = vi.fn().mockResolvedValue([]);
const mockGetTool = vi.fn().mockResolvedValue({ name: 'test', description: 'Test tool' });

vi.mock('../../services/mcpGatewayApi', () => ({
  mcpGatewayService: {
    getMySubscriptions: (...args: unknown[]) => mockGetMySubscriptions(...args),
    getTool: (...args: unknown[]) => mockGetTool(...args),
    unsubscribeTool: vi.fn().mockResolvedValue(undefined),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { MySubscriptions } from './MySubscriptions';

describe('MySubscriptions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetMySubscriptions.mockResolvedValue([]);
  });

  it('renders the heading', async () => {
    renderWithProviders(<MySubscriptions />);
    expect(await screen.findByRole('heading', { name: /My Subscriptions/ })).toBeInTheDocument();
  });

  it('shows browse catalog link', async () => {
    renderWithProviders(<MySubscriptions />);
    expect(await screen.findByText(/Browse Catalog/)).toBeInTheDocument();
  });

  it('shows empty state when no subscriptions', async () => {
    renderWithProviders(<MySubscriptions />);
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('renders subscription data in table', async () => {
    mockGetMySubscriptions.mockResolvedValue([
      {
        id: 'sub-1',
        toolName: 'stoa_list_apis',
        status: 'active',
        usageCount: 42,
        subscribedAt: '2026-01-15T00:00:00Z',
      },
    ]);
    renderWithProviders(<MySubscriptions />);
    expect(await screen.findByText('stoa_list_apis')).toBeInTheDocument();
  });

  it('shows error message on API failure', async () => {
    mockGetMySubscriptions.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<MySubscriptions />);
    await waitFor(() => {
      expect(screen.getByText(/failed|error/i)).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<MySubscriptions />);
        expect(
          await screen.findByRole('heading', { name: /My Subscriptions/ })
        ).toBeInTheDocument();
      });
    }
  );
});
