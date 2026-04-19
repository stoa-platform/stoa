# Handoff — Fix claude.ai remote MCP connector vs stoa-gateway

**Date diagnostic** : 2026-04-17
**Branche au moment du diag** : `feat/cab-2095-stoactl-api-tenant-scope` (hors scope, ne pas mélanger)
**Cible prod cassée** : `https://mcp.gostoa.dev`
**Symptôme utilisateur** : claude.ai → "Authorization with the MCP server failed" (ref côté Anthropic `ofid_d2fef633fa45878c`).

Ce document est **self-contained**. Une session fraîche doit pouvoir l'exécuter sans contexte conversationnel.

---

## 0bis. Progression

| Phase | Ticket | Statut | Artefacts |
|-------|--------|--------|-----------|
| 1 — Fix Accept/SSE | [CAB-2106](https://linear.app/hlfh-workspace/issue/CAB-2106) | **Merged** `bd286867` (PR #2402) | — |
| 2 — Canary + prod validation (Accept) | [CAB-2106](https://linear.app/hlfh-workspace/issue/CAB-2106) | **Prod curl matrix PASS** on 0.9.6 (PR #2405 merged `bb5046f6`). ArgoCD rolled `dev-bd286867`. Insufficient — see Phase 3. | `AUDIT-RESULTS.md` |
| 3 — public_methods hotfix | [CAB-2109](https://linear.app/hlfh-workspace/issue/CAB-2109) | **Merged** `fb082f8c` (PR #2411), release 0.9.7 merged `400ae970` (PR #2412). Prod rollout `dev-fb082f8c` live on OVH MKS 2/2 pods. Discovery matrix + tools/call 401 contract all green on prod. | `AUDIT-RESULTS.md` |
| 3 — Enforce auth on /mcp/* | — | Pending | — |
| 4 — CORS ingress | — | Pending | — |
| 5 — OTLP saturation | — | Pending | — |

Phase 1 DoD:
- [x] `cargo test -p stoa-gateway` — 2158 lib + 47 contract + 52 integration + 15 resilience + 26 security, all green.
- [x] `RUSTFLAGS=-Dwarnings cargo clippy --all-targets -- -D warnings` — clean.
- [x] Unit tests `accepts_event_stream` — 9 cases.
- [x] Contract tests Accept × method — 9 cases on /mcp/sse (initialize, tools/list, tools/call × explicit SSE / both / q-values / case / JSON-only / absent + session reuse).
- [x] Manual curl reproduction against a running binary — PASS, recorded in `AUDIT-RESULTS.md`.
- [ ] PR opened — awaiting push authorization.

## 0. Contexte minimal

- `stoa-gateway` = binaire Rust, `stoa-system` ns sur cluster OVH MKS. Deux pods `stoa-gateway-5976d6b6f7-*`.
- Kubeconfig prod : `~/.kube/config-stoa-ovh`.
- Ingress nginx + ACME (cert-manager). Domaine `mcp.gostoa.dev` → service `stoa-gateway:80`.
- Keycloak = `https://auth.gostoa.dev/realms/stoa`. Le gateway agit comme AS-relais (DCR proxy) + RS (valide JWT).
- Deployment mode : `edge-mcp` (ADR-024).

---

## 1. Diagnostic validé (preuves)

### A. OAuth fonctionne
- `/.well-known/oauth-protected-resource` → 200
- `/.well-known/oauth-authorization-server` → 200 (issuer `auth.gostoa.dev`, registration_endpoint `mcp.gostoa.dev/oauth/register`)
- `POST /oauth/register` → 201 (DCR proxy Keycloak)
- `POST /oauth/token` → 200
- JWT validé côté gateway (logs `JWT validated — user authenticated`, user_id `2fefc656-8725-4761-95bb-1ae2e24db96e`, scopes `openid, profile, email, stoa:read, stoa:write, stoa:admin`)

### B. BUG P0 — Accept: text/event-stream non honoré
Le handler `POST /mcp/sse` retourne **toujours** `Content-Type: application/json` quel que soit le `Accept`. Spec Streamable HTTP MCP 2025-03-26 exige de retourner `text/event-stream` si le client l'accepte, et de maintenir le flux ouvert.

Reproduction :
```
curl -sS -D - -X POST https://mcp.gostoa.dev/mcp/sse \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
  --max-time 5
```
Observé : `HTTP/2 200`, `content-type: application/json`, body JSON complet + `mcp-session-id` dans les headers, connexion close.
Attendu : `content-type: text/event-stream`, frame SSE `event: message\ndata: {...}\n\n`, flux maintenu.

### C. Conséquence observée côté Claude
Boucle ~90 s : `POST /oauth/register` → `POST /oauth/token` → `POST /mcp/sse` initialize → **nouvelle session à chaque coup** (`session_id:"None"` entrant systématiquement). Aucun `tools/list` ni `tools/call` jamais déclenché. Le connecteur abandonne et redémarre à zéro.

### D. Bugs secondaires découverts

1. **Soft-auth sur `/mcp/*`** (gotcha déjà en mémoire `gotcha_gateway_soft_auth_mcp.md`) : un POST sans `Authorization` renvoie 200 + scope anon `stoa:read` au lieu de `401 WWW-Authenticate: Bearer resource_metadata=…`. Avec bearer invalide, le 401 est correct → preuve que le code `require_auth` existe mais n'est pas branché sur le chemin anonyme.
2. **CORS absent** : ingress `stoa-gateway` n'a aucune annotation `nginx.ingress.kubernetes.io/cors-*` (alors que `stoa-control-plane-api` en a). Pas bloquant pour claude.ai remote (backend Anthropic, UA `Claude-User`), mais cassera tout client MCP in-browser (Inspector local, Portal, etc.).
3. **OTLP saturé** : logs spam `BatchSpanProcessor.Flush.ExportError: sending queue is full`. Collector sous-dimensionné ou HS. Pollue le debug.

---

## 2. Fichiers à éditer (repérage)

Repo : `github.com/stoa-platform/stoa`, répertoire `stoa-gateway/`.

- `stoa-gateway/src/mcp/sse.rs`
  - `handle_sse_post` (l. ~158)
  - `handle_streamable_http_post` (l. ~393) — peut déjà contenir une logique à factoriser
  - `handle_sse_get` (l. ~412), `handle_sse_delete` (l. ~494)
  - `extract_bearer_token` (l. ~1131)
- `stoa-gateway/src/mcp/session.rs` (587 LOC) — gestion `mcp-session-id`
- `stoa-gateway/src/mcp/handlers.rs` (1598 LOC) — handlers par méthode JSON-RPC
- Tests existants dans `sse.rs` à partir de l. ~1162 (module `mod tests`)

Pour le chart :
- `charts/stoa-platform/templates/ingress.yaml` (ou sous-chart `stoa-gateway`)
- Miroir `stoa-infra/charts/` à synchroniser (règle CLAUDE.md #6)

---

## 3. Phases d'exécution

### Phase 1 — P0 Fix Accept / SSE (1 PR, ≤ 300 LOC)

**Branche** : `fix/cab-XXXX-gateway-mcp-sse-accept-negotiation` (créer ticket Linear avant, cf §6).

Tâches :
1. Parser `Accept` (utiliser `mime` crate ou parse simple) dans `handle_sse_post`.
2. Si `text/event-stream` acceptable :
   - Répondre avec `Content-Type: text/event-stream`, `Transfer-Encoding: chunked`.
   - Émettre la réponse JSON-RPC sous `event: message\ndata: <json>\n\n`.
   - Conserver l'écriture ouverte via `axum::response::sse::Sse` (déjà utilisé si `handle_sse_get` existe) ou stream manuel.
   - Garder le flux ouvert (keepalive ping toutes les 15 s) jusqu'à disconnect client ou `DELETE /mcp/sse`.
3. Si `application/json` uniquement : comportement actuel inchangé (back-compat).
4. Ne pas re-créer de session si `mcp-session-id` entrant est valide et présent → router vers la session existante. Si invalide → 404 `Mcp-Session-Not-Found`.
5. Tests unitaires à ajouter :
   - Accept matrix × method : `initialize`, `tools/list`, `tools/call` × Accept {json only, event-stream only, both, none}.
   - Session reuse : second POST avec `mcp-session-id` ne doit pas créer nouvelle session.
6. Vérifier que `handle_streamable_http_post` n'est pas un alias oublié — soit l'aligner soit le supprimer si mort.

**Contrainte** :
- Pas de `--no-verify`, pre-push green (lint-before-commit rule).
- Conventional commit `fix(gateway): honor Accept: text/event-stream on /mcp/sse (CAB-XXXX)`.
- Squash merge + delete branch.

**DoD Phase 1** :
- `cargo test -p stoa-gateway` vert.
- `cargo clippy --all-targets -- -D warnings` vert.
- Reproduction manuelle curl : Accept event-stream → réponse SSE, JSON only → JSON.
- Test Accept matrix : ≥ 8 cas verts.

### Phase 2 — P0 Validation canary puis prod

1. Tilt k3d local : re-tester `POST /mcp/sse` avec curl matrix + MCP Inspector (`npx @modelcontextprotocol/inspector`). Gotcha Tilt k3d en mémoire (`gotcha_tilt_local.md`) — lire avant.
2. Dev VPS (`dev-vps` 94.23.107.107 — Docker Compose, pas K8s) : déployer build.
3. Configurer un connecteur MCP claude.ai de test pointant sur l'URL dev (ex : `https://dev-mcp.gostoa.dev` si existe, sinon prod avec feature flag — à clarifier).
4. Observer les logs dev : séquence `DCR → token → initialize → tools/list → tools/call` sans boucle.
5. Bump version chart gateway (patch) + release PR automatique (release-please).
6. Post-merge : ArgoCD sync auto. Vérifier rollout (`kubectl -n stoa-system rollout status deploy/stoa-gateway --kubeconfig ~/.kube/config-stoa-ovh`).
7. Capture écran claude.ai OK + `kubectl logs` montrant `tools/list` → archivage `docs/audits/2026-04-17-mcp-claude-ai-connector/AUDIT-RESULTS.md`.

**DoD Phase 2** : claude.ai connecteur listé "Connected", tools apparaissent, appel d'outil réussit. Evidence archive remplie.

### Phase 3 — P1 Soft-auth close (PR séparée)

**Branche** : `fix/cab-YYYY-gateway-enforce-auth-mcp`

Tâches :
1. Identifier le code `require_auth` existant (déjà mentionné comme "code mort").
2. Brancher sur toutes les routes `/mcp/*` sauf `GET /mcp` (ping anon) si existant.
3. POST sans `Authorization` → `401` + `WWW-Authenticate: Bearer resource_metadata="/.well-known/oauth-protected-resource"`.
4. Tests contract : anonymous, invalid bearer, expired bearer, valid bearer → 401/401/401/200.
5. Supprimer le fallback `[stoa:read]` anonyme.

**DoD** : tous les tests contract verts, reproduction curl sans header Authorization renvoie 401 avec challenge.

### Phase 4 — P2 CORS ingress (PR séparée, dual-repo)

1. Ajouter annotations dans `charts/stoa-platform/templates/ingress.yaml` pour le gateway (ou sous-chart dédié) :
   ```
   nginx.ingress.kubernetes.io/enable-cors: "true"
   nginx.ingress.kubernetes.io/cors-allow-origin: "https://claude.ai, https://*.claude.ai, https://console.gostoa.dev, https://portal.gostoa.dev"
   nginx.ingress.kubernetes.io/cors-allow-methods: "GET, POST, OPTIONS, DELETE"
   nginx.ingress.kubernetes.io/cors-allow-headers: "Authorization, Content-Type, mcp-session-id, mcp-protocol-version, Accept"
   nginx.ingress.kubernetes.io/cors-expose-headers: "mcp-session-id"
   ```
2. Rendre configurables via `values.yaml` (`gateway.ingress.cors.allowedOrigins: []`).
3. Sync miroir `stoa-infra/charts/`.
4. Test post-deploy : `curl -X OPTIONS https://mcp.gostoa.dev/mcp/sse -H 'Origin: https://claude.ai' -H 'Access-Control-Request-Method: POST'` → 200 + headers CORS attendus.

### Phase 5 — P3 OTLP (ticket séparé, hors scope immédiat)

1. Vérifier santé `otel-collector` / tempo (ns `monitoring` ou `logging`).
2. Tuner `BatchSpanProcessor` : augmenter `max_queue_size`, réduire `scheduled_delay`, ou baisser sampling.
3. Ticket dédié, pas bloquant.

---

## 4. Commandes de référence

Toutes prod = `KUBECONFIG=~/.kube/config-stoa-ovh`.

```
# Pods gateway
kubectl -n stoa-system get pods -l app=stoa-gateway

# Logs en tail (filtrer bruit OTEL)
kubectl -n stoa-system logs -l app=stoa-gateway --tail=500 \
  | grep -v "BatchSpanProcessor\|opentelemetry\|acme-challenge"

# Access logs Claude-User
kubectl -n stoa-system logs -l app=stoa-gateway --tail=5000 \
  | grep -E "access_log" | grep -E "Claude-User|Claude/"

# Trace OAuth → initialize d'une session
kubectl -n stoa-system logs -l app=stoa-gateway --tail=10000 \
  | grep -E "oauth/register|oauth/token|/mcp/sse" | grep "access_log"

# Rollout
kubectl -n stoa-system rollout status deploy/stoa-gateway
```

Test externe :
```
curl -sS -D - -X POST https://mcp.gostoa.dev/mcp/sse \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <kc-token>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}'
```

Récup token Keycloak (user test) : via Portal OIDC session cookie, ou `stoactl auth login --oidc` si dispo, ou flow client_credentials avec un client admin de test.

---

## 5. Règles projet à respecter

- **CLAUDE.md** : 1 chose à la fois, test-first `fix()`, PR ≤ 300 LOC, `--squash`+`--delete-branch`, conventional commits, Ticket ID sur 1er commit, lint avant commit, pas de `--no-verify`.
- **Dual-repo** : chart gateway modifié doit être synchronisé `stoa/charts/` ↔ `stoa-infra/charts/`.
- **Evidence archive** obligatoire après test Playwright / validation claude.ai : `docs/audits/2026-04-17-mcp-claude-ai-connector/AUDIT-RESULTS.md` + captures.
- **Pas de reset password** Keycloak si token expiré — utiliser creds `.env`.
- **Pre-push hook** obligatoire.
- **Tests qui échouent AVANT le code** (test-first).
- Pas mocker la boundary sous test (pas de `AsyncMock` sur HTTP ; utiliser `httpx.MockTransport` ou un serveur réel).

---

## 6. Ticketing Linear (à faire AVANT de coder)

Team Linear STOA : `624a9948-a160-4e47-aba5-7f9404d23506`.

Créer 4 tickets :

| Ticket | Titre | Priorité | Pts | Phase |
|--------|-------|----------|-----|-------|
| CAB-NEW-A | fix(gateway): honor Accept: text/event-stream on /mcp/sse | P0 | 5 | 1+2 |
| CAB-NEW-B | fix(gateway): enforce 401 on unauthenticated /mcp/* (close soft-auth) | P1 | 3 | 3 |
| CAB-NEW-C | feat(chart): CORS annotations on stoa-gateway ingress | P2 | 2 | 4 |
| CAB-NEW-D | chore(gateway): fix OTLP batch processor saturation | P3 | 2 | 5 |

Impact Score probable ≥ HIGH (touche auth + prod client-facing) → vérifier si Council requis (seuil 16+). Utiliser `docs/scripts/build-context.sh --component stoa-gateway --ticket CAB-NEW-A` pour générer le context pack avant code.

---

## 7. Mémoires/Gotchas à lire AVANT de coder

Dans `/Users/torpedo/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/` :

- `gotcha_gateway_soft_auth_mcp.md` — bug soft-auth, directement en lien avec Phase 3.
- `gotcha_gateway_chart_baseDomain_hardcode.md` — chart gateway hardcode `baseDomain` sur `templates/deployment.yaml:62`. Pertinent pour Phase 4 (edits du chart).
- `gotcha_tilt_local.md` — k3d local HTTPS pour OIDC, Helm overridable.
- `feedback_evidence_archive.md` — archive obligatoire après test.
- `feedback_lint_before_commit.md` — lint avant `git add`.
- `feedback_linear_in_review.md` — "In Review" seulement si PR existe.

---

## 8. Pièges connus à éviter

- **Pas de ré-déclenchement de DCR** côté serveur : Claude.ai spamme `/oauth/register`. Ne pas confondre cause et symptôme.
- **mcp-session-id** : le header doit être à la fois renvoyé sur la réponse initialize ET accepté sur les requêtes suivantes. Ne pas oublier `Access-Control-Expose-Headers` si CORS activé (Phase 4).
- **Streamable HTTP spec 2025-03-26** : https://modelcontextprotocol.io/specification/2025-03-26/basic/transports — à relire, notamment section "Sending Messages to the Server".
- **Ne pas mélanger** avec la branche `feat/cab-2095-stoactl-api-tenant-scope` en cours — créer worktree dédié : `git worktree add .claude/worktrees/gateway-mcp-fix -b fix/cab-XXXX-gateway-mcp-sse-accept main`.
- **Tests gateway** : `cargo test --all-features` requiert cmake (cf MEMORY.md). Local : `cargo test -p stoa-gateway`.

---

## 9. Critère global de succès

Binaire, non négociable :

1. ✅ Sur claude.ai web, ajouter un connecteur MCP "STOA" pointant vers `https://mcp.gostoa.dev/mcp/sse`, login OAuth réussi.
2. ✅ Le connecteur liste les tools (`stoa_tenants`, `stoa_platform_health`, etc.) sans boucle DCR.
3. ✅ Invocation d'un tool (ex : `stoa_platform_health`) retourne une réponse utilisable dans une conversation claude.ai.
4. ✅ Logs gateway prod montrent la séquence complète : `initialize` (1×) → `tools/list` → `tools/call` → `notifications/*`.
5. ✅ Aucune régression sur `claude-code` CLI (`GET /mcp/sse` avec UA `claude-code/x.y.z` continue de fonctionner).

Si les 5 ne sont pas verts en prod, le handoff n'est pas clôturé.
