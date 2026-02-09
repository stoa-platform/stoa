CAB-864 Phase 1 — mTLS Architecture Design + ADR (docs only, PAS de code).

Branch: `feat/cab-864-mtls-design`

## Contexte technique (architecture auth actuelle du Gateway)

### stoa-gateway/src/auth/ — 7 fichiers
```
auth/
├── mod.rs          — exports: JWT, API Key, RBAC, combined middleware
├── claims.rs       — Claims struct (310 lignes): sub, exp, iat, iss, aud, tenant,
│                     realm_access, resource_access, scope
│                     Helpers: user_id(), tenant_id(), realm_roles(), has_scope()
│                     StoaRole enum: CpiAdmin, TenantAdmin, DevOps, Viewer
│                     AUCUN champ certificat actuellement
├── middleware.rs    — AuthState, AuthenticatedUser (391 lignes)
│                     auth_middleware(): Authorization header → JWT validate → inject user
│                     AuthUser / OptionalAuthUser: axum extractors
├── jwt.rs          — JwtValidator RS256 via JWKS (337 lignes)
│                     JwtValidatorConfig: issuer, audience, exp, leeway, required_scopes
│                     TokenExtractor: header/cookie/query
├── api_key.rs      — ApiKeyValidator avec moka cache 5min (211 lignes)
│                     combined_auth_middleware(): JWT first, fallback X-API-Key
├── oidc.rs         — OIDC discovery + JWKS caching (moka 5min)
└── rbac.rs         — RBAC enforcement (roles + scopes + tenant isolation)
```

### Flow auth actuel
```
Request → Authorization: Bearer <token> OU X-API-Key: <key>
       → JWT path: JWKS fetch → RS256 verify → extract Claims → AuthenticatedUser
       → API Key path: cache check → CP API /keys/validate → ApiKeyInfo
       → Handler accede via AuthUser extractor
```

### Aucun code mTLS n'existe
- Grep "mtls|x509|certificate|X-SSL|X-Client-Cert" dans auth/ = ZERO match
- Claims struct n'a aucun champ certificat (pas de CN, DN, serial, fingerprint)
- AuthenticatedUser n'a aucune metadata certificat
- Le middleware ne regarde aucun header X-SSL-*

## Architecture cible (F5 BigIP + STOA Gateway)

```
Client App ──mTLS──► F5 BigIP ──HTTP + X.509 headers──► STOA Gateway ──► Backend
                     (TLS termination)                    (cert validation)
```

- F5 BigIP fait la terminaison mTLS (client cert validation)
- F5 forward les metadata certificat via headers HTTP
- STOA Gateway extrait les headers et lie au token OAuth2 (RFC 8705)
- Le backend recoit un token enrichi avec binding certificat

## Taches

### 1. ADR — `docs/architecture/adr-draft-mtls-cert-bound-tokens.md`

Format ADR standard:

```markdown
# ADR-DRAFT: F5 mTLS Termination + RFC 8705 Certificate-Bound Tokens

## Status
Draft (sera renumerote en ADR-039+ dans stoa-docs)

## Context
[Pourquoi on a besoin de mTLS dans STOA]
- Clients enterprise (banques, assurances) exigent mTLS pour API access
- Infrastructure existante: F5 BigIP fait TLS termination
- STOA Gateway (Rust/axum) doit valider le binding certificat ↔ token
- Keycloak gere les tokens OAuth2 (consumer onboarding Phase 2 DONE)

## Decision
[Ce qu'on decide]

### Architecture
- F5 BigIP: mTLS termination, client cert validation, forward X.509 headers
- STOA Gateway: extract cert metadata from headers, verify RFC 8705 binding
- Keycloak: issue tokens with `cnf` claim (protocol mapper)

### Headers F5 → Gateway
| Header | Contenu | Exemple |
|--------|---------|---------|
| X-SSL-Client-Cert | PEM-encoded client cert (URL-encoded) | -----BEGIN%20CERT... |
| X-SSL-Client-S-DN | Subject DN | CN=acme-consumer,O=Acme Corp |
| X-SSL-Client-I-DN | Issuer DN | CN=STOA CA,O=STOA Platform |
| X-SSL-Client-Serial | Serial number | 0A:1B:2C:3D |
| X-SSL-Client-Fingerprint | SHA-256 fingerprint | a1b2c3d4... |
| X-SSL-Client-Verify | Verification status | SUCCESS |

### RFC 8705 Certificate-Bound Tokens
- Token endpoint: Keycloak issue JWT avec `cnf` claim
- `cnf` claim format: `{"x5t#S256": "<base64url-encoded-sha256-thumbprint>"}`
- Resource server (Gateway): extract cert thumbprint from header, compare avec `cnf.x5t#S256`
- Mismatch → 403 Forbidden

### Flow detaille (6 steps)
```
1. Client presente son certificat TLS a F5
2. F5 valide le cert (CA chain, expiry, revocation)
3. F5 forward request + headers X-SSL-* au Gateway
4. Gateway extrait thumbprint du header X-SSL-Client-Fingerprint
5. Gateway decode JWT, extrait cnf.x5t#S256
6. Gateway compare: thumbprint == cnf.x5t#S256
   → Match: request passe
   → Mismatch: 403 "certificate binding mismatch"
   → Missing header + mtls_required: 401
   → Missing cnf + mtls_require_binding: 403
```

### Keycloak Configuration
- Protocol Mapper: "x509-certificate-thumbprint"
- Token Claim Name: `cnf`
- Claim JSON Type: JSON
- Valeur: calculee depuis le client cert enregistre lors du consumer onboarding

## Consequences

### Positif
- Zero-trust: token lie au certificat, pas rejouable depuis un autre client
- Compatible F5 existant (pas de changement infra)
- Backward compatible: mtls_enabled=false par defaut

### Negatif
- Complexite config Keycloak (protocol mapper custom)
- Dependance F5 headers (pas standard, vendor-specific)
- Rotation certificat = rotation token binding
```

### 2. Architecture diagram — `docs/architecture/mtls-flow.md`

Diagramme ASCII detaille:
- Flow standard (6 etapes ci-dessus en detail)
- Flow bulk onboarding: CSV → API → Keycloak clients + cert registration
- Failure modes: table avec chaque cas d'erreur
- Config Gateway: champs a ajouter dans config.rs

### 3. Implementation roadmap (dans l'ADR, section "Implementation Plan")

- Phase 2: Module `auth/mtls.rs` (extraction headers + validation binding)
- Phase 2: Extension Claims struct (champ `cnf: Option<CnfClaim>`)
- Phase 2: Middleware wire (extract before JWT, verify after)
- Phase 3: Bulk onboarding endpoint (POST /admin/consumers/bulk, CSV, 100 max)
- Phase 3: Keycloak protocol mapper configuration

## Regles

- PAS DE CODE dans cette phase — design + ADR only
- ADR format: Status, Context, Decision, Consequences
- Diagrammes en ASCII art (pas mermaid, pas d'images)
- Le numero ADR est "DRAFT" — sera renumerote en ADR-039+ quand migre vers stoa-docs
- Les noms dans les exemples sont generiques ("acme-consumer", "tenant-bank")
- ZERO nom de client reel
- Commit: `docs(architecture): mTLS + RFC 8705 cert-bound tokens ADR draft (CAB-864 P1)`
