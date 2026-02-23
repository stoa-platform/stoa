import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DeployLogViewer } from './DeployLogViewer';
import type { DeployLogEntry } from '@/types';

function makeLog(overrides: Partial<DeployLogEntry> = {}): DeployLogEntry {
  return {
    deployment_id: 'd1',
    tenant_id: 't1',
    seq: 1,
    level: 'info',
    step: null,
    message: 'test message',
    ...overrides,
  };
}

describe('DeployLogViewer', () => {
  it('renders empty state when no logs', () => {
    render(<DeployLogViewer logs={[]} />);
    expect(screen.getByText('No log entries yet.')).toBeInTheDocument();
  });

  it('renders log entries with sequence numbers', () => {
    const logs = [makeLog({ seq: 1, message: 'Starting deploy' })];
    render(<DeployLogViewer logs={logs} />);
    expect(screen.getByText('001')).toBeInTheDocument();
    expect(screen.getByText('Starting deploy')).toBeInTheDocument();
  });

  it('renders step badges when step is present', () => {
    const logs = [makeLog({ step: 'validating', message: 'Checking config' })];
    render(<DeployLogViewer logs={logs} />);
    expect(screen.getByText('[validating]')).toBeInTheDocument();
  });

  it('applies color classes based on log level', () => {
    const logs = [
      makeLog({ level: 'error', message: 'Failed!', seq: 1 }),
      makeLog({ level: 'warn', message: 'Careful!', seq: 2 }),
    ];
    render(<DeployLogViewer logs={logs} />);
    const errorMsg = screen.getByText('Failed!');
    const warnMsg = screen.getByText('Careful!');
    expect(errorMsg.className).toContain('text-red-400');
    expect(warnMsg.className).toContain('text-yellow-400');
  });

  it('shows streaming indicator when streaming prop is true', () => {
    render(<DeployLogViewer logs={[]} streaming={true} />);
    expect(screen.getByText('Streaming...')).toBeInTheDocument();
  });

  it('hides streaming indicator when streaming prop is false', () => {
    render(<DeployLogViewer logs={[]} streaming={false} />);
    expect(screen.queryByText('Streaming...')).not.toBeInTheDocument();
  });

  it('renders the Deploy Logs header', () => {
    render(<DeployLogViewer logs={[]} />);
    expect(screen.getByText('Deploy Logs')).toBeInTheDocument();
  });
});
