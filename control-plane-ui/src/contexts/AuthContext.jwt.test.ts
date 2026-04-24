import { describe, expect, it } from 'vitest';

import { decodeJwtPayload, isMcpCallbackPath } from './auth-helpers';

function encodeBase64Url(bytes: Uint8Array): string {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function craftJwt(payloadObj: unknown): string {
  const header = encodeBase64Url(new TextEncoder().encode('{"alg":"HS256","typ":"JWT"}'));
  const payload = encodeBase64Url(new TextEncoder().encode(JSON.stringify(payloadObj)));
  return `${header}.${payload}.signature`;
}

describe('decodeJwtPayload (P1-5 — base64url + UTF-8)', () => {
  it('decodes a standard base64url payload', () => {
    const token = craftJwt({ sub: 'user-1', realm_access: { roles: ['viewer'] } });
    const payload = decodeJwtPayload(token) as { sub: string; realm_access: { roles: string[] } };
    expect(payload.sub).toBe('user-1');
    expect(payload.realm_access.roles).toEqual(['viewer']);
  });

  it('handles payloads that contain base64url-specific chars (`-` and `_` via `>?` input)', () => {
    // Payload forcing `-` and `_` in the base64url encoding comes from
    // bytes that standard base64 encodes with `+` / `/`.
    // '\x3e\x3f' → standard b64 'Pj8' (no + or /), '\xfb\xef' → '++/' (close).
    // Easier: craft a payload whose JSON contains chars producing `+`/`/`
    // in std base64, which our base64url encoder then rewrites to `-`/`_`.
    const token = craftJwt({ weird: '>>>???' });
    const payload = decodeJwtPayload(token) as { weird: string };
    expect(payload.weird).toBe('>>>???');
  });

  it('pads short payload segments (length % 4 != 0) correctly', () => {
    // 1-char payload (after JSON stringify) produces a 4-char b64 segment
    // but we also want to exercise the 2-char and 3-char mod cases.
    // `{}` → 'e30' (3-char → 4-char with 1 `=`)
    const token = craftJwt({});
    const payload = decodeJwtPayload(token);
    expect(payload).toEqual({});
  });

  it('decodes UTF-8 claims (accents, non-ASCII display names)', () => {
    const token = craftJwt({ name: 'José Ñuño', preferred_username: 'naïve' });
    const payload = decodeJwtPayload(token) as { name: string; preferred_username: string };
    expect(payload.name).toBe('José Ñuño');
    expect(payload.preferred_username).toBe('naïve');
  });

  it('throws on a malformed token (missing payload segment)', () => {
    expect(() => decodeJwtPayload('only-one-segment')).toThrowError(/missing payload/);
  });
});

describe('isMcpCallbackPath (P1-15 — exact + basePath)', () => {
  it('matches the exact /mcp-connectors/callback at root base', () => {
    expect(isMcpCallbackPath('/mcp-connectors/callback', '/')).toBe(true);
  });

  it('matches a sub-path under /mcp-connectors/callback at root base', () => {
    expect(isMcpCallbackPath('/mcp-connectors/callback/linear', '/')).toBe(true);
  });

  it('rejects /mcp-connectors/callback-evil lookalike', () => {
    expect(isMcpCallbackPath('/mcp-connectors/callback-evil', '/')).toBe(false);
  });

  it('matches under a console basePath', () => {
    expect(isMcpCallbackPath('/console/mcp-connectors/callback', '/console/')).toBe(true);
  });

  it('tolerates missing trailing slash on baseUrl', () => {
    expect(isMcpCallbackPath('/console/mcp-connectors/callback', '/console')).toBe(true);
  });

  it('rejects paths outside /mcp-connectors/callback', () => {
    expect(isMcpCallbackPath('/dashboard', '/')).toBe(false);
    expect(isMcpCallbackPath('/mcp-connectors', '/')).toBe(false);
  });
});
