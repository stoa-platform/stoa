/**
 * Tests for UsageChart (CAB-1390)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { UsageChart } from './UsageChart';
import { renderWithProviders } from '../../test/helpers';
import type { DailyCallStat } from '../../types';

const mockData: DailyCallStat[] = [
  { date: '2026-02-15', calls: 100 },
  { date: '2026-02-16', calls: 200 },
  { date: '2026-02-17', calls: 150 },
];

describe('UsageChart', () => {
  it('shows loading skeleton when isLoading is true', () => {
    const { container } = renderWithProviders(<UsageChart data={[]} isLoading={true} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('does not show loading skeleton when isLoading is false', () => {
    const { container } = renderWithProviders(<UsageChart data={mockData} isLoading={false} />);
    expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument();
  });

  it('renders without crashing when data is empty', () => {
    const { container } = renderWithProviders(<UsageChart data={[]} />);
    expect(container).toBeTruthy();
  });

  it('renders a bar for each data point', () => {
    const { container } = renderWithProviders(<UsageChart data={mockData} />);
    // Each bar has inline style with minHeight (unique to bar divs)
    const bars = container.querySelectorAll('[style*="min-height"]');
    expect(bars.length).toBe(mockData.length);
  });

  it('renders day labels for each data point', () => {
    renderWithProviders(<UsageChart data={mockData} />);
    // Day labels are rendered (e.g., "Mon", "Tue")
    const dayLabels = screen.queryAllByText(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)$/);
    expect(dayLabels.length).toBeGreaterThan(0);
  });
});
