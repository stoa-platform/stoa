/**
 * DPoP (RFC 9449) step definitions for STOA E2E Tests
 *
 * Generates DPoP proofs (JWT) using Node.js crypto APIs and sends requests
 * with DPoP headers to validate the gateway's sender-constrained token enforcement.
 *
 * IMPORTANT: Reusable assertion steps (I receive a {int} response, I receive a {int} error,
 * the error message contains {string}) are defined in gateway.steps.ts — do NOT re-declare here.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { gatewayState } from './gateway-state';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const { Given, When } = createBdd(test);

// ---------------------------------------------------------------------------
// Test state
// ---------------------------------------------------------------------------

let dpopAccessToken: string | null = null;
let dpopKeyPair: crypto.KeyPairKeyObjectResult | null = null;

// mTLS dual-binding state
let mtlsFingerprint: string | null = null;
let mtlsHeaders: Record<string, string> = {};

// Auth URL for token acquisition
const AUTH_URL = process.env.STOA_AUTH_URL || 'https://auth.gostoa.dev';
const CERTS_DIR = path.resolve(__dirname, '../../scripts/demo/certs');

// ---------------------------------------------------------------------------
// Helpers — DPoP proof generation (RFC 9449)
// ---------------------------------------------------------------------------

/**
 * Generate an ES256 key pair for DPoP proof signing.
 */
function generateDpopKeyPair(): crypto.KeyPairKeyObjectResult {
  return crypto.generateKeyPairSync('ec', { namedCurve: 'P-256' });
}

/**
 * Export the public key as JWK (no private components).
 */
function exportPublicJwk(keyPair: crypto.KeyPairKeyObjectResult): Record<string, string> {
  const jwk = keyPair.publicKey.export({ format: 'jwk' }) as Record<string, unknown>;
  return {
    kty: jwk.kty as string,
    crv: jwk.crv as string,
    x: jwk.x as string,
    y: jwk.y as string,
  };
}

/**
 * Export the full key (including private d) as JWK — used to test private key rejection.
 */
function exportFullJwk(keyPair: crypto.KeyPairKeyObjectResult): Record<string, string> {
  const jwk = keyPair.privateKey.export({ format: 'jwk' }) as Record<string, unknown>;
  return {
    kty: jwk.kty as string,
    crv: jwk.crv as string,
    x: jwk.x as string,
    y: jwk.y as string,
    d: jwk.d as string,
  };
}

/**
 * Base64url encode a buffer or string.
 */
function base64url(input: Buffer | string): string {
  const buf = typeof input === 'string' ? Buffer.from(input) : input;
  return buf.toString('base64url');
}

/**
 * Compute ath (access token hash) per RFC 9449: base64url(sha256(ascii(token))).
 */
function computeAth(accessToken: string): string {
  const hash = crypto.createHash('sha256').update(accessToken, 'ascii').digest();
  return base64url(hash);
}

interface DpopProofOptions {
  method: string;
  uri: string;
  accessToken?: string;
  keyPair?: crypto.KeyPairKeyObjectResult;
  algorithm?: string;
  includeAth?: boolean;
  wrongAth?: boolean;
  iatOffset?: number; // seconds offset from now (negative = past, positive = future)
  jti?: string;
  includePrivateKey?: boolean;
}

/**
 * Build a DPoP proof JWT per RFC 9449.
 *
 * Header: { typ: "dpop+jwt", alg: "ES256", jwk: <public-key> }
 * Payload: { jti: <unique>, htm: <method>, htu: <uri>, iat: <now>, ath: <hash> }
 */
function buildDpopProof(options: DpopProofOptions): string {
  const kp = options.keyPair || dpopKeyPair!;
  const alg = options.algorithm || 'ES256';
  const jti = options.jti || crypto.randomUUID();
  const iat = Math.floor(Date.now() / 1000) + (options.iatOffset || 0);

  // JWK: public only unless testing private key rejection
  const jwk = options.includePrivateKey ? exportFullJwk(kp) : exportPublicJwk(kp);

  // Header
  const header = { typ: 'dpop+jwt', alg, jwk };
  const headerB64 = base64url(JSON.stringify(header));

  // Payload
  const payload: Record<string, unknown> = {
    jti,
    htm: options.method,
    htu: options.uri,
    iat,
  };

  if (options.includeAth !== false && options.accessToken) {
    payload.ath = options.wrongAth
      ? base64url(crypto.randomBytes(32)) // deliberately wrong hash
      : computeAth(options.accessToken);
  }

  const payloadB64 = base64url(JSON.stringify(payload));

  // Sign
  const signingInput = `${headerB64}.${payloadB64}`;
  const sign = crypto.createSign('SHA256');
  sign.update(signingInput);
  const signature = sign.sign(
    { key: kp.privateKey, dsaEncoding: 'ieee-p1363' },
  );
  const signatureB64 = base64url(signature);

  return `${headerB64}.${payloadB64}.${signatureB64}`;
}

/**
 * Send an HTTP request to the gateway with optional DPoP and mTLS headers.
 */
async function sendGatewayRequest(
  request: any,
  methodAndPath: string,
  dpopProof?: string,
  extraHeaders?: Record<string, string>,
): Promise<{ status: number; body: any }> {
  const [method, ...pathParts] = methodAndPath.split(' ');
  const urlPath = pathParts.join(' ');
  const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
  const fullUrl = `${baseUrl}${urlPath}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (dpopAccessToken) {
    headers['Authorization'] = `DPoP ${dpopAccessToken}`;
  }

  if (dpopProof) {
    headers['DPoP'] = dpopProof;
  }

  if (extraHeaders) {
    Object.assign(headers, extraHeaders);
  }

  const requestBody = method === 'POST' ? JSON.stringify({ tool: 'echo', input: {} }) : undefined;

  try {
    const response = await request[method.toLowerCase()](fullUrl, {
      headers,
      data: requestBody,
    });
    let body: any;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    return { status: response.status(), body };
  } catch (error: any) {
    return { status: 0, body: { error: error.message } };
  }
}

// ---------------------------------------------------------------------------
// Background steps
// ---------------------------------------------------------------------------

Given(
  'I have a DPoP-bound access token for consumer {string}',
  async ({ request }, _consumerId: string) => {
    // 1. Generate fresh ES256 key pair
    dpopKeyPair = generateDpopKeyPair();

    // 2. Build DPoP proof for the token endpoint
    const tokenUrl = `${AUTH_URL}/realms/stoa/protocol/openid-connect/token`;
    const proof = buildDpopProof({
      method: 'POST',
      uri: tokenUrl,
      keyPair: dpopKeyPair,
    });

    // 3. Request DPoP-bound token from Keycloak
    const clientId = process.env.DPOP_E2E_CLIENT_ID || 'stoa-e2e-dpop';
    const clientSecret = process.env.DPOP_E2E_CLIENT_SECRET || 'dpop-e2e-dev-secret';

    const tokenResponse = await request.fetch(tokenUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        DPoP: proof,
      },
      data: `grant_type=client_credentials&client_id=${encodeURIComponent(clientId)}&client_secret=${encodeURIComponent(clientSecret)}`,
    });

    if (!tokenResponse.ok()) {
      const errorBody = await tokenResponse.text();
      throw new Error(
        `DPoP token acquisition failed (${tokenResponse.status()}): ${errorBody}`
      );
    }

    const tokenData = await tokenResponse.json();
    dpopAccessToken = tokenData.access_token;

    // Reset shared state
    gatewayState.lastResponse = null;
    mtlsFingerprint = null;
    mtlsHeaders = {};
  },
);

Given(
  'I also have mTLS credentials for consumer {string}',
  async ({}, consumerId: string) => {
    // Load mTLS fingerprint for dual-binding scenarios
    const fingerprintFile = path.resolve(CERTS_DIR, `${consumerId}.fingerprint`);
    if (fs.existsSync(fingerprintFile)) {
      mtlsFingerprint = fs.readFileSync(fingerprintFile, 'utf-8').trim();
    } else {
      mtlsFingerprint = process.env.TEST_MTLS_FINGERPRINT || 'test-fingerprint-sha256';
    }

    mtlsHeaders = {
      'X-SSL-Client-Verify': 'SUCCESS',
      'X-SSL-Client-Fingerprint': mtlsFingerprint,
      'X-SSL-Client-S-DN': `CN=${consumerId}`,
      'X-SSL-Client-I-DN': 'CN=STOA Test CA',
    };
  },
);

// ---------------------------------------------------------------------------
// When steps — DPoP-specific actions
// ---------------------------------------------------------------------------

When(
  'I send a DPoP-protected request to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I call {string} without DPoP proof',
  async ({ request }, methodAndPath: string) => {
    // Send request with DPoP token scheme but no DPoP header
    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath);
  },
);

When(
  'I send a DPoP proof with algorithm {string} to {string}',
  async ({ request }, algorithm: string, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    // For HS256: we build a structurally valid JWT but with symmetric alg
    // The gateway should reject it before signature verification
    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
      algorithm,
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send an expired DPoP proof to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
      iatOffset: -600, // 10 minutes in the past (max_age_secs default is 300)
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send a future-dated DPoP proof to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
      iatOffset: 120, // 2 minutes in the future (clock_skew_secs default is 30)
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send a DPoP proof with htm {string} to {string}',
  async ({ request }, wrongMethod: string, methodAndPath: string) => {
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    // Use the WRONG method in the proof while the actual request uses the correct one
    const proof = buildDpopProof({
      method: wrongMethod.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send a DPoP proof with wrong htu to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');

    // Use a completely wrong URI in the proof
    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: 'https://evil.example.com/stolen-token',
      accessToken: dpopAccessToken!,
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send a DPoP proof and replay it to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');
    const fixedJti = crypto.randomUUID();

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
      jti: fixedJti,
    });

    // First request — should succeed (or at least not be a replay error)
    await sendGatewayRequest(request, methodAndPath, proof);

    // Second request with SAME jti — should be detected as replay
    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send a DPoP proof without ath claim to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
      includeAth: false,
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send a DPoP proof with wrong ath to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
      wrongAth: true,
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);

When(
  'I send a dual-bound request with mTLS and DPoP to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
    });

    // Send with both DPoP proof AND mTLS headers
    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof, mtlsHeaders);
  },
);

When(
  'I send a DPoP proof with private key in jwk to {string}',
  async ({ request }, methodAndPath: string) => {
    const [method] = methodAndPath.split(' ');
    const baseUrl = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
    const urlPath = methodAndPath.split(' ').slice(1).join(' ');

    const proof = buildDpopProof({
      method: method.toUpperCase(),
      uri: `${baseUrl}${urlPath}`,
      accessToken: dpopAccessToken!,
      includePrivateKey: true,
    });

    gatewayState.lastResponse = await sendGatewayRequest(request, methodAndPath, proof);
  },
);
