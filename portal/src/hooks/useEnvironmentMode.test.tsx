import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useEnvironmentMode } from './useEnvironmentMode';

const mockPortalEnvironment = vi.fn();
vi.mock('../contexts/EnvironmentContext', () => ({
  usePortalEnvironment: () => mockPortalEnvironment(),
}));

const mockAuth = vi.fn();
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

function makeEnvContext(mode: 'full' | 'read-only' | 'promote-only') {
  return {
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode, color: 'green' },
    environments: [],
    endpoints: null,
    switchEnvironment: vi.fn(),
    loading: false,
    error: null,
  };
}

function makeAuth(role: string) {
  return {
    user: { name: 'Test', email: 'test@test.com', roles: [role] },
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    accessToken: 'token',
    hasPermission: () => true,
    hasAnyPermission: () => true,
    hasRole: (r: string) => r === role,
    hasScope: () => true,
    logout: vi.fn(),
  };
}

describe('useEnvironmentMode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('full mode allows all operations', () => {
    mockPortalEnvironment.mockReturnValue(makeEnvContext('full'));
    mockAuth.mockReturnValue(makeAuth('viewer'));

    const { result } = renderHook(() => useEnvironmentMode());

    expect(result.current).toEqual({
      canCreate: true,
      canEdit: true,
      canDelete: true,
      canDeploy: true,
      isReadOnly: false,
    });
  });

  it('read-only mode blocks all operations for non-admin', () => {
    mockPortalEnvironment.mockReturnValue(makeEnvContext('read-only'));
    mockAuth.mockReturnValue(makeAuth('viewer'));

    const { result } = renderHook(() => useEnvironmentMode());

    expect(result.current).toEqual({
      canCreate: false,
      canEdit: false,
      canDelete: false,
      canDeploy: false,
      isReadOnly: true,
    });
  });

  it('read-only mode allows all operations for cpi-admin', () => {
    mockPortalEnvironment.mockReturnValue(makeEnvContext('read-only'));
    mockAuth.mockReturnValue(makeAuth('cpi-admin'));

    const { result } = renderHook(() => useEnvironmentMode());

    expect(result.current).toEqual({
      canCreate: true,
      canEdit: true,
      canDelete: true,
      canDeploy: true,
      isReadOnly: false,
    });
  });

  it('promote-only mode allows deploy only', () => {
    mockPortalEnvironment.mockReturnValue(makeEnvContext('promote-only'));
    mockAuth.mockReturnValue(makeAuth('devops'));

    const { result } = renderHook(() => useEnvironmentMode());

    expect(result.current).toEqual({
      canCreate: false,
      canEdit: false,
      canDelete: false,
      canDeploy: true,
      isReadOnly: false,
    });
  });

  it('full mode allows all for tenant-admin', () => {
    mockPortalEnvironment.mockReturnValue(makeEnvContext('full'));
    mockAuth.mockReturnValue(makeAuth('tenant-admin'));

    const { result } = renderHook(() => useEnvironmentMode());

    expect(result.current.canCreate).toBe(true);
    expect(result.current.isReadOnly).toBe(false);
  });

  it('read-only mode blocks tenant-admin', () => {
    mockPortalEnvironment.mockReturnValue(makeEnvContext('read-only'));
    mockAuth.mockReturnValue(makeAuth('tenant-admin'));

    const { result } = renderHook(() => useEnvironmentMode());

    expect(result.current.canCreate).toBe(false);
    expect(result.current.isReadOnly).toBe(true);
  });
});
