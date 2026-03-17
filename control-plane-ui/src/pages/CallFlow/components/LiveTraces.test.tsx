import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LiveTraces } from './LiveTraces';
import type { TraceEntry } from './LiveTraces';

const mockTrace: TraceEntry = {
  id: 'trace-001',
  route: '/api/customers',
  method: 'GET',
  mode: 'edge-mcp',
  statusCode: 200,
  durationMs: 45,
  timestamp: '2026-03-17T12:00:00Z',
  spans: [
    {
      name: 'gateway_ingress',
      service: 'stoa-gateway',
      startOffsetMs: 0,
      durationMs: 5,
      status: 'success',
    },
    {
      name: 'auth_validation',
      service: 'stoa-gateway',
      startOffsetMs: 5,
      durationMs: 10,
      status: 'success',
    },
    {
      name: 'backend_call',
      service: 'stoa-gateway',
      startOffsetMs: 15,
      durationMs: 25,
      status: 'success',
    },
  ],
};

const errorTrace: TraceEntry = {
  ...mockTrace,
  id: 'trace-002',
  statusCode: 500,
  durationMs: 1200,
  spans: [
    {
      name: 'gateway_ingress',
      service: 'stoa-gateway',
      startOffsetMs: 0,
      durationMs: 5,
      status: 'success',
    },
    {
      name: 'backend_call',
      service: 'stoa-gateway',
      startOffsetMs: 5,
      durationMs: 1195,
      status: 'error',
    },
  ],
};

describe('LiveTraces', () => {
  it('renders empty state when no traces', () => {
    render(<LiveTraces traces={[]} />);
    expect(screen.getByText(/no recent traces/i)).toBeInTheDocument();
  });

  it('renders trace table with data', () => {
    render(<LiveTraces traces={[mockTrace]} />);
    expect(screen.getByText(/GET \/api\/customers/)).toBeInTheDocument();
    expect(screen.getByText('45ms')).toBeInTheDocument();
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('Gateway')).toBeInTheDocument();
  });

  it('highlights error traces', () => {
    const { container } = render(<LiveTraces traces={[errorTrace]} />);
    const row = container.querySelector('tr.bg-red-50\\/50');
    expect(row).toBeInTheDocument();
  });

  it('calls onSelectTrace on row click', () => {
    const handler = vi.fn();
    render(<LiveTraces traces={[mockTrace]} onSelectTrace={handler} />);
    fireEvent.click(screen.getByText('45ms').closest('tr')!);
    expect(handler).toHaveBeenCalledWith('trace-001');
  });

  it('renders span legend', () => {
    render(<LiveTraces traces={[mockTrace]} />);
    expect(screen.getByText('gateway ingress')).toBeInTheDocument();
    expect(screen.getByText('auth validation')).toBeInTheDocument();
    expect(screen.getByText('backend call')).toBeInTheDocument();
  });
});
