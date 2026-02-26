/**
 * AuditLogPage Tests - CAB-1470
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { AuditLogPage } from '../audit-log/AuditLogPage';

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

const mockAuditData = vi.fn();

vi.mock('../../hooks/useAuditLog', () => ({
  useAuditLog: () => ({
    data: mockAuditData(),
    isLoading: false,
  }),
}));

const sampleEntries = [
  {
    id: 'al1',
    timestamp: '2026-02-25T14:00:00Z',
    action: 'api.subscribed',
    resource_type: 'api',
    resource_name: 'Payment API',
    actor_name: 'john@example.com',
    details: 'Subscribed to plan Gold',
  },
  {
    id: 'al2',
    timestamp: '2026-02-25T13:00:00Z',
    action: 'key.created',
    resource_type: 'api_key',
    resource_name: 'prod-key-1',
    actor_name: 'jane@example.com',
    details: 'Created API key for Payment API',
  },
];

describe('AuditLogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
    mockAuditData.mockReturnValue({
      entries: sampleEntries,
      total: 2,
    });
  });

  it('renders the page heading and subtitle', async () => {
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByText('Audit Log')).toBeInTheDocument();
    });
    expect(screen.getByText('Activity history for your account')).toBeInTheDocument();
  });

  it('renders table column headers', async () => {
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByText('Timestamp')).toBeInTheDocument();
    });
    expect(screen.getByText('Action')).toBeInTheDocument();
    expect(screen.getByText('Resource')).toBeInTheDocument();
    expect(screen.getByText('Actor')).toBeInTheDocument();
    expect(screen.getByText('Details')).toBeInTheDocument();
  });

  it('renders audit log entries', async () => {
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });
    expect(screen.getByText('prod-key-1')).toBeInTheDocument();
    expect(screen.getByText('john@example.com')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
    expect(screen.getByText('api.subscribed')).toBeInTheDocument();
    expect(screen.getByText('key.created')).toBeInTheDocument();
  });

  it('shows empty state when no entries', async () => {
    mockAuditData.mockReturnValue({ entries: [], total: 0 });
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByText('No audit log entries found')).toBeInTheDocument();
    });
  });

  it('renders search input', async () => {
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search by resource or actor...')).toBeInTheDocument();
    });
  });

  it('renders action filter dropdown', async () => {
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByText('All actions')).toBeInTheDocument();
    });
  });

  it('shows pagination when total > limit', async () => {
    mockAuditData.mockReturnValue({
      entries: sampleEntries,
      total: 50,
    });
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByText('Previous')).toBeInTheDocument();
    });
    expect(screen.getByText('Next')).toBeInTheDocument();
  });

  it('hides pagination when total fits in one page', async () => {
    mockAuditData.mockReturnValue({ entries: sampleEntries, total: 2 });
    renderWithProviders(<AuditLogPage />);
    await waitFor(() => {
      expect(screen.getByText('Audit Log')).toBeInTheDocument();
    });
    expect(screen.queryByText('Previous')).not.toBeInTheDocument();
  });

  it('returns null when not authenticated', () => {
    mockAuth.mockReturnValue({
      ...createAuthMock('cpi-admin'),
      isAuthenticated: false,
      isLoading: false,
    });
    const { container } = renderWithProviders(<AuditLogPage />);
    expect(container.innerHTML).toBe('');
  });

  describe('Persona-based Tests', () => {
    const personas: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(personas)('%s can access audit log page (audit:read)', async (persona) => {
      mockAuth.mockReturnValue(createAuthMock(persona));
      renderWithProviders(<AuditLogPage />);
      await waitFor(() => {
        expect(screen.getByText('Audit Log')).toBeInTheDocument();
      });
    });
  });
});
