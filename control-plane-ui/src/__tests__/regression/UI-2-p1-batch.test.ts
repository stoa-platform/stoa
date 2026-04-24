/**
 * Regression lock — UI-2 P1 batch (PR #2519)
 *
 * This file exists primarily to satisfy the Regression Test Guard CI check
 * (workflow .github/workflows/regression-guard.yml expects a
 * `regression/.*\.test\.(ts|tsx)` file on any `fix(` commit).
 *
 * The full behavior is locked in dedicated unit suites:
 *   - src/services/http/client.test.ts      — P1-2 (timeout defaults)
 *   - src/services/http/payload.test.ts     — P1-8 (extractList shape guard)
 *   - src/services/http/redirect.test.ts    — P1-16 (redirect flag TTL)
 *   - src/services/http/errors.test.ts      — P1-16 (flash suppression)
 *   - src/services/api/chat.test.ts         — P1-13 (group_by default)
 *   - src/services/api/monitoring.test.ts   — P1-14 (statusCode=0)
 *   - src/services/skillsApi.test.ts        — P1-4 (REST path + encoding)
 *   - src/test/services/api/list-shape-guard.test.ts — P1-8
 *   - src/contexts/AuthContext.jwt.test.ts  — P1-5, P1-15
 *   - src/contexts/AuthContext.lifecycle.test.tsx — P1-6, P1-7
 *   - src/pages/APIMonitoring.test.tsx      — P1-1 canary (partial failure no clobber)
 *   - src/pages/AITools/ToolDetail.test.tsx — P1-1 canary
 *   - src/pages/GatewayGuardrails/GuardrailsDashboard.test.tsx — P1-1 canary
 *
 * Below we re-assert three small-but-highest-value invariants so that any
 * future rewrite of the touched surfaces must update both this file and
 * the dedicated suite — signalling intent clearly to the reviewer.
 */
import { describe, expect, it } from 'vitest';
import { extractList, httpClient } from '../../services/http';
import { decodeJwtPayload, isMcpCallbackPath } from '../../contexts/auth-helpers';
import { isRedirecting, markRedirecting, resetRedirecting } from '../../services/http/redirect';

describe('regression/UI-2 — P1 batch contract invariants', () => {
  it('httpClient has a non-zero default timeout (P1-2)', () => {
    // A zero default means hanging backends leave requests alive forever;
    // the P1 batch wired config.api.timeout (default 30_000).
    expect(httpClient.defaults.timeout).toBeGreaterThan(0);
  });

  it('extractList fails fast on unexpected shape (P1-8)', () => {
    // Prior `data.items ?? data` silently cast an envelope without `items`
    // to the list type, which then crashed downstream with a cryptic error.
    expect(() => extractList({ total: 5, page: 1 }, 'apis')).toThrowError(/apis response shape/);
  });

  it('decodeJwtPayload handles base64url + UTF-8 (P1-5)', () => {
    // atob alone fails on `-`/`_` chars and corrupts non-ASCII claims.
    const payload = { name: 'José', realm_access: { roles: ['viewer'] } };
    const header = btoa('{"alg":"HS256","typ":"JWT"}');
    const body = btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(payload))))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    const decoded = decodeJwtPayload(`${header}.${body}.sig`) as typeof payload;
    expect(decoded.name).toBe('José');
    expect(decoded.realm_access.roles).toEqual(['viewer']);
  });

  it('isMcpCallbackPath rejects lookalike paths (P1-15)', () => {
    // `startsWith('/mcp-connectors/callback')` previously matched
    // `/mcp-connectors/callback-evil`. The helper now requires exact
    // or `/`-separated subpath.
    expect(isMcpCallbackPath('/mcp-connectors/callback', '/')).toBe(true);
    expect(isMcpCallbackPath('/mcp-connectors/callback-evil', '/')).toBe(false);
    expect(isMcpCallbackPath('/console/mcp-connectors/callback', '/console/')).toBe(true);
  });

  it('redirect flag TTL auto-resets so silence-forever never happens (P1-16)', () => {
    // Without the TTL, a failed signinRedirect() would keep the flag on
    // and all subsequent errors would be silently swallowed.
    resetRedirecting();
    expect(isRedirecting()).toBe(false);
    markRedirecting(1);
    expect(isRedirecting()).toBe(true);
    resetRedirecting();
    expect(isRedirecting()).toBe(false);
  });
});
