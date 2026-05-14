---
title: "Plan correctif — Souscription UAC API + MCP Tools"
date: 2026-05-11
updated_at: 2026-05-13
source_audit: "docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md"
validation_status: validated
validated_at: "2026-05-13"
validated_by: "operator (solo project mode)"
validated_for_code_execution: true
conditions_pending: false
decision_record: "docs/decisions/2026-05-11-uac-subscription-mcp-corrective.md"
decision_verdict: "GO_WITH_CONDITIONS"
operator_approvals_record: "docs/decisions/2026-05-13-cab-2225-2229-operator-approvals.md"
last_challenger_verdict: "GO_WITH_CONDITIONS"
challenged_at: "2026-05-13"
challenger: "GPT-5.5 Pro — external non-Claude challenger"
decision_gate: closed
decision_gate_closed_at: "2026-05-13"
implementation_pending:
  - "PR #2781 Vault wrap on _wrap_pseudonymization_key (CAB-2226 condition)"
  - "P0-MCP-1 approval-token runtime (gated on PR #2781 + #2780 lock-step deploy)"
  - "P0-GW-1 / P0-GW-2 gateway fail-closed runtime (CAB-2227)"
  - "P0-AUD-2 minimal Gateway↔CP audit emit (in ADR-070 §4.6)"
scope:
  - control-plane-api/
  - stoa-gateway/
  - stoa-docs/docs/architecture/adr/
regulatory_context:
  - DORA
  - NIS2
verdict_from_audit: "NOGO"
target_outcome: "Regulatory-ready execution path for subscription, MCP tool invocation, gateway enforcement, and audit trail"
project_mode: solo
owners:
  accountable: "operator (founder, acting as product/security/privacy/business owner)"
  cp_api: "operator"
  gateway: "operator"
  docs_adr: "operator"
  security: "operator (no separate Security/DPO/Legal/Business role exists at this stage)"
  external_challenger: "GPT-5.5 Pro (external non-Claude challenger, 2026-05-13)"
---

> **2026-05-13 — Operator validation closed (CAB-2229).**
> Status: `challenged → validated`. Operator approvals on CAB-2225..2229 recorded in `docs/decisions/2026-05-13-cab-2225-2229-operator-approvals.md`. The 7 challenger conditions (C1-C7) are integrated below in §1.4. Code execution authorised within the accepted ADR scope.
>
> **Refused at this stage** (in spite of plan validation):
> - PR #2781 merge before Vault wrap lands on `_wrap_pseudonymization_key` (CAB-2226 binding condition).
> - PR #2780 merge before PR #2781 deploys to a given environment (lock-step ordering codified in `control-plane-api/alembic/versions/107_README.md`).
> - Any future move to raw storage for `pseudonymization_key` without a NEW ADR explicitly narrowing the trust boundary.
> - Multi-role sign-off framing on new artefacts — solo project mode applies (per `feedback_solo_project_mode_signoffs`).
>
> **Phase 0 rule preserved (challenger §5)**: Phase 0 closes local P0 blockers only if P0-AUD-2 minimal Gateway↔CP audit chain is included. ADR-070 §4.6 codifies this; the chain itself is part of PR #2781 scope.
>
> **Historical (pre-validation) note** — the doctrine `challenged` state above became `validated` via operator decision on 2026-05-13. The "Refused now" list from the prior challenged-state has been folded into the live conditions above; the original wording is preserved in git history via this section's pre-validation revision.

# Plan correctif — Souscription UAC API + MCP Tools

## 0. Résumé exécutable

L’audit du 2026-05-11 conclut à un **NOGO DORA/NIS2** sur la souscription UAC API + MCP Tools, avec **4 blockers P0** et un score de gates de conformité de **3 PASS / 5 PARTIAL / 4 FAIL**.

Ce plan est volontairement en `validation_status: draft`.

**Règle de gouvernance : aucune écriture P0 ne doit démarrer avant Decision Gate.**  
Sont inclus dans “écriture P0” : changement gateway fail-closed, migration DB audit, trigger PostgreSQL, réécriture `erase_user_pii`, enforcement `requires_human_approval`, endpoint inter-service audit, refactor de state machine, et tout changement de comportement irréversible.

Le plan cible une correction en **9 semaines**, structurée ainsi :

| Phase | Fenêtre | Objectif | Sortie attendue |
|---|---:|---|---|
| Gate 0 | Avant semaine 1 | Valider le plan avec challenger externe | Decision record `GO / GO_WITH_CONDITIONS / NOGO` |
| Phase 0 | Semaines 1-2 | Fermer les blockers P0 | 4 FAIL → 0 FAIL sur gates bloquants |
| Phase 1 | Semaines 3-5 | Restaurer chaîne audit + observabilité + runtime validation | Audit Gateway↔CP opérationnel, metadata MCP typées |
| Phase 2 | Semaines 6-9 | Workflow approval auditable + state machine unifiée | Souscription et révocation prouvables bout-en-bout |
| ADRs | En parallèle | Versionner la doctrine absente | ADR-067, 068, 069, 070, 071 publiées (ADR-001 reste predecessor accepté, non amendé) |

---

## 1. Decision Gate obligatoire

### 1.1 Pourquoi ce gate est bloquant

Ce plan touche trois zones à impact élevé :

1. **Audit log** : immutabilité, trigger PostgreSQL, pseudonymisation, retention.
2. **Gateway enforcement** : fail-closed, policy fallback, approval runtime, refus en cas de CP injoignable.
3. **State machine de souscription** : changements visibles produit, migrations, révocation et provisioning.

Ces zones ont un impact business direct et peuvent être irréversibles après migration. Le Decision Gate doit donc précéder les PRs P0.

### 1.2 Inputs requis pour le gate

Le gate doit recevoir un dossier minimal :

| Artefact | Statut requis |
|---|---|
| Audit source `AUDIT-RESULTS.md` | Disponible |
| Présent plan correctif | `draft` |
| Cartographie des P0 | Incluse section 3 |
| Stratégie migration audit log | Incluse section 5.4 |
| Stratégie fail-closed gateway | Incluse section 5.1 |
| Stratégie approval runtime | Incluse section 5.3 |
| Liste ADRs à formaliser | Incluse section 8 |
| Plan de tests/smoke | Inclus section 7 |
| Registre risques | Inclus section 9 |

### 1.3 Questions que le challenger externe doit trancher

Le challenger externe doit répondre explicitement à ces questions :

1. Le passage fail-closed est-il acceptable business sans mode dégradé “read-only” ?
2. Peut-on autoriser un cache de permissions gateway pendant une indisponibilité CP, ou faut-il refuser tout appel dès que le cache expire ?
3. Le modèle d’approval token JWT single-use est-il suffisant pour prouver le 4-eyes sur opérations destructives ?
4. La pseudonymisation hors-table `audit_events` résout-elle correctement le conflit GDPR Art.17 vs DORA Art.11 ?
5. Le trigger PostgreSQL d’immutabilité doit-il bloquer toutes les mises à jour, y compris les migrations correctives futures ?
6. La state machine unifiée proposée couvre-t-elle les états “partial provisioning” et “revocation failed” ?
7. Le plan 9 semaines est-il réaliste au regard des migrations DB, gateway Rust, CP Python, tests e2e et ADRs ?

### 1.4 Décisions possibles

| Verdict | Signification | Effet |
|---|---|---|
| `GO` | Plan accepté tel quel | Phase 0 peut démarrer |
| `GO_WITH_CONDITIONS` | Plan accepté avec réserves écrites | Phase 0 démarre uniquement sur les items non contestés |
| `NOGO` | Plan rejeté ou incomplet | Aucune écriture P0 ; retour en design |
| `SPLIT_GATE` | Certains P0 validés, d’autres non | PRs autorisées uniquement pour le périmètre explicitement validé |

### 1.5 No-go criteria du gate

Le gate doit refuser le démarrage si au moins une condition est vraie :

- Le propriétaire business refuse le fail-closed sans alternative documentée.
- L’équipe sécurité refuse le design de token d’approbation.
- La migration audit log ne définit pas précisément ce que devient `erase_user_pii`.
- Le plan de rollback des migrations DB est absent.
- Les ADR-067 et ADR-068 restent non versionnées.
- Les tests de preuve DORA/NIS2 ne sont pas identifiés avant implémentation.

### 1.6 Intégration des conditions C1-C7 (CAB-2229, opérateur 2026-05-13)

Le gate est fermé : opérateur GO_WITH_CONDITIONS, validation_status flippé à `validated`. Les 7 conditions du challenger sont addressées comme suit. Sources canoniques : `docs/decisions/2026-05-11-uac-subscription-mcp-corrective.md` (challenger verdict) + `docs/decisions/2026-05-13-cab-2225-2229-operator-approvals.md` (operator approvals).

| # | Condition | Statut | Référence canonique |
|---|-----------|--------|---------------------|
| C1 | Split Phase 0 / NOGO régulateur — Option A (Phase 0 minimal audit chain) ou SPLIT_GATE explicite | **CLOSED — Option A** | ADR-070 §4.6 codifie la chain minimum Phase 0 (denies + approval-gated, durable spool). Operator approval CAB-2227 confirme C1 Option A. |
| C2 | Sign-off business du fail-closed | **CLOSED — operator** | Operator approval CAB-2227 enregistré : `validated_for_code_execution: true` côté opérateur, SLA impact accepté. Frontmatter §C2 conditions intégrées dans ADR-070 §4.1. |
| C3 | Cache permissions = artefact signé non extensible | **CLOSED** | ADR-070 §4.2 codifie le `policy_cache_artefact` (policy_version, issued_at, expires_at ≤ 60 min, signature, deny_default). Operator parameters : TTL = 60 min, jamais extensible localement. |
| C4 | Approval token avec intent binding + preuve 4-eyes | **CLOSED** | ADR-067 §4.4 codifie les 6 invariants approval token (jti single-use atomic, arguments_hash, policy_version, contract_version, requester/approver séparés, audit issued/used/rejected). Operator approval CAB-2225 confirme conditions binding. |
| C5 | Audit immutability : trigger strict + procédure migration séparée | **CLOSED** | ADR-068 §4.4 (trigger + 3 exceptions break-glass), ADR-069 §4.2 (pseudo aux table). Operator approval CAB-2226 : key disposition = retrievable-with-dual-control ; **Vault wrap mandatory** sur PR #2781 (`implementation_pending`). |
| C6 | State machine partial provisioning + failure states | **CLOSED** | ADR-071 §4.1 codifie `PARTIALLY_PROVISIONED`, `PROVISIONING_FAILED`, `DEPROVISIONING_FAILED`. Operator approval CAB-2228 : visibility consumer-visible avec target breakdown, 4-eyes strict 2 tenant-admins, time budget 15 min. PR #2782 (DEPROVISIONING_FAILED) + PR #2784 (suspend/reactivate webhooks) déjà mergées. |
| C7 | Planning 9 semaines conditionnel staffing parallèle | **CLOSED — solo mode** | Solo project mode (`feedback_solo_project_mode_signoffs`) : l'opérateur s'engage personnellement sur le timeline. Si la capacité solo s'avère insuffisante en cours d'exécution, le plan rebase à 12-14 semaines sans drame. Aucun staffing tiers requis. |

**Implications sur les PRs en cours** (cf. `implementation_pending` du frontmatter) :

- **PR #2781** (Codex iter2 — code rewrite DRAFT) : reste DRAFT jusqu'au commit Vault wrap iter3 (CAB-2226 condition). Quand Vault wrap landed + review clean → Ready-for-Review.
- **PR #2780** (alembic 107 DRAFT) : reste DRAFT, lock-step ordering codifié dans `107_README.md`. Merge UNIQUEMENT après que PR #2781 est mergée ET déployée sur l'environnement cible.
- **P0-MCP-1, P0-GW-1/2, P0-AUD-2** : maintenant autorisés (`validated_for_code_execution: true`). Prompts Codex à venir par item.

**Anti-pattern rappel** : aucune approbation ne doit être enregistrée comme "DPO approved", "Legal approved", "Security approved", ou "Business approved". Forme canonique : "APPROVED by operator acting as product, security, privacy, legal, and business decision owner for this solo project stage".

---

## 2. Scope et non-goals

### 2.1 Scope

Le plan couvre :

- Flow de souscription Portal → Approval → Provisioning → Gateway.
- Registration, listing et invocation MCP Tools.
- Enforcement gateway Rust.
- Audit log CP-API.
- Chaîne audit Gateway → CP.
- Runtime enforcement `requires_human_approval`.
- State machine subscription.
- Formalisation ADR de la doctrine actuellement non versionnée.

### 2.2 Non-goals

Le plan ne couvre pas :

- Refonte UX complète du Portal/Console.
- Changement du modèle économique des plans ou quotas.
- Réécriture complète du gateway.
- Remplacement d’OpenSearch.
- Certification réglementaire formelle par un auditeur externe.
- Revue exhaustive des ADRs hors périmètre UAC/MCP/audit/gateway.

---

## 3. Findings bloquants à fermer

### 3.1 P0 blockers

| ID | Domaine | Finding | Fichier / zone | Correction cible |
|---|---|---|---|---|
| P0-GW-1 | Gateway | CP injoignable → permissions tool `allow-all` | `stoa-gateway/src/control_plane/tool_permissions.rs:88-96` | Default deny + circuit breaker + readiness degraded/fail |
| P0-MCP-1 | MCP runtime | `requires_human_approval=true` ignoré à l’exécution | `stoa-gateway/src/mcp/handlers.rs:354-390` | Gate pre-exec + approval token CP |
| P0-AUD-1 | Audit DB | `erase_user_pii()` fait des `UPDATE audit_events` | `control-plane-api/src/services/audit_service.py:420-461` | Trigger immutabilité + table d’effacement pseudonymisée séparée |
| P0-AUD-2 | Audit chain | Gateway émet uniquement vers tracing local | Gateway + CP-API internal endpoint absent | `/v1/internal/audit/emit` + client gateway + retry |
| P0-SUB-1 | Subscription | Deprovision one-shot, pas de retry | `services/provisioning_service.py:341-380` | `REVOKING/DEPROVISIONING` + retry persistant + alerte |
| P0-SUB-2 | Subscription | TTL extension `flush()` sans `commit()` | `routers/subscriptions.py:562` | Commit explicite + test transactionnel |

### 3.2 Gates de conformité visés

| Gate | État audit | État cible Phase 0/1 |
|---|---|---|
| G1 Audit log immutable | FAIL | PASS en Phase 0 |
| G2 Gateway → CP audit chain | FAIL | PASS en Phase 1 |
| G3 Fail-closed CP injoignable | FAIL | PASS en Phase 0 |
| G4 Destructive → approval runtime | FAIL | PASS en Phase 0 |
| G5 Retention 5 ans schedulée | PARTIAL | PASS en Phase 1 |
| G6 Schema validation runtime UAC | PARTIAL | PASS en Phase 1 |
| G7 Revocation latency < 5 min | PARTIAL | PASS en Phase 2 |
| G8 Session tracking actor | PARTIAL | PASS en Phase 2 |
| G9 State machine subscription unifiée | PARTIAL | PASS en Phase 2 |
| G10 Approval justification + diff | PARTIAL | PASS en Phase 2 |
| G11 Actor identification | PASS | Maintenu |
| G12 Resource taxonomy | PASS | Maintenu |

---

## 4. Principes de design obligatoires

### 4.1 Fail-closed par défaut

Tout chemin qui manque d’information d’autorisation doit refuser.

Règles :

- Permission absente = deny.
- CP unreachable + cache absent = deny.
- CP unreachable + cache expiré = deny.
- Policy file absent/corrompu en production = boot fail.
- Classification “Very High” = block, pas log-only.
- Readiness doit refléter l’état réel d’enforcement.

### 4.2 Doctrine exécutée au runtime

Une règle documentée n’est conforme que si elle est appliquée au chemin d’exécution.

Règles :

- `requires_human_approval=true` doit bloquer `tools/call` sans approval token valide.
- `side_effects` et `safe_for_agents` doivent être exposés dans `tools/list` comme champs typés.
- Les annotations MCP doivent dériver du contrat UAC, pas de heuristiques `operation_id`.

### 4.3 Audit append-only

`audit_events` doit être considéré append-only.

Règles :

- `UPDATE audit_events` interdit.
- `DELETE audit_events` interdit.
- Toute correction doit passer par append compensatoire ou table auxiliaire.
- Toute demande GDPR d’effacement doit être représentée sans altérer la preuve historique.
- Les mutations d’audit doivent être prouvées par test DB, pas seulement par convention applicative.

### 4.4 Preuve avant conformité déclarée

Chaque gate DORA/NIS2 doit avoir au moins :

- Un test unitaire ou d’intégration.
- Un smoke test bout-en-bout si le gate traverse CP + Gateway.
- Une preuve observable dans log/audit.
- Une entrée ADR ou plan si le comportement est doctrinal.

### 4.5 State machine lisible par produit et ops

Un utilisateur ou opérateur ne doit pas voir `ACTIVE` si l’appel gateway n’est pas prêt.

Règles :

- Ne pas confondre approval métier et provisioning technique.
- Exposer explicitement `PROVISIONING`, `READY`, `REVOKING`, `DEPROVISIONING`, `REVOKED`, `FAILED`.
- Toute transition asynchrone doit être auditée.

---

## 5. Phase 0 — Blockers DORA/NIS2

**Fenêtre : semaines 1-2 après Decision Gate.**  
**Objectif : fermer les P0 sans refonte large.**

### 5.1 P0-1 — Gateway fail-closed sur CP injoignable

**Problème**  
Le gateway tombe en `allow-all` quand les permissions CP sont indisponibles ou non renseignées.

**Design cible**

Introduire un état explicite de permissions :

```text
PermissionState =
  Fresh(policy_version, expires_at, explicit_allow_set)
  Stale(policy_version, expired_at, explicit_allow_set)
  Unavailable(reason)
```

Règles :

```text
if tool_name in Fresh.explicit_allow_set:
    allow
else:
    deny

if state == Stale:
    deny new calls
    emit audit deny reason=permission_cache_expired

if state == Unavailable:
    deny
    readiness = fail or degraded according to deployment profile
```

**Fichiers**

- `stoa-gateway/src/control_plane/tool_permissions.rs`
- `stoa-gateway/src/handlers/admin/health.rs`
- Tests Rust nouveaux.

**Tests requis**

- `test_tool_permissions_cp_unreachable_denies.rs`
- `test_tool_permissions_missing_tool_denies.rs`
- `test_tool_permissions_expired_cache_denies.rs`
- `test_gateway_readiness_fails_when_cp_permission_state_unavailable.rs`

**Acceptance criteria**

- Aucun chemin `unwrap_or(&true)` ne subsiste sur permissions.
- CP down sans cache frais → `tools/call` retourne 403 ou 503 selon design final, jamais allow.
- Readiness reflète l’état non conforme.
- Un événement audit gateway est émis, même si le flush CP est retryé en arrière-plan.

---

### 5.2 P0-2 — Gateway policy engine fail-closed au boot

**Problème**  
Policy file absent ou invalide crée un moteur permissif `enabled=false`.

**Design cible**

En profil production :

- policy file absent = boot failure.
- policy file corrompu = boot failure.
- OPA/policy disabled explicitement = interdit sauf profil dev/test.
- readiness = FAIL si policy non chargée.

**Fichiers**

- `stoa-gateway/src/state.rs`
- `stoa-gateway/src/config.rs`
- `stoa-gateway/src/handlers/admin/health.rs`

**Tests requis**

- `test_gateway_boot_fails_when_policy_file_missing_in_prod.rs`
- `test_gateway_boot_fails_when_policy_file_corrupt_in_prod.rs`
- `test_gateway_allows_policy_disabled_only_in_dev_profile.rs`

**Acceptance criteria**

- Plus aucun fallback silencieux vers permissive mode.
- Le mode dev/test est explicite et impossible à activer par omission en prod.
- L’état policy est visible dans health/readiness.

---

### 5.3 P0-3 — Destructive → approval enforcement runtime

**Problème**  
Le contrat UAC peut déclarer `requires_human_approval=true`, mais le gateway ne bloque pas l’exécution.

**Design cible**

Ajouter une phase pre-exec dans `tools/call` :

```text
auth
rate-limit
OPA/policy
approval gate  <-- nouveau
schema validation
execution
metering
audit emit
```

**Approval gate**

Si `tool.requires_human_approval == true` :

1. Exiger `X-Approval-Token`.
2. Vérifier signature CP.
3. Vérifier `aud=gateway`.
4. Vérifier `tenant_id`.
5. Vérifier `tool_name`.
6. Vérifier `tool_call_id`.
7. Vérifier TTL court.
8. Vérifier `jti` single-use.
9. Auditer allow/deny.

**Claims minimaux du JWT**

```json
{
  "iss": "control-plane-api",
  "aud": "stoa-gateway",
  "tenant_id": "tenant-id",
  "tool_name": "tenant:contract:operation",
  "tool_call_id": "uuid",
  "approval_id": "uuid",
  "approver_actor_id": "user-id",
  "approval_level": "human" ,
  "policy_version": "version",
  "iat": 0,
  "exp": 0,
  "jti": "uuid"
}
```

**Fichiers**

- `stoa-gateway/src/mcp/handlers.rs`
- `stoa-gateway/src/mcp/tools/mod.rs`
- Nouveau module `approval_token.rs`
- CP-API endpoint ou service d’émission token.

**Tests requis**

- `test_destructive_tool_without_approval_token_denies.rs`
- `test_destructive_tool_with_invalid_approval_token_denies.rs`
- `test_destructive_tool_with_wrong_tool_name_token_denies.rs`
- `test_destructive_tool_with_valid_single_use_token_allows_once.rs`
- `test_non_destructive_tool_does_not_require_approval_token.rs`

**Acceptance criteria**

- Tout destructive call sans token → 403.
- 403 produit un audit event structuré.
- Token valide single-use → allow une seule fois.
- La doctrine ADR-067 est exécutée au runtime, pas seulement décrite.

---

### 5.4 P0-4 — Audit log immutabilité DB

**Problème**  
`erase_user_pii()` modifie `audit_events`, contredisant l’append-only déclaré.

**Design cible**

1. Créer table séparée :

```sql
pseudonymized_audit_erasures (
  id uuid primary key,
  audit_event_id uuid not null,
  actor_id_original_hash text not null,
  tenant_id uuid,
  erasure_subject_id uuid not null,
  erasure_reason text not null,
  requested_by uuid not null,
  created_at timestamptz not null default now(),
  correlation_id uuid,
  metadata jsonb not null default '{}'
)
```

2. Ajouter trigger :

```sql
CREATE OR REPLACE FUNCTION prevent_audit_events_mutation()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only: UPDATE/DELETE forbidden';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_immutable_update
BEFORE UPDATE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_events_mutation();

CREATE TRIGGER audit_events_immutable_delete
BEFORE DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_events_mutation();
```

3. Réécrire `erase_user_pii()` :

```text
Before:
  UPDATE audit_events SET actor_id = null, details = redacted ...

After:
  INSERT pseudonymized_audit_erasures (...)
  INSERT audit_events(action='AUDIT_PII_ERASURE_RECORDED', ...)
  No UPDATE/DELETE on audit_events
```

**Fichiers**

- Nouvelle migration Alembic.
- `control-plane-api/src/services/audit_service.py`
- Tests DB.

**Tests requis**

- `test_update_audit_events_raises_pg_exception.py`
- `test_delete_audit_events_raises_pg_exception.py`
- `test_erase_user_pii_does_not_update_audit_events.py`
- `test_erase_user_pii_records_pseudonymized_erasure.py`
- `test_erasure_request_appends_audit_event.py`

**Acceptance criteria**

- `UPDATE audit_events` échoue au niveau PostgreSQL.
- `DELETE audit_events` échoue au niveau PostgreSQL.
- `erase_user_pii()` ne mute jamais `audit_events`.
- Le conflit GDPR/DORA est documenté dans ADR-069 avant merge.

**Point à trancher au Gate**

Le trigger doit-il être temporairement désactivable pour migrations contrôlées ?  
Recommandation par défaut : **non en production**, sauf procédure break-glass formalisée et auditée.

---

### 5.5 P0-5 — Deprovision retry loop

**Problème**  
Une révocation CP peut laisser la route gateway active si le gateway est down au moment du revoke.

**Design cible**

Introduire un état persistant :

```text
ACTIVE
  -> REVOKING
  -> DEPROVISIONING
  -> REVOKED

Failure:
  -> DEPROVISION_FAILED
  -> retry scheduled
  -> ops alert if retry budget exhausted
```

Comportement :

- Dès `REVOKING`, CP doit considérer la souscription non utilisable.
- Gateway doit recevoir invalidation.
- Si gateway unreachable, retry exponentiel.
- Tant que l’ack gateway n’est pas reçu, état visible `DEPROVISIONING` ou `DEPROVISION_FAILED`.

**Fichiers**

- `control-plane-api/src/services/provisioning_service.py`
- `control-plane-api/src/models/subscriptions.py`
- `control-plane-api/src/routers/subscriptions.py`
- Migration éventuelle.

**Tests requis**

- `test_revoke_enters_reoking_or_deprovisioning_state.py`
- `test_deprovision_retries_when_gateway_unreachable.py`
- `test_deprovision_exhausted_retries_emits_ops_alert.py`
- `test_revoked_only_after_gateway_ack.py`

**Acceptance criteria**

- Plus de révocation one-shot silencieuse.
- Le statut produit ne ment pas sur l’état gateway.
- Les échecs de deprovision sont auditables.

---

### 5.6 P0-6 — TTL extension commit explicite

**Problème**  
`flush()` ne garantit pas la persistance si une étape suivante échoue.

**Design cible**

Remplacer le `flush()` par une transaction explicite :

```text
validate extension
mutate subscription ttl
append audit event
commit
emit webhook after commit
```

**Fichiers**

- `control-plane-api/src/routers/subscriptions.py`

**Tests requis**

- `test_ttl_extension_commits_before_post_commit_side_effects.py`
- `test_ttl_extension_rollback_does_not_emit_webhook.py`

**Acceptance criteria**

- L’extension TTL est atomique.
- Les side-effects externes ne partent qu’après commit DB.
- Les échecs post-commit ne rollbackent pas le TTL.

---

## 6. Phase 1 — Chaîne audit, observabilité, validation runtime

**Fenêtre : semaines 3-5.**  
**Objectif : passer de “P0 fermé localement” à “preuve bout-en-bout”.**

### 6.1 P1-1 — Endpoint CP `/v1/internal/audit/emit`

**Design cible**

Créer un endpoint inter-service côté CP-API.

```http
POST /v1/internal/audit/emit
Authorization: HMAC-SHA256 ...
Idempotency-Key: ...
Content-Type: application/json
```

Payload minimal :

```json
{
  "source": "stoa-gateway",
  "event_type": "TOOL_CALL_DECISION",
  "decision": "allow|deny",
  "reason": "string",
  "tenant_id": "uuid",
  "actor_id": "uuid|null",
  "session_id": "string|null",
  "resource_type": "mcp_tool",
  "resource_id": "tool_name",
  "tool_call_id": "uuid",
  "approval_id": "uuid|null",
  "policy_version": "string|null",
  "correlation_id": "uuid",
  "occurred_at": "ISO8601 UTC",
  "details": {}
}
```

Gateway client :

- Buffer mémoire borné.
- Retry async avec backoff.
- Idempotency key.
- Métrique `gateway_audit_emit_lag_seconds`.
- Métrique `gateway_audit_emit_dropped_total`.

Acceptance criteria :

- Allow/deny gateway visible dans CP audit.
- Refus rate-limit, RBAC, OPA, approval gate, schema validation tous audités.
- Perte audit visible par métrique et alerte.

---

### 6.2 P1-2 — Métadonnées LLM typées dans `tools/list`

**Design cible**

`tools/list` doit exposer :

```json
{
  "name": "tenant:contract:operation",
  "description": "...",
  "inputSchema": {},
  "annotations": {
    "side_effects": "none|read|write|destructive",
    "safe_for_agents": true,
    "requires_human_approval": false,
    "destructive_hint": false,
    "contract_version": "string",
    "tenant_id": "uuid"
  }
}
```

Acceptance criteria :

- Plus besoin de regex dans `description`.
- `requires_human_approval` est un champ machine-readable.
- Les annotations proviennent du contrat UAC.

---

### 6.3 P1-3 — UAC contract as source of truth

Actions :

- Supprimer fallback `Action::from_operation_id` pour destructive inference.
- Charger `side_effects` depuis UAC.
- Aligner `destructive_hint` sur `side_effects == destructive`.
- Refuser la publication si champ absent pour endpoints à effet de bord.

Tests :

- `test_destructive_hint_comes_from_uac_side_effects.rs`
- `test_operation_id_heuristic_does_not_mark_destructive.rs`
- `test_missing_side_effects_rejected_for_mutating_endpoint.py`

---

### 6.4 P1-4 — Invalidation gateway sur publish UAC

Design :

- Lorsqu’un contrat UAC est publié, CP émet un événement d’invalidation.
- Gateway force refresh du tenant.
- TTL stale-while-revalidate ne peut pas masquer un changement de sécurité critique.

Acceptance criteria :

- Changement `requires_human_approval=false -> true` pris en compte sans attendre TTL.
- Smoke test : publish UAC, list tools, call destructive sans token, 403.

---

### 6.5 P1-5 — Retention 5 ans schedulée

Design :

- `AUDIT_RETENTION_DAYS=1825` par défaut.
- Helm CronJob quotidien.
- `purge_before()` utilisé uniquement sur données purgeables, pas sur `audit_events` append-only si DORA impose conservation.
- En cas de conflit, ADR-069 tranche.

Acceptance criteria :

- CronJob déployé et monitoré.
- Dry-run disponible.
- Audit de purge généré.
- Pas de suppression silencieuse d’événements réglementaires.

---

### 6.6 P1-6 — Schema validation runtime UAC

Design :

- Valider `tools/call.arguments` contre `inputSchema`.
- Valider réponse contre `outputSchema` si défini.
- Refuser ou redacter selon stratégie documentée pour output invalid.

Acceptance criteria :

- Arguments invalides → 400/422 + audit deny.
- Output invalid → audit event + stratégie déterministe.
- Tests sur schémas nested, required fields, additionalProperties.

---

### 6.7 P1-7 — Webhooks suspend/reactivate

Actions :

- Émettre webhook Kafka pour `SUSPENDED`.
- Émettre webhook Kafka pour `REACTIVATED`.
- Ajouter audit events structurés.
- Ajouter correlation_id.

Acceptance criteria :

- Suspend/reactivate visible en forensic externe.
- Tests existants “does not emit webhook” supprimés ou inversés.

---

### 6.8 P1-8 — Classification Very High en mode block

Actions :

- Remplacer “log only, do NOT deny” par block.
- Ajouter override break-glass si nécessaire, mais seulement avec audit renforcé.

Acceptance criteria :

- Route VH non autorisée → deny.
- Break-glass exige justification, actor, TTL, audit.
- Readiness/config expose le mode.

---

## 7. Phase 2 — Workflow approval auditable + state machine

**Fenêtre : semaines 6-9.**  
**Objectif : rendre le workflow prouvable par un auditeur externe.**

### 7.1 P2-1 — State machine subscription unifiée

State machine cible :

```text
DRAFT
  -> PENDING_APPROVAL
  -> REJECTED

PENDING_APPROVAL
  -> APPROVED
  -> PROVISIONING
  -> READY
  -> ACTIVE

ACTIVE
  -> SUSPENDED
  -> REVOKING
  -> EXPIRED

SUSPENDED
  -> ACTIVE
  -> REVOKING

REVOKING
  -> DEPROVISIONING
  -> REVOKED

Failure states:
  PROVISIONING_FAILED
  DEPROVISIONING_FAILED
```

Règles :

- `ACTIVE` signifie utilisable côté gateway.
- `READY` signifie gateway ack reçu, activation possible.
- `REVOKED` signifie gateway ack de révocation reçu.
- `DEPROVISIONING_FAILED` ne doit pas être masqué.

Acceptance criteria :

- `status` absorbe `provisioning_status` ou ce dernier devient internal-only clairement documenté.
- Migration avec mapping des états existants.
- UI/API ne présente plus `ACTIVE` pendant provisioning.

---

### 7.2 P2-2 — Approval justification + diff before/after

Actions :

- Ajouter `approval_justification`.
- Ajouter `approval_diff` JSONB.
- Stocker approver actor/session/IP.
- Exiger justification non vide pour approvals manuels.
- Pour destructive endpoints, exiger enhanced approval si ADR-067 le décide.

Acceptance criteria :

- `SUBSCRIPTION_APPROVED` contient justification et diff.
- `TOOL_APPROVAL_GRANTED` contient approver, scope, TTL, target tool_call.
- Diff before/after lisible par SOC.

---

### 7.3 P2-3 — Session tracking actor

Actions :

- Ajouter colonne `session_id` à `audit_events`.
- Hydrater depuis middleware auth.
- Propager correlation_id + session_id vers gateway quand applicable.

Acceptance criteria :

- Actor = user + tenant + session + IP pour mutations critiques.
- OpenSearch et PostgreSQL alignés.
- Tests middleware.

---

### 7.4 P2-4 — Subscribe/stream gateway ↔ CP

Design cible :

- Remplacer ou compléter poll 60s par stream/subscribe.
- Invalidation révocation prioritaire.
- Ack gateway requis pour transition `REVOKED`.
- Latence mesurée et alerte si > 5 min.

Acceptance criteria :

- Revoke CP → deny gateway < 5 min mesuré par smoke.
- Aucun fallback cached allow après révocation explicite.
- Métrique `revocation_propagation_seconds`.

---

### 7.5 P2-5 — Hash chain ou WORM signé

Options à trancher :

| Option | Avantages | Inconvénients |
|---|---|---|
| Hash chain PostgreSQL | Preuve locale continue | Complexifie corrections et backfills |
| Export WORM signé | Robuste pour audit externe | Latence entre event et preuve WORM |
| Les deux | Meilleure défense | Coût plus élevé |

Recommandation draft :

- Phase 2 : hash chain sur `audit_events`.
- Export quotidien signé vers stockage WORM si disponible infra.

Acceptance criteria :

- Un event ne peut pas être altéré sans briser la chaîne.
- Export signé vérifiable.
- Tests de vérification de chaîne.

---

### 7.6 P2-6 — Approval token CP single-use

Compléter P0-3 avec :

- Store `approval_tokens` ou `approval_grants`.
- `jti` single-use.
- Expiration courte.
- Revocation possible.
- Audit `APPROVAL_TOKEN_ISSUED`, `APPROVAL_TOKEN_USED`, `APPROVAL_TOKEN_REJECTED`.

Acceptance criteria :

- Rejeu token refusé.
- Token expiré refusé.
- Token mauvais tenant/tool refusé.
- Tout refus audité.

---

## 8. ADRs à formaliser

### 8.1 ADR-071 — API subscription lifecycle

> **2026-05-13 reconciliation note.** L'ancienne entrée "ADR-001 — API exposure strategy" est obsolète : ADR-001 existe déjà (Accepted 2026-01-18) et reste **predecessor non amendé**. Le manque réel = lifecycle souscription, traité par un ADR neuf (ADR-071) qui étend ADR-001 sans le modifier.

But :

- Formaliser le flow producer → subscription → consumer **à l'intérieur** de l'architecture définie par ADR-001.
- Définir la state machine unifiée (`REQUESTED → PENDING → APPROVED → PROVISIONING → ACTIVE → REVOKING → REVOKED`) + états dégradés (`PARTIALLY_PROVISIONED`, `PROVISIONING_FAILED`, `DEPROVISIONING_FAILED`, `SUSPENDED`).
- Définir le modèle per-target ack pour les déploiements multi-gateway / multi-region.
- Définir la matrice RBAC (consumer tenant-admin requête, producer tenant-admin approuve, 4-eyes pour API exposant des destructive endpoints).
- Définir l'émission audit obligatoire à chaque transition.

Statut cible : `accepted` avant Phase 2.

Draft : `docs/audits/2026-05-11-uac-subscription-mcp/adrs-drafts/adr-071-api-subscription-lifecycle.md`.

---

### 8.2 ADR-067 — UAC describes / MCP projects / Smoke proves

But :

- Sortir la doctrine de `.claude/docs/`.
- Définir les trois piliers :
  - UAC describes.
  - MCP projects.
  - Smoke proves.
- Définir les champs obligatoires : `side_effects`, `safe_for_agents`, `requires_human_approval`.
- Définir l’enforcement runtime.

Statut cible : `accepted` avant merge P0-3.

---

### 8.3 ADR-068 — Audit log actor/resource doctrine

But :

- Formaliser `actor`, `tenant`, `session`, `resource`, `correlation_id`.
- Définir les types d’événements.
- Définir la chaîne CP ↔ Gateway.
- Définir les exigences SOC/export.

Statut cible : `accepted` avant merge P1-1.

---

### 8.4 ADR-069 — GDPR ↔ DORA audit reconciliation

But :

- Trancher `erase_user_pii`.
- Définir pseudonymisation, effacement, append-only.
- Définir le statut des tables auxiliaires.
- Définir retention et WORM.

Statut cible : `accepted` avant migration P0-4.

---

### 8.5 ADR-070 — Gateway fail-closed posture

But :

- Codifier les defaults gateway.
- Définir cache permissions.
- Définir readiness.
- Définir break-glass.
- Définir dev/test exceptions.

Statut cible : `accepted` avant merge P0-1/P0-2.

---

## 9. Plan de tests et preuves

### 9.1 Smoke tests réglementaires obligatoires

| # | Smoke | Preuve attendue |
|---|---|---|
| S1 | CP down → gateway refuses tools/call | HTTP deny + readiness fail + audit local/queued |
| S2 | Destructive call sans `X-Approval-Token` | 403 + CP audit event |
| S3 | Destructive call avec token valide | 200 + `APPROVAL_TOKEN_USED` + `TOOL_CALLED allow` |
| S4 | Rejeu token | 403 + audit reject |
| S5 | `UPDATE audit_events` | exception PostgreSQL |
| S6 | `erase_user_pii` | `audit_events` inchangé + table erasure alimentée |
| S7 | Gateway deny OPA/rate/RBAC | audit Gateway→CP présent |
| S8 | Revoke CP | gateway deny < 5 min |
| S9 | `tools/list` | metadata typées présentes |
| S10 | Suspend/reactivate | audit + Kafka event |
| S11 | UAC publish change approval | invalidation gateway immédiate |
| S12 | Retention CronJob dry-run | rapport + audit de purge |

### 9.2 Tests unitaires/integration par composant

#### CP-API

- Audit service immutability.
- Erasure service.
- Subscription state machine.
- Approval justification/diff.
- Internal audit endpoint HMAC.
- Retention CronJob.
- Webhook suspend/reactivate.
- UAC publish invalidation.

#### Gateway Rust

- Tool permissions fail-closed.
- Policy boot fail.
- Approval gate.
- JWT validation.
- MCP `tools/list` metadata.
- Runtime schema validation.
- Audit client retry/buffer.
- Revocation invalidation.

#### E2E

- Subscription approval → provisioning → gateway active.
- Destructive tool approval path.
- Revocation propagation.
- CP outage posture.
- Audit export forensic reconstruction.

### 9.3 Definition of Done globale

Le plan est terminé seulement si :

- Les 12 gates DORA/NIS2 sont PASS ou explicitement acceptées avec justification externe.
- Les 4 P0 FAIL sont fermés par tests.
- Les ADR-067/068/069/070 sont versionnées.
- Le smoke suite est automatisé en CI ou environnement pré-prod.
- Le challenger externe signe un Decision Record final.
- Le runbook ops décrit fail-closed, break-glass, audit replay, revocation failed.

---

## 10. Registre risques

| Risque | Probabilité | Impact | Mitigation |
|---|---:|---:|---|
| Fail-closed provoque indisponibilité client lors d’un incident CP | Élevée | Élevé | Circuit breaker, status page, runbook, cache frais strict, communication business |
| Trigger audit bloque migration légitime | Moyenne | Élevé | Procédure migration dédiée, tests staging, break-glass audité si accepté par ADR-069 |
| Approval token ralentit agents IA | Moyenne | Moyen | UX approval claire, TTL court mais réaliste, erreurs explicites |
| Gateway audit buffer perd des events | Moyenne | Élevé | Buffer borné + métrique drop + alerte + option durable queue |
| State machine migration casse UI/API | Moyenne | Élevé | Compatibility layer, migration progressive, tests contract |
| ADRs retardent P0 | Moyenne | Moyen | ADR minimal viable avant merge, approfondissement parallèle |
| OpenSearch/PG divergence | Moyenne | Moyen | Source of truth PG, reconciliation job |
| Revocation stream instable | Moyenne | Élevé | Poll fallback fail-closed, ack required, alerting |
| Business refuse block VH | Moyenne | Élevé | Decision Gate explicite, break-glass strictement audité |

---

## 11. Séquencement recommandé des PRs

### Gate 0

```text
PR-DOC-0: Plan correctif draft
PR-DOC-1: ADR-067 draft
PR-DOC-2: ADR-068 draft
PR-DOC-3: ADR-069 draft
PR-DOC-4: ADR-070 draft
Decision record: GO / GO_WITH_CONDITIONS / NOGO
```

### Phase 0

```text
PR-P0-1: gateway tool permissions fail-closed
PR-P0-2: gateway policy boot fail-closed
PR-P0-3: MCP approval gate runtime
PR-P0-4: audit_events immutability trigger + erase_user_pii rewrite
PR-P0-5: deprovision retry loop + states minimal
PR-P0-6: subscription TTL commit fix
```

### Phase 1

```text
PR-P1-1: CP internal audit emit endpoint
PR-P1-2: gateway audit client
PR-P1-3: tools/list typed metadata
PR-P1-4: UAC-driven annotations
PR-P1-5: UAC publish invalidation
PR-P1-6: retention CronJob
PR-P1-7: runtime schema validation
PR-P1-8: suspend/reactivate webhooks
PR-P1-9: VH block mode
```

### Phase 2

```text
PR-P2-1: subscription state machine migration
PR-P2-2: approval justification + diff
PR-P2-3: session_id audit_events
PR-P2-4: gateway subscribe/stream revocation
PR-P2-5: audit hash chain / WORM export
PR-P2-6: approval token store single-use
PR-P2-7: e2e DORA/NIS2 smoke suite
```

---

## 12. Rollback et migration

### 12.1 Règles générales

- Toute migration DB doit être testée sur snapshot anonymisé.
- Toute migration doit avoir un plan forward-fix si rollback impossible.
- Les triggers d’immutabilité doivent être validés en staging avant prod.
- Les comportements fail-closed doivent être canariés.

### 12.2 Migration audit immutability

Ordre recommandé :

1. Créer table `pseudonymized_audit_erasures`.
2. Modifier `erase_user_pii()` pour ne plus muter `audit_events`.
3. Ajouter tests applicatifs.
4. Déployer en staging.
5. Ajouter trigger immutabilité.
6. Tester `UPDATE/DELETE` bloqués.
7. Déployer prod avec surveillance.
8. Activer alertes sur exceptions mutation audit.

Rollback :

- Ne pas supprimer le trigger sans Decision Record.
- En cas de blocage, forward-fix recommandé.
- Break-glass uniquement si ADR-069 le permet.

### 12.3 Migration state machine

Ordre recommandé :

1. Ajouter nouveaux états sans supprimer anciens champs.
2. Backfill mapping.
3. Adapter API read model.
4. Adapter transitions.
5. Ajouter tests e2e.
6. Déprécier `provisioning_status`.
7. Supprimer uniquement après période de compatibilité.

---

## 13. Métriques et alertes

| Métrique | Seuil |
|---|---|
| `gateway_cp_permission_unavailable_total` | alerte immédiate en prod |
| `gateway_tool_call_denied_total{reason}` | dashboard SOC |
| `gateway_audit_emit_lag_seconds` | alerte si p95 > 60s |
| `gateway_audit_emit_dropped_total` | alerte si > 0 |
| `revocation_propagation_seconds` | alerte si > 300s |
| `audit_events_mutation_attempt_total` | alerte si > 0 |
| `approval_token_replay_denied_total` | dashboard sécurité |
| `deprovision_retry_exhausted_total` | alerte immédiate |
| `uac_publish_invalidation_lag_seconds` | alerte si p95 > 30s |

---

## 14. Runbooks à produire

| Runbook | Phase |
|---|---|
| CP outage with fail-closed gateway | Phase 0 |
| Approval token failure / replay | Phase 0 |
| Audit immutability exception | Phase 0 |
| Gateway audit emit backlog | Phase 1 |
| Revocation stuck in `DEPROVISIONING` | Phase 1/2 |
| Break-glass for VH route | Phase 1 |
| Hash chain verification | Phase 2 |
| GDPR erasure request under DORA | Phase 2 |

---

## 15. Annexes

### 15.1 Template Decision Record

```yaml
---
title: "Decision — UAC Subscription MCP Corrective Plan"
date: 2026-05-XX
source_plan: "docs/plans/2026-05-11-uac-subscription-mcp-corrective.md"
source_audit: "docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md"
decision: "GO | GO_WITH_CONDITIONS | NOGO | SPLIT_GATE"
challenger: "TBD"
validation_status: "draft | accepted | rejected"
---

# Decision

## Verdict

TBD.

## Conditions

TBD.

## Scope autorisé

TBD.

## Scope refusé / à revoir

TBD.

## Réponses aux questions du gate

1. Fail-closed acceptable ?
2. Cache permissions acceptable ?
3. Approval token suffisant ?
4. GDPR vs DORA résolu ?
5. Trigger immutabilité acceptable ?
6. State machine suffisante ?
7. Planning réaliste ?

## Sign-off

- Accountable owner:
- Security:
- Compliance:
- Gateway:
- CP-API:
- External challenger:
```

### 15.2 Checklist avant démarrage Phase 0

- [ ] Decision Record créé.
- [ ] Challenger externe assigné.
- [ ] ADR-067 draft disponible.
- [ ] ADR-068 draft disponible.
- [ ] ADR-069 draft disponible.
- [ ] ADR-070 draft disponible.
- [ ] Business owner informé de l’impact fail-closed.
- [ ] Environnement staging prêt.
- [ ] Snapshot DB anonymisé disponible.
- [ ] Smoke tests P0 définis.
- [ ] Rollback/forward-fix migration audit validé.
