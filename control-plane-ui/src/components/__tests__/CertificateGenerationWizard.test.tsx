/**
 * Tests for CertificateGenerationWizard (CAB-1788).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CertificateGenerationWizard } from '../CertificateGenerationWizard';

// Mock the crypto module — forge keygen is too slow for unit tests
vi.mock('../../lib/crypto', () => ({
  generateKeyPair: vi.fn(() => ({
    privateKeyPem: '-----BEGIN RSA PRIVATE KEY-----\nMOCK\n-----END RSA PRIVATE KEY-----',
    publicKeyPem: '-----BEGIN PUBLIC KEY-----\nMOCK\n-----END PUBLIC KEY-----',
    fingerprint: 'a'.repeat(64),
  })),
  createCSR: vi.fn(
    () => '-----BEGIN CERTIFICATE REQUEST-----\nMOCK\n-----END CERTIFICATE REQUEST-----'
  ),
  createPKCS12: vi.fn(() => new Blob(['mock'], { type: 'application/x-pkcs12' })),
  downloadOnce: vi.fn(),
  downloadPem: vi.fn(),
}));

// Mock apiService
vi.mock('../../services/api', () => ({
  apiService: {
    signCSR: vi.fn(() =>
      Promise.resolve({
        signed_certificate_pem: '-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----',
        subject_dn: 'CN=test-client,OU=Test Tenant,O=STOA Platform',
        issuer_dn: 'CN=test-tenant-ca,OU=Test Tenant,O=STOA Platform',
        validity_days: 365,
      })
    ),
  },
}));

// Mock Toast
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: mockToastSuccess,
    error: mockToastError,
  }),
}));

// Mock Button
vi.mock('@stoa/shared/components/Button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    loading,
    ...props
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    loading?: boolean;
    className?: string;
    variant?: string;
    size?: string;
  }) => (
    <button onClick={onClick} disabled={disabled || loading} data-testid={props.className}>
      {children}
    </button>
  ),
}));

describe('CertificateGenerationWizard', () => {
  const defaultProps = {
    tenantId: 'test-tenant',
    tenantName: 'Test Tenant',
    onClose: vi.fn(),
    onComplete: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders step 1 with common name input', () => {
    render(<CertificateGenerationWizard {...defaultProps} />);
    expect(screen.getByText('Generate Client Certificate')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. my-api-client')).toBeInTheDocument();
    expect(screen.getByText('Generate Keypair')).toBeInTheDocument();
  });

  it('shows the 3 step indicators', () => {
    render(<CertificateGenerationWizard {...defaultProps} />);
    expect(screen.getByText('Generate Keys')).toBeInTheDocument();
    expect(screen.getByText('Sign Certificate')).toBeInTheDocument();
    expect(screen.getByText('Download')).toBeInTheDocument();
  });

  it('disables generate button when common name is empty', () => {
    render(<CertificateGenerationWizard {...defaultProps} />);
    const btn = screen.getByText('Generate Keypair');
    expect(btn.closest('button')).toBeDisabled();
  });

  it('advances to step 2 after generating keypair', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('e.g. my-api-client'), 'my-client');
    await user.click(screen.getByText('Generate Keypair'));

    await waitFor(() => {
      expect(screen.getByText('RSA-4096 keypair generated')).toBeInTheDocument();
    });
    // The "Sign Certificate" text appears both as step indicator and as the action button
    const signTexts = screen.getAllByText('Sign Certificate');
    expect(signTexts.length).toBeGreaterThanOrEqual(1);
  });

  it('advances to step 3 after signing CSR', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...defaultProps} />);

    // Step 1
    await user.type(screen.getByPlaceholderText('e.g. my-api-client'), 'my-client');
    await user.click(screen.getByText('Generate Keypair'));

    // Step 2
    await waitFor(() => {
      expect(screen.getByText('RSA-4096 keypair generated')).toBeInTheDocument();
    });

    // Find and click the "Sign Certificate" button (not the step label)
    const signButtons = screen.getAllByRole('button');
    const signBtn = signButtons.find(
      (b) => b.textContent === 'Sign Certificate' && !b.className?.includes('rounded-full')
    );
    if (signBtn) await user.click(signBtn);

    // Step 3
    await waitFor(() => {
      expect(screen.getByText('Download your private key now')).toBeInTheDocument();
    });
  });

  it('shows security notice about private key staying in browser', () => {
    render(<CertificateGenerationWizard {...defaultProps} />);
    expect(
      screen.getByText(/private key is generated in the browser and never sent to the server/)
    ).toBeInTheDocument();
  });

  it('calls onClose when cancel is clicked on step 1', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...defaultProps} />);

    await user.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('shows validity days selector with default 1 year', () => {
    render(<CertificateGenerationWizard {...defaultProps} />);
    const select = screen.getByDisplayValue('1 year');
    expect(select).toBeInTheDocument();
  });

  it('prompts confirmation when closing with unsaved key', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(<CertificateGenerationWizard {...defaultProps} />);

    // Generate key to trigger unsaved state
    await user.type(screen.getByPlaceholderText('e.g. my-api-client'), 'my-client');
    await user.click(screen.getByText('Generate Keypair'));

    await waitFor(() => {
      expect(screen.getByText('RSA-4096 keypair generated')).toBeInTheDocument();
    });

    // Try to close — should be prompted
    await user.click(screen.getByText('Cancel'));
    expect(confirmSpy).toHaveBeenCalledWith(
      expect.stringContaining('private key has not been downloaded')
    );
    // onClose NOT called because user denied
    expect(defaultProps.onClose).not.toHaveBeenCalled();

    confirmSpy.mockRestore();
  });

  it('shows PKCS12 export section in download step', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...defaultProps} />);

    // Step 1 → Step 2
    await user.type(screen.getByPlaceholderText('e.g. my-api-client'), 'my-client');
    await user.click(screen.getByText('Generate Keypair'));

    await waitFor(() => {
      expect(screen.getByText('RSA-4096 keypair generated')).toBeInTheDocument();
    });

    // Step 2 → Step 3
    const signButtons = screen.getAllByRole('button');
    const signBtn = signButtons.find(
      (b) => b.textContent === 'Sign Certificate' && !b.className?.includes('rounded-full')
    );
    if (signBtn) await user.click(signBtn);

    await waitFor(() => {
      expect(screen.getByText('PKCS#12 Export (.p12)')).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText('Bundle password')).toBeInTheDocument();
  });

  it('registers beforeunload handler', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    render(<CertificateGenerationWizard {...defaultProps} />);

    expect(addSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function));
    addSpy.mockRestore();
  });
});
