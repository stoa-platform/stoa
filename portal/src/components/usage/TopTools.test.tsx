/**
 * Tests for TopTools (CAB-1390)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { TopTools } from './TopTools';
import { renderWithProviders } from '../../test/helpers';
import type { ToolUsageStat } from '../../types';

const mockTools: ToolUsageStat[] = [
  { tool_id: 't1', tool_name: 'list-apis', call_count: 500, success_rate: 98, avg_latency_ms: 120 },
  {
    tool_id: 't2',
    tool_name: 'create-api',
    call_count: 300,
    success_rate: 95,
    avg_latency_ms: 200,
  },
  { tool_id: 't3', tool_name: 'delete-api', call_count: 100, success_rate: 99, avg_latency_ms: 80 },
];

describe('TopTools', () => {
  it('shows loading skeleton when isLoading is true', () => {
    const { container } = renderWithProviders(<TopTools tools={[]} isLoading={true} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows empty state when no tools', () => {
    renderWithProviders(<TopTools tools={[]} />);
    expect(screen.getByText('No tools used yet')).toBeInTheDocument();
  });

  it('renders tool names', () => {
    renderWithProviders(<TopTools tools={mockTools} />);
    expect(screen.getByText('list-apis')).toBeInTheDocument();
    expect(screen.getByText('create-api')).toBeInTheDocument();
    expect(screen.getByText('delete-api')).toBeInTheDocument();
  });

  it('renders call counts', () => {
    renderWithProviders(<TopTools tools={mockTools} />);
    expect(screen.getByText('500')).toBeInTheDocument();
    expect(screen.getByText('300')).toBeInTheDocument();
  });

  it('renders rank numbers (1., 2., 3...)', () => {
    renderWithProviders(<TopTools tools={mockTools} />);
    // Component renders rank as "{index + 1}." with trailing period
    expect(screen.getByText('1.')).toBeInTheDocument();
    expect(screen.getByText('2.')).toBeInTheDocument();
    expect(screen.getByText('3.')).toBeInTheDocument();
  });
});
