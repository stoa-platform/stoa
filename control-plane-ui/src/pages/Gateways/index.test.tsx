import { describe, it, expect } from 'vitest';
import * as exports from './index';

describe('Gateways index exports', () => {
  it('exports GatewayList', () => {
    expect(exports.GatewayList).toBeDefined();
  });

  it('exports GatewayModesDashboard', () => {
    expect(exports.GatewayModesDashboard).toBeDefined();
  });

  it('exports GatewayRegistrationForm', () => {
    expect(exports.GatewayRegistrationForm).toBeDefined();
  });
});
