/**
 * Real-code regression lock for services/http/interceptors.ts.
 *
 * Locks: P2-1 (request error path decorates friendly-error on AxiosError
 * and skips it on unrelated throws).
 */
import axios, { AxiosError, type AxiosAdapter, type AxiosResponse } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installRequestInterceptor } from './interceptors';
import * as errorsModule from './errors';

type AdapterBehavior = (config: Parameters<AxiosAdapter>[0]) => Promise<AxiosResponse>;

function makeInstance(adapter: AdapterBehavior) {
  const instance = axios.create({ adapter });
  installRequestInterceptor(instance);
  return instance;
}

describe('installRequestInterceptor (P2-1)', () => {
  let applySpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    applySpy = vi.spyOn(errorsModule, 'applyFriendlyErrorMessage');
  });

  afterEach(() => {
    applySpy.mockRestore();
  });

  it('calls applyFriendlyErrorMessage on AxiosError in the request error path', async () => {
    const instance = makeInstance(
      async (config) =>
        ({
          data: {},
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        }) as AxiosResponse
    );

    // Inject an AxiosError by registering a second request interceptor that
    // throws before the actual network call. The installed interceptor's
    // error callback should then fire.
    instance.interceptors.request.use(() => {
      const err = new AxiosError('pre-send boom');
      err.isAxiosError = true;
      throw err;
    });

    await expect(instance.get('/v1/thing')).rejects.toBeInstanceOf(AxiosError);
    expect(applySpy).toHaveBeenCalledTimes(1);
    expect(applySpy.mock.calls[0][0]).toBeInstanceOf(AxiosError);
  });

  it('does not call applyFriendlyErrorMessage on non-AxiosError throws', async () => {
    const instance = makeInstance(
      async (config) =>
        ({
          data: {},
          status: 200,
          statusText: 'OK',
          headers: {},
          config,
        }) as AxiosResponse
    );

    instance.interceptors.request.use(() => {
      throw new Error('plain non-axios throw');
    });

    await expect(instance.get('/v1/thing')).rejects.toThrow('plain non-axios throw');
    expect(applySpy).not.toHaveBeenCalled();
  });
});
