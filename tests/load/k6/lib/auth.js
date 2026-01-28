// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
// =============================================================================
// K6 Keycloak Authentication Helper
// =============================================================================
// STOA Platform - Phase 9.5 Production Readiness
// Handles OAuth2 token acquisition for authenticated load tests
// =============================================================================

import http from 'k6/http';
import { check, fail } from 'k6';
import { getEnv, headers } from './config.js';

// Token cache to avoid re-authentication on every request
let cachedToken = null;
let tokenExpiry = 0;

/**
 * Get OAuth2 access token from Keycloak
 * Uses client credentials or password grant based on credentials provided
 */
export function getAccessToken(forceRefresh = false) {
  const now = Date.now();

  // Return cached token if still valid (with 30s buffer)
  if (!forceRefresh && cachedToken && tokenExpiry > now + 30000) {
    return cachedToken;
  }

  const env = getEnv();
  const tokenUrl = `${env.keycloakUrl}/realms/${env.realm}/protocol/openid-connect/token`;

  // Check for credentials in environment
  const username = __ENV.TEST_USER || __ENV.KEYCLOAK_USER;
  const password = __ENV.TEST_PASSWORD || __ENV.KEYCLOAK_PASSWORD;
  const clientSecret = __ENV.CLIENT_SECRET || __ENV.KEYCLOAK_CLIENT_SECRET;

  let payload;

  if (username && password) {
    // Password grant (user authentication)
    payload = {
      grant_type: 'password',
      client_id: env.clientId,
      username: username,
      password: password,
    };
    if (clientSecret) {
      payload.client_secret = clientSecret;
    }
  } else if (clientSecret) {
    // Client credentials grant (service account)
    payload = {
      grant_type: 'client_credentials',
      client_id: env.clientId,
      client_secret: clientSecret,
    };
  } else {
    console.warn('No authentication credentials provided. Running unauthenticated tests.');
    return null;
  }

  const response = http.post(tokenUrl, payload, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    timeout: '30s',
  });

  const success = check(response, {
    'token request successful': (r) => r.status === 200,
    'token response has access_token': (r) => {
      try {
        return JSON.parse(r.body).access_token !== undefined;
      } catch {
        return false;
      }
    },
  });

  if (!success) {
    console.error(`Token request failed: ${response.status} - ${response.body}`);
    fail('Failed to obtain access token');
  }

  const tokenData = JSON.parse(response.body);
  cachedToken = tokenData.access_token;
  tokenExpiry = now + (tokenData.expires_in * 1000);

  return cachedToken;
}

/**
 * Get authorization headers with Bearer token
 */
export function getAuthHeaders() {
  const token = getAccessToken();

  if (!token) {
    return headers.json;
  }

  return {
    ...headers.json,
    'Authorization': `Bearer ${token}`,
  };
}

/**
 * Make authenticated GET request
 */
export function authGet(url, params = {}) {
  return http.get(url, {
    ...params,
    headers: { ...getAuthHeaders(), ...(params.headers || {}) },
  });
}

/**
 * Make authenticated POST request
 */
export function authPost(url, body, params = {}) {
  const payload = typeof body === 'string' ? body : JSON.stringify(body);
  return http.post(url, payload, {
    ...params,
    headers: { ...getAuthHeaders(), ...(params.headers || {}) },
  });
}

/**
 * Make authenticated PUT request
 */
export function authPut(url, body, params = {}) {
  const payload = typeof body === 'string' ? body : JSON.stringify(body);
  return http.put(url, payload, {
    ...params,
    headers: { ...getAuthHeaders(), ...(params.headers || {}) },
  });
}

/**
 * Make authenticated DELETE request
 */
export function authDelete(url, params = {}) {
  return http.del(url, null, {
    ...params,
    headers: { ...getAuthHeaders(), ...(params.headers || {}) },
  });
}

/**
 * Invalidate cached token (for testing token refresh)
 */
export function invalidateToken() {
  cachedToken = null;
  tokenExpiry = 0;
}

export default {
  getAccessToken,
  getAuthHeaders,
  authGet,
  authPost,
  authPut,
  authDelete,
  invalidateToken,
};
