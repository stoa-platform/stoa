/**
 * GatewaysPage Tests - CAB-1133
 *
 * Tests for the gateway instances admin page.
 * Route guard: scope="stoa:admin" — only cpi-admin has access.
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { GatewaysPage } from '../gateways/GatewaysPage';

// Mock gatewaysService
const mockListGateways = vi.fn();
vi.mock('../../services/gateways', () => ({
  gatewaysService: {
    listGateways: (...args: unknown[]) => mockListGateways(...args),
    triggerHealthCheck: vi.fn().mockResolvedValue(true),
  },
}));

// Mock AuthContext
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'GatewaysPage — %s persona',
  (role) => {
    beforeEach(() => {
      vi.clearAllMocks();
      mockAuth.mockReturnValue(createAuthMock(role));
    });

    it('renders table when gateways exist (admin only)', async () => {
      if (role !== 'cpi-admin') return;

      mockListGateways.mockResolvedValue({
        items: [
          {
            id: '1',
            name: 'kong-gra',
            display_name: 'Kong DB-less (GRA)',
            gateway_type: 'kong',
            base_url: 'https://kong.example.com',
            environment: 'prod',
            status: 'online',
            last_health_check: '2026-02-12T10:00:00Z',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-02-12T10:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      });

      renderWithProviders(<GatewaysPage />);

      await waitFor(() => {
        expect(screen.getByText('Kong DB-less (GRA)')).toBeInTheDocument();
      });
      expect(screen.getByText('Online')).toBeInTheDocument();
    });

    it('renders empty state when no gateways (admin only)', async () => {
      if (role !== 'cpi-admin') return;

      mockListGateways.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
      });

      renderWithProviders(<GatewaysPage />);

      await waitFor(() => {
        expect(screen.getByText('No gateways registered')).toBeInTheDocument();
      });
    });

    it('verifies stoa:admin scope availability based on role', () => {
      const auth = createAuthMock(role);
      if (role === 'cpi-admin') {
        expect(auth.hasScope('stoa:admin')).toBe(true);
      } else {
        expect(auth.hasScope('stoa:admin')).toBe(false);
      }
    });
  }
);
