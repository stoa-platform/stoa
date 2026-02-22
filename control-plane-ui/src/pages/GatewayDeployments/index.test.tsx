import { describe, it, expect } from 'vitest';
import * as exports from './index';

describe('GatewayDeployments index exports', () => {
  it('exports GatewayDeploymentsDashboard', () => {
    expect(exports.GatewayDeploymentsDashboard).toBeDefined();
  });

  it('exports DeployAPIDialog', () => {
    expect(exports.DeployAPIDialog).toBeDefined();
  });
});
