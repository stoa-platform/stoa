/**
 * Tests for DashboardStats (CAB-1390)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { DashboardStats } from './DashboardStats';
import { renderWithProviders, mockDashboardStats } from '../../test/helpers';

describe('DashboardStats', () => {
  it('shows loading skeletons when isLoading is true', () => {
    const { container } = renderWithProviders(<DashboardStats stats={null} isLoading={true} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders "Tools Available" stat card', () => {
    renderWithProviders(<DashboardStats stats={mockDashboardStats() as never} />);
    expect(screen.getByText('Tools Available')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('renders "Active Subscriptions" stat card', () => {
    renderWithProviders(<DashboardStats stats={mockDashboardStats() as never} />);
    expect(screen.getByText('Active Subscriptions')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders "API Calls" stat card', () => {
    renderWithProviders(<DashboardStats stats={mockDashboardStats() as never} />);
    // Value is formatted with toLocaleString — may render as "2,450" or "2450" depending on locale
    expect(screen.getByText(/2.?450/)).toBeInTheDocument();
  });

  it('shows zero values when stats is null (not loading)', () => {
    renderWithProviders(<DashboardStats stats={null} />);
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBeGreaterThanOrEqual(3);
  });

  it('renders trend indicator when trend data is provided', () => {
    const statsWithTrend = {
      ...mockDashboardStats(),
      tools_trend: 10,
      subscriptions_trend: -5,
    };
    const { container } = renderWithProviders(<DashboardStats stats={statsWithTrend as never} />);
    // Trend arrows rendered in the component
    expect(container.querySelector('svg')).toBeInTheDocument();
  });
});
