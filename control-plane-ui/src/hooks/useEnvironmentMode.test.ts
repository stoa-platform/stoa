import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useEnvironmentMode } from './useEnvironmentMode';

const mockUseEnvironment = vi.fn();
const mockUseAuth = vi.fn();

vi.mock('../contexts/EnvironmentContext', () => ({
  useEnvironment: () => mockUseEnvironment(),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

function setupMocks(mode: string, role: string) {
  mockUseEnvironment.mockReturnValue({
    activeEnvironment: mode === 'full' ? 'dev' : mode === 'read-only' ? 'prod' : 'staging',
    activeConfig: { name: 'env', label: 'Env', mode, color: 'green' },
    environments: [],
    switchEnvironment: vi.fn(),
  });
  mockUseAuth.mockReturnValue({
    user: { id: 'u1', roles: [role] },
    hasRole: vi.fn((r: string) => r === role),
  });
}

describe('useEnvironmentMode', () => {
  it('returns all permissions in full mode', () => {
    setupMocks('full', 'viewer');
    const { result } = renderHook(() => useEnvironmentMode());
    expect(result.current).toEqual({
      canCreate: true,
      canEdit: true,
      canDelete: true,
      canDeploy: true,
      isReadOnly: false,
    });
  });

  it('blocks writes in read-only mode for non-admin', () => {
    setupMocks('read-only', 'viewer');
    const { result } = renderHook(() => useEnvironmentMode());
    expect(result.current).toEqual({
      canCreate: false,
      canEdit: false,
      canDelete: false,
      canDeploy: false,
      isReadOnly: true,
    });
  });

  it('allows writes in read-only mode for cpi-admin', () => {
    setupMocks('read-only', 'cpi-admin');
    const { result } = renderHook(() => useEnvironmentMode());
    expect(result.current).toEqual({
      canCreate: true,
      canEdit: true,
      canDelete: true,
      canDeploy: true,
      isReadOnly: false,
    });
  });

  it('allows only deploy in promote-only mode', () => {
    setupMocks('promote-only', 'devops');
    const { result } = renderHook(() => useEnvironmentMode());
    expect(result.current).toEqual({
      canCreate: false,
      canEdit: false,
      canDelete: false,
      canDeploy: true,
      isReadOnly: false,
    });
  });
});
