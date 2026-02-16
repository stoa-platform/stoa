import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UsageStats } from './UsageStats';

describe('UsageStats', () => {
  it('should show empty state when no stats', () => {
    render(<UsageStats />);
    expect(screen.getByText('No usage data available yet')).toBeInTheDocument();
  });

  it('should show empty state when callsThisMonth is 0', () => {
    render(<UsageStats stats={{ callsThisMonth: 0 }} />);
    expect(screen.getByText('No usage data available yet')).toBeInTheDocument();
  });

  it('should render stat cards when stats present', () => {
    render(
      <UsageStats
        stats={{
          callsThisMonth: 5000,
          callsToday: 200,
          avgLatencyMs: 150,
          successRate: 99.5,
          lastCalledAt: new Date().toISOString(),
        }}
      />
    );
    expect(screen.getByText('5.0K')).toBeInTheDocument();
    expect(screen.getByText('Calls this month')).toBeInTheDocument();
    expect(screen.getByText('150ms')).toBeInTheDocument();
    expect(screen.getByText('99.5%')).toBeInTheDocument();
  });

  it('should format large numbers', () => {
    render(<UsageStats stats={{ callsThisMonth: 1500000 }} />);
    expect(screen.getByText('1.5M')).toBeInTheDocument();
  });

  it('should format latency in seconds when >= 1000ms', () => {
    render(<UsageStats stats={{ callsThisMonth: 100, avgLatencyMs: 2500 }} />);
    expect(screen.getByText('2.50s')).toBeInTheDocument();
  });

  it('should show subtext for today calls', () => {
    render(<UsageStats stats={{ callsThisMonth: 100, callsToday: 42 }} />);
    expect(screen.getByText('42 today')).toBeInTheDocument();
  });

  it('should show error count in subtext', () => {
    render(<UsageStats stats={{ callsThisMonth: 100, successRate: 95.0, errorCount: 5 }} />);
    expect(screen.getByText('5 errors')).toBeInTheDocument();
  });

  it('should show trend indicator', () => {
    render(<UsageStats stats={{ callsThisMonth: 100, trend: 'up' }} />);
    expect(screen.getByText('Increasing')).toBeInTheDocument();
  });

  it('should show decreasing trend', () => {
    render(<UsageStats stats={{ callsThisMonth: 100, trend: 'down' }} />);
    expect(screen.getByText('Decreasing')).toBeInTheDocument();
  });

  it('should show "Never" when lastCalledAt not set', () => {
    render(<UsageStats stats={{ callsThisMonth: 100 }} />);
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('should show daily usage chart when stats present', () => {
    render(<UsageStats stats={{ callsThisMonth: 100 }} />);
    expect(screen.getByText('Daily usage (last 7 days)')).toBeInTheDocument();
    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Sun')).toBeInTheDocument();
  });

  it('should render heading', () => {
    render(<UsageStats />);
    expect(screen.getByText('Usage Statistics')).toBeInTheDocument();
    expect(screen.getByText('This month')).toBeInTheDocument();
  });
});
