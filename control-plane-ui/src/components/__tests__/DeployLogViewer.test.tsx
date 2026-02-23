import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DeployLogViewer } from '../DeployLogViewer';
import type { DeploymentLog } from '../../types';

function makeLogs(count: number): DeploymentLog[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `log-${i}`,
    deployment_id: 'deploy-1',
    tenant_id: 'oasis-gunters',
    seq: i,
    level: (['info', 'warn', 'error', 'debug'] as const)[i % 4],
    step: i === 0 ? 'init' : undefined,
    message: `Log message ${i}`,
    created_at: new Date(2026, 1, 15, 10, 0, i).toISOString(),
  }));
}

describe('DeployLogViewer', () => {
  it('shows waiting message when no logs', () => {
    render(<DeployLogViewer logs={[]} />);
    expect(screen.getByText('Waiting for deploy logs...')).toBeInTheDocument();
  });

  it('renders log entries with level labels', () => {
    const logs = makeLogs(4);
    render(<DeployLogViewer logs={logs} />);

    expect(screen.getByText('Log message 0')).toBeInTheDocument();
    expect(screen.getByText('Log message 1')).toBeInTheDocument();
    expect(screen.getByText('Log message 2')).toBeInTheDocument();
    expect(screen.getByText('Log message 3')).toBeInTheDocument();

    // Level labels
    expect(screen.getByText('info')).toBeInTheDocument();
    expect(screen.getByText('warn')).toBeInTheDocument();
    expect(screen.getByText('error')).toBeInTheDocument();
    expect(screen.getByText('debug')).toBeInTheDocument();
  });

  it('renders step tags when present', () => {
    const logs = makeLogs(2);
    render(<DeployLogViewer logs={logs} />);
    expect(screen.getByText('[init]')).toBeInTheDocument();
  });

  it('respects maxHeight prop', () => {
    const logs = makeLogs(2);
    const { container } = render(<DeployLogViewer logs={logs} maxHeight="200px" />);
    const viewer = container.firstChild as HTMLElement;
    expect(viewer.style.maxHeight).toBe('200px');
  });
});
