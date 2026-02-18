import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { CallsTable } from '../CallsTable';
import { renderWithProviders } from '../../../test/helpers';
import type { UsageCall } from '../../../types';

vi.mock('../../../services/usage', () => ({
  formatLatency: (ms: number) => `${ms}ms`,
}));

const makeCall = (overrides: Partial<UsageCall> = {}): UsageCall => ({
  id: 'call-1',
  tool_id: 'tool-1',
  tool_name: 'list-apis',
  timestamp: new Date(Date.now() - 60000).toISOString(), // 1 min ago
  status: 'success',
  latency_ms: 120,
  ...overrides,
});

describe('CallsTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Recent Calls heading', () => {
    renderWithProviders(<CallsTable calls={[]} />);

    expect(screen.getByText('Recent Calls')).toBeInTheDocument();
  });

  it('renders empty state when no calls', () => {
    renderWithProviders(<CallsTable calls={[]} />);

    expect(screen.getByText('No calls found')).toBeInTheDocument();
  });

  it('renders table headers', () => {
    renderWithProviders(<CallsTable calls={[]} />);

    expect(screen.getByText('Time')).toBeInTheDocument();
    expect(screen.getByText('Tool')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Latency')).toBeInTheDocument();
  });

  it('renders a call row with tool name and id', () => {
    const call = makeCall({ tool_name: 'create-api', tool_id: 'tool-42' });
    renderWithProviders(<CallsTable calls={[call]} />);

    expect(screen.getByText('create-api')).toBeInTheDocument();
    expect(screen.getByText('tool-42')).toBeInTheDocument();
  });

  it('renders success status badge', () => {
    const call = makeCall({ status: 'success' });
    renderWithProviders(<CallsTable calls={[call]} />);

    // 'Success' appears in both filter button and badge — getAll to confirm both
    const allSuccess = screen.getAllByText('Success');
    expect(allSuccess.length).toBeGreaterThanOrEqual(2);
  });

  it('renders error status badge', () => {
    const call = makeCall({ status: 'error' });
    renderWithProviders(<CallsTable calls={[call]} />);

    // 'Error' appears in both filter button and badge
    const allError = screen.getAllByText('Error');
    expect(allError.length).toBeGreaterThanOrEqual(2);
  });

  it('renders timeout status badge', () => {
    const call = makeCall({ status: 'timeout' });
    renderWithProviders(<CallsTable calls={[call]} />);

    // 'Timeout' appears in both filter button and badge
    const allTimeout = screen.getAllByText('Timeout');
    expect(allTimeout.length).toBeGreaterThanOrEqual(2);
  });

  it('renders latency from formatLatency', () => {
    const call = makeCall({ latency_ms: 200 });
    renderWithProviders(<CallsTable calls={[call]} />);

    expect(screen.getByText('200ms')).toBeInTheDocument();
  });

  it('renders loading skeleton when isLoading is true', () => {
    renderWithProviders(<CallsTable calls={[]} isLoading={true} />);

    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders filter buttons', () => {
    renderWithProviders(<CallsTable calls={[]} />);

    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Success')).toBeInTheDocument();
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('Timeout')).toBeInTheDocument();
  });

  it('filters calls by status when filter button clicked', () => {
    const calls = [
      makeCall({ id: 'c1', status: 'success', tool_name: 'tool-success' }),
      makeCall({ id: 'c2', status: 'error', tool_name: 'tool-error' }),
    ];
    renderWithProviders(<CallsTable calls={calls} />);

    // Get the filter button specifically (in the filter bar, not the status badge)
    const filterButtons = screen
      .getAllByRole('button')
      .filter((btn) => ['All', 'Success', 'Error', 'Timeout'].includes(btn.textContent ?? ''));
    const errorFilterBtn = filterButtons.find((btn) => btn.textContent === 'Error');
    expect(errorFilterBtn).toBeTruthy();
    fireEvent.click(errorFilterBtn!);

    expect(screen.queryByText('tool-success')).not.toBeInTheDocument();
    expect(screen.getByText('tool-error')).toBeInTheDocument();
  });

  it('shows all calls when All filter clicked after filtering', () => {
    const calls = [
      makeCall({ id: 'c1', status: 'success', tool_name: 'tool-success' }),
      makeCall({ id: 'c2', status: 'error', tool_name: 'tool-error' }),
    ];
    renderWithProviders(<CallsTable calls={calls} />);

    const filterButtons = screen
      .getAllByRole('button')
      .filter((btn) => ['All', 'Success', 'Error', 'Timeout'].includes(btn.textContent ?? ''));
    const errorFilterBtn = filterButtons.find((btn) => btn.textContent === 'Error')!;
    const allFilterBtn = filterButtons.find((btn) => btn.textContent === 'All')!;

    fireEvent.click(errorFilterBtn);
    fireEvent.click(allFilterBtn);

    expect(screen.getByText('tool-success')).toBeInTheDocument();
    expect(screen.getByText('tool-error')).toBeInTheDocument();
  });

  it('calls onFilterChange when filter changes', () => {
    const onFilterChange = vi.fn();
    renderWithProviders(<CallsTable calls={[]} onFilterChange={onFilterChange} />);

    const filterButtons = screen
      .getAllByRole('button')
      .filter((btn) => ['All', 'Success', 'Error', 'Timeout'].includes(btn.textContent ?? ''));
    const errorFilterBtn = filterButtons.find((btn) => btn.textContent === 'Error')!;
    fireEvent.click(errorFilterBtn);

    expect(onFilterChange).toHaveBeenCalledWith('error', null);
  });

  it('renders result count in footer', () => {
    const calls = [makeCall({ id: 'c1' }), makeCall({ id: 'c2' })];
    renderWithProviders(<CallsTable calls={calls} />);

    expect(screen.getByText(/2 results/)).toBeInTheDocument();
  });

  it('renders timestamp for each call', () => {
    const call = makeCall({
      timestamp: new Date(Date.now() - 5 * 60000).toISOString(), // 5 min ago
    });
    renderWithProviders(<CallsTable calls={[call]} />);

    expect(screen.getByText('5m ago')).toBeInTheDocument();
  });
});
