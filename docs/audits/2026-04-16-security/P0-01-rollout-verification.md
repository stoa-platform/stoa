# P0-01 Rollout Verification — CAB-2082 + CAB-2094 + CAB-2083

**Ticket**: CAB-2140 (audit-only, no code change)
**Parent MEGA**: CAB-2079 — Auth/RBAC hardening
**Date**: 2026-04-20
**Scope**: Verify that the Security P0 findings of the 2026-04-16 audit are deployed in prod (OVH MKS GRA9, namespace `stoa-system`).

## Summary

The three original P0 findings of the 2026-04-16 audit were mitigated between 2026-04-16 and 2026-04-20 by CAB-2082, CAB-2083 and CAB-2094. This document archives the evidence that those changes are live in prod.

**Result**: All three mitigations verified deployed and effective. **Close CAB-2140 as verified.**

## Findings vs. Mitigations

| Audit finding | Mitigation ticket | Merge commit | Status |
|---|---|---|---|
| P0-01 JWT issuer not validated | CAB-2082 | `9fef1523 fix(api): enforce JWT issuer + cache Keycloak public key (CAB-2082) (#2393)` | Done 2026-04-20 08:37 |
| P0-01 follow-up: internal vs public URL | CAB-2094 | `d300949b fix(api): split Keycloak public vs internal URL (CAB-2094) (#2399)` | Done 2026-04-17 20:24 |
| P0-02 Parzival hardcoded fallback | CAB-2083 | `4b211e08 fix(e2e): kill Parzival@2026! hardcoded fallback (CAB-2083) (#2394)` + hotfix `d0744d19` | Done 2026-04-20 08:25 |

## Evidence

### 1. Regression tests active

```
control-plane-api/tests/test_regression_cab_2082_jwt_issuer.py
control-plane-api/tests/test_regression_cab_2094_issuer_internal_url.py
control-plane-api/tests/test_regression_cab_2083_no_hardcoded_parzival.py
```

All three files present on `main` as of 2026-04-20. CI runs them on every PR. Reintroduction of any of the original bugs will break CI.

### 2. Prod deployment config (OVH MKS GRA9, `stoa-system` ns)

```bash
$ KUBECONFIG=~/.kube/config-stoa-ovh kubectl get deploy stoa-control-plane-api -n stoa-system -o yaml
```

Relevant env vars on prod pods:

| Env var | Value | Expected | Match |
|---|---|---|---|
| `KEYCLOAK_URL` | `https://auth.gostoa.dev` | public URL (authoritative for `iss` check) | ✅ |
| `KEYCLOAK_INTERNAL_URL` | `http://keycloak.stoa-system.svc.cluster.local` | internal service URL (for JWKS fetch) | ✅ |
| `KEYCLOAK_REALM` | `stoa` | | ✅ |
| `KEYCLOAK_CLIENT_ID` | `control-plane-api` | | ✅ |
| `CORS_ORIGINS` | `https://console.gostoa.dev,https://portal.gostoa.dev,http://localhost:3000,http://localhost:5173` | see note below | ⚠ localhost leak |

**⚠ Finding for CAB-2142**: `CORS_ORIGINS` in prod still includes `http://localhost:3000,http://localhost:5173`. Not directly exploitable (no credentials from an attacker-controlled localhost can be issued by the real Keycloak), but unnecessary attack surface. Covered by CAB-2142.

### 3. Image deployed

```
ghcr.io/stoa-platform/control-plane-api:dev-e0ba0fbc7342024fb9382dafd0e70ded37f77f7c
```

Commit `e0ba0fbc` post-dates all three mitigation merges (`9fef1523`, `d300949b`, `4b211e08`, `d0744d19`) per `git log --oneline`.

Pods status:

```
stoa-control-plane-api-84f5489b9d-jh2wh   1/1     Running   0   140m   10.2.3.149
stoa-control-plane-api-84f5489b9d-mtsqf   1/1     Running   0   140m   10.2.0.119
```

Both replicas Ready. Age 140 min → image picked up today.

### 4. Runtime fail-closed check

```bash
$ curl -sS -o /tmp/me-forged.txt -w "HTTP %{http_code}\n" \
    -H "Authorization: Bearer eyJhbGciOiJub25lIn0..." \
    https://api.gostoa.dev/v1/me

HTTP 401
Body: {"detail":"Invalid token: The specified alg value is not allowed"}
```

The forged token (`alg:none`) is rejected at the algorithm check, which is earlier than the issuer check but still demonstrates the fail-closed behavior. Issuer-specific rejection is covered by `test_regression_cab_2082_jwt_issuer.py::TestIssuerValidation::test_invalid_issuer_rejected_as_401`.

### 5. Parzival literal scan

```bash
$ grep -rn "Parzival@2026!" .
control-plane-api/CHANGELOG.md:48:* **e2e:** kill Parzival@2026! hardcoded fallback (CAB-2083) ...
control-plane-api/tests/test_regression_cab_2083_no_hardcoded_parzival.py:3:The literal `Parzival@2026!` ...
control-plane-api/tests/test_regression_cab_2083_no_hardcoded_parzival.py:19:FORBIDDEN_LITERAL = "Parzival@2026!"
```

Only CHANGELOG (historical) and the regression test itself (as the scan target). No live fallback in source.

## Conclusion

All three P0 findings of the 2026-04-16 audit are mitigated and verified in prod. CAB-2140 can be closed.

Residual findings for follow-up:
- **CAB-2142**: CORS localhost origins leak in prod — covered.
- **CAB-2141**: cancelled as duplicate of CAB-2083.
- The remaining P1/P2 findings (mcp_proxy, debug flags, rate-limit keying, portal storage) are tracked as CAB-2142, CAB-2143, CAB-2144, CAB-2145, CAB-2146.

No further action required on this ticket.
