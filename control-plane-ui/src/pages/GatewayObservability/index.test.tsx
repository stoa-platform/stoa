import { describe, it, expect } from 'vitest';
import * as exports from './index';

describe('GatewayObservability index exports', () => {
  it('exports GatewayObservabilityDashboard', () => {
    expect(exports.GatewayObservabilityDashboard).toBeDefined();
  });
});
