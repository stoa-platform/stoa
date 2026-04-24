/**
 * Regression lock — CAB-2164 UI-3 Cleanup.
 *
 * // regression for CAB-2164
 *
 * Anchors the invariants of the UI-3 cleanup batch:
 *   - P2-11: `REWRITE-BUGS.md` exists (the file renamed + created is the fix).
 *   - P2-12: `src/services/api/gateways.ts` and
 *            `src/services/api/gatewayDeployments.ts` carry 0 `any` tokens
 *            and 0 `eslint-disable no-explicit-any` markers.
 *   - Consumer contract: `GatewayDetail.tsx` reads real backend fields
 *            (`desired_state?.api_name` + `gateway_environment`) instead of
 *            the flat `d.api_name` / `d.environment` reads that silently
 *            returned undefined against the real payload.
 *   - `AggregatedMetrics` exposes optional `guardrails`/`rate_limiting`
 *     slices consumed by `GuardrailsDashboard.tsx`.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, expectTypeOf, it } from 'vitest';
import type {
  AggregatedMetrics,
  GatewayGuardrailsEvent,
  GatewayHealthSummary,
  GatewayInstance,
  GatewayInstanceCreate,
  GatewayInstanceUpdate,
  GatewayModeStats,
  GatewayPolicy,
  PaginatedGatewayDeployments,
  PaginatedGatewayInstances,
} from '../../types';

const REPO_ROOT = join(__dirname, '..', '..', '..', '..');

function readRepoFile(relative: string): string {
  return readFileSync(join(REPO_ROOT, relative), 'utf8');
}

describe('regression/CAB-2164', () => {
  describe('P2-11 — REWRITE-BUGS.md + BACKEND-GAPS-CAB-2159.md present', () => {
    it('REWRITE-BUGS.md documents zombies + UI-3 findings', () => {
      const source = readRepoFile('control-plane-ui/REWRITE-BUGS.md');
      expect(source).toMatch(/§A — Zombies preserved/);
      expect(source).toMatch(/§B — UI-3 findings digest/);
      expect(source).toMatch(/CAB-2164/);
    });

    it('BACKEND-GAPS-CAB-2159.md carries BUG-6..9 (UI-3-discovered gaps)', () => {
      const source = readRepoFile('control-plane-ui/BACKEND-GAPS-CAB-2159.md');
      expect(source).toMatch(/BUG-6/);
      expect(source).toMatch(/BUG-7/);
      expect(source).toMatch(/BUG-8/);
      expect(source).toMatch(/BUG-9/);
    });
  });

  describe('P2-12 — zero `any` in gateways/deployments clients', () => {
    const ANY_PATTERN = /(:\s*any\b|<any>|as any\b|any\[\])/;
    const DISABLE_PATTERN = /eslint-disable-next-line\s+@typescript-eslint\/no-explicit-any/;

    const targets = [
      'control-plane-ui/src/services/api/gateways.ts',
      'control-plane-ui/src/services/api/gatewayDeployments.ts',
    ];

    for (const target of targets) {
      it(`${target} has no \`any\` tokens`, () => {
        const source = readRepoFile(target);
        expect(source).not.toMatch(ANY_PATTERN);
      });

      it(`${target} has no \`eslint-disable no-explicit-any\` markers`, () => {
        const source = readRepoFile(target);
        expect(source).not.toMatch(DISABLE_PATTERN);
      });
    }
  });

  describe('GatewayDetail.tsx reads real backend fields', () => {
    it('maps deployments with desired_state?.api_name + gateway_environment', () => {
      const source = readRepoFile('control-plane-ui/src/pages/Gateways/GatewayDetail.tsx');
      // Correct paths present:
      expect(source).toContain('d.desired_state?.api_name');
      expect(source).toContain('d.gateway_environment');
      // Flat (wrong) paths gone:
      expect(source).not.toMatch(/\bd\.api_name\b/);
      expect(source).not.toMatch(/\bd\.environment\b/);
      // No more wide cast fallback:
      expect(source).not.toContain('(d: Record<string, unknown>)');
    });
  });

  describe('Type contracts (tsc-anchored)', () => {
    it('AggregatedMetrics exposes optional guardrails + rate_limiting slices', () => {
      expectTypeOf<AggregatedMetrics>().toHaveProperty('guardrails');
      expectTypeOf<AggregatedMetrics>().toHaveProperty('rate_limiting');
    });

    it('GatewayGuardrailsEvent carries the consumer-observed shape', () => {
      expectTypeOf<GatewayGuardrailsEvent>().toHaveProperty('timestamp');
      expectTypeOf<GatewayGuardrailsEvent>().toHaveProperty('trace_id');
      expectTypeOf<GatewayGuardrailsEvent>().toHaveProperty('span_id');
      expectTypeOf<GatewayGuardrailsEvent>().toHaveProperty('tool');
      expectTypeOf<GatewayGuardrailsEvent>().toHaveProperty('action');
      expectTypeOf<GatewayGuardrailsEvent>().toHaveProperty('reason');
    });

    it('GatewayHealthSummary + GatewayModeStats are exposed from types/index', () => {
      expectTypeOf<GatewayHealthSummary>().toHaveProperty('online');
      expectTypeOf<GatewayModeStats>().toHaveProperty('total_gateways');
    });

    it('PaginatedGatewayInstances + PaginatedGatewayDeployments wrap UI item types', () => {
      expectTypeOf<PaginatedGatewayInstances['items']>().toEqualTypeOf<GatewayInstance[]>();
      // PaginatedGatewayDeployments narrows items to UI GatewayDeployment (with
      // the P2-E-typed desired_state), not the looser Schemas shape.
      expectTypeOf<PaginatedGatewayDeployments['items'][number]>().toHaveProperty('desired_state');
    });

    it('GatewayInstanceCreate + GatewayInstanceUpdate + GatewayPolicy reachable', () => {
      expectTypeOf<GatewayInstanceCreate>().toHaveProperty('name');
      expectTypeOf<GatewayInstanceUpdate>().toHaveProperty('display_name');
      expectTypeOf<GatewayPolicy>().toHaveProperty('policy_type');
    });
  });
});
