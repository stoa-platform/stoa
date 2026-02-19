/**
 * Tests for OnboardingFunnel component (CAB-1325 Phase 3)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { OnboardingFunnel } from '../OnboardingFunnel';
import type { FunnelResponse } from '../../../services/onboarding';

// Mock hooks
const mockUseOnboardingFunnel = vi.fn();
const mockUseStalledUsers = vi.fn();

vi.mock('../../../hooks/useOnboardingAnalytics', () => ({
  useOnboardingFunnel: () => mockUseOnboardingFunnel(),
  useStalledUsers: () => mockUseStalledUsers(),
}));

const mockFunnel: FunnelResponse = {
  stages: [
    { stage: 'registered', count: 100, conversion_rate: 1.0 },
    { stage: 'choose_use_case', count: 80, conversion_rate: 0.8 },
    { stage: 'create_app', count: 60, conversion_rate: 0.6 },
    { stage: 'subscribe_api', count: 40, conversion_rate: 0.4 },
    { stage: 'first_call', count: 30, conversion_rate: 0.3 },
  ],
  total_started: 100,
  total_completed: 30,
  avg_ttftc_seconds: 45.2,
  p50_ttftc_seconds: 30.0,
  p90_ttftc_seconds: 120.0,
};

describe('OnboardingFunnel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseOnboardingFunnel.mockReturnValue({
      data: mockFunnel,
      isLoading: false,
      error: null,
    });
    mockUseStalledUsers.mockReturnValue({
      data: [],
    });
  });

  it('renders funnel header with total users', () => {
    render(<OnboardingFunnel />);

    expect(screen.getByText('Onboarding Funnel')).toBeInTheDocument();
    expect(screen.getByText('100 users started')).toBeInTheDocument();
  });

  it('renders all 5 funnel stages with counts and rates', () => {
    render(<OnboardingFunnel />);

    expect(screen.getByText('Registered')).toBeInTheDocument();
    expect(screen.getByText('Chose Use Case')).toBeInTheDocument();
    expect(screen.getByText('Created App')).toBeInTheDocument();
    expect(screen.getByText('Subscribed to API')).toBeInTheDocument();
    expect(screen.getByText('First Tool Call')).toBeInTheDocument();

    // Check conversion rates are displayed
    expect(screen.getByText('(100%)')).toBeInTheDocument();
    expect(screen.getByText('(30%)')).toBeInTheDocument();
  });

  it('renders TTFTC stats (avg, p50, p90)', () => {
    render(<OnboardingFunnel />);

    expect(screen.getByText('Avg TTFTC')).toBeInTheDocument();
    expect(screen.getByText('45s')).toBeInTheDocument(); // avg
    expect(screen.getByText('30s')).toBeInTheDocument(); // p50
    expect(screen.getByText('2m')).toBeInTheDocument(); // p90 = 120s = 2m
  });

  it('shows stalled users alert when users are stalled', () => {
    mockUseStalledUsers.mockReturnValue({
      data: [
        {
          user_id: 'u1',
          tenant_id: 't1',
          last_step: 'create_app',
          started_at: '',
          hours_stalled: 48,
        },
        { user_id: 'u2', tenant_id: 't2', last_step: null, started_at: '', hours_stalled: 72 },
      ],
    });

    render(<OnboardingFunnel />);

    expect(screen.getByText(/2 users stalled/)).toBeInTheDocument();
  });

  it('renders nothing when funnel data fails to load', () => {
    mockUseOnboardingFunnel.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Forbidden'),
    });

    const { container } = render(<OnboardingFunnel />);

    expect(container.innerHTML).toBe('');
  });

  it('renders loading skeleton when loading', () => {
    mockUseOnboardingFunnel.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    const { container } = render(<OnboardingFunnel />);

    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });
});
