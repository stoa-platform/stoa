import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { UsageChart } from '../UsageChart';
import { renderWithProviders } from '../../../test/helpers';
import type { DailyCallStat } from '../../../types';

const makeDay = (date: string, calls: number): DailyCallStat => ({ date, calls });

const sevenDays: DailyCallStat[] = [
  makeDay('2026-02-04', 180),
  makeDay('2026-02-05', 220),
  makeDay('2026-02-06', 190),
  makeDay('2026-02-07', 250),
  makeDay('2026-02-08', 160),
  makeDay('2026-02-09', 200),
  makeDay('2026-02-10', 150),
];

describe('UsageChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Call Volume heading', () => {
    renderWithProviders(<UsageChart data={sevenDays} />);

    expect(screen.getByText('Call Volume (7 days)')).toBeInTheDocument();
  });

  it('renders total call count', () => {
    renderWithProviders(<UsageChart data={sevenDays} />);

    const total = sevenDays.reduce((sum, d) => sum + d.calls, 0); // 1350
    expect(screen.getByText(`Total: ${total.toLocaleString()} calls`)).toBeInTheDocument();
  });

  it('renders 7 day bars', () => {
    const { container } = renderWithProviders(<UsageChart data={sevenDays} />);

    // Each day has a bar div
    const bars = container.querySelectorAll('.rounded-t');
    expect(bars).toHaveLength(7);
  });

  it('renders loading skeleton when isLoading is true', () => {
    renderWithProviders(<UsageChart data={[]} isLoading={true} />);

    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
    // Heading still shown
    expect(screen.getByText('Call Volume (7 days)')).toBeInTheDocument();
  });

  it('renders Y-axis labels (0, mid, max)', () => {
    renderWithProviders(<UsageChart data={sevenDays} />);

    expect(screen.getByText('0')).toBeInTheDocument();
    // max is 250, mid is 125
    expect(screen.getByText('125')).toBeInTheDocument();
    expect(screen.getByText('250')).toBeInTheDocument();
  });

  it('renders last bar with primary-500 (today) class', () => {
    const { container } = renderWithProviders(<UsageChart data={sevenDays} />);

    const todayBar = container.querySelector('.bg-primary-500');
    expect(todayBar).toBeInTheDocument();
  });

  it('renders non-today bars with primary-200 class', () => {
    const { container } = renderWithProviders(<UsageChart data={sevenDays} />);

    const normalBars = container.querySelectorAll('.bg-primary-200');
    expect(normalBars).toHaveLength(6); // 7 days - 1 today
  });

  it('renders with empty data without crashing', () => {
    renderWithProviders(<UsageChart data={[]} />);

    expect(screen.getByText('Call Volume (7 days)')).toBeInTheDocument();
  });

  it('renders weekday labels', () => {
    renderWithProviders(<UsageChart data={sevenDays} />);

    // Should render day labels like Mon, Tue, etc.
    // The dates are 2026-02-04 (Wed) through 2026-02-10 (Tue)
    expect(screen.getAllByText(/Mon|Tue|Wed|Thu|Fri|Sat|Sun/).length).toBeGreaterThan(0);
  });

  it('renders single day without crashing', () => {
    renderWithProviders(<UsageChart data={[makeDay('2026-02-10', 100)]} />);

    expect(screen.getByText('Total: 100 calls')).toBeInTheDocument();
  });
});
