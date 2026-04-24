import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { isRedirecting, markRedirecting, resetRedirecting } from './redirect';

describe('redirect flag (P1-16 — flash-error suppression)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetRedirecting();
  });

  afterEach(() => {
    vi.useRealTimers();
    resetRedirecting();
  });

  it('starts unset', () => {
    expect(isRedirecting()).toBe(false);
  });

  it('markRedirecting() sets the flag', () => {
    markRedirecting();
    expect(isRedirecting()).toBe(true);
  });

  it('resetRedirecting() clears the flag immediately', () => {
    markRedirecting();
    resetRedirecting();
    expect(isRedirecting()).toBe(false);
  });

  it('auto-resets after the TTL (default 30s)', () => {
    markRedirecting();
    expect(isRedirecting()).toBe(true);
    vi.advanceTimersByTime(30_000);
    expect(isRedirecting()).toBe(false);
  });

  it('respects a custom TTL', () => {
    markRedirecting(5_000);
    vi.advanceTimersByTime(4_999);
    expect(isRedirecting()).toBe(true);
    vi.advanceTimersByTime(2);
    expect(isRedirecting()).toBe(false);
  });

  it('re-arming markRedirecting() clears the previous TTL', () => {
    markRedirecting(5_000);
    vi.advanceTimersByTime(4_000);
    markRedirecting(5_000); // re-arm
    vi.advanceTimersByTime(4_999);
    // Still within the new 5s window relative to the re-arm
    expect(isRedirecting()).toBe(true);
    vi.advanceTimersByTime(2);
    expect(isRedirecting()).toBe(false);
  });
});
