/**
 * Regression test for PR #1649 (CAB-1649)
 *
 * Root cause: PromQL queries used wrong label name `code` instead of `status`
 * for Gateway metrics, and missed `status_code` for Control Plane API metrics.
 *
 * Invariant: QUERIES object must use `status` for Gateway and `status_code` for API.
 */
import { describe, it, expect } from 'vitest';
import { QUERIES } from '../../pages/Operations/OperationsDashboard';

describe('regression/operations-promql-queries', () => {
  it('availability query uses status for Gateway and status_code for API', () => {
    expect(QUERIES.availability).toContain('stoa_http_requests_total{status=~"5.."}');
    expect(QUERIES.availability).not.toContain('{code=~');
    expect(QUERIES.availability).toContain(
      'stoa_control_plane_http_requests_total{status_code=~"5.."}'
    );
  });

  it('errorRate query uses status for Gateway and status_code for API', () => {
    expect(QUERIES.errorRate).toContain('stoa_http_requests_total{status=~"5.."}');
    expect(QUERIES.errorRate).not.toContain('{code=~');
    expect(QUERIES.errorRate).toContain(
      'stoa_control_plane_http_requests_total{status_code=~"5.."}'
    );
  });

  it('errorBudget query uses status (not code) label', () => {
    expect(QUERIES.errorBudget).toContain('stoa_http_requests_total{status=~"5.."}');
    expect(QUERIES.errorBudget).not.toContain('{code=~');
  });
});
