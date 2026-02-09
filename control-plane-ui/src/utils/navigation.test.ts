import { describe, it, expect } from 'vitest';
import { observabilityPath, logsPath, isAllowedEmbedUrl } from './navigation';

describe('observabilityPath', () => {
  it('returns base path without target URL', () => {
    expect(observabilityPath()).toBe('/observability');
  });

  it('returns path with encoded target URL', () => {
    expect(observabilityPath('https://grafana.gostoa.dev/d/abc')).toBe(
      '/observability?url=https%3A%2F%2Fgrafana.gostoa.dev%2Fd%2Fabc'
    );
  });
});

describe('logsPath', () => {
  it('returns base path without target URL', () => {
    expect(logsPath()).toBe('/logs');
  });

  it('returns path with encoded target URL', () => {
    expect(logsPath('https://grafana.gostoa.dev/explore')).toBe(
      '/logs?url=https%3A%2F%2Fgrafana.gostoa.dev%2Fexplore'
    );
  });
});

describe('isAllowedEmbedUrl', () => {
  it('allows grafana.gostoa.dev', () => {
    expect(isAllowedEmbedUrl('https://grafana.gostoa.dev/d/abc')).toBe(true);
  });

  it('allows prometheus.gostoa.dev', () => {
    expect(isAllowedEmbedUrl('https://prometheus.gostoa.dev/graph')).toBe(true);
  });

  it('allows localhost', () => {
    expect(isAllowedEmbedUrl('http://localhost:3000/d/abc')).toBe(true);
  });

  it('rejects external URLs', () => {
    expect(isAllowedEmbedUrl('https://evil.com/steal')).toBe(false);
  });

  it('allows relative paths', () => {
    expect(isAllowedEmbedUrl('/d/dashboard')).toBe(true);
  });

  it('rejects non-relative invalid URLs', () => {
    expect(isAllowedEmbedUrl('javascript:alert(1)')).toBe(false);
  });
});
