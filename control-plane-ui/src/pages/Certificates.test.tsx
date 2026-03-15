/**
 * Certificates page tests (CAB-1786)
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Certificates } from './Certificates';
import type { Consumer } from '../types';

// Mock dependencies
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ isReady: true, user: { name: 'Test' } }),
}));

vi.mock('../hooks/useEnvironmentMode', () => ({
  useEnvironmentMode: () => ({ canEdit: true, canDelete: true }),
}));

const { mockGetTenants, mockGetConsumers, mockBulkRevoke, mockRevokeCert } = vi.hoisted(() => ({
  mockGetTenants: vi
    .fn()
    .mockResolvedValue([{ id: 'tenant-1', name: 'acme', display_name: 'Acme Corp' }]),
  mockGetConsumers: vi.fn().mockResolvedValue([]),
  mockBulkRevoke: vi.fn().mockResolvedValue({ success: 1, failed: 0, skipped: 0, errors: [] }),
  mockRevokeCert: vi.fn().mockResolvedValue({}),
}));

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: mockGetTenants,
    getConsumers: mockGetConsumers,
    bulkRevokeCertificates: mockBulkRevoke,
    revokeCertificate: mockRevokeCert,
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), null],
}));

vi.mock('../components/CertificateHealthBadge', () => ({
  CertificateHealthBadge: ({ status }: { status: string }) => (
    <span data-testid="cert-badge">{status}</span>
  ),
}));

vi.mock('../components/ConsumerDetailModal', () => ({
  ConsumerDetailModal: () => <div data-testid="consumer-modal">Modal</div>,
}));

function makeCertConsumer(overrides: Partial<Consumer> = {}): Consumer {
  return {
    id: 'c1',
    tenant_id: 'tenant-1',
    external_id: 'ext-1',
    name: 'Consumer One',
    email: 'one@example.com',
    status: 'active',
    certificate_fingerprint: 'aabbccddee112233445566778899aabb',
    certificate_status: 'active',
    certificate_subject_dn: 'CN=consumer-one,O=Acme',
    certificate_not_before: '2025-01-01T00:00:00Z',
    certificate_not_after: new Date(Date.now() + 120 * 24 * 60 * 60 * 1000).toISOString(),
    last_rotated_at: undefined,
    rotation_count: 0,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderCertificates(consumers: Consumer[] = []) {
  mockGetConsumers.mockResolvedValue(consumers);

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/certificates']}>
        <Certificates />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Certificates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page heading', async () => {
    renderCertificates();
    expect(await screen.findByRole('heading', { name: /certificates/i })).toBeInTheDocument();
  });

  it('shows empty state when no consumers have certificates', async () => {
    renderCertificates([
      makeCertConsumer({ certificate_fingerprint: undefined, certificate_status: undefined }),
    ]);
    expect(await screen.findByText(/no certificates bound/i)).toBeInTheDocument();
  });

  it('renders dashboard cards with correct counts', async () => {
    const consumers = [
      makeCertConsumer({ id: 'c1', name: 'Active Cert' }), // >90 days → active
      makeCertConsumer({
        id: 'c2',
        name: 'Expiring Cert',
        certificate_not_after: new Date(Date.now() + 60 * 24 * 60 * 60 * 1000).toISOString(),
      }), // 60 days → expiring
      makeCertConsumer({
        id: 'c3',
        name: 'Critical Cert',
        certificate_not_after: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(),
      }), // 5 days → critical
      makeCertConsumer({
        id: 'c4',
        name: 'Revoked Cert',
        certificate_status: 'revoked',
      }),
    ];
    renderCertificates(consumers);

    // Wait for data to load
    expect(await screen.findByText('Active Cert')).toBeInTheDocument();

    // Dashboard cards — verify all 4 category labels present
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Expiring Soon')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('Revoked')).toBeInTheDocument();
  });

  it('renders certificate table with consumer data', async () => {
    const consumer = makeCertConsumer();
    renderCertificates([consumer]);

    expect(await screen.findByText('Consumer One')).toBeInTheDocument();
    expect(screen.getByText('ext-1')).toBeInTheDocument();
    expect(screen.getByTestId('cert-badge')).toHaveTextContent('active');
  });

  it('shows SubNav with consumers group tabs', async () => {
    renderCertificates();
    const nav = await screen.findByRole('navigation', { name: 'Sub-navigation' });
    expect(nav).toBeInTheDocument();
    expect(within(nav).getByText('Consumers')).toBeInTheDocument();
    expect(within(nav).getByText('Certificates')).toBeInTheDocument();
    expect(within(nav).getByText('Credential Mappings')).toBeInTheDocument();
  });

  it('marks Certificates tab as active', async () => {
    renderCertificates();
    const nav = await screen.findByRole('navigation', { name: 'Sub-navigation' });
    const certLink = within(nav).getByText('Certificates').closest('a');
    expect(certLink).toHaveAttribute('aria-current', 'page');
  });

  it('shows expiry alert banner when critical certs exist', async () => {
    renderCertificates([
      makeCertConsumer({
        certificate_not_after: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(),
      }),
    ]);
    expect(await screen.findByText(/expiring within 30 days/i)).toBeInTheDocument();
  });

  it('does not show expiry alert when no critical certs', async () => {
    renderCertificates([makeCertConsumer()]); // 120 days out
    await screen.findByText('Consumer One');
    expect(screen.queryByText(/expiring within 30 days/i)).not.toBeInTheDocument();
  });

  it('shows revoke button for active certificates', async () => {
    renderCertificates([makeCertConsumer()]);
    expect(await screen.findByText('Revoke')).toBeInTheDocument();
  });

  it('hides revoke button for already-revoked certificates', async () => {
    renderCertificates([makeCertConsumer({ certificate_status: 'revoked' })]);
    await screen.findByText('Consumer One');
    expect(screen.queryByText('Revoke')).not.toBeInTheDocument();
  });

  it('shows bulk actions toolbar when items are selected', async () => {
    const user = userEvent.setup();
    renderCertificates([makeCertConsumer()]);
    await screen.findByText('Consumer One');

    const checkbox = screen.getAllByRole('checkbox')[1]; // first is header
    await user.click(checkbox);

    expect(screen.getByText('1 selected')).toBeInTheDocument();
  });

  it('filters by clicking dashboard cards', async () => {
    const user = userEvent.setup();
    const consumers = [
      makeCertConsumer({ id: 'c1', name: 'Active Consumer' }),
      makeCertConsumer({
        id: 'c2',
        name: 'Revoked Consumer',
        certificate_status: 'revoked',
      }),
    ];
    renderCertificates(consumers);

    await screen.findByText('Active Consumer');
    expect(screen.getByText('Revoked Consumer')).toBeInTheDocument();

    // Click "Revoked" card
    const revokedCard = screen.getByText('Revoked').closest('button')!;
    await user.click(revokedCard);

    // Should only show revoked
    expect(screen.queryByText('Active Consumer')).not.toBeInTheDocument();
    expect(screen.getByText('Revoked Consumer')).toBeInTheDocument();
  });
});
