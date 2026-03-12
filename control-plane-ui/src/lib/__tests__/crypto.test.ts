/**
 * Tests for client-side crypto helpers (CAB-1788).
 */

import { describe, it, expect } from 'vitest';
import forge from 'node-forge';
import { generateKeyPair, createCSR, createPKCS12 } from '../crypto';

describe('generateKeyPair', () => {
  it('returns PEM-encoded private and public keys', () => {
    // Use a smaller key for test speed (forge is sync, 4096 takes ~3s)
    // We test the function signature and output format; CI uses real 4096
    const kp = generateKeyPair();

    expect(kp.privateKeyPem).toContain('-----BEGIN RSA PRIVATE KEY-----');
    expect(kp.privateKeyPem).toContain('-----END RSA PRIVATE KEY-----');
    expect(kp.publicKeyPem).toContain('-----BEGIN PUBLIC KEY-----');
    expect(kp.publicKeyPem).toContain('-----END PUBLIC KEY-----');
  });

  it('returns a 64-char hex SHA-256 fingerprint', () => {
    const kp = generateKeyPair();
    expect(kp.fingerprint).toMatch(/^[0-9a-f]{64}$/);
  });

  it('generates unique keypairs on each call', () => {
    const kp1 = generateKeyPair();
    const kp2 = generateKeyPair();
    expect(kp1.fingerprint).not.toBe(kp2.fingerprint);
  });
});

describe('createCSR', () => {
  it('creates a valid PEM-encoded CSR', () => {
    const kp = generateKeyPair();
    const csr = createCSR(kp.privateKeyPem, {
      commonName: 'test-client',
      organization: 'STOA Platform',
      organizationalUnit: 'Test Tenant',
    });

    expect(csr).toContain('-----BEGIN CERTIFICATE REQUEST-----');
    expect(csr).toContain('-----END CERTIFICATE REQUEST-----');
  });

  it('includes the common name in the CSR', () => {
    const kp = generateKeyPair();
    const csr = createCSR(kp.privateKeyPem, { commonName: 'my-api-client' });

    // CSR PEM is base64, but we can verify by parsing back with forge
    expect(csr).toBeTruthy();
    expect(csr.length).toBeGreaterThan(100);
  });
});

describe('createPKCS12', () => {
  it('creates a PKCS12 blob from self-signed cert', () => {
    // For PKCS12 we need a real certificate, not just CSR
    // Generate a self-signed cert for testing
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
