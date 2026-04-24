import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { applyFriendlyErrorMessage } from './errors';
import { markRedirecting, resetRedirecting } from './redirect';

vi.mock('@stoa/shared/utils', () => ({
  getFriendlyErrorMessage: (_err: unknown, fallback: string) => `friendly: ${fallback}`,
}));

describe('applyFriendlyErrorMessage (P1-16 — redirect flag gate)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetRedirecting();
  });

  afterEach(() => {
    vi.useRealTimers();
    resetRedirecting();
  });

  it('applies friendly message when not redirecting', () => {
    const err = new Error('boom');
    applyFriendlyErrorMessage(err);
    expect(err.message).toBe('friendly: boom');
  });

  it('skips friendly message while redirect flag is set (no tech flash)', () => {
    markRedirecting();
    const err = new Error('boom');
    applyFriendlyErrorMessage(err);
    expect(err.message).toBe('boom'); // unchanged
  });

  it('re-enables friendly message after the flag TTL expires', () => {
    markRedirecting(5_000);
    vi.advanceTimersByTime(5_001);

    const err = new Error('boom');
    applyFriendlyErrorMessage(err);
    expect(err.message).toBe('friendly: boom');
  });
});
