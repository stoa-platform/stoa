import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Schemas } from '@stoa/shared/api-types';
import type { TenantCAInfo } from '../../types';
import { CertificateGenerationWizard } from '../CertificateGenerationWizard';
import { apiService } from '../../services/api';
import { createCSR, createPKCS12, downloadOnce, generateKeyPair } from '../../lib/crypto';

// No cryptography, certificate material, network or file download in these UI tests.
vi.mock('../../lib/crypto', () => ({
  generateKeyPair: vi.fn(),
  createCSR: vi.fn(),
  createPKCS12: vi.fn(),
  downloadOnce: vi.fn(),
  downloadPem: vi.fn(),
}));
vi.mock('../../services/api', () => ({
  apiService: { getTenantCA: vi.fn(), generateTenantCA: vi.fn(), signCSR: vi.fn() },
}));
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ error: vi.fn(), success: vi.fn() }),
}));

const keyPair = {
  privateKeyPem: 'fixture-private',
  publicKeyPem: 'fixture-public',
  fingerprint: 'a'.repeat(64),
};
const certificate: Schemas['CSRSignResponse'] = {
  id: 'fixture-id',
  serial_number: 'fixture-serial',
  fingerprint_sha256: 'b'.repeat(64),
  not_before: '2026-01-01T00:00:00Z',
  not_after: '2026-06-30T00:00:00Z',
  status: 'active',
  signed_certificate_pem: 'fixture-certificate',
  subject_dn: 'fixture-subject',
  issuer_dn: 'fixture-issuer',
  validity_days: 180,
};
const props = {
  tenantId: 'fixture-tenant',
  tenantName: 'Fixture Tenant',
  onClose: vi.fn(),
  onComplete: vi.fn(),
};
const cn = () => screen.getByRole('textbox', { name: /Common Name/ });
const validity = () => screen.getByRole('combobox', { name: 'Validity (days)' });
const button = (name: string) => screen.getByRole('button', { name });

async function goToSign(user: ReturnType<typeof userEvent.setup>) {
  await user.type(cn(), '  fixture-client  ');
  await user.selectOptions(validity(), '180');
  await user.click(button('Generate Keypair'));
  await screen.findByRole('button', { name: 'Sign Certificate' });
}
async function goToDownload(user: ReturnType<typeof userEvent.setup>) {
  await goToSign(user);
  await user.click(button('Sign Certificate'));
  await screen.findByRole('button', { name: 'Export .p12' });
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(generateKeyPair).mockReturnValue(keyPair);
  vi.mocked(createCSR).mockReturnValue('fixture-request');
  vi.mocked(createPKCS12).mockReturnValue(new Blob(['fixture-bundle']));
  vi.mocked(apiService.getTenantCA).mockResolvedValue({
    tenant_id: 'fixture-tenant',
    subject_dn: 'fixture-ca-subject',
    serial_number: 'fixture-ca-serial',
    not_before: certificate.not_before,
    not_after: certificate.not_after,
    key_algorithm: 'RSA-4096',
    fingerprint_sha256: 'c'.repeat(64),
    ca_certificate_pem: 'fixture-ca-certificate',
    status: 'active',
  } satisfies TenantCAInfo);
  vi.mocked(apiService.signCSR).mockResolvedValue(certificate);
});
afterEach(() => vi.useRealTimers());

describe('regression/CAB-2298 certificate wizard steps', () => {
  it('labels required fields and blocks empty or whitespace-only CN progression', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...props} />);
    expect(cn()).toBeRequired();
    expect(validity()).toHaveValue('365');
    expect(button('Generate Keypair')).toBeDisabled();
    await user.type(cn(), '   ');
    await user.tab();
    expect(button('Generate Keypair')).toBeDisabled();
    expect(cn()).toHaveAttribute('aria-invalid', 'true');
    expect(cn()).toHaveAccessibleDescription('Enter a Common Name for the certificate subject');
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a Common Name');
    await user.type(cn(), 'fixture-client');
    expect(cn()).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(button('Generate Keypair')).toBeEnabled();
    expect(generateKeyPair).not.toHaveBeenCalled();
    expect(apiService.signCSR).not.toHaveBeenCalled();
  });

  it('freezes inputs and prevents duplicate generation and dismissal while pending', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...props} />);
    await user.type(cn(), 'fixture-client');
    fireEvent.click(button('Generate Keypair'));
    const pending = button('Generating RSA-4096 keypair...');
    expect(pending).toBeDisabled();
    expect(cn()).toBeDisabled();
    expect(validity()).toBeDisabled();
    expect(button('Cancel')).toBeDisabled();
    expect(button('Close dialog')).toBeDisabled();
    fireEvent.click(pending);
    fireEvent.click(button('Cancel'));
    await screen.findByRole('button', { name: 'Sign Certificate' });
    expect(generateKeyPair).toHaveBeenCalledTimes(1);
    expect(props.onClose).not.toHaveBeenCalled();
    expect(apiService.signCSR).not.toHaveBeenCalled();
  });

  it('reports a synchronous key generation failure and permits retry', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...props} />);
    await user.type(cn(), 'fixture-client');
    vi.mocked(generateKeyPair).mockImplementationOnce(() => {
      throw new Error('Fixture generation failure');
    });
    vi.useFakeTimers();
    fireEvent.click(button('Generate Keypair'));
    // The candidate throws outside the promise; capture that timer error to assert the UI state.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50).catch(() => undefined);
    });
    vi.useRealTimers();
    expect(screen.getByRole('alert')).toHaveTextContent('Fixture generation failure');
    expect(cn()).toHaveValue('fixture-client');
    expect(button('Generate Keypair')).toBeEnabled();
    await user.click(button('Generate Keypair'));
    await screen.findByRole('button', { name: 'Sign Certificate' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('returns to inputs with CN and validity preserved, then signs the revised values', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...props} />);
    await goToSign(user);
    await user.click(button('Back'));
    expect(cn()).toHaveValue('  fixture-client  ');
    expect(validity()).toHaveValue('180');
    expect(apiService.signCSR).not.toHaveBeenCalled();
    await user.clear(cn());
    await user.type(cn(), '  revised-client  ');
    await user.selectOptions(validity(), '90');
    await user.click(button('Generate Keypair'));
    await user.click(await screen.findByRole('button', { name: 'Sign Certificate' }));
    await screen.findByRole('button', { name: 'Export .p12' });
    expect(createCSR).toHaveBeenCalledWith(
      'fixture-private',
      expect.objectContaining({ commonName: 'revised-client' })
    );
    expect(apiService.signCSR).toHaveBeenCalledExactlyOnceWith(
      'fixture-tenant',
      'fixture-request',
      90
    );
    expect(apiService.generateTenantCA).not.toHaveBeenCalled();
  });

  it('prevents duplicate signing, back navigation and dismissal until the request settles', async () => {
    const user = userEvent.setup();
    let resolveSigning!: (value: typeof certificate) => void;
    vi.mocked(apiService.signCSR).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSigning = resolve;
      })
    );
    render(<CertificateGenerationWizard {...props} />);
    await goToSign(user);
    await user.click(button('Sign Certificate'));
    await waitFor(() => expect(apiService.signCSR).toHaveBeenCalledTimes(1));
    const pending = button('Signing certificate...');
    expect(pending).toBeDisabled();
    for (const name of ['Back', 'Cancel', 'Close dialog']) {
      expect(button(name)).toBeDisabled();
      fireEvent.click(button(name));
    }
    fireEvent.click(pending);
    expect(apiService.signCSR).toHaveBeenCalledTimes(1);
    expect(props.onClose).not.toHaveBeenCalled();
    expect(props.onComplete).not.toHaveBeenCalled();
    await act(async () => resolveSigning(certificate));
    expect(button('Export .p12')).toBeInTheDocument();
    expect(button('Cancel')).toBeEnabled();
  });

  it('announces signing failure, keeps the chosen subject and duration, and allows retry', async () => {
    const user = userEvent.setup();
    vi.mocked(apiService.signCSR).mockRejectedValueOnce(new Error('Fixture validation failure'));
    render(<CertificateGenerationWizard {...props} />);
    await goToSign(user);
    await user.click(button('Sign Certificate'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Fixture validation failure');
    expect(screen.getByText(/CN=\s*fixture-client/)).toBeInTheDocument();
    expect(screen.getByText(/180 days/)).toBeInTheDocument();
    expect(button('Sign Certificate')).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Export .p12' })).not.toBeInTheDocument();
    await user.click(button('Sign Certificate'));
    await screen.findByRole('button', { name: 'Export .p12' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(apiService.signCSR).toHaveBeenCalledTimes(2);
    expect(props.onComplete).not.toHaveBeenCalled();
  });

  it('requires a labelled bundle password and completes only after successful export', async () => {
    const user = userEvent.setup();
    render(<CertificateGenerationWizard {...props} />);
    await goToDownload(user);
    const password = screen.getByLabelText('Bundle password');
    expect(password).toBeRequired();
    expect(password).toHaveAttribute('type', 'password');
    expect(button('Export .p12')).toBeDisabled();
    fireEvent.click(button('Export .p12'));
    expect(createPKCS12).not.toHaveBeenCalled();
    await user.type(password, 'fixture-password');
    await user.click(button('Export .p12'));
    expect(createPKCS12).toHaveBeenCalledExactlyOnceWith(
      'fixture-private',
      'fixture-certificate',
      'fixture-password'
    );
    expect(downloadOnce).toHaveBeenCalledExactlyOnceWith(
      expect.any(Blob),
      'fixture-client-certificate.p12'
    );
    expect(screen.getByText('Certificate downloaded successfully')).toBeInTheDocument();
    expect(props.onComplete).not.toHaveBeenCalled();
    await user.click(button('Done'));
    expect(props.onComplete).toHaveBeenCalledTimes(1);
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it('announces export failure without marking the certificate downloaded and allows retry', async () => {
    const user = userEvent.setup();
    vi.mocked(createPKCS12).mockImplementationOnce(() => {
      throw new Error('Fixture export failure');
    });
    render(<CertificateGenerationWizard {...props} />);
    await goToDownload(user);
    await user.type(screen.getByLabelText('Bundle password'), 'fixture-password');
    await user.click(button('Export .p12'));
    expect(screen.getByRole('alert')).toHaveTextContent('Fixture export failure');
    expect(screen.queryByText('Certificate downloaded successfully')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Done' })).not.toBeInTheDocument();
    expect(downloadOnce).not.toHaveBeenCalled();
    expect(props.onComplete).not.toHaveBeenCalled();
    await user.click(button('Export .p12'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(downloadOnce).toHaveBeenCalledTimes(1);
    expect(button('Done')).toBeInTheDocument();
  });
});
