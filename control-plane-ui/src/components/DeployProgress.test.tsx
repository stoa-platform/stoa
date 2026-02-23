import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DeployProgress } from './DeployProgress';
import type { DeployLogEntry, DeployEventType } from '@/types';

function makeLog(overrides: Partial<DeployLogEntry> = {}): DeployLogEntry {
  return {
    deployment_id: 'd1',
    tenant_id: 't1',
    seq: 1,
    level: 'info',
    step: null,
    message: 'test',
    ...overrides,
  };
}

describe('DeployProgress', () => {
  it('renders all four deploy steps', () => {
    render(<DeployProgress logs={[]} lastEvent={null} />);
    expect(screen.getByText('validating')).toBeInTheDocument();
    expect(screen.getByText('syncing')).toBeInTheDocument();
    expect(screen.getByText('health-check')).toBeInTheDocument();
    expect(screen.getByText('complete')).toBeInTheDocument();
  });

  it('marks active steps from log entries', () => {
    const logs = [makeLog({ step: 'validating' }), makeLog({ step: 'syncing', seq: 2 })];
    render(<DeployProgress logs={logs} lastEvent={null} />);
    // Active steps should have blue text
    const syncing = screen.getByText('syncing');
    expect(syncing.className).toContain('text-blue-400');
  });

  it('marks all steps as done on deploy-success', () => {
    const logs = [makeLog({ step: 'validating' })];
    render(<DeployProgress logs={logs} lastEvent={'deploy-success' as DeployEventType} />);
    const validating = screen.getByText('validating');
    expect(validating.className).toContain('text-green-400');
  });

  it('marks active step as failed on deploy-failed', () => {
    const logs = [makeLog({ step: 'syncing' })];
    render(<DeployProgress logs={logs} lastEvent={'deploy-failed' as DeployEventType} />);
    const syncing = screen.getByText('syncing');
    expect(syncing.className).toContain('text-red-400');
  });

  it('infers earlier steps as done when later steps are active', () => {
    const logs = [makeLog({ step: 'health-check' })];
    render(<DeployProgress logs={logs} lastEvent={null} />);
    const validating = screen.getByText('validating');
    expect(validating.className).toContain('text-green-400');
  });
});
