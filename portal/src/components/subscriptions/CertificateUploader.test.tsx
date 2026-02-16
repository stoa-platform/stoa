import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CertificateUploader } from './CertificateUploader';
import type { CertificateValidationResult } from '../../services/certificateValidator';

const mockValidResult: CertificateValidationResult = {
  valid: true,
  certificate: {
    subject: 'CN=test.example.com',
    issuer: 'CN=Test CA',
    valid_from: '2026-01-01T00:00:00Z',
    valid_to: '2027-01-01T00:00:00Z',
    days_until_expiry: 320,
    is_valid: true,
    is_expired: false,
    expires_soon: false,
    serial_number: '1234',
    fingerprint_sha256: 'AB:CD:EF:12:34',
    key_size: 2048,
    signature_algorithm: 'SHA256WithRSA',
    san: ['test.example.com', 'www.example.com'],
  },
  errors: [],
  warnings: [],
};

vi.mock('../../services/certificateValidator', () => ({
  uploadCertificate: vi.fn(),
  validateCertificate: vi.fn(),
  formatCertificateDate: vi.fn((d: string) => new Date(d).toLocaleDateString()),
}));

import { uploadCertificate, validateCertificate } from '../../services/certificateValidator';

describe('CertificateUploader', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render upload area', () => {
    render(<CertificateUploader />);
    expect(screen.getByText(/Click to upload/)).toBeInTheDocument();
    expect(screen.getByText(/PEM, CRT, CER files/)).toBeInTheDocument();
  });

  it('should show required indicator when required', () => {
    render(<CertificateUploader required />);
    expect(screen.getByText('*')).toBeInTheDocument();
  });

  it('should reject files over 1MB', async () => {
    render(<CertificateUploader />);
    const file = new File(['x'.repeat(1024 * 1025)], 'cert.pem', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => {
      expect(screen.getByText('File too large. Maximum size is 1MB.')).toBeInTheDocument();
    });
  });

  it('should reject invalid file extensions', async () => {
    render(<CertificateUploader />);
    const file = new File(['content'], 'cert.txt', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => {
      expect(screen.getByText(/Invalid file type/)).toBeInTheDocument();
    });
  });

  it('should upload and validate a valid certificate', async () => {
    vi.mocked(uploadCertificate).mockResolvedValue(mockValidResult);

    const onValidated = vi.fn();
    render(<CertificateUploader onCertificateValidated={onValidated} />);

    const file = new File(['-----BEGIN CERTIFICATE-----'], 'cert.pem', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('Valid')).toBeInTheDocument();
      expect(screen.getByText('CN=test.example.com')).toBeInTheDocument();
    });
    expect(onValidated).toHaveBeenCalledWith(mockValidResult);
  });

  it('should show certificate details after validation', async () => {
    vi.mocked(uploadCertificate).mockResolvedValue(mockValidResult);

    render(<CertificateUploader />);
    const file = new File(['cert'], 'cert.pem', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('CN=Test CA')).toBeInTheDocument();
      expect(screen.getByText('AB:CD:EF:12:34')).toBeInTheDocument();
      expect(screen.getByText('test.example.com, www.example.com')).toBeInTheDocument();
    });
  });

  it('should show expired status', async () => {
    const expiredResult = {
      ...mockValidResult,
      certificate: {
        ...mockValidResult.certificate!,
        is_valid: false,
        is_expired: true,
      },
    };
    vi.mocked(uploadCertificate).mockResolvedValue(expiredResult);

    render(<CertificateUploader />);
    const file = new File(['cert'], 'cert.pem', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('Expired')).toBeInTheDocument();
    });
  });

  it('should show expires soon status', async () => {
    const soonResult = {
      ...mockValidResult,
      certificate: {
        ...mockValidResult.certificate!,
        expires_soon: true,
        days_until_expiry: 15,
      },
    };
    vi.mocked(uploadCertificate).mockResolvedValue(soonResult);

    render(<CertificateUploader />);
    const file = new File(['cert'], 'cert.pem', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('Expires in 15 days')).toBeInTheDocument();
    });
  });

  it('should clear certificate on Clear click', async () => {
    vi.mocked(uploadCertificate).mockResolvedValue(mockValidResult);
    const onCleared = vi.fn();

    render(<CertificateUploader onCertificateCleared={onCleared} />);
    const file = new File(['cert'], 'cert.pem', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('Valid')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Clear'));
    expect(screen.getByText(/Click to upload/)).toBeInTheDocument();
    expect(onCleared).toHaveBeenCalled();
  });

  it('should validate pasted PEM content', async () => {
    vi.mocked(validateCertificate).mockResolvedValue(mockValidResult);

    render(<CertificateUploader />);
    const uploadArea = screen.getByRole('button', { name: /Upload certificate/ });
    fireEvent.paste(uploadArea, {
      clipboardData: {
        getData: () => '-----BEGIN CERTIFICATE-----\nABC\n-----END CERTIFICATE-----',
      },
    });

    await waitFor(() => {
      expect(validateCertificate).toHaveBeenCalled();
    });
  });

  it('should show warnings from validation', async () => {
    const warnResult = {
      ...mockValidResult,
      warnings: ['Certificate uses weak key size'],
    };
    vi.mocked(uploadCertificate).mockResolvedValue(warnResult);

    render(<CertificateUploader />);
    const file = new File(['cert'], 'cert.pem', { type: 'text/plain' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText('Certificate uses weak key size')).toBeInTheDocument();
    });
  });
});
