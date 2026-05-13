---
title: "Audit — Souscription UAC API + MCP Tools (code↔ADR, DORA/NIS2)"
date: 2026-05-11
author: Claude (audit pipeline 4-axes)
scope: control-plane-api/, stoa-gateway/, stoa-docs/architecture/adr/
verdict: NOGO (production blockers across 4 axes)
compliance_gates: 3/12 PASS · 5/12 PARTIAL · 4/12 FAIL
---

# Audit — Souscription UAC API + MCP Tools

## Executive summary (TL;DR)

L'audit cible 4 axes : (1) flow souscription Portal→Approval→Gateway, (2) registration/invocation MCP Tools, (3) audit log + traçabilité DORA/NIS2, (4) enforcement gateway Rust.

**Verdict global : NOGO pour passer un audit DORA/NIS2 demain.** Le système est largement fonctionnel pour le happy-path mais **fail-open** dans plusieurs branches critiques, **viole sa propre doctrine** (ADR-067 destructive→approval n'est pas appliquée à l'exécution), et **rompt la chaîne d'audit** entre Control Plane et Gateway. Deux ADRs structurants (067 doctrine UAC, 068 audit log actor/resource) sont **référencés mais n'existent pas** en `stoa-docs/`.

**4 patterns systémiques** émergent (cross-cutting) :

1. **Doctrine déclarée ≠ doctrine appliquée** — règle "destructive→approval" validée au parsing UAC mais ignorée par `mcp_tools_call` et par le flow de souscription.
2. **Fail-open** — gateway en mode permissif quand CP injoignable, quand policy file absent, classification VH "log-only", deprovision one-shot.
3. **Audit log troué** — `erase_user_pii()` fait des `UPDATE` sur `audit_events`, gateway émet vers `tracing` local (jamais vers CP), `suspend/reactivate` sans webhook.
4. **State machine ambiguë** — `status` et `provisioning_status` dédoublés, pas de `DEPROVISIONING` state, approval = jump direct sans état intermédiaire visible.

**Gates DORA/NIS2 (12 contrôles binaires)** : 3 PASS, 5 PARTIAL, 4 FAIL. Les 4 FAIL bloquent toute publication régulateur.

---

## 1. Matrice ADR ↔ Code (synthèse)

| ADR | Sujet | Existe | Code aligné | Note |
|-----|-------|--------|-------------|------|
| ADR-001 | API exposure strategy | **Non trouvé** | n/a | Subscription flow non documenté formellement |
| ADR-006 | Tool registry architecture | Oui | Partiel | Drift catalog GitHub vs DB CP-API (gotcha CAB-2135) |
| ADR-012 | MCP RBAC | Oui | Partiel | tenant_tool_permissions check OK ; manque scope check cross-tenant |
| ADR-021 | UAC-driven observability | Oui | Partiel | correlation_id existe mais pas systématique dans logs subscription |
| ADR-022 | UAC tenant architecture | Oui | Partiel | Pas de validation `request.tenant_id == api.owner.tenant_id` à la création |
| ADR-028/039 | mTLS + cert-bound tokens | Oui | Partiel | sender_constraint pas câblé dans chemin policy |
| ADR-044 | MCP OAuth gateway proxy | Oui | OK | |
| ADR-046 | MCP federation | Oui | Partiel | Identity propagation à confirmer côté tenant_mcp_servers |
| ADR-051 | Lazy MCP discovery | Oui | Partiel | TTL OK ; pas d'invalidation event sur publish contract |
| ADR-054 | RBAC taxonomy v2 | Oui | OK | |
| ADR-055 | Portal/Console governance | Oui | OK | |
| ADR-066 | UAC as executable contract | Oui | Partiel | Schemas stockés, **pas validés au runtime** côté gateway |
| **ADR-067** | UAC describes / MCP projects / Smoke proves | **MANQUANT** | Doctrine codée dans validator Python mais **non appliquée gateway** | Ligne canonique dans `.claude/docs/uac-llm-ready.md` ; jamais formalisée en ADR |
| **ADR-068** | Audit log actor/resource doctrine | **MANQUANT** | Partiellement implémenté | Référencée comme "used 2026-05-10" dans memory mais fichier ADR absent |

---

## 2. Findings par axe

### Axe A — Subscription flow

Architecture observée : `SubscriptionCreate → PENDING → (auto/manual approval) → ACTIVE` avec `provisioning_status` parallèle (`NONE → PROVISIONING → READY → FAILED`). Propagation gateway = `asyncio.create_task()` fire-and-forget via Adapter Registry (webMethods par défaut). Webhooks Kafka émis en best-effort.

**Findings (severity-ranked)** :

| ID | Sev | Finding | Preuve |
|----|-----|---------|--------|
| SUB-1 | P0 | **Deprovision one-shot, pas de retry** : revocation côté CP mais gateway route reste active si gateway down au moment du revoke | `services/provisioning_service.py:341-380` (pas de retry loop comme `_provision_with_session`) |
| SUB-2 | P0 | **TTL extension: flush sans commit** : `await db.flush()` au lieu de `commit()`, transaction réversible si étape suivante échoue | `routers/subscriptions.py:562` |
| SUB-3 | P1 | **Suspend/Reactivate sans webhook** : aucun audit trail externe pour ces transitions ; documenté comme gap intentionnel dans le test `test_suspend_does_not_emit_webhook_L8` → **CLOSED** PR #2784, regression test `tests/test_regression_cab_2225_sub_3_suspend_reactivate_webhook.py`. | `routers/subscriptions.py:777-846` |
| SUB-4 | P1 | **Provision timeout 10s hardcodé, sans correlation_id dans log warning** : timeouts en prod intraçables | `routers/subscriptions.py:209-216` |
| SUB-5 | P1 | **`auto_approve_roles` jamais testé end-to-end** : feature documentée sur Plan, aucun test e2e ne prouve qu'un viewer auto-approuve sans manual gate | `routers/subscriptions.py:182` |
| SUB-6 | P2 | **Cross-tenant subscription non rejetée à la création** : pas de check `api.owner.tenant_id == request.tenant_id` | `routers/subscriptions.py:147` |
| SUB-7 | P2 | **Provisioning race** : deux `provision_on_approval` concurrents écrivent `provisioning_status=PROVISIONING` sans garde idempotente | `services/provisioning_service.py:135-137` |

**State machine actuelle vs idéale** :

```
ACTUELLE (status + provisioning_status dédoublés) :
CREATE → PENDING → ACTIVE ──┬─→ SUSPENDED ⇄ ACTIVE
                            └─→ REVOKED  (deprovision async, peut échouer silencieusement)

provisioning_status hors-bande : NONE → PROVISIONING → READY/FAILED
  (un user voit status=ACTIVE alors que provisioning_status=PROVISIONING → API call 404 gateway)

IDÉALE (unifiée, observable) :
CREATE → PENDING (approval) → APPROVED → PROVISIONING → READY → ACTIVE
                  └→ REJECTED                                    ⇄ SUSPENDED
                                                                  └→ REVOKING → REVOKED
```

---

### Axe B — MCP Tools (UAC → MCP projection + invocation)

Architecture observée : `UacToolGenerator` (Python) produit `McpGeneratedTool` à partir du contrat UAC (nom stable `{tenant}:{contract}:{operation}`). Gateway Rust refresh dynamique via cache stale-while-revalidate. Validator UAC applique la règle "destructive→requires_human_approval" **au parsing du contrat**.

**Doctrine ADR-067 — état par pilier** :
- **UAC describes** : OK — schemas Pydantic `UacEndpointLlmSpec` complets.
- **MCP projects** : **PARTIEL** — la projection existe mais **les métadonnées LLM ne sont pas transportées** dans la réponse `tools/list` du gateway (description-only).
- **Smoke proves** : **NON** — aucun smoke ne vérifie que `tools/list` retourne le tool_name attendu, ni que annotations matchent `side_effects`.

**Findings** :

| ID | Sev | Finding | Preuve |
|----|-----|---------|--------|
| MCP-1 | P0 | **`requires_human_approval=true` ignoré à l'exécution** : 5 phases (auth/rate/OPA/exec/meter) ne lisent jamais le flag — doctrine ADR-067 fictive en runtime | `stoa-gateway/src/mcp/handlers.rs:354-390` |
| MCP-2 | P0 | **Métadonnées LLM non projetées dans `tools/list`** : `side_effects`, `safe_for_agents`, `requires_human_approval` enfouis dans texte description, parsables uniquement par regex côté client | `stoa-gateway/src/mcp/tools/mod.rs:140-152` |
| MCP-3 | P1 | **Annotations décorrélées du contrat** : `destructive_hint` dérivé de `UacAction` enum (fallback `operation_id`), pas de `side_effects` JSON du contrat | `stoa-gateway/src/mcp/tools/api_bridge.rs:155-219` |
| MCP-4 | P1 | **Pas d'invalidation event sur publish UAC** : gateway sert ancienne version jusqu'à expiration TTL (minutes-heures) | `services/uac_tool_generator.py:74-88` (invalidate_tools sans webhook) |
| MCP-5 | P2 | **`tools/list` POST vs GET incohérent** : `lib.rs:141` route en POST, `access_log.rs:107` test en GET, proxy CP-API utilise chemin `/v1/mcp/tools` non aligné | mismatch routes Rust |
| MCP-6 | P2 | **Tenant scope check absent dans tools/call** : pas de vérification `tool.tenant_id == auth.tenant_id` après lookup — collision cross-tenant possible si tool_name forgé | `stoa-gateway/src/mcp/handlers.rs:380+` |

---

### Axe C — Audit log + traçabilité (DORA/NIS2)

Architecture observée : dual-stack — table PostgreSQL `audit_events` (déclarée immutable, append-only) + indexation OpenSearch asynchrone. Middlewares `HTTPLoggingMiddleware` + `AuditMiddleware` (dual-write). Gateway Rust émet uniquement via `tracing::info!` (logs locaux).

**Matrice 12 contrôles DORA/NIS2 (binaire)** :

| # | Contrôle | Statut | Preuve | Article |
|---|----------|--------|--------|---------|
| 1 | Audit existe sur mutations critiques | **PASS** | `subscriptions.py:88,673,730` + middleware POST/PUT/PATCH | DORA Art.5 |
| 2 | Actor identifié (user + tenant + session + IP) | **PARTIAL** | actor/tenant/IP OK ; **session_id absent** du modèle DB (capturé en OpenSearch seulement) | DORA Art.8, NIS2 Art.21 |
| 3 | Resource identifié (type+id) | **PASS** | `AuditEvent.resource_type` / `resource_id` | DORA Art.5 |
| 4 | Timestamp ISO8601 UTC | **PASS** | `created_at DateTime(timezone=True)` UTC | DORA Art.8 |
| 5 | **Immutabilité DB** | **FAIL** | `audit_service.erase_user_pii():420-461` exécute `UPDATE audit_events` ; pas de trigger PG bloquant UPDATE/DELETE ; commentaire "immutable" contradit le code | DORA Art.11 |
| 6 | Intégrité (hash chain / WORM) | **FAIL** | Aucune chaîne de hash, pas d'export signé, pas de WORM bucket | DORA Art.8, NIS2 Art.21 |
| 7 | Retention 5 ans codifiée | **PARTIAL** | `purge_before()` existe mais **jamais appelée** ; aucune `AUDIT_RETENTION_DAYS` consommée ; aucun CronJob | DORA Art.11 |
| 8 | Search & export SOC | **PASS** | `list_events()` filtres complets, export CSV/JSON | DORA Art.17 |
| 9 | PII redaction (pas de pwd/token) | **PASS** | Champ `details` JSONB annoté "sanitized" | GDPR + DORA Art.8 |
| 10 | **Gateway → CP audit chain** | **FAIL** | `stoa-gateway` émet uniquement `tracing::info!` — aucun endpoint `/internal/audit/emit` côté CP, aucun client gateway | DORA Art.5 |
| 11 | Approval workflow tracé | **PARTIAL** | actor_id du approver OK, **pas de `approval_justification`**, pas de diff before/after structuré | DORA Art.9 |
| 12 | Incident response (correlation_id end-to-end) | **PARTIAL** | correlation_id présent en DB, aucune chaîne propagée côté gateway, pas de `incident_id` | DORA Art.17 |

**Score : 3 PASS / 5 PARTIAL / 4 FAIL.**

**Conflit GDPR vs DORA non résolu** : `erase_user_pii()` détruit le proof trail pour satisfaire GDPR Art.17, ce qui viole l'immutabilité requise par DORA Art.11. Aucune ADR ne tranche (séparer table `pseudonymized_audit_erasures`, ou pseudonymisation in-place avec preuve hash de l'original).

---

### Axe D — Gateway Rust enforcement (stoa-gateway)

Architecture observée : JWT validation → expansion scopes (ADR-012) → OPA policy → tool exec → metering. Pas de polling subscribe/stream vers CP — config statique YAML + registration heartbeat.

**Posture fail-closed : FAIL.** 4 chemins permissifs documentés :

| ID | Sev | Finding | Preuve |
|----|-----|---------|--------|
| GW-1 | P0 | **CP injoignable → default-allow tool permissions** | `src/control_plane/tool_permissions.rs:69-96` (ligne 92: `perms.get(tool_name).unwrap_or(&true)`, log warn et continue) |
| GW-2 | P0 | **Policy file absent → permissive fallback** | `src/state.rs:176-189` crée engine `enabled=false` ; readiness probe ne reflète pas cet état dégradé |
| GW-3 | P0 | **Destructive ops gating absent** : `destructive_hint=true` n'entraîne aucun check approval token ou 4-eyes | `src/mcp/tools/mod.rs:41-43` + `handlers.rs:354-390` |
| GW-4 | P1 | **Classification VH soft-mode** : routes "Very High" loguent la décision mais **ne dénient pas** ("log only, do NOT deny") | `src/proxy/dynamic.rs:410-422` + `src/state.rs:285` |
| GW-5 | P1 | **Schema validation runtime absente** : tool arguments passés direct sans valider contre `inputSchema` UAC ; idem `outputSchema` | `src/mcp/handlers.rs`, `src/mcp/tools/mod.rs:130-155` |
| GW-6 | P1 | **Audit emit absent du chemin deny** : aucun event structuré CP/Kafka sur rate-limit/policy/RBAC deny — logs unstructured seulement | `src/metering/`, `src/events/` (gap) |
| GW-7 | P1 | **Revocation latency indéfinie** : cache CP-permissions 60s TTL ; entre revoke côté CP et prochain poll → calls allowed | `tool_permissions.rs:52` |
| GW-8 | P2 | **Rate-limit keying tenant-only** : multiple subscriptions du même tenant partagent un même bucket → bypass quota cross-subscription | `src/quota/middleware.rs:64-80` |
| GW-9 | P2 | **SIGHUP hot reload async non bloquant** : clients in-flight voient policies mixtes (stale + new) | `src/main.rs:44-74` |

---

## 3. Patterns systémiques (cross-cutting)

### 3.1 — Doctrine sans enforcement runtime

La règle "destructive→approval" (ADR-067 informelle) est appliquée à **3 endroits différents avec 3 sémantiques différentes** :

| Couche | Comportement | File |
|--------|-------------|------|
| Validator UAC (parsing) | Reject le contrat si malformé | `uac_validator.py:175-178` |
| Tool generator (DB) | Enrichit la description texte avec marker | `uac_tool_generator.py:111-127` |
| Gateway runtime (call) | **Ignore** le flag | `mcp/handlers.rs:354-390` |

**Conséquence** : un IA agent qui appelle un tool destructive recevra une description disant "DESTRUCTIVE — requires approval" puis l'exécution se fait quand même. L'audit log ne porte aucune trace d'un éventuel approval. → **régulateur conclut "feature absente"**.

### 3.2 — Fail-open au lieu de fail-closed

5 chemins :
- CP injoignable → tool permissions = allow-all (GW-1)
- Policy file absent → policy = allow-all (GW-2)
- Classification VH → log-only (GW-4)
- Deprovision échoué → gateway route reste active (SUB-1)
- Webhook Kafka échoué → flow continue (SUB-3 partial)

**Conséquence DORA Art.9 (incident detection)** : aucun de ces fallback ne génère d'alerte. Métrique manquante.

### 3.3 — Chaîne d'audit rompue Gateway↔CP

Gateway = source des décisions allow/deny chaudes. CP = source des décisions de souscription/approval. **Aucun pont** : pas d'endpoint `/v1/internal/audit/emit` côté CP, pas de client gateway. → multi-DC / forensic = impossible.

### 3.4 — State machine inconsistante

`status` + `provisioning_status` dédoublés ; pas de state `DEPROVISIONING` ; revoke écrit `status=REVOKED` instantanément même si gateway down. → vue produit (UI) trompeuse.

---

## 4. DORA/NIS2 — Gates binaires (synthèse)

| # | Gate (capacité bloquante) | Statut | Owner Fix |
|---|---------------------------|--------|-----------|
| G1 | Audit log immutable (DB trigger / WORM) | **FAIL** | cp-api (migration alembic + trigger PG) |
| G2 | Gateway → CP audit chain | **FAIL** | cp-api (endpoint internal) + stoa-gateway (client) |
| G3 | Fail-closed sur CP injoignable | **FAIL** | stoa-gateway (default-deny + readiness gate) |
| G4 | Destructive→approval enforcement runtime | **FAIL** | stoa-gateway (handlers.rs phase pre-exec) |
| G5 | Retention 5 ans schedulée | **PARTIAL** | cp-api (Helm CronJob purge_before) |
| G6 | Schema validation runtime UAC | **PARTIAL** | stoa-gateway (input/output validate) |
| G7 | Revocation latency < 5 min | **PARTIAL** | stoa-gateway (subscribe/stream remplace poll) |
| G8 | Session tracking actor (DB column) | **PARTIAL** | cp-api (migration alembic + middleware) |
| G9 | State machine subscription unifiée | **PARTIAL** | cp-api (refactor + migration) |
| G10 | Approval justification + diff before/after | **PARTIAL** | cp-api (model + UI) |
| G11 | Actor identification (user/tenant/IP) | **PASS** | — |
| G12 | Resource taxonomy (type:id) | **PASS** | — |

**Verdict binaire : 4 FAIL bloquent une publication régulateur.** Les 6 PARTIAL doivent passer avant audit externe.

---

## 5. Plan rewrite/fix — priorisé

### Phase 0 — Blockers DORA/NIS2 (P0, semaine 1-2)

**P0-1. Gateway fail-closed sur CP injoignable**
- Fichier : `stoa-gateway/src/control_plane/tool_permissions.rs:88-96`
- Fix : remplacer `unwrap_or(&true)` par fail-closed + circuit breaker. Readiness probe (`handlers/admin/health.rs:31`) reflète l'état CP.
- Test régression : `test_tool_permissions_cp_unreachable_denies.rs`.

**P0-2. Gateway policy engine fail-closed sur load failure**
- Fichier : `stoa-gateway/src/state.rs:176-189`
- Fix : si policy file absent/corrompu → panic au boot (pas de fallback `enabled=false`). Readiness FAIL.

**P0-3. Destructive→approval enforcement runtime**
- Fichier : `stoa-gateway/src/mcp/handlers.rs:354-390` + nouveau champ `McpGeneratedTool.requires_approval`
- Fix : phase 4bis (entre OPA et exec) — si `requires_approval=true` && pas de header `X-Approval-Token` valide → 403. Approval token = JWT signé par CP avec claim `tool_call_id`.

**P0-4. Audit log immutabilité DB**
- Fichier : nouvelle migration alembic + `audit_service.erase_user_pii`
- Fix : trigger PG `BEFORE UPDATE OR DELETE ON audit_events RAISE EXCEPTION`. Réécrire `erase_user_pii` pour pseudonymiser dans table séparée `pseudonymized_audit_erasures` (préserve la chaîne).

**P0-5. Deprovision retry loop**
- Fichier : `control-plane-api/src/services/provisioning_service.py` (analogue de `_provision_with_session`)
- Fix : 3 retries exponentiels + état persistant `DEPROVISIONING` ; alerte ops si épuisé.

**P0-6. Subscription TTL extension commit**
- Fichier : `routers/subscriptions.py:562` — `flush()` → `commit()`.

### Phase 1 — Chaîne d'audit + observabilité (P1, semaine 3-4)

- **P1-1. Endpoint `/v1/internal/audit/emit`** côté CP-API + client Rust gateway. Buffer + retry async. Signature HMAC inter-service.
- **P1-2. Métadonnées LLM dans `tools/list`** (Rust `ToolDefinition` + `side_effects`/`requires_human_approval`/`safe_for_agents` typés).
- **P1-3. Annotations `destructive_hint` dérivées du contrat UAC** (pas de `Action::from_operation_id` fallback).
- **P1-4. Webhook Kafka invalidation sur publish UAC** → gateway refresh forcé du tenant.
- **P1-5. CronJob Helm rétention** (`purge_before` daily, 5 ans par défaut configurable).
- **P1-6. Schema validation runtime** côté gateway (input + output).
- **P1-7. Webhooks suspend/reactivate** dans `routers/subscriptions.py:777-846`.
- **P1-8. Classification VH passe en mode block** (`state.rs:285` flip + tests).

### Phase 2 — Workflow approval auditable (P1/P2, semaine 5-6)

- **P2-1. State machine subscription unifiée** (`status` absorbe `provisioning_status`, ajout `DEPROVISIONING`/`REVOKING`). Migration + UI.
- **P2-2. Approval justification + diff** (champ `approval_justification` + diff JSONB before/after policy).
- **P2-3. Session tracking actor** (colonne `session_id` audit_events + hydratation middleware).
- **P2-4. Subscribe/stream gateway↔CP** (remplace poll 60s ; latence révocation < 5 min garantie).
- **P2-5. Hash chain ou export WORM signé** (intégrité audit).
- **P2-6. Approval token JWT signé** (lié à `tool_call_id`, TTL court, single-use).

### Phase 3 — Hygiène ADR (parallèle, semaine 1-6)

- **ADR-001 (API exposure strategy)** — formaliser le flow producer→subscription→consumer.
- **ADR-067 (UAC describes / MCP projects / Smoke proves)** — extraire `.claude/docs/uac-llm-ready.md` vers `stoa-docs/docs/architecture/adr/adr-067-*.md`.
- **ADR-068 (audit log actor/resource doctrine)** — formaliser (référencée memory mais inexistante).
- **ADR-069 (GDPR ↔ DORA audit reconciliation)** — trancher pseudonymisation vs delete vs archive séparée.
- **ADR-070 (gateway fail-closed posture)** — codifier defaults + readiness gates.

---

## 6. Workflow validation auditable (cible)

Pour passer un audit DORA/NIS2, le workflow cible de souscription doit garantir :

```
PORTAL (consumer tenant-admin)              CP-API                    GATEWAY
       │ POST /subscriptions                   │                          │
       │ (api_id, plan_id, justification)      │                          │
       ├──────────────────────────────────────►│                          │
       │                                       ├─ audit: SUBSCRIPTION_REQUESTED (actor, tenant, resource, session, justification, hash_prev)
       │                                       │                          │
       │                            [check api.owner.tenant_id ≠ caller]
       │                            [PENDING + approval task]             │
       │                            ┌──────────┘                          │
       │                            ▼                                     │
       │                  CONSOLE (producer tenant-admin)
       │                            │ POST /approve { justification, diff }
       │                            ├─ audit: SUBSCRIPTION_APPROVED
       │                            │                                     │
       │                            │ if api.has_destructive_endpoints:
       │                            │   require enhanced_approval (4-eyes)│
       │                            │                                     │
       │                            ▼                                     │
       │                    PROVISIONING ──── stream/subscribe ──────────►│
       │                            │                          [gateway pull policy, fail-closed]
       │                            │                          ┌──────────┤
       │                            │                          │          │
       │                            ◄─── ack(policy_version) ──┤          │
       │                            ▼                          ▼          │
       │                          READY → ACTIVE        [emit audit GW]   │
       │                            │                          │          │
       │                            ├─ audit: SUBSCRIPTION_READY (with policy hash)
       │                            │                                     │
       ◄────────────────────────────┤                                     │
       │                                                                  │
       │ tools/call (destructive)                                         │
       ├──────────────────────────────────────────────────────────────────►│
       │                                       │     [phase: requires_approval check]
       │                                       │     [require X-Approval-Token JWT]
       │                                       │     [emit audit GW→CP via /internal/audit/emit]
       │                                       │                          │
       │                            ◄──────────────────────────────────────┤
       │                            │ audit: TOOL_CALLED (allow/deny + approval_id)
       ◄────────────────────────────┤                                     │

REVOCATION :
       │ POST /subscriptions/{id}/revoke
       ├──────────────────────────────────────►│                          │
       │                            REVOKING (état persistant)            │
       │                            ├─ stream invalidation ──────────────►│
       │                            │                          [drain in-flight, deny new]
       │                            │                          ├─ ack    │
       │                            ◄──────────────────────────┤          │
       │                          REVOKED                                 │
```

**Propriétés à prouver par smoke test** :

1. Un revoke côté CP → gateway refuse en < 5 min (mesuré). Aucun fallback "cached allow".
2. Un destructive call sans `X-Approval-Token` → 403 + audit log.
3. CP down → gateway readiness FAIL + tool calls refusés.
4. `UPDATE audit_events` → exception PG.
5. `erase_user_pii` → audit_events intacts, copie pseudonymisée dans `pseudonymized_audit_erasures`.
6. `tools/list` réponse contient `side_effects`, `requires_human_approval` typés.
7. Suspend/reactivate → audit log + Kafka event.

---

## 7. Effort estimé (calibrage)

| Phase | Scope | LOC estimés | Tests | Effort dev |
|-------|-------|-------------|-------|-----------|
| P0 (blockers DORA/NIS2) | 6 fix isolés | ~800 | ~12 tests régression | 2 sem |
| P1 (chaîne audit + obs) | endpoint inter-service + 7 fix | ~2500 | ~25 tests + smoke gateway↔CP | 3 sem |
| P2 (workflow approval + state) | refactor state machine + UI | ~3500 | ~30 tests + e2e BDD | 4 sem |
| Phase 3 (ADRs) | 5 ADRs | n/a | n/a | parallèle, 0.5 sem total |
| **TOTAL** | | **~6800 LOC** | **~67 tests** | **9 sem** + parallèle |

**Decision Gate recommandé** : ce plan touche audit log, gateway enforcement, et state machine subscription → impact business direct (compliance) ET irréversible (migration DB) → **Decision Gate obligatoire avec challenger externe** (cf. memory `feedback_doctrine_routes_through_doctrine`).

---

## 8. Annexe — Trouvailles "doctrine routes through doctrine"

Pendant l'audit, 2 méta-trouvailles dépassent le scope tech :

**M1.** ADR-067 et ADR-068 sont cités dans CLAUDE.md et `memory.md` comme références doctrinales **mais n'existent pas** dans `stoa-docs/docs/architecture/adr/`. → la doctrine vit dans des fichiers `.claude/docs/` non versionnés en source-of-truth régulateur.

**M2.** Le `feedback_doctrine_routes_through_doctrine.md` (memory) stipule que les propositions de gouvernance doivent passer par plan-validation + Decision Gate **elles-mêmes**. Cet audit déclenche au moins 5 ADRs nouvelles ou formalisées → **cet audit doit lui-même routes through Decision Gate** avant exécution.

**Action recommandée** : créer `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md` avec `validation_status: draft`, et `docs/decisions/2026-05-11-uac-subscription-mcp-corrective.md` pour verdict challenger externe (GPT ou équivalent) **avant** toute écriture P0.

---

*Fin d'audit. Sources : 4 investigations parallèles (subscription, MCP, audit, gateway), 14 ADRs lus, ~80 fichiers code croisés, preuves file:line à chaque finding.*
