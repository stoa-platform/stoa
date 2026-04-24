import { describe, expect, it } from 'vitest';
import { path } from './path';

describe('path() helper — P0-6 regression lock', () => {
  it('encodes special characters in segments', () => {
    expect(path('v1', 'a/b', 'c?d', 'é')).toBe('/v1/a%2Fb/c%3Fd/%C3%A9');
  });

  it('is a no-op on UUID segments', () => {
    const uuid = '123e4567-e89b-12d3-a456-426614174000';
    expect(path('v1', 'tenants', uuid)).toBe(`/v1/tenants/${uuid}`);
  });

  it('handles empty segments', () => {
    expect(path('v1', '')).toBe('/v1/');
  });

  it('always prefixes with a leading slash', () => {
    expect(path('v1')).toBe('/v1');
  });

  it('encodes spaces, hash, and plus', () => {
    expect(path('api', 'with space', 'with#hash', 'with+plus')).toBe(
      '/api/with%20space/with%23hash/with%2Bplus'
    );
  });
});
