import { vi } from 'vitest';
import type { User } from '../../types';
import { mockAdminUser, mockViewerUser } from './data';

interface MockAuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isReady: boolean;
}

let authState: MockAuthState = {
  user: mockAdminUser,
  isAuthenticated: true,
  isLoading: false,
  isReady: true,
};

export const mockLogin = vi.fn();
export const mockLogout = vi.fn();
export const mockHasPermission = vi.fn((permission: string) => {
  return authState.user?.permissions.includes(permission) ?? false;
});
export const mockHasRole = vi.fn((role: string) => {
  return authState.user?.roles.includes(role) ?? false;
});

export function setMockAuthState(state: Partial<MockAuthState>) {
  authState = { ...authState, ...state };
}

export function setMockUser(user: User | null) {
  authState.user = user;
  authState.isAuthenticated = !!user;
  authState.isReady = !!user;
}

export function resetMockAuth() {
  authState = { user: mockAdminUser, isAuthenticated: true, isLoading: false, isReady: true };
  mockLogin.mockClear();
  mockLogout.mockClear();
  mockHasPermission.mockClear();
  mockHasPermission.mockImplementation(
    (p: string) => authState.user?.permissions.includes(p) ?? false
  );
  mockHasRole.mockClear();
  mockHasRole.mockImplementation((r: string) => authState.user?.roles.includes(r) ?? false);
}

export function getMockAuthValue() {
  return {
    user: authState.user,
    isAuthenticated: authState.isAuthenticated,
    isLoading: authState.isLoading,
    isReady: authState.isReady,
    login: mockLogin,
    logout: mockLogout,
    hasPermission: mockHasPermission,
    hasRole: mockHasRole,
  };
}

export { mockAdminUser, mockViewerUser };
