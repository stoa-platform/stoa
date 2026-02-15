import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../contexts/EnvironmentContext', () => ({
  useEnvironment: vi.fn(() => ({
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [{ name: 'dev', label: 'Development', mode: 'full', color: 'green' }],
    switchEnvironment: vi.fn(),
  })),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockGetConsumers = vi.fn().mockResolvedValue([
  {
    id: 'consumer-1',
    tenant_id: 'tenant-1',
    external_id: 'ext-001',
    name: 'Alice',
    email: 'alice@example.com',
    company: 'Acme Corp',
    status: 'active',
    certificate_fingerprint: 'AB:CD:EF:12:34:56:78:90',
    certificate_status: 'active',
    certificate_subject_dn: 'CN=alice,O=Acme',
    certificate_not_before: '2024-01-01T00:00:00Z',
    certificate_not_after: '2025-01-01T00:00:00Z',
    rotation_count: 0,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
]);

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([
      {
        id: 'tenant-1',
        name: 'tenant-1',
        display_name: 'Tenant One',
        status: 'active',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    ]),
    getConsumers: (...args: unknown[]) => mockGetConsumers(...args),
    suspendConsumer: vi.fn(),
    activateConsumer: vi.fn(),
    deleteConsumer: vi.fn(),
    bulkRevokeCertificates: vi
      .fn()
      .mockResolvedValue({ success: 1, failed: 0, skipped: 0, errors: [] }),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
}));

vi.mock('@stoa/shared/components/Celebration', () => ({
  useCelebration: () => ({ celebrate: vi.fn() }),
}));

vi.mock('@stoa/shared/components/Collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../hooks/useEnvironmentMode', () => ({
  useEnvironmentMode: () => ({
    canCreate: true,
    canEdit: true,
    canDelete: true,
    canDeploy: true,
    isReadOnly: false,
  }),
}));

import { Consumers } from './Consumers';

function renderConsumers() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Consumers />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Consumers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page title', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText('Consumers')).toBeInTheDocument();
    });
  });

  it('renders the search input', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/search by id, name, email/i)).toBeInTheDocument();
    });
  });

  it('shows consumer data after loading', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  it('shows status badge', async () => {
    renderConsumers();
    await waitFor(() => {
      // "active" appears in both consumer status badge and certificate status
      const activeElements = screen.getAllByText('active');
      expect(activeElements.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows certificate fingerprint in table', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText(/AB:CD:EF:12/)).toBeInTheDocument();
    });
  });

  it('opens detail modal when clicking a row', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });
    const row = screen.getByText('Alice').closest('tr');
    expect(row).toBeInTheDocument();
    row!.click();
    await waitFor(() => {
      // Modal should show consumer details — the modal header repeats the name
      const aliceElements = screen.getAllByText('Alice');
      expect(aliceElements.length).toBeGreaterThanOrEqual(2); // table + modal
    });
  });

  it('shows empty state when no consumers', async () => {
    mockGetConsumers.mockResolvedValueOnce([]);
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText(/no consumers/i)).toBeInTheDocument();
    });
  });

  // --- CAB-872: Health Badge, Cert Filter, Bulk Actions ---

  it('shows CertificateHealthBadge in table for cert with active status', async () => {
    renderConsumers();
    await waitFor(() => {
      // The badge renders "Expired" since notAfter is 2025-01-01 which is past
      expect(screen.getByText('Expired')).toBeInTheDocument();
    });
  });

  it('shows certificate filter dropdown', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText('Certificate')).toBeInTheDocument();
    });
    // Check filter options exist
    const certSelect = screen.getByDisplayValue('All Certs');
    expect(certSelect).toBeInTheDocument();
  });

  it('shows checkbox column for bulk selection', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });
    // canEdit = true, so checkboxes should be present
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBeGreaterThanOrEqual(2); // header + at least 1 row
  });

  it('shows bulk toolbar when row checkbox is clicked', async () => {
    renderConsumers();
    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });
    const checkboxes = screen.getAllByRole('checkbox');
    // Click the row checkbox (not the header)
    fireEvent.click(checkboxes[1]);
    await waitFor(() => {
      expect(screen.getByText('1 selected')).toBeInTheDocument();
      expect(screen.getByText(/Revoke Selected/)).toBeInTheDocument();
    });
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderConsumers();
        await waitFor(() => {
          expect(screen.getByText('Consumers')).toBeInTheDocument();
        });
      });
    }
  );
});
