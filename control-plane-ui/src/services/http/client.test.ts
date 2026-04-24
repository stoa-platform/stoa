import { describe, expect, it } from 'vitest';

import { createHttpInstance } from './client';
import { config } from '../../config';

describe('createHttpInstance (P1-2 — default timeout)', () => {
  it('sets baseURL from config', () => {
    const instance = createHttpInstance();
    expect(instance.defaults.baseURL).toBe(config.api.baseUrl);
  });

  it('sets a non-zero default timeout (30_000 unless overridden)', () => {
    const instance = createHttpInstance();
    // Default must NOT be 0 (axios default) — that leaves hanging requests alive
    // forever when a backend pod stalls (P1-2).
    expect(instance.defaults.timeout).toBeGreaterThan(0);
    // Default constant from config.ts is 30_000; allow override via env.
    expect(instance.defaults.timeout).toBe(config.api.timeout);
  });

  it('sets JSON content-type header', () => {
    const instance = createHttpInstance();
    expect(instance.defaults.headers['Content-Type']).toBe('application/json');
  });
});
