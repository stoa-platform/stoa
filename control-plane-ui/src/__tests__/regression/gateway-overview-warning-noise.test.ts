import { describe, expect, it } from 'vitest';
import { filterProminentOverviewWarnings } from '../../pages/Gateways/gatewayOverviewWarnings';

describe('regression/gateway-overview-warning-noise', () => {
  it('keeps informational runtime metrics warnings out of prominent gateway alerts', () => {
    expect(
      filterProminentOverviewWarnings([
        {
          code: 'runtime_metrics_partial',
          severity: 'info',
          message: 'Some runtime metrics are not available for this gateway',
        },
        {
          code: 'runtime_heartbeat_stale',
          severity: 'warning',
          message: 'Gateway heartbeat is stale',
        },
      ])
    ).toEqual([
      {
        code: 'runtime_heartbeat_stale',
        severity: 'warning',
        message: 'Gateway heartbeat is stale',
      },
    ]);
  });
});
