import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DeploymentDetailDrawer } from './DeploymentDetailDrawer';
import type { GatewayDeployment } from '../../types';

vi.mock('../../services/api', () => ({
  apiService: {
    forceSyncDeployment: vi.fn().mockResolvedValue({}),
    undeployFromGateway: vi.fn().mockResolvedValue({}),
    testDeployment: vi.fn().mockResolvedValue({ reachable: true, status_code: 200 }),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(false), () => null],
}));

function makeDeployment(overrides: Partial<GatewayDeployment> = {}): GatewayDeployment {
  return {
    id: 'dep-1',
    api_catalog_id: 'cat-1',
    gateway_instance_id: 'gw-1',
    desired_state: {
      api_name: 'petstore',
      tenant_id: 'acme',
      backend_url: 'http://api.example.com',
    },
    desired_at: '2026-03-20T10:00:00Z',
    sync_status: 'pending',
    sync_attempts: 0,
    created_at: '2026-03-20T10:00:00Z',
    updated_at: '2026-03-20T10:00:00Z',
    gateway_name: 'stoa-dev',
    gateway_display_name: 'STOA Dev Gateway',
    gateway_type: 'stoa_edge_mcp',
    gateway_environment: 'dev',
    ...overrides,
  };
}

describe('DeploymentDetailDrawer', () => {
  it('renders API name and gateway info', () => {
    render(
      <DeploymentDetailDrawer deployment={makeDeployment()} onClose={vi.fn()} onAction={vi.fn()} />
    );
    expect(screen.getAllByText('petstore').length).toBeGreaterThan(0);
    expect(screen.getByText('STOA Dev Gateway')).toBeInTheDocument();
    expect(screen.getByText('dev')).toBeInTheDocument();
    expect(screen.getByText('stoa_edge_mcp')).toBeInTheDocument();
  });

  it('shows error banner when sync_error is present', () => {
    render(
      <DeploymentDetailDrawer
        deployment={makeDeployment({
          sync_status: 'error',
          sync_error: 'sync_api failed: HTTP 422 — backend_url required',
          sync_attempts: 3,
        })}
        onClose={vi.fn()}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText('Sync Error')).toBeInTheDocument();
    expect(
      screen.getByText('sync_api failed: HTTP 422 — backend_url required')
    ).toBeInTheDocument();
  });

  it('shows success banner for synced deployments', () => {
    render(
      <DeploymentDetailDrawer
        deployment={makeDeployment({ sync_status: 'synced' })}
        onClose={vi.fn()}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText('Successfully synced to gateway')).toBeInTheDocument();
  });

  it('shows Force Sync button for retryable statuses', () => {
    render(
      <DeploymentDetailDrawer
        deployment={makeDeployment({ sync_status: 'error' })}
        onClose={vi.fn()}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText('Force Sync')).toBeInTheDocument();
  });

  it('hides Force Sync button for synced deployments', () => {
    render(
      <DeploymentDetailDrawer
        deployment={makeDeployment({ sync_status: 'synced' })}
        onClose={vi.fn()}
        onAction={vi.fn()}
      />
    );
    expect(screen.queryByText('Force Sync')).not.toBeInTheDocument();
  });

  it('highlights empty fields in desired state', () => {
    render(
      <DeploymentDetailDrawer
        deployment={makeDeployment({
          desired_state: { api_name: 'petstore', backend_url: '' },
        })}
        onClose={vi.fn()}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText('(empty)')).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', async () => {
    const onClose = vi.fn();
    render(
      <DeploymentDetailDrawer deployment={makeDeployment()} onClose={onClose} onAction={vi.fn()} />
    );
    const closeButtons = screen.getAllByRole('button');
    // The X button is the first one in the header
    await userEvent.click(closeButtons[0]);
    expect(onClose).toHaveBeenCalled();
  });

  it('renders sync timeline with three steps', () => {
    render(
      <DeploymentDetailDrawer
        deployment={makeDeployment({ last_sync_attempt: '2026-03-20T10:05:00Z' })}
        onClose={vi.fn()}
        onAction={vi.fn()}
      />
    );
    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(screen.getByText('First sync attempt')).toBeInTheDocument();
    expect(screen.getByText('Synced to gateway')).toBeInTheDocument();
  });
});
