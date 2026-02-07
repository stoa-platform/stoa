/**
 * Tests for format utilities
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { formatRelativeTime, formatNumber, formatCompactNumber } from './format';

describe('format utilities', () => {
  describe('formatRelativeTime', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-02-07T12:00:00Z'));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should return "just now" for less than 60 seconds ago', () => {
      const date = new Date('2026-02-07T11:59:30Z').toISOString();
      expect(formatRelativeTime(date)).toBe('just now');
    });

    it('should return minutes ago for less than 60 minutes', () => {
      const date = new Date('2026-02-07T11:55:00Z').toISOString();
      expect(formatRelativeTime(date)).toBe('5m ago');
    });

    it('should return hours ago for less than 24 hours', () => {
      const date = new Date('2026-02-07T09:00:00Z').toISOString();
      expect(formatRelativeTime(date)).toBe('3h ago');
    });

    it('should return days ago for less than 7 days', () => {
      const date = new Date('2026-02-05T12:00:00Z').toISOString();
      expect(formatRelativeTime(date)).toBe('2d ago');
    });

    it('should return formatted date for 7+ days ago', () => {
      const date = new Date('2026-01-20T12:00:00Z').toISOString();
      const result = formatRelativeTime(date);
      // toLocaleDateString returns locale-specific format
      expect(result).not.toContain('ago');
      expect(result).toBeTruthy();
    });

    it('should handle edge case at exactly 60 seconds', () => {
      const date = new Date('2026-02-07T11:59:00Z').toISOString();
      expect(formatRelativeTime(date)).toBe('1m ago');
    });

    it('should handle edge case at exactly 60 minutes', () => {
      const date = new Date('2026-02-07T11:00:00Z').toISOString();
      expect(formatRelativeTime(date)).toBe('1h ago');
    });

    it('should handle edge case at exactly 24 hours', () => {
      const date = new Date('2026-02-06T12:00:00Z').toISOString();
      expect(formatRelativeTime(date)).toBe('1d ago');
    });
  });

  describe('formatNumber', () => {
    it('should return the number as-is for values under 1000', () => {
      expect(formatNumber(0)).toBe('0');
      expect(formatNumber(1)).toBe('1');
      expect(formatNumber(999)).toBe('999');
    });

    it('should format thousands with k suffix', () => {
      expect(formatNumber(1000)).toBe('1.0k');
      expect(formatNumber(1500)).toBe('1.5k');
      expect(formatNumber(999999)).toBe('1000.0k');
    });

    it('should format millions with M suffix', () => {
      expect(formatNumber(1000000)).toBe('1.0M');
      expect(formatNumber(2500000)).toBe('2.5M');
    });
  });

  describe('formatCompactNumber', () => {
    it('should format numbers using Intl compact notation', () => {
      expect(formatCompactNumber(0)).toBe('0');
      expect(formatCompactNumber(999)).toBe('999');
    });

    it('should format large numbers compactly', () => {
      const result = formatCompactNumber(1500);
      // Intl.NumberFormat compact notation varies by locale
      expect(result).toBeTruthy();
    });

    it('should format millions', () => {
      const result = formatCompactNumber(1000000);
      expect(result).toContain('M');
    });
  });
});
