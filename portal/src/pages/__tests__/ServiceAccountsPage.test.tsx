/**
 * ServiceAccountsPage Tests - CAB-1133
 *
 * Tests for the service accounts management page.
 * Route guard: scope="stoa:subscriptions:write" — cpi-admin + tenant-admin only.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { ServiceAccountsPage } from '../service-accounts/ServiceAccountsPage';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';

// Mock AuthContext
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock apiClient
vi.mock('../../services/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'ServiceAccountsPage — %s persona',
  (role) => {
    let apiClient: {
      get: ReturnType<typeof vi.fn>;
      post: ReturnType<typeof vi.fn>;
      delete: ReturnType<typeof vi.fn>;
    };

    beforeEach(async () => {
      vi.clearAllMocks();
      mockAuth.mockReturnValue(createAuthMock(role));
      const apiModule = await import('../../services/api');
      apiClient = apiModule.apiClient as typeof apiClient;
      apiClient.get.mockResolvedValue({ data: [] });
    });

    it('renders "Service Accounts" heading', async () => {
      renderWithProviders(<ServiceAccountsPage />);

      await waitFor(() => {
        expect(screen.getByText('Service Accounts')).toBeInTheDocument();
      });
    });

    it('shows empty state when no service accounts', async () => {
      apiClient.get.mockResolvedValue({ data: [] });

      renderWithProviders(<ServiceAccountsPage />);

      await waitFor(() => {
        expect(screen.getByText('No service accounts yet')).toBeInTheDocument();
        expect(screen.getByText('Create your first service account')).toBeInTheDocument();
      });
    });

    it('renders service account list when accounts exist', async () => {
      apiClient.get.mockResolvedValue({
        data: [
          {
            id: 'sa-1',
            client_id: 'stoa_sa_abc123',
            name: 'Claude Desktop',
            description: 'MCP access for Claude',
            enabled: true,
          },
        ],
      });

      renderWithProviders(<ServiceAccountsPage />);

      await waitFor(() => {
        expect(screen.getByText('Claude Desktop')).toBeInTheDocument();
      });
    });

    it('verifies stoa:subscriptions:write scope access per role', () => {
      const auth = createAuthMock(role);
      const expected = ['cpi-admin', 'tenant-admin'].includes(role);
      expect(auth.hasScope('stoa:subscriptions:write')).toBe(expected);
    });

    // CAB-1673: Structural snapshot guard
    it('matches structural snapshot', async () => {
      apiClient.get.mockResolvedValue({ data: [] });
      const { container } = renderWithProviders(<ServiceAccountsPage />);
      await waitFor(() => {
        expect(screen.getByText('Service Accounts')).toBeInTheDocument();
      });
      const buttons = [...container.querySelectorAll('button')].map(
        (b) => b.textContent?.trim() || ''
      );
      const headings = [...container.querySelectorAll('h1, h2, h3')].map(
        (h) => h.textContent?.trim() || ''
      );
      const links = [...container.querySelectorAll('a[href]')].map((a) => ({
        text: a.textContent?.trim() || '',
        href: a.getAttribute('href'),
      }));
      expect({ buttons, headings, links }).toMatchSnapshot();
    });
  }
);
