import type { GatewayOverviewResponse } from '../../types';

export function filterProminentOverviewWarnings(
  warnings: GatewayOverviewResponse['data_quality']['warnings']
) {
  return warnings.filter((warning) => warning.severity !== 'info');
}
