import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders, mockAPI, mockTenant } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetApis = vi.fn().mockResolvedValue([
  mockAPI({ id: 'api-1', name: 'payment-api', display_name: 'Payment API', audience: 'public' }),
  mockAPI({
    id: 'api-2',
    name: 'billing-api',
    display_name: 'Billing API',
    audience: 'internal',
  }),
]);
const mockGetTenants = vi
  .fn()
  .mockResolvedValue([
    mockTenant({ id: 't1', name: 'oasis-gunters', display_name: 'OASIS Gunters' }),
  ]);
const mockUpdateAudience = vi.fn().mockResolvedValue({
  api_id: 'payment-api',
  tenant_id: 'oasis-gunters',
  audience: 'internal',
  updated_by: 'halliday',
});

vi.mock('../services/api', () => ({
  apiService: {
    getApis: (...args: unknown[]) => mockGetApis(...args),
    getTenants: (...args: unknown[]) => mockGetTenants(...args),
    updateApiAudience: (...args: unknown[]) => mockUpdateAudience(...args),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

import { AudienceGovernance } from './AudienceGovernance';

function renderComponent() {
  return renderWithProviders(<AudienceGovernance />, { route: '/audience-governance' });
}

describe('AudienceGovernance', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetApis.mockResolvedValue([
      mockAPI({
        id: 'api-1',
        name: 'payment-api',
        display_name: 'Payment API',
        audience: 'public',
      }),
      mockAPI({
        id: 'api-2',
        name: 'billing-api',
        display_name: 'Billing API',
        audience: 'internal',
      }),
    ]);
    mockGetTenants.mockResolvedValue([
      mockTenant({ id: 't1', name: 'oasis-gunters', display_name: 'OASIS Gunters' }),
    ]);
  });

  it('renders the heading', () => {
    renderComponent();
    expect(screen.getByRole('heading', { name: 'Audience Governance' })).toBeInTheDocument();
  });

  it('shows tenant selector for cpi-admin', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('OASIS Gunters')).toBeInTheDocument();
    });
  });

  it('shows APIs after selecting tenant', async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('OASIS Gunters')).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole('combobox'), 'oasis-gunters');

    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
      expect(screen.getByText('Billing API')).toBeInTheDocument();
    });
  });

  it('shows audience badges', async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('OASIS Gunters')).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole('combobox'), 'oasis-gunters');

    await waitFor(() => {
      expect(screen.getByText('public')).toBeInTheDocument();
      expect(screen.getByText('internal')).toBeInTheDocument();
    });
  });

  it('filters APIs by search', async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('OASIS Gunters')).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByRole('combobox'), 'oasis-gunters');

    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText('Search APIs...'), 'billing');

    expect(screen.queryByText('Payment API')).not.toBeInTheDocument();
    expect(screen.getByText('Billing API')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(screen.getByRole('heading', { name: 'Audience Governance' })).toBeInTheDocument();
      });

      // cpi-admin, tenant-admin, devops all have apis:update — badges are clickable
      if (role === 'cpi-admin' || role === 'tenant-admin' || role === 'devops') {
        it('audience badges are clickable', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          const user = userEvent.setup();
          renderComponent();

          if (role === 'cpi-admin') {
            await waitFor(() => {
              expect(screen.getByText('OASIS Gunters')).toBeInTheDocument();
            });
            await user.selectOptions(screen.getAllByRole('combobox')[0], 'oasis-gunters');
          }

          await waitFor(() => {
            expect(screen.getByText('public')).toBeInTheDocument();
          });

          // Click the audience badge — should open an inline select
          await user.click(screen.getByText('public'));

          // The inline select replaces the badge
          const selects = screen.getAllByRole('combobox');
          const audienceSelect = selects.find((el) => el.tagName === 'SELECT' && el.closest('td'));
          expect(audienceSelect).toBeDefined();
        });
      }

      if (role === 'viewer') {
        it('audience badges are not clickable', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();

          await waitFor(() => {
            expect(screen.getByText('public')).toBeInTheDocument();
          });

          const badge = screen.getByText('public');
          expect(badge).toBeDisabled();
        });
      }
    }
  );
});
