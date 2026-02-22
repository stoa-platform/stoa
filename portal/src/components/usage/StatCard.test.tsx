/**
 * Tests for StatCard (CAB-1390)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { StatCard } from './StatCard';
import { renderWithProviders } from '../../test/helpers';

describe('StatCard', () => {
  it('renders the title and value', () => {
    renderWithProviders(<StatCard title="Total Calls" value={1234} />);
    expect(screen.getByText('Total Calls')).toBeInTheDocument();
    expect(screen.getByText('1234')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    renderWithProviders(<StatCard title="Calls" value={42} subtitle="This week" />);
    expect(screen.getByText('This week')).toBeInTheDocument();
  });

  it('shows loading skeleton when isLoading is true', () => {
    const { container } = renderWithProviders(
      <StatCard title="Calls" value={0} isLoading={true} />
    );
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('does not show the value when loading', () => {
    renderWithProviders(<StatCard title="Calls" value={999} isLoading={true} />);
    expect(screen.queryByText('999')).not.toBeInTheDocument();
  });

  it('renders positive trend badge', () => {
    renderWithProviders(
      <StatCard title="Calls" value={100} trend={{ value: 12, isPositive: true }} />
    );
    expect(screen.getByText(/12%/i)).toBeInTheDocument();
  });

  it('renders negative trend badge', () => {
    renderWithProviders(
      <StatCard title="Calls" value={100} trend={{ value: 8, isPositive: false }} />
    );
    expect(screen.getByText(/8%/i)).toBeInTheDocument();
  });

  it('renders string values', () => {
    renderWithProviders(<StatCard title="Rate" value="99.5%" />);
    expect(screen.getByText('99.5%')).toBeInTheDocument();
  });
});
