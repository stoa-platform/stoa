import { describe, expect, it } from 'vitest';
import { deploymentModeValue } from '../../pages/Gateways/gatewayDisplay';
import type { GatewayInstance } from '../../types';

describe('regression/CAB-2173 sidecar mode display', () => {
  it('shows native STOA sidecar runtime mode instead of remote-agent topology mode', () => {
    const gateway = {
      gateway_type: 'stoa_sidecar',
      mode: 'sidecar',
      deployment_mode: 'connect',
    } as GatewayInstance;

    expect(deploymentModeValue(gateway)).toBe('sidecar');
  });
});
