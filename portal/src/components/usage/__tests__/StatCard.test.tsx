import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { StatCard } from '../StatCard';
import { renderWithProviders } from '../../../test/helpers';

describe('StatCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders title and value', () => {
    renderWithProviders(<StatCard title="Total Calls" value={1200} />);

    expect(screen.getByText('Total Calls')).toBeInTheDocument();
    expect(screen.getByText('1200')).toBeInTheDocument();
  });

  it('renders string value', () => {
    renderWithProviders(<StatCard title="Success Rate" value="95.5%" />);

    expect(screen.getByText('95.5%')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    renderWithProviders(<StatCard title="Calls" value={100} subtitle="This week" />);

    expect(screen.getByText('This week')).toBeInTheDocument();
  });

  it('does not render subtitle when not provided', () => {
    renderWithProviders(<StatCard title="Calls" value={100} />);

    expect(screen.queryByText('This week')).not.toBeInTheDocument();
  });

  it('renders positive trend', () => {
    renderWithProviders(
      <StatCard title="Calls" value={100} trend={{ value: 12, isPositive: true }} />
    );

    expect(screen.getByText('↑ 12%')).toBeInTheDocument();
  });

  it('renders negative trend', () => {
    renderWithProviders(
      <StatCard title="Calls" value={100} trend={{ value: 5, isPositive: false }} />
    );

    expect(screen.getByText('↓ 5%')).toBeInTheDocument();
  });

  it('renders loading skeleton when isLoading is true', () => {
    renderWithProviders(<StatCard title="Calls" value={100} isLoading={true} />);

    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
    // Value not shown while loading
    expect(screen.queryByText('100')).not.toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    const icon = <span data-testid="test-icon">icon</span>;
    renderWithProviders(<StatCard title="Calls" value={100} icon={icon} />);

    expect(screen.getByTestId('test-icon')).toBeInTheDocument();
  });

  it('renders with default color (cyan)', () => {
    const { container } = renderWithProviders(<StatCard title="Calls" value={100} />);

    expect(container.querySelector('.border-cyan-200')).toBeInTheDocument();
  });

  it('renders with emerald color', () => {
    const { container } = renderWithProviders(
      <StatCard title="Calls" value={100} color="emerald" />
    );

    expect(container.querySelector('.border-emerald-200')).toBeInTheDocument();
  });

  it('renders with amber color', () => {
    const { container } = renderWithProviders(<StatCard title="Calls" value={100} color="amber" />);

    expect(container.querySelector('.border-amber-200')).toBeInTheDocument();
  });

  it('renders with red color', () => {
    const { container } = renderWithProviders(<StatCard title="Calls" value={100} color="red" />);

    expect(container.querySelector('.border-red-200')).toBeInTheDocument();
  });

  it('renders with purple color', () => {
    const { container } = renderWithProviders(
      <StatCard title="Calls" value={100} color="purple" />
    );

    expect(container.querySelector('.border-purple-200')).toBeInTheDocument();
  });
});
