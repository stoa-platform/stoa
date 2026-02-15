/**
 * ApplicationDetail Tests - CAB-1133
 *
 * Tests for the application detail page with tabs (Overview, Credentials, Subscriptions).
 * Route guard: permission="apps:read" — all 4 personas have access.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  renderWithProviders,
  createAuthMock,
  mockApplication,
  type PersonaRole,
} from '../../test/helpers';
import { Routes, Route } from 'react-router-dom';

// Mock hooks
const mockUseApplication = vi.fn();
const mockUseDeleteApplication = vi.fn();
const mockUseRegenerateSecret = vi.fn();
const mockUseApplicationSubscriptions = vi.fn();

vi.mock('../../hooks/useApplications', () => ({
  useApplication: (id: string) => mockUseApplication(id),
  useDeleteApplication: () => mockUseDeleteApplication(),
  useRegenerateSecret: (id: string) => mockUseRegenerateSecret(id),
}));

vi.mock('../../hooks/useSubscriptions', () => ({
  useApplicationSubscriptions: (id: string) => mockUseApplicationSubscriptions(id),
}));

// Mock CredentialsViewer
vi.mock('../../components/apps/CredentialsViewer', () => ({
  CredentialsViewer: ({ clientId }: { clientId: string }) => (
    <div data-testid="credentials-viewer">Credentials: {clientId}</div>
  ),
}));

describe('ApplicationDetail', () => {
  let ApplicationDetail: React.ComponentType;

  beforeEach(async () => {
    vi.clearAllMocks();

    const pageModule = await import('../apps/ApplicationDetail');
    ApplicationDetail = pageModule.ApplicationDetail;

    mockUseDeleteApplication.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseRegenerateSecret.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseApplicationSubscriptions.mockReturnValue({ data: [], isLoading: false });
  });

  const renderWithRoute = (appId: string = 'app-1') => {
    return renderWithProviders(
      <Routes>
        <Route path="/apps/:id" element={<ApplicationDetail />} />
      </Routes>,
      { route: `/apps/${appId}` }
    );
  };

  it('shows loading state', () => {
    mockUseApplication.mockReturnValue({ data: undefined, isLoading: true, isError: false });

    renderWithRoute();

    expect(screen.getByText('Loading application...')).toBeInTheDocument();
  });

  it('shows error state when application not found', async () => {
    mockUseApplication.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Not found'),
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Failed to load application')).toBeInTheDocument();
    });
  });

  it('renders application name and status', async () => {
    mockUseApplication.mockReturnValue({
      data: mockApplication({ name: 'My Test App', status: 'active' }),
      isLoading: false,
      isError: false,
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('My Test App')).toBeInTheDocument();
      expect(screen.getAllByText('Active').length).toBeGreaterThan(0);
    });
  });

  it('renders 3 tabs: Overview, Credentials, Subscriptions', async () => {
    mockUseApplication.mockReturnValue({
      data: mockApplication(),
      isLoading: false,
      isError: false,
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Credentials')).toBeInTheDocument();
      expect(screen.getByText('Subscriptions')).toBeInTheDocument();
    });
  });

  it('clicking Credentials tab shows credentials viewer', async () => {
    const user = userEvent.setup();
    mockUseApplication.mockReturnValue({
      data: mockApplication(),
      isLoading: false,
      isError: false,
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByText('Credentials')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Credentials'));

    await waitFor(() => {
      expect(screen.getByTestId('credentials-viewer')).toBeInTheDocument();
    });
  });

  it('renders delete button', async () => {
    mockUseApplication.mockReturnValue({
      data: mockApplication(),
      isLoading: false,
      isError: false,
    });

    renderWithRoute();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Delete/i })).toBeInTheDocument();
    });
  });

  describe('Persona-based Tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(personas)('%s has apps:read permission for application detail', (persona) => {
      const auth = createAuthMock(persona);
      expect(auth.hasPermission('apps:read')).toBe(true);
    });

    it.each(personas)('%s can view application detail', async (persona) => {
      createAuthMock(persona); // Verify no error creating mock
      mockUseApplication.mockReturnValue({
        data: mockApplication(),
        isLoading: false,
        isError: false,
      });

      renderWithRoute();

      await waitFor(() => {
        expect(screen.getByText('My App')).toBeInTheDocument();
      });
    });
  });
});
