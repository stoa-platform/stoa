/**
 * Tests for Certificate Validator Service (CAB-313)
 */

import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import axios from 'axios';
import {
  validateCertificate,
  validateSubscriptionRequest,
  formatCertificateDate,
  getCertificateStatusColor,
  getCertificateStatusIcon,
  type CertificateInfo,
  type CertificateValidationResult,
} from './certificateValidator';

// Mock axios module
vi.mock('axios', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    isAxiosError: vi.fn(),
  },
}));

const mockedAxiosPost = axios.post as Mock;
const mockedAxiosIsError = axios.isAxiosError as unknown as Mock;

describe('certificateValidator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('validateCertificate', () => {
    it('should return valid result for valid certificate', async () => {
      const mockResponse: CertificateValidationResult = {
        valid: true,
        certificate: {
          subject: 'CN=test.example.com',
          issuer: 'CN=Test CA',
          valid_from: '2024-01-01T00:00:00Z',
          valid_to: '2025-12-31T23:59:59Z',
          days_until_expiry: 365,
          is_valid: true,
          is_expired: false,
          expires_soon: false,
          serial_number: '1234567890',
          fingerprint_sha256: 'ab:cd:ef:...',
          key_size: 2048,
          signature_algorithm: 'sha256WithRSAEncryption',
          san: ['DNS:test.example.com'],
        },
        errors: [],
        warnings: [],
      };

      mockedAxiosPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await validateCertificate('-----BEGIN CERTIFICATE-----...');

      expect(result.valid).toBe(true);
      expect(result.certificate).toBeDefined();
      expect(result.errors).toHaveLength(0);
    });

    it('should return invalid result for invalid certificate', async () => {
      const mockResponse: CertificateValidationResult = {
        valid: false,
        certificate: null,
        errors: ['Invalid PEM format'],
        warnings: [],
      };

      mockedAxiosPost.mockResolvedValueOnce({ data: mockResponse });

      const result = await validateCertificate('invalid-data');

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Invalid PEM format');
    });

    it('should handle network errors gracefully', async () => {
      mockedAxiosPost.mockRejectedValueOnce(new Error('Network Error'));
      mockedAxiosIsError.mockReturnValue(false);

      const result = await validateCertificate('test');

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Network error: Unable to validate certificate');
    });

    it('should handle API errors with detail message', async () => {
      const axiosError = {
        response: {
          data: { detail: 'Certificate service unavailable' },
        },
      };
      mockedAxiosPost.mockRejectedValueOnce(axiosError);
      mockedAxiosIsError.mockReturnValue(true);

      const result = await validateCertificate('test');

      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Certificate service unavailable');
    });
  });

  describe('validateSubscriptionRequest', () => {
    it('should validate subscription without certificate', async () => {
      const result = await validateSubscriptionRequest('tool-id');

      expect(result.can_subscribe).toBe(true);
      expect(result.certificate_valid).toBe(true);
    });

    it('should validate subscription with valid certificate', async () => {
      const mockCertResponse: CertificateValidationResult = {
        valid: true,
        certificate: {
          subject: 'CN=client.example.com',
          issuer: 'CN=Test CA',
          valid_from: '2024-01-01T00:00:00Z',
          valid_to: '2025-12-31T23:59:59Z',
          days_until_expiry: 365,
          is_valid: true,
          is_expired: false,
          expires_soon: false,
          serial_number: '1234567890',
          fingerprint_sha256: 'ab:cd:ef:...',
          key_size: 2048,
          signature_algorithm: 'sha256WithRSAEncryption',
          san: [],
        },
        errors: [],
        warnings: [],
      };

      mockedAxiosPost.mockResolvedValueOnce({ data: mockCertResponse });

      const result = await validateSubscriptionRequest('tool-id', '-----BEGIN CERTIFICATE-----...');

      expect(result.can_subscribe).toBe(true);
      expect(result.certificate_valid).toBe(true);
      expect(result.certificate).toBeDefined();
    });

    it('should fail subscription with invalid certificate', async () => {
      const mockCertResponse: CertificateValidationResult = {
        valid: false,
        certificate: null,
        errors: ['Certificate expired'],
        warnings: [],
      };

      mockedAxiosPost.mockResolvedValueOnce({ data: mockCertResponse });

      const result = await validateSubscriptionRequest('tool-id', 'invalid-cert');

      expect(result.can_subscribe).toBe(false);
      expect(result.certificate_valid).toBe(false);
      expect(result.errors).toContain('Certificate expired');
    });

    it('should include warnings from certificate validation', async () => {
      const mockCertResponse: CertificateValidationResult = {
        valid: true,
        certificate: {
          subject: 'CN=client.example.com',
          issuer: 'CN=Test CA',
          valid_from: '2024-01-01T00:00:00Z',
          valid_to: '2024-02-01T23:59:59Z',
          days_until_expiry: 20,
          is_valid: true,
          is_expired: false,
          expires_soon: true,
          serial_number: '1234567890',
          fingerprint_sha256: 'ab:cd:ef:...',
          key_size: 2048,
          signature_algorithm: 'sha256WithRSAEncryption',
          san: [],
        },
        errors: [],
        warnings: ['Certificate expires in 20 days'],
      };

      mockedAxiosPost.mockResolvedValueOnce({ data: mockCertResponse });

      const result = await validateSubscriptionRequest('tool-id', '-----BEGIN CERTIFICATE-----...');

      expect(result.can_subscribe).toBe(true);
      expect(result.warnings).toContain('Certificate expires in 20 days');
    });
  });

  describe('formatCertificateDate', () => {
    it('should format date correctly', () => {
      const dateString = '2024-06-15T14:30:00Z';
      const formatted = formatCertificateDate(dateString);

      expect(formatted).toContain('Jun');
      expect(formatted).toContain('15');
      expect(formatted).toContain('2024');
    });
  });

  describe('getCertificateStatusColor', () => {
    it('should return red for expired certificate', () => {
      const cert: CertificateInfo = {
        subject: 'CN=test',
        issuer: 'CN=CA',
        valid_from: '2023-01-01T00:00:00Z',
        valid_to: '2023-12-31T23:59:59Z',
        days_until_expiry: -30,
        is_valid: false,
        is_expired: true,
        expires_soon: false,
        serial_number: '123',
        fingerprint_sha256: 'abc',
        key_size: 2048,
        signature_algorithm: 'sha256',
        san: [],
      };

      expect(getCertificateStatusColor(cert)).toBe('text-red-600');
    });

    it('should return amber for soon-to-expire certificate', () => {
      const cert: CertificateInfo = {
        subject: 'CN=test',
        issuer: 'CN=CA',
        valid_from: '2024-01-01T00:00:00Z',
        valid_to: '2024-02-15T23:59:59Z',
        days_until_expiry: 15,
        is_valid: true,
        is_expired: false,
        expires_soon: true,
        serial_number: '123',
        fingerprint_sha256: 'abc',
        key_size: 2048,
        signature_algorithm: 'sha256',
        san: [],
      };

      expect(getCertificateStatusColor(cert)).toBe('text-amber-600');
    });

    it('should return green for valid certificate', () => {
      const cert: CertificateInfo = {
        subject: 'CN=test',
        issuer: 'CN=CA',
        valid_from: '2024-01-01T00:00:00Z',
        valid_to: '2025-12-31T23:59:59Z',
        days_until_expiry: 365,
        is_valid: true,
        is_expired: false,
        expires_soon: false,
        serial_number: '123',
        fingerprint_sha256: 'abc',
        key_size: 2048,
        signature_algorithm: 'sha256',
        san: [],
      };

      expect(getCertificateStatusColor(cert)).toBe('text-green-600');
    });
  });

  describe('getCertificateStatusIcon', () => {
    it('should return error for expired', () => {
      const cert: CertificateInfo = {
        subject: 'CN=test',
        issuer: 'CN=CA',
        valid_from: '2023-01-01T00:00:00Z',
        valid_to: '2023-12-31T23:59:59Z',
        days_until_expiry: -30,
        is_valid: false,
        is_expired: true,
        expires_soon: false,
        serial_number: '123',
        fingerprint_sha256: 'abc',
        key_size: 2048,
        signature_algorithm: 'sha256',
        san: [],
      };

      expect(getCertificateStatusIcon(cert)).toBe('error');
    });

    it('should return warning for expires soon', () => {
      const cert: CertificateInfo = {
        subject: 'CN=test',
        issuer: 'CN=CA',
        valid_from: '2024-01-01T00:00:00Z',
        valid_to: '2024-02-15T23:59:59Z',
        days_until_expiry: 15,
        is_valid: true,
        is_expired: false,
        expires_soon: true,
        serial_number: '123',
        fingerprint_sha256: 'abc',
        key_size: 2048,
        signature_algorithm: 'sha256',
        san: [],
      };

      expect(getCertificateStatusIcon(cert)).toBe('warning');
    });

    it('should return success for valid', () => {
      const cert: CertificateInfo = {
        subject: 'CN=test',
        issuer: 'CN=CA',
        valid_from: '2024-01-01T00:00:00Z',
        valid_to: '2025-12-31T23:59:59Z',
        days_until_expiry: 365,
        is_valid: true,
        is_expired: false,
        expires_soon: false,
        serial_number: '123',
        fingerprint_sha256: 'abc',
        key_size: 2048,
        signature_algorithm: 'sha256',
        san: [],
      };

      expect(getCertificateStatusIcon(cert)).toBe('success');
    });
  });
});
