import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Consumer } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockRevokeCertificate = vi.fn().mockResolvedValue({});
const mockRotateCertificate = vi.fn().mockResolvedValue({});
const mockBindCertificate = vi.fn().mockResolvedValue({});

vi.mock('../services/api', () => ({
  apiService: {
    revokeCertificate: (...args: unknown[]) => mockRevokeCertificate(...args),
    rotateCertificate: (...args: unknown[]) => mockRotateCertificate(...args),
    bindCertificate: (...args: unknown[]) => mockBindCertificate(...args),
  },
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

const mockToast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => mockToast,
}));

const mockConfirm = vi.fn().mockResolvedValue(true);
vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [mockConfirm, () => null],
}));

import { ConsumerDetailModal } from './ConsumerDetailModal';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const baseConsumer: Consumer = {
  id: 'consumer-1',
  tenant_id: 'tenant-1',
  external_id: 'ext-001',
  name: 'Alice',
  email: 'alice@example.com',
  company: 'Acme Corp',
  status: 'active',
  certificate_fingerprint: 'AB:CD:EF:12:34:56:78:90:AB:CD:EF:12',
  certificate_status: 'active',
  certificate_subject_dn: 'CN=alice,O=Acme',
  certificate_not_before: '2024-01-01T00:00:00Z',
  certificate_not_after: '2025-01-01T00:00:00Z',
  rotation_count: 2,
  last_rotated_at: '2024-06-01T00:00:00Z',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

function renderModal(consumer: Consumer = baseConsumer, onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConsumerDetailModal consumer={consumer} tenantId="tenant-1" onClose={onClose} />
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ConsumerDetailModal', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders consumer name and external_id', () => {
    renderModal();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('ext-001')).toBeInTheDocument();
  });

  it('renders consumer info fields', () => {
    renderModal();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  it('renders certificate details when cert exists', () => {
    renderModal();
    expect(screen.getByText('AB:CD:EF:12:34:56:78:90:AB:CD:EF:12')).toBeInTheDocument();
    expect(screen.getByText('CN=alice,O=Acme')).toBeInTheDocument();
  });

  it('shows "No certificate" message when no cert', () => {
    const noCertConsumer = { ...baseConsumer, certificate_fingerprint: undefined };
    renderModal(noCertConsumer);
    expect(screen.getByText(/no certificate bound/i)).toBeInTheDocument();
  });

  it('shows Rotate and Revoke buttons for active cert', () => {
    renderModal();
    expect(screen.getByText('Rotate Certificate')).toBeInTheDocument();
    expect(screen.getByText('Revoke Certificate')).toBeInTheDocument();
  });

  it('hides action buttons for revoked cert', () => {
    const revokedConsumer = { ...baseConsumer, certificate_status: 'revoked' as const };
    renderModal(revokedConsumer);
    expect(screen.queryByText('Rotate Certificate')).not.toBeInTheDocument();
    expect(screen.queryByText('Revoke Certificate')).not.toBeInTheDocument();
  });

  it('opens rotate form when clicking Rotate Certificate', () => {
    renderModal();
    fireEvent.click(screen.getByText('Rotate Certificate'));
    expect(screen.getByText('New PEM Certificate')).toBeInTheDocument();
    expect(screen.getByText('Confirm Rotation')).toBeInTheDocument();
  });

  it('calls onClose when clicking backdrop', () => {
    const onClose = vi.fn();
    const { container } = renderModal(baseConsumer, onClose);
    // The backdrop is the first fixed div
    const backdrop = container.querySelector('.bg-black\\/50');
    expect(backdrop).toBeInTheDocument();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls revokeCertificate on revoke confirmation', async () => {
    const onClose = vi.fn();
    renderModal(baseConsumer, onClose);
    fireEvent.click(screen.getByText('Revoke Certificate'));
    await waitFor(() => {
      expect(mockRevokeCertificate).toHaveBeenCalledWith('tenant-1', 'consumer-1');
    });
    expect(mockToast.success).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('does not revoke when confirmation is cancelled', async () => {
    mockConfirm.mockResolvedValueOnce(false);
    renderModal();
    fireEvent.click(screen.getByText('Revoke Certificate'));
    await waitFor(() => {
      expect(mockConfirm).toHaveBeenCalled();
    });
    expect(mockRevokeCertificate).not.toHaveBeenCalled();
  });

  it('shows rotation count when > 0', () => {
    renderModal();
    expect(screen.getByText('Rotations')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows error toast on revoke failure', async () => {
    mockRevokeCertificate.mockRejectedValueOnce(new Error('Network error'));
    renderModal();
    fireEvent.click(screen.getByText('Revoke Certificate'));
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Revoke failed', 'Network error');
    });
  });

  // --- Bind Certificate Tests (CAB-872) ---

  it('shows Bind Certificate button when no cert', () => {
    const noCertConsumer = { ...baseConsumer, certificate_fingerprint: undefined };
    renderModal(noCertConsumer);
    expect(screen.getByText('Bind Certificate')).toBeInTheDocument();
  });

  it('opens bind form when clicking Bind Certificate', () => {
    const noCertConsumer = { ...baseConsumer, certificate_fingerprint: undefined };
    renderModal(noCertConsumer);
    fireEvent.click(screen.getByText('Bind Certificate'));
    expect(screen.getByText('PEM Certificate')).toBeInTheDocument();
    expect(screen.getByText('Confirm Bind')).toBeInTheDocument();
  });

  it('calls bindCertificate on confirm', async () => {
    const onClose = vi.fn();
    const noCertConsumer = { ...baseConsumer, certificate_fingerprint: undefined };
    renderModal(noCertConsumer, onClose);
    fireEvent.click(screen.getByText('Bind Certificate'));
    const textarea = screen.getByPlaceholderText(/BEGIN CERTIFICATE/);
    fireEvent.change(textarea, {
      target: { value: '-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----' },
    });
    fireEvent.click(screen.getByText('Confirm Bind'));
    await waitFor(() => {
      expect(mockBindCertificate).toHaveBeenCalledWith(
        'tenant-1',
        'consumer-1',
        '-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----'
      );
    });
    expect(mockToast.success).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('shows error when bind fails', async () => {
    mockBindCertificate.mockRejectedValueOnce(new Error('Invalid PEM'));
    const noCertConsumer = { ...baseConsumer, certificate_fingerprint: undefined };
    renderModal(noCertConsumer);
    fireEvent.click(screen.getByText('Bind Certificate'));
    const textarea = screen.getByPlaceholderText(/BEGIN CERTIFICATE/);
    fireEvent.change(textarea, { target: { value: 'invalid-pem' } });
    fireEvent.click(screen.getByText('Confirm Bind'));
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Bind failed', 'Invalid PEM');
    });
  });

  it('shows Rebind Certificate for revoked cert', () => {
    const revokedConsumer = { ...baseConsumer, certificate_status: 'revoked' as const };
    renderModal(revokedConsumer);
    expect(screen.getByText('Rebind Certificate')).toBeInTheDocument();
  });

  it('shows Replace Certificate for expired cert', () => {
    const expiredConsumer = { ...baseConsumer, certificate_status: 'expired' as const };
    renderModal(expiredConsumer);
    expect(screen.getByText('Replace Certificate')).toBeInTheDocument();
  });

  it('shows CertificateHealthBadge for active cert', () => {
    renderModal();
    expect(screen.getByText('Health')).toBeInTheDocument();
  });
});
