import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { DashboardStats } from '../DashboardStats';
import { renderWithProviders, mockDashboardStats } from '../../../test/helpers';

describe('DashboardStats', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders three stat cards with data', () => {
    const stats = mockDashboardStats();
    renderWithProviders(<DashboardStats stats={stats} />);

    expect(screen.getByText('Tools Available')).toBeInTheDocument();
    expect(screen.getByText('Active Subscriptions')).toBeInTheDocument();
    expect(screen.getByText('API Calls')).toBeInTheDocument();
  });

  it('renders stat values from props', () => {
    const stats = mockDashboardStats();
    renderWithProviders(<DashboardStats stats={stats} />);

    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('2,450')).toBeInTheDocument();
  });

  it('renders zero values when stats is null', () => {
    renderWithProviders(<DashboardStats stats={null} />);

    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBe(3);
  });

  it('renders loading skeleton when isLoading is true', () => {
    const { container } = renderWithProviders(<DashboardStats stats={null} isLoading={true} />);

    const pulsingElements = container.querySelectorAll('.animate-pulse');
    expect(pulsingElements.length).toBeGreaterThan(0);
  });

  it('renders subtitle text for each stat', () => {
    const stats = mockDashboardStats();
    renderWithProviders(<DashboardStats stats={stats} />);

    expect(screen.getByText('Ready to integrate')).toBeInTheDocument();
    expect(screen.getByText('Currently active')).toBeInTheDocument();
    expect(screen.getByText('This week')).toBeInTheDocument();
  });

  it('shows trend indicator when trend is positive', () => {
    const stats = { ...mockDashboardStats(), tools_trend: 10 };
    renderWithProviders(<DashboardStats stats={stats} />);

    expect(screen.getByText('10%')).toBeInTheDocument();
  });

  it('shows trend indicator when trend is negative', () => {
    const stats = { ...mockDashboardStats(), tools_trend: -5 };
    renderWithProviders(<DashboardStats stats={stats} />);

    expect(screen.getByText('5%')).toBeInTheDocument();
  });
});
