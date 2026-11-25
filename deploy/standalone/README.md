# Published-route JWT proof

`POST /admin/contracts` with `inboundAuth: "jwt"` (or a `policies` entry of
type `jwt_validation`) stores a `jwt_validation` policy on each generated REST
route. The dynamic proxy then requires a Keycloak RS256 bearer:

- no `Authorization` header → `401` and `WWW-Authenticate: Bearer ... error="invalid_request"`
- valid `client_credentials` token → proxied (`200` from the backend)
- expired token → `401` (`Token expired`)
- token the realm key did not sign → `401` (`Invalid token`)

A contract with no such policy is unchanged, including when classification
still lists advisory `auth-jwt`. Audience validation stays off.

Issuer is `{STOA_KEYCLOAK_URL}/realms/{STOA_KEYCLOAK_REALM}`.

```bash
# Gateway binary on the host, Keycloak and nginx in Docker:
STOA_PROOF_BIN=./stoa-gateway/target/debug/stoa-gateway deploy/standalone/jwt-proof.sh

# Or the gateway image:
deploy/standalone/jwt-proof.sh stoa-gateway:0.9.25
```

The script prints status codes only. It does not print the admin token or the
client secret.
