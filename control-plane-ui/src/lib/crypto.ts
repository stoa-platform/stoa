/**
 * Client-side certificate helpers — WebCrypto keygen + node-forge CSR/PKCS12 (CAB-1788).
 *
 * All private key material stays in browser memory until explicitly downloaded.
 * Blob URLs are revoked after first use.
 */

import forge from 'node-forge';

export interface GeneratedKeyPair {
  privateKeyPem: string;
  publicKeyPem: string;
  fingerprint: string;
}

export interface GeneratedCertBundle {
  privateKeyPem: string;
  signedCertificatePem: string;
  csrPem: string;
}

/**
 * Generate an RSA-4096 keypair using node-forge (synchronous but runs in ~2-4s).
 * Returns PEM-encoded private/public keys and SHA-256 fingerprint of the public key.
 */
export function generateKeyPair(): GeneratedKeyPair {
  const keypair = forge.pki.rsa.generateKeyPair({ bits: 4096, e: 0x10001 });

  const privateKeyPem = forge.pki.privateKeyToPem(keypair.privateKey);
  const publicKeyPem = forge.pki.publicKeyToPem(keypair.publicKey);

  // SHA-256 fingerprint of the DER-encoded public key
  const pubDer = forge.asn1.toDer(forge.pki.publicKeyToAsn1(keypair.publicKey)).getBytes();
  const md = forge.md.sha256.create();
  md.update(pubDer);
  const fingerprint = md.digest().toHex();

  return { privateKeyPem, publicKeyPem, fingerprint };
}

/**
 * Create a PKCS#10 CSR from a PEM private key with the given subject fields.
 */
export function createCSR(
  privateKeyPem: string,
  subject: { commonName: string; organization?: string; organizationalUnit?: string }
): string {
  const privateKey = forge.pki.privateKeyFromPem(privateKeyPem);
  const publicKey = forge.pki.setRsaPublicKey(privateKey.n, privateKey.e);

  const csr = forge.pki.createCertificationRequest();
  csr.publicKey = publicKey;

  const attrs: forge.pki.CertificateField[] = [];
  if (subject.organization) {
    attrs.push({ name: 'organizationName', value: subject.organization });
  }
  if (subject.organizationalUnit) {
    attrs.push({ name: 'organizationalUnitName', value: subject.organizationalUnit });
  }
  attrs.push({ name: 'commonName', value: subject.commonName });
  csr.setSubject(attrs);

  csr.sign(privateKey, forge.md.sha256.create());

  return forge.pki.certificationRequestToPem(csr);
}

/**
 * Create a PKCS#12 (.p12) bundle from a private key and signed certificate.
 * Returns a Blob suitable for one-time download.
 */
export function createPKCS12(
  privateKeyPem: string,
  certificatePem: string,
  password: string
): Blob {
  const privateKey = forge.pki.privateKeyFromPem(privateKeyPem);
  const certificate = forge.pki.certificateFromPem(certificatePem);

  const p12Asn1 = forge.pkcs12.toPkcs12Asn1(privateKey, [certificate], password, {
    algorithm: '3des',
    friendlyName: certificate.subject.getField('CN')?.value || 'client-cert',
  });

  const p12Der = forge.asn1.toDer(p12Asn1).getBytes();
  const bytes = new Uint8Array(p12Der.length);
  for (let i = 0; i < p12Der.length; i++) {
    bytes[i] = p12Der.charCodeAt(i);
  }

  return new Blob([bytes], { type: 'application/x-pkcs12' });
}

/**
 * Create a one-time download link. The blob URL is revoked after the link is clicked.
 */
export function downloadOnce(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke immediately — one-time download
  URL.revokeObjectURL(url);
}

/**
 * Download a PEM string as a file.
 */
export function downloadPem(pem: string, filename: string): void {
  const blob = new Blob([pem], { type: 'application/x-pem-file' });
  downloadOnce(blob, filename);
}
