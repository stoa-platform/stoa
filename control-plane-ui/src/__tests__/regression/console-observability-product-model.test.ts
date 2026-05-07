import { describe, expect, it } from 'vitest';
import { observabilityTabs } from '../../components/subNavGroups';

describe('regression/console-observability-product-model', () => {
  it('keeps Console Observability centered on the three product views plus expert mode', () => {
    expect(observabilityTabs.map((tab) => [tab.label, tab.href])).toEqual([
      ['Gateway Health', '/observability'],
      ['Live Calls', '/observability/live-calls'],
      ['Security & Guardrails', '/observability/security'],
      ['Expert Mode', '/observability/grafana'],
    ]);
  });

  it('does not promote legacy observability dashboards as primary tabs', () => {
    const primaryHrefs = observabilityTabs.map((tab) => tab.href);

    expect(primaryHrefs).not.toContain('/logs');
    expect(primaryHrefs).not.toContain('/monitoring');
    expect(primaryHrefs).not.toContain('/call-flow');
    expect(primaryHrefs).not.toContain('/api-traffic');
    expect(primaryHrefs).not.toContain('/gateway-observability');
    expect(primaryHrefs).not.toContain('/gateway-guardrails');
  });
});
