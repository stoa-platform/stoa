/**
 * RateLimitsPage Tests - CAB-1470
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { RateLimitsPage } from '../rate-limits/RateLimitsPage';

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

const mockRateLimitsData = vi.fn();

vi.mock('../../hooks/useRateLimits', () => ({
  useRateLimits: () => ({
    data: mockRateLimitsData(),
    isLoading: false,
  }),
}));

const sampleRateLimits = [
  {
    api_id: 'api-1',
    api_name: 'Payment API',
    subscription_id: 'sub-1',
    plan_name: 'Gold',
    period: 'minute',
    limit: 1000,
    used: 450,
    remaining: 550,
    reset_at: '2026-02-25T15:00:00Z',
  },
  {
    api_id: 'api-2',
    api_name: 'Maps API',
    subscription_id: 'sub-2',
    plan_name: 'Silver',
    period: 'hour',
    limit: 500,
    used: 475,
    remaining: 25,
    reset_at: '2026-02-25T16:00:00Z',
  },
];

describe('RateLimitsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
    mockRateLimitsData.mockReturnValue({ rate_limits: sampleRateLimits });
  });

  it('renders the page heading and subtitle', async () => {
    renderWithProviders(<RateLimitsPage />);
    await waitFor(() => {
      expect(screen.getByText('Rate Limits')).toBeInTheDocument();
    });
    expect(screen.getByText('Monitor your API usage quotas')).toBeInTheDocument();
  });

  it('renders rate limit cards', async () => {
    renderWithProviders(<RateLimitsPage />);
    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });
    expect(screen.getByText('Maps API')).toBeInTheDocument();
  });

  it('renders plan names and periods', async () => {
    renderWithProviders(<RateLimitsPage />);
    await waitFor(() => {
      expect(screen.getByText(/Gold/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Silver/)).toBeInTheDocument();
    expect(screen.getByText(/per minute/)).toBeInTheDocument();
    expect(screen.getByText(/per hour/)).toBeInTheDocument();
  });

  it('renders usage bars with counts', async () => {
    renderWithProviders(<RateLimitsPage />);
    await waitFor(() => {
      expect(screen.getByText(/450/)).toBeInTheDocument();
    });
    expect(screen.getByText(/475/)).toBeInTheDocument();
  });

  it('renders remaining counts', async () => {
    renderWithProviders(<RateLimitsPage />);
    await waitFor(() => {
      expect(screen.getByText('550 remaining')).toBeInTheDocument();
    });
    expect(screen.getByText('25 remaining')).toBeInTheDocument();
  });

  it('shows empty state when no rate limits', async () => {
    mockRateLimitsData.mockReturnValue({ rate_limits: [] });
    renderWithProviders(<RateLimitsPage />);
    await waitFor(() => {
      expect(screen.getByText('No active rate limits')).toBeInTheDocument();
    });
    expect(screen.getByText('Subscribe to APIs to see your usage quotas here')).toBeInTheDocument();
  });

  it('returns null when not authenticated', () => {
    mockAuth.mockReturnValue({
      ...createAuthMock('cpi-admin'),
      isAuthenticated: false,
      isLoading: false,
    });
    const { container } = renderWithProviders(<RateLimitsPage />);
    expect(container.innerHTML).toBe('');
  });

  describe('Persona-based Tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(personas)('%s can access rate limits page (stoa:metrics:read)', async (persona) => {
      mockAuth.mockReturnValue(createAuthMock(persona));
      renderWithProviders(<RateLimitsPage />);
      await waitFor(() => {
        expect(screen.getByText('Rate Limits')).toBeInTheDocument();
      });
    });
  });
});
