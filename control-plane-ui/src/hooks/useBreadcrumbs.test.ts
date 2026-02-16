import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useBreadcrumbs } from './useBreadcrumbs';

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useLocation: vi.fn(),
  useParams: vi.fn(),
}));

import { useLocation, useParams } from 'react-router-dom';

const mockUseLocation = vi.mocked(useLocation);
const mockUseParams = vi.mocked(useParams);

describe('useBreadcrumbs', () => {
  it('returns Dashboard only for root path', () => {
    mockUseLocation.mockReturnValue({ pathname: '/', search: '', hash: '', state: null, key: '' });
    mockUseParams.mockReturnValue({});

    const { result } = renderHook(() => useBreadcrumbs());
    expect(result.current).toEqual([{ label: 'Dashboard' }]);
  });

  it('returns breadcrumbs for known route', () => {
    mockUseLocation.mockReturnValue({
      pathname: '/tenants',
      search: '',
      hash: '',
      state: null,
      key: '',
    });
    mockUseParams.mockReturnValue({});

    const { result } = renderHook(() => useBreadcrumbs());
    expect(result.current).toEqual([{ label: 'Dashboard', href: '/' }, { label: 'Tenants' }]);
  });

  it('returns breadcrumbs for nested known route', () => {
    mockUseLocation.mockReturnValue({
      pathname: '/admin/prospects',
      search: '',
      hash: '',
      state: null,
      key: '',
    });
    mockUseParams.mockReturnValue({});

    const { result } = renderHook(() => useBreadcrumbs());
    expect(result.current).toEqual([
      { label: 'Dashboard', href: '/' },
      { label: 'Admin', href: '/admin' },
      { label: 'Prospects' },
    ]);
  });

  it('handles dynamic params as "Details"', () => {
    mockUseLocation.mockReturnValue({
      pathname: '/tenants/abc-123',
      search: '',
      hash: '',
      state: null,
      key: '',
    });
    mockUseParams.mockReturnValue({ id: 'abc-123' });

    const { result } = renderHook(() => useBreadcrumbs());
    expect(result.current).toEqual([
      { label: 'Dashboard', href: '/' },
      { label: 'Tenants', href: '/tenants' },
      { label: 'Details' },
    ]);
  });

  it('formats unknown segments as title case', () => {
    mockUseLocation.mockReturnValue({
      pathname: '/some-unknown-page',
      search: '',
      hash: '',
      state: null,
      key: '',
    });
    mockUseParams.mockReturnValue({});

    const { result } = renderHook(() => useBreadcrumbs());
    expect(result.current).toEqual([
      { label: 'Dashboard', href: '/' },
      { label: 'Some Unknown Page' },
    ]);
  });

  it('maps all known route labels', () => {
    const knownRoutes = [
      { path: '/apis', label: 'APIs' },
      { path: '/ai-tools', label: 'AI Tools' },
      { path: '/subscriptions', label: 'Subscriptions' },
      { path: '/gateway', label: 'Gateway' },
      { path: '/gateways', label: 'Gateway Registry' },
      { path: '/deployments', label: 'Deployments' },
      { path: '/applications', label: 'Applications' },
      { path: '/errors', label: 'Error Snapshots' },
      { path: '/mcp', label: 'MCP' },
    ];

    for (const { path, label } of knownRoutes) {
      mockUseLocation.mockReturnValue({
        pathname: path,
        search: '',
        hash: '',
        state: null,
        key: '',
      });
      mockUseParams.mockReturnValue({});

      const { result } = renderHook(() => useBreadcrumbs());
      expect(result.current[result.current.length - 1].label).toBe(label);
    }
  });

  it('only last segment has no href', () => {
    mockUseLocation.mockReturnValue({
      pathname: '/admin/prospects',
      search: '',
      hash: '',
      state: null,
      key: '',
    });
    mockUseParams.mockReturnValue({});

    const { result } = renderHook(() => useBreadcrumbs());
    // All except last should have href
    result.current.slice(0, -1).forEach((crumb) => {
      expect(crumb.href).toBeDefined();
    });
    // Last should not have href
    expect(result.current[result.current.length - 1].href).toBeUndefined();
  });
});
