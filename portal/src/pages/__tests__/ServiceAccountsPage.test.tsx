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

// Mock apiClient
vi.mock('../../services/api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('ServiceAccountsPage', () => {
  let apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    vi.clearAllMocks();
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

  describe('Persona-based Tests', () => {
    it.each(['cpi-admin', 'tenant-admin'] as PersonaRole[])(
      '%s has stoa:subscriptions:write scope for service accounts',
      (persona) => {
        const auth = createAuthMock(persona);
        expect(auth.hasScope('stoa:subscriptions:write')).toBe(true);
      }
    );

    it.each(['devops', 'viewer'] as PersonaRole[])(
      '%s does not have stoa:subscriptions:write scope',
      (persona) => {
        const auth = createAuthMock(persona);
        expect(auth.hasScope('stoa:subscriptions:write')).toBe(false);
      }
    );

    it('cpi-admin can render service accounts page', async () => {
      renderWithProviders(<ServiceAccountsPage />);

      await waitFor(() => {
        expect(screen.getByText('Service Accounts')).toBeInTheDocument();
      });
    });
  });
});
