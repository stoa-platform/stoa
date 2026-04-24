/**
 * Regression lock — UI-1 Wave 1 bug hunt batch.
 *
 * // regression for UI-1 W1
 *
 * Anchors the 7 fixed invariants from BUG-REPORT-UI-1-W1.md:
 *   - P1-A: Application.client_id stays nullable on the UI alias, search
 *           filter coerces null via `?? ''`.
 *   - P1-B: .github/workflows/api-contract-check.yml uses `npm ci`.
 *   - P2-A: API alias has no stale ENRICHED `audience`/`created_at`/
 *           `updated_at`; GatewayInstance only narrows `visibility`.
 *   - P2-B: contract.test.ts asserts full required[] coverage (no
 *           `Math.min(required.length, 3)` cap).
 *   - P2-D: TraceDetail.tsx does not reach for `as unknown as`.
 *   - P2-E: GatewayDeployment.desired_state is typed (no `as any`
 *           accesses in GatewayDeploymentsDashboard.tsx).
 *   - P2-F: certificate_status cast sites use normalizeCertificateStatus.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, expectTypeOf, it } from 'vitest';
import type { Schemas } from '@stoa/shared/api-types';
import type { Application, API, GatewayInstance, GatewayDeployment } from '../../types';
import { normalizeCertificateStatus } from '../../types';

const REPO_ROOT = join(__dirname, '..', '..', '..', '..');

function readRepoFile(relative: string): string {
  return readFileSync(join(REPO_ROOT, relative), 'utf8');
}

describe('regression/UI-1-W1', () => {
  describe('P1-A — Application.client_id stays nullable', () => {
    it('preserves the backend `client_id: string | null` contract', () => {
      expectTypeOf<Application['client_id']>().toEqualTypeOf<
        Schemas['ApplicationResponse']['client_id']
      >();
    });

    it('preserves `tenant_id: string | null` (parallel dormant hazard)', () => {
      expectTypeOf<Application['tenant_id']>().toEqualTypeOf<
        Schemas['ApplicationResponse']['tenant_id']
      >();
    });

    it("Applications.tsx search filter coerces client_id with `?? ''`", () => {
      const source = readRepoFile('control-plane-ui/src/pages/Applications.tsx');
      expect(source).toContain("(app.client_id ?? '').toLowerCase()");
      expect(source).not.toContain('app.client_id.toLowerCase()');
    });
  });

  describe('P1-B — CI drift-gate uses npm ci', () => {
    it('api-contract-check.yml installs with lockfile', () => {
      const workflow = readRepoFile('.github/workflows/api-contract-check.yml');
      expect(workflow).toContain('npm ci');
      expect(workflow).not.toContain('npm install --no-save openapi-typescript');
    });
  });

  describe('P2-A — stale ENRICHED removed', () => {
    it('API alias no longer re-adds audience/created_at/updated_at', () => {
      // audience / created_at / updated_at come from Schemas['APIResponse'].
      expectTypeOf<API['audience']>().toEqualTypeOf<Schemas['APIResponse']['audience']>();
      expectTypeOf<API['created_at']>().toEqualTypeOf<Schemas['APIResponse']['created_at']>();
    });

    it('GatewayInstance is canonical except for visibility narrowing', () => {
      expectTypeOf<GatewayInstance['gateway_type']>().toEqualTypeOf<
        Schemas['GatewayInstanceResponse']['gateway_type']
      >();
      expectTypeOf<GatewayInstance['enabled']>().toEqualTypeOf<
        Schemas['GatewayInstanceResponse']['enabled']
      >();
      // visibility is narrowed — UI has a concrete shape the backend only
      // describes as `Record<string, unknown> | null`.
      expectTypeOf<GatewayInstance['visibility']>().toEqualTypeOf<
        { tenant_ids: string[] } | null | undefined
      >();
    });
  });

  describe('P2-B — contract test enforces full required[] coverage', () => {
    it('contract.test.ts asserts missing required[] is empty', () => {
      const source = readRepoFile('control-plane-ui/src/__tests__/contract.test.ts');
      // The new assertion:
      expect(source).toContain('should have ALL required properties covered');
      expect(source).toContain('expect(missing).toEqual([])');
      // The old cap is gone:
      expect(source).not.toContain('Math.min(required.length, 3)');
    });
  });

  describe('P2-D — TraceDetail unified on canonical schema', () => {
    it('TraceDetail.tsx does not use `as unknown as`', () => {
      const source = readRepoFile('control-plane-ui/src/pages/CallFlow/TraceDetail.tsx');
      expect(source).not.toContain('as unknown as');
    });

    it('MonitoringTransactionDetail aliases TransactionDetailWithDemoResponse', () => {
      const source = readRepoFile('control-plane-ui/src/services/api/monitoring.ts');
      expect(source).toContain(
        "export type MonitoringTransactionDetail = Schemas['TransactionDetailWithDemoResponse']"
      );
    });
  });

  describe('P2-E — GatewayDeployment.desired_state typed', () => {
    it('desired_state typed access compiles without casts', () => {
      // Forge a GatewayDeployment-shaped object (minimum required fields).
      const dep: GatewayDeployment = {
        id: 'd1',
        api_catalog_id: 'api-1',
        gateway_instance_id: 'gw-1',
        desired_state: { api_name: 'orders', tenant_id: 't1' },
        desired_at: '2026-04-24T00:00:00Z',
        sync_status: 'synced',
        sync_attempts: 0,
        created_at: '2026-04-24T00:00:00Z',
        updated_at: '2026-04-24T00:00:00Z',
      };
      // Typed access — no `as any` at the call site.
      const apiName: string | undefined =
        typeof dep.desired_state.api_name === 'string' ? dep.desired_state.api_name : undefined;
      expect(apiName).toBe('orders');
    });

    it('GatewayDeploymentsDashboard.tsx does not cast desired_state', () => {
      const source = readRepoFile(
        'control-plane-ui/src/pages/GatewayDeployments/GatewayDeploymentsDashboard.tsx'
      );
      expect(source).not.toContain('(dep.desired_state as any)');
      expect(source).not.toContain('desired_state as any');
    });
  });

  describe('P2-F — certificate_status coerced via normalizeCertificateStatus', () => {
    it('coerces null to undefined', () => {
      expect(normalizeCertificateStatus(null)).toBeUndefined();
    });

    it('coerces unknown strings to undefined', () => {
      expect(normalizeCertificateStatus('bogus')).toBeUndefined();
    });

    it('passes known values through unchanged', () => {
      expect(normalizeCertificateStatus('active')).toBe('active');
      expect(normalizeCertificateStatus('rotating')).toBe('rotating');
      expect(normalizeCertificateStatus('revoked')).toBe('revoked');
      expect(normalizeCertificateStatus('expired')).toBe('expired');
    });

    it('consumers no longer cast certificate_status blindly', () => {
      const consumers = readRepoFile('control-plane-ui/src/pages/Consumers.tsx');
      const detail = readRepoFile('control-plane-ui/src/components/ConsumerDetailModal.tsx');
      expect(consumers).not.toContain('certificate_status as CertificateStatus');
      expect(detail).not.toContain('certificate_status as CertificateStatus');
    });
  });
});
