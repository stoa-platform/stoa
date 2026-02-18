/**
 * Tests for GettingStartedChecklist (CAB-1325 PR 1.2b)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders, createAuthMock } from '../../../test/helpers';
import { GettingStartedChecklist } from '../GettingStartedChecklist';
import * as useOnboardingModule from '../../../hooks/useOnboarding';

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: vi.fn().mockReturnValue({
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    isNewUser: false,
    accessToken: 'mock-token',
    user: {
      tenant_id: 'test-tenant',
      roles: ['tenant-admin'],
      permissions: [],
      effective_scopes: [],
    },
    hasPermission: () => false,
    hasAnyPermission: () => false,
    hasAllPermissions: () => false,
    hasRole: () => false,
    hasScope: () => false,
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
    refreshPermissions: vi.fn(),
  }),
}));

vi.mock('../../../hooks/useOnboarding');

const mockUseOnboardingProgress = vi.mocked(useOnboardingModule.useOnboardingProgress);

const baseProgress = {
  tenant_id: 'test-tenant',
  user_id: 'test-user',
  steps_completed: {},
  started_at: '2026-02-20T14:00:00Z',
  completed_at: null,
  ttftc_seconds: null,
  is_complete: false,
};

function mockProgress(overrides: Partial<typeof baseProgress> = {}) {
  mockUseOnboardingProgress.mockReturnValue({
    data: { ...baseProgress, ...overrides },
    isLoading: false,
    isSuccess: true,
    isError: false,
    error: null,
  } as ReturnType<typeof useOnboardingModule.useOnboardingProgress>);
}

describe('GettingStartedChecklist', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockProgress();
  });

  it('renders checklist with 4 steps when onboarding incomplete', () => {
    renderWithProviders(<GettingStartedChecklist />);
    expect(screen.getByText('Getting Started')).toBeInTheDocument();
    expect(screen.getByText('Choose your use case')).toBeInTheDocument();
    expect(screen.getByText('Create your first app')).toBeInTheDocument();
    expect(screen.getByText('Subscribe to an API')).toBeInTheDocument();
    expect(screen.getByText('Make your first API call')).toBeInTheDocument();
    expect(screen.getByText('0 of 4 steps complete')).toBeInTheDocument();
  });

  it('shows completed steps with checkmarks', () => {
    mockProgress({
      steps_completed: {
        choose_use_case: '2026-02-20T14:00:00Z',
        create_app: '2026-02-20T14:05:00Z',
      },
    });
    renderWithProviders(<GettingStartedChecklist />);
    expect(screen.getByText('2 of 4 steps complete')).toBeInTheDocument();
  });

  it('renders nothing when loading', () => {
    mockUseOnboardingProgress.mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useOnboardingModule.useOnboardingProgress>);
    const { container } = renderWithProviders(<GettingStartedChecklist />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when onboarding is complete', () => {
    mockProgress({ is_complete: true, completed_at: '2026-02-20T15:00:00Z' });
    const { container } = renderWithProviders(<GettingStartedChecklist />);
    expect(container.firstChild).toBeNull();
  });

  it('dismisses checklist on button click', () => {
    renderWithProviders(<GettingStartedChecklist />);
    expect(screen.getByText('Getting Started')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Dismiss'));
    expect(screen.queryByText('Getting Started')).not.toBeInTheDocument();
    expect(sessionStorage.getItem('checklist_dismissed')).toBe('true');
  });

  it('stays dismissed when sessionStorage flag set', () => {
    sessionStorage.setItem('checklist_dismissed', 'true');
    const { container } = renderWithProviders(<GettingStartedChecklist />);
    expect(container.firstChild).toBeNull();
  });
});
