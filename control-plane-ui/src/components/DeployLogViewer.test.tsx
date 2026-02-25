import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DeployLogViewer } from './DeployLogViewer';

const makeLogs = (overrides?: Partial<{ level: string; step: string }>[]) => {
  const defaults = [
    {
      id: '1',
      level: 'info',
      step: 'init',
      message: 'Starting deploy',
      created_at: '2026-02-15T10:00:01Z',
    },
    {
      id: '2',
      level: 'warn',
      step: 'sync',
      message: 'Slow response',
      created_at: '2026-02-15T10:00:02Z',
    },
    {
      id: '3',
      level: 'error',
      step: null,
      message: 'Connection failed',
      created_at: '2026-02-15T10:00:03Z',
    },
  ];
  if (overrides) {
    return defaults.map((d, i) => ({ ...d, ...(overrides[i] || {}) }));
  }
  return defaults;
};

describe('DeployLogViewer', () => {
  it('renders empty state when no logs', () => {
    render(<DeployLogViewer logs={[]} />);
    expect(screen.getByText('Waiting for deploy logs...')).toBeInTheDocument();
  });

  it('renders log messages', () => {
    render(<DeployLogViewer logs={makeLogs()} />);
    expect(screen.getByText('Starting deploy')).toBeInTheDocument();
    expect(screen.getByText('Slow response')).toBeInTheDocument();
    expect(screen.getByText('Connection failed')).toBeInTheDocument();
  });

  it('renders log levels', () => {
    render(<DeployLogViewer logs={makeLogs()} />);
    expect(screen.getByText('info')).toBeInTheDocument();
    expect(screen.getByText('warn')).toBeInTheDocument();
    expect(screen.getByText('error')).toBeInTheDocument();
  });

  it('renders step labels when present', () => {
    render(<DeployLogViewer logs={makeLogs()} />);
    expect(screen.getByText('[init]')).toBeInTheDocument();
    expect(screen.getByText('[sync]')).toBeInTheDocument();
  });
});
