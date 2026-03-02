import { describe, it, expect } from 'vitest';
import { getFriendlyError, getFriendlyErrorMessage } from './errorMessages';

describe('errorMessages', () => {
  describe('getFriendlyError', () => {
    it('returns friendly message for 401 status from Axios error shape', () => {
      const error = { response: { status: 401 }, message: 'Request failed with status code 401' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('Your session has expired. Please log in again.');
      expect(result.action).toBe('login');
    });

    it('returns friendly message for 403 status', () => {
      const error = { response: { status: 403 }, message: 'Request failed with status code 403' };
      const result = getFriendlyError(error);
      expect(result.message).toBe("You don't have permission to access this resource.");
      expect(result.action).toBe('home');
    });

    it('returns friendly message for 404 status', () => {
      const error = { response: { status: 404 }, message: 'Request failed with status code 404' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('The requested resource was not found.');
      expect(result.action).toBe('home');
    });

    it('returns friendly message for 500 status', () => {
      const error = { response: { status: 500 }, message: 'Request failed with status code 500' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('Something went wrong on our end. Please try again later.');
      expect(result.action).toBe('retry');
    });

    it('returns friendly message for 429 rate limit', () => {
      const error = { response: { status: 429 }, message: 'Request failed with status code 429' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('Too many requests. Please wait a moment and try again.');
      expect(result.action).toBe('retry');
    });

    it('returns friendly message for 502 bad gateway', () => {
      const error = { response: { status: 502 } };
      const result = getFriendlyError(error);
      expect(result.message).toBe('The server is temporarily unavailable. Please try again later.');
    });

    it('returns friendly message for 503 service unavailable', () => {
      const error = { response: { status: 503 } };
      const result = getFriendlyError(error);
      expect(result.message).toBe('The service is temporarily unavailable. Please try again later.');
    });

    it('extracts status code from raw message string pattern', () => {
      const error = { message: 'Request failed with status code 401' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('Your session has expired. Please log in again.');
    });

    it('extracts status code from string error', () => {
      const result = getFriendlyError('Request failed with status code 404');
      expect(result.message).toBe('The requested resource was not found.');
    });

    it('returns network error for Axios network error shape', () => {
      const error = { request: {}, message: 'Network Error' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('Unable to connect to the server. Please check your connection.');
      expect(result.action).toBe('retry');
    });

    it('returns network error for ERR_NETWORK code', () => {
      const error = { code: 'ERR_NETWORK', request: {}, message: 'Network Error' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('Unable to connect to the server. Please check your connection.');
    });

    it('returns network error for ECONNABORTED code', () => {
      const error = { code: 'ECONNABORTED', request: {}, message: 'timeout of 5000ms exceeded' };
      const result = getFriendlyError(error);
      expect(result.message).toBe('Unable to connect to the server. Please check your connection.');
    });

    it('uses backend detail message when available and not a raw status pattern', () => {
      const error = {
        response: { status: 422, data: { detail: 'Email already registered' } },
        message: 'Request failed with status code 422',
      };
      const result = getFriendlyError(error);
      // Status code mapping takes priority (status 422 is mapped)
      expect(result.message).toBe('The provided data is invalid. Please check your input.');
    });

    it('uses backend detail for unmapped status codes', () => {
      const error = {
        response: { status: 418, data: { detail: 'I am a teapot' } },
        message: 'Request failed with status code 418',
      };
      const result = getFriendlyError(error);
      expect(result.message).toBe('I am a teapot');
    });

    it('falls back to custom fallback message', () => {
      const error = {};
      const result = getFriendlyError(error, 'Custom fallback');
      expect(result.message).toBe('Custom fallback');
    });

    it('returns generic message when nothing else matches', () => {
      const error = {};
      const result = getFriendlyError(error);
      expect(result.message).toBe('Something went wrong. Please try again later.');
      expect(result.action).toBe('retry');
    });

    it('handles null/undefined error gracefully', () => {
      expect(getFriendlyError(null).message).toBe('Something went wrong. Please try again later.');
      expect(getFriendlyError(undefined).message).toBe(
        'Something went wrong. Please try again later.'
      );
    });

    it('handles Error instance with raw status message', () => {
      const error = new Error('Request failed with status code 500');
      const result = getFriendlyError(error);
      expect(result.message).toBe('Something went wrong on our end. Please try again later.');
    });

    it('does not use backend detail that looks like a raw status message', () => {
      const error = {
        response: {
          status: 418,
          data: { detail: 'Request failed with status code 418' },
        },
        message: 'Request failed with status code 418',
      };
      const result = getFriendlyError(error);
      // Should use generic fallback, not the raw-looking detail
      expect(result.message).toBe('Something went wrong. Please try again later.');
    });
  });

  describe('getFriendlyErrorMessage', () => {
    it('returns just the message string', () => {
      const error = { response: { status: 401 } };
      expect(getFriendlyErrorMessage(error)).toBe(
        'Your session has expired. Please log in again.'
      );
    });

    it('returns fallback when provided', () => {
      expect(getFriendlyErrorMessage({}, 'My fallback')).toBe('My fallback');
    });
  });
});
