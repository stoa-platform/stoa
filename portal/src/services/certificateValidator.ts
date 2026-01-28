// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Certificate Validation Service (CAB-313)
 *
 * Client-side service for validating certificates before subscription.
 * Communicates with the Control Plane API certificate validation endpoint.
 */

import axios from 'axios';
import { config } from '../config';

export interface CertificateInfo {
  subject: string;
  issuer: string;
  valid_from: string;
  valid_to: string;
  days_until_expiry: number;
  is_valid: boolean;
  is_expired: boolean;
  expires_soon: boolean;
  serial_number: string;
  fingerprint_sha256: string;
  key_size: number | null;
  signature_algorithm: string;
  san: string[];
}

export interface CertificateValidationResult {
  valid: boolean;
  certificate: CertificateInfo | null;
  errors: string[];
  warnings: string[];
}

export interface SubscriptionRequirements {
  requires_mtls: boolean;
  scopes_required: string[];
  tier_minimum: 'free' | 'basic' | 'premium';
  quota_available: number;
}

export interface SubscriptionValidationResult {
  can_subscribe: boolean;
  certificate_valid: boolean;
  requirements_met: boolean;
  errors: string[];
  warnings: string[];
  certificate?: CertificateInfo;
}

const API_BASE_URL = config.api.baseUrl || '/api';

/**
 * Validate a PEM certificate string
 */
export async function validateCertificate(pemData: string): Promise<CertificateValidationResult> {
  try {
    const response = await axios.post<CertificateValidationResult>(
      `${API_BASE_URL}/v1/certificates/validate`,
      { pem_data: pemData }
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response) {
      return {
        valid: false,
        certificate: null,
        errors: [error.response.data?.detail || 'Failed to validate certificate'],
        warnings: [],
      };
    }
    return {
      valid: false,
      certificate: null,
      errors: ['Network error: Unable to validate certificate'],
      warnings: [],
    };
  }
}

/**
 * Upload and validate a certificate file
 */
export async function uploadCertificate(file: File): Promise<CertificateValidationResult> {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await axios.post<CertificateValidationResult>(
      `${API_BASE_URL}/v1/certificates/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response) {
      return {
        valid: false,
        certificate: null,
        errors: [error.response.data?.detail || 'Failed to upload certificate'],
        warnings: [],
      };
    }
    return {
      valid: false,
      certificate: null,
      errors: ['Network error: Unable to upload certificate'],
      warnings: [],
    };
  }
}

/**
 * Validate subscription request with optional certificate
 */
export async function validateSubscriptionRequest(
  _toolId: string,
  certificate?: string
): Promise<SubscriptionValidationResult> {
  const errors: string[] = [];
  const warnings: string[] = [];
  let certificateValid = true;
  let certificateInfo: CertificateInfo | undefined;

  // If certificate provided, validate it first
  if (certificate) {
    const certResult = await validateCertificate(certificate);

    if (!certResult.valid) {
      certificateValid = false;
      errors.push(...certResult.errors);
    }

    warnings.push(...certResult.warnings);

    if (certResult.certificate) {
      certificateInfo = certResult.certificate;
    }
  }

  // TODO: Fetch tool requirements and validate against them
  // For now, we just validate the certificate if provided

  return {
    can_subscribe: errors.length === 0,
    certificate_valid: certificateValid,
    requirements_met: true, // TODO: Implement requirements check
    errors,
    warnings,
    certificate: certificateInfo,
  };
}

/**
 * Check if certificate service is available
 */
export async function checkCertificateServiceHealth(): Promise<{
  available: boolean;
  cryptography_available: boolean;
}> {
  try {
    const response = await axios.get<{
      status: string;
      cryptography_available: boolean;
    }>(`${API_BASE_URL}/v1/certificates/health`);

    return {
      available: response.data.status === 'healthy',
      cryptography_available: response.data.cryptography_available,
    };
  } catch {
    return {
      available: false,
      cryptography_available: false,
    };
  }
}

/**
 * Format a date for display
 */
export function formatCertificateDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Get status color class based on certificate validity
 */
export function getCertificateStatusColor(cert: CertificateInfo): string {
  if (cert.is_expired) return 'text-red-600';
  if (cert.expires_soon) return 'text-amber-600';
  if (cert.is_valid) return 'text-green-600';
  return 'text-gray-600';
}

/**
 * Get status icon name based on certificate validity
 */
export function getCertificateStatusIcon(cert: CertificateInfo): 'error' | 'warning' | 'success' {
  if (cert.is_expired) return 'error';
  if (cert.expires_soon) return 'warning';
  if (cert.is_valid) return 'success';
  return 'error';
}
