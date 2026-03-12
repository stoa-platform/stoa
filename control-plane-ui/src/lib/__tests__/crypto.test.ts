/**
 * Tests for client-side crypto helpers (CAB-1788).
 *
 * RSA-4096 keygen is slow (~3-4s), so we generate once and reuse across tests.
 * The PKCS12 test uses 2048-bit keys for speed.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import forge from 'node-forge';
import { generateKeyPair, createCSR, createPKCS12, type GeneratedKeyPair } from '../crypto';

let cachedKeyPair: GeneratedKeyPair;

beforeAll(() => {
  cachedKeyPair = generateKeyPair();
}, 15000); // 15s timeout for RSA-4096

describe('generateKeyPair', () => {
  it('returns PEM-encoded private and public keys', () => {
    expect(cachedKeyPair.privateKeyPem).toContain('RSA PRIVATE KEY');
    expect(cachedKeyPair.publicKeyPem).toContain('PUBLIC KEY');
  });

  it('returns a 64-char hex SHA-256 fingerprint', () => {
    expect(cachedKeyPair.fingerprint).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe('createCSR', () => {
  it('creates a valid PEM-encoded CSR', () => {
    const csr = createCSR(cachedKeyPair.privateKeyPem, {
      commonName: 'test-client',
      organization: 'STOA Platform',
      organizationalUnit: 'Test Tenant',
    });

    expect(csr).toContain('CERTIFICATE REQUEST');
  });

  it('produces a CSR with substantial content', () => {
    const csr = createCSR(cachedKeyPair.privateKeyPem, { commonName: 'my-api-client' });

    expect(csr).toBeTruthy();
    expect(csr.length).toBeGreaterThan(100);
  });
});

describe('createPKCS12', () => {
  it('creates a PKCS12 blob from a certificate and key', () => {
    // Use 2048-bit for speed in this test
    const keypair = forge.pki.rsa.generateKeyPair({ bits: 2048, e: 0x10001 });
    const cert = forge.pki.createCertificate();
    cert.publicKey = keypair.publicKey;
    cert.serialNumber = '01';
    cert.validity.notBefore = new Date();
    cert.validity.notAfter = new Date();
    cert.validity.notAfter.setFullYear(cert.validity.notBefore.getFullYear() + 1);
    cert.setSubject([{ name: 'commonName', value: 'test' }]);
    cert.setIssuer([{ name: 'commonName', value: 'test-ca' }]);
    cert.sign(keypair.privateKey, forge.md.sha256.create());

    const privateKeyPem = forge.pki.privateKeyToPem(keypair.privateKey);
    const certPem = forge.pki.certificateToPem(cert);

    const blob = createPKCS12(privateKeyPem, certPem, 'testpass');

    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe('application/x-pkcs12');
    expect(blob.size).toBeGreaterThan(0);
  });
});
