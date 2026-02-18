import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { TopTools } from '../TopTools';
import { renderWithProviders } from '../../../test/helpers';
import type { ToolUsageStat } from '../../../types';

vi.mock('../../../services/usage', () => ({
  formatLatency: (ms: number) => `${ms}ms`,
}));

const makeTool = (overrides: Partial<ToolUsageStat> = {}): ToolUsageStat => ({
  tool_id: 'tool-1',
  tool_name: 'list-apis',
  call_count: 500,
  success_rate: 99.0,
  avg_latency_ms: 120,
  ...overrides,
});

describe('TopTools', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Top Tools heading', () => {
    renderWithProviders(<TopTools tools={[]} />);

    expect(screen.getByText('Top Tools')).toBeInTheDocument();
  });

  it('renders empty state when no tools', () => {
    renderWithProviders(<TopTools tools={[]} />);

    expect(screen.getByText('No tools used yet')).toBeInTheDocument();
  });

  it('renders tool name', () => {
    const tool = makeTool({ tool_name: 'create-order' });
    renderWithProviders(<TopTools tools={[tool]} />);

    expect(screen.getByText('create-order')).toBeInTheDocument();
  });

  it('renders call count', () => {
    const tool = makeTool({ call_count: 1500 });
    renderWithProviders(<TopTools tools={[tool]} />);

    expect(screen.getByText('1,500')).toBeInTheDocument();
  });

  it('renders rank number for each tool', () => {
    const tools = [
      makeTool({ tool_id: 't1', tool_name: 'tool-1', call_count: 500 }),
      makeTool({ tool_id: 't2', tool_name: 'tool-2', call_count: 300 }),
    ];
    renderWithProviders(<TopTools tools={tools} />);

    expect(screen.getByText('1.')).toBeInTheDocument();
    expect(screen.getByText('2.')).toBeInTheDocument();
  });

  it('renders progress bar for each tool', () => {
    const tool = makeTool();
    const { container } = renderWithProviders(<TopTools tools={[tool]} />);

    const bars = container.querySelectorAll('.bg-primary-400');
    expect(bars.length).toBeGreaterThan(0);
  });

  it('renders loading skeleton when isLoading is true', () => {
    renderWithProviders(<TopTools tools={[]} isLoading={true} />);

    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders multiple tools in order', () => {
    const tools = [
      makeTool({ tool_id: 't1', tool_name: 'list-apis', call_count: 500 }),
      makeTool({ tool_id: 't2', tool_name: 'create-api', call_count: 300 }),
      makeTool({ tool_id: 't3', tool_name: 'delete-api', call_count: 100 }),
    ];
    renderWithProviders(<TopTools tools={tools} />);

    expect(screen.getByText('list-apis')).toBeInTheDocument();
    expect(screen.getByText('create-api')).toBeInTheDocument();
    expect(screen.getByText('delete-api')).toBeInTheDocument();
  });

  it('renders first tool with full width bar (100%)', () => {
    const tools = [
      makeTool({ tool_id: 't1', call_count: 500 }),
      makeTool({ tool_id: 't2', call_count: 250 }),
    ];
    const { container } = renderWithProviders(<TopTools tools={tools} />);

    const bars = container.querySelectorAll<HTMLElement>('.bg-primary-400');
    expect(bars[0].style.width).toBe('100%');
    expect(bars[1].style.width).toBe('50%');
  });

  it('renders success rate in hover stats', () => {
    const tool = makeTool({ success_rate: 97.5 });
    renderWithProviders(<TopTools tools={[tool]} />);

    expect(screen.getByText('97.5% success')).toBeInTheDocument();
  });

  it('renders avg latency in hover stats', () => {
    const tool = makeTool({ avg_latency_ms: 200 });
    renderWithProviders(<TopTools tools={[tool]} />);

    expect(screen.getByText('200ms avg')).toBeInTheDocument();
  });
});
