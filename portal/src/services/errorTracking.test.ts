import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We need to control import.meta.env.VITE_ERROR_TRACKING_ENDPOINT
// Vitest allows overriding import.meta.env before import

describe('errorTracking', () => {
  const originalFetch = globalThis.fetch;
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn().mockResolvedValue({ ok: true });
    globalThis.fetch = mockFetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.resetModules();
  });

  describe('captureException', () => {
    it('does nothing when endpoint is not set', async () => {
      vi.stubEnv('VITE_ERROR_TRACKING_ENDPOINT', '');

      const { captureException } = await import('./errorTracking');
      captureException(new Error('test'));

      expect(mockFetch).not.toHaveBeenCalled();
    });

    it('sends error to endpoint when configured', async () => {
      vi.stubEnv('VITE_ERROR_TRACKING_ENDPOINT', 'https://errors.example.com/capture');

      const { captureException } = await import('./errorTracking');
      const error = new Error('Something broke');
      captureException(error, { extra: { userId: 'u-1' } });

      expect(mockFetch).toHaveBeenCalledWith('https://errors.example.com/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: expect.stringContaining('"message":"Something broke"'),
      });
    });

    it('silently catches fetch errors', async () => {
      vi.stubEnv('VITE_ERROR_TRACKING_ENDPOINT', 'https://errors.example.com/capture');
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const { captureException } = await import('./errorTracking');

      // Should not throw
      expect(() => captureException(new Error('test'))).not.toThrow();
    });
  });

  describe('captureErrorBoundary', () => {
    it('calls captureException with componentStack', async () => {
      vi.stubEnv('VITE_ERROR_TRACKING_ENDPOINT', 'https://errors.example.com/capture');

      const { captureErrorBoundary } = await import('./errorTracking');
      const error = new Error('Render failed');
      const errorInfo = { componentStack: '\n    in MyComponent\n    in App', digest: undefined };
      captureErrorBoundary(error, errorInfo);

      expect(mockFetch).toHaveBeenCalledWith('https://errors.example.com/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: expect.stringContaining('"componentStack"'),
      });
    });
  });
});
